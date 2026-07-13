"""Tests for `ibqn.experiments.reconciliation_metrics` (Fase J6)."""
from __future__ import annotations

import pandas as pd
import pytest

from ibqn.assurance.reconciliation_policy import DURATION_INCREASE, NO_ACTION, ROUTE_CHANGE, SLOT_INCREASE
from ibqn.experiments.reconciliation_metrics import compute_reconciliation_metrics


def _row(initial_status, attempted, action=None, recovered=None, additional_wall_time_s=None, episodes=None):
    return {
        "initial_status": initial_status, "reconciliation_attempted": attempted, "action": action,
        "recovered": recovered, "additional_wall_time_s": additional_wall_time_s, "episodes": episodes,
    }


@pytest.mark.unit
def test_metrics_never_fabricate_a_rate_from_an_empty_denominator():
    df = pd.DataFrame([_row("SATISFIED", False)])  # no violations at all, nothing attempted
    metrics = compute_reconciliation_metrics(df)
    assert metrics["initial_violation_rate"] == 0.0  # a real, computable zero (denominator n_total > 0)
    assert metrics["recovery_attempt_rate"] is None  # denominator (n_initial_violated) is 0
    assert metrics["recovery_rate"] is None
    assert metrics["additional_wall_time"] is None


@pytest.mark.unit
def test_recovery_rate_and_failed_recovery_rate_over_attempted_trials():
    df = pd.DataFrame([
        _row("VIOLATED", True, ROUTE_CHANGE, True, 1.2, 2),
        _row("VIOLATED", True, DURATION_INCREASE, False, 0.8, 2),
        _row("VIOLATED", True, SLOT_INCREASE, True, 1.5, 2),
        _row("SATISFIED", False),
    ])
    metrics = compute_reconciliation_metrics(df)

    assert metrics["n_total"] == 4
    assert metrics["initial_violation_rate"] == pytest.approx(3 / 4)
    assert metrics["recovery_attempt_rate"] == pytest.approx(3 / 3)
    assert metrics["recovery_rate"] == pytest.approx(2 / 3)
    assert metrics["failed_recovery_rate"] == pytest.approx(1 / 3)
    assert metrics["route_change_rate"] == pytest.approx(1 / 3)
    assert metrics["duration_change_rate"] == pytest.approx(1 / 3)
    assert metrics["slot_change_rate"] == pytest.approx(1 / 3)
    assert metrics["additional_wall_time"] == pytest.approx((1.2 + 0.8 + 1.5) / 3)
    assert metrics["additional_episodes"] == pytest.approx(2.0)


@pytest.mark.unit
def test_no_action_rate_is_over_initially_violated_trials():
    df = pd.DataFrame([
        _row("VIOLATED", False, NO_ACTION, None, None, None),
        _row("VIOLATED", True, ROUTE_CHANGE, True, 1.0, 2),
    ])
    metrics = compute_reconciliation_metrics(df)
    assert metrics["no_action_rate"] == pytest.approx(1 / 2)


@pytest.mark.unit
def test_recovery_attempt_rate_can_be_less_than_one():
    """Not every VIOLATED trial necessarily gets an attempt in a real
    campaign (e.g. reconciliation_enabled=False) - recovery_attempt_rate
    must reflect that, not assume every violation triggers an attempt."""
    df = pd.DataFrame([
        _row("VIOLATED", False),  # reconciliation disabled for this trial
        _row("VIOLATED", True, ROUTE_CHANGE, True, 1.0, 2),
    ])
    metrics = compute_reconciliation_metrics(df)
    assert metrics["recovery_attempt_rate"] == pytest.approx(0.5)
