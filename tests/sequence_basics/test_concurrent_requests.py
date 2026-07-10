"""Tests for concurrent reservations sharing a common repeater's memory pool.

Topology: a star of 3 leaves (`leaf1`, `leaf2`, `leaf3`) around a shared
interior repeater (`center`), each leaf connected to `center` through its own
BSM node. `leaf1` concurrently requests entanglement with both `leaf2` and
`leaf3`, so both reservations compete for `center`'s memory pool (an interior
node reserves `2 * memory_size` per reservation - see
docs/sequence_code_analysis.md, section 4.5). There is no fairness/priority
policy beyond admission order (documented limitation, section 4.7): these
tests only check that concurrent admission is memory-safe (no double
booking) and that delivered pairs never cross-contaminate between the two
independent reservations.
"""
import pytest

from sequence.kernel.timeline import Timeline
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from sequence.app.request_app import RequestApp

LEAF_MEMORY_SIZE = 20
PER_RESERVATION_SIZE = 8  # each of the 2 reservations asks for 8 memories at leaf1/leaf2/leaf3;
                           # center needs 2 * 8 = 16 per reservation, i.e. 32 total for both


class RecordingRequestApp(RequestApp):
    def __init__(self, node):
        super().__init__(node)
        self.results = []  # (reservation, bool)

    def get_reservation_result(self, reservation, result):
        self.results.append((reservation, result))
        super().get_reservation_result(reservation, result)


def build_star_topology(center_memory_size, sim_time_ms=100):
    tl = Timeline(sim_time_ms * 1e9)

    center = QuantumRouter("center", tl, center_memory_size)
    leaf1 = QuantumRouter("leaf1", tl, LEAF_MEMORY_SIZE)
    leaf2 = QuantumRouter("leaf2", tl, LEAF_MEMORY_SIZE)
    leaf3 = QuantumRouter("leaf3", tl, LEAF_MEMORY_SIZE)
    bsm_c1 = BSMNode("bsm_c1", tl, ["center", "leaf1"])
    bsm_c2 = BSMNode("bsm_c2", tl, ["center", "leaf2"])
    bsm_c3 = BSMNode("bsm_c3", tl, ["center", "leaf3"])

    for a, b, bsm in ((center, leaf1, bsm_c1), (center, leaf2, bsm_c2), (center, leaf3, bsm_c3)):
        a.add_bsm_node(bsm.name, b.name)
        b.add_bsm_node(bsm.name, a.name)

    nodes = [center, leaf1, leaf2, leaf3, bsm_c1, bsm_c2, bsm_c3]
    for i, node in enumerate(nodes):
        node.set_seed(i)

    for n1 in nodes:
        for n2 in nodes:
            if n1 is n2:
                continue
            cc = ClassicalChannel(f"cc_{n1.name}_{n2.name}", tl, 1e3, delay=1e8)
            cc.set_ends(n1, n2.name)

    for a, b, bsm in ((center, leaf1, bsm_c1), (center, leaf2, bsm_c2), (center, leaf3, bsm_c3)):
        qa = QuantumChannel(f"qc_{a.name}_{bsm.name}", tl, 1e-5, 1e3)
        qa.set_ends(a, bsm.name)
        qb = QuantumChannel(f"qc_{b.name}_{bsm.name}", tl, 1e-5, 1e3)
        qb.set_ends(b, bsm.name)

    center.network_manager.routing_protocol.update_forwarding_rule("leaf1", "leaf1")
    center.network_manager.routing_protocol.update_forwarding_rule("leaf2", "leaf2")
    center.network_manager.routing_protocol.update_forwarding_rule("leaf3", "leaf3")
    leaf1.network_manager.routing_protocol.update_forwarding_rule("leaf2", "center")
    leaf1.network_manager.routing_protocol.update_forwarding_rule("leaf3", "center")
    leaf2.network_manager.routing_protocol.update_forwarding_rule("leaf1", "center")
    leaf3.network_manager.routing_protocol.update_forwarding_rule("leaf1", "center")

    apps = {node.name: RecordingRequestApp(node) for node in (leaf1, leaf2, leaf3)}

    tl.init()
    nodes_by_name = {node.name: node for node in nodes}
    return tl, nodes_by_name, apps


@pytest.mark.unit
def test_concurrent_reservations_succeed_when_repeater_capacity_suffices():
    # center needs 2 * PER_RESERVATION_SIZE per reservation -> 32 total; give it exactly enough headroom
    tl, nodes, apps = build_star_topology(center_memory_size=4 * PER_RESERVATION_SIZE)

    apps["leaf1"].start("leaf2", int(0.1e12), int(10e12), PER_RESERVATION_SIZE, 0.5)
    apps["leaf1"].start("leaf3", int(0.1e12), int(10e12), PER_RESERVATION_SIZE, 0.5)
    tl.run()

    assert [result for _, result in apps["leaf1"].results] == [True, True]
    assert len(nodes["center"].network_manager.protocol_stack[1].accepted_reservations) == 2

    # no cross-contamination: leaf2's delivered pairs must never claim to be
    # entangled with leaf3, and vice versa
    for info in nodes["leaf2"].resource_manager.memory_manager:
        if info.entangle_time > 0:
            assert info.remote_node == "leaf1"
    for info in nodes["leaf3"].resource_manager.memory_manager:
        if info.entangle_time > 0:
            assert info.remote_node == "leaf1"


@pytest.mark.unit
def test_concurrent_reservations_contend_for_shared_repeater_memory():
    # center capacity (2 * PER_RESERVATION_SIZE) is only enough for ONE of the
    # two reservations (each needs 2 * PER_RESERVATION_SIZE at the interior node)
    tl, nodes, apps = build_star_topology(center_memory_size=2 * PER_RESERVATION_SIZE)

    apps["leaf1"].start("leaf2", int(0.1e12), int(10e12), PER_RESERVATION_SIZE, 0.5)
    apps["leaf1"].start("leaf3", int(0.1e12), int(10e12), PER_RESERVATION_SIZE, 0.5)
    tl.run()

    results = [result for _, result in apps["leaf1"].results]
    assert len(results) == 2
    # exactly one of the two concurrent reservations must be admitted - which
    # one depends on message-arrival order at `center`, not on request order
    assert sum(results) == 1
    assert len(nodes["center"].network_manager.protocol_stack[1].accepted_reservations) == 1


@pytest.mark.unit
def test_two_reservations_between_same_pair_do_not_double_book_memory():
    """A single leaf1<->leaf2 pair issuing two overlapping reservations that
    jointly exceed leaf2's own memory pool must have the second rejected,
    even with a generously oversized repeater (isolating leaf2's own pool as
    the bottleneck, not `center`'s 2x interior-node rule)."""
    tl, nodes, apps = build_star_topology(center_memory_size=200)

    apps["leaf1"].start("leaf2", int(0.1e12), int(10e12), 15, 0.5)
    tl.run()
    assert apps["leaf1"].results[-1][1] is True

    # overlaps in time and would need 15 + 10 = 25 > 20 memories on leaf2
    apps["leaf1"].start("leaf2", int(1e12), int(9e12), 10, 0.5)
    tl.run()
    assert apps["leaf1"].results[-1][1] is False
