"""Tests for `ibqn.experiments.planner_operation_matrix` (Fase J5)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ibqn.experiments.persistence import read_trials_dataframe, trials_csv_path
from ibqn.experiments.planner_operation_matrix import (
    EXECUTION_FAILED,
    FEASIBLE_AND_SATISFIED,
    FEASIBLE_BUT_VIOLATED,
    INFEASIBLE_AND_REJECTED,
    INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE,
    build_matrix,
    classify_trials,
    compute_gap_metrics,
    upgrade_rejected_with_oracle,
)

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"


def _row(trial_id, final_status, **overrides):
    row = {
        "trial_id": trial_id, "final_status": final_status,
        "min_delivered_pairs": None, "delivered_pairs": None,
        "duration_s": 1.0, "throughput_active_window": None,
        "absolute_fidelity_error": None,
    }
    row.update(overrides)
    return row


@pytest.mark.unit
def test_classify_trials_maps_every_status_to_its_category():
    df = pd.DataFrame([
        _row("t1", "SATISFIED"), _row("t2", "VIOLATED"),
        _row("t3", "REJECTED"), _row("t4", "FAILED"),
    ])
    categories = classify_trials(df)
    assert list(categories) == [
        FEASIBLE_AND_SATISFIED, FEASIBLE_BUT_VIOLATED, INFEASIBLE_AND_REJECTED, EXECUTION_FAILED,
    ]


@pytest.mark.unit
def test_classify_trials_rejects_unknown_status():
    df = pd.DataFrame([_row("t1", "SOMETHING_ELSE")])
    with pytest.raises(ValueError, match="unknown final_status"):
        classify_trials(df)


@pytest.mark.unit
def test_upgrade_rejected_with_oracle_only_touches_matched_rejected_rows():
    df = pd.DataFrame([_row("t1", "REJECTED"), _row("t2", "REJECTED"), _row("t3", "SATISFIED")])
    categories = classify_trials(df)

    updated = upgrade_rejected_with_oracle(categories, df, {"t1": True, "t2": False})

    assert updated.loc[0] == INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE  # t1: oracle succeeded
    assert updated.loc[1] == INFEASIBLE_AND_REJECTED  # t2: oracle also failed, stays rejected
    assert updated.loc[2] == FEASIBLE_AND_SATISFIED  # t3: untouched, not REJECTED to begin with


@pytest.mark.unit
def test_upgrade_rejected_with_oracle_ignores_trials_not_in_the_mapping():
    df = pd.DataFrame([_row("t1", "REJECTED")])
    categories = classify_trials(df)
    updated = upgrade_rejected_with_oracle(categories, df, {})
    assert updated.loc[0] == INFEASIBLE_AND_REJECTED


@pytest.mark.unit
def test_build_matrix_has_one_row_per_category_with_correct_counts():
    df = pd.DataFrame([
        _row("t1", "SATISFIED"), _row("t2", "SATISFIED"), _row("t3", "VIOLATED"), _row("t4", "REJECTED"),
    ])
    matrix = build_matrix(df)
    counts = dict(zip(matrix["category"], matrix["count"]))
    assert counts[FEASIBLE_AND_SATISFIED] == 2
    assert counts[FEASIBLE_BUT_VIOLATED] == 1
    assert counts[INFEASIBLE_AND_REJECTED] == 1
    assert counts[EXECUTION_FAILED] == 0
    assert set(matrix["category"]) == {
        FEASIBLE_AND_SATISFIED, FEASIBLE_BUT_VIOLATED, INFEASIBLE_AND_REJECTED,
        INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE, EXECUTION_FAILED,
    }


@pytest.mark.unit
def test_gap_metrics_never_fabricate_a_rate_from_an_empty_denominator():
    df = pd.DataFrame([_row("t1", "REJECTED")])  # no oracle comparisons, no feasible trials at all
    metrics = compute_gap_metrics(df)
    assert metrics["false_feasibility_rate"] is None
    assert metrics["false_rejection_rate"] is None
    assert metrics["fidelity_prediction_error"] is None
    assert metrics["delivery_deficit"] is None


@pytest.mark.unit
def test_false_rejection_rate_distinguishes_untested_from_all_true_rejections():
    """The category labels alone can't tell "no oracle was run" apart
    from "the oracle was run and every rejection was confirmed true" -
    oracle_tested_trial_ids must be passed explicitly to disambiguate."""
    df = pd.DataFrame([_row("t1", "REJECTED"), _row("t2", "REJECTED")])
    categories = classify_trials(df)

    untested = compute_gap_metrics(df, categories)
    assert untested["false_rejection_rate"] is None

    tested_all_true_rejections = compute_gap_metrics(df, categories, oracle_tested_trial_ids={"t1", "t2"})
    assert tested_all_true_rejections["false_rejection_rate"] == 0.0

    upgraded = upgrade_rejected_with_oracle(categories, df, {"t1": True, "t2": False})
    tested_one_false_rejection = compute_gap_metrics(df, upgraded, oracle_tested_trial_ids={"t1", "t2"})
    assert tested_one_false_rejection["false_rejection_rate"] == pytest.approx(0.5)


@pytest.mark.unit
def test_operational_success_rate_counts_over_all_trials_including_rejected():
    df = pd.DataFrame([_row("t1", "SATISFIED"), _row("t2", "REJECTED")])
    metrics = compute_gap_metrics(df)
    assert metrics["operational_success_rate"] == pytest.approx(0.5)


@pytest.mark.unit
def test_delivery_and_throughput_deficit_are_zero_when_goal_is_met_or_exceeded():
    df = pd.DataFrame([
        _row("t1", "SATISFIED", min_delivered_pairs=10, delivered_pairs=15, duration_s=1.0, throughput_active_window=20.0),
    ])
    metrics = compute_gap_metrics(df)
    assert metrics["delivery_deficit"] == 0.0
    assert metrics["throughput_deficit"] == 0.0


@pytest.mark.unit
def test_delivery_and_throughput_deficit_are_positive_when_goal_is_missed():
    df = pd.DataFrame([
        _row("t1", "VIOLATED", min_delivered_pairs=10, delivered_pairs=4, duration_s=1.0, throughput_active_window=4.0),
    ])
    metrics = compute_gap_metrics(df)
    assert metrics["delivery_deficit"] == pytest.approx(6.0)
    assert metrics["throughput_deficit"] == pytest.approx(6.0)  # required rate 10/1.0=10, observed 4.0


@pytest.mark.skipif(not RESULTS_DIR.exists(), reason="requires the persisted C03 campaign fixture")
@pytest.mark.unit
def test_matrix_and_metrics_over_real_c03_campaign_data():
    """C03_assurance_outcomes was specifically designed (Fase H3) to
    naturally produce all three of SATISFIED/VIOLATED/REJECTED - a real
    smoke test that this module handles genuine persisted data, not just
    synthetic fixtures."""
    df = read_trials_dataframe(trials_csv_path(RESULTS_DIR, "C03_assurance_outcomes"))
    categories = classify_trials(df)
    assert set(categories.unique()) <= {
        FEASIBLE_AND_SATISFIED, FEASIBLE_BUT_VIOLATED, INFEASIBLE_AND_REJECTED, EXECUTION_FAILED,
    }
    assert FEASIBLE_AND_SATISFIED in categories.values
    assert FEASIBLE_BUT_VIOLATED in categories.values
    assert INFEASIBLE_AND_REJECTED in categories.values

    matrix = build_matrix(df, categories)
    assert matrix["count"].sum() == len(df)

    metrics = compute_gap_metrics(df, categories)
    assert metrics["n_total"] == len(df)
    assert 0.0 <= metrics["operational_success_rate"] <= 1.0
