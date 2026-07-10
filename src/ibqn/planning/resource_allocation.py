"""Estimates how many memories a route needs at each node.

Mirrors `RSVPProtocol.schedule` (`sequence/network_management/rsvp.py`):
endpoints reserve `requested_pairs` memories, interior (swapping) nodes
reserve `requested_pairs * 2` (see docs/sequence_code_analysis.md, section 4.5).
"""
from __future__ import annotations

from ..network.capabilities import NetworkCapabilities
from .models import ResourceRequirement

INTERIOR_NODE_MULTIPLIER = 2


def required_memories_per_node(route: list[str], requested_pairs: int) -> dict[str, int]:
    """Returns `{node_id: memories_required}` for every node along `route`."""
    if len(route) < 2:
        raise ValueError(f"a route needs at least 2 nodes, got {route!r}")
    interior = set(route[1:-1])
    return {
        node_id: requested_pairs * INTERIOR_NODE_MULTIPLIER if node_id in interior else requested_pairs
        for node_id in route
    }


def build_reservations(
    route: list[str], requested_pairs: int, capabilities: NetworkCapabilities
) -> list[ResourceRequirement]:
    required = required_memories_per_node(route, requested_pairs)
    return [
        ResourceRequirement(
            node_id=node_id,
            memories_required=memories_required,
            memories_available=capabilities.node(node_id).memories,
        )
        for node_id, memories_required in required.items()
    ]
