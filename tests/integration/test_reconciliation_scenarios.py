"""Fase J6 end-to-end scenario tests: real, isolated two-episode
reconciliation runs demonstrating that each lever
(`assurance.reconciliation_policy`) actually recovers a genuinely
VIOLATED trial when applied - not just a policy-level recommendation
(see tests/unit/test_reconciliation_policy.py for those), but the full
`reconcile()`/`apply_reconciliation_decision` machinery exercised against
the real SeQUeNCe simulator. Parameters were found empirically (by
sweeping duration_s/reserved_memory_slots against real runs), not
derived from a closed-form model - consistent with this project's
"discover empirically" rule (see docs/reconciliation_scope.md).
"""
from __future__ import annotations

import pytest

from ibqn.assurance.evaluator import evaluate_intent
from ibqn.assurance.reconciliation import reconcile
from ibqn.assurance.reconciliation_policy import (
    DURATION_INCREASE,
    ROUTE_CHANGE,
    SLOT_INCREASE,
    apply_reconciliation_decision,
    decide_reconciliation_action,
)
from ibqn.assurance.telemetry import collect_intent_evidence
from ibqn.assurance.violations import classify_violations
from ibqn.demos.intents import diamond_intent, simple_intent
from ibqn.demos.topologies import diamond_spec, three_node_spec
from ibqn.execution.sequence_executor import SequenceExecutor
from ibqn.intent.models import IntentStatus, SuccessCondition
from ibqn.intent.repository import IntentRepository
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.sequence_adapter import SequenceAdapter
from ibqn.planning.planner import IntentPlanner
from ibqn.planning.routing import ShortestHopCountRouting


def _run_episode_1(topology_spec, intent, *, seed, routing_strategy=None):
    capabilities = NetworkCapabilities(topology_spec)
    planner = IntentPlanner(capabilities, routing_strategy=routing_strategy)
    plan = planner.plan(intent)
    assert plan.feasible

    repository = IntentRepository()
    adapter = SequenceAdapter(topology_spec, seed=seed)
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, plan)
    executor.run()
    assert repository.get(intent.id).lifecycle.status == IntentStatus.ACTIVE

    evidence = collect_intent_evidence(intent)
    evaluation = evaluate_intent(intent, evidence)
    final_status = IntentStatus.SATISFIED if evaluation.satisfied else IntentStatus.VIOLATED
    repository.transition(intent.id, final_status, "; ".join(evaluation.violations) or "satisfied", sim_time=0.0)
    return repository, plan, evaluation


@pytest.mark.unit
def test_recoverable_by_route_change():
    """Diamond topology, ShortestHopCountRouting picks the lossy 'bad'
    route - VIOLATED on delivered_pairs. The policy recommends switching
    routes, and doing so actually recovers the intent."""
    spec = diamond_spec()
    intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    repository, plan, evaluation = _run_episode_1(spec, intent, seed=0, routing_strategy=ShortestHopCountRouting())
    assert repository.get(intent.id).lifecycle.status == IntentStatus.VIOLATED

    violations = classify_violations(evaluation)
    capabilities = NetworkCapabilities(spec)
    decision = decide_reconciliation_action(
        violations, capabilities=capabilities, source=intent.endpoints.source, destination=intent.endpoints.destination,
        current_route=plan.route, current_reserved_memory_slots=intent.requirements.reserved_memory_slots,
        min_fidelity=intent.requirements.min_fidelity, allow_purification=intent.policy.allow_purification,
    )
    assert decision.action == ROUTE_CHANGE

    result = reconcile(
        intent, spec, repository, evaluation, seed=1,
        routing_strategy=decision.recommended_routing_strategy,
    )
    assert result.final_status == IntentStatus.SATISFIED
    assert result.new_plan.route != plan.route


@pytest.mark.unit
def test_recoverable_by_duration_increase():
    """Single-route topology, short reservation window - not enough
    elapsed time to deliver the declared goal. The policy recommends
    more time (no better route exists, slots are not scarce), and
    doubling duration actually recovers the intent."""
    spec = three_node_spec(attenuation_db_per_m=0.01, stop_time_s=0.3)
    intent = simple_intent(
        intent_id="dur-recon", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=10, min_delivered_pairs=30, start_time=0.01, duration=0.03,
        success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=30)],
    )

    repository, plan, evaluation = _run_episode_1(spec, intent, seed=0, routing_strategy=ShortestHopCountRouting())
    assert repository.get(intent.id).lifecycle.status == IntentStatus.VIOLATED

    violations = classify_violations(evaluation)
    capabilities = NetworkCapabilities(spec)
    decision = decide_reconciliation_action(
        violations, capabilities=capabilities, source=intent.endpoints.source, destination=intent.endpoints.destination,
        current_route=plan.route, current_reserved_memory_slots=intent.requirements.reserved_memory_slots,
        min_fidelity=intent.requirements.min_fidelity, allow_purification=intent.policy.allow_purification,
    )
    assert decision.action == DURATION_INCREASE

    adjusted_intent = apply_reconciliation_decision(intent, decision, duration_multiplier=2.0)
    assert adjusted_intent.requirements.duration_s == pytest.approx(0.06)

    result = reconcile(
        intent, spec, repository, evaluation, seed=1,
        routing_strategy=ShortestHopCountRouting(), intent_override=adjusted_intent,
    )
    assert result.final_status == IntentStatus.SATISFIED


@pytest.mark.unit
def test_recoverable_by_slot_increase():
    """Single-route topology, few reserved memory slots - throughput is
    memory-limited (few concurrent generation attempts). The policy
    recommends more slots (no better route exists, slots are scarce),
    and doubling slots actually recovers the intent."""
    spec = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.3, repeater_memories=40, end_memories=20)
    intent = simple_intent(
        intent_id="slot-recon", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=2, min_delivered_pairs=30, start_time=0.01, duration=0.02,
        success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=30)],
    )

    repository, plan, evaluation = _run_episode_1(spec, intent, seed=0, routing_strategy=ShortestHopCountRouting())
    assert repository.get(intent.id).lifecycle.status == IntentStatus.VIOLATED

    violations = classify_violations(evaluation)
    capabilities = NetworkCapabilities(spec)
    decision = decide_reconciliation_action(
        violations, capabilities=capabilities, source=intent.endpoints.source, destination=intent.endpoints.destination,
        current_route=plan.route, current_reserved_memory_slots=intent.requirements.reserved_memory_slots,
        min_fidelity=intent.requirements.min_fidelity, allow_purification=intent.policy.allow_purification,
    )
    assert decision.action == SLOT_INCREASE

    adjusted_intent = apply_reconciliation_decision(intent, decision, slot_multiplier=2.0)
    assert adjusted_intent.requirements.reserved_memory_slots == 4

    result = reconcile(
        intent, spec, repository, evaluation, seed=1,
        routing_strategy=ShortestHopCountRouting(), intent_override=adjusted_intent,
    )
    assert result.final_status == IntentStatus.SATISFIED
