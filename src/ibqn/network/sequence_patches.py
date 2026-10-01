"""The ONE place IBQN alters SeQUeNCe's own behavior at runtime, so every
deviation from stock `sequence` is explicit, documented, tested and
reversible (see docs/physical_model.md, "Deviations from stock SeQUeNCe").

Only one patch exists: `ibqn_ep_rule_condition_request`, a replacement for
`sequence.resource_management.action_condition_set.ep_rule_condition_request`
(the condition deciding WHICH two memories a BBPSSW purification round
consumes on the requesting side of a link). It is active ONLY while the
Bell-diagonal formalism is active - under `ket_vector` it delegates to the
stock function unchanged, so legacy runs are byte-identical.

Why it is needed. Stock SeQUeNCe pairs a kept memory only with a measured
memory whose recorded fidelity is EXACTLY equal
(`measured_memory.fidelity == kept_memory.fidelity`,
`action_condition_set.py`, `ep_rule_condition_request`). That equality is a
proxy for "two pairs of the same generation" and holds trivially under the
scalar `ket_vector` bookkeeping, where every fresh pair has fidelity
`raw_fidelity` and every swap/purification output is a deterministic
function of its inputs. Under `bell_diagonal` with finite coherence time,
each pair's fidelity is read from its decohered quantum state
(`Memory.get_bds_fidelity`), so two pairs almost never share a fidelity
bit-for-bit after any swap or purification round - exact-equality pairing
then silently disables (a) every purification round after the first on a
link, and (b) all end-to-end purification. `BBPSSW_BDS.purification_res`
itself handles unequal inputs exactly (it reads both states separately),
so the equality was never a physical requirement.

What the replacement does differently:
1. pairs the kept memory with the eligible memory whose fidelity is
   CLOSEST (equal fidelities are still preferred, so the stock choice is
   reproduced whenever it exists);
2. requires BOTH memories to be below the reservation's target (stock only
   checks the kept one, the measured one being implied by equality) - a
   pair that already meets the target is never sacrificed;
3. requires both pairs' CURRENT state fidelity - the Bell-diagonal state
   with each memory's idle decoherence applied up to now, the same
   `Memory.bds_decohere()` the protocol itself applies first thing in
   `BBPSSW_BDS.start` - to be strictly above 1/2, the threshold below
   which BBPSSW cannot improve a pair and `BBPSSWProtocol.start` aborts the
   whole simulation with an `AssertionError` (the `SIMULATION_ERROR`
   harness outcome documented in
   docs/paper_ibqn_validation/simulation_error_trace.md). The recorded
   `MemoryInfo.fidelity` is a snapshot taken when the pair was last
   updated, and the two endpoints snapshot at different moments; with
   strong decoherence the remote endpoint's snapshot can already be below
   1/2 while the local one is not (observed with T=10 ms), so only the
   live value is a safe guard. Applying the channel here is physically
   neutral: the Pauli channel is Markovian, so decohering "up to now" and
   then "from now on" composes to exactly the single channel SeQUeNCe would
   otherwise apply later. Pairs below the floor are simply left alone for
   the swap/delivery rules or the memory cutoff.

Everything else - `purification_mode` semantics (`'until_target'` may
re-purify `PURIFIED` pairs, `'once'` only `ENTANGLED` ones; any other value,
including IBQN's `'never'`, never purifies), the rule's memory scope, and
the requesting/awaiting split between the two link endpoints - is
preserved exactly.
"""
from __future__ import annotations

from sequence.constants import BELL_DIAGONAL_STATE_FORMALISM
from sequence.kernel.quantum_manager import QuantumManager
from sequence.resource_management import action_condition_set as _action_condition_set
from sequence.resource_management import resource_manager as _resource_manager

_STOCK_EP_RULE_CONDITION_REQUEST = _action_condition_set.ep_rule_condition_request

PURIFICATION_FIDELITY_FLOOR = 0.5
"""BBPSSW only improves pairs with fidelity > 1/2 (`BBPSSWProtocol.start`
asserts exactly this on both inputs)."""

