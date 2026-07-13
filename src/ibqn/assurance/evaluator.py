"""Evaluates an intent's `validation.success_conditions` against
`telemetry.IntentEvidence` - never against the requirements the intent
itself declared (see docs/assurance_design.md, section 1: "não trate a
fidelidade configurada no pedido como fidelidade observada").

Comparison operators are dispatched through the standard library's
`operator` module (`ge`, `le`, `gt`, `lt`, `eq`, `ne`) - `eval()` is never
used to interpret a YAML-provided condition string.
"""
from __future__ import annotations

import operator as op
from collections.abc import Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from ..intent.models import EntanglementIntent
from .telemetry import IntentEvidence

if TYPE_CHECKING:
    pass

_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    ">=": op.ge,
    "<=": op.le,
    ">": op.gt,
    "<": op.lt,
    "==": op.eq,
    "!=": op.ne,
}


class UnsupportedMetricError(ValueError):
    """Raised when a `success_conditions` entry names a metric this
    evaluator has no real, evidence-backed way to compute (see
    docs/assurance_design.md, section 7 - e.g. per-pair latency)."""


def _delivered_pairs(evidence: IntentEvidence, intent: EntanglementIntent) -> float:
    return float(len(evidence.delivered_pairs))


def _average_fidelity(evidence: IntentEvidence, intent: EntanglementIntent) -> float | None:
    if not evidence.delivered_pairs:
        return None
    fidelities = [pair.fidelity for pair in evidence.delivered_pairs]
    return sum(fidelities) / len(fidelities)


def _min_fidelity(evidence: IntentEvidence, intent: EntanglementIntent) -> float | None:
    if not evidence.delivered_pairs:
        return None
    return min(pair.fidelity for pair in evidence.delivered_pairs)


def _throughput(evidence: IntentEvidence, intent: EntanglementIntent) -> float:
    """Pairs per second over the *requested* reservation window - the same
    definition `sequence.app.request_app.RequestApp.get_throughput` uses
    (`memory_counter / (end_t - start_t)`), recomputed here from
    intent-scoped evidence instead of the app's own raw counter."""
    return len(evidence.delivered_pairs) / intent.requirements.duration_s


def _completion_time(evidence: IntentEvidence, intent: EntanglementIntent) -> float | None:
    """Seconds from `start_time_s` to the delivery of the Nth pair, or
    `None` if fewer than N were ever delivered - the same concept as
    `sequence.utils.metrics.DeliveryTimeMetric`, recomputed here filtered
    by `intent_id` instead of `owner_name` (see docs/assurance_design.md,
    section 3). N is `min_delivered_pairs` when the intent declares an
    explicit service-level delivery goal (Fase J2), falling back to
    `reserved_memory_slots` for intents that don't - matching this
    metric's pre-J2 behavior exactly (see
    docs/intent_resource_semantics.md)."""
    target = intent.requirements.min_delivered_pairs or intent.requirements.reserved_memory_slots
    if len(evidence.delivered_pairs) < target:
        return None
    nth_pair = evidence.delivered_pairs[target - 1]
    return nth_pair.sim_time_s - intent.requirements.start_time_s


_METRIC_FUNCTIONS: dict[str, Callable[[IntentEvidence, EntanglementIntent], float | None]] = {
    "delivered_pairs": _delivered_pairs,
    "average_fidelity": _average_fidelity,
    "min_fidelity": _min_fidelity,
    "throughput": _throughput,
    "completion_time": _completion_time,
}

SUPPORTED_METRICS: frozenset[str] = frozenset(_METRIC_FUNCTIONS)


class ConditionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    operator: str
    expected: float
    observed: float | None
    passed: bool
    evidence_source: str

    def __str__(self) -> str:
        return f"{self.metric} {self.operator} {self.expected} (observed={self.observed}) -> {'PASS' if self.passed else 'FAIL'}"


class IntentEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent_id: str
    satisfied: bool
    condition_results: list[ConditionResult]
    violations: list[str]


def evaluate_intent(intent: EntanglementIntent, evidence: IntentEvidence) -> IntentEvaluation:
    """Evaluates every condition in `intent.validation.success_conditions`
    against `evidence`.

    Raises:
        UnsupportedMetricError: if a condition names a metric not in
            `SUPPORTED_METRICS`.
    """
    results: list[ConditionResult] = []
    for condition in intent.validation.success_conditions:
        if condition.metric not in _METRIC_FUNCTIONS:
            raise UnsupportedMetricError(
                f"assurance cannot evaluate metric '{condition.metric}' for intent '{intent.id}' - "
                f"supported metrics: {sorted(SUPPORTED_METRICS)} (see docs/assurance_design.md, section 7)"
            )
        observed = _METRIC_FUNCTIONS[condition.metric](evidence, intent)
        passed = observed is not None and _OPERATORS[condition.operator](observed, condition.expected)
        results.append(
            ConditionResult(
                metric=condition.metric,
                operator=condition.operator,
                expected=condition.expected,
                observed=observed,
                passed=passed,
                evidence_source=(
                    f"{len(evidence.delivered_pairs)} DELIVERY event(s) tagged intent_id='{intent.id}'"
                ),
            )
        )

    satisfied = all(result.passed for result in results)
    violations = [str(result) for result in results if not result.passed]
    return IntentEvaluation(
        intent_id=intent.id, satisfied=satisfied, condition_results=results, violations=violations
    )
