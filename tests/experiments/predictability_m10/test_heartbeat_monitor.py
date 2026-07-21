"""Unit tests for M10.8's tail-event instrumentation
(experiments.heartbeat_monitor) - heartbeat sampling and termination-
reason classification (section 13's exact vocabulary: TIMEOUT,
NO_PROGRESS, MAX_RETRIES, SIMULATION_COMPLETE, ERROR)."""
from __future__ import annotations

import json

import pytest

from ibqn.experiments.heartbeat_monitor import classify_termination, read_heartbeats


def _write_heartbeats(path, samples):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")


@pytest.mark.unit
def test_read_heartbeats_empty_for_missing_file(tmp_path):
    assert read_heartbeats(tmp_path / "missing.jsonl") == []


@pytest.mark.unit
def test_read_heartbeats_tolerates_a_partial_last_line(tmp_path):
    """A process killed mid-write can leave a truncated final JSON line -
    must not crash the reader, just skip it."""
    path = tmp_path / "hb.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"wall_elapsed_s": 1.0, "sim_time_s": 0.1, "run_counter": 10, "pending_events": 2}) + "\n")
        f.write('{"wall_elapsed_s": 2.0, "sim_time_s"')  # truncated, no trailing newline
    samples = read_heartbeats(path)
    assert len(samples) == 1


@pytest.mark.unit
def test_classify_termination_simulation_error():
    assert classify_termination("does_not_matter.jsonl", final_status="SIMULATION_ERROR", timed_out=False) == "ERROR"


@pytest.mark.unit
def test_classify_termination_simulation_complete(tmp_path):
    path = tmp_path / "hb.jsonl"
    _write_heartbeats(path, [{"wall_elapsed_s": 1.0, "sim_time_s": 0.1, "run_counter": 10, "pending_events": 0}])
    assert classify_termination(path, final_status="SATISFIED", timed_out=False) == "SIMULATION_COMPLETE"


@pytest.mark.unit
def test_classify_termination_timeout_with_progressing_run_counter(tmp_path):
    """Sim time / run_counter kept increasing right up to the kill - a
    legitimate high-event-count tail scenario, not a stuck loop."""
    path = tmp_path / "hb.jsonl"
    _write_heartbeats(path, [
        {"wall_elapsed_s": 2.0, "sim_time_s": 0.01, "run_counter": 100, "pending_events": 5},
        {"wall_elapsed_s": 4.0, "sim_time_s": 0.02, "run_counter": 500, "pending_events": 8},
        {"wall_elapsed_s": 6.0, "sim_time_s": 0.03, "run_counter": 1200, "pending_events": 12},
    ])
    assert classify_termination(path, final_status="TIMEOUT", timed_out=True) == "TIMEOUT"


@pytest.mark.unit
def test_classify_termination_no_progress_when_run_counter_stalls(tmp_path):
    """run_counter unchanged across the last several heartbeats before
    the kill - a genuine stuck/pathological condition, not real work."""
    path = tmp_path / "hb.jsonl"
    _write_heartbeats(path, [
        {"wall_elapsed_s": 2.0, "sim_time_s": 0.01, "run_counter": 100, "pending_events": 5},
        {"wall_elapsed_s": 4.0, "sim_time_s": 0.01, "run_counter": 500, "pending_events": 5},
        {"wall_elapsed_s": 6.0, "sim_time_s": 0.01, "run_counter": 500, "pending_events": 5},
        {"wall_elapsed_s": 8.0, "sim_time_s": 0.01, "run_counter": 500, "pending_events": 5},
    ])
    assert classify_termination(path, final_status="TIMEOUT", timed_out=True) == "NO_PROGRESS"


@pytest.mark.unit
def test_classify_termination_max_retries_when_event_limit_flagged(tmp_path):
    path = tmp_path / "hb.jsonl"
    _write_heartbeats(path, [
        {"wall_elapsed_s": 2.0, "sim_time_s": 0.01, "run_counter": 100, "pending_events": 5, "event_limit_exceeded": False},
        {"wall_elapsed_s": 4.0, "sim_time_s": 0.02, "run_counter": 6_000_000, "pending_events": 500, "event_limit_exceeded": True},
    ])
    assert classify_termination(path, final_status="TIMEOUT", timed_out=True) == "MAX_RETRIES"


@pytest.mark.unit
def test_classify_termination_timeout_with_no_heartbeats_at_all(tmp_path):
    """A cap so tight the process was killed before even the first
    heartbeat interval elapsed - correctly defaults to TIMEOUT, not
    NO_PROGRESS (there is no evidence of a stall, only an absence of data)."""
    path = tmp_path / "hb.jsonl"
    assert classify_termination(path, final_status="TIMEOUT", timed_out=True) == "TIMEOUT"


@pytest.mark.unit
def test_heartbeat_monitor_writes_samples_during_a_real_sleep(tmp_path):
    """Integration-lite: a real background thread writing real samples,
    without needing a full SeQUeNCe simulation - uses a stand-in object
    with the same `.now()`/`.run_counter`/`.events` shape Timeline has."""
    import time

    from ibqn.experiments.heartbeat_monitor import HeartbeatMonitor

    class FakeTimeline:
        def __init__(self):
            self.run_counter = 0
            self.events = []

        def now(self):
            self.run_counter += 1
            return self.run_counter * 1_000_000_000  # nanoseconds-ish, matches SECOND scaling

    path = tmp_path / "hb.jsonl"
    timeline = FakeTimeline()
    with HeartbeatMonitor(timeline, path, interval_s=0.1):
        time.sleep(0.35)
    samples = read_heartbeats(path)
    assert len(samples) >= 2
