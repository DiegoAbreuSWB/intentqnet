"""Tests for `ibqn.assurance.reconciliation_policy` (Fase J6) - see
docs/reconciliation_scope.md.
"""
from __future__ import annotations

import pytest

from ibqn.assurance.reconciliation_policy import (
    DURATION_INCREASE,
    NO_ACTION,
    ROUTE_CHANGE,
    SLOT_INCREASE,
    apply_reconciliation_decision,
    decide_reconciliation_action,
)
from ibqn.assurance.violations import Violation, ViolationCategory
from ibqn.demos.intents import simple_intent
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec


def _spec(nodes, links, stop_time_s=1.0) -> NetworkTopologySpec:
    return NetworkTopologySpec(nodes=nodes, quantum_links=links, stop_time_s=stop_time_s)


def _node(node_id, *, raw_fidelity=0.85, swapping_degradation=0.95, memories=10):
    return NodeSpec(id=node_id, memories=memories, raw_fidelity=raw_fidelity, swapping_degradation=swapping_degradation)


def _link(a, b, *, distance_m=1000, attenuation_db_per_m=1e-5):
    return QuantumLinkSpec(source=a, destination=b, distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m)


def _violation(category, *, metric="x", expected=1.0, observed=0.5):
    return Violation(intent_id="i1", metric=metric, category=category, operator=">=", expected=expected, observed=observed)


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


@pytest.mark.unit
def test_fidelity_violation_recommends_route_change_when_a_better_route_exists():
    capabilities = NetworkCapabilities(DIAMOND_LIKE)
    violations = [_violation(ViolationCategory.FIDELITY, metric="average_fidelity", expected=0.6)]

    decision = decide_reconciliation_action(
        violations, capabilities=capabilities, source="r1", destination="r3",
        current_route=["r1", "bad", "r3"], current_reserved_memory_slots=10,
        min_fidelity=0.6, allow_purification=True,
    )

    assert decision.action == ROUTE_CHANGE
    assert decision.recommended_routing_strategy is not None
    assert decision.constraints_checked


@pytest.mark.unit
def test_fidelity_violation_recommends_no_action_when_target_is_a_physical_ceiling():
    capabilities = NetworkCapabilities(DIAMOND_LIKE)
    # a target far above what even the best route + purification could reach
    violations = [_violation(ViolationCategory.FIDELITY, metric="average_fidelity", expected=0.9999)]

    decision = decide_reconciliation_action(
        violations, capabilities=capabilities, source="r1", destination="r3",
        current_route=["r1", "bad", "r3"], current_reserved_memory_slots=10,
        min_fidelity=0.9999, allow_purification=True,
    )

    assert decision.action == NO_ACTION
    assert decision.recommended_routing_strategy is None
    assert "physical fidelity ceiling" in decision.explanation


# --- THROUGHPUT/DELIVERED_PAIRS: route change vs. slot increase vs. duration increase ---

@pytest.mark.unit
def test_throughput_violation_recommends_route_change_when_a_lower_loss_route_exists():
    capabilities = NetworkCapabilities(DIAMOND_LIKE)
    violations = [_violation(ViolationCategory.DELIVERED_PAIRS, metric="delivered_pairs", expected=10, observed=4)]

    decision = decide_reconciliation_action(
        violations, capabilities=capabilities, source="r1", destination="r3",
        current_route=["r1", "bad", "r3"], current_reserved_memory_slots=10,
        min_fidelity=0.6, allow_purification=True,
    )

    assert decision.action == ROUTE_CHANGE
    assert decision.recommended_routing_strategy is not None


LINEAR_SINGLE_ROUTE = _spec(
    [_node("a", raw_fidelity=0.85), _node("r", raw_fidelity=0.85), _node("b", raw_fidelity=0.85)],
    [_link("a", "r"), _link("r", "b")],
)


@pytest.mark.unit
def test_throughput_violation_recommends_slot_increase_when_no_better_route_and_slots_are_low():
    capabilities = NetworkCapabilities(LINEAR_SINGLE_ROUTE)
    violations = [_violation(ViolationCategory.DELIVERED_PAIRS, metric="delivered_pairs", expected=30, observed=17)]

    decision = decide_reconciliation_action(
        violations, capabilities=capabilities, source="a", destination="b",
        current_route=["a", "r", "b"], current_reserved_memory_slots=2,  # below the low-slot threshold
        min_fidelity=0.6, allow_purification=True,
    )

    assert decision.action == SLOT_INCREASE
    assert decision.recommended_routing_strategy is None


