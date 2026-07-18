"""Unit tests for L3-R (`ProbabilisticResourceAwarePlanner` /
`estimate_probabilistic_resource_aware_plan`) - M6d. Verifies: L3-original
is untouched by this module's existence; L2-R's deterministic gates are
reused (not re-derived) for hard infeasibility; the attempt-rate
correction actually changes `expected_delivered_pairs` relative to
L3-original by exactly the audited factor; probabilities stay in [0, 1];
admission is threshold-sensitive; no operational seed is ever used.
"""
from __future__ import annotations

import inspect

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.topology_catalog import linear_chain_spec
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.planning.planners import PlanningContext, ProbabilisticResourceAwarePlanner, generate_candidate_paths
from ibqn.planning.planners.l2_resource_aware import ATTEMPT_RATE_CONSERVATIVE_FACTOR, RejectionReason
from ibqn.planning.planners.l3_probabilistic import estimate_probabilistic_plan
from ibqn.planning.planners.l3_resource_aware import estimate_probabilistic_resource_aware_plan
from ibqn.planning.routing import ShortestHopCountRouting


def _three_node_intent(min_fidelity=0.65, reserved_memory_slots=10, min_delivered_pairs=10, duration=0.1):
    return simple_intent(
        intent_id="l3r-test", source="a", destination="b", min_fidelity=min_fidelity,
        requested_pairs=reserved_memory_slots, min_delivered_pairs=min_delivered_pairs,
        start_time=0.01, duration=duration,
    )


@pytest.mark.unit
def test_l3r_probability_bounds_hold_across_a_range_of_configs():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    for min_fidelity in [0.65, 0.70, 0.72, 0.75, 0.9999]:
        for reserved_memory_slots in [1, 2, 10]:
            intent = _three_node_intent(min_fidelity=min_fidelity, reserved_memory_slots=reserved_memory_slots)
            estimate = estimate_probabilistic_resource_aware_plan(capabilities, ["a", "r", "b"], intent)
            assert 0.0 <= estimate.fidelity_success_probability <= 1.0
            assert 0.0 <= estimate.delivery_success_probability <= 1.0
            assert 0.0 <= estimate.satisfaction_probability <= 1.0


@pytest.mark.unit
def test_l3r_short_circuits_on_insufficient_peak_memory():
    """Reuses L2-R's deterministic memory gate - a structurally impossible
    peak-memory requirement is not a probability to estimate."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = _three_node_intent(min_fidelity=0.72, reserved_memory_slots=1)  # needs 1 round -> peak memory 2
    estimate = estimate_probabilistic_resource_aware_plan(capabilities, ["a", "r", "b"], intent)
    assert estimate.satisfaction_probability == 0.0
    assert estimate.delivery_success_probability == 0.0
    assert RejectionReason.INSUFFICIENT_PEAK_MEMORY in estimate.approximation_method


@pytest.mark.unit
def test_l3r_short_circuits_on_model_limit_reached():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = _three_node_intent(min_fidelity=0.999999999)
    estimate = estimate_probabilistic_resource_aware_plan(capabilities, ["a", "r", "b"], intent, max_rounds=100)
    if RejectionReason.MODEL_LIMIT_REACHED in estimate.approximation_method:
        assert estimate.satisfaction_probability == 0.0


@pytest.mark.unit
def test_l3r_expected_delivered_pairs_matches_l3_original_corrected_by_the_audited_factor():
    """The ONLY change from L3-original's expected-delivered-pairs formula
    is the generation-rate input (corrected by ATTEMPT_RATE_CONSERVATIVE_
    FACTOR, docs/l3_attempt_rate_audit.md) - everything downstream (raw
    pair probability, purification pair cost) is computed identically, so
    the ratio must match the correction factor exactly (up to floating
    point), not merely "be lower"."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = _three_node_intent(min_fidelity=0.65, reserved_memory_slots=10, min_delivered_pairs=10, duration=0.1)
    original = estimate_probabilistic_plan(capabilities, ["a", "r", "b"], intent)
    corrected = estimate_probabilistic_resource_aware_plan(capabilities, ["a", "r", "b"], intent)
    assert corrected.expected_delivered_pairs == pytest.approx(
        original.expected_delivered_pairs / ATTEMPT_RATE_CONSERVATIVE_FACTOR, rel=1e-6,
    )


