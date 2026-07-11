"""A pure-Python, SeQUeNCe-independent view of a `NetworkTopologySpec`: a
graph for path-finding plus the physical parameters needed to *estimate*
fidelity/loss before running any simulation.

Built once from the same `NetworkTopologySpec` that `SequenceAdapter` uses to
configure the real hardware (`SequenceAdapter._apply_node_physical_params`),
so `planning.*` estimates and what actually gets simulated never drift apart.
`planning/` never imports `network.sequence_adapter` - only this module.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from .topology import NetworkTopologySpec


@dataclass(frozen=True)
class LinkCapability:
    source: str
    destination: str
    distance_m: float
    attenuation_db_per_m: float

    @property
    def loss_db(self) -> float:
        """Approximate one-way optical loss, in dB (`distance_m * attenuation_db_per_m`,
        the same linear model `sequence.components.optical_channel.QuantumChannel`
        uses to derive its `loss` probability)."""
        return self.distance_m * self.attenuation_db_per_m


@dataclass(frozen=True)
class NodeCapability:
    id: str
    memories: int
    raw_fidelity: float
    swapping_degradation: float


class NetworkCapabilities:
    """Read-only, queryable view of a topology's nodes/links, for use by
    `planning.routing`/`planning.feasibility` before any `SequenceAdapter`
    exists."""

    def __init__(self, spec: NetworkTopologySpec):
        self._nodes: dict[str, NodeCapability] = {
            node.id: NodeCapability(
                id=node.id, memories=node.memories,
                raw_fidelity=node.raw_fidelity, swapping_degradation=node.swapping_degradation,
            )
            for node in spec.nodes
        }
        self._links: dict[frozenset[str], LinkCapability] = {
            frozenset({link.source, link.destination}): LinkCapability(
                source=link.source, destination=link.destination,
                distance_m=link.distance_m, attenuation_db_per_m=link.attenuation_db_per_m,
            )
            for link in spec.quantum_links
        }
        self._graph = nx.Graph()
        self._graph.add_nodes_from(self._nodes)
        for link in spec.quantum_links:
            self._graph.add_edge(
                link.source, link.destination,
                distance_m=link.distance_m, loss_db=link.distance_m * link.attenuation_db_per_m,
            )

    def node(self, node_id: str) -> NodeCapability:
        try:
            return self._nodes[node_id]
        except KeyError:
            raise KeyError(f"no node named '{node_id}' in this topology") from None

    def link(self, a: str, b: str) -> LinkCapability:
        try:
            return self._links[frozenset({a, b})]
        except KeyError:
            raise KeyError(f"no direct quantum link between '{a}' and '{b}'") from None

    def graph(self) -> nx.Graph:
        """Returns the underlying `networkx.Graph` (nodes = router ids, edge
        attributes `distance_m`/`loss_db`) for routing strategies to run
        their own path-finding algorithms over."""
        return self._graph

    def hop_fidelity(self, a: str, b: str) -> float:
        """Estimated fidelity of a freshly generated elementary pair on link
        `a`-`b`. `Memory.raw_fidelity` is configured per-node
        (`MemoryArray.update_memory_params`), and each side's memory is
        independently set to *its own* node's `raw_fidelity` on success
        (`sequence/entanglement_management/generation/barret_kok.py:228`) -
        for a heterogeneous pair this is conservatively estimated as the
        minimum of the two endpoints' configured value.

        Confirmed (campaign C01, Fase H3, `notebooks/article/
        A05_planner_estimation_error.ipynb`) that this genuinely
        *underestimates* whenever a swap happens at a node whose
        `raw_fidelity` exceeds a neighbor's: both memories feeding that
        swap belong to the swap node itself, so the real result depends on
        the swap node's own `raw_fidelity`, not `min(a, b)` - up to 0.083
        (12%) off on the diamond topology's heterogeneous nodes, exactly 0
        on every uniform-fidelity topology this project otherwise uses.
        See `docs/limitations.md`."""
        return min(self.node(a).raw_fidelity, self.node(b).raw_fidelity)
