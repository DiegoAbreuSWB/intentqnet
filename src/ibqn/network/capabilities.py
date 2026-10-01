"""A pure-Python, SeQUeNCe-independent view of a `NetworkTopologySpec`: a
graph for path-finding plus the physical parameters needed to *estimate*
fidelity/loss before running any simulation.

Built once from the same `NetworkTopologySpec` that `SequenceAdapter` uses to
configure the real hardware, so `planning.*` estimates and what actually
gets simulated never drift apart. `planning/` never imports
`network.sequence_adapter` - only this module (and `ibqn.physics`, which
carries the formalism-specific closed forms both sides share).
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from ..physics import DEPOLARIZING_ERRORS, NodePhysics, PhysicsModel
from .topology import NetworkTopologySpec


@dataclass(frozen=True)
class LinkCapability:
    source: str
    destination: str
    distance_m: float
    attenuation_db_per_m: float
    detector_efficiency: float | None = None

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
    gate_fidelity: float = 1.0
    measurement_fidelity: float = 1.0
    swapping_success_prob: float = 1.0
    coherence_time_s: float = -1.0
    cutoff_ratio: float = 1.0
    decoherence_errors: tuple[float, float, float] = DEPOLARIZING_ERRORS

    def physics(self) -> NodePhysics:
        return NodePhysics(
            raw_fidelity=self.raw_fidelity, swapping_degradation=self.swapping_degradation,
            gate_fidelity=self.gate_fidelity, measurement_fidelity=self.measurement_fidelity,
            coherence_time_s=self.coherence_time_s, decoherence_errors=self.decoherence_errors,
        )


class NetworkCapabilities:
    """Read-only, queryable view of a topology's nodes/links, for use by
    `planning.routing`/`planning.feasibility` before any `SequenceAdapter`
    exists."""

    def __init__(self, spec: NetworkTopologySpec):
        self._classical_delay_s = spec.classical_delay_s
        self._formalism = spec.formalism
        self._nodes: dict[str, NodeCapability] = {
            node.id: NodeCapability(
                id=node.id, memories=node.memories,
                raw_fidelity=node.raw_fidelity, swapping_degradation=node.swapping_degradation,
                gate_fidelity=node.gate_fidelity, measurement_fidelity=node.measurement_fidelity,
                swapping_success_prob=node.swapping_success_prob,
                coherence_time_s=node.coherence_time_s, cutoff_ratio=node.cutoff_ratio,
                decoherence_errors=node.decoherence_errors or DEPOLARIZING_ERRORS,
            )
            for node in spec.nodes
        }
        self._links: dict[frozenset[str], LinkCapability] = {
            frozenset({link.source, link.destination}): LinkCapability(
                source=link.source, destination=link.destination,
                distance_m=link.distance_m, attenuation_db_per_m=link.attenuation_db_per_m,
                detector_efficiency=link.detector_efficiency,
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
        self._physics = PhysicsModel(
            spec.formalism, {node_id: node.physics() for node_id, node in self._nodes.items()},
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

    @property
    def formalism(self) -> str:
        """The topology's quantum-state formalism (`NetworkTopologySpec.formalism`)."""
        return self._formalism

    @property
    def physics(self) -> PhysicsModel:
        """Formalism-aware closed forms (swap, purification, decoherence) for
        this topology - the ONLY place planners get fidelity arithmetic from
        (see docs/physical_model.md)."""
        return self._physics

    @property
    def classical_delay_s(self) -> float:
        """Single classical-channel delay (seconds) applying to every node
        pair in this topology (`NetworkTopologySpec.classical_delay_s`) -
        exposed read-only for `planning.planners.l3_probabilistic`'s
        attempt-rate model (planner-family study, M5); not used by
        L1/L2, which never need timing beyond the closed-form fidelity
        formulas."""
        return self._classical_delay_s

    def hop_fidelity(self, a: str, b: str) -> float:
        """Estimated fidelity of a freshly generated elementary pair on link
        `a`-`b`: `min(raw_fidelity(a), raw_fidelity(b))` (see
        `ibqn.physics.PhysicsModel.link_fidelity` for why the minimum is the
        conservative, formalism-independent choice). Exact whenever both
        endpoints share the same `raw_fidelity` - every topology in this
        project's catalog except the diamond's endpoints. Confirmed
        (campaign C01, Fase H3) to *underestimate* the legacy ket_vector
        model whenever a swap happens at a node whose `raw_fidelity` exceeds
        a neighbor's; `planning.fidelity_estimation.SequenceConsistentEstimator`
        reproduces that per-node mechanism instead. See
        docs/fidelity_estimation_model.md and docs/limitations.md."""
        return self._physics.link_fidelity(a, b)
