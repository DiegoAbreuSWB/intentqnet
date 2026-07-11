"""Tests for `ibqn.experiments.persistence` (Fase H3.2)."""
import pytest

from ibqn.experiments.persistence import (
    append_error_record,
    append_trial_record,
    errors_jsonl_path,
    read_errors,
    read_trial_ids,
    read_trials_dataframe,
    trials_csv_path,
)
from ibqn.experiments.records import TrialRecord


def _make_record(trial_id="C01:diamond:abc:x:0:intent-001", **overrides) -> TrialRecord:
    fields = dict(
        campaign="C01", trial_id=trial_id, scenario="diamond", parameter_hash="abc",
        seed=0, intent_id="intent-001", routing_strategy="shortest_hop_count",
        purification_policy="automatic", reconciliation_enabled=False,
        route="r1 -> bad -> r3", hop_count=2, requested_pairs=10, requested_fidelity=0.6, duration_s=0.1,
        attenuation_db_per_m=0.02, distance_m=1000.0, coherence_time_s=-1.0,
        accepted=True, satisfied=False, recovered=None, final_status="VIOLATED",
        delivered_pairs=4, excess_delivery_pairs=0, delivery_ratio=0.4,
        average_fidelity=0.6864, minimum_fidelity=0.6864,
        throughput_active_window=40.0, throughput_delivery_interval=200.0,
        first_pair_latency_s=0.02, completion_time_s=None,
        planning_time_s=0.001, simulation_wall_time_s=1.2,
        eg_attempts=100, eg_success=90, ep_attempts=0, ep_success=0, es_attempts=4, es_success=4,
        violations="delivered_pairs >= 10.0", error_type=None, error_message=None,
        project_git_commit="abc123", sequence_git_commit="def456",
        python_version="3.13.14", timestamp="2026-01-01T00:00:00+00:00",
    )
    fields.update(overrides)
    return TrialRecord(**fields)


@pytest.mark.unit
def test_read_trial_ids_on_missing_file_is_empty(tmp_path):
    assert read_trial_ids(trials_csv_path(tmp_path, "C01")) == set()


@pytest.mark.unit
def test_append_then_read_trial_ids(tmp_path):
    path = trials_csv_path(tmp_path, "C01")
    known = read_trial_ids(path)
    appended = append_trial_record(path, _make_record(), known_trial_ids=known)
    assert appended is True
    assert read_trial_ids(path) == {"C01:diamond:abc:x:0:intent-001"}


@pytest.mark.unit
def test_append_prevents_duplicate_trial_id(tmp_path):
    path = trials_csv_path(tmp_path, "C01")
    known = read_trial_ids(path)
    first = append_trial_record(path, _make_record(), known_trial_ids=known)
    second = append_trial_record(path, _make_record(delivered_pairs=999), known_trial_ids=known)
    assert first is True
    assert second is False

    df = read_trials_dataframe(path)
    assert len(df) == 1
    assert df.iloc[0]["delivered_pairs"] == 4  # the second (duplicate) write never happened


@pytest.mark.unit
def test_read_trials_dataframe_round_trips_values(tmp_path):
    path = trials_csv_path(tmp_path, "C01")
    known = read_trial_ids(path)
    append_trial_record(path, _make_record(), known_trial_ids=known)

    df = read_trials_dataframe(path)
    row = df.iloc[0]
    assert row["campaign"] == "C01"
    assert row["delivered_pairs"] == 4
    assert row["average_fidelity"] == pytest.approx(0.6864)
    assert bool(row["accepted"]) is True


@pytest.mark.unit
def test_read_trials_dataframe_on_missing_file_has_expected_columns(tmp_path):
    df = read_trials_dataframe(trials_csv_path(tmp_path, "does-not-exist"))
    assert list(df.columns) == TrialRecord.fieldnames()
    assert len(df) == 0


@pytest.mark.unit
def test_recovery_after_partial_last_line(tmp_path):
    """A process killed mid-write can leave a truncated final row - reading
    must not raise, and every earlier, complete row must still be usable."""
    path = trials_csv_path(tmp_path, "C01")
    known = read_trial_ids(path)
    append_trial_record(path, _make_record(trial_id="trial-1"), known_trial_ids=known)
    append_trial_record(path, _make_record(trial_id="trial-2"), known_trial_ids=known)

    with path.open("a", encoding="utf-8") as handle:
        handle.write("C01,trial-3,diamond,abc,0,intent-001,shortest_hop_count")  # no trailing newline, missing columns

    ids = read_trial_ids(path)  # must not raise
    assert {"trial-1", "trial-2"} <= ids

    df = read_trials_dataframe(path)  # must not raise
    assert len(df) == 3
    assert df.iloc[2]["delivered_pairs"] != df.iloc[2]["delivered_pairs"] or df.iloc[2]["campaign"] == "C01"  # nan or parsed


@pytest.mark.unit
def test_append_error_record_and_read_back(tmp_path):
    path = errors_jsonl_path(tmp_path, "C01")
    append_error_record(
        path, trial_id="t1", campaign="C01", scenario="diamond", parameter_hash="abc",
        strategy="x", seed=0, intent_id="intent-001", error_type="ValueError",
        error_message="boom", timestamp="2026-01-01T00:00:00+00:00",
    )
    append_error_record(
        path, trial_id="t2", campaign="C01", scenario="diamond", parameter_hash="abc",
        strategy="x", seed=1, intent_id="intent-001", error_type="RuntimeError",
        error_message="also boom", timestamp="2026-01-01T00:00:01+00:00",
    )
    errors = read_errors(path)
    assert len(errors) == 2
    assert errors[0]["error_type"] == "ValueError"
    assert errors[1]["trial_id"] == "t2"


@pytest.mark.unit
def test_read_errors_tolerates_truncated_last_line(tmp_path):
    path = errors_jsonl_path(tmp_path, "C01")
    append_error_record(
        path, trial_id="t1", campaign="C01", scenario="diamond", parameter_hash="abc",
        strategy="x", seed=0, intent_id="intent-001", error_type="ValueError",
        error_message="boom", timestamp="2026-01-01T00:00:00+00:00",
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"trial_id": "t2", "incompl')  # truncated JSON, no closing brace/newline

    errors = read_errors(path)  # must not raise
    assert len(errors) == 1
    assert errors[0]["trial_id"] == "t1"


@pytest.mark.unit
def test_read_errors_on_missing_file_is_empty(tmp_path):
    assert read_errors(errors_jsonl_path(tmp_path, "does-not-exist")) == []
