"""Closed-form physics the planner uses to *estimate* what SeQUeNCe will do,
selected by the topology's quantum-state formalism (see
docs/physical_model.md).

Every formula here is a direct port of the corresponding SeQUeNCe protocol
code - never an independently invented model - and is pinned to that code
by `tests/unit/test_physics.py`, which evaluates the real protocol methods
(`EntanglementSwappingA_BDS.swapping_res`, `BBPSSW_BDS.purification_res`,
`Memory.bds_decohere`, `EntanglementSwappingA_Circuit.updated_fidelity`,
`BBPSSWCircuit.improved_fidelity`) on real simulator objects and compares:

- `bell_diagonal` (this project's default since the physical-realism
  revision): entangled pairs are Bell-diagonal states, the memory fidelity
  is *derived from the state* (`Memory.get_bds_fidelity`), swapping and
  BBPSSW purification are analytical compositions of Pauli channels that
  depend on each node's gate/measurement fidelity
  (`sequence/entanglement_management/swapping/swapping_bds.py`,
  `.../purification/bbpssw_bds.py`), and memories decohere continuously
  while idle (`sequence/components/memory.py`, `Memory.bds_decohere`).
  SeQUeNCe's `is_twirled=True` default means every input is twirled into
  Werner form before each operation, so tracking a single fidelity per pair
  is exact, not an approximation.
- `ket_vector` (legacy): the pre-revision scalar bookkeeping model -
  fidelity multiplies by a fixed `swapping_degradation` per swap and
  BBPSSW follows Dur-Briegel's ideal-gate formula, independent of the
  quantum state SeQUeNCe actually stores (always a perfect Bell pair).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

KET_VECTOR_FORMALISM = "ket_vector"
BELL_DIAGONAL_FORMALISM = "bell_diagonal"
SUPPORTED_FORMALISMS: tuple[str, ...] = (KET_VECTOR_FORMALISM, BELL_DIAGONAL_FORMALISM)

DEPOLARIZING_ERRORS: tuple[float, float, float] = (1 / 3, 1 / 3, 1 / 3)
"""SeQUeNCe's default `decoherence_errors` under the Bell-diagonal
formalism (`MemoryArray.__init__`, `sequence/components/memory.py`):
X/Y/Z Pauli errors equally likely."""

MAXIMALLY_MIXED_FIDELITY = 0.25
"""Fidelity of the fully depolarized two-qubit state - the asymptote of
`bds_decohere` for any input."""


# --------------------------------------------------------------------------
# Bell-diagonal (Werner) formulas - ports of swapping_bds.py / bbpssw_bds.py
# --------------------------------------------------------------------------

def werner_elements(fidelity: float) -> tuple[float, float, float, float]:
    """Diagonal elements (I, Z, X, Y order, as `QuantumManagerBellDiagonal`
    documents) of the Werner state with the given fidelity - what
    SeQUeNCe's twirling (`is_twirled=True`) reduces every input to."""
    rest = (1.0 - fidelity) / 3.0
    return fidelity, rest, rest, rest


def bds_swap_fidelity(left_fidelity: float, right_fidelity: float, *, gate_fidelity: float, measurement_fidelity: float) -> float:
    """Fidelity of the pair produced by swapping two Werner pairs at a node
    with the given gate/measurement fidelity - verbatim port of
    `EntanglementSwappingA_BDS.swapping_res` (twirled branch), whose
    output fidelity is `new_elem_1`."""
    l1, l2, l3, l4 = werner_elements(left_fidelity)
    r1, r2, r3, r4 = werner_elements(right_fidelity)
    g, m = gate_fidelity, measurement_fidelity
    c_i = l1 * r1 + l2 * r2 + l3 * r3 + l4 * r4
    c_x = l1 * r2 + l2 * r1 + l3 * r4 + l4 * r3
    c_y = l1 * r4 + l4 * r1 + l2 * r3 + l3 * r2
    c_z = l1 * r3 + l3 * r1 + l2 * r4 + l4 * r2
    return g * (m ** 2 * c_i + m * (1 - m) * (c_x + c_z) + (1 - m) ** 2 * c_y) + (1 - g) / 4


