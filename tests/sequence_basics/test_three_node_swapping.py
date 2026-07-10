"""Tests for entanglement swapping across a 3-node linear chain (r1-m1-r2-m2-r3),
driven through the real reservation pipeline (`NetworkManager.request`), mirroring
`example/demo_for_beginners/three_node_eg_ep_es.ipynb` (see
`docs/sequence_code_analysis.md`, sections 4.2 and 4.3).

`target_fidelity` is kept below the fidelity achievable by a single swap (no
purification needed), so this file isolates swapping behavior. Purification is
covered separately in `test_purification.py`.
"""
import pytest

from sequence.kernel.timeline import Timeline
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel

RAW_FIDELITY = 0.95
SWAPPING_DEGRADATION = 0.95
REQUEST_FIDELITY = 0.8  # below RAW_FIDELITY**2 * SWAPPING_DEGRADATION -> no purification needed
EXPECTED_SWAP_FIDELITY = RAW_FIDELITY * RAW_FIDELITY * SWAPPING_DEGRADATION


def build_three_node_topology(memory_size=10, sim_time_ms=300, cc_delay_ms=0.1, qc_atten=1e-5, qc_dist_km=1):
    tl = Timeline(sim_time_ms * 1e9)

    r1 = QuantumRouter("r1", tl, memory_size)
    r2 = QuantumRouter("r2", tl, memory_size * 2)
    r3 = QuantumRouter("r3", tl, memory_size)
    m1 = BSMNode("m1", tl, ["r1", "r2"])
    m2 = BSMNode("m2", tl, ["r2", "r3"])

    r1.add_bsm_node(m1.name, r2.name)
    r2.add_bsm_node(m1.name, r1.name)
    r2.add_bsm_node(m2.name, r3.name)
    r3.add_bsm_node(m2.name, r2.name)

    r2.swapping_success_prob = 1
    r2.swapping_degradation = SWAPPING_DEGRADATION

    nodes = [r1, r2, r3, m1, m2]
    for i, node in enumerate(nodes):
        node.set_seed(i)

    for node in (r1, r2, r3):
        memory_array = node.get_components_by_type("MemoryArray")[0]
        memory_array.update_memory_params("coherence_time", 10)
        memory_array.update_memory_params("raw_fidelity", RAW_FIDELITY)

    for node1 in nodes:
        for node2 in nodes:
            if node1 is node2:
                continue
            cc = ClassicalChannel(f"cc_{node1.name}_{node2.name}", tl, 1e3, delay=cc_delay_ms * 1e9)
            cc.set_ends(node1, node2.name)

    qc_dist_m = qc_dist_km * 1e3
    qc0 = QuantumChannel("qc_r1_m1", tl, qc_atten, qc_dist_m)
    qc1 = QuantumChannel("qc_r2_m1", tl, qc_atten, qc_dist_m)
    qc0.set_ends(r1, m1.name)
    qc1.set_ends(r2, m1.name)
    qc2 = QuantumChannel("qc_r2_m2", tl, qc_atten, qc_dist_m)
    qc3 = QuantumChannel("qc_r3_m2", tl, qc_atten, qc_dist_m)
    qc2.set_ends(r2, m2.name)
    qc3.set_ends(r3, m2.name)

    r1.network_manager.routing_protocol.update_forwarding_rule("r2", "r2")
    r1.network_manager.routing_protocol.update_forwarding_rule("r3", "r2")
    r2.network_manager.routing_protocol.update_forwarding_rule("r1", "r1")
    r2.network_manager.routing_protocol.update_forwarding_rule("r3", "r3")
    r3.network_manager.routing_protocol.update_forwarding_rule("r1", "r2")
    r3.network_manager.routing_protocol.update_forwarding_rule("r2", "r2")

    return tl, r1, r2, r3, m1, m2


@pytest.mark.unit
def test_reservation_is_accepted_with_correct_path():
    tl, r1, r2, r3, m1, m2 = build_three_node_topology(memory_size=10)
    tl.init()
    r1.network_manager.request("r3", int(0.1e12), int(10e12), 10, REQUEST_FIDELITY)
    tl.run()

    reservation_protocol = r1.network_manager.protocol_stack[1]
    assert len(reservation_protocol.accepted_reservations) == 1
    reservation = reservation_protocol.accepted_reservations[0]
    assert reservation.path == ["r1", "r2", "r3"]
    assert reservation.memory_size == 10
    assert reservation.fidelity == REQUEST_FIDELITY


@pytest.mark.unit
def test_end_to_end_pairs_reach_target_fidelity_without_purification():
    tl, r1, r2, r3, m1, m2 = build_three_node_topology(memory_size=10)
    tl.init()
    r1.network_manager.request("r3", int(0.1e12), int(10e12), 10, REQUEST_FIDELITY)
    tl.run()

    r1_delivered = [info for info in r1.resource_manager.memory_manager if info.entangle_time > 0]
    r3_delivered = [info for info in r3.resource_manager.memory_manager if info.entangle_time > 0]

    assert len(r1_delivered) == 10
    assert len(r3_delivered) == 10

    for info in r1_delivered:
        assert info.state == "ENTANGLED"  # not PURIFIED: no purification round should have triggered
        assert info.fidelity == pytest.approx(EXPECTED_SWAP_FIDELITY)
        assert info.fidelity >= REQUEST_FIDELITY
        assert info.remote_node == "r3"

    for info in r3_delivered:
        assert info.state == "ENTANGLED"
        assert info.fidelity == pytest.approx(EXPECTED_SWAP_FIDELITY)
        assert info.remote_node == "r1"


@pytest.mark.unit
def test_end_to_end_pairing_is_mutually_consistent():
    tl, r1, r2, r3, m1, m2 = build_three_node_topology(memory_size=10)
    tl.init()
    r1.network_manager.request("r3", int(0.1e12), int(10e12), 10, REQUEST_FIDELITY)
    tl.run()

    r3_memory_manager = list(r3.resource_manager.memory_manager)
    for info in r1.resource_manager.memory_manager:
        if info.entangle_time <= 0:
            continue
        remote_info = next(i for i in r3_memory_manager if i.memory.name == info.remote_memo)
        assert remote_info.remote_node == "r1"
        assert remote_info.remote_memo == info.memory.name


@pytest.mark.unit
def test_interior_node_never_holds_the_end_to_end_pair():
    """The interior node (r2) only brokers the swap: it consumes its two
    elementary pairs and returns them to RAW immediately after `start()`
    (`swapping_circuit.py`, `update_resource_manager(..., MemoryInfo.RAW)`),
    then the memory is picked back up by the still-installed generation rule
    for a further round - so at any snapshot r2 shows ENTANGLED/OCCUPIED
    elementary pairs, but it must never appear as the remote endpoint of a
    delivered r1<->r3 pair, and must never reach PURIFIED (no purification is
    expected in this scenario)."""
    tl, r1, r2, r3, m1, m2 = build_three_node_topology(memory_size=10)
    tl.init()
    r1.network_manager.request("r3", int(0.1e12), int(10e12), 10, REQUEST_FIDELITY)
    tl.run()

    r2_states = {info.state for info in r2.resource_manager.memory_manager}
    assert "PURIFIED" not in r2_states

    for info in r1.resource_manager.memory_manager:
        assert info.remote_node != "r2"
    for info in r3.resource_manager.memory_manager:
        assert info.remote_node != "r2"
