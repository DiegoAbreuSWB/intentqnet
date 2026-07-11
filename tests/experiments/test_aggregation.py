"""Tests for `ibqn.experiments.aggregation` (Fase H3.3)."""
import math

import pandas as pd
import pytest

from ibqn.experiments.aggregation import aggregate_records


def _trials_df():
    return pd.DataFrame([
        {"strategy": "a", "seed": 0, "scenario": "s", "parameter_hash": "h", "intent_id": "i",
         "delivered_pairs": 10, "average_fidelity": 0.70, "accepted": True, "final_status": "SATISFIED", "recovered": None},
        {"strategy": "a", "seed": 1, "scenario": "s", "parameter_hash": "h", "intent_id": "i",
         "delivered_pairs": 12, "average_fidelity": 0.71, "accepted": True, "final_status": "SATISFIED", "recovered": None},
        {"strategy": "b", "seed": 0, "scenario": "s", "parameter_hash": "h", "intent_id": "i",
         "delivered_pairs": 400, "average_fidelity": 0.60, "accepted": True, "final_status": "VIOLATED", "recovered": False},
        {"strategy": "b", "seed": 1, "scenario": "s", "parameter_hash": "h", "intent_id": "i",
         "delivered_pairs": 420, "average_fidelity": 0.61, "accepted": True, "final_status": "SATISFIED", "recovered": True},
    ])


@pytest.mark.unit
def test_aggregate_records_basic_stats():
    df = _trials_df()
    agg = aggregate_records(df, group_by=["strategy"], metrics=["delivered_pairs"])
    row_a = agg[(agg["strategy"] == "a") & (agg["metric"] == "delivered_pairs")].iloc[0]
    assert row_a["n_total"] == 2
    assert row_a["n_valid"] == 2
    assert row_a["n_missing"] == 0
    assert row_a["mean"] == 11.0
    assert row_a["median"] == 11.0
    assert row_a["min"] == 10.0
    assert row_a["max"] == 12.0


@pytest.mark.unit
def test_ci95_is_none_with_fewer_than_two_observations():
    df = _trials_df().iloc[[0]]  # only one row for strategy "a"
    agg = aggregate_records(df, group_by=["strategy"], metrics=["delivered_pairs"])
    row = agg.iloc[0]
    assert row["n_valid"] == 1
    assert row["ci95_low"] is None
    assert row["ci95_high"] is None


@pytest.mark.unit
def test_ci95_is_populated_with_two_or_more_observations():
    df = _trials_df()
    agg = aggregate_records(df, group_by=["strategy"], metrics=["delivered_pairs"])
    row_a = agg[agg["strategy"] == "a"].iloc[0]
    assert row_a["ci95_low"] is not None
    assert row_a["ci95_low"] < row_a["mean"] < row_a["ci95_high"]


@pytest.mark.unit
def test_missing_values_are_not_treated_as_zero():
    df = pd.DataFrame([
        {"strategy": "a", "delivered_pairs": 10.0, "accepted": True, "final_status": "SATISFIED", "recovered": None},
        {"strategy": "a", "delivered_pairs": None, "accepted": True, "final_status": "SATISFIED", "recovered": None},
    ])
    agg = aggregate_records(df, group_by=["strategy"], metrics=["delivered_pairs"])
    row = agg.iloc[0]
    assert row["n_total"] == 2
    assert row["n_valid"] == 1
    assert row["n_missing"] == 1
    assert row["mean"] == 10.0  # not (10 + 0) / 2 = 5.0


@pytest.mark.unit
def test_rates_computed_correctly():
    df = _trials_df()
    agg = aggregate_records(df, group_by=["strategy"], metrics=["delivered_pairs"])
    row_a = agg[agg["strategy"] == "a"].iloc[0]
    row_b = agg[agg["strategy"] == "b"].iloc[0]
    assert row_a["satisfaction_rate"] == 1.0
    assert row_a["violation_rate"] == 0.0
    assert row_b["satisfaction_rate"] == 0.5
    assert row_b["violation_rate"] == 0.5


@pytest.mark.unit
def test_recovery_rate_is_none_when_no_trial_is_eligible():
    df = _trials_df()
    agg = aggregate_records(df, group_by=["strategy"], metrics=["delivered_pairs"])
    row_a = agg[agg["strategy"] == "a"].iloc[0]
    assert row_a["recovery_rate"] is None or (isinstance(row_a["recovery_rate"], float) and math.isnan(row_a["recovery_rate"]))


@pytest.mark.unit
def test_recovery_rate_computed_only_over_eligible_trials():
    df = _trials_df()
    agg = aggregate_records(df, group_by=["strategy"], metrics=["delivered_pairs"])
    row_b = agg[agg["strategy"] == "b"].iloc[0]
    assert row_b["recovery_rate"] == 0.5  # 1 of 2 "b" trials recovered (the other wasn't recovered)


@pytest.mark.unit
def test_aggregate_records_on_empty_dataframe():
    empty = pd.DataFrame(columns=["strategy", "delivered_pairs", "accepted", "final_status", "recovered"])
    agg = aggregate_records(empty, group_by=["strategy"], metrics=["delivered_pairs"])
    assert len(agg) == 0
    assert "metric" in agg.columns


