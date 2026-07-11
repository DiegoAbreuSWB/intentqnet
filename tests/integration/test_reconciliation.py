"""Integration test for `assurance.reconciliation.reconcile`: a diamond
topology where the default routing strategy's choice is genuinely violated,
and reconciliation - on a brand-new episode (new `Timeline`/`SequenceAdapter`,
same `IntentRepository`) with a different routing strategy - reaches
SATISFIED (the "RECONCILED" case from the project brief).

Calibration notes (see docs/assurance_design.md for the full rationale):
- `bad` is a direct 2-hop route with high attenuation (0.02 dB/m): slow
  photon-loss-limited generation, but fidelity/memory are both fine, so the
  planner calls it feasible - it just cannot deliver `requested_pairs`
  within the short window.
- `good1`/`good2` form a 3-hop, near-lossless detour: more swaps (so a
  *lower* fidelity ceiling than `bad` - `min_fidelity` is kept low enough,
  0.6, that both routes clear it), but delivers far more pairs per second.
- `ShortestHopCountRouting` (the default) always prefers `bad` (fewer
  hops); `LeastLossRouting` prefers the low-loss detour despite more hops.
"""
import pytest
from sequence.utils import metrics

from ibqn.assurance.evaluator import evaluate_intent
from ibqn.assurance.reconciliation import reconcile
from ibqn.assurance.telemetry import collect_intent_evidence
from ibqn.execution.sequence_executor import SequenceExecutor
from ibqn.intent.models import (
    EntanglementIntent, IntentEndpoints, IntentRequirements, IntentStatus, IntentValidation, SuccessCondition,
)
from ibqn.intent.repository import IntentRepository
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.sequence_adapter import SequenceAdapter
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec
from ibqn.planning.planner import IntentPlanner
from ibqn.planning.routing import LeastLossRouting, ShortestHopCountRouting

BAD_ATTENUATION = 0.02
GOOD_ATTENUATION = 1e-5
NODE_FIDELITY = 0.9
NODE_DEGRADATION = 0.95


def diamond_spec(stop_time_s: float = 0.2) -> NetworkTopologySpec:
    return NetworkTopologySpec(
        nodes=[
            NodeSpec(id="r1", memories=20),
            NodeSpec(id="r3", memories=20),
            NodeSpec(id="bad", memories=20, raw_fidelity=NODE_FIDELITY, swapping_degradation=NODE_DEGRADATION),
            NodeSpec(id="good1", memories=20, raw_fidelity=NODE_FIDELITY, swapping_degradation=NODE_DEGRADATION),
            NodeSpec(id="good2", memories=20, raw_fidelity=NODE_FIDELITY, swapping_degradation=NODE_DEGRADATION),
        ],
        quantum_links=[
            QuantumLinkSpec(source="r1", destination="bad", distance_m=1000, attenuation_db_per_m=BAD_ATTENUATION),
            QuantumLinkSpec(source="bad", destination="r3", distance_m=1000, attenuation_db_per_m=BAD_ATTENUATION),
            QuantumLinkSpec(source="r1", destination="good1", distance_m=500, attenuation_db_per_m=GOOD_ATTENUATION),
            QuantumLinkSpec(source="good1", destination="good2", distance_m=500, attenuation_db_per_m=GOOD_ATTENUATION),
            QuantumLinkSpec(source="good2", destination="r3", distance_m=500, attenuation_db_per_m=GOOD_ATTENUATION),
        ],
        classical_delay_s=1e-4,
        stop_time_s=stop_time_s,
    )


def build_intent(requested_pairs=10, min_fidelity=0.6, start_time=0.02, duration=0.1) -> EntanglementIntent:
    return EntanglementIntent(
        id="intent-001",
        endpoints=IntentEndpoints(source="r1", destination="r3"),
        requirements=IntentRequirements(
            min_fidelity=min_fidelity, min_throughput=1, max_latency=1.0,
            requested_pairs=requested_pairs, start_time=start_time, duration=duration,
        ),
        validation=IntentValidation(
            metrics=["delivered_pairs"],
            success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=requested_pairs)],
        ),
    )


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics.configure()
    metrics.reset_metrics()
    yield


