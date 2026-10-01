"""Tests for `ibqn.experiments.parallel`: running a campaign's trials in
worker processes must produce exactly the rows sequential execution does.
"""
from __future__ import annotations

import os
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pandas as pd
import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.parallel import TrialOutcome, execute_jobs
from ibqn.experiments.programmatic_campaign import run_programmatic_campaign

COMPARED_COLUMNS = [
    "trial_id", "final_status", "delivered_pairs", "average_fidelity", "minimum_fidelity",
    "estimated_fidelity", "route", "eg_success", "es_success", "ep_success", "purification_mode", "formalism",
]


def _run(tmp_path, name, workers):
    intent = simple_intent(
        intent_id="par", source="a", destination="b", min_fidelity=0.6, requested_pairs=5,
        min_delivered_pairs=5, start_time=0.01, duration=0.03,
    )
    summary = run_programmatic_campaign(
        campaign_name="PAR", scenario_name="three_node",
        base_topology=three_node_spec(stop_time_s=0.05), base_intents=[intent],
        parameter_grid={"min_fidelity": [0.6, 0.99]}, seeds=[0, 1],
        output_directory=tmp_path / name, workers=workers,
    )
    frame = pd.read_csv(tmp_path / name / "raw" / "PAR" / "trials.csv")
    return summary, frame.sort_values("trial_id").reset_index(drop=True)


@pytest.mark.unit
def test_parallel_campaign_matches_sequential_campaign_row_for_row(tmp_path):
    sequential_summary, sequential = _run(tmp_path, "seq", workers=1)
    parallel_summary, parallel = _run(tmp_path, "par", workers=2)

    assert sequential_summary.completed_trials == parallel_summary.completed_trials == 4
    assert sequential_summary.failed_trials == parallel_summary.failed_trials == 0
    pd.testing.assert_frame_equal(sequential[COMPARED_COLUMNS], parallel[COMPARED_COLUMNS])
    assert set(sequential["final_status"]) == {"SATISFIED", "REJECTED"}  # both branches exercised


def _square(job):
    return job * job


def _explode(job):
    raise RuntimeError("never called inline for an empty job list")


@pytest.mark.unit
def test_execute_jobs_inline_path_preserves_order_and_handles_empty_input():
    assert list(execute_jobs([3, 1, 2], workers=1, job_runner=_square)) == [(3, 9), (1, 1), (2, 4)]
    assert list(execute_jobs([], workers=8, job_runner=_explode)) == []


@pytest.mark.unit
def test_execute_jobs_parallel_path_returns_every_result():
    results = dict(execute_jobs(range(6), workers=3, job_runner=_square))
    assert results == {n: n * n for n in range(6)}


@pytest.mark.unit
def test_trial_outcome_failed_flag():
    assert TrialOutcome(error_type="ValueError", error_message="x").failed
    assert not TrialOutcome(record=None).failed


def _die_once(job):
    marker, value = job
    marker = Path(marker)
    if value == 2 and not marker.exists():
        marker.write_text("died")
        os._exit(1)  # what the OS does to a worker under memory pressure: no exception, no cleanup
    return value * value


def _always_die(job):
    os._exit(1)


@pytest.mark.unit
def test_execute_jobs_resubmits_the_jobs_lost_when_a_worker_dies(tmp_path):
    marker = tmp_path / "died-once"
    jobs = [(str(marker), n) for n in range(6)]

    results = [(job[1], result) for job, result in execute_jobs(jobs, workers=3, job_runner=_die_once)]

    assert marker.exists()                                      # a worker really died mid-campaign
    assert sorted(results) == [(n, n * n) for n in range(6)]    # every job still reported exactly once


@pytest.mark.unit
def test_execute_jobs_gives_up_once_the_restart_budget_is_spent():
    with pytest.raises(BrokenProcessPool):
        list(execute_jobs(range(4), workers=2, job_runner=_always_die, max_pool_restarts=1))


def _numeric_thread_settings(job):
    return {name: os.environ.get(name) for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")}


@pytest.mark.unit
def test_workers_load_numeric_libraries_single_threaded(monkeypatch):
    """Multi-threaded BLAS reserves ~1 GB of committed memory per worker for
    nothing (the simulator multiplies 4-element vectors)."""
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MKL_NUM_THREADS", "3")  # an explicit user choice is respected

    settings = [result for _, result in execute_jobs(range(2), workers=2, job_runner=_numeric_thread_settings)]

    assert settings == [{"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "3"}] * 2
