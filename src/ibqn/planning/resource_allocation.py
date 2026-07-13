"""Estimates how many memories a route needs at each node.

Mirrors `RSVPProtocol.schedule` (`sequence/network_management/rsvp.py`):
endpoints reserve `reserved_memory_slots` memories, interior (swapping)
nodes reserve `reserved_memory_slots * 2` (see
docs/sequence_code_analysis.md, section 4.5). `reserved_memory_slots` is a
RESOURCE size, not a delivery target - see
docs/intent_resource_semantics.md.
"""
from __future__ import annotations

from ..network.capabilities import NetworkCapabilities
from .models import ResourceRequirement

INTERIOR_NODE_MULTIPLIER = 2


def required_memories_per_node(route: list[str], reserved_memory_slots: int) -> dict[str, int]:
    """Returns `{node_id: memories_required}` for every node along `route`."""
    if len(route) < 2:
        raise ValueError(f"a route needs at least 2 nodes, got {route!r}")
    interior = set(route[1:-1])
    return {
        node_id: reserved_memory_slots * INTERIOR_NODE_MULTIPLIER if node_id in interior else reserved_memory_slots
        for node_id in route
    }


def build_reservations(
    route: list[str], reserved_memory_slots: int, capabilities: NetworkCapabilities
) -> list[ResourceRequirement]:
    required = required_memories_per_node(route, reserved_memory_slots)
    return [
        ResourceRequirement(
            node_id=node_id,
            memories_required=memories_required,
            memories_available=capabilities.node(node_id).memories,
        )
        for node_id, memories_required in required.items()
    ]
