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

Physical-realism revision (docs/physical_model.md): every hardware
parameter is pushed through `RouterNetTopo`'s `templates` mechanism - one
template per router (`MemoryArray`/`EntanglementSwapping` sections) and one
per quantum link (the auto-generated BSM node's `encoding_type`/detector
parameters) - rather than patched onto already-built objects. This matters
for `coherence_time`: `Memory.__init__` derives `decoherence_rate` from it
once, at construction, so setting it afterwards (the pre-revision
`MemoryArray.update_memory_params` approach) silently left continuous
decoherence disabled.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sequence.constants import SECOND

from ..physics import BELL_DIAGONAL_FORMALISM, KET_VECTOR_FORMALISM, SUPPORTED_FORMALISMS

_ROUTER_TYPE = "QuantumRouter"

DEFAULT_FORMALISM = BELL_DIAGONAL_FORMALISM
DEFAULT_COHERENCE_TIME_S = 1.0
DEFAULT_CUTOFF_RATIO = 0.5

Formalism = Literal["ket_vector", "bell_diagonal"]


class NodeSpec(BaseModel):
    """A quantum router in the topology. Per-node seeds are assigned by
    `SequenceAdapter`, not here (see `SequenceAdapter._build_config`) -
    scenario authors only order the nodes; reproducibility comes from a
    single experiment-level seed.

    Which parameters the simulator actually consumes depends on the
    topology's `formalism` (see docs/physical_model.md):

    - `bell_diagonal` (default): `raw_fidelity`, `gate_fidelity`,
      `measurement_fidelity`, `swapping_success_prob`, `coherence_time_s`,
      `decoherence_errors`, `cutoff_ratio`. `swapping_degradation` is
      IGNORED - swap noise is derived from the node's gate/measurement
      fidelity by `EntanglementSwappingA_BDS.swapping_res`.
    - `ket_vector` (legacy): `raw_fidelity`, `swapping_degradation`,
      `swapping_success_prob`, `coherence_time_s` (hard cutoff only, no
      continuous decoherence). Gate/measurement fidelity and
      `decoherence_errors` are ignored by SeQUeNCe's circuit-based
      protocols.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    type: Literal["quantum_router"] = "quantum_router"
    memories: int = Field(gt=0, description="number of quantum memories in this router's MemoryArray")
    raw_fidelity: float = Field(
        default=0.85, gt=0.5, le=1.0,
        description="dimensionless, initial fidelity of freshly generated elementary pairs "
                     "(sequence.components.memory.MemoryArray default is 0.85)",
    )
    swapping_degradation: float = Field(
        default=0.95, gt=0.0, le=1.0,
        description="dimensionless, LEGACY ket_vector-only fidelity factor applied per swap "
                     "(sequence.entanglement_management.swapping.swapping_circuit default is 0.95); ignored "
                     "under bell_diagonal, where swap noise comes from gate_fidelity/measurement_fidelity",
    )
    swapping_success_prob: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="dimensionless, probability that this node's Bell-state measurement succeeds when it "
                     "swaps (QuantumRouter.swapping_success_prob, default 1)",
    )
    gate_fidelity: float = Field(
        default=1.0, gt=0.0, le=1.0,
        description="dimensionless, fidelity of this node's two-qubit gates (Node.gate_fid, default 1 = ideal); "
                     "bell_diagonal only - enters EntanglementSwappingA_BDS.swapping_res and BBPSSW_BDS.purification_res",
    )
    measurement_fidelity: float = Field(
        default=1.0, gt=0.0, le=1.0,
        description="dimensionless, fidelity of this node's single-qubit measurements (Node.meas_fid, default 1); "
                     "bell_diagonal only",
    )
    coherence_time_s: float = Field(
        default=DEFAULT_COHERENCE_TIME_S,
        description="seconds, memory coherence time T. bell_diagonal: continuous Pauli-channel decoherence at "
                     "rate 1/T while a pair idles (Memory.bds_decohere) PLUS a hard cutoff at cutoff_ratio*T; "
                     "ket_vector: hard cutoff only. A negative value means infinite coherence (SeQUeNCe's -1 "
                     "convention, the pre-revision default)",
    )
    cutoff_ratio: float = Field(
        default=DEFAULT_CUTOFF_RATIO, gt=0.0,
        description="dimensionless, a memory holding a pair is force-expired (reset to RAW) after "
                     "cutoff_ratio * coherence_time_s (Memory.cutoff_ratio; SeQUeNCe default 1). The default 0.5 "
                     "keeps a raw_fidelity>=0.85 pair above the F=0.5 purification threshold for its whole "
                     "lifetime under depolarizing decoherence - see docs/physical_model.md",
    )
    decoherence_errors: tuple[float, float, float] | None = Field(
        default=None,
        description="probabilities of X, Y, Z Pauli errors conditioned on an error (must sum to 1); None means "
                     "SeQUeNCe's bell_diagonal default [1/3, 1/3, 1/3] (depolarizing). bell_diagonal only",
    )
    memory_efficiency: float = Field(
        default=1.0, gt=0.0, le=1.0,
        description="dimensionless, probability a memory emits its photon when excited (Memory.efficiency, default 1)",
    )
    memory_frequency_hz: float = Field(
        default=80e6, gt=0.0,
        description="Hz, maximum memory excitation frequency (Memory.frequency, default 80e6)",
    )

    @model_validator(mode="after")
    def _decoherence_errors_normalized(self) -> "NodeSpec":
        if self.decoherence_errors is not None:
            total = sum(self.decoherence_errors)
            if any(p < 0 for p in self.decoherence_errors) or abs(total - 1.0) > 1e-8:
                raise ValueError(f"decoherence_errors must be non-negative and sum to 1, got {self.decoherence_errors}")
        return self

    @property
    def infinite_coherence(self) -> bool:
        return self.coherence_time_s <= 0


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
    detector_efficiency: float | None = Field(
        default=None, gt=0.0, le=1.0,
        description="dimensionless, efficiency of each of the midpoint BSM's two detectors; None keeps "
                     "SeQUeNCe's Detector default (0.9)",
    )


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
    platform: str | None = Field(
        default=None,
        description="name of the `network.platforms.PlatformProfile` whose demonstrated hardware parameters this "
                     "topology's nodes/links carry (provenance only - the values themselves live in the NodeSpec/"
                     "QuantumLinkSpec fields); None when parameters were set by hand",
    )
    formalism: Formalism = Field(
        default=DEFAULT_FORMALISM,
        description="quantum-state formalism: 'bell_diagonal' (default - state-derived fidelity, gate/measurement "
                     "noise, continuous decoherence, single-heralded generation) or 'ket_vector' (legacy scalar "
                     "bookkeeping model with Barrett-Kok generation) - see docs/physical_model.md",
    )

    @model_validator(mode="after")
    def _links_reference_declared_nodes(self) -> "NetworkTopologySpec":
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("node ids must be unique")
        for link in self.quantum_links:
            for endpoint in (link.source, link.destination):
                if endpoint not in node_ids:
                    raise ValueError(f"quantum_links references undeclared node '{endpoint}'")
        if self.formalism not in SUPPORTED_FORMALISMS:
            raise ValueError(f"unsupported formalism {self.formalism!r}")
        return self

    @property
    def is_bell_diagonal(self) -> bool:
        return self.formalism == BELL_DIAGONAL_FORMALISM

    def node(self, node_id: str) -> NodeSpec:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(f"no node named '{node_id}' in this topology")

    @staticmethod
    def _router_template_name(node_id: str) -> str:
        return f"{node_id}.router_template"

    @staticmethod
    def _bsm_template_name(link: QuantumLinkSpec) -> str:
        return f"{link.source}.{link.destination}.bsm_template"

    def _router_template(self, node: NodeSpec) -> dict[str, Any]:
        memory_array: dict[str, Any] = {
            "fidelity": node.raw_fidelity,
            "coherence_time": node.coherence_time_s if not node.infinite_coherence else -1,
            "cutoff_ratio": node.cutoff_ratio,
            "efficiency": node.memory_efficiency,
            "frequency": node.memory_frequency_hz,
        }
        if self.is_bell_diagonal and node.decoherence_errors is not None:
            # `MemoryArray.__init__` asserts decoherence_errors are only given
            # under the Bell-diagonal formalism, and fills in the depolarizing
            # default itself when omitted there.
            memory_array["decoherence_errors"] = list(node.decoherence_errors)
        swapping: dict[str, Any] = {"swapping_success_prob": node.swapping_success_prob}
        if not self.is_bell_diagonal:
            # `es_rule_action_A` forwards `swapping_degradation` as a `degradation=`
            # kwarg that only `EntanglementSwappingA_Circuit` accepts - the BDS
            # class derives swap noise from gate/measurement fidelity instead.
            swapping["swapping_degradation"] = node.swapping_degradation
        return {"MemoryArray": memory_array, "EntanglementSwapping": swapping}

    def _bsm_template(self, link: QuantumLinkSpec) -> dict[str, Any]:
        if self.is_bell_diagonal:
            encoding, bsm_class = "single_heralded", "SingleHeraldedBSM"
        else:
            encoding, bsm_class = "single_atom", "SingleAtomBSM"
        template: dict[str, Any] = {"encoding_type": encoding}
        if link.detector_efficiency is not None:
            template[bsm_class] = {"detectors": [{"efficiency": link.detector_efficiency}] * 2}
        return template

    def to_router_net_topo_config(self, *, seed: int) -> dict[str, Any]:
        """Builds the config `dict` for `RouterNetTopo(config)`.

        Per-node/per-qconnection seeds are derived deterministically from
        `seed` by position (`seed + index`), so the same `NetworkTopologySpec`
        + `seed` always reproduces the same topology-level randomness.
        """
        templates: dict[str, dict[str, Any]] = {}
        node_entries = []
        for i, node in enumerate(self.nodes):
            template_name = self._router_template_name(node.id)
            templates[template_name] = self._router_template(node)
            node_entries.append({
                "name": node.id, "type": _ROUTER_TYPE, "seed": seed + i, "memo_size": node.memories,
                "template": template_name,
            })

        qconnection_entries = []
        for i, link in enumerate(self.quantum_links):
            template_name = self._bsm_template_name(link)
            templates[template_name] = self._bsm_template(link)
            qconnection_entries.append({
                "node1": link.source,
                "node2": link.destination,
                "attenuation": link.attenuation_db_per_m,
                "distance": link.distance_m,
                "type": "meet_in_the_middle",
                "seed": seed + len(self.nodes) + i,
                "template": template_name,
            })

        node_ids = [node.id for node in self.nodes]
        delay_ps = int(self.classical_delay_s * SECOND)
        cconnection_entries = [
            {"node1": a, "node2": b, "delay": delay_ps}
            for idx, a in enumerate(node_ids)
            for b in node_ids[idx + 1:]
        ]
        return {
            "templates": templates,
            "nodes": node_entries,
            "qconnections": qconnection_entries,
            "cconnections": cconnection_entries,
            "stop_time": int(self.stop_time_s * SECOND),
            "formalism": self.formalism,
        }
