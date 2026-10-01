"""Topologies for the calibrated ("realistic") campaign suite: the same
shapes the original catalog used (`experiments.topology_catalog`,
`demos.topologies`), rebuilt with literature-calibrated hardware
(`network.platforms`), metropolitan link lengths, and classical channels
that follow the fiber (docs/parameter_calibration.md).

Design choices shared by every builder:

- **Link length 5 km** by default - the scale of the deployed
  demonstrations (7.9-12.5 km node separations in Hefei, 10-15 km arms in
  Delft-The Hague, a 35 km loop in Boston) at which the baseline SiV
  platform still delivers ~10^2 end-to-end pairs/s in the simulator.
- **Few memories per node** (4 at endpoints, 8 at repeaters by default) -
  demonstrated nodes hold 1-2 qubits; a handful is the near-term
  multiplexing assumption, and the campaigns sweep it (`memory_size`).
- Node ids match the original builders (`a`/`r<i>`/`b`, `r1`/`bad`/
  `good1`/`good2`/`r3`, `a0..a3`/`b0..b3`, `center`/`leaf<i>`) so intents
  and analysis code carry over.
"""
from __future__ import annotations

from ..network.platforms import (
    DEFAULT_PLATFORM,
    DEPLOYED_FIBER_ATTENUATION_DB_PER_M,
    PlatformProfile,
    classical_delay_s,
)
from ..network.topology import DEFAULT_FORMALISM, NetworkTopologySpec, QuantumLinkSpec

DEFAULT_LINK_M = 5_000.0


def _spec(nodes, links: list[QuantumLinkSpec], platform: PlatformProfile, stop_time_s: float) -> NetworkTopologySpec:
    return NetworkTopologySpec(
        nodes=nodes, quantum_links=links,
        classical_delay_s=classical_delay_s(max(link.distance_m for link in links)),
        classical_delay_model="fiber", stop_time_s=stop_time_s,
        formalism=DEFAULT_FORMALISM, platform=platform.name,
    )


def realistic_chain(
    n_repeaters: int,
    *,
    platform: PlatformProfile = DEFAULT_PLATFORM,
    link_m: float = DEFAULT_LINK_M,
    end_memories: int = 4,
    repeater_memories: int = 8,
    stop_time_s: float = 0.5,
) -> NetworkTopologySpec:
    """Linear chain `a - r1 - ... - rN - b` with uniform hardware."""
    if n_repeaters < 0:
        raise ValueError(f"n_repeaters must be >= 0, got {n_repeaters}")
    node_ids = ["a"] + [f"r{i + 1}" for i in range(n_repeaters)] + ["b"]
    nodes = [
        platform.node(node_id, end_memories if node_id in ("a", "b") else repeater_memories)
        for node_id in node_ids
    ]
    links = [platform.link(node_ids[i], node_ids[i + 1], link_m) for i in range(len(node_ids) - 1)]
    return _spec(nodes, links, platform, stop_time_s)


def realistic_diamond(
    *,
    platform: PlatformProfile = DEFAULT_PLATFORM,
    direct_link_m: float = 20_000.0,
    direct_attenuation_db_per_m: float = DEPLOYED_FIBER_ATTENUATION_DB_PER_M,
    detour_link_m: float = DEFAULT_LINK_M,
    memories: int = 8,
    stop_time_s: float = 0.5,
) -> NetworkTopologySpec:
    """`r1` to `r3` over two physically different routes:

    - `r1 - bad - r3`: ONE repeater, but two long links over deployed fiber
      (20 km at 0.49 dB/km by default - the Boston loop's measured loss).
      Fewest hops and highest fidelity (a single swap), but slow: ~10 dB
      per link and a 100 us classical delay per negotiation.
    - `r1 - good1 - good2 - r3`: TWO repeaters over short low-loss links.
      Lower fidelity (two swaps) but an order of magnitude faster.

    The physical analogue of the original `demos.topologies.diamond_spec`
    (whose 20 dB/km vs 0.01 dB/km contrast had no experimental basis):
    hop-count and fidelity routing pick `bad`, loss-aware routing picks the
    detour."""
    nodes = [platform.node(node_id, memories) for node_id in ("r1", "r3", "bad", "good1", "good2")]
    links = [
        platform.link("r1", "bad", direct_link_m, attenuation_db_per_m=direct_attenuation_db_per_m),
        platform.link("bad", "r3", direct_link_m, attenuation_db_per_m=direct_attenuation_db_per_m),
        platform.link("r1", "good1", detour_link_m),
        platform.link("good1", "good2", detour_link_m),
        platform.link("good2", "r3", detour_link_m),
    ]
    return _spec(nodes, links, platform, stop_time_s)


def realistic_mesh(
    *,
    platform: PlatformProfile = DEFAULT_PLATFORM,
    link_m: float = DEFAULT_LINK_M,
    memories: int = 8,
    stop_time_s: float = 0.5,
) -> NetworkTopologySpec:
    """The 2x4 grid of `topology_catalog.small_mesh_spec` (`a0..a3` over
    `b0..b3`), uniform hardware and link length."""
    top = [f"a{i}" for i in range(4)]
    bottom = [f"b{i}" for i in range(4)]
    nodes = [platform.node(node_id, memories) for node_id in top + bottom]
    links = []
    for row in (top, bottom):
        links.extend(platform.link(row[i], row[i + 1], link_m) for i in range(len(row) - 1))
    links.extend(platform.link(a, b, link_m) for a, b in zip(top, bottom))
    return _spec(nodes, links, platform, stop_time_s)


def realistic_star(
    *,
    platform: PlatformProfile = DEFAULT_PLATFORM,
    n_leaves: int = 4,
    link_m: float = DEFAULT_LINK_M,
    leaf_memories: int = 4,
    center_memories: int = 16,
    stop_time_s: float = 0.5,
) -> NetworkTopologySpec:
    """One `center` repeater with `n_leaves` leaves - intents between
    disjoint leaf pairs share `center` as their swap node."""
    leaves = [f"leaf{i + 1}" for i in range(n_leaves)]
    nodes = [platform.node("center", center_memories)] + [platform.node(leaf, leaf_memories) for leaf in leaves]
    links = [platform.link("center", leaf, link_m) for leaf in leaves]
    return _spec(nodes, links, platform, stop_time_s)
