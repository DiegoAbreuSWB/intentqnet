"""Pins every closed form in `ibqn.physics` to the SeQUeNCe protocol code it
ports, by evaluating the REAL protocol methods on real simulator objects
(Bell-diagonal states in a `QuantumManagerBellDiagonal`, `Memory`
instances, `QuantumRouter`s with gate/measurement fidelities) and comparing
number for number - never against a hand-derived expectation (see
docs/physical_model.md and docs/sequence_code_analysis.md, section 2).
"""
from __future__ import annotations

import math

import pytest
from sequence.components.memory import Memory
from sequence.constants import BELL_DIAGONAL_STATE_FORMALISM, KET_VECTOR_FORMALISM
from sequence.entanglement_management.purification.bbpssw_bds import BBPSSW_BDS
from sequence.entanglement_management.purification.bbpssw_circuit import BBPSSWCircuit
from sequence.entanglement_management.swapping.swapping_bds import EntanglementSwappingA_BDS
from sequence.kernel.timeline import Timeline
from sequence.topology.node import QuantumRouter

from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.sequence_adapter import configure_sequence_globals, reset_sequence_globals
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec
from ibqn.physics import (
    IDEAL_BBPSSW,
    PhysicsModel,
    bds_decohered_fidelity,
    bds_purification_step,
    bds_swap_fidelity,
    ket_purification_step,
    ket_swap_fidelity,
    werner_elements,
)


def _bds_timeline() -> Timeline:
    configure_sequence_globals(BELL_DIAGONAL_STATE_FORMALISM)
    return Timeline(stop_time=10 ** 12, formalism=BELL_DIAGONAL_STATE_FORMALISM)


def _router(name: str, tl: Timeline, *, gate_fid: float = 1.0, meas_fid: float = 1.0) -> QuantumRouter:
    router = QuantumRouter(name, tl, memo_size=4, gate_fid=gate_fid, meas_fid=meas_fid)
    router.set_seed(0)
    return router


def _memory(router: QuantumRouter, index: int) -> Memory:
    return router.get_components_by_type("MemoryArray")[0][index]


def _entangle(tl: Timeline, memory_a: Memory, node_a: str, memory_b: Memory, node_b: str, fidelity: float) -> None:
    """Writes one Werner pair into the two memories exactly as
    `SingleHeraldedA.update_memory` would (shared BDS state + the
    `entangled_memory` bookkeeping every protocol asserts on)."""
    tl.quantum_manager.set([memory_a.qstate_key, memory_b.qstate_key], list(werner_elements(fidelity)))
    memory_a.entangled_memory = {"node_id": node_b, "memo_id": memory_b.name}
    memory_b.entangled_memory = {"node_id": node_a, "memo_id": memory_a.name}
    memory_a.fidelity = memory_b.fidelity = fidelity


@pytest.mark.unit
@pytest.mark.parametrize("left,right,gate,meas", [
    (0.85, 0.85, 1.0, 1.0),
    (0.85, 0.70, 1.0, 1.0),
    (0.95, 0.80, 0.98, 0.97),
    (0.60, 0.99, 0.90, 1.0),
])
def test_bds_swap_fidelity_matches_sequence_swapping_res(left, right, gate, meas):
    tl = _bds_timeline()
    a, mid, b = _router("a", tl), _router("mid", tl, gate_fid=gate, meas_fid=meas), _router("b", tl)
    tl.init()
    _entangle(tl, _memory(a, 0), "a", _memory(mid, 0), "mid", left)
    _entangle(tl, _memory(mid, 1), "mid", _memory(b, 0), "b", right)

    protocol = EntanglementSwappingA_BDS(mid, "esa", _memory(mid, 0), _memory(mid, 1))
    real = protocol.swapping_res()

    assert bds_swap_fidelity(left, right, gate_fidelity=gate, measurement_fidelity=meas) == pytest.approx(real[0], abs=1e-12)
    # SeQUeNCe twirls its output back into Werner form - the single fidelity IS the whole state
    assert real[1:] == pytest.approx([(1 - real[0]) / 3] * 3)


@pytest.mark.unit
def test_bds_swap_with_ideal_gates_multiplies_werner_parameters():
    """Sanity check against the textbook result: for ideal gates the Werner
    parameter w = (4F-1)/3 multiplies under swapping."""
    f = bds_swap_fidelity(0.85, 0.85, gate_fidelity=1.0, measurement_fidelity=1.0)
    w = (4 * 0.85 - 1) / 3
    assert f == pytest.approx((1 + 3 * w * w) / 4)
    assert f == pytest.approx(0.73)


