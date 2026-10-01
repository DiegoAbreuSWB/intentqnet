"""Centralizes every direct interaction with SeQUeNCe's topology/timeline
construction, so the rest of `ibqn` never touches `RouterNetTopo`/`Timeline`
objects directly (see docs/architecture.md).

It is also where the topology's quantum-state formalism is made effective
(docs/physical_model.md). SeQUeNCe 1.0 selects its protocol implementations
through FOUR independent process-wide switches, of which
`Timeline(formalism=...)` sets only the first:

1. `QuantumManager` formalism - how states are stored (`Timeline` sets it);
2. `EntanglementGenerationA/B` global type - Barrett-Kok (circuit-based,
   `ket_vector`) vs single-heralded (the only generation protocol that
   writes Bell-diagonal states);
3. `EntanglementSwappingA/B` formalism - circuit vs Bell-diagonal swap;
4. `BBPSSWProtocol` formalism - circuit vs Bell-diagonal purification.

Left at their defaults (2-4 default to the ket/circuit variants), a
`bell_diagonal` timeline would still run circuit-based swap/purification
and fail on the first swap. `configure_sequence_globals` sets all four
consistently; it runs at construction (BSM nodes instantiate their
generation protocol immediately) and again at `init()` (every other
protocol is created lazily, while the simulation runs).
"""
from __future__ import annotations

from sequence.constants import BARRET_KOK, BELL_DIAGONAL_STATE_FORMALISM, KET_VECTOR_FORMALISM, SINGLE_HERALDED
from sequence.entanglement_management.generation import EntanglementGenerationA, EntanglementGenerationB
from sequence.entanglement_management.purification.bbpssw_protocol import BBPSSWProtocol
from sequence.entanglement_management.swapping.swapping_base import EntanglementSwappingA, EntanglementSwappingB
from sequence.kernel.quantum_manager import QuantumManager
from sequence.kernel.timeline import Timeline
from sequence.topology.node import QuantumRouter
from sequence.topology.router_net_topo import RouterNetTopo

from ..utils.logging import get_logger
from .sequence_patches import apply_sequence_patches
from .topology import NetworkTopologySpec

logger = get_logger(__name__)

_GENERATION_TYPE_BY_FORMALISM = {
    KET_VECTOR_FORMALISM: BARRET_KOK,
    BELL_DIAGONAL_STATE_FORMALISM: SINGLE_HERALDED,
}


def configure_sequence_globals(formalism: str) -> None:
    """Makes `formalism` effective for every SeQUeNCe protocol created from
    now on in this process (see the module docstring)."""
    try:
        generation_type = _GENERATION_TYPE_BY_FORMALISM[formalism]
    except KeyError:
        raise ValueError(f"unsupported formalism {formalism!r} - supported: {sorted(_GENERATION_TYPE_BY_FORMALISM)}") from None
    QuantumManager.set_global_manager_formalism(formalism)
    EntanglementGenerationA.set_global_type(generation_type)
    EntanglementGenerationB.set_global_type(generation_type)
    EntanglementSwappingA.set_formalism(formalism)
    EntanglementSwappingB.set_formalism(formalism)
    BBPSSWProtocol.set_formalism(formalism)


def reset_sequence_globals() -> None:
    """Restores every switch to SeQUeNCe's own defaults (`ket_vector`,
    Barrett-Kok, circuit swap/purification) - for test isolation."""
    # Explicit `set_*` calls rather than the classes' own `clear_*` helpers:
    # SeQUeNCe 1.0 only defines those on some of the classes.
    QuantumManager.clear_active_formalism()
    EntanglementGenerationA.set_global_type(BARRET_KOK)
    EntanglementGenerationB.set_global_type(BARRET_KOK)
    EntanglementSwappingA.set_formalism(KET_VECTOR_FORMALISM)
    EntanglementSwappingB.set_formalism(KET_VECTOR_FORMALISM)
    BBPSSWProtocol.set_formalism(KET_VECTOR_FORMALISM)


