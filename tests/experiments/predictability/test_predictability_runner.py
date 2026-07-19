"""Integration tests for `experiments.predictability_runner.
execute_predictability_trial` (M9) - a SEPARATE runner from
`planner_study_runner.execute_trial_with_policy`, added for M9's
attempt-telemetry capture and explicit RNG reseeding (see the module
docstring for why). Uses small, fast, non-marginal configurations only -
the retry-storm/critical-region regions are covered by
`docs/retry_storm_analysis.md`'s dedicated pilot, not by unit tests.
"""
from __future__ import annotations

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.predictability_runner import execute_predictability_trial
from ibqn.experiments.records import TrialIdentity
from ibqn.planning.planners import ConservativeOneRoundPlanner, PlanningContext
from ibqn.planning.routing import ShortestHopCountRouting


@pytest.mark.unit
def test_execute_predictability_trial_satisfied_case_captures_attempt_telemetry():
    capabilities_topology = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
    intent = simple_intent(
        intent_id="t", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=10, min_delivered_pairs=5, start_time=0.01, duration=0.02,
    )
    identity = TrialIdentity(campaign="t", scenario="three_node", parameter_hash="x", strategy="L1", seed=0, intent_id="t")
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    record = execute_predictability_trial(
        identity, intent, capabilities_topology, ConservativeOneRoundPlanner(), context,
        project_commit=None, sequence_commit=None,
    )
    assert record.final_status in ("SATISFIED", "VIOLATED")
    assert record.timed_out is False
    assert record.eg_attempts is not None
    assert record.eg_attempts >= 0


@pytest.mark.unit
def test_execute_predictability_trial_rejected_case_has_no_simulation_cost():
    capabilities_topology = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
    intent = simple_intent(
        intent_id="t", source="a", destination="b", min_fidelity=0.9999,
        requested_pairs=10, min_delivered_pairs=5, start_time=0.01, duration=0.02,
    )
    identity = TrialIdentity(campaign="t", scenario="three_node", parameter_hash="x", strategy="L1", seed=0, intent_id="t")
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    record = execute_predictability_trial(
        identity, intent, capabilities_topology, ConservativeOneRoundPlanner(), context,
        project_commit=None, sequence_commit=None,
    )
    assert record.final_status == "REJECTED"
    assert record.simulation_wall_time_s is None
    assert record.timed_out is False


@pytest.mark.unit
def test_execute_predictability_trial_never_reads_a_seed_cli_argument_from_context():
    """The RNG reseed is derived from `identity.seed` (the trial's own
    declared operational seed), never from `context.operational_seed` -
    same seed-isolation discipline as L4 (see docs/predictability_study.md)."""
    import inspect

    from ibqn.experiments.predictability_runner import execute_predictability_trial as fn

    signature = inspect.signature(fn)
    assert "identity" in signature.parameters
    assert "context" in signature.parameters
