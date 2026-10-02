"""Tests for `ibqn.assurance.reconciliation_policy` (Fase J6) - see
docs/reconciliation_scope.md.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ibqn.assurance.reconciliation import reconcile
from ibqn.assurance.reconciliation_policy import (
    DURATION_INCREASE,
    NO_ACTION,
    ROUTE_CHANGE,
    SLOT_INCREASE,
    apply_reconciliation_decision,
    check_within_budget,
    decide_reconciliation_action,
)
from ibqn.assurance.violations import Violation, ViolationCategory
from ibqn.demos.intents import simple_intent
from ibqn.intent.models import IntentPolicy
from ibqn.intent.repository import IntentRepository
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec

MAY_GROW = IntentPolicy(max_resource_scale=2.0)
"""A policy under which every lever is permitted (rerouting is allowed by default)."""


def _spec(nodes, links, stop_time_s=1.0) -> NetworkTopologySpec:
    return NetworkTopologySpec(nodes=nodes, quantum_links=links, stop_time_s=stop_time_s)


def _node(node_id, *, raw_fidelity=0.85, swapping_degradation=0.95, memories=10):
    return NodeSpec(id=node_id, memories=memories, raw_fidelity=raw_fidelity, swapping_degradation=swapping_degradation)


def _link(a, b, *, distance_m=1000, attenuation_db_per_m=1e-5):
    return QuantumLinkSpec(source=a, destination=b, distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m)


def _violation(category, *, metric="x", expected=1.0, observed=0.5):
    return Violation(intent_id="i1", metric=metric, category=category, operator=">=", expected=expected, observed=observed)


def _decide(violations, spec, *, policy=MAY_GROW, slots=10, route=None, source="a", destination="b", min_fidelity=0.6):
    return decide_reconciliation_action(
        violations, policy=policy, capabilities=NetworkCapabilities(spec), source=source, destination=destination,
        current_route=route or [source, "r", destination], current_reserved_memory_slots=slots,
        min_fidelity=min_fidelity, allow_purification=True,
    )


# --- FIDELITY: recoverable by route change vs. irrecoverable (fidelity ceiling) ---

DIAMOND_LIKE = _spec(
    [
        _node("r1", raw_fidelity=0.85), _node("r3", raw_fidelity=0.85),
        _node("bad", raw_fidelity=0.9, swapping_degradation=0.95),
        _node("good1", raw_fidelity=0.9, swapping_degradation=0.95),
        _node("good2", raw_fidelity=0.9, swapping_degradation=0.95),
    ],
    [
        # attenuation mirrors demos.topologies.diamond_spec's real calibration:
        # 'bad' is fast to plan but lossy, 'good1'/'good2' is a low-loss detour.
        _link("r1", "bad", attenuation_db_per_m=0.02), _link("bad", "r3", attenuation_db_per_m=0.02),
        _link("r1", "good1", attenuation_db_per_m=1e-5), _link("good1", "good2", attenuation_db_per_m=1e-5),
        _link("good2", "r3", attenuation_db_per_m=1e-5),
    ],
)
DIAMOND_ROUTE = dict(source="r1", destination="r3", route=["r1", "bad", "r3"])


@pytest.mark.unit
def test_fidelity_violation_recommends_route_change_when_a_better_route_exists():
    violations = [_violation(ViolationCategory.FIDELITY, metric="average_fidelity", expected=0.6)]
    decision = _decide(violations, DIAMOND_LIKE, **DIAMOND_ROUTE)

    assert decision.action == ROUTE_CHANGE
    assert decision.recommended_routing_strategy is not None
    assert decision.constraints_checked


@pytest.mark.unit
def test_fidelity_violation_recommends_no_action_when_target_is_a_physical_ceiling():
    # a target far above what even the best route + purification could reach
    violations = [_violation(ViolationCategory.FIDELITY, metric="average_fidelity", expected=0.9999)]
    decision = _decide(violations, DIAMOND_LIKE, min_fidelity=0.9999, **DIAMOND_ROUTE)

    assert decision.action == NO_ACTION
    assert decision.recommended_routing_strategy is None
    assert "physical fidelity ceiling" in decision.explanation


# --- THROUGHPUT/DELIVERED_PAIRS: route change vs. slot increase vs. duration increase ---

@pytest.mark.unit
def test_throughput_violation_recommends_route_change_when_a_lower_loss_route_exists():
    violations = [_violation(ViolationCategory.DELIVERED_PAIRS, metric="delivered_pairs", expected=10, observed=4)]
    decision = _decide(violations, DIAMOND_LIKE, **DIAMOND_ROUTE)

    assert decision.action == ROUTE_CHANGE
    assert decision.recommended_routing_strategy is not None


LINEAR_SINGLE_ROUTE = _spec(
    [_node("a", raw_fidelity=0.85), _node("r", raw_fidelity=0.85), _node("b", raw_fidelity=0.85)],
    [_link("a", "r"), _link("r", "b")],
)


@pytest.mark.unit
def test_throughput_violation_recommends_slot_increase_when_no_better_route_and_slots_are_low():
    violations = [_violation(ViolationCategory.DELIVERED_PAIRS, metric="delivered_pairs", expected=30, observed=17)]
    decision = _decide(violations, LINEAR_SINGLE_ROUTE, slots=2)  # below the low-slot threshold

    assert decision.action == SLOT_INCREASE
    assert decision.recommended_routing_strategy is None


@pytest.mark.unit
def test_throughput_violation_recommends_duration_increase_when_no_better_route_and_slots_are_adequate():
    violations = [_violation(ViolationCategory.DELIVERED_PAIRS, metric="delivered_pairs", expected=30, observed=13)]
    decision = _decide(violations, LINEAR_SINGLE_ROUTE, slots=10)  # well above the low-slot threshold

    assert decision.action == DURATION_INCREASE
    assert decision.recommended_routing_strategy is None


# --- the intent's policy bounds the levers ---

@pytest.mark.unit
def test_by_default_the_budget_cannot_grow():
    assert IntentPolicy().max_resource_scale == 1.0
    violations = [_violation(ViolationCategory.DELIVERED_PAIRS, metric="delivered_pairs", expected=30, observed=13)]
    for slots in (2, 10):  # would be a slot increase / a duration increase if the budget could grow
        decision = _decide(violations, LINEAR_SINGLE_ROUTE, policy=IntentPolicy(), slots=slots)
        assert decision.action == NO_ACTION
        assert "max_resource_scale=1" in decision.explanation


@pytest.mark.unit
def test_a_route_change_needs_permission_to_reroute():
    no_rerouting = IntentPolicy(allow_rerouting=False, max_resource_scale=2.0)
    delivery = [_violation(ViolationCategory.DELIVERED_PAIRS, metric="delivered_pairs", expected=10, observed=4)]
    # a lower-loss route exists, but the policy forbids moving there: the budget lever is used instead
    decision = _decide(delivery, DIAMOND_LIKE, policy=no_rerouting, **DIAMOND_ROUTE)
    assert decision.action == DURATION_INCREASE
    assert any("rerouting not permitted" in line for line in decision.constraints_checked)

    fidelity = [_violation(ViolationCategory.FIDELITY, metric="average_fidelity", expected=0.6)]
    decision = _decide(fidelity, DIAMOND_LIKE, policy=no_rerouting, **DIAMOND_ROUTE)
    assert decision.action == NO_ACTION
    assert "does not allow rerouting" in decision.explanation

    nothing_permitted = _decide(delivery, DIAMOND_LIKE, policy=IntentPolicy(allow_rerouting=False), **DIAMOND_ROUTE)
    assert nothing_permitted.action == NO_ACTION


@pytest.mark.unit
def test_a_slot_increase_needs_room_for_one_more_slot():
    # a scale of 1.2 cannot add a slot to a budget of 2 (2.4 -> 2), so the window grows instead
    violations = [_violation(ViolationCategory.DELIVERED_PAIRS, metric="delivered_pairs", expected=30, observed=17)]
    decision = _decide(violations, LINEAR_SINGLE_ROUTE, policy=IntentPolicy(max_resource_scale=1.2), slots=2)
    assert decision.action == DURATION_INCREASE


@pytest.mark.unit
def test_the_scale_must_be_at_least_one():
    with pytest.raises(ValidationError):
        IntentPolicy(max_resource_scale=0.5)


# --- unhandled violation categories ---

@pytest.mark.unit
def test_unhandled_violation_category_recommends_no_action():
    violations = [_violation(ViolationCategory.COMPLETION_TIME, metric="completion_time", expected=1.0, observed=2.0)]
    decision = _decide(violations, LINEAR_SINGLE_ROUTE)

    assert decision.action == NO_ACTION
    assert "no corresponding lever" in decision.explanation


@pytest.mark.unit
def test_decide_reconciliation_action_requires_at_least_one_violation():
    with pytest.raises(ValueError, match="at least one violation"):
        _decide([], LINEAR_SINGLE_ROUTE)


# --- apply_reconciliation_decision ---

def _base_intent(max_resource_scale=2.0, *, slots=10):
    return simple_intent(
        intent_id="i1", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=slots, start_time=0.01, duration=0.05, max_resource_scale=max_resource_scale,
    )


@pytest.mark.unit
def test_apply_duration_increase_scales_duration_only():
    intent = _base_intent()
    decision = _decide([_violation(ViolationCategory.DELIVERED_PAIRS)], LINEAR_SINGLE_ROUTE, slots=10)
    assert decision.action == DURATION_INCREASE

    adjusted = apply_reconciliation_decision(intent, decision, duration_multiplier=2.0)
    assert adjusted.requirements.duration_s == pytest.approx(intent.requirements.duration_s * 2)
    assert adjusted.requirements.reserved_memory_slots == intent.requirements.reserved_memory_slots
    assert adjusted.id == intent.id


@pytest.mark.unit
def test_apply_slot_increase_scales_slots_only():
    intent = _base_intent()
    decision = _decide([_violation(ViolationCategory.DELIVERED_PAIRS)], LINEAR_SINGLE_ROUTE, slots=2)
    assert decision.action == SLOT_INCREASE

    adjusted = apply_reconciliation_decision(intent, decision, slot_multiplier=2.0)
    assert adjusted.requirements.reserved_memory_slots == intent.requirements.reserved_memory_slots * 2
    assert adjusted.requirements.duration_s == intent.requirements.duration_s


@pytest.mark.unit
def test_apply_never_exceeds_the_budget_the_intent_allows():
    duration = _decide([_violation(ViolationCategory.DELIVERED_PAIRS)], LINEAR_SINGLE_ROUTE, slots=10)
    slots = _decide([_violation(ViolationCategory.DELIVERED_PAIRS)], LINEAR_SINGLE_ROUTE, slots=2)

    capped = _base_intent(max_resource_scale=1.5)
    assert apply_reconciliation_decision(capped, duration, duration_multiplier=2.0).requirements.duration_s == \
        pytest.approx(capped.requirements.duration_s * 1.5)
    five_slots = _base_intent(max_resource_scale=1.5, slots=5)
    assert apply_reconciliation_decision(five_slots, slots, slot_multiplier=2.0).requirements.reserved_memory_slots == 7

    fixed = _base_intent(max_resource_scale=1.0)
    for decision in (duration, slots):
        with pytest.raises(ValueError, match="does not allow"):
            apply_reconciliation_decision(fixed, decision)


@pytest.mark.unit
def test_apply_route_change_or_no_action_leaves_intent_unchanged():
    intent = _base_intent()
    route_change_decision = _decide(
        [_violation(ViolationCategory.FIDELITY, metric="average_fidelity", expected=0.6)], DIAMOND_LIKE, **DIAMOND_ROUTE,
    )
    assert route_change_decision.action == ROUTE_CHANGE
    assert apply_reconciliation_decision(intent, route_change_decision) == intent

    no_action_decision = _decide([_violation(ViolationCategory.COMPLETION_TIME, metric="completion_time")], LINEAR_SINGLE_ROUTE)
    assert no_action_decision.action == NO_ACTION
    assert apply_reconciliation_decision(intent, no_action_decision) == intent


@pytest.mark.unit
def test_an_episode_beyond_the_budget_is_refused_before_it_runs():
    intent = _base_intent(max_resource_scale=1.0, slots=4)
    larger = intent.model_copy(update={"requirements": intent.requirements.model_copy(update={"reserved_memory_slots": 8})})
    longer = intent.model_copy(update={"requirements": intent.requirements.model_copy(update={"duration_s": 0.1})})
    for episode in (larger, longer):
        with pytest.raises(ValueError, match="budget"):
            check_within_budget(intent, episode)
        # reconcile() checks before touching the repository or the simulator
        with pytest.raises(ValueError, match="budget"):
            reconcile(intent, LINEAR_SINGLE_ROUTE, IntentRepository(), trigger_evaluation=None, seed=0,
                      intent_override=episode)
    check_within_budget(_base_intent(max_resource_scale=2.0, slots=4), larger)  # within a doubled budget
