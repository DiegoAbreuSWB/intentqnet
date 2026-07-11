"""Reusable `NetworkTopologySpec` builders shared by the H1 "SeQUeNCe
basics" notebooks (`notebooks/01`-`06`), so each notebook configures a
topology with a single, documented function call instead of repeating the
same node/link construction.
"""
from __future__ import annotations

from ..network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec


def two_node_spec(
    *,
    memories: int = 10,
    distance_m: float = 1000,
    attenuation_db_per_m: float = 1e-4,
    raw_fidelity: float = 0.85,
    classical_delay_s: float = 1e-4,
    stop_time_s: float = 0.1,
) -> NetworkTopologySpec:
    """Two routers (`a`, `b`) directly linked - SeQUeNCe places the BSM node
    (`BSM.a.b`) at the midpoint automatically (see
    docs/sequence_code_analysis.md, section 4.6)."""
    return NetworkTopologySpec(
        nodes=[
            NodeSpec(id="a", memories=memories, raw_fidelity=raw_fidelity),
            NodeSpec(id="b", memories=memories, raw_fidelity=raw_fidelity),
        ],
        quantum_links=[
            QuantumLinkSpec(source="a", destination="b", distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m),
        ],
        classical_delay_s=classical_delay_s,
        stop_time_s=stop_time_s,
    )


def three_node_spec(
    *,
    end_memories: int = 10,
    repeater_memories: int = 20,
    distance_m: float = 1000,
    attenuation_db_per_m: float = 1e-5,
    raw_fidelity: float = 0.85,
    swapping_degradation: float = 0.95,
    classical_delay_s: float = 1e-4,
    stop_time_s: float = 0.2,
) -> NetworkTopologySpec:
    """Linear chain `a - r - b`, `r` acting as the sole repeater/swap node."""
    return NetworkTopologySpec(
        nodes=[
            NodeSpec(id="a", memories=end_memories, raw_fidelity=raw_fidelity),
            NodeSpec(
                id="r", memories=repeater_memories, raw_fidelity=raw_fidelity,
                swapping_degradation=swapping_degradation,
            ),
            NodeSpec(id="b", memories=end_memories, raw_fidelity=raw_fidelity),
        ],
        quantum_links=[
            QuantumLinkSpec(source="a", destination="r", distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m),
            QuantumLinkSpec(source="r", destination="b", distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m),
        ],
        classical_delay_s=classical_delay_s,
        stop_time_s=stop_time_s,
    )
