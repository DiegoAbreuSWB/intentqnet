"""Overhead instrumentation (Fase J7, see docs/overhead_methodology.md):
decomposes one trial's wall-clock time into orchestration stages (the
IBQN layer's own cost) versus `simulation_wall_time_s` (the real
SeQUeNCe `Timeline.run()` cost) - so "how much does IBQN cost" can be
answered independently of "how much does the simulation itself cost".

Deliberately a SEPARATE, standalone instrumented entry point
(`run_instrumented_trial`), not a modification of
`runner.execute_trial`: adding per-stage timers to the production
runner would require another TrialRecord schema change and campaign
regeneration (as Fase J1/J2 needed) for a measurement this project only
needs at the granularity of a dedicated overhead campaign (`F06`, Fase
J10), not on every routine trial.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from ..assurance.evaluator import IntentEvaluation, evaluate_intent
from ..assurance.reconciliation_policy import ReconciliationDecision, decide_reconciliation_action
from ..assurance.telemetry import collect_intent_evidence
from ..assurance.violations import classify_violations
from ..execution.sequence_executor import SequenceExecutor
from ..intent.models import EntanglementIntent, IntentStatus
from ..intent.parser import load_intent_file_with_timing
from ..intent.repository import IntentRepository
from ..network.capabilities import NetworkCapabilities
from ..network.sequence_adapter import SequenceAdapter
from ..network.topology import NetworkTopologySpec
from ..planning.fidelity_estimation import LinkFidelityEstimator
from ..planning.planner import IntentPlanner
from ..planning.purification import PurificationStrategy
from ..planning.routing import RoutingStrategy


@dataclass(frozen=True)
class TrialTiming:
    """Wall-clock decomposition of one instrumented trial. Every field is
    a real `time.perf_counter()` measurement around a concrete code path
    - `None` only for stages this version cannot isolate without
    modifying a well-tested core module (`route_application_wall_time_s`,
    see the module docstring of `execution.sequence_executor`), never a
    guess."""

    intent_parsing_wall_time_s: float
    intent_validation_wall_time_s: float
    capability_extraction_wall_time_s: float
    planning_wall_time_s: float
    route_application_wall_time_s: float | None
    deployment_wall_time_s: float
    assurance_wall_time_s: float
    reconciliation_decision_wall_time_s: float | None
    persistence_wall_time_s: float | None
    simulation_wall_time_s: float

    @property
    def total_orchestration_wall_time_s(self) -> float:
        """Every stage above except `simulation_wall_time_s` - the IBQN
        layer's own cost, independent of the simulator's."""
        return (
            self.intent_parsing_wall_time_s + self.intent_validation_wall_time_s
            + self.capability_extraction_wall_time_s + self.planning_wall_time_s
            + (self.route_application_wall_time_s or 0.0) + self.deployment_wall_time_s
            + self.assurance_wall_time_s + (self.reconciliation_decision_wall_time_s or 0.0)
            + (self.persistence_wall_time_s or 0.0)
        )

    @property
    def total_trial_wall_time_s(self) -> float:
        return self.total_orchestration_wall_time_s + self.simulation_wall_time_s

    @property
    def orchestration_overhead_ratio(self) -> float:
        total = self.total_trial_wall_time_s
        return (self.total_orchestration_wall_time_s / total) if total > 0 else 0.0

    @property
    def planning_overhead_ratio(self) -> float:
        total = self.total_trial_wall_time_s
        return (self.planning_wall_time_s / total) if total > 0 else 0.0


def run_instrumented_trial(
    intent_source: EntanglementIntent | str | Path,
    topology_spec: NetworkTopologySpec,
    *,
    seed: int,
    routing_strategy: RoutingStrategy | None = None,
    purification_strategy: PurificationStrategy | None = None,
    fidelity_estimator: LinkFidelityEstimator | None = None,
    reconciliation_enabled: bool = False,
) -> tuple[TrialTiming, IntentEvaluation | None]:
    """Runs one intent-based trial exactly like `runner.execute_trial`
    does (same planner/executor/assurance calls, in the same order), but
    wrapped with a `time.perf_counter()` around each stage.

    `intent_source` as a path measures real `intent_parsing_wall_time_s`/
    `intent_validation_wall_time_s` (see
    `intent.parser.load_intent_file_with_timing`); passed as an
    already-built `EntanglementIntent`, both are `0.0` - parsing/
    validation genuinely didn't happen in this call, not an omission.

    `persistence_wall_time_s` is `None`: this function never writes a
    `TrialRecord` to disk (that's `runner.execute_trial`'s job) - see the
    module docstring for why overhead instrumentation is a separate path.
    """
    if isinstance(intent_source, (str, Path)):
        intent, parsing_s, validation_s = load_intent_file_with_timing(intent_source)
    else:
        intent, parsing_s, validation_s = intent_source, 0.0, 0.0

    t0 = time.perf_counter()
    capabilities = NetworkCapabilities(topology_spec)
    capability_extraction_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    planner = IntentPlanner(
        capabilities, routing_strategy=routing_strategy, purification_strategy=purification_strategy,
        fidelity_estimator=fidelity_estimator,
    )
    plan = planner.plan(intent)
    planning_s = time.perf_counter() - t0

    if not plan.feasible:
        timing = TrialTiming(
            intent_parsing_wall_time_s=parsing_s, intent_validation_wall_time_s=validation_s,
            capability_extraction_wall_time_s=capability_extraction_s, planning_wall_time_s=planning_s,
            route_application_wall_time_s=None, deployment_wall_time_s=0.0, assurance_wall_time_s=0.0,
            reconciliation_decision_wall_time_s=None, persistence_wall_time_s=None, simulation_wall_time_s=0.0,
        )
        return timing, None

    repository = IntentRepository()
    adapter = SequenceAdapter(topology_spec, seed=seed)
    executor = SequenceExecutor(adapter, repository)

    t0 = time.perf_counter()
    executor.deploy(intent, plan)
    deployment_s = time.perf_counter() - t0
    # route_application_wall_time_s is not separately isolated: `_deploy_plan`
    # (execution.sequence_executor) applies the route as an internal step of
    # the same `deploy()` call measured above - splitting it out would
    # require adding timing hooks inside that module, out of scope for this
    # phase (see the module docstring).

    t0 = time.perf_counter()
    executor.run()
    simulation_s = time.perf_counter() - t0

    if repository.get(intent.id).lifecycle.status != IntentStatus.ACTIVE:
        timing = TrialTiming(
            intent_parsing_wall_time_s=parsing_s, intent_validation_wall_time_s=validation_s,
            capability_extraction_wall_time_s=capability_extraction_s, planning_wall_time_s=planning_s,
            route_application_wall_time_s=None, deployment_wall_time_s=deployment_s, assurance_wall_time_s=0.0,
            reconciliation_decision_wall_time_s=None, persistence_wall_time_s=None,
            simulation_wall_time_s=simulation_s,
        )
        return timing, None

    t0 = time.perf_counter()
    evidence = collect_intent_evidence(intent)
    evaluation = evaluate_intent(intent, evidence)
    assurance_s = time.perf_counter() - t0

    reconciliation_decision_s = None
    if reconciliation_enabled and not evaluation.satisfied:
        t0 = time.perf_counter()
        violations = classify_violations(evaluation)
        decision: ReconciliationDecision = decide_reconciliation_action(
            violations, capabilities=capabilities, source=intent.endpoints.source, destination=intent.endpoints.destination,
            current_route=plan.route, current_reserved_memory_slots=intent.requirements.reserved_memory_slots,
            min_fidelity=intent.requirements.min_fidelity, allow_purification=intent.policy.allow_purification,
            fidelity_estimator=fidelity_estimator, purification_strategy=purification_strategy,
        )
        reconciliation_decision_s = time.perf_counter() - t0

    timing = TrialTiming(
        intent_parsing_wall_time_s=parsing_s, intent_validation_wall_time_s=validation_s,
        capability_extraction_wall_time_s=capability_extraction_s, planning_wall_time_s=planning_s,
        route_application_wall_time_s=None, deployment_wall_time_s=deployment_s, assurance_wall_time_s=assurance_s,
        reconciliation_decision_wall_time_s=reconciliation_decision_s, persistence_wall_time_s=None,
        simulation_wall_time_s=simulation_s,
    )
    return timing, evaluation
