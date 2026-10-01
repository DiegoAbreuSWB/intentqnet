"""Topology catalog (Fase J4, see docs/topology_catalog.md): every result
in this project through Fase H3 was demonstrated on at most two
topologies (the uniform `three_node_spec` and the heterogeneous
`demos.topologies.diamond_spec`). This module adds the remaining shapes
needed to check whether routing/purification/reconciliation findings
generalize, or were an artifact of those two specific topologies.

- T1/T4 - `linear_chain_spec(n_repeaters)`: a single parametric builder
  covers both "a linear chain" (T1, any fixed repeater count) and "a
  chain of variable length" (T4, sweep `n_repeaters` across 0-4) - the
  same shape, just a different repeater count each time.
- T2 - the existing `demos.topologies.diamond_spec` (heterogeneous,
  routing strategies genuinely diverge) - reused, not duplicated.
- T3 - `small_mesh_spec`: an 8-router 2x4 grid with multiple candidate
  paths between opposite corners, for testing planner scalability and
  strategy divergence beyond a single diamond.
- T5 - `near_equivalent_paths_spec`: two routes with deliberately close
  (not identical) cost, to check whether small physical differences
  produce large or small operational differences (decision stability).
"""
from __future__ import annotations

from ..network.topology import DEFAULT_FORMALISM, NetworkTopologySpec, NodeSpec, QuantumLinkSpec

DEFAULT_ATTENUATION_DB_PER_M = 1e-5
DEFAULT_DISTANCE_M = 1000.0
DEFAULT_RAW_FIDELITY = 0.85
DEFAULT_SWAPPING_DEGRADATION = 0.95


def linear_chain_spec(
    n_repeaters: int,
    *,
    end_memories: int = 10,
    repeater_memories: int = 20,
    distance_m: float = DEFAULT_DISTANCE_M,
    attenuation_db_per_m: float = DEFAULT_ATTENUATION_DB_PER_M,
    raw_fidelity: float = DEFAULT_RAW_FIDELITY,
    swapping_degradation: float = DEFAULT_SWAPPING_DEGRADATION,
    classical_delay_s: float = 1e-4,
    stop_time_s: float = 0.2,
    formalism: str = DEFAULT_FORMALISM,
) -> NetworkTopologySpec:
    """A linear chain `a - r1 - r2 - ... - rN - b` (T1: fixed `n_repeaters`,
    T4: sweep `n_repeaters` across [0, 1, 2, 3, 4]). `n_repeaters=0` is a
    direct 2-node link (no swap at all - the same shape
    `demos.topologies.two_node_spec` builds); `n_repeaters=1` matches
    `demos.topologies.three_node_spec`'s shape (uniform physical
    parameters throughout, unlike the heterogeneous diamond)."""
    if n_repeaters < 0:
        raise ValueError(f"n_repeaters must be >= 0, got {n_repeaters}")

    node_ids = ["a"] + [f"r{i + 1}" for i in range(n_repeaters)] + ["b"]
    nodes = [
        NodeSpec(
            id=node_id,
            memories=end_memories if node_id in ("a", "b") else repeater_memories,
            raw_fidelity=raw_fidelity,
            swapping_degradation=swapping_degradation,
        )
        for node_id in node_ids
    ]
    links = [
        QuantumLinkSpec(
            source=node_ids[i], destination=node_ids[i + 1],
            distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m,
        )
        for i in range(len(node_ids) - 1)
    ]
    return NetworkTopologySpec(
        nodes=nodes, quantum_links=links,
        classical_delay_s=classical_delay_s, stop_time_s=stop_time_s, formalism=formalism,
    )