_ALLOWED_STATES_BY_MODE: dict[str, frozenset[str]] = {
    "until_target": frozenset({"ENTANGLED", "PURIFIED"}),
    "once": frozenset({"ENTANGLED"}),
}


def live_pair_fidelity(memory_info) -> float | None:
    """The pair's Bell-diagonal state fidelity right now, with BOTH memories'
    idle decoherence applied (exactly what `BBPSSW_BDS.start` computes
    before deciding anything), or `None` if the pair has no state (e.g. it
    was just reset). Mutates only what SeQUeNCe's own next `bds_decohere`
    call would have mutated anyway - see the module docstring, point 3."""
    memory = memory_info.memory
    try:
        remote_memory = memory.timeline.get_entity_by_name(memory_info.remote_memo) if memory_info.remote_memo else None
        memory.bds_decohere()
        if remote_memory is not None:
            remote_memory.bds_decohere()
        return memory.get_bds_fidelity()
    except Exception:  # no Bell-diagonal state for this key (pair gone) - not a purification candidate
        return None


def ibqn_ep_rule_condition_request(kept_memory, memory_manager, args):
    """Drop-in replacement for `ep_rule_condition_request` - see the module
    docstring. Same signature/return contract: a `[kept, measured]` pair of
    `MemoryInfo` when purification should start, else `[]`.

    The `< target` tests deliberately use the recorded snapshot fidelity,
    like the stock condition and like the awaiting endpoint's
    `ep_rule_condition_await` (which must have created a waiting protocol
    for the same memories for the request to match); only the `> 1/2`
    floor uses the live state, for the reason given in the module
    docstring."""
    if QuantumManager.get_active_formalism() != BELL_DIAGONAL_STATE_FORMALISM:
        return _STOCK_EP_RULE_CONDITION_REQUEST(kept_memory, memory_manager, args)

    allowed_states = _ALLOWED_STATES_BY_MODE.get(args["purification_mode"])
    if allowed_states is None:  # 'never' (IBQN) or anything else SeQUeNCe doesn't know: no purification
        return []
    memory_indices = args["memory_indices"]
    target_fidelity = args["reservation"].fidelity

    def eligible(info) -> bool:
        if not (info.index in memory_indices and info.state in allowed_states and info.fidelity < target_fidelity):
            return False
        live = live_pair_fidelity(info)
        return live is not None and live > PURIFICATION_FIDELITY_FLOOR

    if not eligible(kept_memory):
        return []

    best_candidate = None
    best_distance = None
    for candidate in memory_manager:
        if (
            candidate is not kept_memory
            and candidate.remote_node == kept_memory.remote_node
            and candidate.remote_memo != kept_memory.remote_memo
            and eligible(candidate)
        ):
            distance = abs(candidate.fidelity - kept_memory.fidelity)
            if best_distance is None or distance < best_distance:
                best_candidate, best_distance = candidate, distance
                if distance == 0:
                    break
    if best_candidate is None:
        return []
    return [kept_memory, best_candidate]


def apply_sequence_patches() -> None:
    """Installs the patch (idempotent). `ResourceManager.generate_load_rules`
    binds the condition function through the name imported into
    `sequence.resource_management.resource_manager`, so that module's
    attribute is what has to change; the defining module is patched too so
    both names agree."""
    _resource_manager.ep_rule_condition_request = ibqn_ep_rule_condition_request
    _action_condition_set.ep_rule_condition_request = ibqn_ep_rule_condition_request


def remove_sequence_patches() -> None:
    """Restores stock SeQUeNCe behavior (used by tests that need to show the
    difference the patch makes)."""
    _resource_manager.ep_rule_condition_request = _STOCK_EP_RULE_CONDITION_REQUEST
    _action_condition_set.ep_rule_condition_request = _STOCK_EP_RULE_CONDITION_REQUEST


def sequence_patches_applied() -> bool:
    return _resource_manager.ep_rule_condition_request is ibqn_ep_rule_condition_request
