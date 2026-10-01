"""Tests for the calibrated-suite infrastructure: fiber-following classical
delays (`NetworkTopologySpec.classical_delay_model`), the theoretical-
operations profile, and `experiments.realistic_topologies`.
"""
from __future__ import annotations

import pytest

from ibqn.experiments.realistic_topologies import realistic_chain, realistic_diamond, realistic_mesh, realistic_star
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.platforms import (
    DEPLOYED_FIBER_ATTENUATION_DB_PER_M,
    SIV_2024,
    SIV_2024_THEORETICAL_OPS,
    TRAPPED_ION_2023,
    apply_platform,
)
from ibqn.network.sequence_adapter import SequenceAdapter
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec
from ibqn.planning.routing import HighestFidelityRouting, LeastLossRouting, ShortestHopCountRouting


def _two_link_spec(model: str) -> NetworkTopologySpec:
    return NetworkTopologySpec(
        nodes=[NodeSpec(id=n, memories=4) for n in ("a", "r", "b")],
        quantum_links=[
            QuantumLinkSpec(source="a", destination="r", distance_m=2_000, attenuation_db_per_m=2e-4),
            QuantumLinkSpec(source="r", destination="b", distance_m=10_000, attenuation_db_per_m=2e-4),
        ],
        classical_delay_s=1e-3, classical_delay_model=model, stop_time_s=0.1,
    )


@pytest.mark.unit
def test_uniform_classical_delay_is_the_original_single_value():
    spec = _two_link_spec("uniform")
    assert spec.classical_delay_between("a", "r") == spec.classical_delay_between("a", "b") == 1e-3
    config = spec.to_router_net_topo_config(seed=0)
    assert {c["delay"] for c in config["cconnections"]} == {int(1e-3 * 1e12)}


@pytest.mark.unit
def test_fiber_classical_delay_follows_the_shortest_fiber_path():
    spec = _two_link_spec("fiber")
    assert spec.classical_delay_between("a", "r") == pytest.approx(2_000 / 2e8)      # 10 us
    assert spec.classical_delay_between("r", "b") == pytest.approx(10_000 / 2e8)     # 50 us
    assert spec.classical_delay_between("a", "b") == pytest.approx(12_000 / 2e8)     # through r
    delays = {frozenset({c["node1"], c["node2"]}): c["delay"] for c in spec.to_router_net_topo_config(seed=0)["cconnections"]}
    assert delays[frozenset({"a", "r"})] == 10_000_000  # ps
    assert delays[frozenset({"r", "b"})] == 50_000_000
    assert delays[frozenset({"a", "b"})] == 60_000_000
    capabilities = NetworkCapabilities(spec)
    assert capabilities.classical_delay_between("b", "r") == pytest.approx(5e-5)
    assert capabilities.classical_delay_between("a", "a") == 0.0


@pytest.mark.unit
def test_fiber_delay_falls_back_to_the_scalar_for_pairs_without_a_fiber_path():
    spec = NetworkTopologySpec(
        nodes=[NodeSpec(id=n, memories=2) for n in ("a", "b", "island")],
        quantum_links=[QuantumLinkSpec(source="a", destination="b", distance_m=4_000, attenuation_db_per_m=2e-4)],
        classical_delay_s=7e-4, classical_delay_model="fiber", stop_time_s=0.1,
    )
    assert spec.classical_delay_between("a", "b") == pytest.approx(2e-5)
    assert spec.classical_delay_between("a", "island") == 7e-4


@pytest.mark.unit
def test_the_adapter_really_builds_per_pair_classical_channels():
    adapter = SequenceAdapter(_two_link_spec("fiber"), seed=0)
    a, r, b = (adapter.get_router(n) for n in ("a", "r", "b"))
    assert a.cchannels["r"].delay == 10_000_000
    assert r.cchannels["b"].delay == 50_000_000
    assert a.cchannels["b"].delay == 60_000_000


