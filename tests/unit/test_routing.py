"""Tests for `ibqn.planning.routing`. A "diamond + long low-loss detour"
topology (`DIVERGING_SPEC`) is used so the three strategies genuinely
disagree on the best route - proving the interchangeable-strategy design
actually changes planner behavior, not just that each strategy runs without
crashing.
"""
import pytest

from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec
from ibqn.planning.feasibility import estimate_swap_only_fidelity
from ibqn.planning.routing import HighestFidelityRouting, LeastLossRouting, ShortestHopCountRouting

LINEAR_SPEC = NetworkTopologySpec(
    nodes=[
        NodeSpec(id="r1", memories=10),
        NodeSpec(id="r2", memories=10),
        NodeSpec(id="r3", memories=10),
    ],
    quantum_links=[
        QuantumLinkSpec(source="r1", destination="r2", distance_m=1000, attenuation_db_per_m=1e-5),
        QuantumLinkSpec(source="r2", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5),
    ],
    stop_time_s=1.0,
)

# r1 -> r3 reachable via 3 routes:
#   r1-rA-r3   (2 hops, moderate loss,  moderate fidelity)
#   r1-rB-r3   (2 hops, high loss,      low fidelity)
#   r1-rC-rD-r3 (3 hops, near-zero loss, high fidelity)
DIVERGING_SPEC = NetworkTopologySpec(
    nodes=[
        NodeSpec(id="r1", memories=10, raw_fidelity=0.99),
        NodeSpec(id="r3", memories=10, raw_fidelity=0.99),
        NodeSpec(id="rA", memories=10, raw_fidelity=0.85, swapping_degradation=0.95),
        NodeSpec(id="rB", memories=10, raw_fidelity=0.70, swapping_degradation=0.80),
        NodeSpec(id="rC", memories=10, raw_fidelity=0.99, swapping_degradation=0.95),
        NodeSpec(id="rD", memories=10, raw_fidelity=0.99, swapping_degradation=0.95),
    ],
    quantum_links=[
        QuantumLinkSpec(source="r1", destination="rA", distance_m=1000, attenuation_db_per_m=1e-3),
        QuantumLinkSpec(source="rA", destination="r3", distance_m=1000, attenuation_db_per_m=1e-3),
        QuantumLinkSpec(source="r1", destination="rB", distance_m=5000, attenuation_db_per_m=1e-3),
        QuantumLinkSpec(source="rB", destination="r3", distance_m=5000, attenuation_db_per_m=1e-3),
        QuantumLinkSpec(source="r1", destination="rC", distance_m=100, attenuation_db_per_m=1e-4),
        QuantumLinkSpec(source="rC", destination="rD", distance_m=100, attenuation_db_per_m=1e-4),
        QuantumLinkSpec(source="rD", destination="r3", distance_m=100, attenuation_db_per_m=1e-4),
    ],
    stop_time_s=1.0,
)


@pytest.mark.unit
def test_shortest_hop_count_routing_on_linear_topology():
    capabilities = NetworkCapabilities(LINEAR_SPEC)
    paths = ShortestHopCountRouting().find_candidate_paths(capabilities, "r1", "r3")

    assert paths[0] == ["r1", "r2", "r3"]


@pytest.mark.unit
def test_no_path_returns_empty_list():
    spec = NetworkTopologySpec(
        nodes=[NodeSpec(id="r1", memories=10), NodeSpec(id="r2", memories=10), NodeSpec(id="isolated", memories=10)],
        quantum_links=[QuantumLinkSpec(source="r1", destination="r2", distance_m=1000, attenuation_db_per_m=1e-5)],
        stop_time_s=1.0,
    )
    capabilities = NetworkCapabilities(spec)

    for strategy in (ShortestHopCountRouting(), LeastLossRouting(), HighestFidelityRouting()):
        assert strategy.find_candidate_paths(capabilities, "r1", "isolated") == []


@pytest.mark.unit
def test_shortest_hop_count_picks_a_two_hop_route_on_diverging_topology():
    capabilities = NetworkCapabilities(DIVERGING_SPEC)
    paths = ShortestHopCountRouting().find_candidate_paths(capabilities, "r1", "r3")

    assert len(paths[0]) == 3  # r1, one interior node, r3: 2 hops


@pytest.mark.unit
def test_least_loss_routing_prefers_the_longer_low_loss_detour():
    capabilities = NetworkCapabilities(DIVERGING_SPEC)
    paths = LeastLossRouting().find_candidate_paths(capabilities, "r1", "r3")

    best = paths[0]
    all_candidates = [["r1", "rA", "r3"], ["r1", "rB", "r3"], ["r1", "rC", "rD", "r3"]]
    best_by_loss = min(
        all_candidates,
        key=lambda path: sum(capabilities.link(path[i], path[i + 1]).loss_db for i in range(len(path) - 1)),
    )
    assert best == best_by_loss
    assert best == ["r1", "rC", "rD", "r3"]  # the detour has ~0.03 dB total vs 2 dB / 10 dB


@pytest.mark.unit
def test_highest_fidelity_routing_prefers_the_route_with_best_estimated_fidelity():
    capabilities = NetworkCapabilities(DIVERGING_SPEC)
    paths = HighestFidelityRouting().find_candidate_paths(capabilities, "r1", "r3")

    best = paths[0]
    all_candidates = [["r1", "rA", "r3"], ["r1", "rB", "r3"], ["r1", "rC", "rD", "r3"]]
    best_by_fidelity = max(
        all_candidates, key=lambda path: estimate_swap_only_fidelity(capabilities, path)[0]
    )
    assert best == best_by_fidelity
    assert best == ["r1", "rC", "rD", "r3"]  # rA/rB have much lower raw_fidelity than rC/rD


@pytest.mark.unit
def test_three_strategies_can_genuinely_disagree():
    """The core value proposition of interchangeable routing: at least two
    of the three strategies must pick different top routes on
    DIVERGING_SPEC."""
    capabilities = NetworkCapabilities(DIVERGING_SPEC)
    hop_choice = ShortestHopCountRouting().find_candidate_paths(capabilities, "r1", "r3")[0]
    loss_choice = LeastLossRouting().find_candidate_paths(capabilities, "r1", "r3")[0]
    fidelity_choice = HighestFidelityRouting().find_candidate_paths(capabilities, "r1", "r3")[0]

    assert hop_choice != loss_choice
    assert hop_choice != fidelity_choice


@pytest.mark.unit
def test_max_candidates_is_respected():
    capabilities = NetworkCapabilities(DIVERGING_SPEC)
    paths = ShortestHopCountRouting().find_candidate_paths(capabilities, "r1", "r3", max_candidates=2)
    assert len(paths) <= 2
