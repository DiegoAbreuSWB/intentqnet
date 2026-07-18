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
) -> PlannerStudyTrialRecord:
    """Plans `intent` with `policy` (an `IntentPlannerPolicy`), deploys the
    resulting plan (if feasible) via the real `SequenceExecutor`, runs the
    simulation, and evaluates assurance - exactly the same downstream
    pipeline `experiments.runner.execute_trial` uses, only the planning
    step is swapped."""
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
        )
        fields.update(overrides)
        return PlannerStudyTrialRecord(**fields)

    if not decision.feasible:
        return _record(final_status="REJECTED")

    repository = IntentRepository()
    adapter = SequenceAdapter(topology_spec, seed=identity.seed)
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, decision.selected_plan)

    t0 = time.perf_counter()
    executor.run()
    simulation_wall_time_s = time.perf_counter() - t0

    record_status = repository.get(intent.id).lifecycle.status
    if record_status != IntentStatus.ACTIVE:
        return _record(final_status=record_status.value, simulation_wall_time_s=round(simulation_wall_time_s, 6))

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
    estimated_fidelity = decision.predicted_average_fidelity
    absolute_error = (
        average_fidelity - estimated_fidelity if average_fidelity is not None and estimated_fidelity is not None
        else None
    )

    return _record(
        final_status=final_status.value, satisfied=evaluation.satisfied, delivered_pairs=delivered_pairs,
        average_fidelity=average_fidelity, observed_fidelity=average_fidelity,
        absolute_fidelity_error=absolute_error, simulation_wall_time_s=round(simulation_wall_time_s, 6),
    )
