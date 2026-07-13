"""Fase J6 metrics (section 8.8, docs/reconciliation_scope.md) - a pure
analysis function over a DataFrame of reconciliation attempt records (one
row per trial whose episode 1 reached a terminal status; only rows with
`initial_status == "VIOLATED"` ever attempt reconciliation).

Expected columns: `initial_status` (episode 1's final_status),
`reconciliation_attempted` (bool), `action`
(`assurance.reconciliation_policy`'s `ROUTE_CHANGE`/`DURATION_INCREASE`/
`SLOT_INCREASE`/`NO_ACTION`, or `None` when not attempted), `recovered`
(bool, only meaningful when attempted), `additional_wall_time_s` (float,
episode 2's wall time), `episodes` (int, always 2 when attempted in this
project's single-retry design).
"""
from __future__ import annotations

import pandas as pd

from ..assurance.reconciliation_policy import DURATION_INCREASE, NO_ACTION, ROUTE_CHANGE, SLOT_INCREASE


def compute_reconciliation_metrics(df: pd.DataFrame) -> dict:
    """Section 8.8's metrics - `None` (never `0`) wherever the
    denominator would be zero."""
    n_total = len(df)

    def _rate(numerator: int, denominator: int) -> float | None:
        return (numerator / denominator) if denominator > 0 else None

    n_initial_violated = int((df["initial_status"] == "VIOLATED").sum())
    attempted = df[df["reconciliation_attempted"]] if "reconciliation_attempted" in df.columns else df.iloc[0:0]
    n_attempted = len(attempted)
    n_recovered = int((attempted["recovered"] == True).sum())  # noqa: E712
    n_failed_recovery = int((attempted["recovered"] == False).sum())  # noqa: E712
    n_no_action = int((df["action"] == NO_ACTION).sum()) if "action" in df.columns else 0

    action_counts = attempted["action"].value_counts() if "action" in attempted.columns else pd.Series(dtype=int)

    wall_times = attempted["additional_wall_time_s"].dropna() if "additional_wall_time_s" in attempted.columns else pd.Series(dtype=float)
    episode_counts = attempted["episodes"].dropna() if "episodes" in attempted.columns else pd.Series(dtype=float)

    return {
        "n_total": n_total,
        "initial_violation_rate": _rate(n_initial_violated, n_total),
        "recovery_attempt_rate": _rate(n_attempted, n_initial_violated),
        "recovery_rate": _rate(n_recovered, n_attempted),
        "failed_recovery_rate": _rate(n_failed_recovery, n_attempted),
        "no_action_rate": _rate(n_no_action, n_initial_violated),
        "route_change_rate": _rate(int(action_counts.get(ROUTE_CHANGE, 0)), n_attempted),
        "duration_change_rate": _rate(int(action_counts.get(DURATION_INCREASE, 0)), n_attempted),
        "slot_change_rate": _rate(int(action_counts.get(SLOT_INCREASE, 0)), n_attempted),
        "additional_wall_time": float(wall_times.mean()) if len(wall_times) else None,
        "additional_episodes": float(episode_counts.mean()) if len(episode_counts) else None,
    }
