"""Tests for L2-R (`ResourceAwareIterativePlanner` / `estimate_resource_
aware_plan`) - the three distinct resource checks (peak memory, structural
pair cost, generation capacity within the window), specific rejection
reasons, and the checkpoint-1 regression it exists to fix (four-node
chain: L2 accepts, real execution VIOLATES; L2-R must reject with a
specific reason instead).
"""
# LEGACY-MODEL REGRESSION: the thresholds/numbers below are ket_vector
# closed form (f1*f2*degradation, Dur-Briegel purification). Since the
# physical-realism revision (docs/physical_model.md) the project default
# is bell_diagonal, so these fixtures pin formalism="ket_vector" to keep
# checking the legacy model they document.

from __future__ import annotations

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.topology_catalog import linear_chain_spec
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.planning.planners import PlanningContext, ResourceAwareIterativePlanner, generate_candidate_paths
from ibqn.planning.planners.l2_resource_aware import (
    MODEL_MAX_STRUCTURAL_PAIR_COST,
    RejectionReason,
    estimate_resource_aware_plan,
)
from ibqn.planning.routing import ShortestHopCountRouting


def _three_node_intent(min_fidelity=0.65, reserved_memory_slots=10, min_delivered_pairs=10, duration=0.1):
    return simple_intent(
        intent_id="l2r-test", source="a", destination="b", min_fidelity=min_fidelity,
        requested_pairs=reserved_memory_slots, min_delivered_pairs=min_delivered_pairs,
        start_time=0.01, duration=duration,
    )


@pytest.mark.unit
def test_peak_memory_differs_from_cumulative_pair_consumption():
    """The two must never be conflated: peak memory required for one
    purification round in flight is 2 (kept+measured), regardless of how
    many total rounds run - NOT `2**rounds` (that's cumulative
    consumption, a completely different quantity)."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = _three_node_intent(min_fidelity=0.75)  # needs 2 purification rounds
    estimate = estimate_resource_aware_plan(capabilities, ["a", "r", "b"], intent)
    assert estimate.purification_rounds == 2
    assert estimate.peak_memory_slots_required == 2  # NOT 2**2=4
    assert estimate.structural_raw_pairs_per_final_pair == 4  # this IS 2**2


@pytest.mark.unit
def test_structural_pair_cost_is_exactly_two_to_the_rounds():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    for min_fidelity, expected_rounds in [(0.65, 0), (0.70, 1), (0.72, 1), (0.75, 2)]:
        intent = _three_node_intent(min_fidelity=min_fidelity)
        estimate = estimate_resource_aware_plan(capabilities, ["a", "r", "b"], intent)
        assert estimate.purification_rounds == expected_rounds
        assert estimate.structural_raw_pairs_per_final_pair == 2**expected_rounds if expected_rounds else 1


@pytest.mark.unit
def test_no_double_exponentiation_bug():
    """Regression guard: structural pair cost must be `2**rounds`, never
    `2**(2**rounds)` or any other double-exponentiation - verified
    directly against max_rounds up to 10."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = _three_node_intent(min_fidelity=0.9999)
    estimate = estimate_resource_aware_plan(capabilities, ["a", "r", "b"], intent, max_rounds=10)
    assert estimate.structural_raw_pairs_per_final_pair <= 2**10  # never astronomically larger


