"""Tests for elementary entanglement generation (Barrett-Kok) between two adjacent
quantum routers connected through a BSM node.

Mirrors the official example `example/demo_for_beginners/two_node_eg.ipynb`
(manual `Rule` installation, no reservation/network-management layer involved),
which is the lowest-level, most controlled way to exercise
`EntanglementGenerationA`/`EntanglementGenerationB` (see
`docs/sequence_code_analysis.md`, section 4.2).
"""
import pytest

from sequence.kernel.timeline import Timeline
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from sequence.resource_management.rule_manager import Rule
from sequence.entanglement_management.generation import EntanglementGenerationA

DEFAULT_RAW_FIDELITY = 0.85  # sequence/components/memory.py MemoryArray default


def eg_rule_condition(memory_info, manager, args):
    return [memory_info] if memory_info.state == "RAW" else []


def eg_rule_action_primary(memories_info, args):
    def eg_req_func(protocols, args):
        for protocol in protocols:
            if isinstance(protocol, EntanglementGenerationA):
                return protocol

    memory = memories_info[0].memory
    protocol = EntanglementGenerationA.create(None, "EGA." + memory.name, "m1", "r2", memory)
    protocol.primary = True
    return [protocol, ["r2"], [eg_req_func], [None]]


def eg_rule_action_secondary(memories_info, args):
    memory = memories_info[0].memory
    protocol = EntanglementGenerationA.create(None, "EGA." + memory.name, "m1", "r1", memory)
    return [protocol, [None], [None], [None]]


def build_two_node_topology(num_memories=10, sim_time_ms=100, qc_atten=1e-4, qc_dist=1e3):
    """Builds the 2-router + 1-BSM-node topology, with manually installed
    entanglement-generation rules (no NetworkManager/reservation involved)."""
    tl = Timeline(sim_time_ms * 1e9)

    r1 = QuantumRouter("r1", tl, num_memories)
    r2 = QuantumRouter("r2", tl, num_memories)
    m1 = BSMNode("m1", tl, ["r1", "r2"])
    r1.set_seed(0)
    r2.set_seed(1)
    m1.set_seed(2)

    for node1 in (r1, r2, m1):
        for node2 in (r1, r2, m1):
            if node1 is node2:
                continue
            cc = ClassicalChannel(f"cc_{node1.name}_{node2.name}", tl, 1e3, delay=1e9)
            cc.set_ends(node1, node2.name)

    qc1 = QuantumChannel("qc_r1_m1", tl, qc_atten, qc_dist)
    qc1.set_ends(r1, m1.name)
    qc2 = QuantumChannel("qc_r2_m1", tl, qc_atten, qc_dist)
    qc2.set_ends(r2, m1.name)

    tl.init()
    r1.resource_manager.load(Rule(10, eg_rule_action_primary, eg_rule_condition, None, None))
    r2.resource_manager.load(Rule(10, eg_rule_action_secondary, eg_rule_condition, None, None))

    return tl, r1, r2, m1


@pytest.mark.unit
def test_all_memories_become_entangled_with_raw_fidelity():
    tl, r1, r2, m1 = build_two_node_topology(num_memories=10, sim_time_ms=100)

    tl.run()

    r1_infos = list(r1.resource_manager.memory_manager)
    assert len(r1_infos) == 10
    assert all(info.state == "ENTANGLED" for info in r1_infos)
    assert all(info.fidelity == pytest.approx(DEFAULT_RAW_FIDELITY) for info in r1_infos)
    assert tl.run_counter > 0


@pytest.mark.unit
def test_entanglement_pairing_is_mutually_consistent():
    """Every entangled memory on r1 must point to a memory on r2 that, in turn,
    points back to it - i.e. the handshake result is a true bijection, not just
    a one-sided bookkeeping update."""
    tl, r1, r2, m1 = build_two_node_topology(num_memories=10, sim_time_ms=100)
    tl.run()

    r2_memory_manager = r2.resource_manager.memory_manager

    for info in r1.resource_manager.memory_manager:
        assert info.remote_node == "r2"
        remote_info = next(i for i in r2_memory_manager if i.memory.name == info.remote_memo)
        assert remote_info.state == "ENTANGLED"
        assert remote_info.remote_node == "r1"
        assert remote_info.remote_memo == info.memory.name


@pytest.mark.probabilistic
def test_same_seed_reproduces_identical_entangle_times():
    """Reproducibility contract: two runs built from scratch with the same
    per-node seeds must produce bit-identical entangle_time sequences."""
    tl_a, r1_a, *_ = build_two_node_topology(num_memories=10, sim_time_ms=100)
    tl_a.run()
    times_a = sorted(info.entangle_time for info in r1_a.resource_manager.memory_manager)

    tl_b, r1_b, *_ = build_two_node_topology(num_memories=10, sim_time_ms=100)
    tl_b.run()
    times_b = sorted(info.entangle_time for info in r1_b.resource_manager.memory_manager)

    assert times_a == times_b


@pytest.mark.probabilistic
def test_final_entangled_count_is_seed_independent_given_enough_time():
    """Barrett-Kok retries on failure as long as the memory stays RAW and the
    rule remains installed: given a generous time budget, the final count of
    entangled memories should not depend on which per-node seeds were used,
    even though the exact timing of each success does."""
    counts = []
    for base_seed in range(5):
        tl = Timeline(150 * 1e9)
        r1 = QuantumRouter("r1", tl, 10)
        r2 = QuantumRouter("r2", tl, 10)
        m1 = BSMNode("m1", tl, ["r1", "r2"])
        r1.set_seed(base_seed)
        r2.set_seed(base_seed + 1)
        m1.set_seed(base_seed + 2)

        for node1 in (r1, r2, m1):
            for node2 in (r1, r2, m1):
                if node1 is node2:
                    continue
                cc = ClassicalChannel(f"cc_{node1.name}_{node2.name}", tl, 1e3, delay=1e9)
                cc.set_ends(node1, node2.name)
        qc1 = QuantumChannel("qc_r1_m1", tl, 1e-4, 1e3)
        qc1.set_ends(r1, m1.name)
        qc2 = QuantumChannel("qc_r2_m1", tl, 1e-4, 1e3)
        qc2.set_ends(r2, m1.name)

        tl.init()
        r1.resource_manager.load(Rule(10, eg_rule_action_primary, eg_rule_condition, None, None))
        r2.resource_manager.load(Rule(10, eg_rule_action_secondary, eg_rule_condition, None, None))
        tl.run()

        counts.append(sum(1 for info in r1.resource_manager.memory_manager if info.state == "ENTANGLED"))

    assert counts == [10, 10, 10, 10, 10]
