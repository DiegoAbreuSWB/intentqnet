"""Forces a `SequenceAdapter`'s topology to actually route a reservation
along a planner-chosen route.

`RouterNetTopo._generate_forwarding_table` auto-populates every router's
static forwarding table with the *shortest-hop-count* Dijkstra path (see
docs/sequence_code_analysis.md, section 4.6). A route chosen by
`planning.routing.LeastLossRouting`/`HighestFidelityRouting` may differ from
that default - without overriding the forwarding table, `RSVPProtocol`
would silently route the reservation along whichever path SeQUeNCe's
default table points to, contradicting the plan. `ForwardingProtocol.push`
looks up the table fresh, by final destination, at every hop
(`sequence/network_management/forwarding.py`), so overriding is a matter of
setting, at each interior hop, "to reach the final destination, go to the
next node in the route".
"""
from __future__ import annotations

from ..network.sequence_adapter import SequenceAdapter


def apply_route(adapter: SequenceAdapter, route: list[str]) -> None:
    """Overrides the forwarding table along `route` so a reservation from
    `route[0]` to `route[-1]` actually traverses these exact hops."""
    destination = route[-1]
    for i in range(len(route) - 1):
        router = adapter.get_router(route[i])
        router.network_manager.routing_protocol.update_forwarding_rule(destination, route[i + 1])
