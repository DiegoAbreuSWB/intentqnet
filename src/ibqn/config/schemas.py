"""Declarative scenario schema (see the project brief, section 15
"Estrutura de cenários"): bundles a network topology, simulation parameters,
and a list of intent files into one reproducible unit.

Reuses `network.topology.NodeSpec`/`QuantumLinkSpec` rather than duplicating
their unit-documented fields.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..network.topology import DEFAULT_FORMALISM, NetworkTopologySpec, NodeSpec, QuantumLinkSpec


class SimulationSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    duration_s: float = Field(gt=0, description="seconds, total simulation stop time")
    seed: int = Field(description="base experiment seed - per-node/per-link seeds derive from it, see "
                                   "NetworkTopologySpec.to_router_net_topo_config")


class IntentReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    file: str = Field(min_length=1, description="path to an intent YAML/JSON file, relative to the scenario file's directory")


class ScenarioSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    simulation: SimulationSpec
    nodes: list[NodeSpec] = Field(min_length=2)
    quantum_links: list[QuantumLinkSpec] = Field(min_length=1)
    classical_delay_s: float = Field(
        default=1e-3, ge=0, description="seconds, one-way delay for the automatic full-mesh classical network"
    )
    formalism: str = Field(
        default=DEFAULT_FORMALISM,
        description="one of sequence.constants.*_FORMALISM (default bell_diagonal - docs/physical_model.md)",
    )
    platform: str | None = Field(
        default=None,
        description="name of a `network.platforms.PlatformProfile`; when set, every node's and link's hardware "
                     "parameters are replaced by the profile's literature-calibrated values (node ids, memory "
                     "counts and link distances are kept, and classical_delay_s becomes the longest link's fiber "
                     "delay) - see docs/parameter_calibration.md",
    )
    intents: list[IntentReference] = Field(min_length=1)

    def to_network_topology_spec(self) -> NetworkTopologySpec:
        spec = NetworkTopologySpec(
            nodes=self.nodes,
            quantum_links=self.quantum_links,
            classical_delay_s=self.classical_delay_s,
            stop_time_s=self.simulation.duration_s,
            formalism=self.formalism,
        )
        if self.platform is not None:
            from ..network.platforms import apply_platform, resolve_platform

            spec = apply_platform(spec, resolve_platform(self.platform))
        return spec
