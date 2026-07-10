"""Tests for reservation admission control (`NetworkManager.request` /
`RSVPProtocol`), using a minimal 2-router + 1-BSM-node topology (see
docs/sequence_code_analysis.md, sections 4.2 and 4.5).

Admission is purely a memory-count/time-window check
(`MemoryTimeCard.schedule_reservation`) - there is no fidelity feasibility
estimation in the core (documented limitation, section 4.7). These tests
therefore only exercise memory/time admission, captured through the real
`RequestApp.get_reservation_result(reservation, bool)` callback.
"""
import pytest

from sequence.kernel.timeline import Timeline
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from sequence.app.request_app import RequestApp

MEMORIES_PER_ROUTER = 10


class RecordingRequestApp(RequestApp):
    def __init__(self, node):
        super().__init__(node)
        self.results = []  # list of (reservation, bool)

    def get_reservation_result(self, reservation, result):
        self.results.append((reservation, result))
        super().get_reservation_result(reservation, result)


def build_two_node_topology(sim_time_ms=50):
    tl = Timeline(sim_time_ms * 1e9)

    r1 = QuantumRouter("r1", tl, MEMORIES_PER_ROUTER)
    r2 = QuantumRouter("r2", tl, MEMORIES_PER_ROUTER)
    m1 = BSMNode("m1", tl, ["r1", "r2"])
    r1.add_bsm_node(m1.name, r2.name)
    r2.add_bsm_node(m1.name, r1.name)

    for i, node in enumerate((r1, r2, m1)):
        node.set_seed(i)

    for node1 in (r1, r2, m1):
        for node2 in (r1, r2, m1):
            if node1 is node2:
                continue
            cc = ClassicalChannel(f"cc_{node1.name}_{node2.name}", tl, 1e3, delay=1e8)
            cc.set_ends(node1, node2.name)

    qc1 = QuantumChannel("qc_r1_m1", tl, 1e-5, 1e3)
    qc1.set_ends(r1, m1.name)
    qc2 = QuantumChannel("qc_r2_m1", tl, 1e-5, 1e3)
    qc2.set_ends(r2, m1.name)

    r1.network_manager.routing_protocol.update_forwarding_rule("r2", "r2")
    r2.network_manager.routing_protocol.update_forwarding_rule("r1", "r1")

    app1 = RecordingRequestApp(r1)
    app2 = RecordingRequestApp(r2)

    tl.init()
    return tl, r1, r2, m1, app1, app2


@pytest.mark.unit
def test_reservation_within_capacity_is_accepted():
    tl, r1, r2, m1, app1, app2 = build_two_node_topology()

    app1.start("r2", int(1e9), int(20e9), MEMORIES_PER_ROUTER, 0.5)
    tl.run()

    assert len(app1.results) == 1
    reservation, result = app1.results[0]
    assert result is True
    assert reservation.path == ["r1", "r2"]
    assert reservation.memory_size == MEMORIES_PER_ROUTER


@pytest.mark.unit
def test_reservation_exceeding_available_memory_is_rejected():
    tl, r1, r2, m1, app1, app2 = build_two_node_topology()

    app1.start("r2", int(1e9), int(20e9), MEMORIES_PER_ROUTER * 2, 0.5)
    tl.run()

    assert len(app1.results) == 1
    _, result = app1.results[0]
    assert result is False


@pytest.mark.unit
def test_two_time_disjoint_reservations_are_both_accepted():
    tl, r1, r2, m1, app1, app2 = build_two_node_topology(sim_time_ms=50)

    app1.start("r2", int(1e9), int(10e9), MEMORIES_PER_ROUTER, 0.5)
    tl.run()
    assert app1.results[-1][1] is True

    # second reservation starts strictly after the first one's end_time
    app1.start("r2", int(11e9), int(20e9), MEMORIES_PER_ROUTER, 0.5)
    tl.run()
    assert app1.results[-1][1] is True
    assert len(app1.results) == 2


@pytest.mark.unit
def test_overlapping_reservations_exceeding_capacity_reject_the_second():
    tl, r1, r2, m1, app1, app2 = build_two_node_topology(sim_time_ms=50)

    app1.start("r2", int(1e9), int(20e9), MEMORIES_PER_ROUTER, 0.5)
    tl.run()
    assert app1.results[-1][1] is True

    # overlaps [1e9, 20e9] in time and would need more memory than remains free
    app1.start("r2", int(5e9), int(15e9), MEMORIES_PER_ROUTER, 0.5)
    tl.run()
    assert app1.results[-1][1] is False
    assert len(app1.results) == 2


@pytest.mark.unit
def test_accepted_reservation_is_tracked_by_both_endpoints():
    tl, r1, r2, m1, app1, app2 = build_two_node_topology()

    app1.start("r2", int(1e9), int(20e9), MEMORIES_PER_ROUTER, 0.5)
    tl.run()

    r1_reservations = r1.network_manager.protocol_stack[1].accepted_reservations
    r2_reservations = r2.network_manager.protocol_stack[1].accepted_reservations
    assert len(r1_reservations) == 1
    assert len(r2_reservations) == 1
    assert r1_reservations[0].initiator == "r1"
    assert r1_reservations[0].responder == "r2"
