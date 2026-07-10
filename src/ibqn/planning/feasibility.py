"""Estimates whether a candidate route can satisfy an intent's requirements,
using the same closed-form formulas SeQUeNCe's own protocols use at
simulation time - never an independently invented physics model (see
docs/sequence_code_analysis.md, section 2 constraints).

Swap fidelity: `EntanglementSwappingA_Circuit.updated_fidelity`
(`sequence/entanglement_management/swapping/swapping_circuit.py`) is
`f1 * f2 * degradation`. Because multiplication is associative, the total
end-to-end fidelity of a linear route is `product(hop_fidelities) *
product(interior_degradations)` *regardless of swap order/tree shape* -
so this estimate is valid even though swap order itself is not
parametrizable in this version (see `planning.swapping`). Purification
fidelity is delegated to a `planning.purification.PurificationStrategy`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..intent.models import EntanglementIntent
from ..network.capabilities import NetworkCapabilities
from .purification import PurificationStrategy, PurifyUntilTarget
from .resource_allocation import build_reservations


@dataclass(frozen=True)
class FeasibilityResult:
    route: list[str]
    hop_fidelities: list[float]
    swap_only_fidelity: float
    requires_purification: bool
    purified_fidelity_estimate: float | None
    purification_rounds_estimate: int
    memory_feasible: bool
    feasible: bool
    reason: str = ""
    reservations: list = field(default_factory=list)


def estimate_swap_only_fidelity(capabilities: NetworkCapabilities, route: list[str]) -> tuple[float, list[float]]:
    """Returns `(end_to_end_fidelity, per_hop_fidelities)` for `route`,
    assuming no purification - see module docstring for the formula."""
    hop_fidelities = [capabilities.hop_fidelity(route[i], route[i + 1]) for i in range(len(route) - 1)]
    fidelity = 1.0
    for hop_fidelity in hop_fidelities:
        fidelity *= hop_fidelity
    for interior_node in route[1:-1]:
        fidelity *= capabilities.node(interior_node).swapping_degradation
    return fidelity, hop_fidelities


def estimate_latency_s(capabilities: NetworkCapabilities, route: list[str]) -> float:
    """Round-trip photon travel time along `route`, using
    `sequence.constants.SPEED_OF_LIGHT` (2e-4 m/ps, i.e. 2e8 m/s) - the same
    constant `QuantumChannel`/`ClassicalChannel` use to derive delay."""
    from sequence.constants import SPEED_OF_LIGHT  # meters per picosecond

    speed_m_per_s = SPEED_OF_LIGHT * 1e12
    total_distance_m = sum(
        capabilities.link(route[i], route[i + 1]).distance_m for i in range(len(route) - 1)
    )
    return 2 * total_distance_m / speed_m_per_s


def evaluate_route(
    capabilities: NetworkCapabilities,
    route: list[str],
    intent: EntanglementIntent,
    *,
    purification_strategy: PurificationStrategy = PurifyUntilTarget(),
) -> FeasibilityResult:
    """Evaluates one candidate `route` against `intent`'s requirements/policy."""
    swap_only_fidelity, hop_fidelities = estimate_swap_only_fidelity(capabilities, route)
    reservations = build_reservations(route, intent.requirements.requested_pairs, capabilities)
    memory_feasible = all(r.satisfied for r in reservations)
    memory_reason = "insufficient memory at: " + ", ".join(
        r.node_id for r in reservations if not r.satisfied
    )

    decision = purification_strategy.decide(
        swap_only_fidelity, intent.requirements.min_fidelity, intent.policy.allow_purification
    )
    achieved_fidelity = decision.fidelity_estimate

    if achieved_fidelity >= intent.requirements.min_fidelity:
        feasible = memory_feasible
        reason = "" if feasible else memory_reason
    else:
        feasible = False
        reason = (
            f"min_fidelity {intent.requirements.min_fidelity:.3f} exceeds the achievable estimate "
            f"{achieved_fidelity:.3f} ({decision.note})"
        )

    return FeasibilityResult(
        route=route, hop_fidelities=hop_fidelities, swap_only_fidelity=swap_only_fidelity,
        requires_purification=decision.attempt, purified_fidelity_estimate=decision.fidelity_estimate if decision.attempt else None,
        purification_rounds_estimate=decision.rounds_estimate,
        memory_feasible=memory_feasible, feasible=feasible, reason=reason, reservations=reservations,
    )
