"""Tests for `ibqn.demos` - the reusable helpers backing the H1 "SeQUeNCe
basics" notebooks (topology builders, memory-lifecycle instrumentation,
environment introspection, table formatting).
"""
import pandas as pd
import pytest

from ibqn.demos.environment import collect_environment_info, run_smoke_test
from ibqn.demos.instrumentation import MemoryLifecycleRecorder
from ibqn.demos.tables import (
    delivered_pairs_table,
    evaluation_table,
    memory_transitions_table,
    plan_summary_table,
    reservations_table,
)
from ibqn.demos.topologies import three_node_spec, two_node_spec
from ibqn.assurance.evaluator import evaluate_intent
from ibqn.assurance.telemetry import collect_intent_evidence
from ibqn.execution.sequence_executor import SequenceExecutor
from ibqn.intent.models import (
    EntanglementIntent, IntentEndpoints, IntentRequirements, IntentValidation, SuccessCondition,
)
from ibqn.intent.repository import IntentRepository
from ibqn.network.sequence_adapter import SequenceAdapter
from ibqn.planning.models import ExecutionPlan
from ibqn.planning.planner import IntentPlanner
from ibqn.network.capabilities import NetworkCapabilities


def build_intent(source="a", destination="b", min_fidelity=0.6, requested_pairs=3) -> EntanglementIntent:
    return EntanglementIntent(
        id="intent-001",
        endpoints=IntentEndpoints(source=source, destination=destination),
        requirements=IntentRequirements(
            min_fidelity=min_fidelity, min_throughput=1, max_latency=1,
            requested_pairs=requested_pairs, start_time=0.02, duration=0.05,
        ),
        validation=IntentValidation(
            metrics=["delivered_pairs"],
            success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=requested_pairs)],
        ),
    )


@pytest.mark.unit
def test_two_node_spec_builds_expected_topology():
    spec = two_node_spec(memories=5)
    assert [n.id for n in spec.nodes] == ["a", "b"]
    assert spec.nodes[0].memories == 5
    assert len(spec.quantum_links) == 1


@pytest.mark.unit
def test_three_node_spec_builds_linear_chain_with_repeater():
    spec = three_node_spec(end_memories=4, repeater_memories=8)
    assert [n.id for n in spec.nodes] == ["a", "r", "b"]
    assert spec.nodes[1].memories == 8
    assert len(spec.quantum_links) == 2


@pytest.mark.unit
def test_collect_environment_info_reports_real_values():
    info = collect_environment_info()
    assert info.python_version.count(".") == 2
    assert info.sequence_version == "1.0.0"
    assert info.ibqn_version
    assert info.dependency_versions["pydantic"] != "NOT INSTALLED"


@pytest.mark.unit
def test_run_smoke_test_builds_and_runs_a_tiny_topology():
    result = run_smoke_test()
    assert result["routers_built"] == 2
    assert result["graph_nodes"] == 2
    assert result["graph_edges"] == 1


@pytest.mark.unit
def test_memory_lifecycle_recorder_captures_real_transitions_with_attribution():
    spec = three_node_spec(stop_time_s=0.1)
    adapter = SequenceAdapter(spec, seed=0)
    recorder = MemoryLifecycleRecorder(adapter.get_router("a"))

    intent = build_intent()
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)
    executor.submit(intent)
    executor.run()

    assert len(recorder.transitions) > 0
    # every transition must have a real, non-empty "responsible" label
    assert all(t.responsible for t in recorder.transitions)
    # the full 4-state machine must appear somewhere in a real run
    seen_states = {t.new_state for t in recorder.transitions}
    assert seen_states == {"RAW", "OCCUPIED", "ENTANGLED"} or seen_states == {"RAW", "OCCUPIED", "ENTANGLED", "PURIFIED"}
    # timestamps must be monotonically non-decreasing (recorded in event order)
    times = [t.sim_time_s for t in recorder.transitions]
    assert times == sorted(times)


@pytest.mark.unit
def test_memory_lifecycle_recorder_detach_restores_original_methods():
    """Bound methods accessed via the class descriptor are fresh wrapper
    objects on every access (`obj.method is obj.method` is False in normal
    Python), so identity is checked on the underlying `__func__` instead -
    the actual, meaningful notion of "is this still ResourceManager's own
    method"."""
    spec = two_node_spec()
    adapter = SequenceAdapter(spec, seed=0)
    router = adapter.get_router("a")
    original_update_func = router.resource_manager.update.__func__
    original_load_func = router.resource_manager.load.__func__

    recorder = MemoryLifecycleRecorder(router)
    assert router.resource_manager.update.__func__ is not original_update_func

    recorder.detach()
    assert router.resource_manager.update.__func__ is original_update_func
    assert router.resource_manager.load.__func__ is original_load_func


@pytest.mark.unit
def test_delivered_pairs_table_has_expected_columns_and_content():
    spec = three_node_spec(stop_time_s=0.1)
    adapter = SequenceAdapter(spec, seed=0)
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)
    intent = build_intent()
    executor.submit(intent)
    executor.run()

    evidence = collect_intent_evidence(intent)
    df = delivered_pairs_table(evidence)

    assert list(df.columns) == ["pair", "local_memory", "remote_memory", "delivery_time_s", "fidelity"]
    assert len(df) == len(evidence.delivered_pairs)
    assert len(df) > 0
    assert (df["remote_memory"] != "").all()


@pytest.mark.unit
def test_delivered_pairs_table_empty_evidence_has_correct_columns():
    from ibqn.assurance.telemetry import IntentEvidence

    df = delivered_pairs_table(IntentEvidence(intent_id="x"))
    assert list(df.columns) == ["pair", "local_memory", "remote_memory", "delivery_time_s", "fidelity"]
    assert len(df) == 0


@pytest.mark.unit
def test_plan_summary_and_reservations_tables():
    spec = three_node_spec(stop_time_s=0.1)
    capabilities = NetworkCapabilities(spec)
    planner = IntentPlanner(capabilities)
    intent = build_intent()

    plan = planner.plan(intent)
    summary = plan_summary_table(plan)
    reservations = reservations_table(plan)

    assert "field" in summary.columns and "value" in summary.columns
    assert set(reservations.columns) == {"node_id", "memories_required", "memories_available", "satisfied"}
    assert len(reservations) == len(plan.reservations)


@pytest.mark.unit
def test_evaluation_table_has_expected_columns():
    spec = three_node_spec(stop_time_s=0.1)
    adapter = SequenceAdapter(spec, seed=0)
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)
    intent = build_intent()
    executor.submit(intent)
    executor.run()

    evidence = collect_intent_evidence(intent)
    evaluation = evaluate_intent(intent, evidence)
    df = evaluation_table(evaluation)

    assert list(df.columns) == ["metric", "operator", "expected", "observed", "passed"]
    assert len(df) == len(evaluation.condition_results)
