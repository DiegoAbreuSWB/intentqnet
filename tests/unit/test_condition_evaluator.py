"""Tests for `ibqn.assurance.evaluator` - pure evaluation logic against a
constructed `IntentEvidence`, no SeQUeNCe simulation involved. Confirms
comparisons are dispatched through `operator.*`, never `eval()` (see
docs/assurance_design.md, section 8), and that unsupported metrics raise
rather than silently returning a guessed value.
"""
import pytest

from ibqn.assurance.evaluator import SUPPORTED_METRICS, UnsupportedMetricError, evaluate_intent
from ibqn.assurance.telemetry import DeliveredPair, IntentEvidence
from ibqn.assurance.violations import ViolationCategory, classify_violations
from ibqn.intent.models import (
    EntanglementIntent, IntentEndpoints, IntentRequirements, IntentValidation, SuccessCondition,
)


def build_intent(*, min_fidelity=0.8, requested_pairs=10, duration=10.0, metrics=None, conditions=None) -> EntanglementIntent:
    return EntanglementIntent(
        id="intent-001",
        endpoints=IntentEndpoints(source="a", destination="b"),
        requirements=IntentRequirements(
            min_fidelity=min_fidelity, min_throughput=1, max_latency=1,
            requested_pairs=requested_pairs, start_time=0.0, duration=duration,
        ),
        validation=IntentValidation(
            metrics=metrics or ["delivered_pairs"],
            success_conditions=conditions or [SuccessCondition(metric="delivered_pairs", operator=">=", expected=requested_pairs)],
        ),
    )


def build_evidence(fidelities: list[float], *, sim_time_step_s: float = 1.0, start_at_s: float = 0.0) -> IntentEvidence:
    pairs = [
        DeliveredPair(pair_number=i + 1, sim_time_s=start_at_s + i * sim_time_step_s, fidelity=fidelity)
        for i, fidelity in enumerate(fidelities)
    ]
    return IntentEvidence(intent_id="intent-001", delivered_pairs=pairs)


@pytest.mark.unit
def test_all_conditions_pass_when_evidence_meets_requirements():
    intent = build_intent(
        requested_pairs=3,
        metrics=["delivered_pairs", "average_fidelity"],
        conditions=[
            SuccessCondition(metric="delivered_pairs", operator=">=", expected=3),
            SuccessCondition(metric="average_fidelity", operator=">=", expected=0.8),
        ],
    )
    evidence = build_evidence([0.9, 0.85, 0.95])

    evaluation = evaluate_intent(intent, evidence)

    assert evaluation.satisfied is True
    assert evaluation.violations == []
    assert all(r.passed for r in evaluation.condition_results)


@pytest.mark.unit
def test_delivered_pairs_below_expected_fails():
    intent = build_intent(requested_pairs=10)
    evidence = build_evidence([0.9] * 3)  # only 3 delivered, wanted >= 10

    evaluation = evaluate_intent(intent, evidence)

    assert evaluation.satisfied is False
    assert len(evaluation.violations) == 1
    result = evaluation.condition_results[0]
    assert result.metric == "delivered_pairs"
    assert result.observed == 3.0
    assert result.passed is False


@pytest.mark.unit
def test_average_fidelity_computed_correctly():
    intent = build_intent(
        metrics=["average_fidelity"],
        conditions=[SuccessCondition(metric="average_fidelity", operator=">=", expected=0.9)],
    )
    evidence = build_evidence([0.8, 0.9, 1.0])  # mean = 0.9

    evaluation = evaluate_intent(intent, evidence)

    assert evaluation.condition_results[0].observed == pytest.approx(0.9)
    assert evaluation.satisfied is True  # 0.9 >= 0.9


@pytest.mark.unit
def test_min_fidelity_computed_correctly():
    intent = build_intent(
        metrics=["min_fidelity"],
        conditions=[SuccessCondition(metric="min_fidelity", operator=">=", expected=0.85)],
    )
    evidence = build_evidence([0.99, 0.80, 0.95])

    evaluation = evaluate_intent(intent, evidence)

    assert evaluation.condition_results[0].observed == pytest.approx(0.80)
    assert evaluation.satisfied is False  # 0.80 < 0.85


@pytest.mark.unit
def test_fidelity_metrics_are_none_when_no_pairs_delivered():
    intent = build_intent(
        metrics=["average_fidelity"],
        conditions=[SuccessCondition(metric="average_fidelity", operator=">=", expected=0.5)],
    )
    evidence = build_evidence([])

    evaluation = evaluate_intent(intent, evidence)

    assert evaluation.condition_results[0].observed is None
    assert evaluation.condition_results[0].passed is False  # None never satisfies a comparison


