"""Executes a `Scenario` end-to-end: builds the topology, plans and deploys
every intent it declares, runs the simulation once, evaluates each intent
that became `ACTIVE` against its own declared success conditions, and
collects results straight from `IntentRepository`/`sequence.utils.metrics` -
never computed independently of the simulation (see
docs/sequence_code_analysis.md, section 2 constraints).

No intent leaves `run_scenario` sitting in `ACTIVE` with `satisfied=None`:
every intent that reaches `ACTIVE` is evaluated and transitioned to
`SATISFIED`/`VIOLATED` before results are returned (see
docs/assurance_design.md, section 9). Intents that never reached `ACTIVE`
(`REJECTED`/`FAILED`) have no delivery evidence to judge, so `evaluation`
stays `None` for them.
"""
from __future__ import annotations

import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sequence.constants import SECOND
from sequence.utils import metrics

from ..assurance.evaluator import IntentEvaluation, evaluate_intent
from ..assurance.reconciliation import reconcile
from ..assurance.telemetry import IntentEvidence, collect_intent_evidence
from ..demos.environment import collect_environment_info
from ..execution.sequence_executor import SequenceExecutor
from ..intent.models import EntanglementIntent, IntentStatus
from ..intent.parser import load_intent_file
from ..intent.repository import IntentRepository
from ..network.capabilities import NetworkCapabilities
from ..network.sequence_adapter import SequenceAdapter
from ..planning.models import ExecutionPlan
from ..planning.planner import IntentPlanner
from ..planning.purification import PurificationStrategy
from ..planning.routing import RoutingStrategy
from ..planning.swapping import SwappingStrategy
from ..utils.logging import get_logger
from .campaigns import CampaignSpec
from .manifests import build_initial_manifest, manifest_path, read_manifest, update_manifest_progress, write_manifest
from .persistence import append_error_record, append_trial_record, errors_jsonl_path, read_trial_ids, trials_csv_path
from .records import TrialIdentity, TrialRecord
from .scenarios import Scenario
from .sweeps import (
    TrialParameters,
    apply_parameters,
    compute_parameter_hash,
    expand_parameter_grid,
    resolve_purification_policy,
    resolve_routing_strategy,
)

logger = get_logger(__name__)

RECONCILIATION_SEED_OFFSET = 1_000_000


@dataclass
class IntentRunResult:
    intent_id: str
    final_status: IntentStatus
    satisfied: bool | None
    plan: ExecutionPlan
    evaluation: IntentEvaluation | None = None
    metrics: dict = field(default_factory=dict)


@dataclass
class ScenarioResult:
    scenario_name: str
    seed: int
    intent_results: list[IntentRunResult]

    def get(self, intent_id: str) -> IntentRunResult:
        try:
            return next(r for r in self.intent_results if r.intent_id == intent_id)
        except StopIteration:
            raise KeyError(f"no result for intent '{intent_id}' in this scenario run") from None


