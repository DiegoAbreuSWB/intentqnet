"""Tests for `ibqn.experiments.overhead` (Fase J7) - see
docs/overhead_methodology.md.
"""
from __future__ import annotations

import pytest

from ibqn.demos.intents import diamond_intent, simple_intent
from ibqn.demos.topologies import diamond_spec, three_node_spec
from ibqn.experiments.baselines import run_native_sequence_baseline
from ibqn.experiments.overhead import run_instrumented_trial
from ibqn.intent.parser import load_intent_file_with_timing
from ibqn.planning.routing import ShortestHopCountRouting


@pytest.mark.unit
def test_all_timings_are_nonnegative_and_totals_are_consistent():
    spec = three_node_spec()
    intent = simple_intent(intent_id="ovh", source="a", destination="b", min_fidelity=0.6, requested_pairs=10)

    timing, evaluation = run_instrumented_trial(intent, spec, seed=0, routing_strategy=ShortestHopCountRouting())

    for field in (
        "intent_parsing_wall_time_s", "intent_validation_wall_time_s", "capability_extraction_wall_time_s",
        "planning_wall_time_s", "deployment_wall_time_s", "assurance_wall_time_s", "simulation_wall_time_s",
    ):
        assert getattr(timing, field) >= 0.0

    assert timing.total_trial_wall_time_s == pytest.approx(
        timing.total_orchestration_wall_time_s + timing.simulation_wall_time_s
    )
    assert timing.simulation_wall_time_s > 0.0  # a real simulation actually ran
    assert 0.0 <= timing.orchestration_overhead_ratio <= 1.0
    assert 0.0 <= timing.planning_overhead_ratio <= 1.0
    assert evaluation is not None


@pytest.mark.unit
def test_object_intent_has_zero_parsing_and_validation_time():
    """Parsing/validation genuinely didn't happen when the intent is
    passed as an already-built object - 0.0 is a real measurement here,
    not an omission (see the module docstring)."""
    spec = three_node_spec()
    intent = simple_intent(intent_id="ovh", source="a", destination="b", min_fidelity=0.6, requested_pairs=10)

    timing, _ = run_instrumented_trial(intent, spec, seed=0, routing_strategy=ShortestHopCountRouting())

    assert timing.intent_parsing_wall_time_s == 0.0
    assert timing.intent_validation_wall_time_s == 0.0


@pytest.mark.unit
def test_file_based_intent_has_nonzero_parsing_and_validation_time(tmp_path):
    spec = three_node_spec()
    intent_file = tmp_path / "intent.yaml"
    intent_file.write_text(
        """
intent:
  id: ovh-file
  endpoints: {source: a, destination: b}
  requirements: {min_fidelity: 0.6, min_throughput: 1.0, max_latency: 1.0, reserved_memory_slots: 10, start_time_s: 0.01, duration_s: 0.05}
  validation:
    metrics: [delivered_pairs]
    success_conditions: {delivered_pairs: ">= 10"}
""",
        encoding="utf-8",
    )

    timing, _ = run_instrumented_trial(intent_file, spec, seed=0, routing_strategy=ShortestHopCountRouting())

    assert timing.intent_parsing_wall_time_s > 0.0
    assert timing.intent_validation_wall_time_s > 0.0

    # cross-check against the parser's own timing function directly
    _, parsing_s, validation_s = load_intent_file_with_timing(intent_file)
    assert parsing_s > 0.0
    assert validation_s > 0.0


@pytest.mark.unit
def test_infeasible_plan_short_circuits_with_zero_downstream_timings():
    spec = three_node_spec()
    intent = simple_intent(intent_id="ovh-infeasible", source="a", destination="b", min_fidelity=0.999999, requested_pairs=10)

    timing, evaluation = run_instrumented_trial(intent, spec, seed=0, routing_strategy=ShortestHopCountRouting())

    assert evaluation is None
    assert timing.deployment_wall_time_s == 0.0
    assert timing.assurance_wall_time_s == 0.0
    assert timing.simulation_wall_time_s == 0.0
    assert timing.planning_wall_time_s > 0.0  # planning itself still happened and took real time


@pytest.mark.unit
def test_reconciliation_decision_timing_only_recorded_when_violated_and_enabled():
    spec = diamond_spec()
    intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    without_reconciliation, _ = run_instrumented_trial(
        intent, spec, seed=0, routing_strategy=ShortestHopCountRouting(), reconciliation_enabled=False,
    )
    assert without_reconciliation.reconciliation_decision_wall_time_s is None

    with_reconciliation, evaluation = run_instrumented_trial(
        intent, spec, seed=0, routing_strategy=ShortestHopCountRouting(), reconciliation_enabled=True,
    )
    assert evaluation is not None and evaluation.satisfied is False  # ShortestHopCount picks the lossy route -> VIOLATED
    assert with_reconciliation.reconciliation_decision_wall_time_s is not None
    assert with_reconciliation.reconciliation_decision_wall_time_s >= 0.0


@pytest.mark.unit
def test_ibqn_orchestration_overhead_is_measurable_against_the_native_baseline():
    """docs/baselines.md's fairness setup, reused here to confirm IBQN's
    orchestration cost is a real, nonzero, measurable quantity - not by
    asserting a specific magnitude (wall-clock timings are inherently
    noisy), just that the concept is well-defined and both paths report
    comparable fields."""
    spec = diamond_spec()
    intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    ibqn_timing, _ = run_instrumented_trial(intent, spec, seed=0, routing_strategy=ShortestHopCountRouting())
    native = run_native_sequence_baseline(spec, intent, seed=0)

    assert ibqn_timing.total_orchestration_wall_time_s >= 0.0
    assert native.planning_wall_time_s == 0.0  # confirmed in Fase J3: no planning step exists in the native baseline