@pytest.mark.unit
def test_throughput_violation_recommends_duration_increase_when_no_better_route_and_slots_are_adequate():
    capabilities = NetworkCapabilities(LINEAR_SINGLE_ROUTE)
    violations = [_violation(ViolationCategory.DELIVERED_PAIRS, metric="delivered_pairs", expected=30, observed=13)]

    decision = decide_reconciliation_action(
        violations, capabilities=capabilities, source="a", destination="b",
        current_route=["a", "r", "b"], current_reserved_memory_slots=10,  # well above the low-slot threshold
        min_fidelity=0.6, allow_purification=True,
    )

    assert decision.action == DURATION_INCREASE
    assert decision.recommended_routing_strategy is None


# --- unhandled violation categories ---

@pytest.mark.unit
def test_unhandled_violation_category_recommends_no_action():
    capabilities = NetworkCapabilities(LINEAR_SINGLE_ROUTE)
    violations = [_violation(ViolationCategory.COMPLETION_TIME, metric="completion_time", expected=1.0, observed=2.0)]

    decision = decide_reconciliation_action(
        violations, capabilities=capabilities, source="a", destination="b",
        current_route=["a", "r", "b"], current_reserved_memory_slots=10,
        min_fidelity=0.6, allow_purification=True,
    )

    assert decision.action == NO_ACTION
    assert "no corresponding lever" in decision.explanation


@pytest.mark.unit
def test_decide_reconciliation_action_requires_at_least_one_violation():
    capabilities = NetworkCapabilities(LINEAR_SINGLE_ROUTE)
    with pytest.raises(ValueError, match="at least one violation"):
        decide_reconciliation_action(
            [], capabilities=capabilities, source="a", destination="b",
            current_route=["a", "r", "b"], current_reserved_memory_slots=10,
            min_fidelity=0.6, allow_purification=True,
        )


# --- apply_reconciliation_decision ---

def _base_intent():
    return simple_intent(
        intent_id="i1", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=10, start_time=0.01, duration=0.05,
    )


@pytest.mark.unit
def test_apply_duration_increase_scales_duration_only():
    intent = _base_intent()
    decision = decide_reconciliation_action(
        [_violation(ViolationCategory.DELIVERED_PAIRS)],
        capabilities=NetworkCapabilities(LINEAR_SINGLE_ROUTE), source="a", destination="b",
        current_route=["a", "r", "b"], current_reserved_memory_slots=10, min_fidelity=0.6, allow_purification=True,
    )
    assert decision.action == DURATION_INCREASE

    adjusted = apply_reconciliation_decision(intent, decision, duration_multiplier=2.0)
    assert adjusted.requirements.duration_s == pytest.approx(intent.requirements.duration_s * 2)
    assert adjusted.requirements.reserved_memory_slots == intent.requirements.reserved_memory_slots
    assert adjusted.id == intent.id


@pytest.mark.unit
def test_apply_slot_increase_scales_slots_only():
    intent = _base_intent()
    decision = decide_reconciliation_action(
        [_violation(ViolationCategory.DELIVERED_PAIRS)],
        capabilities=NetworkCapabilities(LINEAR_SINGLE_ROUTE), source="a", destination="b",
        current_route=["a", "r", "b"], current_reserved_memory_slots=2, min_fidelity=0.6, allow_purification=True,
    )
    assert decision.action == SLOT_INCREASE

    adjusted = apply_reconciliation_decision(intent, decision, slot_multiplier=2.0)
    assert adjusted.requirements.reserved_memory_slots == intent.requirements.reserved_memory_slots * 2
    assert adjusted.requirements.duration_s == intent.requirements.duration_s


@pytest.mark.unit
def test_apply_route_change_or_no_action_leaves_intent_unchanged():
    intent = _base_intent()
    route_change_decision = decide_reconciliation_action(
        [_violation(ViolationCategory.FIDELITY, metric="average_fidelity", expected=0.6)],
        capabilities=NetworkCapabilities(DIAMOND_LIKE), source="r1", destination="r3",
        current_route=["r1", "bad", "r3"], current_reserved_memory_slots=10, min_fidelity=0.6, allow_purification=True,
    )
    assert route_change_decision.action == ROUTE_CHANGE
    assert apply_reconciliation_decision(intent, route_change_decision) == intent

    no_action_decision = decide_reconciliation_action(
        [_violation(ViolationCategory.COMPLETION_TIME, metric="completion_time")],
        capabilities=NetworkCapabilities(LINEAR_SINGLE_ROUTE), source="a", destination="b",
        current_route=["a", "r", "b"], current_reserved_memory_slots=10, min_fidelity=0.6, allow_purification=True,
    )
    assert no_action_decision.action == NO_ACTION
    assert apply_reconciliation_decision(intent, no_action_decision) == intent
