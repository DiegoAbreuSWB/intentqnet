"""L4 - simulation-in-the-loop planner (planner-family study, M7).

For each candidate route, runs K internal SeQUeNCe simulations (real
executions - `execution.sequence_executor.SequenceExecutor`, the same
class every other planner level's operational deployment eventually uses)
using seeds DERIVED from the intent/topology/config, NEVER the trial's
real operational seed - see `_derive_internal_seeds` and
`tests/planning/planners/test_l4_simulation.py::test_l4_never_uses_the_operational_seed`.
Aggregates the K outcomes into a `PlannerSimulationSummary` per candidate
and admits the best one per `admission_policy`.

L4 is NOT the offline oracle (`experiments.baselines`'s retrospective
re-test of an already-rejected intent): L4 acts BEFORE the operational
trial, on distinct internal seeds, as part of planning itself - a
deployable (if expensive) planner, not a post-hoc analysis tool. It is
the high-fidelity, high-cost end of this study's planner family; P03
(M8) measures exactly how much K costs and buys.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from sequence.utils import metrics

from ...assurance.evaluator import evaluate_intent
from ...assurance.telemetry import collect_intent_evidence
from ...execution.sequence_executor import SequenceExecutor
from ...intent.models import EntanglementIntent, IntentStatus
from ...intent.repository import IntentRepository
from ...network.capabilities import NetworkCapabilities
from ...network.sequence_adapter import SequenceAdapter
from ..fidelity_estimation import ConservativeMinEstimator
from ..models import EstimatedMetrics, ExecutionPlan
from ..purification import PurifyUntilTarget
from ..resource_allocation import build_reservations
from .base import evaluate_candidates, to_candidate_evaluation
from .models import PlannerDecision, PlannerExplanation, PlanningContext

INTERNAL_SEED_BASE_OFFSET = 500_000_000
"""Large, fixed offset added to a deterministic hash-derived value so
internal planning seeds can never collide with this project's small
(0-19 or similar) operational seeds, nor with
`experiments.runner.RECONCILIATION_SEED_OFFSET` (1_000_000)."""


@dataclass(frozen=True)
class SimulationPlannerConfig:
    simulations_per_candidate: int = 10
    internal_seed_policy: str = "hash_derived"
    candidate_limit: int = 3
    time_budget_s: float | None = None
    parallelism: int = 1
    """Sequential by default (=1) - this project's SeQUeNCe simulations are
    not thread-safe across a shared `sequence.utils.metrics` singleton
    (docs/sequence_code_analysis.md, section 4.1); parallelism > 1 would
    require per-process isolation, out of scope for this milestone."""
    early_stopping: bool = False
    early_stopping_confidence: float = 0.95
    early_stopping_acceptance_threshold: float = 0.5


@dataclass(frozen=True)
class PlannerSimulationSummary:
    candidate_plan: list[str]
    n_simulations: int
    satisfaction_rate: float
    expected_delivered_pairs: float
    fidelity_distribution: list[float] = field(default_factory=list)
    throughput_distribution: list[float] = field(default_factory=list)
    simulation_wall_time_s: float = 0.0
    stopped_early: bool = False
    stopping_reason: str = ""


def _derive_internal_seeds(intent: EntanglementIntent, route: list[str], config: SimulationPlannerConfig, n: int) -> list[int]:
    """Deterministic seeds derived from (intent id, route, requirements,
    config) - NEVER the trial's operational seed. Same inputs always
    produce the same internal seeds (reproducible), different from any
    realistic operational seed by construction (see
    `INTERNAL_SEED_BASE_OFFSET`)."""
    key = (
        f"{intent.id}|{'-'.join(route)}|{intent.requirements.min_fidelity}|"
        f"{intent.requirements.reserved_memory_slots}|{intent.requirements.duration_s}|"
        f"{config.simulations_per_candidate}"
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    base = INTERNAL_SEED_BASE_OFFSET + (int(digest[:8], 16) % 100_000_000)
    return [base + i for i in range(n)]


def _wilson_ci(successes: int, n: int, confidence: float) -> tuple[float, float]:
    from scipy import stats

    if n == 0:
        return 0.0, 1.0
    p = successes / n
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def run_internal_simulations(
    capabilities: NetworkCapabilities,
    topology_spec,
    route: list[str],
    intent: EntanglementIntent,
    config: SimulationPlannerConfig,
) -> PlannerSimulationSummary:
    """Runs up to `config.simulations_per_candidate` real internal
    simulations of `route` for `intent`, on seeds derived from
    `_derive_internal_seeds` - never the operational seed. Early stopping
    (if enabled) uses a Wilson confidence interval on the running
    satisfaction rate: stops once the CI's lower bound clears
    `early_stopping_acceptance_threshold` (clearly satisfiable) or the
    upper bound falls below it (clearly not) - never merely because early
    trials happened to agree."""
    t0 = time.perf_counter()
    seeds = _derive_internal_seeds(intent, route, config, config.simulations_per_candidate)

    purification_strategy = PurifyUntilTarget()
    fidelity_estimator = ConservativeMinEstimator()
    evaluation_result = evaluate_candidates(
        capabilities, [route], intent, purification_strategy=purification_strategy, fidelity_estimator=fidelity_estimator,
    )[0]
    estimated_fidelity = (
        evaluation_result.purified_fidelity_estimate if evaluation_result.requires_purification
        else evaluation_result.swap_only_fidelity
    )
    plan = ExecutionPlan(
        intent_id=intent.id, feasible=True, route=route,
        reservations=build_reservations(route, intent.requirements.reserved_memory_slots, capabilities),
        requires_purification=evaluation_result.requires_purification,
        purification_rounds_estimate=evaluation_result.purification_rounds_estimate,
        estimated_metrics=EstimatedMetrics(fidelity=estimated_fidelity, latency_s=0.0),
        fidelity_estimator=fidelity_estimator.name,
    )

    satisfied_count = 0
    delivered_pairs_list: list[int] = []
    fidelity_list: list[float] = []
    throughput_list: list[float] = []
    stopped_early = False
    stopping_reason = ""
    n_run = 0

    for seed in seeds:
        if config.time_budget_s is not None and (time.perf_counter() - t0) >= config.time_budget_s:
            stopped_early = True
            stopping_reason = f"time_budget_s={config.time_budget_s} exhausted after {n_run} simulation(s)"
            break

        metrics.configure()
        repository = IntentRepository()
        adapter = SequenceAdapter(topology_spec, seed=seed)
        executor = SequenceExecutor(adapter, repository)
        executor.deploy(intent, plan)
        executor.run()
        n_run += 1

        status = repository.get(intent.id).lifecycle.status
        if status == IntentStatus.ACTIVE:
            evidence = collect_intent_evidence(intent)
            evaluation = evaluate_intent(intent, evidence)
            if evaluation.satisfied:
                satisfied_count += 1
            delivered = len(evidence.delivered_pairs) if evidence else 0
            delivered_pairs_list.append(delivered)
            if delivered:
                fidelities = [p.fidelity for p in evidence.delivered_pairs]
                fidelity_list.append(sum(fidelities) / len(fidelities))
                throughput_list.append(delivered / intent.requirements.duration_s)

        if config.early_stopping and n_run >= 2:
            lo, hi = _wilson_ci(satisfied_count, n_run, config.early_stopping_confidence)
            if lo > config.early_stopping_acceptance_threshold:
                stopped_early = True
                stopping_reason = (
                    f"Wilson {config.early_stopping_confidence:.0%} CI lower bound {lo:.3f} exceeds "
                    f"acceptance_threshold={config.early_stopping_acceptance_threshold} after {n_run} simulation(s)"
                )
                break
            if hi < config.early_stopping_acceptance_threshold:
                stopped_early = True
                stopping_reason = (
                    f"Wilson {config.early_stopping_confidence:.0%} CI upper bound {hi:.3f} is below "
                    f"acceptance_threshold={config.early_stopping_acceptance_threshold} after {n_run} simulation(s)"
                )
                break

    simulation_wall_time_s = time.perf_counter() - t0
    return PlannerSimulationSummary(
        candidate_plan=route, n_simulations=n_run,
        satisfaction_rate=(satisfied_count / n_run) if n_run else 0.0,
        expected_delivered_pairs=(sum(delivered_pairs_list) / len(delivered_pairs_list)) if delivered_pairs_list else 0.0,
        fidelity_distribution=fidelity_list, throughput_distribution=throughput_list,
        simulation_wall_time_s=simulation_wall_time_s, stopped_early=stopped_early, stopping_reason=stopping_reason,
    )


class SimulationInTheLoopPlanner:
    """L4: admits the candidate route with the highest internally-
    simulated satisfaction rate, provided it clears `admission_threshold`.
    Expensive (K real simulations per candidate at planning time) but the
    highest-fidelity planner level in this study before L5."""

    name = "simulation_in_the_loop"
    level = "L4"

    def __init__(self, *, config: SimulationPlannerConfig | None = None, admission_threshold: float = 0.5):
        self._config = config or SimulationPlannerConfig()
        self._admission_threshold = admission_threshold

    def plan(
        self,
        intent: EntanglementIntent,
        network_state: NetworkCapabilities,
        candidate_paths: list[list[str]],
        context: PlanningContext,
    ) -> PlannerDecision:
        t0 = time.perf_counter()
        limited_candidates = candidate_paths[: self._config.candidate_limit]

        candidate_evaluations = []
        summaries: dict[tuple[str, ...], PlannerSimulationSummary] = {}
        if limited_candidates:
            purification_strategy = PurifyUntilTarget()
            fidelity_estimator = ConservativeMinEstimator()
            evaluations = evaluate_candidates(
                network_state, limited_candidates, intent,
                purification_strategy=purification_strategy, fidelity_estimator=fidelity_estimator,
            )
            candidate_evaluations = [to_candidate_evaluation(e) for e in evaluations]

            topology_spec = context.topology_spec
            for route in limited_candidates:
                summaries[tuple(route)] = run_internal_simulations(
                    network_state, topology_spec, route, intent, self._config,
                )

        planning_wall_time_s = time.perf_counter() - t0

        admissible = [
            (route, summaries[tuple(route)]) for route in limited_candidates
            if summaries[tuple(route)].satisfaction_rate >= self._admission_threshold
        ]

        if not admissible:
            reason = (
                f"no path found from '{intent.endpoints.source}' to '{intent.endpoints.destination}'"
                if not candidate_paths else
                f"no candidate cleared admission_threshold={self._admission_threshold} "
                f"across {len(limited_candidates)} simulated candidate(s)"
            )
            plan = ExecutionPlan.infeasible(intent.id, reason)
            explanation = PlannerExplanation(
                summary=f"rejected: {reason}",
                decisive_factors=[f"internally-simulated satisfaction rate below {self._admission_threshold}"],
                limiting_constraints=[f"simulations_per_candidate={self._config.simulations_per_candidate}"],
            )
            return PlannerDecision(
                planner_name=self.name, planner_level=self.level, feasible=False, selected_plan=plan,
                candidate_evaluations=candidate_evaluations, rejection_reason=reason,
                assumptions=f"K={self._config.simulations_per_candidate} internal simulations per candidate, seeds "
                            "derived from intent/route/config, never the operational seed",
                planning_wall_time_s=planning_wall_time_s, explanation=explanation,
            )

        best_route, best_summary = max(admissible, key=lambda item: item[1].satisfaction_rate)
        best_feasibility = next(e for r, e in zip(limited_candidates, evaluations) if r == best_route)
        estimated_fidelity = (
            best_feasibility.purified_fidelity_estimate if best_feasibility.requires_purification
            else best_feasibility.swap_only_fidelity
        )
        from ..feasibility import estimate_latency_s
        plan = ExecutionPlan(
            intent_id=intent.id, feasible=True, route=best_route,
            route_rationale=(
                f"selected by L4: internally-simulated satisfaction rate {best_summary.satisfaction_rate:.3f} "
                f"over {best_summary.n_simulations} simulations"
            ),
            reservations=best_feasibility.reservations, requires_purification=best_feasibility.requires_purification,
            purification_rounds_estimate=best_feasibility.purification_rounds_estimate,
            estimated_metrics=EstimatedMetrics(
                fidelity=estimated_fidelity, latency_s=estimate_latency_s(network_state, best_route),
            ),
            fidelity_estimator=fidelity_estimator.name,
            fallback_routes=[r for r, _ in admissible if r != best_route],
        )
        explanation = PlannerExplanation(
            summary=(
                f"accepted route {' -> '.join(best_route)}: {best_summary.n_simulations} internal simulations, "
                f"satisfaction rate {best_summary.satisfaction_rate:.3f}"
                + (f" ({best_summary.stopping_reason})" if best_summary.stopped_early else "")
            ),
            decisive_factors=[f"n_simulations={best_summary.n_simulations}", f"satisfaction_rate={best_summary.satisfaction_rate:.3f}"],
            limiting_constraints=[f"admission_threshold={self._admission_threshold}"],
        )
        return PlannerDecision(
            planner_name=self.name, planner_level=self.level, feasible=True, selected_plan=plan,
            candidate_evaluations=candidate_evaluations,
            predicted_satisfaction_probability=best_summary.satisfaction_rate,
            predicted_delivered_pairs=best_summary.expected_delivered_pairs,
            predicted_average_fidelity=estimated_fidelity, predicted_minimum_fidelity=estimated_fidelity,
            assumptions=f"K={self._config.simulations_per_candidate} internal simulations per candidate, seeds "
                        "derived from intent/route/config, never the operational seed",
            planning_wall_time_s=planning_wall_time_s, explanation=explanation,
        )
