"""Reusable `NetworkTopologySpec` builders shared by the H1 "SeQUeNCe
basics" notebooks (`notebooks/01`-`06`) and the H2 "intent-based
architecture" notebooks (`notebooks/10`-`19`), so each notebook configures
a topology with a single, documented function call instead of repeating
the same node/link construction.
"""
from __future__ import annotations

from ..network.topology import DEFAULT_FORMALISM, NetworkTopologySpec, NodeSpec, QuantumLinkSpec

DIAMOND_BAD_ATTENUATION = 0.02
DIAMOND_GOOD_ATTENUATION = 1e-5
DIAMOND_NODE_FIDELITY = 0.9
DIAMOND_NODE_DEGRADATION = 0.95


def two_node_spec(
    *,
    memories: int = 10,
    distance_m: float = 1000,
    attenuation_db_per_m: float = 1e-4,
    raw_fidelity: float = 0.85,
    classical_delay_s: float = 1e-4,
    stop_time_s: float = 0.1,
    formalism: str = DEFAULT_FORMALISM,
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
        formalism=formalism,
    )


def diamond_spec(*, stop_time_s: float = 0.2, formalism: str = DEFAULT_FORMALISM) -> NetworkTopologySpec:
    """Diamond topology with a fast-but-lossy direct route (`r1-bad-r3`) and
    a slower, near-lossless 3-hop detour (`r1-good1-good2-r3`) - the only
    topology in this project where `ShortestHopCountRouting`/
    `HighestFidelityRouting`/`LeastLossRouting` genuinely disagree (see
    `tests/integration/test_reconciliation.py`, which this mirrors so the
    H2 notebooks demonstrate the exact same, already-tested calibration
    rather than a new, unverified one).

    `bad`'s high attenuation (0.02 dB/m) makes it photon-loss-limited (slow
    to deliver `requested_pairs` in a short window) despite fine fidelity;
    `good1`/`good2`'s extra swap costs fidelity (two degradations instead of
    one) but delivers far more pairs per second.
    """
    return NetworkTopologySpec(
        nodes=[
            NodeSpec(id="r1", memories=20),
            NodeSpec(id="r3", memories=20),
            NodeSpec(id="bad", memories=20, raw_fidelity=DIAMOND_NODE_FIDELITY, swapping_degradation=DIAMOND_NODE_DEGRADATION),
            NodeSpec(id="good1", memories=20, raw_fidelity=DIAMOND_NODE_FIDELITY, swapping_degradation=DIAMOND_NODE_DEGRADATION),
            NodeSpec(id="good2", memories=20, raw_fidelity=DIAMOND_NODE_FIDELITY, swapping_degradation=DIAMOND_NODE_DEGRADATION),
        ],
        quantum_links=[
            QuantumLinkSpec(source="r1", destination="bad", distance_m=1000, attenuation_db_per_m=DIAMOND_BAD_ATTENUATION),
            QuantumLinkSpec(source="bad", destination="r3", distance_m=1000, attenuation_db_per_m=DIAMOND_BAD_ATTENUATION),
            QuantumLinkSpec(source="r1", destination="good1", distance_m=500, attenuation_db_per_m=DIAMOND_GOOD_ATTENUATION),
            QuantumLinkSpec(source="good1", destination="good2", distance_m=500, attenuation_db_per_m=DIAMOND_GOOD_ATTENUATION),
            QuantumLinkSpec(source="good2", destination="r3", distance_m=500, attenuation_db_per_m=DIAMOND_GOOD_ATTENUATION),
        ],
        classical_delay_s=1e-4,
        stop_time_s=stop_time_s,
        formalism=formalism,
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
    formalism: str = DEFAULT_FORMALISM,
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
        formalism=formalism,
    )


def star_spec(
    *,
    n_leaves: int = 4,
    leaf_memories: int = 10,
    center_memories: int = 80,
    distance_m: float = 1000,
    attenuation_db_per_m: float = 1e-5,
    raw_fidelity: float = 0.85,
    swapping_degradation: float = 0.95,
    classical_delay_s: float = 1e-4,
    stop_time_s: float = 0.1,
    formalism: str = DEFAULT_FORMALISM,
) -> NetworkTopologySpec:
    """One `center` repeater connected to `n_leaves` independent leaf
    routers (`leaf1`, `leaf2`, ...) - lets multiple intents on disjoint
    leaf pairs share `center` as an interior swap node, so notebook 18 can
    demonstrate that per-intent isolation holds even when a node is
    shared (just never as a source/destination - see
    `execution.sequence_executor.SequenceExecutor._check_no_node_conflict`)."""
    leaves = [f"leaf{i + 1}" for i in range(n_leaves)]
    return NetworkTopologySpec(
        nodes=[
            NodeSpec(id="center", memories=center_memories, raw_fidelity=raw_fidelity, swapping_degradation=swapping_degradation),
            *(NodeSpec(id=leaf, memories=leaf_memories, raw_fidelity=raw_fidelity) for leaf in leaves),
        ],
        quantum_links=[
            QuantumLinkSpec(source="center", destination=leaf, distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m)
            for leaf in leaves
        ],
        classical_delay_s=classical_delay_s,
        stop_time_s=stop_time_s,
        formalism=formalism,
    )
