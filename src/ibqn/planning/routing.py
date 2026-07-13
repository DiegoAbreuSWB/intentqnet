"""Interchangeable routing strategies: given a `NetworkCapabilities` graph
and an endpoint pair, return candidate routes ranked best-first by the
strategy's own criterion. The planner (`planning.planner`) tries them in
order and keeps the rest as `ExecutionPlan.fallback_routes`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import networkx as nx

from ..network.capabilities import NetworkCapabilities
from .feasibility import estimate_swap_only_fidelity


class RoutingStrategy(ABC):
    @abstractmethod
    def find_candidate_paths(
        self, capabilities: NetworkCapabilities, source: str, destination: str, *, max_candidates: int = 3
    ) -> list[list[str]]:
        """Returns up to `max_candidates` routes from `source` to
        `destination`, best-first. Returns `[]` if no path exists."""


class ShortestHopCountRouting(RoutingStrategy):
    """Fewest quantum links, ignoring loss/fidelity/distance.

    Fase J3 correction: `RouterNetTopo._generate_forwarding_table` does
    NOT use unweighted Dijkstra - it weights each edge by the summed
    physical `distance_m` of its two BSM half-links
    (`router_net_topo.py:192-208`, `graph.add_weighted_edges_from(costs)`)
    and runs plain (distance-weighted) `dijkstra_path`. So SeQUeNCe's own
    auto-generated static routing table minimizes total DISTANCE, not hop
    count - this strategy's top choice only coincides with it when the
    fewest-hop route also happens to be the shortest-distance one.
    Confirmed empirically on the diamond topology
    (`experiments.baselines.run_native_sequence_baseline`,
    `tests/experiments/test_baselines.py`): the native forwarding table
    picks the 3-hop `good1`/`good2` detour (1500 m total) over the
    2-hop `bad` link (2000 m total), which this strategy would never
    choose since it ignores distance entirely. See docs/baselines.md."""

    def find_candidate_paths(self, capabilities, source, destination, *, max_candidates=3):
        return _k_shortest_paths(capabilities.graph(), source, destination, weight=None, k=max_candidates)


class LeastLossRouting(RoutingStrategy):
    """Minimizes cumulative optical loss (`distance_m * attenuation_db_per_m`
    summed over hops), which may prefer more hops over fewer if the shorter
    hop count runs through a much lossier link."""

    def find_candidate_paths(self, capabilities, source, destination, *, max_candidates=3):
        return _k_shortest_paths(capabilities.graph(), source, destination, weight="loss_db", k=max_candidates)


class HighestFidelityRouting(RoutingStrategy):
    """Maximizes the estimated end-to-end fidelity
    (`feasibility.estimate_swap_only_fidelity`) before purification. Not
    expressible as a single-edge-weight shortest-path problem (fidelity is a
    product over hops *and* an extra per-interior-node degradation factor),
    so this strategy enumerates simple paths directly - only tractable for
    the small/linear topologies this planner version targets (see
    docs/limitations.md)."""

    def __init__(self, *, max_simple_paths_considered: int = 50):
        self._max_simple_paths_considered = max_simple_paths_considered

    def find_candidate_paths(self, capabilities, source, destination, *, max_candidates=3):
        graph = capabilities.graph()
        if source not in graph or destination not in graph:
            return []
        try:
            candidates = []
            for i, path in enumerate(nx.all_simple_paths(graph, source, destination)):
                if i >= self._max_simple_paths_considered:
                    break
                candidates.append(path)
        except nx.NodeNotFound:
            return []
        candidates.sort(key=lambda path: estimate_swap_only_fidelity(capabilities, path)[0], reverse=True)
        return candidates[:max_candidates]


def _k_shortest_paths(graph: nx.Graph, source: str, destination: str, *, weight, k: int) -> list[list[str]]:
    if source not in graph or destination not in graph:
        return []
    try:
        paths = []
        for i, path in enumerate(nx.shortest_simple_paths(graph, source, destination, weight=weight)):
            if i >= k:
                break
            paths.append(path)
        return paths
    except nx.NetworkXNoPath:
        return []
