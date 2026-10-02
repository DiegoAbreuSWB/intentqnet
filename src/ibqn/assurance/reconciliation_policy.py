"""Reconciliation decision policy (Fase J6, see docs/reconciliation_scope.md).

Before this phase, `experiments.runner._reconciliation_routing_strategy_name`
was the only decision logic reconciliation had: always retry with a
different ROUTING strategy, regardless of what kind of violation
triggered reconciliation - documented as a known limitation ("this
planner version has no logic that picks a strategy from a violation's
category"). This module adds that logic: given the classified
`Violation`s from episode 1, `decide_reconciliation_action` picks among
three concrete levers (route change, reservation duration increase,
reserved memory slot increase) or concludes no lever is expected to help
(an explicit, checked judgment - not silence), producing a
`ReconciliationDecision` that documents *why*.

This is a heuristic, not a search: it inspects a small, fixed set of
physical facts (alternative routes' conservative fidelity/loss estimates)
and applies simple, explainable rules - consistent with this project's
existing planner (also a heuristic, not an optimizer, see
docs/architecture.md).

Only the levers the intent's `IntentPolicy` permits are ever chosen: a
route change needs `allow_rerouting`, and more slots or more time need
`max_resource_scale > 1` - the intent's slots and duration are a budget,
and by default a later episode may not exceed it. When the policy rules out
every lever that would help, the decision is `NO_ACTION`, and its
explanation says which permission was missing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..intent.models import EntanglementIntent, IntentPolicy
from ..network.capabilities import NetworkCapabilities
from ..planning.fidelity_estimation import ConservativeMinEstimator, LinkFidelityEstimator
from ..planning.purification import PurificationStrategy, PurifyUntilTarget
from ..planning.routing import HighestFidelityRouting, LeastLossRouting, RoutingStrategy, ShortestHopCountRouting
from .violations import Violation, ViolationCategory

ROUTE_CHANGE = "route_change"
DURATION_INCREASE = "duration_increase"
SLOT_INCREASE = "slot_increase"
NO_ACTION = "no_action"

_ALTERNATIVE_STRATEGIES: list[RoutingStrategy] = [LeastLossRouting(), HighestFidelityRouting(), ShortestHopCountRouting()]

# Below this many memories at the busiest node, entanglement-generation
# throughput is plausibly memory-limited (few concurrent attempts) rather
# than purely loss/duration-limited - a heuristic threshold, not derived
# from a closed-form model (see docs/reconciliation_scope.md).
_LOW_SLOT_THRESHOLD = 4


@dataclass(frozen=True)
class ReconciliationDecision:
    violation_type: ViolationCategory
    action: str
    expected_effect: str
    constraints_checked: list[str] = field(default_factory=list)
    explanation: str = ""
    recommended_routing_strategy: RoutingStrategy | None = None
    """Set only when `action == ROUTE_CHANGE` - the strategy whose
    candidate route this decision recommends, ready to pass directly to
    `reconcile(routing_strategy=...)`."""


def scaled_slots(slots: int, scale: float) -> int:
    """The most memory slots a budget of `slots` grows to under `scale`,
    never more than `slots * scale`."""
    return max(slots, math.floor(slots * scale + 1e-9))


def _best_alternative_route(
    capabilities: NetworkCapabilities, source: str, destination: str, current_route: list[str],
    *, fidelity_estimator: LinkFidelityEstimator, purification_strategy: PurificationStrategy,
    target_fidelity: float, allow_purification: bool,
) -> tuple[list[str] | None, float | None, RoutingStrategy | None]:
    """Returns `(route, estimated_fidelity, strategy)` for whichever
    alternative (non-`current_route`) candidate, across a fixed set of
    routing strategies, achieves the highest estimated fidelity -
    `(None, None, None)` if every strategy's top choice is
    `current_route` itself."""
    best_route, best_fidelity, best_strategy = None, None, None
    for strategy in _ALTERNATIVE_STRATEGIES:
        candidates = strategy.find_candidate_paths(capabilities, source, destination)
        for route in candidates:
            if route == current_route:
                continue
            estimate = fidelity_estimator.estimate_path(
                route, capabilities, purification_strategy=purification_strategy,
                target_fidelity=target_fidelity, allow_purification=allow_purification,
            )
            if best_fidelity is None or estimate.estimated_end_to_end_fidelity > best_fidelity:
                best_route, best_fidelity, best_strategy = route, estimate.estimated_end_to_end_fidelity, strategy
    return best_route, best_fidelity, best_strategy


def _route_loss_db(capabilities: NetworkCapabilities, route: list[str]) -> float:
    return sum(capabilities.link(route[i], route[i + 1]).loss_db for i in range(len(route) - 1))


def decide_reconciliation_action(
    violations: list[Violation],
    *,
    policy: IntentPolicy,
    capabilities: NetworkCapabilities,
    source: str,
    destination: str,
    current_route: list[str],
    current_reserved_memory_slots: int,
    min_fidelity: float,
    allow_purification: bool,
    fidelity_estimator: LinkFidelityEstimator | None = None,
    purification_strategy: PurificationStrategy | None = None,
) -> ReconciliationDecision:
    """Picks the action expected to address the FIRST (primary) violation
    in `violations` - reconciliation only attempts one lever per episode
    (see docs/assurance_design.md, section 11: no automatic multi-strategy
    search) - among the levers `policy` (the intent's `IntentPolicy`)
    permits."""
    if not violations:
        raise ValueError("decide_reconciliation_action requires at least one violation")

    fidelity_estimator = fidelity_estimator or ConservativeMinEstimator()
    purification_strategy = purification_strategy or PurifyUntilTarget()
    primary = violations[0]
    can_grow = policy.max_resource_scale > 1.0
    permissions = (f"policy: allow_rerouting={policy.allow_rerouting}, "
                   f"max_resource_scale={policy.max_resource_scale:g}")

    if primary.category == ViolationCategory.FIDELITY:
        checked = [permissions]
        if not policy.allow_rerouting:
            return ReconciliationDecision(
                violation_type=primary.category, action=NO_ACTION,
                expected_effect="the only lever for a fidelity violation, a route change, is not permitted",
                constraints_checked=checked,
                explanation="fidelity violation, but the intent's policy does not allow rerouting - no permitted lever remains",
            )
        alt_route, alt_fidelity, alt_strategy = _best_alternative_route(
            capabilities, source, destination, current_route,
            fidelity_estimator=fidelity_estimator, purification_strategy=purification_strategy,
            target_fidelity=min_fidelity, allow_purification=allow_purification,
        )
        checked.append(
            f"compared {fidelity_estimator.name} fidelity estimate of every alternative candidate route "
            f"(routing strategies: {[type(s).__name__ for s in _ALTERNATIVE_STRATEGIES]}) against min_fidelity={min_fidelity}",
        )
        if alt_route is not None and alt_fidelity is not None and alt_fidelity >= min_fidelity:
            return ReconciliationDecision(
                violation_type=primary.category, action=ROUTE_CHANGE,
                expected_effect=f"route {alt_route} estimated at {alt_fidelity:.4f} >= target {min_fidelity}",
                constraints_checked=checked,
                explanation=(
                    f"fidelity violation, and an alternative route achieves a higher estimated fidelity "
                    f"({alt_fidelity:.4f}) than the current route's own estimate would - switching routes is "
                    f"expected to help"
                ),
                recommended_routing_strategy=alt_strategy,
            )
        return ReconciliationDecision(
            violation_type=primary.category, action=NO_ACTION,
            expected_effect="no candidate route (with or without purification) is estimated to reach min_fidelity",
            constraints_checked=checked,
            explanation=(
                "fidelity violation, but no alternative route's estimate (with purification if allowed) reaches "
                "min_fidelity either - this is a physical fidelity ceiling this topology cannot satisfy for this "
                "intent, not a routing problem reconciliation can fix"
            ),
        )

    if primary.category in (ViolationCategory.THROUGHPUT, ViolationCategory.DELIVERED_PAIRS):
        checked = [permissions]
        current_loss_db = _route_loss_db(capabilities, current_route)
        if policy.allow_rerouting:
            alt_route = None
            alt_loss_db = None
            alt_strategy = None
            for strategy in _ALTERNATIVE_STRATEGIES:
                for route in strategy.find_candidate_paths(capabilities, source, destination):
                    if route == current_route:
                        continue
                    loss = _route_loss_db(capabilities, route)
                    if alt_loss_db is None or loss < alt_loss_db:
                        alt_route, alt_loss_db, alt_strategy = route, loss, strategy
            checked.append(f"compared cumulative optical loss (dB) of every alternative candidate route against the current route's {current_loss_db:.4f} dB")

            if alt_route is not None and alt_loss_db is not None and alt_loss_db < current_loss_db:
                return ReconciliationDecision(
                    violation_type=primary.category, action=ROUTE_CHANGE,
                    expected_effect=f"route {alt_route} has {alt_loss_db:.4f} dB cumulative loss, vs. current {current_loss_db:.4f} dB",
                    constraints_checked=checked,
                    explanation="throughput/delivery violation, and a lower-loss alternative route exists - expected to deliver more pairs per unit time",
                    recommended_routing_strategy=alt_strategy,
                )
        else:
            checked.append("rerouting not permitted by the intent's policy: alternative routes not considered")

        if not can_grow:
            return ReconciliationDecision(
                violation_type=primary.category, action=NO_ACTION,
                expected_effect="the remaining levers, more memory slots or more time, exceed the budget the intent grants",
                constraints_checked=checked,
                explanation=(
                    "throughput/delivery violation, no permitted lower-loss route, and the intent's policy does not "
                    "allow its resource budget to grow (max_resource_scale=1) - no permitted lever remains"
                ),
            )

        checked.append(f"checked reserved_memory_slots ({current_reserved_memory_slots}) against a low-slot heuristic threshold ({_LOW_SLOT_THRESHOLD})")
        if (current_reserved_memory_slots < _LOW_SLOT_THRESHOLD
                and scaled_slots(current_reserved_memory_slots, policy.max_resource_scale) > current_reserved_memory_slots):
            return ReconciliationDecision(
                violation_type=primary.category, action=SLOT_INCREASE,
                expected_effect=f"more reserved memory slots (currently {current_reserved_memory_slots}) allow more concurrent generation attempts",
                constraints_checked=checked,
                explanation="throughput/delivery violation, no lower-loss route exists, and the current slot count is low enough that memory availability plausibly bottlenecks concurrent generation attempts",
            )

        checked.append("no lower-loss route and no low-slot bottleneck found; assuming the shortfall is purely a matter of elapsed time")
        return ReconciliationDecision(
            violation_type=primary.category, action=DURATION_INCREASE,
            expected_effect="more time in the reservation window allows more pairs to be generated and delivered along the same route",
            constraints_checked=checked,
            explanation="throughput/delivery violation, the current route is already the best available by loss, and slots are not unusually scarce - the remaining lever is simply more time",
        )

    return ReconciliationDecision(
        violation_type=primary.category, action=NO_ACTION,
        expected_effect="no lever in this policy addresses this violation category",
        constraints_checked=[f"violation category {primary.category.value!r} is not handled by any rule in this policy"],
        explanation=f"violation category {primary.category.value!r} (metric={primary.metric!r}) has no corresponding lever in this heuristic - see docs/reconciliation_scope.md",
    )


def apply_reconciliation_decision(
    intent: EntanglementIntent, decision: ReconciliationDecision,
    *, duration_multiplier: float = 2.0, slot_multiplier: float = 2.0,
) -> EntanglementIntent:
    """Returns the intent `reconcile()`'s episode 2 should plan/deploy
    against, given `decision` (pass as `reconcile(..., intent_override=...)`).

    `ROUTE_CHANGE`/`NO_ACTION` return `intent` unchanged - the routing
    strategy itself is what changes for `ROUTE_CHANGE`
    (`decision.recommended_routing_strategy`, passed separately to
    `reconcile(routing_strategy=...)`), and `NO_ACTION` by definition
    applies no lever. `DURATION_INCREASE`/`SLOT_INCREASE` return a
    modified copy with `duration_s`/`reserved_memory_slots` scaled up by
    `duration_multiplier`/`slot_multiplier` (simple fixed factors, 2x by
    default, not a search over how much increase would suffice), capped at
    the intent's `policy.max_resource_scale`. Raises `ValueError` when the
    intent's policy leaves no room for the increase the decision asks for."""
    scale = intent.policy.max_resource_scale
    if decision.action == DURATION_INCREASE:
        factor = min(duration_multiplier, scale)
        if factor <= 1.0:
            raise ValueError(
                f"intent {intent.id!r} does not allow its reservation duration to grow "
                f"(policy.max_resource_scale={scale:g})"
            )
        new_requirements = intent.requirements.model_copy(update={"duration_s": intent.requirements.duration_s * factor})
        return intent.model_copy(update={"requirements": new_requirements})
    if decision.action == SLOT_INCREASE:
        slots = intent.requirements.reserved_memory_slots
        new_slots = scaled_slots(slots, min(slot_multiplier, scale))
        if new_slots <= slots:
            raise ValueError(
                f"intent {intent.id!r} does not allow its reserved memory slots ({slots}) to grow "
                f"(policy.max_resource_scale={scale:g})"
            )
        new_requirements = intent.requirements.model_copy(update={"reserved_memory_slots": new_slots})
        return intent.model_copy(update={"requirements": new_requirements})
    return intent


def check_within_budget(intent: EntanglementIntent, episode_intent: EntanglementIntent) -> None:
    """Raises `ValueError` if `episode_intent` (a later episode of `intent`)
    uses more memory slots or a longer window than `intent`'s policy
    allows."""
    scale = intent.policy.max_resource_scale
    declared, used = intent.requirements, episode_intent.requirements
    if used.reserved_memory_slots > scaled_slots(declared.reserved_memory_slots, scale):
        raise ValueError(
            f"episode of intent {intent.id!r} reserves {used.reserved_memory_slots} memory slots, more than its budget "
            f"of {declared.reserved_memory_slots} allows (policy.max_resource_scale={scale:g})"
        )
    if used.duration_s > declared.duration_s * scale * (1 + 1e-9):
        raise ValueError(
            f"episode of intent {intent.id!r} lasts {used.duration_s:g} s, longer than its budget of "
            f"{declared.duration_s:g} s allows (policy.max_resource_scale={scale:g})"
        )
