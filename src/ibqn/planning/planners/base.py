"""`IntentPlannerPolicy` - the common interface every planner level (L1-L5,
plus the hybrid) implements (planner study, M1, section 3).

Centralizes what every level would otherwise duplicate (section 3's
explicit list): candidate-path generation delegates to the SAME
`planning.routing.RoutingStrategy` the current `IntentPlanner` already
uses, and route feasibility/resource checks delegate to the existing
`planning.feasibility.evaluate_route` (which itself already composes
`planning.fidelity_estimation`/`planning.resource_allocation`). No planner
level below re-implements pathfinding, fidelity formulas, or memory
validation - see `docs/planner_levels.md`.
"""
from __future__ import annotations

from typing import Protocol

from ...intent.models import EntanglementIntent
from ...network.capabilities import NetworkCapabilities
from ..feasibility import FeasibilityResult, evaluate_route
from .models import CandidateEvaluation, PlannerDecision, PlanningContext


class IntentPlannerPolicy(Protocol):
    """One planner level's decision logic. `plan()` receives
    `candidate_paths` already generated (see `generate_candidate_paths`
    below) - it never generates its own, so swapping which `RoutingStrategy`
    is active never has to be duplicated per planner level."""

    name: str
    level: str

    def plan(
        self,
        intent: EntanglementIntent,
        network_state: NetworkCapabilities,
        candidate_paths: list[list[str]],
        context: PlanningContext,
    ) -> PlannerDecision: ...


def generate_candidate_paths(
    intent: EntanglementIntent, network_state: NetworkCapabilities, context: PlanningContext,
) -> list[list[str]]:
    """The ONE place candidate routes are generated for every planner level
    - delegates entirely to `context.routing_strategy`
    (`planning.routing.RoutingStrategy`), the same interface
    `planning.planner.IntentPlanner` already consumes. Called once by
    whatever orchestrates a planner-family comparison (a campaign trial, a
    notebook, a test) and the SAME list is handed to every policy under
    comparison, so no level can get a different candidate set than another
    for the same intent/topology/seed."""
    return context.routing_strategy.find_candidate_paths(
        network_state, intent.endpoints.source, intent.endpoints.destination, max_candidates=context.max_candidates,
    )


def evaluate_candidates(
    network_state: NetworkCapabilities,
    candidate_paths: list[list[str]],
    intent: EntanglementIntent,
    *,
    purification_strategy,
    fidelity_estimator,
) -> list[FeasibilityResult]:
    """Evaluates every candidate route via the existing
    `planning.feasibility.evaluate_route` - the exact function
    `planning.planner.IntentPlanner.plan()` uses internally - so no planner
    level re-derives fidelity/resource feasibility from scratch. Returns
    results in the same best-first order as `candidate_paths`."""
    return [
        evaluate_route(
            network_state, route, intent,
            purification_strategy=purification_strategy, fidelity_estimator=fidelity_estimator,
        )
        for route in candidate_paths
    ]


def to_candidate_evaluation(result: FeasibilityResult) -> CandidateEvaluation:
    """Adapts the existing `FeasibilityResult` (planning.feasibility) into
    the planner-family-agnostic `CandidateEvaluation` shape, without
    duplicating any of the fields it already carries."""
    predicted_fidelity = result.purified_fidelity_estimate if result.requires_purification else result.swap_only_fidelity
    return CandidateEvaluation(
        route=result.route, feasible=result.feasible, reason=result.reason,
        predicted_fidelity=predicted_fidelity, predicted_delivered_pairs=None,
        extra={"purification_rounds_estimate": result.purification_rounds_estimate},
    )
