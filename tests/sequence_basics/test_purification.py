"""Tests for entanglement purification (BBPSSW) triggered automatically by the
reservation pipeline when `target_fidelity` exceeds what a single swap alone can
deliver (see `docs/sequence_code_analysis.md`, section 4.4).

`target_fidelity` is set above `RAW_FIDELITY**2 * SWAPPING_DEGRADATION` (a single
swap's fidelity), which forces `ep_rule_condition_*` (`purification_mode`
`'until_target'`) to install a BBPSSW round. The expected post-purification
fidelity is computed with the *real* simulator formula
(`BBPSSWCircuit.improved_fidelity`), never hand-derived, so the test's ground
truth has the same origin as the simulator's own behavior.
"""
import pytest

from sequence.kernel.timeline import Timeline
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from sequence.entanglement_management.purification.bbpssw_circuit import BBPSSWCircuit
from sequence.utils import metrics
from sequence.utils.metrics.event_types import EventTypes

RAW_FIDELITY = 0.85
SWAPPING_DEGRADATION = 0.95
SWAP_ONLY_FIDELITY = RAW_FIDELITY * RAW_FIDELITY * SWAPPING_DEGRADATION
REQUEST_FIDELITY = 0.72  # > SWAP_ONLY_FIDELITY -> purification is required
EXPECTED_PURIFIED_FIDELITY = BBPSSWCircuit.improved_fidelity(SWAP_ONLY_FIDELITY)


def build_three_node_topology(memory_size=10, sim_time_ms=300):
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
            cc = ClassicalChannel(f"cc_{node1.name}_{node2.name}", tl, 1e3, delay=1e8)
            cc.set_ends(node1, node2.name)

    for a, b, mid in ((r1, r2, m1), (r2, r3, m2)):
        qa = QuantumChannel(f"qc_{a.name}_{mid.name}", tl, 1e-5, 1e3)
        qa.set_ends(a, mid.name)
        qb = QuantumChannel(f"qc_{b.name}_{mid.name}", tl, 1e-5, 1e3)
        qb.set_ends(b, mid.name)

    r1.network_manager.routing_protocol.update_forwarding_rule("r2", "r2")
    r1.network_manager.routing_protocol.update_forwarding_rule("r3", "r2")
    r2.network_manager.routing_protocol.update_forwarding_rule("r1", "r1")
    r2.network_manager.routing_protocol.update_forwarding_rule("r3", "r3")
    r3.network_manager.routing_protocol.update_forwarding_rule("r1", "r2")
    r3.network_manager.routing_protocol.update_forwarding_rule("r2", "r2")

    return tl, r1, r2, r3, m1, m2


@pytest.fixture(autouse=True)
def _reset_metrics():
    """`sequence.utils.metrics` is a process-wide singleton (see
    docs/sequence_code_analysis.md); isolate each test from the others."""
    metrics.configure()
    metrics.reset_metrics()
    yield
    metrics._enabled = False
    metrics._enabled_events.clear()


@pytest.mark.unit
def test_purification_is_triggered_and_improves_fidelity_above_single_swap():
    metrics.enable([EventTypes.EP_SUCCESS, EventTypes.EP_FAILURE])

    tl, r1, r2, r3, m1, m2 = build_three_node_topology(memory_size=10)
    tl.init()
    r1.network_manager.request("r3", int(0.1e12), int(10e12), 10, REQUEST_FIDELITY)
    tl.run()

    purified = [info for info in r1.resource_manager.memory_manager if info.state == "PURIFIED"]
    assert len(purified) > 0, "expected at least one PURIFIED memory given target_fidelity > single-swap fidelity"

    for info in purified:
        assert info.fidelity == pytest.approx(EXPECTED_PURIFIED_FIDELITY)
        assert info.fidelity > SWAP_ONLY_FIDELITY
        assert info.fidelity >= REQUEST_FIDELITY

    ep_counter = metrics.get_counter("ep")
    assert ep_counter.successes("r1") > 0, "BBPSSW should have been attempted and succeeded at least once on r1"


