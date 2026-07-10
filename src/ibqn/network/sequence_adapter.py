"""Centralizes every direct interaction with SeQUeNCe's topology/timeline
construction, so the rest of `ibqn` never touches `RouterNetTopo`/`Timeline`
objects directly (see docs/architecture.md).
"""
from __future__ import annotations

from sequence.kernel.timeline import Timeline
from sequence.topology.node import QuantumRouter
from sequence.topology.router_net_topo import RouterNetTopo

from ..utils.logging import get_logger
from .topology import NetworkTopologySpec

logger = get_logger(__name__)


class SequenceAdapter:
    """Owns one `RouterNetTopo` (and, through it, one `Timeline`) built from
    a `NetworkTopologySpec`. This is the *only* class in `ibqn` allowed to
    construct SeQUeNCe topology/timeline objects directly."""

    def __init__(self, topology_spec: NetworkTopologySpec, *, seed: int = 0):
        self._spec = topology_spec
        self._seed = seed
        config = topology_spec.to_router_net_topo_config(seed=seed)
        self._router_net_topo = RouterNetTopo(config)
        self._apply_node_physical_params()
        logger.info(
            "topology built: %d routers, %d quantum links, seed=%d",
            len(topology_spec.nodes), len(topology_spec.quantum_links), seed,
        )
        self._initialized = False

    def _apply_node_physical_params(self) -> None:
        """`raw_fidelity`/`swapping_degradation` are not part of the
        `RouterNetTopo` config dict schema (see docs/sequence_integration.md)
        - they must be pushed into the real hardware objects after
        construction, via the same public hooks the official SeQUeNCe
        examples use (`MemoryArray.update_memory_params`,
        `QuantumRouter.swapping_degradation`)."""
        for node_spec in self._spec.nodes:
            router = self.get_router(node_spec.id)
            memory_array = router.get_components_by_type("MemoryArray")[0]
            memory_array.update_memory_params("raw_fidelity", node_spec.raw_fidelity)
            router.swapping_degradation = node_spec.swapping_degradation

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
        `init()` to run twice."""
        if self._initialized:
            return
        self.get_timeline().init()
        self._initialized = True

    def run(self) -> None:
        """Initializes (if needed) and runs the simulation to completion."""
        self.init()
        logger.info("running simulation, stop_time=%.3fs", self._spec.stop_time_s)
        self.get_timeline().run()
