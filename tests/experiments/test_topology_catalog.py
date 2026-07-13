"""Smoke tests for the Fase J4 topology catalog (docs/topology_catalog.md,
section 6.6): for every topology, confirm connectivity, candidate routes,
that the planned route is the one SeQUeNCe actually accepts, and run one
real (small) simulation end to end.
"""
from __future__ import annotations

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import diamond_spec
from ibqn.execution.sequence_executor import SequenceExecutor
from ibqn.experiments.topology_catalog import (
    linear_chain_spec,
    near_equivalent_paths_spec,
    small_mesh_spec,
)
from ibqn.intent.repository import IntentRepository
from ibqn.intent.models import IntentStatus
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.sequence_adapter import SequenceAdapter
from ibqn.planning.planner import IntentPlanner
from ibqn.planning.routing import HighestFidelityRouting, LeastLossRouting, ShortestHopCountRouting


def _smoke_test_topology(spec, source, destination, *, seed=0, min_fidelity=0.3):
    # min_fidelity=0.3 is deliberately low: this smoke test only checks
    # structural properties (connectivity, candidate routes, forwarding,
    # acceptance) - it is not meant to probe feasibility limits (that is
    # what campaigns like C02/C03 already do), and longer chains (4
    # repeaters) or the mesh's longest path need a target achievable
    # even after 4-5 swaps' worth of degradation plus one purification round.
    """Shared smoke test body (section 6.6): connectivity, candidate
    routes, forwarding/acceptance, physical parameters, one real run."""
    capabilities = NetworkCapabilities(spec)
    graph = capabilities.graph()
    assert source in graph and destination in graph
    assert any(True for _ in graph.neighbors(source))  # at least one edge out of source

    for strategy in (ShortestHopCountRouting(), LeastLossRouting(), HighestFidelityRouting()):
        candidates = strategy.find_candidate_paths(capabilities, source, destination)
        assert candidates, f"{type(strategy).__name__} found no route {source}->{destination} on this topology"
        for route in candidates:
            assert route[0] == source and route[-1] == destination

    for node in spec.nodes:
        assert node.memories > 0
        assert 0.5 < node.raw_fidelity <= 1.0
    for link in spec.quantum_links:
        assert link.distance_m > 0
        assert link.attenuation_db_per_m > 0

    intent = simple_intent(
        intent_id=f"smoke-{source}-{destination}", source=source, destination=destination,
        min_fidelity=min_fidelity, requested_pairs=5, start_time=0.01, duration=stop_time_margin(spec),
    )
    planner = IntentPlanner(capabilities)
    plan = planner.plan(intent)
    assert plan.feasible, f"expected a feasible plan on this topology, got: {plan.infeasibility_reason}"

    repository = IntentRepository()
    adapter = SequenceAdapter(spec, seed=seed)
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, plan)
    executor.run()

    source_router = adapter.get_router(source)
    accepted_reservation = source_router.network_manager.protocol_stack[-1].accepted_reservations[0]
    assert accepted_reservation.path == plan.route, "the accepted reservation must use exactly the planned route"
    assert repository.get(intent.id).lifecycle.status == IntentStatus.ACTIVE


def stop_time_margin(spec) -> float:
    return max(spec.stop_time_s - 0.02, 0.01)


@pytest.mark.unit
@pytest.mark.parametrize("n_repeaters", [0, 1, 2, 3, 4])
def test_linear_chain_smoke_test_across_repeater_counts(n_repeaters):
    spec = linear_chain_spec(n_repeaters, stop_time_s=0.2)
    _smoke_test_topology(spec, "a", "b")


@pytest.mark.unit
def test_linear_chain_rejects_negative_repeater_count():
    with pytest.raises(ValueError, match="n_repeaters"):
        linear_chain_spec(-1)


@pytest.mark.unit
def test_diamond_heterogeneous_topology_smoke_test():
    _smoke_test_topology(diamond_spec(stop_time_s=0.2), "r1", "r3")


@pytest.mark.unit
def test_small_mesh_smoke_test_between_opposite_corners():
    _smoke_test_topology(small_mesh_spec(stop_time_s=0.2), "a0", "b3")


@pytest.mark.unit
def test_small_mesh_has_multiple_candidate_paths_between_opposite_corners():
    spec = small_mesh_spec()
    capabilities = NetworkCapabilities(spec)
    candidates = ShortestHopCountRouting().find_candidate_paths(capabilities, "a0", "b3", max_candidates=5)
    assert len(candidates) >= 2, "the mesh must offer more than one route between opposite corners"


@pytest.mark.unit
def test_near_equivalent_paths_smoke_test():
    _smoke_test_topology(near_equivalent_paths_spec(stop_time_s=0.2), "source", "dest")


@pytest.mark.unit
def test_near_equivalent_paths_costs_are_genuinely_close_but_not_identical():
    spec = near_equivalent_paths_spec(cost_gap_fraction=0.05)
    capabilities = NetworkCapabilities(spec)
    loss_a = capabilities.link("source", "mid_a").loss_db + capabilities.link("mid_a", "dest").loss_db
    loss_b = capabilities.link("source", "mid_b").loss_db + capabilities.link("mid_b", "dest").loss_db
    assert loss_a != loss_b
    relative_gap = abs(loss_b - loss_a) / loss_a
    assert relative_gap == pytest.approx(0.05, abs=1e-9)


@pytest.mark.unit
def test_near_equivalent_paths_least_loss_still_picks_the_genuinely_cheaper_route():
    spec = near_equivalent_paths_spec(cost_gap_fraction=0.05)
    capabilities = NetworkCapabilities(spec)
    route = LeastLossRouting().find_candidate_paths(capabilities, "source", "dest")[0]
    assert route == ["source", "mid_a", "dest"]  # mid_a's attenuation is lower by construction
