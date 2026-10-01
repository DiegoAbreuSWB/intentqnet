"""Tests for `ibqn.experiments.parallel`: running a campaign's trials in
worker processes must produce exactly the rows sequential execution does.
"""
from __future__ import annotations

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
