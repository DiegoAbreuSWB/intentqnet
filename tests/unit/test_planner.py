"""Tests for `ibqn.planning.planner.IntentPlanner` - pure planning logic
(no SeQUeNCe simulation). End-to-end plan-then-execute is covered in
tests/integration/test_intent_to_execution.py.
"""
import pytest

from ibqn.intent.models import (
    EntanglementIntent, IntentEndpoints, IntentPolicy, IntentRequirements, IntentValidation, SuccessCondition,
)
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec
from ibqn.planning.planner import IntentPlanner
from ibqn.planning.purification import NeverPurify
from ibqn.planning.routing import HighestFidelityRouting, LeastLossRouting, ShortestHopCountRouting

LINEAR_SPEC = NetworkTopologySpec(
    nodes=[
        NodeSpec(id="r1", memories=10, raw_fidelity=0.85, swapping_degradation=0.95),
        NodeSpec(id="r2", memories=20, raw_fidelity=0.85, swapping_degradation=0.95),
        NodeSpec(id="r3", memories=10, raw_fidelity=0.85, swapping_degradation=0.95),
    ],
    quantum_links=[
        QuantumLinkSpec(source="r1", destination="r2", distance_m=1000, attenuation_db_per_m=1e-5),
        QuantumLinkSpec(source="r2", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5),
    ],
    stop_time_s=1.0,
)

# Two 2-hop routes of very different quality, so more than one candidate is
# feasible and the planner has something real to rank/keep as fallback.
TWO_ROUTE_SPEC = NetworkTopologySpec(
    nodes=[
        NodeSpec(id="r1", memories=10),
        NodeSpec(id="r3", memories=10),
        NodeSpec(id="good", memories=10, raw_fidelity=0.95, swapping_degradation=0.98),
        NodeSpec(id="bad", memories=10, raw_fidelity=0.90, swapping_degradation=0.90),
    ],
    quantum_links=[
        QuantumLinkSpec(source="r1", destination="good", distance_m=1000, attenuation_db_per_m=1e-5),
        QuantumLinkSpec(source="good", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5),
        QuantumLinkSpec(source="r1", destination="bad", distance_m=1000, attenuation_db_per_m=1e-5),
        QuantumLinkSpec(source="bad", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5),
    ],
    stop_time_s=1.0,
)


def build_intent(min_fidelity, requested_pairs=10, allow_purification=True) -> EntanglementIntent:
    return EntanglementIntent(
        id="intent-001",
        endpoints=IntentEndpoints(source="r1", destination="r3"),
        requirements=IntentRequirements(
            min_fidelity=min_fidelity, min_throughput=1, max_latency=1.0,
            requested_pairs=requested_pairs, start_time=0, duration=1,
        ),
        policy=IntentPolicy(allow_purification=allow_purification),
        validation=IntentValidation(
            metrics=["delivered_pairs"],
            success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=requested_pairs)],
        ),
    )


@pytest.mark.unit
def test_planner_produces_feasible_plan_with_default_strategies():
    planner = IntentPlanner(NetworkCapabilities(LINEAR_SPEC))
    plan = planner.plan(build_intent(min_fidelity=0.65))

    assert plan.feasible is True
    assert plan.route == ["r1", "r2", "r3"]
    assert plan.requires_purification is False
    assert plan.estimated_metrics is not None
    assert plan.estimated_metrics.fidelity == pytest.approx(0.85 * 0.85 * 0.95)
    assert len(plan.reservations) == 3


@pytest.mark.unit
def test_planner_rejects_intent_with_no_path():
    spec = NetworkTopologySpec(
        nodes=[NodeSpec(id="r1", memories=10), NodeSpec(id="isolated", memories=10), NodeSpec(id="r3", memories=10)],
        quantum_links=[QuantumLinkSpec(source="isolated", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5)],
        stop_time_s=1.0,
    )
    planner = IntentPlanner(NetworkCapabilities(spec))
    plan = planner.plan(build_intent(min_fidelity=0.5))

    assert plan.feasible is False
    assert "no path found" in plan.infeasibility_reason
    assert plan.route == []


@pytest.mark.unit
def test_planner_rejects_intent_when_no_candidate_meets_fidelity():
    planner = IntentPlanner(NetworkCapabilities(LINEAR_SPEC))
    plan = planner.plan(build_intent(min_fidelity=0.999))

    assert plan.feasible is False
    assert "no candidate route is feasible" in plan.infeasibility_reason


@pytest.mark.unit
def test_planner_rejects_when_purification_needed_but_disallowed():
    planner = IntentPlanner(NetworkCapabilities(LINEAR_SPEC))
    plan = planner.plan(build_intent(min_fidelity=0.70, allow_purification=False))

    assert plan.feasible is False


@pytest.mark.unit
def test_planner_records_fallback_routes():
    planner = IntentPlanner(NetworkCapabilities(TWO_ROUTE_SPEC), routing_strategy=HighestFidelityRouting())
    plan = planner.plan(build_intent(min_fidelity=0.5, requested_pairs=5))

    assert plan.feasible is True
    assert plan.route == ["r1", "good", "r3"]
    assert plan.fallback_routes == [["r1", "bad", "r3"]]


@pytest.mark.unit
def test_swapping_different_routing_strategy_changes_the_plan():
    intent = build_intent(min_fidelity=0.5, requested_pairs=5)
    capabilities = NetworkCapabilities(TWO_ROUTE_SPEC)

    plan_default = IntentPlanner(capabilities, routing_strategy=ShortestHopCountRouting()).plan(intent)
    plan_fidelity = IntentPlanner(capabilities, routing_strategy=HighestFidelityRouting()).plan(intent)

    # both routes are 2 hops, so ShortestHopCountRouting ties and returns
    # whichever networkx yields first; HighestFidelityRouting must prefer "good"
    assert plan_fidelity.route == ["r1", "good", "r3"]
    assert plan_fidelity.estimated_metrics.fidelity >= plan_default.estimated_metrics.fidelity


@pytest.mark.unit
def test_never_purify_strategy_produces_infeasible_plan_where_default_would_purify():
    planner_default = IntentPlanner(NetworkCapabilities(LINEAR_SPEC))
    planner_never_purify = IntentPlanner(NetworkCapabilities(LINEAR_SPEC), purification_strategy=NeverPurify())
    intent = build_intent(min_fidelity=0.70)  # needs exactly one purification round

    assert planner_default.plan(intent).feasible is True
    assert planner_never_purify.plan(intent).feasible is False


@pytest.mark.unit
def test_swapping_strategy_note_is_recorded_on_the_plan():
    planner = IntentPlanner(NetworkCapabilities(LINEAR_SPEC))
    plan = planner.plan(build_intent(min_fidelity=0.65))

    assert "binary-bisection" in plan.swapping_strategy_note
    assert "r2" in plan.swapping_strategy_note
