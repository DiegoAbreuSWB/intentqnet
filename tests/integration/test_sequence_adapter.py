"""Integration tests for `ibqn.network.sequence_adapter.SequenceAdapter`,
verifying it builds a real SeQUeNCe topology (via `RouterNetTopo`) from a
`NetworkTopologySpec` without the rest of `ibqn` ever touching SeQUeNCe
objects directly (see docs/architecture.md).
"""
import pytest
from pydantic import ValidationError
from sequence.topology.node import BSMNode, QuantumRouter

from ibqn.network.sequence_adapter import SequenceAdapter
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec

LINEAR_THREE_NODE_SPEC = NetworkTopologySpec(
    nodes=[
        NodeSpec(id="r1", memories=10),
        NodeSpec(id="r2", memories=20),
        NodeSpec(id="r3", memories=10),
    ],
    quantum_links=[
        QuantumLinkSpec(source="r1", destination="r2", distance_m=1000, attenuation_db_per_m=1e-5),
        QuantumLinkSpec(source="r2", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5),
    ],
    classical_delay_s=1e-4,
    stop_time_s=1.0,
)


@pytest.mark.unit
def test_adapter_builds_expected_routers_and_bsm_nodes():
    adapter = SequenceAdapter(LINEAR_THREE_NODE_SPEC, seed=0)

    assert adapter.router_ids() == ["r1", "r2", "r3"]
    for node_id in ("r1", "r2", "r3"):
        router = adapter.get_router(node_id)
        assert isinstance(router, QuantumRouter)
        assert router.name == node_id

    # RouterNetTopo auto-generates one BSM node per meet_in_the_middle link
    bsm_node = adapter.get_timeline().get_entity_by_name("BSM.r1.r2")
    assert isinstance(bsm_node, BSMNode)


@pytest.mark.unit
def test_adapter_applies_correct_memory_array_sizes():
    adapter = SequenceAdapter(LINEAR_THREE_NODE_SPEC, seed=0)

    r1 = adapter.get_router("r1")
    r2 = adapter.get_router("r2")
    memory_array_r1 = r1.get_components_by_type("MemoryArray")[0]
    memory_array_r2 = r2.get_components_by_type("MemoryArray")[0]

    assert len(memory_array_r1.memories) == 10
    assert len(memory_array_r2.memories) == 20


@pytest.mark.unit
def test_adapter_get_router_raises_for_unknown_node():
    adapter = SequenceAdapter(LINEAR_THREE_NODE_SPEC, seed=0)
    with pytest.raises(KeyError, match="no node named"):
        adapter.get_router("does-not-exist")


@pytest.mark.unit
def test_adapter_get_router_raises_for_non_router_node():
    adapter = SequenceAdapter(LINEAR_THREE_NODE_SPEC, seed=0)
    with pytest.raises(TypeError, match="not a QuantumRouter"):
        adapter.get_router("BSM.r1.r2")


@pytest.mark.unit
def test_static_routing_table_is_auto_populated_by_dijkstra():
    """RouterNetTopo._generate_forwarding_table computes the static routing
    table automatically (see docs/sequence_code_analysis.md, section 4.6) -
    the adapter must not need to call `update_forwarding_rule` itself."""
    adapter = SequenceAdapter(LINEAR_THREE_NODE_SPEC, seed=0)
    r1 = adapter.get_router("r1")
    forwarding_table = r1.network_manager.get_forwarding_table()

    assert forwarding_table["r2"] == "r2"
    assert forwarding_table["r3"] == "r2"  # r1 must reach r3 via r2


@pytest.mark.unit
def test_run_with_no_submitted_intents_is_a_harmless_noop():
    adapter = SequenceAdapter(LINEAR_THREE_NODE_SPEC, seed=0)
    adapter.run()  # should not raise
    assert adapter.get_timeline().run_counter >= 0


@pytest.mark.unit
def test_same_seed_produces_reproducible_topology_level_randomness():
    """Two adapters built from the same spec + seed must schedule the same
    sequence of entanglement-generation events (per-node PRNGs derive from
    `seed`, see `NetworkTopologySpec.to_router_net_topo_config`)."""
    from sequence.resource_management.rule_manager import Rule
    from sequence.entanglement_management.generation import EntanglementGenerationA

    def eg_condition(memory_info, manager, args):
        return [memory_info] if memory_info.state == "RAW" else []

    def eg_action_primary(memories_info, args):
        def req(protocols, args):
            for p in protocols:
                if isinstance(p, EntanglementGenerationA):
                    return p
        memory = memories_info[0].memory
        protocol = EntanglementGenerationA.create(None, "EGA." + memory.name, "BSM.r1.r2", "r2", memory)
        protocol.primary = True
        return [protocol, ["r2"], [req], [None]]

    def eg_action_secondary(memories_info, args):
        memory = memories_info[0].memory
        protocol = EntanglementGenerationA.create(None, "EGA." + memory.name, "BSM.r1.r2", "r1", memory)
        return [protocol, [None], [None], [None]]

    def entangle_times(seed):
        adapter = SequenceAdapter(LINEAR_THREE_NODE_SPEC, seed=seed)
        adapter.init()
        r1 = adapter.get_router("r1")
        r2 = adapter.get_router("r2")
        r1.resource_manager.load(Rule(10, eg_action_primary, eg_condition, None, None))
        r2.resource_manager.load(Rule(10, eg_action_secondary, eg_condition, None, None))
        adapter.run()
        return sorted(info.entangle_time for info in r1.resource_manager.memory_manager if info.entangle_time > 0)

    times_a = entangle_times(seed=7)
    times_b = entangle_times(seed=7)
    assert times_a == times_b
    assert len(times_a) > 0


@pytest.mark.unit
def test_topology_spec_rejects_link_to_undeclared_node():
    with pytest.raises(ValidationError, match="undeclared node"):
        NetworkTopologySpec(
            nodes=[NodeSpec(id="r1", memories=10), NodeSpec(id="r2", memories=10)],
            quantum_links=[
                QuantumLinkSpec(source="r1", destination="ghost", distance_m=1000, attenuation_db_per_m=1e-5)
            ],
            stop_time_s=1.0,
        )