def bds_purification_step(
    kept_fidelity: float,
    measured_fidelity: float,
    *,
    own_gate_fidelity: float,
    own_measurement_fidelity: float,
    remote_gate_fidelity: float,
    remote_measurement_fidelity: float,
) -> tuple[float, float]:
    """`(success_probability, kept_fidelity_after_success)` for one BBPSSW
    round between two Werner pairs shared by two nodes - verbatim port of
    `BBPSSW_BDS.purification_res` (twirled branch). With ideal gates and
    measurements this reduces to Dur-Briegel: `p = ab + (1-a)(1-b)` with
    `a = (1 + 2F_kept)/3`, and `F' = (F_k F_m + (1-F_k)(1-F_m)/9) / p`."""
    k1, k2, k3, k4 = werner_elements(kept_fidelity)
    m1, m2, m3, m4 = werner_elements(measured_fidelity)
    g_o, m_o = own_gate_fidelity, own_measurement_fidelity
    g_r, m_r = remote_gate_fidelity, remote_measurement_fidelity
    a, b = k1 + k2, m1 + m2

    same = m_o * m_r + (1 - m_o) * (1 - m_r)
    different = m_o * (1 - m_r) + (1 - m_o) * m_r
    gates = g_o * g_r

    p_success = 0.5 + gates * different + gates * (a * b + (1 - a) * (1 - b)) * (same - different) - gates / 2
    new_elem_1 = gates * (same * (k1 * m1 + k2 * m2) + different * (k1 * m3 + k2 * m4)) + (1 - gates) / 8
    return p_success, new_elem_1 / p_success


def bds_decohered_fidelity(
    fidelity: float,
    idle_time_s: float,
    *,
    coherence_time_s: float,
    decoherence_errors: tuple[float, float, float] = DEPOLARIZING_ERRORS,
) -> float:
    """Fidelity of a Werner pair after one of its memories idles for
    `idle_time_s` - port of `Memory.bds_decohere` (the `_p_id` transform
    row applied to Werner elements). Infinite coherence (`<= 0`, SeQUeNCe's
    `-1` convention) or zero idle time leaves the fidelity unchanged.

    Only ONE memory's channel is applied here; SeQUeNCe applies the channel
    to each memory of a pair separately (each with its own idle time), so
    callers model a pair idling on both ends by calling this twice."""
    if coherence_time_s <= 0 or idle_time_s <= 0:
        return fidelity
    rate = 1.0 / coherence_time_s
    x_rate, y_rate, z_rate = (rate * error for error in decoherence_errors)
    t = idle_time_s
    p_identity = (
        1 + math.exp(-2 * (x_rate + y_rate) * t) + math.exp(-2 * (x_rate + z_rate) * t) + math.exp(-2 * (z_rate + y_rate) * t)
    ) / 4
    # transform row 0 (I) applied to Werner elements: p_I*F + (p_Z + p_X + p_Y)*(1-F)/3
    return p_identity * fidelity + (1 - p_identity) * (1 - fidelity) / 3


# --------------------------------------------------------------------------
# Ket-vector (legacy scalar bookkeeping) formulas
# --------------------------------------------------------------------------

def ket_swap_fidelity(left_fidelity: float, right_fidelity: float, *, swapping_degradation: float) -> float:
    """`EntanglementSwappingA_Circuit.updated_fidelity`: `f1 * f2 * degradation`."""
    return left_fidelity * right_fidelity * swapping_degradation


def ket_purification_step(kept_fidelity: float) -> tuple[float, float]:
    """`(success_probability, improved_fidelity)` per Dur-Briegel (2007) eq.
    18 with equal inputs - `BBPSSWCircuit.improved_fidelity` is exactly the
    ratio of these two terms. Imported lazily so `ibqn.planning` stays
    importable without SeQUeNCe's qutip-backed circuit module."""
    from sequence.entanglement_management.purification.bbpssw_circuit import BBPSSWCircuit

    f = kept_fidelity
    p_success = f ** 2 + 2 * f * (1 - f) / 3 + 5 * ((1 - f) / 3) ** 2
    return p_success, BBPSSWCircuit.improved_fidelity(f)


# --------------------------------------------------------------------------
# Node parameters and the formalism-aware model handed to the planner
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class NodePhysics:
    """The per-node hardware parameters the closed forms above depend on -
    a subset of `network.topology.NodeSpec`, mirrored here so this module
    depends on nothing else in `ibqn` (it is imported by both `network` and
    `planning`)."""

    raw_fidelity: float
    swapping_degradation: float
    gate_fidelity: float
    measurement_fidelity: float
    coherence_time_s: float
    decoherence_errors: tuple[float, float, float] = DEPOLARIZING_ERRORS


class PurificationPhysics(Protocol):
    """What a `planning.purification.PurificationStrategy` needs from the
    physics to project one BBPSSW round: given the (equal) input
    fidelities of two pairs shared by a fixed node pair, the round's
    success probability and the kept pair's output fidelity."""

    def improve(self, fidelity: float) -> tuple[float, float]: ...


