"""Tests for `ibqn.network.sequence_patches` - the single, documented
deviation from stock SeQUeNCe (see docs/physical_model.md).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sequence.constants import BELL_DIAGONAL_STATE_FORMALISM
from sequence.kernel.timeline import Timeline
from sequence.resource_management import action_condition_set, resource_manager
from sequence.topology.node import QuantumRouter

from ibqn.network.sequence_adapter import configure_sequence_globals, reset_sequence_globals
from ibqn.network.sequence_patches import (
    _STOCK_EP_RULE_CONDITION_REQUEST,
    apply_sequence_patches,
    ibqn_ep_rule_condition_request,
    live_pair_fidelity,
    remove_sequence_patches,
    sequence_patches_applied,
)
from ibqn.physics import werner_elements


@pytest.fixture(autouse=True)
def _restore_patch_state():
    """Every other module assumes the patch is installed (the adapter
    installs it); tests here toggle it, so put it back afterwards."""
    yield
    apply_sequence_patches()


class _FakeInfo(SimpleNamespace):
    """A `MemoryInfo` stand-in with just the fields the condition reads."""


def _info(index, state, fidelity, remote_node="b", remote_memo=None, memory=None):
    return _FakeInfo(index=index, state=state, fidelity=fidelity, remote_node=remote_node,
                     remote_memo=remote_memo or f"b.MemoryArray[{index}]", memory=memory)


def _args(mode="until_target", target=0.8, indices=range(10)):
    return {"memory_indices": list(indices), "reservation": SimpleNamespace(fidelity=target), "purification_mode": mode}


@pytest.mark.unit
def test_patch_is_installed_in_both_namespaces_and_reversible():
    apply_sequence_patches()
    assert sequence_patches_applied()
    assert resource_manager.ep_rule_condition_request is ibqn_ep_rule_condition_request
    assert action_condition_set.ep_rule_condition_request is ibqn_ep_rule_condition_request
    remove_sequence_patches()
    assert not sequence_patches_applied()
    assert resource_manager.ep_rule_condition_request is _STOCK_EP_RULE_CONDITION_REQUEST


@pytest.mark.unit
def test_under_ket_vector_the_patch_delegates_to_stock_sequence():
    reset_sequence_globals()  # ket_vector active
    kept = _info(0, "ENTANGLED", 0.7)
    equal = _info(1, "ENTANGLED", 0.7)
    close = _info(2, "ENTANGLED", 0.71)
    # stock: exact equality required
    assert ibqn_ep_rule_condition_request(kept, [kept, close], _args()) == []
    assert ibqn_ep_rule_condition_request(kept, [kept, equal], _args()) == [kept, equal]
    assert _STOCK_EP_RULE_CONDITION_REQUEST(kept, [kept, close], _args()) == []


def _bds_pair(tl, router_a, router_b, index, fidelity, *, last_update_ps=1):
    memory_a = router_a.get_components_by_type("MemoryArray")[0][index]
    memory_b = router_b.get_components_by_type("MemoryArray")[0][index]
    tl.quantum_manager.set([memory_a.qstate_key, memory_b.qstate_key], list(werner_elements(fidelity)))
    memory_a.last_update_time = memory_b.last_update_time = last_update_ps
    memory_a.entangled_memory = {"node_id": router_b.name, "memo_id": memory_b.name}
    memory_b.entangled_memory = {"node_id": router_a.name, "memo_id": memory_a.name}
    return _info(index, "ENTANGLED", fidelity, remote_node=router_b.name, remote_memo=memory_b.name, memory=memory_a)


def _bds_routers(coherence_time=-1):
    configure_sequence_globals(BELL_DIAGONAL_STATE_FORMALISM)
    tl = Timeline(stop_time=10 ** 12, formalism=BELL_DIAGONAL_STATE_FORMALISM)
    template = {"MemoryArray": {"coherence_time": coherence_time}}
    a = QuantumRouter("a", tl, memo_size=6, component_templates=template)
    b = QuantumRouter("b", tl, memo_size=6, component_templates=template)
    tl.init()
    return tl, a, b


@pytest.mark.unit
def test_under_bell_diagonal_unequal_fidelities_pair_with_the_closest_candidate():
    tl, a, b = _bds_routers()
    kept = _bds_pair(tl, a, b, 0, 0.70)
    far = _bds_pair(tl, a, b, 1, 0.60)
    close = _bds_pair(tl, a, b, 2, 0.72)
    above_target = _bds_pair(tl, a, b, 3, 0.85)

    result = ibqn_ep_rule_condition_request(kept, [kept, far, close, above_target], _args(target=0.8))

    assert result == [kept, close]  # never the pair that already meets the target, never the farther one


@pytest.mark.unit
def test_under_bell_diagonal_equal_fidelities_still_reproduce_the_stock_choice():
    tl, a, b = _bds_routers()
    kept = _bds_pair(tl, a, b, 0, 0.70)
    close = _bds_pair(tl, a, b, 1, 0.71)
    equal = _bds_pair(tl, a, b, 2, 0.70)
    assert ibqn_ep_rule_condition_request(kept, [kept, close, equal], _args()) == [kept, equal]


@pytest.mark.unit
def test_purification_modes_are_honored():
    tl, a, b = _bds_routers()
    entangled = _bds_pair(tl, a, b, 0, 0.70)
    purified = _bds_pair(tl, a, b, 1, 0.72)
    purified.state = "PURIFIED"

    assert ibqn_ep_rule_condition_request(entangled, [entangled, purified], _args("until_target")) == [entangled, purified]
    assert ibqn_ep_rule_condition_request(entangled, [entangled, purified], _args("once")) == []
    assert ibqn_ep_rule_condition_request(purified, [entangled, purified], _args("once")) == []
    assert ibqn_ep_rule_condition_request(entangled, [entangled, purified], _args("never")) == []


@pytest.mark.unit
def test_pairs_whose_live_state_fidelity_fell_below_one_half_are_never_purified():
    """The recorded snapshot says 0.7 for both, but one pair has been idling
    in a 5 ms-coherence memory for 20 ms: its live fidelity is below 1/2
    and `BBPSSWProtocol.start` would abort the simulation on it."""
    tl, a, b = _bds_routers(coherence_time=0.005)
    kept = _bds_pair(tl, a, b, 0, 0.70, last_update_ps=1)
    decayed = _bds_pair(tl, a, b, 1, 0.70, last_update_ps=1)
    fresh = _bds_pair(tl, a, b, 2, 0.70, last_update_ps=int(20e9) - 1000)
    tl.time = int(20e9)  # 20 ms later

    assert live_pair_fidelity(decayed) < 0.5
    assert live_pair_fidelity(fresh) > 0.5
    # kept itself has decayed too -> nothing is purified at all
    assert ibqn_ep_rule_condition_request(kept, [kept, decayed, fresh], _args()) == []
    # a fresh kept pair only pairs with the other fresh one
    fresh2 = _bds_pair(tl, a, b, 3, 0.70, last_update_ps=int(20e9) - 1000)
    assert ibqn_ep_rule_condition_request(fresh, [kept, decayed, fresh, fresh2], _args()) == [fresh, fresh2]


@pytest.mark.unit
def test_live_pair_fidelity_is_none_for_a_pair_without_state():
    tl, a, b = _bds_routers()
    raw = _info(0, "RAW", 0.0, memory=a.get_components_by_type("MemoryArray")[0][0], remote_memo=None)
    assert live_pair_fidelity(raw) is None