def run_scenario(
    scenario: Scenario,
    *,
    seed: int | None = None,
    routing_strategy: RoutingStrategy | None = None,
    purification_strategy: PurificationStrategy | None = None,
    swapping_strategy: SwappingStrategy | None = None,
) -> ScenarioResult:
    """Builds a fresh `SequenceAdapter` + `IntentPlanner` + `SequenceExecutor`
    for `scenario`, plans and deploys every declared intent, runs the
    simulation once, evaluates each intent that reached `ACTIVE` against its
    own `validation.success_conditions`, and returns each intent's final
    status/evaluation/plan/metrics.

    `sequence.utils.metrics` is a process-wide singleton
    (docs/sequence_code_analysis.md, section 4.1) - reset at the start of
    every call so repeated trials (see `experiments.seeds`) don't leak into
    each other.
    """
    metrics.configure()
    metrics.reset_metrics()

    effective_seed = seed if seed is not None else scenario.spec.simulation.seed
    topology_spec = scenario.topology_spec()
    capabilities = NetworkCapabilities(topology_spec)
    adapter = SequenceAdapter(topology_spec, seed=effective_seed)
    planner = IntentPlanner(
        capabilities,
        routing_strategy=routing_strategy,
        purification_strategy=purification_strategy,
        swapping_strategy=swapping_strategy,
    )
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)

    plans: dict[str, ExecutionPlan] = {}
    for intent in scenario.intents:
        plan = planner.plan(intent)
        plans[intent.id] = plan
        executor.deploy(intent, plan)

    logger.info(
        "running scenario '%s', seed=%d, %d intent(s)",
        scenario.spec.name, effective_seed, len(scenario.intents),
    )
    executor.run()

    results = []
    for intent in scenario.intents:
        record = repository.get(intent.id)
        evaluation: IntentEvaluation | None = None

        if record.lifecycle.status == IntentStatus.ACTIVE:
            evidence = collect_intent_evidence(intent)
            evaluation = evaluate_intent(intent, evidence)
            final_status = IntentStatus.SATISFIED if evaluation.satisfied else IntentStatus.VIOLATED
            reason = "all success conditions met" if evaluation.satisfied else "; ".join(evaluation.violations)
            repository.transition(intent.id, final_status, reason, sim_time=adapter.get_timeline().now() / SECOND)
            record = repository.get(intent.id)

        satisfied = evaluation.satisfied if evaluation is not None else (
            record.result.satisfied if record.result else None
        )
        trial_metrics = metrics.collect_trial_metrics(intent.endpoints.source)
        results.append(
            IntentRunResult(
                intent_id=intent.id,
                final_status=record.lifecycle.status,
                satisfied=satisfied,
                plan=plans[intent.id],
                evaluation=evaluation,
                metrics=trial_metrics,
            )
        )

    return ScenarioResult(scenario_name=scenario.spec.name, seed=effective_seed, intent_results=results)


# ============================================================================
# Campaign execution (Fase H3, see docs/campaign_architecture.md)
# ============================================================================


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _delivery_metrics(
    evidence: IntentEvidence | None, *, requested_pairs: int, duration_s: float, start_time_s: float,
) -> dict:
    """Derives every delivery-based `TrialRecord` field from `evidence` -
    `None` (not `0`) whenever there is genuinely no evidence to derive
    from (see docs/metrics.md and docs/campaign_architecture.md, section 4).
    `evidence is None` means no episode ran at all (e.g. reconciliation's
    replan was infeasible); an empty `evidence.delivered_pairs` means an
    episode ran but delivered nothing - both are distinct from "not
    applicable"."""
    if evidence is None:
        return {
            "delivered_pairs": None, "excess_delivery_pairs": None, "delivery_ratio": None,
            "average_fidelity": None, "minimum_fidelity": None,
            "throughput_active_window": None, "throughput_delivery_interval": None,
            "first_pair_latency_s": None, "completion_time_s": None,
        }

    pairs = evidence.delivered_pairs
    delivered = len(pairs)
    if not pairs:
        return {
            "delivered_pairs": 0, "excess_delivery_pairs": 0, "delivery_ratio": 0.0,
            "average_fidelity": None, "minimum_fidelity": None,
            "throughput_active_window": 0.0, "throughput_delivery_interval": None,
            "first_pair_latency_s": None, "completion_time_s": None,
        }

    fidelities = [p.fidelity for p in pairs]
    first_time, last_time = pairs[0].sim_time_s, pairs[-1].sim_time_s
    return {
        "delivered_pairs": delivered,
        "excess_delivery_pairs": max(0, delivered - requested_pairs),
        "delivery_ratio": delivered / requested_pairs,
        "average_fidelity": sum(fidelities) / len(fidelities),
        "minimum_fidelity": min(fidelities),
        "throughput_active_window": delivered / duration_s,
        "throughput_delivery_interval": (delivered / (last_time - first_time)) if last_time > first_time else None,
        "first_pair_latency_s": first_time - start_time_s,
        "completion_time_s": (pairs[requested_pairs - 1].sim_time_s - start_time_s) if delivered >= requested_pairs else None,
    }


def _native_counter_metrics(trial_metrics: dict) -> dict:
    """`eg`/`ep`/`es` attempt/success counts - diagnostic only (per
    source-node, not per-intent; see notebook 06 of Fase H1), never used
    to compute `delivered_pairs`/`satisfied`."""
    result = {}
    for prefix in ("eg", "ep", "es"):
        success = trial_metrics.get(f"{prefix}_success")
        failures = trial_metrics.get(f"{prefix}_failures")
        if success is None or failures is None:
            result[f"{prefix}_attempts"] = None
            result[f"{prefix}_success"] = None
        else:
            result[f"{prefix}_attempts"] = int(success) + int(failures)
            result[f"{prefix}_success"] = int(success)
    return result