@pytest.mark.unit
def test_theoretical_operations_profile_differs_from_the_literature_one_only_in_gates_and_measurement():
    literature, theoretical = SIV_2024, SIV_2024_THEORETICAL_OPS
    assert theoretical.gate_fidelity == theoretical.measurement_fidelity == 1.0
    assert literature.gate_fidelity < 1.0 and literature.measurement_fidelity < 1.0
    for field in ("raw_fidelity", "swapping_success_prob", "coherence_time_s", "decoherence_errors",
                  "memory_efficiency", "memory_frequency_hz", "detector_efficiency", "attenuation_db_per_m", "cutoff_ratio"):
        assert getattr(theoretical, field) == getattr(literature, field), field
    assert theoretical.name == "siv_2024_theoretical_ops"


@pytest.mark.unit
def test_apply_platform_switches_to_fiber_delays():
    base = NetworkTopologySpec(
        nodes=[NodeSpec(id=n, memories=4) for n in ("a", "r", "b")],
        quantum_links=[
            QuantumLinkSpec(source="a", destination="r", distance_m=5_000, attenuation_db_per_m=1e-5),
            QuantumLinkSpec(source="r", destination="b", distance_m=5_000, attenuation_db_per_m=1e-5),
        ],
        classical_delay_s=1e-4, stop_time_s=0.1,
    )
    spec = apply_platform(base, TRAPPED_ION_2023)
    assert spec.classical_delay_model == "fiber"
    assert spec.classical_delay_between("a", "r") == pytest.approx(2.5e-5)
    assert spec.classical_delay_between("a", "b") == pytest.approx(5e-5)


@pytest.mark.unit
@pytest.mark.parametrize("n_repeaters", [0, 1, 3])
def test_realistic_chain_shape_and_hardware(n_repeaters):
    spec = realistic_chain(n_repeaters, platform=SIV_2024_THEORETICAL_OPS, link_m=8_000, end_memories=4, repeater_memories=8)
    assert [n.id for n in spec.nodes] == ["a"] + [f"r{i + 1}" for i in range(n_repeaters)] + ["b"]
    assert [n.memories for n in spec.nodes] == [4] + [8] * n_repeaters + [4]
    assert spec.platform == "siv_2024_theoretical_ops" and spec.classical_delay_model == "fiber"
    assert all(link.distance_m == 8_000 for link in spec.quantum_links)
    assert all(node.gate_fidelity == 1.0 and node.raw_fidelity == 0.86 for node in spec.nodes)
    with pytest.raises(ValueError):
        realistic_chain(-1)


@pytest.mark.unit
def test_realistic_diamond_makes_the_routing_strategies_disagree_for_physical_reasons():
    spec = realistic_diamond()
    capabilities = NetworkCapabilities(spec)
    direct, detour = ["r1", "bad", "r3"], ["r1", "good1", "good2", "r3"]
    assert ShortestHopCountRouting().find_candidate_paths(capabilities, "r1", "r3")[0] == direct
    assert HighestFidelityRouting().find_candidate_paths(capabilities, "r1", "r3")[0] == direct   # one swap beats two
    assert LeastLossRouting().find_candidate_paths(capabilities, "r1", "r3")[0] == detour
    assert capabilities.link("r1", "bad").attenuation_db_per_m == DEPLOYED_FIBER_ATTENUATION_DB_PER_M
    assert capabilities.link("r1", "good1").attenuation_db_per_m == SIV_2024.attenuation_db_per_m
    # the direct route is also slower to negotiate: 100 us vs 25 us per attempt exchange
    assert capabilities.classical_delay_between("r1", "bad") == pytest.approx(1e-4)
    assert capabilities.classical_delay_between("r1", "good1") == pytest.approx(2.5e-5)


@pytest.mark.unit
def test_realistic_mesh_and_star_shapes():
    mesh = realistic_mesh()
    assert len(mesh.nodes) == 8 and len(mesh.quantum_links) == 10
    star = realistic_star(n_leaves=4, center_memories=16, leaf_memories=4)
    assert [n.id for n in star.nodes] == ["center", "leaf1", "leaf2", "leaf3", "leaf4"]
    assert star.node("center").memories == 16 and star.node("leaf3").memories == 4
    assert all(spec.classical_delay_model == "fiber" for spec in (mesh, star))
