"""Estimates whether a candidate route can satisfy an intent's requirements,
using the same closed-form formulas SeQUeNCe's own protocols use at
simulation time - never an independently invented physics model (see
docs/sequence_code_analysis.md, section 2 constraints). Which formulas
those are depends on the topology's formalism and is encapsulated in
`ibqn.physics` (reached through `NetworkCapabilities.physics`, see
docs/physical_model.md).

Fase J1 note: the ORIGINAL claim here was that swap order never matters
because multiplication is associative - true for `ConservativeMinEstimator`
(a single scalar per hop), but FALSE for the real, per-node fidelity
assignment `SequenceConsistentEstimator` reproduces, where swap order
determines how many times each interior node's own `raw_fidelity`
contributes (see `planning.fidelity_estimation` and
docs/fidelity_estimation_model.md). Fidelity estimation itself is now
delegated to a `planning.fidelity_estimation.LinkFidelityEstimator`
(default `ConservativeMinEstimator`, preserving this module's original
behavior exactly); purification fidelity is delegated to a
`planning.purification.PurificationStrategy`, as before.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..intent.models import EntanglementIntent
from ..network.capabilities import NetworkCapabilities
from .fidelity_estimation import ConservativeMinEstimator, FidelityEstimate, LinkFidelityEstimator
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
    fidelity_estimate: FidelityEstimate | None = None
    """The full estimator output (Fase J1) - `swap_only_fidelity`/
    `hop_fidelities`/etc. above are convenience views over this, kept for
    backward compatibility with code written before estimators were
    pluggable."""


def estimate_swap_only_fidelity(capabilities: NetworkCapabilities, route: list[str]) -> tuple[float, list[float]]:
    """Returns `(end_to_end_fidelity, per_hop_fidelities)` for `route`,
    assuming no purification: the conservative `min(raw_a, raw_b)` hop
    model, combined left-to-right with the topology formalism's own swap
    formula (`ibqn.physics.PhysicsModel.swap_fidelity` - `f1*f2*degradation`
    under `ket_vector`, the Bell-diagonal gate/measurement-noise composition
    under `bell_diagonal`). Left-to-right is exact for the ket product and
    for ideal Bell-diagonal swaps (the Werner parameter simply multiplies);
    with imperfect gates the real bisection order matters slightly -
    `fidelity_estimation.SequenceConsistentEstimator` reproduces it."""
    if len(route) < 2:
        raise ValueError(f"route must have at least two nodes, got {route!r}")
    hop_fidelities = [capabilities.hop_fidelity(route[i], route[i + 1]) for i in range(len(route) - 1)]
    physics = capabilities.physics
    fidelity = hop_fidelities[0]
    for interior_node, next_hop in zip(route[1:-1], hop_fidelities[1:]):
        fidelity = physics.swap_fidelity(fidelity, next_hop, interior_node)
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
    fidelity_estimator: LinkFidelityEstimator | None = None,
) -> FeasibilityResult:
    """Evaluates one candidate `route` against `intent`'s requirements/policy.

    `fidelity_estimator` defaults to `ConservativeMinEstimator` - this
    function's behavior is byte-for-byte unchanged from before Fase J1
    unless a caller explicitly passes a different estimator (see
    `planning.fidelity_estimation`)."""
    estimator = fidelity_estimator or ConservativeMinEstimator()
    fidelity_estimate = estimator.estimate_path(
        route, capabilities, purification_strategy=purification_strategy,
        target_fidelity=intent.requirements.min_fidelity, allow_purification=intent.policy.allow_purification,
    )
    hop_fidelities = [min(a, b) for a, b in fidelity_estimate.per_link_endpoint_fidelities.values()]
    swap_only_fidelity = fidelity_estimate.pre_swap_fidelity

    reservations = build_reservations(route, intent.requirements.reserved_memory_slots, capabilities)
    memory_feasible = all(r.satisfied for r in reservations)
    memory_reason = "insufficient memory at: " + ", ".join(
        r.node_id for r in reservations if not r.satisfied
    )

    achieved_fidelity = fidelity_estimate.estimated_end_to_end_fidelity

    if achieved_fidelity >= intent.requirements.min_fidelity:
        feasible = memory_feasible
        reason = "" if feasible else memory_reason
    else:
        feasible = False
        reason = (
            f"min_fidelity {intent.requirements.min_fidelity:.3f} exceeds the achievable estimate "
            f"{achieved_fidelity:.3f} ({fidelity_estimate.purification_note})"
        )

    return FeasibilityResult(
        route=route, hop_fidelities=hop_fidelities, swap_only_fidelity=swap_only_fidelity,
        requires_purification=fidelity_estimate.purification_required,
        purified_fidelity_estimate=(
            fidelity_estimate.estimated_end_to_end_fidelity if fidelity_estimate.purification_required else None
        ),
        purification_rounds_estimate=fidelity_estimate.purification_rounds_estimate,
        memory_feasible=memory_feasible, feasible=feasible, reason=reason, reservations=reservations,
        fidelity_estimate=fidelity_estimate,
    )