def small_mesh_spec(
    *,
    memories: int = 20,
    distance_m: float = 500.0,
    attenuation_db_per_m: float = DEFAULT_ATTENUATION_DB_PER_M,
    raw_fidelity: float = DEFAULT_RAW_FIDELITY,
    swapping_degradation: float = DEFAULT_SWAPPING_DEGRADATION,
    classical_delay_s: float = 1e-4,
    stop_time_s: float = 0.2,
    formalism: str = DEFAULT_FORMALISM,
) -> NetworkTopologySpec:
    """An 8-router 2x4 grid (`a0-a3` top row, `b0-b3` bottom row), each
    router linked to its horizontal neighbor(s) and its vertical
    counterpart:

    ```text
    a0 - a1 - a2 - a3
    |    |    |    |
    b0 - b1 - b2 - b3
    ```

    Between opposite corners (e.g. `a0` to `b3`) there are multiple
    candidate simple paths of different lengths, letting
    `HighestFidelityRouting`/`LeastLossRouting`/`ShortestHopCountRouting`
    genuinely disagree at a larger scale than the diamond's single
    2-vs-3-hop choice, and exercising `IntentPlanner`'s path enumeration
    on a topology denser than a simple chain (see docs/limitations.md's
    note on `HighestFidelityRouting`'s scalability)."""
    top = [f"a{i}" for i in range(4)]
    bottom = [f"b{i}" for i in range(4)]
    node_ids = top + bottom
    nodes = [
        NodeSpec(id=node_id, memories=memories, raw_fidelity=raw_fidelity, swapping_degradation=swapping_degradation)
        for node_id in node_ids
    ]
    links = []
    for row in (top, bottom):
        for i in range(len(row) - 1):
            links.append(QuantumLinkSpec(
                source=row[i], destination=row[i + 1],
                distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m,
            ))
    for a, b in zip(top, bottom):
        links.append(QuantumLinkSpec(
            source=a, destination=b, distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m,
        ))
    return NetworkTopologySpec(
        nodes=nodes, quantum_links=links,
        classical_delay_s=classical_delay_s, stop_time_s=stop_time_s, formalism=formalism,
    )


def near_equivalent_paths_spec(
    *,
    memories: int = 20,
    end_memories: int = 10,
    distance_m: float = 500.0,
    attenuation_db_per_m: float = DEFAULT_ATTENUATION_DB_PER_M,
    cost_gap_fraction: float = 0.05,
    raw_fidelity: float = DEFAULT_RAW_FIDELITY,
    swapping_degradation: float = DEFAULT_SWAPPING_DEGRADATION,
    classical_delay_s: float = 1e-4,
    stop_time_s: float = 0.2,
    formalism: str = DEFAULT_FORMALISM,
) -> NetworkTopologySpec:
    """Two single-repeater routes (`source-mid_a-dest`,
    `source-mid_b-dest`) with deliberately CLOSE but not identical cost
    (`mid_b`'s attenuation is `cost_gap_fraction` higher than `mid_a`'s,
    5% by default) - unlike the diamond topology (section 6.2, T2, where
    `good1/good2` beats `bad` by orders of magnitude), this is a
    genuinely close call. Used to check ranking stability (J9): does a
    small, deliberate cost perturbation between two candidates flip the
    routing decision, and does that flip produce a large or small
    operational difference (see docs/topology_catalog.md)."""
    nodes = [
        NodeSpec(id="source", memories=end_memories, raw_fidelity=raw_fidelity),
        NodeSpec(id="dest", memories=end_memories, raw_fidelity=raw_fidelity),
        NodeSpec(id="mid_a", memories=memories, raw_fidelity=raw_fidelity, swapping_degradation=swapping_degradation),
        NodeSpec(id="mid_b", memories=memories, raw_fidelity=raw_fidelity, swapping_degradation=swapping_degradation),
    ]
    links = [
        QuantumLinkSpec(source="source", destination="mid_a", distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m),
        QuantumLinkSpec(source="mid_a", destination="dest", distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m),
        QuantumLinkSpec(source="source", destination="mid_b", distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m * (1 + cost_gap_fraction)),
        QuantumLinkSpec(source="mid_b", destination="dest", distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m * (1 + cost_gap_fraction)),
    ]
    return NetworkTopologySpec(
        nodes=nodes, quantum_links=links,
        classical_delay_s=classical_delay_s, stop_time_s=stop_time_s, formalism=formalism,
    )