@pytest.mark.unit
@pytest.mark.parametrize("kept,meas,own,remote", [
    (0.73, 0.73, (1.0, 1.0), (1.0, 1.0)),
    (0.80, 0.65, (1.0, 1.0), (1.0, 1.0)),
    (0.90, 0.85, (0.98, 0.99), (0.97, 0.995)),
    (0.55, 0.95, (0.95, 0.95), (1.0, 0.9)),
])
def test_bds_purification_step_matches_sequence_purification_res(kept, meas, own, remote):
    tl = _bds_timeline()
    a = _router("a", tl, gate_fid=own[0], meas_fid=own[1])
    b = _router("b", tl, gate_fid=remote[0], meas_fid=remote[1])
    tl.init()
    _entangle(tl, _memory(a, 0), "a", _memory(b, 0), "b", kept)
    _entangle(tl, _memory(a, 1), "a", _memory(b, 1), "b", meas)

    protocol = BBPSSW_BDS(a, "ep", _memory(a, 0), _memory(a, 1))
    protocol.set_others("ep-remote", "b", [_memory(b, 0).name, _memory(b, 1).name])
    real_p, real_state = protocol.purification_res()

    p, f_new = bds_purification_step(
        kept, meas, own_gate_fidelity=own[0], own_measurement_fidelity=own[1],
        remote_gate_fidelity=remote[0], remote_measurement_fidelity=remote[1],
    )
    assert p == pytest.approx(real_p, abs=1e-12)
    assert f_new == pytest.approx(real_state[0], abs=1e-12)


@pytest.mark.unit
def test_bds_purification_with_ideal_gates_reduces_to_dur_briegel():
    """With ideal gates and equal inputs the Bell-diagonal formula IS
    `BBPSSWCircuit.improved_fidelity` (Dur-Briegel eq. 18) - which is why
    `IDEAL_BBPSSW` reproduces every pre-revision planner number exactly."""
    for f in (0.6, 0.73, 0.85, 0.95):
        p_bds, f_bds = bds_purification_step(
            f, f, own_gate_fidelity=1, own_measurement_fidelity=1, remote_gate_fidelity=1, remote_measurement_fidelity=1,
        )
        p_ket, f_ket = ket_purification_step(f)
        assert f_bds == pytest.approx(BBPSSWCircuit.improved_fidelity(f))
        assert f_bds == pytest.approx(f_ket)
        assert p_bds == pytest.approx(p_ket)
        assert IDEAL_BBPSSW.improve(f) == (p_ket, f_ket)


@pytest.mark.unit
@pytest.mark.parametrize("fidelity,idle_s,coherence_s,errors", [
    (0.85, 0.001, 1.0, (1 / 3, 1 / 3, 1 / 3)),
    (0.85, 0.05, 0.01, (1 / 3, 1 / 3, 1 / 3)),
    (0.73, 0.002, 0.005, (0.5, 0.25, 0.25)),
    (0.99, 0.5, 0.2, (0.1, 0.1, 0.8)),
])
def test_bds_decohered_fidelity_matches_memory_bds_decohere(fidelity, idle_s, coherence_s, errors):
    tl = _bds_timeline()
    memory_a = Memory("m0", tl, fidelity=0.85, frequency=0, efficiency=1, coherence_time=coherence_s, wavelength=500,
                      decoherence_errors=list(errors))
    memory_b = Memory("m1", tl, fidelity=0.85, frequency=0, efficiency=1, coherence_time=-1, wavelength=500)
    tl.init()
    tl.quantum_manager.set([memory_a.qstate_key, memory_b.qstate_key], list(werner_elements(fidelity)))
    memory_a.last_update_time = 1  # "generated" at t=1ps (bds_decohere skips memories never updated)
    tl.time = 1 + int(idle_s * 1e12)

    memory_a.bds_decohere()
    real = memory_a.get_bds_fidelity()

    assert bds_decohered_fidelity(fidelity, idle_s, coherence_time_s=coherence_s, decoherence_errors=errors) == pytest.approx(real, abs=1e-12)
    assert real < fidelity


@pytest.mark.unit
def test_bds_decoherence_is_markovian_so_applying_it_in_two_steps_is_exact():
    """Why `ibqn.network.sequence_patches.live_pair_fidelity` may apply the
    channel early without changing the physics."""
    once = bds_decohered_fidelity(0.85, 0.03, coherence_time_s=0.05)
    twice = bds_decohered_fidelity(bds_decohered_fidelity(0.85, 0.01, coherence_time_s=0.05), 0.02, coherence_time_s=0.05)
    assert once == pytest.approx(twice, abs=1e-12)


