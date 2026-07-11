"""Statistical aggregation and paired-trial alignment over persisted
`TrialRecord`s (Fase H3, see docs/campaign_architecture.md, section 8 and
the project brief's Fase H3, sections 16-17).

`aggregate_records` returns a *long* table (one row per group x metric),
which is what notebooks plot directly (`df[df.metric == "delivered_pairs"]`)
without needing to know the full metric list up front.
"""
from __future__ import annotations

import statistics

import pandas as pd
from scipy import stats

NUMERIC_METRICS: tuple[str, ...] = (
    "delivered_pairs", "excess_delivery_pairs", "delivery_ratio",
    "average_fidelity", "minimum_fidelity",
    "throughput_active_window", "throughput_delivery_interval",
    "first_pair_latency_s", "completion_time_s",
    "planning_time_s", "simulation_wall_time_s",
)


def _confidence_interval_95(values: list[float]) -> tuple[float | None, float | None]:
    """Student-t 95% CI - `None` (never `0`) with fewer than 2 observations,
    since a spread can't be estimated from a single value (see
    docs/campaign_architecture.md, section 8/limitations)."""
    if len(values) < 2:
        return None, None
    mean = statistics.mean(values)
    sem = statistics.stdev(values) / (len(values) ** 0.5)
    if sem == 0:
        return mean, mean
    margin = stats.t.ppf(0.975, df=len(values) - 1) * sem
    return mean - margin, mean + margin


def _aggregate_one_metric(series: pd.Series) -> dict:
    values = [float(v) for v in series if pd.notna(v)]
    n_total = len(series)
    n_valid = len(values)
    n_missing = n_total - n_valid
    if not values:
        return {
            "n_total": n_total, "n_valid": 0, "n_missing": n_missing,
            "mean": None, "std": None, "median": None, "min": None, "max": None,
            "ci95_low": None, "ci95_high": None,
        }
    ci_low, ci_high = _confidence_interval_95(values)
    return {
        "n_total": n_total, "n_valid": n_valid, "n_missing": n_missing,
        "mean": statistics.mean(values),
        "std": statistics.stdev(values) if len(values) > 1 else 0.0,
        "median": statistics.median(values),
        "min": min(values), "max": max(values),
        "ci95_low": ci_low, "ci95_high": ci_high,
    }


def _rates(group_df: pd.DataFrame) -> dict:
    n_total = len(group_df)
    accepted = group_df["accepted"].fillna(False).astype(bool)
    final_status = group_df["final_status"]
    recovered = group_df["recovered"]
    eligible_for_recovery = recovered.notna()

    return {
        "acceptance_rate": accepted.mean() if n_total else None,
        "satisfaction_rate": (final_status == "SATISFIED").mean() if n_total else None,
        "violation_rate": (final_status == "VIOLATED").mean() if n_total else None,
        "rejection_rate": (final_status == "REJECTED").mean() if n_total else None,
        "recovery_rate": (
            recovered[eligible_for_recovery].astype(bool).mean() if eligible_for_recovery.any() else None
        ),
    }


def aggregate_records(
    df: pd.DataFrame, *, group_by: list[str], metrics: list[str] | None = None,
) -> pd.DataFrame:
    """Groups `df` (as returned by `persistence.read_trials_dataframe`) by
    every column in `group_by`, and returns one row per (group, metric)
    with `n_total`/`n_valid`/`n_missing`/`mean`/`std`/`median`/`min`/`max`/
    `ci95_low`/`ci95_high`, plus the group's `acceptance_rate`/
    `satisfaction_rate`/`violation_rate`/`rejection_rate`/`recovery_rate`
    (repeated per metric row, for convenience). `recovery_rate` is `None`
    for a group where no trial had `reconciliation_enabled` trigger (i.e.
    `recovered` is `None` for every row - never treated as 0)."""
    if metrics is None:
        metrics = [m for m in NUMERIC_METRICS if m in df.columns]

    if df.empty:
        columns = group_by + [
            "metric", "n_total", "n_valid", "n_missing", "mean", "std", "median", "min", "max",
            "ci95_low", "ci95_high", "acceptance_rate", "satisfaction_rate", "violation_rate",
            "rejection_rate", "recovery_rate",
        ]
        return pd.DataFrame(columns=columns)

    rows = []
    for group_key, group_df in df.groupby(group_by, dropna=False):
        group_values = group_key if isinstance(group_key, tuple) else (group_key,)
        group_dict = dict(zip(group_by, group_values))
        rate_dict = _rates(group_df)
        for metric in metrics:
            metric_stats = _aggregate_one_metric(group_df[metric])
            rows.append({**group_dict, "metric": metric, **metric_stats, **rate_dict})

    return pd.DataFrame(rows)


def align_paired_trials(
    df: pd.DataFrame, *, pair_on: list[str], compare: str, metrics: list[str] | None = None,
) -> pd.DataFrame:
    """Aligns trials sharing `pair_on` (typically scenario/parameter_hash/
    seed/intent_id) but differing in the two-valued column `compare`
    (typically `strategy` or `reconciliation_enabled`), computing a `_diff`
    column (`b - a`, alphabetically) per metric. Missing pairs are kept as
    rows with `paired=False` and `NaN` on the missing side - never dropped
    silently (see the project brief's Fase H3, section 17)."""
    if metrics is None:
        metrics = [m for m in NUMERIC_METRICS if m in df.columns]

    compare_values = sorted(v for v in df[compare].dropna().unique())
    if len(compare_values) != 2:
        raise ValueError(
            f"align_paired_trials needs exactly 2 distinct values in column '{compare}', found {compare_values}"
        )
    value_a, value_b = compare_values

    columns = pair_on + metrics
    side_a = df[df[compare] == value_a][columns].rename(columns={m: f"{m}_{value_a}" for m in metrics})
    side_b = df[df[compare] == value_b][columns].rename(columns={m: f"{m}_{value_b}" for m in metrics})

    merged = side_a.merge(side_b, on=pair_on, how="outer", indicator=True)
    merged["paired"] = merged["_merge"] == "both"
    merged = merged.drop(columns="_merge")

    for metric in metrics:
        merged[f"{metric}_diff"] = merged[f"{metric}_{value_b}"] - merged[f"{metric}_{value_a}"]

    return merged
