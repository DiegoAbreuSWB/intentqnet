"""L1 (`ConservativeOneRoundPlanner`) must reproduce the exact planning
decisions used to generate every F01-F08 result and the ICC 2027
manuscript's central finding (docs/false_rejection_root_cause.md) - never
"corrected" (planner-study brief, section 4). These tests pin down that
exact historical behavior at the byte/value level, on the real F03
topologies, at the real densified threshold range.
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
from ibqn.planning.planner import IntentPlanner
from ibqn.planning.planners import ConservativeOneRoundPlanner, PlanningContext, generate_candidate_paths
from ibqn.planning.routing import ShortestHopCountRouting

# Exact F03 densified threshold range (docs/false_rejection_root_cause.md) -
# 0.70-0.72 SATISFIED, 0.73-0.75 REJECTED, both deterministic.
DENSIFIED_THRESHOLDS = [0.65, 0.70, 0.72, 0.73, 0.735, 0.74, 0.745, 0.75]
ONE_ROUND_CEILING = pytest.approx(0.7202522030749277)
SWAP_ONLY_FIDELITY = pytest.approx(0.686375)


def _three_node_intent(min_fidelity: float):
    return simple_intent(
        intent_id="l1-regression", source="a", destination="b", min_fidelity=min_fidelity,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )


@pytest.mark.unit
@pytest.mark.parametrize("min_fidelity", DENSIFIED_THRESHOLDS)
def test_l1_matches_intent_planner_exactly_on_three_node_chain(min_fidelity):
    """L1 must be byte-for-byte equivalent to calling `IntentPlanner`
    directly - it is a wrapper, not a reimplementation (see
    `planning.planners.l1_conservative`'s module docstring)."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = _three_node_intent(min_fidelity)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)

    reference_plan = IntentPlanner(capabilities, routing_strategy=ShortestHopCountRouting()).plan(intent)
    decision = ConservativeOneRoundPlanner().plan(intent, capabilities, candidates, context)

    assert decision.feasible == reference_plan.feasible
    assert decision.selected_plan.route == reference_plan.route
    assert decision.selected_plan.requires_purification == reference_plan.requires_purification
    assert decision.selected_plan.purification_rounds_estimate == reference_plan.purification_rounds_estimate
    if reference_plan.feasible:
        assert decision.selected_plan.estimated_metrics.fidelity == reference_plan.estimated_metrics.fidelity
    else:
        assert decision.selected_plan.infeasibility_reason == reference_plan.infeasibility_reason


@pytest.mark.unit
@pytest.mark.parametrize("min_fidelity", DENSIFIED_THRESHOLDS)
def test_l1_matches_intent_planner_exactly_on_four_node_chain(min_fidelity):
    capabilities = NetworkCapabilities(linear_chain_spec(2, attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = simple_intent(
        intent_id="l1-regression-4node", source="a", destination="b", min_fidelity=min_fidelity,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)

    reference_plan = IntentPlanner(capabilities, routing_strategy=ShortestHopCountRouting()).plan(intent)
    decision = ConservativeOneRoundPlanner().plan(intent, capabilities, candidates, context)

    assert decision.feasible == reference_plan.feasible
    assert decision.selected_plan.route == reference_plan.route


@pytest.mark.unit
def test_l1_reproduces_the_documented_one_round_ceiling():
    """The exact numbers docs/false_rejection_root_cause.md cites: swap-only
    fidelity 0.686375, one-round-purified ceiling 0.7202522030749277 -
    SATISFIED at and below the ceiling, REJECTED strictly above it."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())

    below_ceiling = _three_node_intent(0.72)
    candidates = generate_candidate_paths(below_ceiling, capabilities, context)
    decision = ConservativeOneRoundPlanner().plan(below_ceiling, capabilities, candidates, context)
    assert decision.feasible is True
    assert decision.predicted_average_fidelity == ONE_ROUND_CEILING

    above_ceiling = _three_node_intent(0.73)
    candidates = generate_candidate_paths(above_ceiling, capabilities, context)
    decision = ConservativeOneRoundPlanner().plan(above_ceiling, capabilities, candidates, context)
    assert decision.feasible is False
    assert decision.predicted_average_fidelity is None
    assert "0.730" in decision.rejection_reason


@pytest.mark.unit
def test_l1_never_predicts_fields_it_has_no_basis_for():
    """Section 4: L1 must not predict delivered pairs, throughput, or a
    satisfaction probability - those stay `None`, never a guessed number."""
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = _three_node_intent(0.65)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)
    decision = ConservativeOneRoundPlanner().plan(intent, capabilities, candidates, context)

    assert decision.predicted_satisfaction_probability is None
    assert decision.predicted_delivered_pairs is None
    assert decision.predicted_throughput is None
    assert decision.uncertainty is None


@pytest.mark.unit
def test_l1_reports_correct_identity():
    assert ConservativeOneRoundPlanner.name == "conservative_one_round"
    assert ConservativeOneRoundPlanner.level == "L1"


@pytest.mark.unit
def test_l1_produces_an_explanation_for_both_accept_and_reject():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())

    accepted_intent = _three_node_intent(0.65)
    candidates = generate_candidate_paths(accepted_intent, capabilities, context)
    accepted = ConservativeOneRoundPlanner().plan(accepted_intent, capabilities, candidates, context)
    assert accepted.explanation is not None
    assert accepted.explanation.summary

    rejected_intent = _three_node_intent(0.75)
    candidates = generate_candidate_paths(rejected_intent, capabilities, context)
    rejected = ConservativeOneRoundPlanner().plan(rejected_intent, capabilities, candidates, context)
    assert rejected.explanation is not None
    assert rejected.explanation.counterfactuals
