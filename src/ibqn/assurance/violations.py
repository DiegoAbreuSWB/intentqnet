"""Classifies the failed `ConditionResult`s of an `IntentEvaluation` into
typed `Violation`s, so a caller (reconciliation, reporting) can reason about
*what kind* of requirement was violated without re-parsing metric-name
strings.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from .evaluator import IntentEvaluation


class ViolationCategory(str, Enum):
    FIDELITY = "fidelity"
    THROUGHPUT = "throughput"
    DELIVERED_PAIRS = "delivered_pairs"
    COMPLETION_TIME = "completion_time"
    UNKNOWN = "unknown"


_METRIC_TO_CATEGORY: dict[str, ViolationCategory] = {
    "average_fidelity": ViolationCategory.FIDELITY,
    "min_fidelity": ViolationCategory.FIDELITY,
    "throughput": ViolationCategory.THROUGHPUT,
    "delivered_pairs": ViolationCategory.DELIVERED_PAIRS,
    "completion_time": ViolationCategory.COMPLETION_TIME,
}


class Violation(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent_id: str
    metric: str
    category: ViolationCategory
    operator: str
    expected: float
    observed: float | None
    relative_gap: float | None = None  # (expected - observed) / expected, when both are known and expected != 0


def classify_violations(evaluation: IntentEvaluation) -> list[Violation]:
    """Returns one `Violation` per failed condition in `evaluation`
    (empty list if `evaluation.satisfied` is True)."""
    violations: list[Violation] = []
    for result in evaluation.condition_results:
        if result.passed:
            continue
        relative_gap = None
        if result.observed is not None and result.expected != 0:
            relative_gap = (result.expected - result.observed) / result.expected
        violations.append(
            Violation(
                intent_id=evaluation.intent_id,
                metric=result.metric,
                category=_METRIC_TO_CATEGORY.get(result.metric, ViolationCategory.UNKNOWN),
                operator=result.operator,
                expected=result.expected,
                observed=result.observed,
                relative_gap=relative_gap,
            )
        )
    return violations
