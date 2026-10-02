"""`pandas.DataFrame` formatting for notebook display - kept out of the
notebooks themselves so every notebook renders the same objects the same
way (see docs/notebooks.md).
"""
from __future__ import annotations

import pandas as pd

from ..assurance.evaluator import IntentEvaluation
from ..assurance.telemetry import IntentEvidence
from ..intent.lifecycle import IntentLifecycle
from ..intent.models import EntanglementIntent
from ..planning.models import ExecutionPlan
from .instrumentation import MemoryLifecycleRecorder
from .reconciliation import ReconciliationDemo


def delivered_pairs_table(evidence: IntentEvidence) -> pd.DataFrame:
    """Columns: pair, local_memory, remote_memory, delivery_time_s, fidelity."""
    if not evidence.delivered_pairs:
        return pd.DataFrame(columns=["pair", "local_memory", "remote_memory", "delivery_time_s", "fidelity"])
    return pd.DataFrame(
        [
            {
                "pair": p.pair_number,
                "local_memory": p.local_memory,
                "remote_memory": p.remote_memory,
                "delivery_time_s": p.sim_time_s,
                "fidelity": p.fidelity,
            }
            for p in evidence.delivered_pairs
        ]
    )


def memory_transitions_table(recorder: MemoryLifecycleRecorder) -> pd.DataFrame:
    """Columns: sim_time_s, memory, from_state, to_state, responsible."""
    if not recorder.transitions:
        return pd.DataFrame(columns=["sim_time_s", "memory", "from_state", "to_state", "responsible"])
    return pd.DataFrame(
        [
            {
                "sim_time_s": t.sim_time_s,
                "memory": t.memory_name,
                "from_state": t.old_state,
                "to_state": t.new_state,
                "responsible": t.responsible,
            }
            for t in recorder.transitions
        ]
    )


def plan_summary_table(plan: ExecutionPlan) -> pd.DataFrame:
    """One row per field - the ExecutionPlan's key facts, not a raw object dump."""
    rows = [
        {"field": "feasible", "value": plan.feasible},
        {"field": "route", "value": " -> ".join(plan.route) if plan.route else "(none)"},
        {"field": "route_rationale", "value": plan.route_rationale},
        {"field": "requires_purification", "value": plan.requires_purification},
        {"field": "purification_rounds_estimate", "value": plan.purification_rounds_estimate},
        {"field": "swapping_strategy_note", "value": plan.swapping_strategy_note},
    ]
    if plan.estimated_metrics is not None:
        rows.append({"field": "estimated_fidelity", "value": round(plan.estimated_metrics.fidelity, 4)})
        rows.append({"field": "estimated_latency_s", "value": plan.estimated_metrics.latency_s})
    if not plan.feasible:
        rows.append({"field": "infeasibility_reason", "value": plan.infeasibility_reason})
    return pd.DataFrame(rows)


def reservations_table(plan: ExecutionPlan) -> pd.DataFrame:
    """Columns: node_id, memories_required, memories_available, satisfied."""
    return pd.DataFrame(
        [
            {
                "node_id": r.node_id,
                "memories_required": r.memories_required,
                "memories_available": r.memories_available,
                "satisfied": r.satisfied,
            }
            for r in plan.reservations
        ]
    )


def evaluation_table(evaluation: IntentEvaluation) -> pd.DataFrame:
    """Columns: metric, operator, expected, observed, passed, evidence_source."""
    return pd.DataFrame(
        [
            {
                "metric": r.metric,
                "operator": r.operator,
                "expected": r.expected,
                "observed": r.observed,
                "passed": r.passed,
                "evidence_source": r.evidence_source,
            }
            for r in evaluation.condition_results
        ]
    )


def intent_table(intent: EntanglementIntent) -> pd.DataFrame:
    """One row per field of `intent` - a flat, readable view instead of a
    raw Pydantic `repr`/`model_dump` dump. Columns: field, value."""
    rows = [
        {"field": "id", "value": intent.id},
        {"field": "service", "value": intent.service},
        {"field": "source", "value": intent.endpoints.source},
        {"field": "destination", "value": intent.endpoints.destination},
        {"field": "min_fidelity (dimensionless)", "value": intent.requirements.min_fidelity},
        {"field": "min_throughput (pairs/s)", "value": intent.requirements.min_throughput},
        {"field": "max_latency (s)", "value": intent.requirements.max_latency},
        {"field": "reserved_memory_slots", "value": intent.requirements.reserved_memory_slots},
        {"field": "min_delivered_pairs", "value": intent.requirements.min_delivered_pairs},
        {"field": "start_time_s (s)", "value": intent.requirements.start_time_s},
        {"field": "duration_s (s)", "value": intent.requirements.duration_s},
        {"field": "policy.priority", "value": intent.policy.priority},
        {"field": "policy.allow_rerouting", "value": intent.policy.allow_rerouting},
        {"field": "policy.allow_purification", "value": intent.policy.allow_purification},
        {"field": "policy.allow_multiple_paths", "value": intent.policy.allow_multiple_paths},
        {"field": "policy.max_resource_scale", "value": intent.policy.max_resource_scale},
        {"field": "validation.metrics", "value": ", ".join(intent.validation.metrics)},
        {
            "field": "validation.success_conditions",
            "value": "; ".join(str(condition) for condition in intent.validation.success_conditions),
        },
    ]
    return pd.DataFrame(rows)


def lifecycle_table(lifecycle: IntentLifecycle) -> pd.DataFrame:
    """One row per recorded transition. Columns: from_status, to_status,
    reason, sim_time_s."""
    return pd.DataFrame(
        [
            {
                "from_status": t.from_status.value if t.from_status else "(none)",
                "to_status": t.to_status.value,
                "reason": t.reason,
                "sim_time_s": t.sim_time,
            }
            for t in lifecycle.history
        ]
    )


def reconciliation_episodes_table(demo: ReconciliationDemo) -> pd.DataFrame:
    """One row per episode. Columns: episode, strategy, route,
    delivered_pairs, average_fidelity, status."""
    rows = []
    for ep in demo.episodes:
        delivered = None
        avg_fidelity = None
        if ep.evaluation is not None:
            for condition in ep.evaluation.condition_results:
                if condition.metric == "delivered_pairs":
                    delivered = condition.observed
                elif condition.metric == "average_fidelity":
                    avg_fidelity = condition.observed
        rows.append(
            {
                "episode": ep.episode,
                "strategy": ep.strategy_name,
                "route": " -> ".join(ep.route) if ep.route else "(none)",
                "delivered_pairs": delivered,
                "average_fidelity": avg_fidelity,
                "status": ep.final_status.value,
            }
        )
    return pd.DataFrame(rows)