@pytest.mark.unit
def test_diamond_scenario_violated_then_reconciled():
    spec = diamond_spec()
    intent = build_intent()
    capabilities = NetworkCapabilities(spec)

    # --- episode 1: default routing picks the fast-but-lossy "bad" route ---
    planner = IntentPlanner(capabilities, routing_strategy=ShortestHopCountRouting())
    first_plan = planner.plan(intent)
    assert first_plan.feasible is True
    assert first_plan.route == ["r1", "bad", "r3"]

    adapter = SequenceAdapter(spec, seed=0)
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, first_plan)
    executor.run()

    assert repository.get("intent-001").lifecycle.status == IntentStatus.ACTIVE

    first_evidence = collect_intent_evidence(intent)
    first_evaluation = evaluate_intent(intent, first_evidence)
    assert first_evaluation.satisfied is False  # fewer than 10 pairs delivered in the window

    final_status = IntentStatus.VIOLATED
    repository.transition(intent.id, final_status, "; ".join(first_evaluation.violations), sim_time=adapter.get_timeline().now() / 1e12)
    assert repository.get("intent-001").lifecycle.status == IntentStatus.VIOLATED

    # --- episode 2: reconciliation, new Timeline, LeastLossRouting picks the detour ---
    reconciliation_result = reconcile(
        intent, spec, repository, first_evaluation,
        seed=1, routing_strategy=LeastLossRouting(),
    )

    assert reconciliation_result.new_plan.route == ["r1", "good1", "good2", "r3"]
    assert reconciliation_result.final_status == IntentStatus.SATISFIED
    assert reconciliation_result.new_evaluation is not None
    assert reconciliation_result.new_evaluation.satisfied is True
    assert repository.get("intent-001").lifecycle.status == IntentStatus.SATISFIED

    # the intent's history preserves the whole journey, across both episodes
    history_statuses = [t.to_status for t in repository.get("intent-001").lifecycle.history]
    assert history_statuses == [
        IntentStatus.RECEIVED, IntentStatus.VALIDATED, IntentStatus.PLANNING, IntentStatus.PLANNED,
        IntentStatus.DEPLOYING, IntentStatus.ACTIVE, IntentStatus.VIOLATED, IntentStatus.RECONCILING,
        IntentStatus.PLANNING, IntentStatus.PLANNED, IntentStatus.DEPLOYING, IntentStatus.ACTIVE,
        IntentStatus.SATISFIED,
    ]


@pytest.mark.unit
def test_reconciliation_with_no_reachable_alternative_reports_rejected():
    """If replanning finds no feasible route at all (here: the topology
    genuinely has none, `r1`/`r3` sit in disconnected components),
    reconciliation must report that plainly rather than crashing or
    silently leaving the intent in an inconsistent state."""
    disconnected_spec = NetworkTopologySpec(
        nodes=[
            NodeSpec(id="r1", memories=10),
            NodeSpec(id="isolated", memories=10),
            NodeSpec(id="r3", memories=10),
        ],
        quantum_links=[
            QuantumLinkSpec(source="isolated", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5),
        ],
        stop_time_s=0.1,
    )
    intent = build_intent(requested_pairs=1, duration=0.05)

    # manufacture a VIOLATED intent directly (as if a prior, unrelated
    # episode had run and failed), to isolate this test to reconcile()'s own
    # infeasible-replan handling rather than re-deriving a real violation
    repository = IntentRepository()
    repository.add(intent, sim_time=0.0)
    repository.transition(intent.id, IntentStatus.VALIDATED, "schema validated", sim_time=0.0)
    repository.transition(intent.id, IntentStatus.PLANNING, "invoking IntentPlanner", sim_time=0.0)
    repository.transition(intent.id, IntentStatus.PLANNED, "manufactured for this test", sim_time=0.0)
    repository.transition(intent.id, IntentStatus.DEPLOYING, "manufactured for this test", sim_time=0.0)
    repository.transition(intent.id, IntentStatus.ACTIVE, "manufactured for this test", sim_time=0.0)
    repository.transition(intent.id, IntentStatus.VIOLATED, "manufactured for this test", sim_time=0.0)

    fake_evaluation = evaluate_intent(intent, collect_intent_evidence(intent))
    assert fake_evaluation.satisfied is False  # no DELIVERY events at all recorded for this intent

    result = reconcile(intent, disconnected_spec, repository, fake_evaluation, seed=1)

    assert result.new_plan.feasible is False
    assert "no path found" in result.new_plan.infeasibility_reason
    assert result.new_evaluation is None
    assert result.final_status == IntentStatus.REJECTED
    assert repository.get(intent.id).lifecycle.status == IntentStatus.REJECTED