@pytest.mark.unit
def test_throughput_uses_requested_duration_as_denominator():
    intent = build_intent(
        duration=10.0,
        metrics=["throughput"],
        conditions=[SuccessCondition(metric="throughput", operator=">=", expected=2)],
    )
    evidence = build_evidence([0.9] * 25)  # 25 pairs / 10s = 2.5 pairs/s

    evaluation = evaluate_intent(intent, evidence)

    assert evaluation.condition_results[0].observed == pytest.approx(2.5)
    assert evaluation.satisfied is True


@pytest.mark.unit
def test_completion_time_is_none_when_target_not_reached():
    intent = build_intent(
        requested_pairs=5,
        metrics=["completion_time"],
        conditions=[SuccessCondition(metric="completion_time", operator="<=", expected=100)],
    )
    evidence = build_evidence([0.9] * 3)  # only 3 of 5 requested pairs delivered

    evaluation = evaluate_intent(intent, evidence)

    assert evaluation.condition_results[0].observed is None
    assert evaluation.condition_results[0].passed is False


@pytest.mark.unit
def test_completion_time_measures_time_to_nth_pair_relative_to_start():
    intent = build_intent(
        requested_pairs=3,
        metrics=["completion_time"],
        conditions=[SuccessCondition(metric="completion_time", operator="<=", expected=5.0)],
    )
    evidence = build_evidence([0.9, 0.9, 0.9], sim_time_step_s=2.0, start_at_s=1.0)
    # pair 3 delivered at sim_time_s = 1 + 2*2 = 5.0; intent start_time = 0.0 -> completion_time = 5.0

    evaluation = evaluate_intent(intent, evidence)

    assert evaluation.condition_results[0].observed == pytest.approx(5.0)
    assert evaluation.satisfied is True  # 5.0 <= 5.0


@pytest.mark.unit
@pytest.mark.parametrize(
    "operator_str,expected,value,should_pass",
    [
        (">=", 5, 5, True), (">=", 5, 4, False),
        ("<=", 5, 5, True), ("<=", 5, 6, False),
        (">", 5, 6, True), (">", 5, 5, False),
        ("<", 5, 4, True), ("<", 5, 5, False),
        ("==", 5, 5, True), ("==", 5, 4, False),
        ("!=", 5, 4, True), ("!=", 5, 5, False),
    ],
)
def test_all_six_operators_are_dispatched_correctly(operator_str, expected, value, should_pass):
    intent = build_intent(
        metrics=["delivered_pairs"],
        conditions=[SuccessCondition(metric="delivered_pairs", operator=operator_str, expected=expected)],
    )
    evidence = build_evidence([0.9] * value)

    evaluation = evaluate_intent(intent, evidence)

    assert evaluation.condition_results[0].passed is should_pass


@pytest.mark.unit
def test_unsupported_metric_raises_instead_of_guessing():
    intent = build_intent(
        metrics=["latency"],
        conditions=[SuccessCondition(metric="latency", operator="<=", expected=0.5)],
    )
    evidence = build_evidence([0.9])

    with pytest.raises(UnsupportedMetricError, match="latency"):
        evaluate_intent(intent, evidence)


@pytest.mark.unit
def test_supported_metrics_are_exactly_the_documented_five():
    assert SUPPORTED_METRICS == frozenset(
        {"delivered_pairs", "average_fidelity", "min_fidelity", "throughput", "completion_time"}
    )


@pytest.mark.unit
def test_classify_violations_categorizes_correctly():
    intent = build_intent(
        requested_pairs=10,
        metrics=["delivered_pairs", "average_fidelity"],
        conditions=[
            SuccessCondition(metric="delivered_pairs", operator=">=", expected=10),
            SuccessCondition(metric="average_fidelity", operator=">=", expected=0.99),
        ],
    )
    evidence = build_evidence([0.5] * 3)  # fails both: too few pairs, fidelity too low

    evaluation = evaluate_intent(intent, evidence)
    violations = classify_violations(evaluation)

    assert len(violations) == 2
    categories = {v.category for v in violations}
    assert categories == {ViolationCategory.DELIVERED_PAIRS, ViolationCategory.FIDELITY}


@pytest.mark.unit
def test_classify_violations_returns_empty_list_when_satisfied():
    intent = build_intent(requested_pairs=1)
    evidence = build_evidence([0.9])

    evaluation = evaluate_intent(intent, evidence)

    assert classify_violations(evaluation) == []
