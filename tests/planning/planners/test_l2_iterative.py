"""Unit tests for L2 (`IterativeAnalyticalPurification` /
`IterativeAnalyticalPlanner`) - the iterative purification round-by-round
math, its stopping conditions, and its integration through the same
`IntentPlanner`/`evaluate_route` machinery L1 uses.
"""
# LEGACY-MODEL REGRESSION: the thresholds/numbers below are ket_vector
# closed form (f1*f2*degradation, Dur-Briegel purification). Since the
# physical-realism revision (docs/physical_model.md) the project default
# is bell_diagonal, so these fixtures pin formalism="ket_vector" to keep
# checking the legacy model they document.

from __future__ import annotations

import pytest
from sequence.entanglement_management.purification.bbpssw_circuit import BBPSSWCircuit

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.planning.planners import PlanningContext, generate_candidate_paths
from ibqn.planning.planners.l2_iterative import IterativeAnalyticalPlanner, IterativeAnalyticalPurification
from ibqn.planning.routing import ShortestHopCountRouting

SWAP_ONLY_FIDELITY = 0.686375
ONE_ROUND = BBPSSWCircuit.improved_fidelity(SWAP_ONLY_FIDELITY)
TWO_ROUND = BBPSSWCircuit.improved_fidelity(ONE_ROUND)


@pytest.mark.unit
def test_no_purification_needed_when_swap_only_already_meets_target():
    strategy = IterativeAnalyticalPurification()
    decision = strategy.decide(swap_only_fidelity=0.9, target_fidelity=0.8, allow_purification=True)
    assert decision.attempt is False
    assert decision.rounds_estimate == 0
    assert strategy.last_estimate.target_reached is True
    assert strategy.last_estimate.rounds == []


@pytest.mark.unit
def test_purification_disallowed_short_circuits():
    strategy = IterativeAnalyticalPurification()
    decision = strategy.decide(swap_only_fidelity=0.6, target_fidelity=0.8, allow_purification=False)
    assert decision.attempt is False
    assert strategy.last_estimate.target_reached is False
    assert strategy.last_estimate.resource_feasible is True


@pytest.mark.unit
def test_one_round_matches_bbpssw_formula_applied_once():
    """L2 with a target reachable in exactly one round must match L1
    exactly (both call the same `BBPSSWCircuit.improved_fidelity` formula
    once)."""
    strategy = IterativeAnalyticalPurification()
    target = ONE_ROUND - 1e-6  # just below the one-round result
    decision = strategy.decide(swap_only_fidelity=SWAP_ONLY_FIDELITY, target_fidelity=target, allow_purification=True)
    assert decision.attempt is True
    assert decision.rounds_estimate == 1
    assert decision.fidelity_estimate == pytest.approx(ONE_ROUND)


@pytest.mark.unit
def test_two_rounds_reaches_targets_l1_cannot():
    """The exact scenario the ICC manuscript's false-rejection finding
    covers: L1's one-round ceiling is ~0.7202522; a two-round estimate
    reaches ~0.7572267, covering the entire 0.73-0.75 densified range that
    L1 rejects (docs/false_rejection_root_cause.md)."""
    strategy = IterativeAnalyticalPurification()
    decision = strategy.decide(swap_only_fidelity=SWAP_ONLY_FIDELITY, target_fidelity=0.75, allow_purification=True)
    assert decision.attempt is True
    assert decision.rounds_estimate == 2
    assert decision.fidelity_estimate == pytest.approx(TWO_ROUND)
    assert strategy.last_estimate.target_reached is True


@pytest.mark.unit
def test_round_breakdown_has_correct_cumulative_pair_cost():
    strategy = IterativeAnalyticalPurification()
    strategy.decide(swap_only_fidelity=SWAP_ONLY_FIDELITY, target_fidelity=0.75, allow_purification=True)
    rounds = strategy.last_estimate.rounds
    assert [r.round_index for r in rounds] == [1, 2]
    assert [r.cumulative_pair_cost for r in rounds] == [2, 4]
    assert rounds[0].input_fidelity == pytest.approx(SWAP_ONLY_FIDELITY)
    assert rounds[0].output_fidelity == pytest.approx(ONE_ROUND)
    assert rounds[1].input_fidelity == pytest.approx(ONE_ROUND)
    assert rounds[1].output_fidelity == pytest.approx(TWO_ROUND)


