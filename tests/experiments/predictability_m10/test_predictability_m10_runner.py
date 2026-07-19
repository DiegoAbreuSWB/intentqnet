"""Integration tests for `experiments.predictability_m10_runner.
execute_predictability_m10_trial` - same-seed reproducibility,
different-seed sensitivity, and non-interference with the frozen
`planner_study_runner`/`predictability_runner` (M9) execution paths.
Uses small, fast, non-marginal configurations only - the replay-
determinism campaign (P10) is the authoritative, larger-scale test.
"""
from __future__ import annotations

import pytest

from ibqn.demos.environment import collect_environment_info
from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.deterministic_context import DeterminismConfig
from ibqn.experiments.predictability_m10_runner import execute_predictability_m10_trial
from ibqn.experiments.records import TrialIdentity
from ibqn.planning.planners import ConservativeOneRoundPlanner, PlanningContext
from ibqn.planning.routing import ShortestHopCountRouting


def _run(seed: int, determinism: DeterminismConfig):
    topology = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
    intent = simple_intent(
        intent_id="t", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=10, min_delivered_pairs=5, start_time=0.01, duration=0.02,
    )
    identity = TrialIdentity(campaign="t", scenario="three_node", parameter_hash="x", strategy="L1", seed=seed, intent_id="t")
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    env = collect_environment_info()
    return execute_predictability_m10_trial(
        identity, intent, topology, ConservativeOneRoundPlanner(), context, env=env, determinism=determinism,
    )


@pytest.mark.unit
def test_same_seed_gives_same_trajectory_hash():
    record_a = _run(seed=3, determinism=DeterminismConfig(enabled=False))
    record_b = _run(seed=3, determinism=DeterminismConfig(enabled=False))
    assert record_a.trajectory_hash is not None
    assert record_a.trajectory_hash == record_b.trajectory_hash
    assert record_a.final_status == record_b.final_status
    assert record_a.delivered_pairs == record_b.delivered_pairs


@pytest.mark.unit
def test_different_seeds_can_produce_different_trajectories():
    """Not a strict requirement every pair of seeds differs (delivered
    pairs could coincidentally match), but across several seeds at least
    one pair must differ for this to be a meaningful stochastic axis at
    all - matches the M9 finding that seed affects delivered-pair COUNT."""
    hashes = {_run(seed=s, determinism=DeterminismConfig(enabled=False)).trajectory_hash for s in range(5)}
    assert len(hashes) > 1


@pytest.mark.unit
def test_determinism_enabled_still_reproducible_with_same_master_seed():
    config = DeterminismConfig(enabled=True, master_seed=99)
    record_a = _run(seed=3, determinism=config)
    record_b = _run(seed=3, determinism=config)
    assert record_a.trajectory_hash == record_b.trajectory_hash
    assert record_a.execution_seed_used == record_b.execution_seed_used


@pytest.mark.unit
def test_disabled_determinism_does_not_set_manifest_fields():
    record = _run(seed=3, determinism=DeterminismConfig(enabled=False))
    assert record.determinism_enabled is False
    assert record.master_seed is None
    assert record.execution_seed_used is None
    assert record.namespace_seeds_json is None


@pytest.mark.unit
def test_replay_index_produces_distinct_trial_ids():
    """Regression guard: `TrialIdentity.trial_id` (the shared, frozen
    schema P01-P02B/P03/M9 all use) has no concept of `replay_index` -
    naively reusing `identity.trial_id` verbatim collapses every replay
    of the same nominal trial onto one trial_id (found in P10's first
    real run: 144/160 rows collided). `trial_id` must always end with
    `:{replay_index}` so replays stay distinguishable and resumable."""
    record_0 = _run(seed=3, determinism=DeterminismConfig(enabled=False))
    from ibqn.experiments.predictability_m10_runner import execute_predictability_m10_trial

    topology = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
    intent = simple_intent(
        intent_id="t", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=10, min_delivered_pairs=5, start_time=0.01, duration=0.02,
    )
    identity = TrialIdentity(campaign="t", scenario="three_node", parameter_hash="x", strategy="L1", seed=3, intent_id="t")
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    env = collect_environment_info()
    record_1 = execute_predictability_m10_trial(
        identity, intent, topology, ConservativeOneRoundPlanner(), context, env=env,
        determinism=DeterminismConfig(enabled=False), replay_index=1,
    )
    assert record_0.trial_id != record_1.trial_id
    assert record_0.trial_id.endswith(":0")
    assert record_1.trial_id.endswith(":1")


@pytest.mark.unit
def test_m9_predictability_runner_unaffected_by_m10_module_existing():
    """M9's own execute_predictability_trial must still work exactly as
    before - this module's existence must not change its behavior."""
    from ibqn.experiments.predictability_runner import execute_predictability_trial

    topology = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
    intent = simple_intent(
        intent_id="t", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=10, min_delivered_pairs=5, start_time=0.01, duration=0.02,
    )
    identity = TrialIdentity(campaign="t", scenario="three_node", parameter_hash="x", strategy="L1", seed=0, intent_id="t")
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    record = execute_predictability_trial(
        identity, intent, topology, ConservativeOneRoundPlanner(), context, project_commit=None, sequence_commit=None,
    )
    assert record.final_status in ("SATISFIED", "VIOLATED")