def _reconciliation_routing_strategy_name(original_name: str) -> str:
    """Episode-2 routing choice when reconciliation triggers: retry with
    `least_loss` unless that is exactly what just failed, in which case
    fall back to `shortest_hop_count`. A simple, deliberately documented
    heuristic, not a discovered one - this planner version has no logic
    that picks a strategy from a violation's category (see notebook 15 of
    Fase H2 and docs/campaign_architecture.md, limitations). Retrying with
    the same strategy that just failed would make `reconciliation_enabled`
    a no-op in every campaign trial, so a *different* strategy is always
    attempted."""
    return "least_loss" if original_name != "least_loss" else "shortest_hop_count"


def execute_trial(
    identity: TrialIdentity, params: TrialParameters, *,
    project_commit: str | None, sequence_commit: str | None,
) -> TrialRecord:
    """Runs exactly one isolated trial end to end: fresh topology, fresh
    `Timeline`, fresh `IntentPlanner`, fresh `IntentRepository`,
    `sequence.utils.metrics` reset first - never reusing a mutable object
    from any other trial (see docs/campaign_architecture.md, section 9).

    If the trial is `VIOLATED` and `params.reconciliation_enabled`, attempts
    exactly one reconciliation episode (`assurance.reconciliation.reconcile`,
    which itself resets metrics before running) - every delivery-derived
    field then reflects the *final* episode only, never a mix of both (see
    the regression fixed in `assurance.reconciliation.reconcile`).
    `planning_time_s`/`simulation_wall_time_s` are summed across both
    episodes when reconciliation runs, so they double as the "additional
    simulation cost" campaign C04 asks for.
    """
    metrics.configure()

    intent = params.intent
    topology_spec = params.topology_spec
    requested_pairs = intent.requirements.requested_pairs
    duration_s = intent.requirements.duration
    start_time_s = intent.requirements.start_time
    attenuation = topology_spec.quantum_links[0].attenuation_db_per_m if topology_spec.quantum_links else None
    distance = topology_spec.quantum_links[0].distance_m if topology_spec.quantum_links else None
    coherence = topology_spec.nodes[0].coherence_time_s if topology_spec.nodes else None

    routing_strategy = resolve_routing_strategy(params.routing_strategy_name)
    purification_strategy = resolve_purification_policy(params.purification_policy_name)

    capabilities = NetworkCapabilities(topology_spec)
    planner = IntentPlanner(capabilities, routing_strategy=routing_strategy, purification_strategy=purification_strategy)

    t0 = time.perf_counter()
    plan = planner.plan(intent)
    planning_time_s = time.perf_counter() - t0

    def _record(**overrides) -> TrialRecord:
        fields = dict(
            campaign=identity.campaign, trial_id=identity.trial_id, scenario=identity.scenario,
            parameter_hash=identity.parameter_hash, seed=identity.seed, intent_id=identity.intent_id,
            routing_strategy=params.routing_strategy_name, purification_policy=params.purification_policy_name,
            reconciliation_enabled=params.reconciliation_enabled,
            route="", hop_count=None, requested_pairs=requested_pairs, requested_fidelity=intent.requirements.min_fidelity,
            duration_s=duration_s, attenuation_db_per_m=attenuation, distance_m=distance, coherence_time_s=coherence,
            accepted=False, satisfied=False, recovered=None, final_status="REJECTED",
            delivered_pairs=None, excess_delivery_pairs=None, delivery_ratio=None,
            average_fidelity=None, minimum_fidelity=None,
            throughput_active_window=None, throughput_delivery_interval=None,
            first_pair_latency_s=None, completion_time_s=None,
            planning_time_s=round(planning_time_s, 6), simulation_wall_time_s=None,
            eg_attempts=None, eg_success=None, ep_attempts=None, ep_success=None, es_attempts=None, es_success=None,
            violations="", error_type=None, error_message=None,
            project_git_commit=project_commit, sequence_git_commit=sequence_commit,
            python_version=sys.version.split()[0], timestamp=_now_iso(),
        )
        fields.update(overrides)
        return TrialRecord(**fields)

    if not plan.feasible:
        return _record(final_status="REJECTED", violations=plan.infeasibility_reason or "")

    repository = IntentRepository()
    adapter = SequenceAdapter(topology_spec, seed=identity.seed)
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, plan)

    t0 = time.perf_counter()
    executor.run()
    simulation_wall_time_s = time.perf_counter() - t0

    record_status = repository.get(intent.id).lifecycle.status
    route_str = " -> ".join(plan.route)
    hop_count = max(len(plan.route) - 1, 0)

    if record_status != IntentStatus.ACTIVE:
        return _record(
            route=route_str, hop_count=hop_count, final_status=record_status.value,
            simulation_wall_time_s=round(simulation_wall_time_s, 6),
        )

    source_router = adapter.get_router(intent.endpoints.source)
    accepted_reservation = source_router.network_manager.protocol_stack[-1].accepted_reservations[0]
    if accepted_reservation.path != plan.route:
        raise AssertionError(
            f"planned route {plan.route} does not match the route SeQUeNCe actually accepted "
            f"{accepted_reservation.path} for trial {identity.trial_id} - see docs/campaign_architecture.md, "
            f"section 15 (this invariant is enforced here, not post-hoc on persisted data)"
        )

    evidence = collect_intent_evidence(intent)
    evaluation = evaluate_intent(intent, evidence)
    final_status = IntentStatus.SATISFIED if evaluation.satisfied else IntentStatus.VIOLATED
    reason = "all success conditions met" if evaluation.satisfied else "; ".join(evaluation.violations)
    repository.transition(intent.id, final_status, reason, sim_time=adapter.get_timeline().now() / SECOND)
    trial_metrics = metrics.collect_trial_metrics(intent.endpoints.source)

    recovered = None
    if final_status == IntentStatus.VIOLATED and params.reconciliation_enabled:
        reconciliation_routing_strategy = resolve_routing_strategy(
            _reconciliation_routing_strategy_name(params.routing_strategy_name)
        )
        t0 = time.perf_counter()
        reconciliation_result = reconcile(
            intent, topology_spec, repository, evaluation,
            seed=identity.seed + RECONCILIATION_SEED_OFFSET,
            routing_strategy=reconciliation_routing_strategy, purification_strategy=purification_strategy,
        )
        simulation_wall_time_s += time.perf_counter() - t0

        recovered = reconciliation_result.final_status == IntentStatus.SATISFIED
        route_str = " -> ".join(reconciliation_result.new_plan.route)
        hop_count = max(len(reconciliation_result.new_plan.route) - 1, 0)
        final_status = reconciliation_result.final_status

        if reconciliation_result.new_evaluation is not None:
            evaluation = reconciliation_result.new_evaluation
            evidence = collect_intent_evidence(intent)  # scoped to episode 2 only (reconcile() resets metrics first)
            trial_metrics = metrics.collect_trial_metrics(intent.endpoints.source)
        else:
            evaluation = None
            evidence = None
            trial_metrics = {}

    accepted = final_status in (IntentStatus.SATISFIED, IntentStatus.VIOLATED)
    satisfied = evaluation.satisfied if evaluation is not None else False
    violations_str = "; ".join(evaluation.violations) if evaluation is not None else ""

    return _record(
        route=route_str, hop_count=hop_count,
        accepted=accepted, satisfied=satisfied, recovered=recovered, final_status=final_status.value,
        simulation_wall_time_s=round(simulation_wall_time_s, 6),
        violations=violations_str,
        **_delivery_metrics(evidence, requested_pairs=requested_pairs, duration_s=duration_s, start_time_s=start_time_s),
        **_native_counter_metrics(trial_metrics),
    )


