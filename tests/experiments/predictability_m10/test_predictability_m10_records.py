"""Unit tests for M10's record schema/persistence and `trajectory_hash`
(experiments.predictability_m10_records) - separate from
`planner_study_records`/`predictability_records` (frozen)."""
from __future__ import annotations

from dataclasses import fields

import pytest

from ibqn.experiments.predictability_m10_records import (
    PredictabilityM10TrialRecord,
    append_trial_record,
    compute_trajectory_hash,
    read_trial_ids,
    trials_csv_path,
)


def _make_record(trial_id: str, replay_index: int = 0, trajectory_hash: str | None = "h") -> PredictabilityM10TrialRecord:
    values = {f.name: None for f in fields(PredictabilityM10TrialRecord)}
    values.update(
        campaign="test", trial_id=trial_id, scenario="three_node", parameter_hash="x", seed=0, intent_id="t",
        planner_level="L1", planner_name="conservative_one_round", replay_index=replay_index,
        reserved_memory_slots=10, min_delivered_pairs=10, requested_fidelity=0.65, duration_s=0.05,
        attenuation_db_per_m=1e-5, distance_m=None, allow_purification=True, route="a -> b", hop_count=1,
        feasible=True, rejection_reason=None, predicted_satisfaction_probability=None, predicted_delivered_pairs=None,
        predicted_average_fidelity=0.7, purification_rounds_estimate=0, planning_time_s=0.001,
        final_status="SATISFIED", satisfied=True, delivered_pairs=10, average_fidelity=0.7, observed_fidelity=0.7,
        absolute_fidelity_error=0.0, simulation_wall_time_s=1.0, timed_out=False, timeout_s=60.0,
        eg_attempts=100, eg_success=50, ep_attempts=0, ep_success=0, es_attempts=0, es_success=0,
        timeline_end_time_s=0.05, trajectory_hash=trajectory_hash,
        determinism_enabled=False, master_seed=None, execution_seed_used=None, namespace_seeds_json=None,
        python_random_reseeded=False, python_hash_seed_env_value=None,
        project_git_commit=None, sequence_git_commit=None, python_version="3.13.0", numpy_version="2.0.0",
        dependency_versions_json=None, platform_system="Windows", platform_release="11", hostname="test",
        timestamp="2026-01-01T00:00:00",
    )
    return PredictabilityM10TrialRecord(**values)


@pytest.mark.unit
def test_record_fieldnames_match_dataclass_fields():
    assert PredictabilityM10TrialRecord.fieldnames() == [f.name for f in fields(PredictabilityM10TrialRecord)]


@pytest.mark.unit
def test_append_and_read_round_trip(tmp_path):
    path = trials_csv_path(tmp_path, "test_campaign")
    append_trial_record(path, _make_record("t1"))
    append_trial_record(path, _make_record("t2", replay_index=1))
    assert read_trial_ids(path) == {"t1", "t2"}


@pytest.mark.unit
def test_trajectory_hash_identical_for_identical_logical_inputs():
    h1 = compute_trajectory_hash(
        final_status="SATISFIED", delivered_pairs=10, average_fidelity=0.7, route="a -> b",
        eg_attempts=100, eg_success=50, ep_attempts=0, ep_success=0, es_attempts=0, es_success=0,
        timeline_end_time_s=0.05,
    )
    h2 = compute_trajectory_hash(
        final_status="SATISFIED", delivered_pairs=10, average_fidelity=0.7, route="a -> b",
        eg_attempts=100, eg_success=50, ep_attempts=0, ep_success=0, es_attempts=0, es_success=0,
        timeline_end_time_s=0.05,
    )
    assert h1 == h2


@pytest.mark.unit
def test_trajectory_hash_ignores_wall_clock_time():
    """Wall time is never part of the trajectory hash - two runs with the
    same logical outcome but different `simulation_wall_time_s` (not
    passed to compute_trajectory_hash at all) must hash identically."""
    import inspect

    signature = inspect.signature(compute_trajectory_hash)
    assert "simulation_wall_time_s" not in signature.parameters
    assert "wall_time" not in signature.parameters


@pytest.mark.unit
def test_trajectory_hash_differs_for_different_delivered_pairs():
    h1 = compute_trajectory_hash(
        final_status="SATISFIED", delivered_pairs=10, average_fidelity=0.7, route="a -> b",
        eg_attempts=100, eg_success=50, ep_attempts=0, ep_success=0, es_attempts=0, es_success=0,
        timeline_end_time_s=0.05,
    )
    h2 = compute_trajectory_hash(
        final_status="SATISFIED", delivered_pairs=11, average_fidelity=0.7, route="a -> b",
        eg_attempts=100, eg_success=50, ep_attempts=0, ep_success=0, es_attempts=0, es_success=0,
        timeline_end_time_s=0.05,
    )
    assert h1 != h2


@pytest.mark.unit
def test_trajectory_hash_tolerates_last_bit_float_noise():
    """Floats are rounded to 9 decimal digits before hashing - tolerates
    harmless floating-point representation noise without masking a real
    logical difference (see compute_trajectory_hash's docstring)."""
    h1 = compute_trajectory_hash(
        final_status="SATISFIED", delivered_pairs=10, average_fidelity=0.7000000001, route="a -> b",
        eg_attempts=100, eg_success=50, ep_attempts=0, ep_success=0, es_attempts=0, es_success=0,
        timeline_end_time_s=0.05,
    )
    h2 = compute_trajectory_hash(
        final_status="SATISFIED", delivered_pairs=10, average_fidelity=0.7000000002, route="a -> b",
        eg_attempts=100, eg_success=50, ep_attempts=0, ep_success=0, es_attempts=0, es_success=0,
        timeline_end_time_s=0.05,
    )
    assert h1 == h2


@pytest.mark.unit
def test_trajectory_hash_differs_for_different_final_status():
    h1 = compute_trajectory_hash(
        final_status="SATISFIED", delivered_pairs=10, average_fidelity=0.7, route="a -> b",
        eg_attempts=100, eg_success=50, ep_attempts=0, ep_success=0, es_attempts=0, es_success=0,
        timeline_end_time_s=0.05,
    )
    h2 = compute_trajectory_hash(
        final_status="VIOLATED", delivered_pairs=10, average_fidelity=0.7, route="a -> b",
        eg_attempts=100, eg_success=50, ep_attempts=0, ep_success=0, es_attempts=0, es_success=0,
        timeline_end_time_s=0.05,
    )
    assert h1 != h2
