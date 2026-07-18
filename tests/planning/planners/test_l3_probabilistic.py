"""Unit tests for L3 (`ProbabilisticPlanner` / `estimate_probabilistic_plan`)
- the probability model's components and its integration through the same
`base.evaluate_candidates`/`generate_candidate_paths` machinery L1/L2 use.
"""
from __future__ import annotations

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.planning.planners import PlanningContext, generate_candidate_paths
from ibqn.planning.planners.l3_probabilistic import (
    BSM_SUCCESS_RATE,
    ProbabilisticPlanner,
    _link_success_probability,
    _purification_round_success_probability,
    _route_raw_pair_probability,
    estimate_probabilistic_plan,
)
from ibqn.planning.routing import ShortestHopCountRouting


@pytest.mark.unit
def test_link_success_probability_matches_bsm_rate_at_zero_loss():
    """Zero attenuation/distance: no photon loss, so link success
    probability should equal exactly the BSM success rate (0.5)."""
    assert _link_success_probability(distance_m=0.0, attenuation_db_per_m=1e-5) == pytest.approx(BSM_SUCCESS_RATE)


@pytest.mark.unit
def test_link_success_probability_decreases_with_loss():
    low_loss = _link_success_probability(distance_m=1000, attenuation_db_per_m=1e-5)
    high_loss = _link_success_probability(distance_m=1000, attenuation_db_per_m=1e-2)
    assert 0 < high_loss < low_loss < BSM_SUCCESS_RATE + 1e-9


@pytest.mark.unit
def test_route_raw_pair_probability_multiplies_across_hops():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    per_hop = _link_success_probability(1000, 1e-5)
    route_probability = _route_raw_pair_probability(capabilities, ["a", "r", "b"])
    assert route_probability == pytest.approx(per_hop * per_hop)


@pytest.mark.unit
def test_purification_round_success_probability_is_one_at_perfect_fidelity():
    assert _purification_round_success_probability(1.0) == pytest.approx(1.0)


@pytest.mark.unit
def test_purification_round_success_probability_in_valid_range():
    for f in [0.5, 0.6, 0.7, 0.8, 0.9, 0.99]:
        p = _purification_round_success_probability(f)
        assert 0.0 <= p <= 1.0


@pytest.mark.unit
def test_estimate_probabilistic_plan_no_purification_needed():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = simple_intent(
        intent_id="l3-basic", source="a", destination="b", min_fidelity=0.65,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    estimate = estimate_probabilistic_plan(capabilities, ["a", "r", "b"], intent)
    assert estimate.fidelity_success_probability == 1.0
    assert estimate.expected_delivered_pairs > 0
    assert estimate.delivery_success_probability > 0.99  # thousands of expected pairs vs. goal of 10
    assert estimate.satisfaction_probability == pytest.approx(
        estimate.fidelity_success_probability * estimate.delivery_success_probability,
    )


@pytest.mark.unit
def test_estimate_probabilistic_plan_unreachable_fidelity_target():
    """Beyond L2's max_rounds ceiling, fidelity_success_probability must be
    exactly 0 (not a smooth decay it has no basis for) - see
    docs/l3_probabilistic_model.md, assumption 4."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = simple_intent(
        intent_id="l3-unreachable", source="a", destination="b", min_fidelity=0.9999,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    estimate = estimate_probabilistic_plan(capabilities, ["a", "r", "b"], intent, max_rounds=8)
    assert estimate.fidelity_success_probability == 0.0
    assert estimate.satisfaction_probability == 0.0


@pytest.mark.unit
def test_estimate_probabilistic_plan_confidence_interval_brackets_the_mean():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = simple_intent(
        intent_id="l3-ci", source="a", destination="b", min_fidelity=0.65,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    estimate = estimate_probabilistic_plan(capabilities, ["a", "r", "b"], intent)
    lo, hi = estimate.confidence_interval
    assert lo <= estimate.expected_delivered_pairs <= hi


@pytest.mark.unit
def test_estimate_probabilistic_plan_variance_matches_poisson_mean():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = simple_intent(
        intent_id="l3-var", source="a", destination="b", min_fidelity=0.65,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    estimate = estimate_probabilistic_plan(capabilities, ["a", "r", "b"], intent)
    assert estimate.delivered_pairs_variance == pytest.approx(estimate.expected_delivered_pairs)


@pytest.mark.unit
def test_probabilistic_planner_admits_high_confidence_plan():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = simple_intent(
        intent_id="l3-admit", source="a", destination="b", min_fidelity=0.65,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)
    decision = ProbabilisticPlanner(admission_threshold=0.5).plan(intent, capabilities, candidates, context)

    assert decision.feasible is True
    assert decision.predicted_satisfaction_probability >= 0.5
    assert decision.predicted_delivered_pairs is not None
    assert decision.selected_plan.feasible is True


@pytest.mark.unit
def test_probabilistic_planner_rejects_below_threshold():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = simple_intent(
        intent_id="l3-reject", source="a", destination="b", min_fidelity=0.9999,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)
    decision = ProbabilisticPlanner(admission_threshold=0.5).plan(intent, capabilities, candidates, context)

    assert decision.feasible is False
    assert decision.rejection_reason is not None
    assert "admission_threshold" in decision.rejection_reason


@pytest.mark.unit
def test_probabilistic_planner_higher_threshold_is_at_least_as_strict():
    """A higher admission_threshold must never accept an intent a lower
    threshold rejects (monotonicity of the admission rule)."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = simple_intent(
        intent_id="l3-monotone", source="a", destination="b", min_fidelity=0.72,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)

    low = ProbabilisticPlanner(admission_threshold=0.5).plan(intent, capabilities, candidates, context)
    high = ProbabilisticPlanner(admission_threshold=0.95).plan(intent, capabilities, candidates, context)
    if high.feasible:
        assert low.feasible


@pytest.mark.unit
def test_probabilistic_planner_reports_correct_identity():
    assert ProbabilisticPlanner.name == "probabilistic"
    assert ProbabilisticPlanner.level == "L3"


@pytest.mark.unit
def test_probabilistic_planner_never_uses_operational_seed():
    import inspect

    signature = inspect.signature(estimate_probabilistic_plan)
    assert "seed" not in signature.parameters