@dataclass(frozen=True)
class _BdsPurificationPhysics:
    own: NodePhysics
    remote: NodePhysics

    def improve(self, fidelity: float) -> tuple[float, float]:
        return bds_purification_step(
            fidelity, fidelity,
            own_gate_fidelity=self.own.gate_fidelity, own_measurement_fidelity=self.own.measurement_fidelity,
            remote_gate_fidelity=self.remote.gate_fidelity, remote_measurement_fidelity=self.remote.measurement_fidelity,
        )


@dataclass(frozen=True)
class _KetPurificationPhysics:
    def improve(self, fidelity: float) -> tuple[float, float]:
        return ket_purification_step(fidelity)


IDEAL_BBPSSW: PurificationPhysics = _KetPurificationPhysics()
"""Dur-Briegel BBPSSW with ideal gates - the formula every planner in this
project used before nodes had gate/measurement fidelities. Under the
Bell-diagonal formalism with `gate_fidelity == measurement_fidelity == 1`
the BDS formula reduces to exactly this (see `bds_purification_step`)."""


class PhysicsModel:
    """Formalism-aware closed forms for one topology. Built by
    `network.capabilities.NetworkCapabilities` from the same
    `NetworkTopologySpec` the `SequenceAdapter` configures the simulator
    with, so estimates and simulation never drift apart."""

    def __init__(self, formalism: str, nodes: dict[str, NodePhysics]):
        if formalism not in SUPPORTED_FORMALISMS:
            raise ValueError(f"unsupported formalism {formalism!r} - supported: {SUPPORTED_FORMALISMS}")
        self._formalism = formalism
        self._nodes = dict(nodes)

    @property
    def formalism(self) -> str:
        return self._formalism

    @property
    def is_bell_diagonal(self) -> bool:
        return self._formalism == BELL_DIAGONAL_FORMALISM

    def node(self, node_id: str) -> NodePhysics:
        try:
            return self._nodes[node_id]
        except KeyError:
            raise KeyError(f"no node named '{node_id}' in this topology") from None

    def link_fidelity(self, node_a: str, node_b: str) -> float:
        """Fidelity of a freshly generated elementary pair on link a-b.

        `bell_diagonal`: `SingleHeraldedA.update_memory` writes ONE shared
        Bell-diagonal state for the pair, using the `raw_fidelity` of
        whichever endpoint's protocol runs first - SeQUeNCe gives no
        guarantee which. Both endpoints then report their own node's
        `raw_fidelity` as the scalar `Memory.fidelity`. For a heterogeneous
        link the conservative choice is the lower of the two, which is
        exact whenever the two raw fidelities agree (every topology in this
        project's catalog except the diamond's endpoints).

        `ket_vector`: each memory takes its OWN node's `raw_fidelity`
        (`BarretKokA._entanglement_succeed`) - see
        `fidelity_estimation.SequenceConsistentEstimator` for the per-side
        view; this method returns the conservative minimum in both cases."""
        return min(self.node(node_a).raw_fidelity, self.node(node_b).raw_fidelity)

    def swap_fidelity(self, left_fidelity: float, right_fidelity: float, swap_node: str) -> float:
        node = self.node(swap_node)
        if self.is_bell_diagonal:
            return bds_swap_fidelity(
                left_fidelity, right_fidelity,
                gate_fidelity=node.gate_fidelity, measurement_fidelity=node.measurement_fidelity,
            )
        return ket_swap_fidelity(left_fidelity, right_fidelity, swapping_degradation=node.swapping_degradation)

    def purification_between(self, node_a: str, node_b: str) -> PurificationPhysics:
        """The one-round BBPSSW model for pairs shared by `node_a`/`node_b`
        (link-level purification between neighbors, or end-to-end
        purification between a route's endpoints)."""
        if self.is_bell_diagonal:
            return _BdsPurificationPhysics(own=self.node(node_a), remote=self.node(node_b))
        return IDEAL_BBPSSW

    def decohered_fidelity(self, fidelity: float, idle_time_s: float, node_id: str) -> float:
        """Fidelity after `node_id`'s memory idles for `idle_time_s` - a
        no-op under `ket_vector`, where SeQUeNCe never degrades the scalar
        fidelity (memories only expire outright at the cutoff time)."""
        if not self.is_bell_diagonal:
            return fidelity
        node = self.node(node_id)
        return bds_decohered_fidelity(
            fidelity, idle_time_s,
            coherence_time_s=node.coherence_time_s, decoherence_errors=node.decoherence_errors,
        )
