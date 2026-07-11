"""`pandas.DataFrame` formatting for notebook display - kept out of the
notebooks themselves so every notebook renders the same objects the same
way (see docs/notebooks.md).
"""
from __future__ import annotations

import pandas as pd

from ..assurance.evaluator import IntentEvaluation
from ..assurance.telemetry import IntentEvidence
from ..planning.models import ExecutionPlan
from .instrumentation import MemoryLifecycleRecorder


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
    """Columns: metric, operator, expected, observed, passed."""
    return pd.DataFrame(
        [
            {
                "metric": r.metric,
                "operator": r.operator,
                "expected": r.expected,
                "observed": r.observed,
                "passed": r.passed,
            }
            for r in evaluation.condition_results
        ]
    )