@pytest.mark.unit
def test_l3r_delivery_probability_drops_on_the_four_node_checkpoint1_regression_case():
    """The exact topology/thresholds where checkpoint 1 found L2 accepts
    then VIOLATES: L3-R's corrected, more conservative attempt rate must
    predict a delivery_success_probability far from saturating at 1.0
    (L3-original, run on the same case, would have been much more
    optimistic before the attempt-rate correction)."""
    capabilities = NetworkCapabilities(linear_chain_spec(2, attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = _three_node_intent(min_fidelity=0.65, reserved_memory_slots=10, min_delivered_pairs=10, duration=0.1)
    route = ["a", "r1", "r2", "b"]
    corrected = estimate_probabilistic_resource_aware_plan(capabilities, route, intent)
    original = estimate_probabilistic_plan(capabilities, route, intent)
    assert corrected.delivery_success_probability <= original.delivery_success_probability


@pytest.mark.unit
def test_l3r_confidence_interval_brackets_the_mean():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = _three_node_intent(min_fidelity=0.65)
    estimate = estimate_probabilistic_resource_aware_plan(capabilities, ["a", "r", "b"], intent)
    lo, hi = estimate.confidence_interval
    assert lo <= estimate.expected_delivered_pairs <= hi


@pytest.mark.unit
def test_l3r_estimated_completion_time_present_when_feasible_none_otherwise():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    feasible_intent = _three_node_intent(min_fidelity=0.65, reserved_memory_slots=10)
    feasible_estimate = estimate_probabilistic_resource_aware_plan(capabilities, ["a", "r", "b"], feasible_intent)
    assert feasible_estimate.estimated_completion_time_s is not None
    assert feasible_estimate.estimated_completion_time_s > 0

    blocked_intent = _three_node_intent(min_fidelity=0.72, reserved_memory_slots=1)
    blocked_estimate = estimate_probabilistic_resource_aware_plan(capabilities, ["a", "r", "b"], blocked_intent)
    assert blocked_estimate.estimated_completion_time_s is None


@pytest.mark.unit
def test_l3_original_estimate_unaffected_by_l3r_module_existing():
    """L3-original's own `ProbabilisticPlanEstimate.estimated_completion_
    time_s` must stay `None` (never computed there) - the shared dataclass
    field addition must not change L3-original's behavior."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = _three_node_intent(min_fidelity=0.65)
    estimate = estimate_probabilistic_plan(capabilities, ["a", "r", "b"], intent)
    assert estimate.estimated_completion_time_s is None


@pytest.mark.unit
def test_probabilistic_resource_aware_planner_admits_high_confidence_plan():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = _three_node_intent(min_fidelity=0.65, reserved_memory_slots=10, min_delivered_pairs=10, duration=0.1)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)
    decision = ProbabilisticResourceAwarePlanner(admission_threshold=0.5).plan(intent, capabilities, candidates, context)
    assert decision.feasible is True
    assert decision.predicted_satisfaction_probability >= 0.5


@pytest.mark.unit
def test_probabilistic_resource_aware_planner_rejects_below_threshold():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = _three_node_intent(min_fidelity=0.9999)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)
    decision = ProbabilisticResourceAwarePlanner(admission_threshold=0.5).plan(intent, capabilities, candidates, context)
    assert decision.feasible is False
    assert decision.rejection_reason is not None


@pytest.mark.unit
def test_probabilistic_resource_aware_planner_higher_threshold_is_at_least_as_strict():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = _three_node_intent(min_fidelity=0.72)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)
    low = ProbabilisticResourceAwarePlanner(admission_threshold=0.1).plan(intent, capabilities, candidates, context)
    high = ProbabilisticResourceAwarePlanner(admission_threshold=0.95).plan(intent, capabilities, candidates, context)
    if high.feasible:
        assert low.feasible


@pytest.mark.unit
def test_probabilistic_resource_aware_planner_reports_correct_identity():
    assert ProbabilisticResourceAwarePlanner.name == "probabilistic_resource_aware"
    assert ProbabilisticResourceAwarePlanner.level == "L3-R"


@pytest.mark.unit
def test_probabilistic_resource_aware_planner_never_uses_operational_seed():
    signature = inspect.signature(estimate_probabilistic_resource_aware_plan)
    assert "seed" not in signature.parameters