def active_sequence_globals() -> dict[str, str]:
    """The current value of each switch, for tests/diagnostics."""
    return {
        "quantum_manager": QuantumManager.get_active_formalism(),
        "generation": EntanglementGenerationA.get_global_type(),
        "generation_bsm_side": EntanglementGenerationB.get_global_type(),
        "swapping_a": EntanglementSwappingA.get_formalism(),
        "swapping_b": EntanglementSwappingB.get_formalism(),
        "purification": BBPSSWProtocol.get_formalism(),
    }


class SequenceAdapter:
    """Owns one `RouterNetTopo` (and, through it, one `Timeline`) built from
    a `NetworkTopologySpec`. This is the *only* class in `ibqn` allowed to
    construct SeQUeNCe topology/timeline objects directly.

    Two adapters with DIFFERENT formalisms must not be run interleaved in
    one process: the switches above are global, and each adapter re-asserts
    its own formalism at `init()` - the last one to initialize wins for
    every protocol created afterwards. Sequential runs (the norm everywhere
    in this project, including `planners.l4_simulation`'s internal loop and
    `assurance.reconciliation`'s second episode) are fine."""

    def __init__(self, topology_spec: NetworkTopologySpec, *, seed: int = 0):
        self._spec = topology_spec
        self._seed = seed
        configure_sequence_globals(topology_spec.formalism)
        apply_sequence_patches()
        config = topology_spec.to_router_net_topo_config(seed=seed)
        self._router_net_topo = RouterNetTopo(config)
        self._apply_node_physical_params()
        logger.info(
            "topology built: %d routers, %d quantum links, formalism=%s, seed=%d",
            len(topology_spec.nodes), len(topology_spec.quantum_links), topology_spec.formalism, seed,
        )
        self._initialized = False

    def _apply_node_physical_params(self) -> None:
        """Memory/BSM/swapping parameters travel through the `RouterNetTopo`
        config's `templates` (see `NetworkTopologySpec.to_router_net_topo_config`).
        Gate and measurement fidelity are the exception: `RouterNetTopo._add_nodes`
        never forwards the config's `gate_fidelity`/`measurement_fidelity`
        keys to `QuantumRouter.__init__` (SeQUeNCe 1.0), so they are set on
        the built routers here - `Node.gate_fid`/`Node.meas_fid` are plain
        attributes read at protocol run time by
        `EntanglementSwappingA_BDS.swapping_res` and
        `BBPSSW_BDS.purification_res`."""
        for node_spec in self._spec.nodes:
            router = self.get_router(node_spec.id)
            router.gate_fid = node_spec.gate_fidelity
            router.meas_fid = node_spec.measurement_fidelity

    @property
    def spec(self) -> NetworkTopologySpec:
        return self._spec

    @property
    def formalism(self) -> str:
        return self._spec.formalism

    def get_timeline(self) -> Timeline:
        return self._router_net_topo.get_timeline()

    def get_router(self, node_id: str) -> QuantumRouter:
        node = self.get_timeline().get_entity_by_name(node_id)
        if node is None:
            raise KeyError(f"no node named '{node_id}' in this topology")
        if not isinstance(node, QuantumRouter):
            raise TypeError(f"node '{node_id}' is a {type(node).__name__}, not a QuantumRouter")
        return node

    def router_ids(self) -> list[str]:
        return [node.id for node in self._spec.nodes]

    def init(self) -> None:
        """Initializes all entities (`Timeline.init()`). Idempotent: calling
        it more than once is a no-op, since SeQUeNCe entities do not expect
        `init()` to run twice. Re-asserts this topology's formalism first,
        because swap/purification protocols are created lazily during the
        run and read the global switches at creation time."""
        configure_sequence_globals(self._spec.formalism)
        if self._initialized:
            return
        self.get_timeline().init()
        self._initialized = True

    def run(self) -> None:
        """Initializes (if needed) and runs the simulation to completion."""
        self.init()
        logger.info("running simulation, stop_time=%.3fs", self._spec.stop_time_s)
        self.get_timeline().run()
