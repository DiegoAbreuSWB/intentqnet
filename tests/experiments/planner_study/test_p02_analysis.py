"""Unit tests for `scripts/analyze_p02.py`'s analysis functions, using
small synthetic data - these compute the actual checkpoint-2 numbers, so
their correctness matters independently of whether the real P02 campaign
has finished running.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from analyze_p02 import brier_score, calibration_curve, counterfactual_outcome, threshold_metrics  # noqa: E402


def _row(predicted_probability, final_status):
    return pd.Series({"predicted_satisfaction_probability": predicted_probability, "final_status": final_status})


@pytest.mark.unit
def test_counterfactual_outcome_admits_when_above_threshold():
    row = _row(0.8, "SATISFIED")
    assert counterfactual_outcome(row, 0.5) == "SATISFIED"


@pytest.mark.unit
def test_counterfactual_outcome_rejects_when_below_threshold():
    row = _row(0.3, "SATISFIED")  # real outcome was SATISFIED, but threshold would have rejected it
    assert counterfactual_outcome(row, 0.5) == "REJECTED"


@pytest.mark.unit
def test_counterfactual_outcome_preserves_violated_when_admitted():
    row = _row(0.9, "VIOLATED")
    assert counterfactual_outcome(row, 0.5) == "VIOLATED"


@pytest.mark.unit
def test_counterfactual_outcome_handles_missing_prediction():
    row = _row(float("nan"), "REJECTED")
    assert counterfactual_outcome(row, 0.5) == "REJECTED"


@pytest.mark.unit
def test_brier_score_is_zero_for_perfect_predictions():
    df = pd.DataFrame({
        "predicted_satisfaction_probability": [1.0, 1.0, 0.0, 0.0],
        "final_status": ["SATISFIED", "SATISFIED", "REJECTED", "VIOLATED"],
    })
    assert brier_score(df) == pytest.approx(0.0)


@pytest.mark.unit
def test_brier_score_is_worse_for_confidently_wrong_predictions():
    confident_wrong = pd.DataFrame({
        "predicted_satisfaction_probability": [1.0, 1.0],
        "final_status": ["VIOLATED", "VIOLATED"],
    })
    confident_right = pd.DataFrame({
        "predicted_satisfaction_probability": [1.0, 1.0],
        "final_status": ["SATISFIED", "SATISFIED"],
    })
    assert brier_score(confident_wrong) > brier_score(confident_right)


@pytest.mark.unit
def test_brier_score_excludes_rows_without_a_prediction():
    df = pd.DataFrame({
        "predicted_satisfaction_probability": [1.0, None],
        "final_status": ["SATISFIED", "REJECTED"],
    })
    # only the first (perfectly-predicted) row should count
    assert brier_score(df) == pytest.approx(0.0)


@pytest.mark.unit
def test_threshold_metrics_false_feasibility_counts_admitted_but_violated():
    df = pd.DataFrame({
        "predicted_satisfaction_probability": [0.9, 0.9],
        "final_status": ["SATISFIED", "VIOLATED"],
    })
    metrics = threshold_metrics(df, threshold=0.5)
    assert metrics["false_feasibility"] == pytest.approx(0.5)  # 1 of 2 admitted trials violated


@pytest.mark.unit
def test_threshold_metrics_false_rejection_counts_rejected_but_would_have_satisfied():
    df = pd.DataFrame({
        "predicted_satisfaction_probability": [0.3, 0.3],
        "final_status": ["SATISFIED", "VIOLATED"],  # both rejected at threshold=0.5
    })
    metrics = threshold_metrics(df, threshold=0.5)
    # 1 of 2 rejected trials would actually have been SATISFIED if admitted
    assert metrics["false_rejection"] == pytest.approx(0.5)


@pytest.mark.unit
def test_threshold_metrics_higher_threshold_never_decreases_rejection_rate():
    df = pd.DataFrame({
        "predicted_satisfaction_probability": [0.4, 0.6, 0.8, 0.95],
        "final_status": ["SATISFIED", "SATISFIED", "SATISFIED", "SATISFIED"],
    })
    low = threshold_metrics(df, threshold=0.5)
    high = threshold_metrics(df, threshold=0.9)
    admitted_low = df[df["predicted_satisfaction_probability"] >= 0.5]
    admitted_high = df[df["predicted_satisfaction_probability"] >= 0.9]
    assert len(admitted_high) <= len(admitted_low)


@pytest.mark.unit
def test_calibration_curve_bins_are_between_zero_and_one():
    df = pd.DataFrame({
        "predicted_satisfaction_probability": [0.1, 0.3, 0.5, 0.7, 0.9],
        "final_status": ["REJECTED", "VIOLATED", "SATISFIED", "SATISFIED", "SATISFIED"],
    })
    curve = calibration_curve(df, n_bins=5)
    assert (curve["mean_predicted"] >= 0).all()
    assert (curve["mean_predicted"] <= 1).all()
    assert (curve["mean_actual"] >= 0).all()
    assert (curve["mean_actual"] <= 1).all()
