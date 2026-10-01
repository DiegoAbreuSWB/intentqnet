"""Executes one planner-family-study trial using an `IntentPlannerPolicy`
(L1/L2/L3/...) instead of the legacy `planning.planner.IntentPlanner`
directly - but reuses exactly the same deployment/simulation/assurance
machinery `experiments.runner.execute_trial` uses
(`execution.sequence_executor.SequenceExecutor`, `intent.repository.
IntentRepository`, `assurance.telemetry.collect_intent_evidence`,
`assurance.evaluator.evaluate_intent`, `sequence.utils.metrics`) - no
duplicated simulation/assurance logic, only the planning step differs.

Kept separate from `experiments.runner.execute_trial` (never modified)
because a `PlannerDecision`'s `selected_plan` is produced by a completely
different interface (`planning.planners.IntentPlannerPolicy`) than
`execute_trial`'s hardcoded `IntentPlanner` + routing/purification/
fidelity-estimator strategy arguments - see docs/planner_levels.md.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from sequence.constants import SECOND
from sequence.utils import metrics

from ..assurance.evaluator import evaluate_intent
from ..assurance.telemetry import collect_intent_evidence
from ..execution.sequence_executor import SequenceExecutor
from ..intent.models import EntanglementIntent, IntentStatus
from ..intent.repository import IntentRepository
from ..network.capabilities import NetworkCapabilities
from ..network.sequence_adapter import SequenceAdapter
from ..network.topology import NetworkTopologySpec
from ..planning.purification import executed_purification_mode
from .planner_study_records import PlannerStudyTrialRecord
from .records import TrialIdentity


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute_trial_with_policy(
    identity: TrialIdentity,
    intent: EntanglementIntent,
    topology_spec: NetworkTopologySpec,
    policy,
    context,
    *,
    project_commit: str | None,
    sequence_commit: str | None,
    regime: str | None = None,
    execution_cache: dict | None = None,
) -> PlannerStudyTrialRecord:
    """Plans `intent` with `policy` (an `IntentPlannerPolicy`), deploys the
    resulting plan (if feasible) via the real `SequenceExecutor`, runs the
    simulation, and evaluates assurance - exactly the same downstream
    pipeline `experiments.runner.execute_trial` uses, only the planning
    step is swapped.

    `execution_cache`: what the network does with an admitted plan depends
    only on the topology, the intent, the seed, the route and the executed
    purification mode - not on which planner chose them. A caller comparing
    several planners on the SAME (topology, intent, seed) can pass one dict
    for all of them; planners that pick the same route and mode then share
    one simulation instead of repeating it (identical records either way,
    see tests/experiments/test_planner_execution_cache.py). Never share a
    cache across different topologies, intents or seeds."""
    from ..planning.planners.base import generate_candidate_paths

    metrics.configure()
    capabilities = NetworkCapabilities(topology_spec)
    candidate_paths = generate_candidate_paths(intent, capabilities, context)

    t0 = time.perf_counter()
    decision = policy.plan(intent, capabilities, candidate_paths, context)
    planning_time_s = time.perf_counter() - t0

    attenuation = topology_spec.quantum_links[0].attenuation_db_per_m if topology_spec.quantum_links else None

    def _record(**overrides) -> PlannerStudyTrialRecord:
        fields = dict(
            campaign=identity.campaign, trial_id=identity.trial_id, scenario=identity.scenario,
            parameter_hash=identity.parameter_hash, seed=identity.seed, intent_id=identity.intent_id,
            planner_level=decision.planner_level, planner_name=decision.planner_name,
            reserved_memory_slots=intent.requirements.reserved_memory_slots,
            min_delivered_pairs=intent.requirements.min_delivered_pairs,
            requested_fidelity=intent.requirements.min_fidelity,
            duration_s=intent.requirements.duration_s, attenuation_db_per_m=attenuation,
            route=" -> ".join(decision.selected_plan.route), hop_count=max(len(decision.selected_plan.route) - 1, 0),
            feasible=decision.feasible, rejection_reason=decision.rejection_reason,
            predicted_satisfaction_probability=decision.predicted_satisfaction_probability,
            predicted_delivered_pairs=decision.predicted_delivered_pairs,
            predicted_average_fidelity=decision.predicted_average_fidelity,
            purification_rounds_estimate=decision.selected_plan.purification_rounds_estimate,
            planning_time_s=round(planning_time_s, 6),
            final_status="REJECTED", satisfied=None, delivered_pairs=None, average_fidelity=None,
            observed_fidelity=None, absolute_fidelity_error=None, simulation_wall_time_s=None,
            project_git_commit=project_commit, sequence_git_commit=sequence_commit,
            python_version=sys.version.split()[0], timestamp=_now_iso(),
            formalism=topology_spec.formalism, platform=topology_spec.platform,
            purification_mode=(
                executed_purification_mode(decision.selected_plan.purification_mode, intent.policy.allow_purification)
                if decision.feasible else None
            ),
            regime=regime, allow_purification=intent.policy.allow_purification,
        )
        fields.update(overrides)
        return PlannerStudyTrialRecord(**fields)

    if not decision.feasible:
        return _record(final_status="REJECTED")

    signature = (
        tuple(decision.selected_plan.route),
        executed_purification_mode(decision.selected_plan.purification_mode, intent.policy.allow_purification),
    )
    outcome = execution_cache.get(signature) if execution_cache is not None else None
    if outcome is None:
        outcome = _execute_plan(intent, topology_spec, decision.selected_plan, seed=identity.seed)
        if execution_cache is not None:
            execution_cache[signature] = outcome

    average_fidelity = outcome.get("average_fidelity")
    estimated_fidelity = decision.predicted_average_fidelity
    absolute_error = (
        average_fidelity - estimated_fidelity if average_fidelity is not None and estimated_fidelity is not None
        else None
    )
    return _record(**outcome, absolute_fidelity_error=absolute_error)


def _execute_plan(intent: EntanglementIntent, topology_spec: NetworkTopologySpec, plan, *, seed: int) -> dict:
    """Deploys `plan` on a fresh timeline, runs it and evaluates assurance.
    Returns the measured record fields - everything in a trial record that
    does not depend on which planner produced the plan."""
    metrics.configure()
    repository = IntentRepository()
    adapter = SequenceAdapter(topology_spec, seed=seed)
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, plan)

    t0 = time.perf_counter()
    try:
        executor.run()
    except Exception as exc:  # noqa: BLE001
        # A planner level admitting at admission_threshold=0.0 (L3/L3-R's
        # P02/P02B collection protocol - see scripts/run_p02b_resource_
        # aware_planners.py) can deploy a route SeQUeNCe's real protocol
        # code correctly refuses mid-simulation (e.g. BBPSSW's own
        # `kept_memo.fidelity > 0.5` assertion, sequence/entanglement_
        # management/purification/bbpssw_protocol.py, when the pre-
        # purification fidelity is already below what purification can
        # ever help) - a real, informative outcome, not a bug in this
        # trial runner. Recording it as SIMULATION_ERROR (with the real
        # exception preserved in rejection_reason) keeps a long campaign
        # from losing all prior trials to one physically-refused plan,
        # while never inventing a SATISFIED/VIOLATED verdict SeQUeNCe
        # itself never reached.
        simulation_wall_time_s = time.perf_counter() - t0
        return dict(
            final_status="SIMULATION_ERROR", rejection_reason=f"{type(exc).__name__}: {exc}",
            simulation_wall_time_s=round(simulation_wall_time_s, 6),
        )
    simulation_wall_time_s = time.perf_counter() - t0

    from .runner import _native_counter_metrics  # local import: `runner` imports this package's siblings

    counters = _native_counter_metrics(metrics.collect_trial_metrics(intent.endpoints.source))

    record_status = repository.get(intent.id).lifecycle.status
    if record_status != IntentStatus.ACTIVE:
        return dict(
            final_status=record_status.value, simulation_wall_time_s=round(simulation_wall_time_s, 6), **counters,
        )

    evidence = collect_intent_evidence(intent)
    evaluation = evaluate_intent(intent, evidence)
    final_status = IntentStatus.SATISFIED if evaluation.satisfied else IntentStatus.VIOLATED
    reason = "all success conditions met" if evaluation.satisfied else "; ".join(evaluation.violations)
    repository.transition(intent.id, final_status, reason, sim_time=adapter.get_timeline().now() / SECOND)

    delivered_pairs = len(evidence.delivered_pairs) if evidence else 0
    average_fidelity = (
        sum(p.fidelity for p in evidence.delivered_pairs) / delivered_pairs
        if evidence and delivered_pairs else None
    )
    minimum_fidelity = min((p.fidelity for p in evidence.delivered_pairs), default=None) if evidence else None

    return dict(
        final_status=final_status.value, satisfied=evaluation.satisfied, delivered_pairs=delivered_pairs,
        average_fidelity=average_fidelity, observed_fidelity=average_fidelity,
        simulation_wall_time_s=round(simulation_wall_time_s, 6),
        minimum_fidelity=minimum_fidelity, discarded_pairs=evidence.discarded_pairs if evidence else None,
        **counters,
    )