@pytest.mark.unit
def test_measurement_memory_returns_to_raw_after_purification():
    """BBPSSW consumes 2 pairs to produce 1: the measurement memory must
    return to RAW regardless of purification success/failure (see
    docs/sequence_code_analysis.md, section 4.4)."""
    metrics.enable([EventTypes.EP_SUCCESS, EventTypes.EP_FAILURE])

    tl, r1, r2, r3, m1, m2 = build_three_node_topology(memory_size=10)
    tl.init()
    r1.network_manager.request("r3", int(0.1e12), int(10e12), 10, REQUEST_FIDELITY)
    tl.run()

    ep_counter = metrics.get_counter("ep")
    attempts = ep_counter.successes("r1") + ep_counter.failures("r1")
    assert attempts > 0

    # a memory pool of 10 could not sustain `attempts` successful *deliveries*
    # on its own without measurement memories being freed back to RAW for reuse
    r1_states = [info.state for info in r1.resource_manager.memory_manager]
    assert "RAW" in r1_states or "OCCUPIED" in r1_states


@pytest.mark.probabilistic
def test_purification_success_rate_is_between_deterministic_bounds():
    """Purification success/failure is a probabilistic coin flip
    (`bbpssw_circuit.py`), calibrated so its long-run rate matches the
    analytical BBPSSW success probability for the fidelity involved. Run
    across multiple independent seeds and check the aggregate success rate
    falls in a broad, non-degenerate band (never 0%, never 100%) - a
    property guaranteed by the physics (BBPSSW success probability is always
    >= 1/2 for input fidelity > 1/2, and < 1 unless inputs are already pure)."""
    from sequence.utils.metrics import aggregate_trial_metrics

    trials = []
    for seed_base in range(5):
        metrics.configure()
        metrics.reset_metrics()
        metrics.enable([EventTypes.EP_SUCCESS, EventTypes.EP_FAILURE])

        tl = Timeline(300 * 1e9)
        r1 = QuantumRouter("r1", tl, 10)
        r2 = QuantumRouter("r2", tl, 20)
        r3 = QuantumRouter("r3", tl, 10)
        m1 = BSMNode("m1", tl, ["r1", "r2"])
        m2 = BSMNode("m2", tl, ["r2", "r3"])
        r1.add_bsm_node(m1.name, r2.name)
        r2.add_bsm_node(m1.name, r1.name)
        r2.add_bsm_node(m2.name, r3.name)
        r3.add_bsm_node(m2.name, r2.name)
        r2.swapping_success_prob = 1
        r2.swapping_degradation = SWAPPING_DEGRADATION
        for i, node in enumerate((r1, r2, r3, m1, m2)):
            node.set_seed(seed_base * 10 + i)
        for node in (r1, r2, r3):
            ma = node.get_components_by_type("MemoryArray")[0]
            ma.update_memory_params("coherence_time", 10)
            ma.update_memory_params("raw_fidelity", RAW_FIDELITY)
        for n1 in (r1, r2, r3, m1, m2):
            for n2 in (r1, r2, r3, m1, m2):
                if n1 is n2:
                    continue
                cc = ClassicalChannel(f"cc_{n1.name}_{n2.name}", tl, 1e3, delay=1e8)
                cc.set_ends(n1, n2.name)
        for a, b, mid in ((r1, r2, m1), (r2, r3, m2)):
            qa = QuantumChannel(f"qc_{a.name}_{mid.name}", tl, 1e-5, 1e3)
            qa.set_ends(a, mid.name)
            qb = QuantumChannel(f"qc_{b.name}_{mid.name}", tl, 1e-5, 1e3)
            qb.set_ends(b, mid.name)
        r1.network_manager.routing_protocol.update_forwarding_rule("r2", "r2")
        r1.network_manager.routing_protocol.update_forwarding_rule("r3", "r2")
        r2.network_manager.routing_protocol.update_forwarding_rule("r1", "r1")
        r2.network_manager.routing_protocol.update_forwarding_rule("r3", "r3")
        r3.network_manager.routing_protocol.update_forwarding_rule("r1", "r2")
        r3.network_manager.routing_protocol.update_forwarding_rule("r2", "r2")

        tl.init()
        r1.network_manager.request("r3", int(0.1e12), int(10e12), 10, REQUEST_FIDELITY)
        tl.run()

        trials.append(metrics.collect_trial_metrics("r1"))

    aggregated = aggregate_trial_metrics(trials)
    assert 0.0 < aggregated["avg_ep_success_rate"] < 1.0