@pytest.mark.unit
def test_max_rounds_cap_stops_before_unreachable_target():
    strategy = IterativeAnalyticalPurification(max_rounds=1)
    decision = strategy.decide(swap_only_fidelity=SWAP_ONLY_FIDELITY, target_fidelity=0.9999, allow_purification=True)
    assert decision.attempt is True
    assert decision.rounds_estimate == 1
    assert strategy.last_estimate.target_reached is False
    assert "max_rounds=1" in strategy.last_estimate.stopping_reason


@pytest.mark.unit
def test_max_pair_cost_marks_resource_infeasible():
    strategy = IterativeAnalyticalPurification(max_rounds=8, max_pair_cost=1)
    decision = strategy.decide(swap_only_fidelity=SWAP_ONLY_FIDELITY, target_fidelity=0.75, allow_purification=True)
    assert strategy.last_estimate.resource_feasible is False
    assert "max_pair_cost=1" in strategy.last_estimate.stopping_reason
    # still returns a usable (if resource-infeasible) PurificationDecision -
    # feasibility.evaluate_route decides what to do with an unreachable
    # target based on the fidelity_estimate returned here, not this flag.
    assert decision.rounds_estimate >= 0


@pytest.mark.unit
def test_fixed_point_detection_stops_before_max_rounds_near_unity():
    """A target essentially at 1.0 should stop on the fixed-point condition
    well before max_rounds, since BBPSSW's gains shrink to numerical noise
    near f=1 - never loops forever or silently returns a wrong 'success'."""
    strategy = IterativeAnalyticalPurification(max_rounds=200)
    decision = strategy.decide(swap_only_fidelity=SWAP_ONLY_FIDELITY, target_fidelity=1.0, allow_purification=True)
    assert decision.attempt is True
    assert strategy.last_estimate.target_reached is False
    assert "fixed point" in strategy.last_estimate.stopping_reason
    assert len(strategy.last_estimate.rounds) < 200


@pytest.mark.unit
def test_l2_planner_matches_l1_when_no_purification_needed():
    """When the swap-only fidelity already meets the target, L1 and L2 must
    agree exactly - the iterative model only diverges from L1 once
    purification is actually attempted."""
    from ibqn.planning.planners import ConservativeOneRoundPlanner

    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = simple_intent(
        intent_id="l2-no-purification", source="a", destination="b", min_fidelity=0.65,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)

    l1 = ConservativeOneRoundPlanner().plan(intent, capabilities, candidates, context)
    l2 = IterativeAnalyticalPlanner().plan(intent, capabilities, candidates, context)

    assert l1.feasible == l2.feasible is True
    assert l1.predicted_average_fidelity == l2.predicted_average_fidelity


@pytest.mark.unit
def test_l2_planner_accepts_where_l1_rejects_in_densified_range():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2, formalism="ket_vector"))
    intent = simple_intent(
        intent_id="l2-accepts", source="a", destination="b", min_fidelity=0.75,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)

    from ibqn.planning.planners import ConservativeOneRoundPlanner

    l1 = ConservativeOneRoundPlanner().plan(intent, capabilities, candidates, context)
    l2 = IterativeAnalyticalPlanner().plan(intent, capabilities, candidates, context)

    assert l1.feasible is False
    assert l2.feasible is True
    assert l2.predicted_average_fidelity == pytest.approx(TWO_ROUND)


@pytest.mark.unit
def test_l2_reports_correct_identity():
    assert IterativeAnalyticalPlanner.name == "iterative_analytical"
    assert IterativeAnalyticalPlanner.level == "L2"


@pytest.mark.unit
def test_l2_never_uses_operational_seed_for_estimation():
    """L2 is deterministic and analytical - it must not accept or require
    any seed at all, unlike L4 (simulation-in-the-loop, not yet
    implemented). This guards against a future edit accidentally wiring a
    seed into L2's estimation path."""
    import inspect

    signature = inspect.signature(IterativeAnalyticalPurification._estimate)
    assert "seed" not in signature.parameters
