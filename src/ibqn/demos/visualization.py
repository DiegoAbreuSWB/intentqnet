"""Draws a `NetworkTopologySpec`'s real graph (nodes/edges as declared, not
a hand-drawn diagram) via `networkx` + `matplotlib` - used by notebooks 12,
15, and 19 to show topologies and highlight the route a plan/episode
actually used.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import networkx as nx

from ..network.topology import NetworkTopologySpec


def _topology_graph(topology_spec: NetworkTopologySpec) -> nx.Graph:
    graph = nx.Graph()
    graph.add_nodes_from(node.id for node in topology_spec.nodes)
    for link in topology_spec.quantum_links:
        graph.add_edge(link.source, link.destination, distance_m=link.distance_m)
    return graph


def draw_topology(
    topology_spec: NetworkTopologySpec,
    *,
    highlight_route: list[str] | None = None,
    title: str = "",
    ax: plt.Axes | None = None,
    seed: int = 0,
) -> plt.Axes:
    """Draws every node/edge declared in `topology_spec`. If
    `highlight_route` is given, its edges/nodes are drawn in a distinct
    color - the route is always a real `ExecutionPlan.route`/episode route,
    never a hand-picked example."""
    graph = _topology_graph(topology_spec)
    if ax is None:
        _, ax = plt.subplots(figsize=(5, 4))

    layout = nx.spring_layout(graph, seed=seed)
    route_edges = set()
    route_nodes = set(highlight_route) if highlight_route else set()
    if highlight_route:
        route_edges = {
            frozenset({highlight_route[i], highlight_route[i + 1]}) for i in range(len(highlight_route) - 1)
        }

    edge_colors = [
        "#C44E52" if frozenset({u, v}) in route_edges else "#AAAAAA" for u, v in graph.edges()
    ]
    edge_widths = [2.5 if frozenset({u, v}) in route_edges else 1.0 for u, v in graph.edges()]
    node_colors = ["#C44E52" if node in route_nodes else "#4C72B0" for node in graph.nodes()]

    nx.draw_networkx_edges(graph, layout, ax=ax, edge_color=edge_colors, width=edge_widths)
    nx.draw_networkx_nodes(graph, layout, ax=ax, node_color=node_colors, node_size=600)
    nx.draw_networkx_labels(graph, layout, ax=ax, font_color="white", font_size=9)
    edge_labels = {(u, v): f"{data['distance_m']:.0f} m" for u, v, data in graph.edges(data=True)}
    nx.draw_networkx_edge_labels(graph, layout, ax=ax, edge_labels=edge_labels, font_size=7)

    ax.set_title(title or "Network topology")
    ax.axis("off")
    return ax
