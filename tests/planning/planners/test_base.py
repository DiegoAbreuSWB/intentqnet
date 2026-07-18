"""Tests for the shared `IntentPlannerPolicy` interface helpers - candidate
generation must delegate to the same `RoutingStrategy` every planner level
shares (never a level-specific reimplementation, planner-study brief
section 3)."""
from __future__ import annotations

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.planning.planners import PlanningContext, generate_candidate_paths
from ibqn.planning.planners.base import evaluate_candidates, to_candidate_evaluation
from ibqn.planning.routing import ShortestHopCountRouting


@pytest.mark.unit
def test_generate_candidate_paths_delegates_to_the_context_routing_strategy():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = simple_intent(
        intent_id="base-test", source="a", destination="b", min_fidelity=0.65,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())

    candidates = generate_candidate_paths(intent, capabilities, context)
    direct = ShortestHopCountRouting().find_candidate_paths(capabilities, "a", "b", max_candidates=context.max_candidates)

    assert candidates == direct
    assert candidates == [["a", "r", "b"]]


@pytest.mark.unit
def test_generate_candidate_paths_returns_empty_for_disconnected_endpoints():
    from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec

    spec = NetworkTopologySpec(
        nodes=[NodeSpec(id="a", memories=10), NodeSpec(id="isolated", memories=10), NodeSpec(id="b", memories=10)],
        quantum_links=[QuantumLinkSpec(source="isolated", destination="b", distance_m=1000, attenuation_db_per_m=1e-5)],
        stop_time_s=1.0,
    )
    capabilities = NetworkCapabilities(spec)
    intent = simple_intent(intent_id="disconnected", source="a", destination="b", min_fidelity=0.5, requested_pairs=1)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())

    assert generate_candidate_paths(intent, capabilities, context) == []


@pytest.mark.unit
def test_evaluate_candidates_matches_evaluate_route_per_candidate():
    from ibqn.planning.feasibility import evaluate_route
    from ibqn.planning.fidelity_estimation import ConservativeMinEstimator
    from ibqn.planning.purification import PurifyUntilTarget

    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    intent = simple_intent(
        intent_id="base-eval", source="a", destination="b", min_fidelity=0.65,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )
    candidates = [["a", "r", "b"]]
    purification = PurifyUntilTarget()
    estimator = ConservativeMinEstimator()

    results = evaluate_candidates(
        capabilities, candidates, intent, purification_strategy=purification, fidelity_estimator=estimator,
    )
    direct = evaluate_route(capabilities, candidates[0], intent, purification_strategy=purification, fidelity_estimator=estimator)

    assert len(results) == 1
    assert results[0].feasible == direct.feasible
    assert results[0].swap_only_fidelity == direct.swap_only_fidelity


@pytest.mark.unit
def test_to_candidate_evaluation_uses_purified_fidelity_when_purification_required():
    from ibqn.planning.feasibility import FeasibilityResult

    result = FeasibilityResult(
        route=["a", "r", "b"], hop_fidelities=[0.85, 0.85], swap_only_fidelity=0.686375,
        requires_purification=True, purified_fidelity_estimate=0.7202522030749277,
        purification_rounds_estimate=1, memory_feasible=True, feasible=True,
    )
    evaluation = to_candidate_evaluation(result)
    assert evaluation.predicted_fidelity == pytest.approx(0.7202522030749277)
    assert evaluation.feasible is True
    assert evaluation.extra["purification_rounds_estimate"] == 1


@pytest.mark.unit
def test_to_candidate_evaluation_uses_swap_only_fidelity_when_no_purification():
    from ibqn.planning.feasibility import FeasibilityResult

    result = FeasibilityResult(
        route=["a", "r", "b"], hop_fidelities=[0.85, 0.85], swap_only_fidelity=0.9,
        requires_purification=False, purified_fidelity_estimate=None,
        purification_rounds_estimate=0, memory_feasible=True, feasible=True,
    )
    evaluation = to_candidate_evaluation(result)
    assert evaluation.predicted_fidelity == pytest.approx(0.9)