@dataclass
class CampaignRunSummary:
    campaign: str
    expected_trials: int
    completed_trials: int
    skipped_trials: int
    failed_trials: int
    duration_s: float
    output_files: list[str]


class CampaignRunner:
    """Loads a `CampaignSpec`, expands its parameter grid, generates every
    expected `TrialIdentity`, skips trials already in `trials.csv`, and
    executes the rest one at a time - persisting immediately and updating
    the manifest after every trial (see docs/campaign_architecture.md,
    sections 6-8)."""

    def __init__(self, spec: CampaignSpec, *, campaign_file: str | Path):
        self._spec = spec
        self._campaign_file = Path(campaign_file)
        self._base_dir = self._campaign_file.parent

    def run(self, *, force_resume: bool = False) -> CampaignRunSummary:
        """`force_resume=True` (used by the CLI's `resume` command) allows
        continuing regardless of `CampaignSpec.execution.resume` - explicit
        user intent overrides the spec's own default for this one
        invocation."""
        start = time.perf_counter()
        scenario = Scenario.load(self._base_dir / self._spec.scenario_file)
        base_topology = scenario.topology_spec()
        base_intents: list[EntanglementIntent] = [
            load_intent_file(self._base_dir / intent_file) for intent_file in self._spec.intents
        ]
        scenario_name = scenario.spec.name

        combinations = expand_parameter_grid(self._spec.effective_parameter_grid())
        expected_trials = len(combinations) * len(self._spec.seeds) * len(base_intents)

        trials_path = trials_csv_path(self._spec.output_directory, self._spec.name)
        errors_path = errors_jsonl_path(self._spec.output_directory, self._spec.name)
        manifest_file = manifest_path(self._spec.output_directory, self._spec.name)

        known_trial_ids = read_trial_ids(trials_path)
        if known_trial_ids and not (self._spec.execution.resume or force_resume):
            raise RuntimeError(
                f"campaign '{self._spec.name}' already has {len(known_trial_ids)} trial(s) in {trials_path} "
                f"and execution.resume is False - delete existing results or set resume: true to continue"
            )

        if read_manifest(manifest_file) is None:
            write_manifest(
                manifest_file,
                build_initial_manifest(self._spec, campaign_file=self._campaign_file, expected_trials=expected_trials),
            )

        env = collect_environment_info()
        skipped_trials = 0
        completed_trials = 0
        failed_trials = 0

        for combination in combinations:
            parameter_hash = compute_parameter_hash(combination)
            for base_intent in base_intents:
                params = apply_parameters(base_topology, base_intent, combination)
                for seed in self._spec.seeds:
                    identity = TrialIdentity(
                        campaign=self._spec.name, scenario=scenario_name, parameter_hash=parameter_hash,
                        strategy=f"{params.routing_strategy_name}__{params.purification_policy_name}",
                        seed=seed, intent_id=base_intent.id,
                    )
                    if identity.trial_id in known_trial_ids:
                        skipped_trials += 1
                        continue

                    try:
                        record = execute_trial(
                            identity, params,
                            project_commit=env.project_commit, sequence_commit=env.sequence_commit,
                        )
                    except Exception as exc:
                        failed_trials += 1
                        logger.warning("trial %s failed: %s: %s", identity.trial_id, type(exc).__name__, exc)
                        append_error_record(
                            errors_path, trial_id=identity.trial_id, campaign=identity.campaign,
                            scenario=identity.scenario, parameter_hash=identity.parameter_hash,
                            strategy=identity.strategy, seed=identity.seed, intent_id=identity.intent_id,
                            error_type=type(exc).__name__,
                            error_message="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                            timestamp=_now_iso(),
                        )
                        update_manifest_progress(
                            manifest_file, completed_trials=completed_trials, skipped_trials=skipped_trials,
                            failed_trials=failed_trials, output_files=[str(trials_path), str(errors_path)],
                        )
                        if not self._spec.execution.continue_on_error:
                            return CampaignRunSummary(
                                campaign=self._spec.name, expected_trials=expected_trials,
                                completed_trials=completed_trials, skipped_trials=skipped_trials,
                                failed_trials=failed_trials, duration_s=time.perf_counter() - start,
                                output_files=[str(trials_path), str(errors_path), str(manifest_file)],
                            )
                        continue

                    append_trial_record(trials_path, record, known_trial_ids=known_trial_ids)
                    completed_trials += 1
                    update_manifest_progress(
                        manifest_file, completed_trials=completed_trials, skipped_trials=skipped_trials,
                        failed_trials=failed_trials, output_files=[str(trials_path), str(errors_path)],
                    )

        return CampaignRunSummary(
            campaign=self._spec.name, expected_trials=expected_trials,
            completed_trials=completed_trials, skipped_trials=skipped_trials, failed_trials=failed_trials,
            duration_s=time.perf_counter() - start,
            output_files=[str(trials_path), str(errors_path), str(manifest_file)],
        )