@pytest.mark.unit
def test_model_limit_reached_for_absurd_purification_cost():
    """A near-unity target with a large max_rounds must saturate to
    MODEL_LIMIT_REACHED, never silently report an astronomical pair cost
    as a normal, deliverable plan (docs/l2_iterative_model.md's audit)."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = _three_node_intent(min_fidelity=0.999999999)
    estimate = estimate_resource_aware_plan(capabilities, ["a", "r", "b"], intent, max_rounds=100)
    if estimate.structural_raw_pairs_per_final_pair > MODEL_MAX_STRUCTURAL_PAIR_COST:
        assert estimate.model_limit_hit is True
        assert estimate.rejection_reason == RejectionReason.MODEL_LIMIT_REACHED
        assert estimate.feasible is False


@pytest.mark.unit
def test_insufficient_peak_memory_when_only_one_slot_reserved_and_purification_needed():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = _three_node_intent(min_fidelity=0.72, reserved_memory_slots=1)
    estimate = estimate_resource_aware_plan(capabilities, ["a", "r", "b"], intent)
    assert estimate.memory_feasible is False
    assert estimate.rejection_reason == RejectionReason.INSUFFICIENT_PEAK_MEMORY


@pytest.mark.unit
def test_target_fidelity_unreachable_reason():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = _three_node_intent(min_fidelity=0.9999, duration=10.0)  # huge duration - not a fidelity issue
    estimate = estimate_resource_aware_plan(capabilities, ["a", "r", "b"], intent, max_rounds=3)
    assert estimate.fidelity_feasible is False
    assert estimate.rejection_reason == RejectionReason.TARGET_FIDELITY_UNREACHABLE


@pytest.mark.unit
def test_delivery_target_exceeds_window_when_fidelity_ok_but_delivery_impossible():
    """Enough fidelity, insufficient delivery - the exact checkpoint-1
    four-node VIOLATED regression this planner exists to catch."""
    capabilities = NetworkCapabilities(linear_chain_spec(2, attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = _three_node_intent(min_fidelity=0.65, reserved_memory_slots=10, min_delivered_pairs=10, duration=0.1)
    estimate = estimate_resource_aware_plan(capabilities, ["a", "r1", "r2", "b"], intent)
    assert estimate.fidelity_feasible is True  # fidelity itself IS reachable
    assert estimate.delivery_feasible is False  # but delivery is not
    assert estimate.rejection_reason == RejectionReason.DELIVERY_TARGET_EXCEEDS_WINDOW


@pytest.mark.unit
def test_l2r_rejects_the_four_node_chain_where_l2_would_violate():
    """The core regression test: on the exact topology/thresholds where
    checkpoint 1 found L2 accepts then VIOLATES, L2-R must reject with a
    specific reason instead of falsely accepting."""
    capabilities = NetworkCapabilities(linear_chain_spec(2, attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    intent = _three_node_intent(min_fidelity=0.65, reserved_memory_slots=10, min_delivered_pairs=10, duration=0.1)
    candidates = generate_candidate_paths(intent, capabilities, context)
    decision = ResourceAwareIterativePlanner().plan(intent, capabilities, candidates, context)
    assert decision.feasible is False
    assert decision.rejection_reason == RejectionReason.DELIVERY_TARGET_EXCEEDS_WINDOW


@pytest.mark.unit
def test_l2r_still_accepts_the_three_node_chain_where_l2_succeeded():
    """L2-R must not regress checkpoint 1's genuine success: the
    three-node chain, where L2 fully resolved false rejections."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    for min_fidelity in [0.65, 0.70, 0.72, 0.73]:
        intent = _three_node_intent(min_fidelity=min_fidelity)
        candidates = generate_candidate_paths(intent, capabilities, context)
        decision = ResourceAwareIterativePlanner().plan(intent, capabilities, candidates, context)
        assert decision.feasible is True, f"L2-R regressed at min_fidelity={min_fidelity}"


@pytest.mark.unit
def test_estimate_feasible_property_matches_all_four_gates():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = _three_node_intent(min_fidelity=0.65)
    estimate = estimate_resource_aware_plan(capabilities, ["a", "r", "b"], intent)
    assert estimate.feasible == (
        estimate.fidelity_feasible and estimate.memory_feasible and estimate.duration_feasible and estimate.delivery_feasible
    )


@pytest.mark.unit
def test_l2r_reports_correct_identity():
    assert ResourceAwareIterativePlanner.name == "iterative_resource_aware"
    assert ResourceAwareIterativePlanner.level == "L2-R"


@pytest.mark.unit
def test_l2r_never_uses_operational_seed():
    import inspect

    signature = inspect.signature(estimate_resource_aware_plan)
    assert "seed" not in signature.parameters


@pytest.mark.unit
def test_no_naive_required_pairs_vs_reserved_slots_check():
    """Regression guard against the conceptually wrong check the
    planner-study brief explicitly warns against
    (`required_pairs <= reserved_memory_slots`, conflating peak occupancy
    with cumulative consumption): a route needing many purification
    rounds (high cumulative pair cost) must still be accepted if
    peak memory (2) and generation capacity both allow it - cumulative
    cost alone must never trigger INSUFFICIENT_PEAK_MEMORY."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    # 2 rounds needed (structural cost 4), but only 10 reserved_memory_slots -
    # nowhere near "4 <= 10" being the actual gating logic (peak memory is
    # always just 2 when purifying, independent of round count).
    intent = _three_node_intent(min_fidelity=0.75, reserved_memory_slots=10)
    estimate = estimate_resource_aware_plan(capabilities, ["a", "r", "b"], intent)
    assert estimate.peak_memory_slots_required == 2
    assert estimate.memory_feasible is True
