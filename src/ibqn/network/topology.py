"""Declarative network topology spec, translated into the config `dict`
accepted directly by `sequence.topology.router_net_topo.RouterNetTopo`
(confirmed in `docs/sequence_code_analysis.md`, section 4.6: `Topology.__init__`
accepts `str | dict`).

This module never builds `Node`/`QuantumChannel`/etc. objects itself - all
actual hardware construction, BSM-node auto-generation for
`meet_in_the_middle` links, and Dijkstra-based static-routing-table
population are delegated to `RouterNetTopo` (see
docs/sequence_code_analysis.md, section 4.6), so the intent layer never
duplicates that logic.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sequence.constants import SECOND

_ROUTER_TYPE = "QuantumRouter"


class NodeSpec(BaseModel):
    """A quantum router in the topology. Per-node seeds are assigned by
    `SequenceAdapter`, not here (see `SequenceAdapter._build_config`) -
    scenario authors only order the nodes; reproducibility comes from a
    single experiment-level seed."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    type: Literal["quantum_router"] = "quantum_router"
    memories: int = Field(gt=0, description="number of quantum memories in this router's MemoryArray")


class QuantumLinkSpec(BaseModel):
    """A quantum link between two routers. SeQUeNCe places a BSM node at the
    midpoint (`meet_in_the_middle`) and splits `distance_m` in half for each
    router-to-BSM quantum channel automatically - callers always specify the
    full router-to-router distance."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    distance_m: float = Field(gt=0, description="meters, full router-to-router distance")
    attenuation_db_per_m: float = Field(gt=0, description="dB/m, QuantumChannel attenuation coefficient")


class NetworkTopologySpec(BaseModel):
    """Everything `SequenceAdapter` needs to build a `RouterNetTopo` + `Timeline`.

    Classical connectivity is always a full mesh among every router in
    `nodes` (a single `classical_delay_s` applies to every pair) - partial/
    sparse classical topologies are not supported in this version:
    `RouterNetTopo._add_qconnections` requires a direct classical connection
    between every pair of routers that share a quantum link, and no
    scenario in this project's test suite has needed anything sparser (see
    docs/sequence_code_analysis.md, section 4.7).
    """

    model_config = ConfigDict(frozen=True)

    nodes: list[NodeSpec] = Field(min_length=2)
    quantum_links: list[QuantumLinkSpec] = Field(min_length=1)
    classical_delay_s: float = Field(
        default=1e-3, ge=0, description="seconds, one-way delay for the automatic full-mesh classical network"
    )
    stop_time_s: float = Field(gt=0, description="seconds, simulation stop time")
    formalism: str = Field(default="ket_vector", description="one of sequence.constants.*_FORMALISM")

    @model_validator(mode="after")
    def _links_reference_declared_nodes(self) -> "NetworkTopologySpec":
        node_ids = {node.id for node in self.nodes}
        for link in self.quantum_links:
            for endpoint in (link.source, link.destination):
                if endpoint not in node_ids:
                    raise ValueError(f"quantum_links references undeclared node '{endpoint}'")
        return self

    def to_router_net_topo_config(self, *, seed: int) -> dict[str, Any]:
        """Builds the config `dict` for `RouterNetTopo(config)`.

        Per-node/per-qconnection seeds are derived deterministically from
        `seed` by position (`seed + index`), so the same `NetworkTopologySpec`
        + `seed` always reproduces the same topology-level randomness.
        """
        node_entries = [
            {"name": node.id, "type": _ROUTER_TYPE, "seed": seed + i, "memo_size": node.memories}
            for i, node in enumerate(self.nodes)
        ]
        qconnection_entries = [
            {
                "node1": link.source,
                "node2": link.destination,
                "attenuation": link.attenuation_db_per_m,
                "distance": link.distance_m,
                "type": "meet_in_the_middle",
                "seed": seed + len(self.nodes) + i,
            }
            for i, link in enumerate(self.quantum_links)
        ]
        node_ids = [node.id for node in self.nodes]
        delay_ps = int(self.classical_delay_s * SECOND)
        cconnection_entries = [
            {"node1": a, "node2": b, "delay": delay_ps}
            for idx, a in enumerate(node_ids)
            for b in node_ids[idx + 1:]
        ]
        return {
            "nodes": node_entries,
            "qconnections": qconnection_entries,
            "cconnections": cconnection_entries,
            "stop_time": int(self.stop_time_s * SECOND),
            "formalism": self.formalism,
        }