@pytest.mark.unit
def test_bds_decoherence_edge_cases():
    assert bds_decohered_fidelity(0.85, 0.0, coherence_time_s=0.01) == 0.85
    assert bds_decohered_fidelity(0.85, 5.0, coherence_time_s=-1) == 0.85
    # asymptote: fully depolarized
    assert bds_decohered_fidelity(0.85, 1000.0, coherence_time_s=0.01) == pytest.approx(0.25, abs=1e-9)


@pytest.mark.unit
def test_ket_swap_fidelity_matches_sequence_updated_fidelity():
    from sequence.entanglement_management.swapping.swapping_circuit import EntanglementSwappingA_Circuit

    reset_sequence_globals()  # ket_vector
    tl = Timeline(stop_time=10 ** 12, formalism=KET_VECTOR_FORMALISM)
    mid = _router("mid", tl)
    tl.init()
    left, right = _memory(mid, 0), _memory(mid, 1)
    left.entangled_memory = {"node_id": "a", "memo_id": "a.MemoryArray[0]"}
    right.entangled_memory = {"node_id": "b", "memo_id": "b.MemoryArray[0]"}
    protocol = EntanglementSwappingA_Circuit(mid, "esa", left, right, success_prob=1, degradation=0.95)

    for f1, f2 in ((0.85, 0.85), (0.9, 0.8), (0.6, 0.99)):
        assert ket_swap_fidelity(f1, f2, swapping_degradation=0.95) == pytest.approx(protocol.updated_fidelity(f1, f2))


def _chain_spec(formalism: str, **node_kwargs) -> NetworkTopologySpec:
    nodes = [NodeSpec(id=n, memories=10, **node_kwargs) for n in ("a", "r1", "b")]
    links = [
        QuantumLinkSpec(source="a", destination="r1", distance_m=1000, attenuation_db_per_m=1e-5),
        QuantumLinkSpec(source="r1", destination="b", distance_m=1000, attenuation_db_per_m=1e-5),
    ]
    return NetworkTopologySpec(nodes=nodes, quantum_links=links, stop_time_s=1.0, formalism=formalism)


@pytest.mark.unit
def test_physics_model_dispatches_on_formalism():
    ket = NetworkCapabilities(_chain_spec(KET_VECTOR_FORMALISM, raw_fidelity=0.85, swapping_degradation=0.95)).physics
    bds = NetworkCapabilities(_chain_spec(BELL_DIAGONAL_STATE_FORMALISM, raw_fidelity=0.85, gate_fidelity=0.98)).physics

    assert ket.formalism == KET_VECTOR_FORMALISM and not ket.is_bell_diagonal
    assert bds.formalism == BELL_DIAGONAL_STATE_FORMALISM and bds.is_bell_diagonal
    assert ket.swap_fidelity(0.85, 0.85, "r1") == pytest.approx(0.85 * 0.85 * 0.95)
    assert bds.swap_fidelity(0.85, 0.85, "r1") == pytest.approx(
        bds_swap_fidelity(0.85, 0.85, gate_fidelity=0.98, measurement_fidelity=1.0)
    )
    assert ket.purification_between("a", "b") is IDEAL_BBPSSW
    assert bds.purification_between("a", "b").improve(0.73) == pytest.approx(
        bds_purification_step(0.73, 0.73, own_gate_fidelity=0.98, own_measurement_fidelity=1,
                              remote_gate_fidelity=0.98, remote_measurement_fidelity=1)
    )
    # decoherence is a bell_diagonal-only effect
    assert ket.decohered_fidelity(0.85, 0.5, "a") == 0.85
    assert bds.decohered_fidelity(0.85, 0.5, "a") < 0.85


@pytest.mark.unit
def test_physics_model_rejects_unknown_formalism_and_node():
    with pytest.raises(ValueError, match="unsupported formalism"):
        PhysicsModel("density_matrix", {})
    with pytest.raises(KeyError, match="no node named"):
        NetworkCapabilities(_chain_spec(BELL_DIAGONAL_STATE_FORMALISM)).physics.node("ghost")


@pytest.mark.unit
def test_link_fidelity_is_conservative_minimum():
    spec = NetworkTopologySpec(
        nodes=[NodeSpec(id="a", memories=2, raw_fidelity=0.9), NodeSpec(id="b", memories=2, raw_fidelity=0.8)],
        quantum_links=[QuantumLinkSpec(source="a", destination="b", distance_m=1000, attenuation_db_per_m=1e-5)],
        stop_time_s=1.0,
    )
    assert NetworkCapabilities(spec).physics.link_fidelity("a", "b") == 0.8
    assert math.isclose(NetworkCapabilities(spec).hop_fidelity("b", "a"), 0.8)
