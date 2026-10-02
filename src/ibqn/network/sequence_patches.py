"""The ONE place IBQN alters SeQUeNCe's own behavior at runtime, so every
deviation from stock `sequence` is explicit, documented, tested and
reversible (see docs/physical_model.md, "Deviations from stock SeQUeNCe").

Two patches exist, both only reachable under the Bell-diagonal formalism
(legacy `ket_vector` runs are byte-identical to stock SeQUeNCe):

1. `ibqn_ep_rule_condition_request`, a replacement for
   `sequence.resource_management.action_condition_set.ep_rule_condition_request`
   (the condition deciding WHICH two memories a BBPSSW purification round
   consumes on the requesting side of a link) - described below.
2. `ibqn_bds_decohere`, a guard around `Memory.bds_decohere` - described at
   the end of this docstring.

--- Patch 1: purification pairing ------------------------------------------

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

--- Patch 2: decoherence when one half of a pair was already consumed -----

The two ends of a pair learn a protocol's outcome at different times (the
purification requester one classical delay before the awaiter; the two
ends of a swapped pair each after their own distance to the swapping
node). The end that learns first may consume its half - hand it to the
application, which resets the memory - while the other end still holds
its half and has not processed the outcome yet. SeQUeNCe's Bell-diagonal
protocols nevertheless update both memories of a pair from either end
(`self.memory.bds_decohere()` and `remote_memory.bds_decohere()` in
`BBPSSW_BDS.start`/`received_message`, `EntanglementSwappingA_BDS.start`,
`EntanglementSwappingB_BDS.received_message`), and `Memory.bds_decohere`
writes the decohered state back under BOTH keys of the pair. With one
half already consumed, stock SeQUeNCe then does one of two things:

(a) Crash. `Memory.reset` drops the consumed memory's state and
    `Memory.excite` stamps `last_update_time` for its next generation
    attempt before any new state exists; `bds_decohere` on that memory
    raises `KeyError` and aborts the whole simulation. Needs the consumed
    memory to be re-excited within the window between the two ends'
    updates, which uniform classical delays rule out (a new attempt takes
    at least two round trips) but fiber-following delays
    (`classical_delay_model='fiber'`, docs/parameter_calibration.md) do
    not: on the diamond's three-hop route the responder is 75 us of
    classical path from the initiator but 25 us from its neighbor, and
    re-excites 50 us after delivering.
(b) Write a stale state. Decohering the half that is still held writes
    the old pair's state back under the consumed memory's key too. Rarely
    harmful - that memory's next reset or next heralded pair replaces it -
    but it is a state the simulator should never hold, and if the consumed
    memory had already been re-entangled it would overwrite the new pair.

The integrity audit (`scripts/realistic/audit_state_integrity.py`, 39
reservations over chains, the diamond and the mesh, three purification
modes, 2 s down to 5 ms of coherence) counts both: of 34,906 decoherence
calls, 33 were case (a) and 551 case (b), none of them onto a re-entangled
memory; all 4,656 swap inputs and 3,704 purification inputs were pairs
both ends still held, and no run ended with a dangling state.

`ibqn_bds_decohere` keeps the stock channel and changes only its reach:
it does nothing for a memory without a state (nothing to decohere), and a
write-back never touches a partner key that no longer refers to the same
pair. Physically this is the correct accounting: a consumed half stopped
decohering when it was consumed, the half still held keeps decohering
until its own node consumes it, and that is the fidelity the holding node
records.
"""
from __future__ import annotations

from sequence.components.memory import Memory
from sequence.constants import BELL_DIAGONAL_STATE_FORMALISM
from sequence.kernel.quantum_manager import QuantumManager
from sequence.resource_management import action_condition_set as _action_condition_set
from sequence.resource_management import resource_manager as _resource_manager

_STOCK_EP_RULE_CONDITION_REQUEST = _action_condition_set.ep_rule_condition_request
_STOCK_BDS_DECOHERE = Memory.bds_decohere

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


def ibqn_bds_decohere(self) -> None:
    """`Memory.bds_decohere` confined to the pair this memory actually
    holds - see the module docstring, patch 2. The Pauli channel itself is
    the stock one."""
    if self.decoherence_errors is None:
        return _STOCK_BDS_DECOHERE(self)  # decoherence disabled: stock no-op
    states = self.timeline.quantum_manager.states
    state = states.get(self.qstate_key)
    if state is None:
        return  # pair already consumed and memory re-initialized: nothing to decohere
    partners = {key: states.get(key) for key in state.keys if key != self.qstate_key}
    _STOCK_BDS_DECOHERE(self)
    for key, previous in partners.items():
        if previous is not state:  # the partner moved on: undo the stock write-back under its key
            if previous is None:
                states.pop(key, None)
            else:
                states[key] = previous


def apply_sequence_patches() -> None:
    """Installs both patches (idempotent). `ResourceManager.generate_load_rules`
    binds the condition function through the name imported into
    `sequence.resource_management.resource_manager`, so that module's
    attribute is what has to change; the defining module is patched too so
    both names agree."""
    _resource_manager.ep_rule_condition_request = ibqn_ep_rule_condition_request
    _action_condition_set.ep_rule_condition_request = ibqn_ep_rule_condition_request
    Memory.bds_decohere = ibqn_bds_decohere


def remove_sequence_patches() -> None:
    """Restores stock SeQUeNCe behavior (used by tests that need to show the
    difference the patches make)."""
    _resource_manager.ep_rule_condition_request = _STOCK_EP_RULE_CONDITION_REQUEST
    _action_condition_set.ep_rule_condition_request = _STOCK_EP_RULE_CONDITION_REQUEST
    Memory.bds_decohere = _STOCK_BDS_DECOHERE


def sequence_patches_applied() -> bool:
    return (
        _resource_manager.ep_rule_condition_request is ibqn_ep_rule_condition_request
        and Memory.bds_decohere is ibqn_bds_decohere
    )
