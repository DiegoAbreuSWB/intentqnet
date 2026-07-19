"""Unit tests for the predictability-limits study's record schema/
persistence (M9) - a schema SEPARATE from `planner_study_records`
(P01-P02B's frozen schema, untouched)."""
from __future__ import annotations

from dataclasses import fields

import pytest

from ibqn.experiments.predictability_records import (
    PredictabilityTrialRecord,
    append_trial_record,
    read_trial_ids,
    trials_csv_path,
)
from ibqn.experiments.predictability_runner import RNG_RESEED_OFFSET


def _make_record(trial_id: str, final_status: str = "SATISFIED", timed_out: bool = False) -> PredictabilityTrialRecord:
    values = {f.name: None for f in fields(PredictabilityTrialRecord)}
    values.update(
        campaign="test", trial_id=trial_id, scenario="three_node", parameter_hash="x", seed=0,
        intent_id="t", planner_level="L1", planner_name="conservative_one_round",
        reserved_memory_slots=10, min_delivered_pairs=10, requested_fidelity=0.65, duration_s=0.05,
        attenuation_db_per_m=1e-5, route="a -> b", hop_count=1, feasible=True, rejection_reason=None,
        predicted_satisfaction_probability=None, predicted_delivered_pairs=None,
        predicted_average_fidelity=0.7, purification_rounds_estimate=0, planning_time_s=0.001,
        final_status=final_status, satisfied=(final_status == "SATISFIED"), delivered_pairs=10,
        average_fidelity=0.7, observed_fidelity=0.7, absolute_fidelity_error=0.0,
        simulation_wall_time_s=1.0, timed_out=timed_out,
        eg_attempts=100, eg_success=50, ep_attempts=None, ep_success=None, es_attempts=None, es_success=None,
        project_git_commit=None, sequence_git_commit=None, python_version="3.13.0", timestamp="2026-01-01T00:00:00",
    )
    return PredictabilityTrialRecord(**values)


@pytest.mark.unit
def test_record_fieldnames_match_dataclass_fields():
    assert PredictabilityTrialRecord.fieldnames() == [f.name for f in fields(PredictabilityTrialRecord)]


@pytest.mark.unit
def test_append_and_read_round_trip(tmp_path):
    path = trials_csv_path(tmp_path, "test_campaign")
    append_trial_record(path, _make_record("t1"))
    append_trial_record(path, _make_record("t2", final_status="TIMEOUT", timed_out=True))
    ids = read_trial_ids(path)
    assert ids == {"t1", "t2"}


@pytest.mark.unit
def test_timeout_row_is_marked_and_censored(tmp_path):
    path = trials_csv_path(tmp_path, "test_campaign")
    append_trial_record(path, _make_record("t1", final_status="TIMEOUT", timed_out=True))
    import csv

    with open(path, newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["final_status"] == "TIMEOUT"
    assert row["timed_out"] == "True"


@pytest.mark.unit
def test_read_trial_ids_empty_for_missing_file(tmp_path):
    assert read_trial_ids(tmp_path / "does_not_exist.csv") == set()


@pytest.mark.unit
def test_rng_reseed_offset_distinct_from_other_project_offsets():
    """Guards against collision with L4's INTERNAL_SEED_BASE_OFFSET
    (500_000_000) and reconciliation's RECONCILIATION_SEED_OFFSET
    (1_000_000) - see predictability_runner's module docstring."""
    from ibqn.planning.planners.l4_simulation import INTERNAL_SEED_BASE_OFFSET

    assert RNG_RESEED_OFFSET != INTERNAL_SEED_BASE_OFFSET
    assert RNG_RESEED_OFFSET > INTERNAL_SEED_BASE_OFFSET
