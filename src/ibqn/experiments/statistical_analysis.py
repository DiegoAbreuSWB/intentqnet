"""Paired statistical analysis for Fase J10's final campaigns (section
13, docs/final_experimental_design.md). Comparisons are always paired by
the same seed (and topology/physical parameters/requirements) across
alternatives - never comparing unpaired samples - and the compared
factor itself is never part of the pairing key (the exact pitfall
`aggregation.align_paired_trials` already documents from Fase H3).

Never declares superiority from a mean/median alone: every comparison
reports `n`, a central tendency, a dispersion measure, a 95% CI, the
paired difference's own summary, an (optionally Holm-adjusted) p-value,
and an effect size - together, per section 13.3.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class PairedComparisonResult:
    n: int
    mean_a: float
    mean_b: float
    median_a: float
    median_b: float
    std_a: float
    std_b: float
    mean_difference: float
    """`b - a`, matching `aggregation.align_paired_trials`'s convention."""
    ci95_low: float
    ci95_high: float
    test_used: str
    """`'paired_t'` or `'wilcoxon'` - chosen from a Shapiro-Wilk normality
    check of the paired differences, never assumed. `'identical'` when
    every paired difference is exactly zero (see below)."""
    normality_p_value: float | None
    p_value: float
    """Raw (not yet Holm-adjusted) p-value - use `holm_correction` across
    a family of comparisons before interpreting significance."""
    effect_size: float
    effect_size_name: str
    """`'cohen_d'` (paired t-test), `'matched_pairs_rank_biserial'`
    (Wilcoxon), or `'none'` (`test_used == 'identical'`)."""


def paired_comparison(values_a: list[float], values_b: list[float], *, alpha: float = 0.05) -> PairedComparisonResult:
    """Compares `values_a`/`values_b`, ALREADY aligned pair-by-pair (e.g.
    by seed) by the caller - this function never re-aligns or drops
    rows itself. Requires `n >= 2` (raises `ValueError` otherwise - a
    single pair has no defined spread or CI)."""
    if len(values_a) != len(values_b):
        raise ValueError(f"values_a and values_b must have the same length, got {len(values_a)} and {len(values_b)}")
    n = len(values_a)
    if n < 2:
        raise ValueError(f"paired_comparison requires at least 2 pairs, got {n}")

    a = np.asarray(values_a, dtype=float)
    b = np.asarray(values_b, dtype=float)
    differences = b - a

    mean_a, mean_b = float(a.mean()), float(b.mean())
    median_a, median_b = float(np.median(a)), float(np.median(b))
    std_a, std_b = float(a.std(ddof=1)), float(b.std(ddof=1))
    mean_difference = float(differences.mean())

    if np.all(differences == 0):
        # Every pair is exactly tied - found empirically (Fase J10) on real
        # campaign data (e.g. a purification policy that never actually
        # triggers produces byte-identical results to "disabled" at every
        # seed). scipy.stats.shapiro/wilcoxon warn or silently return nan
        # on this constant input (confirmed inconsistent even across n:
        # p=1.0 for n=5, p=nan for n=20, same all-zero input) instead of
        # raising - so this well-defined case ("no difference, with
        # certainty, in this sample") is reported directly, without
        # calling either.
        return PairedComparisonResult(
            n=n, mean_a=mean_a, mean_b=mean_b, median_a=median_a, median_b=median_b,
            std_a=std_a, std_b=std_b, mean_difference=0.0,
            ci95_low=0.0, ci95_high=0.0, test_used="identical", normality_p_value=None,
            p_value=1.0, effect_size=0.0, effect_size_name="none",
        )

    normality_p_value: float | None = None
    if n >= 3:
        _, normality_p_value = stats.shapiro(differences)

    use_t_test = normality_p_value is None or normality_p_value >= alpha

    if use_t_test:
        std_diff = float(differences.std(ddof=1))
        se = std_diff / (n ** 0.5)
        t_critical = stats.t.ppf(1 - alpha / 2, df=n - 1)
        ci95_low = mean_difference - t_critical * se
        ci95_high = mean_difference + t_critical * se
        t_stat, p_value = stats.ttest_rel(b, a)
        effect_size = mean_difference / std_diff if std_diff > 0 else 0.0
        result_kwargs = dict(test_used="paired_t", p_value=float(p_value), effect_size=float(effect_size), effect_size_name="cohen_d")
    else:
        try:
            w_stat, p_value = stats.wilcoxon(b, a)
        except ValueError:
            # every difference is exactly zero - wilcoxon is undefined, but the conclusion (no difference) is clear
            p_value = 1.0
        nonzero = differences[differences != 0]
        n_effective = len(nonzero) if len(nonzero) > 0 else n
        # bootstrap CI for the median difference (distribution-free, appropriate alongside Wilcoxon)
        rng = np.random.default_rng(0)
        bootstrap_medians = [
            np.median(rng.choice(differences, size=n, replace=True)) for _ in range(2000)
        ]
        ci95_low, ci95_high = np.percentile(bootstrap_medians, [2.5, 97.5])
        positive = int((nonzero > 0).sum())
        effect_size = (2 * positive / n_effective - 1) if n_effective > 0 else 0.0  # matched-pairs rank-biserial correlation
        result_kwargs = dict(test_used="wilcoxon", p_value=float(p_value), effect_size=float(effect_size), effect_size_name="matched_pairs_rank_biserial")

    return PairedComparisonResult(
        n=n, mean_a=mean_a, mean_b=mean_b, median_a=median_a, median_b=median_b,
        std_a=std_a, std_b=std_b, mean_difference=mean_difference,
        ci95_low=float(ci95_low), ci95_high=float(ci95_high),
        normality_p_value=normality_p_value, **result_kwargs,
    )


def holm_correction(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni step-down correction (section 13.2) - returns
    adjusted p-values in the SAME order as `p_values` (not sorted), each
    monotonically non-decreasing relative to the sort order, as the
    Holm procedure requires."""
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    adjusted = [0.0] * n
    running_max = 0.0
    for rank, i in enumerate(order):
        adjusted_p = (n - rank) * p_values[i]
        running_max = max(running_max, adjusted_p)
        adjusted[i] = min(running_max, 1.0)
    return adjusted


def compare_groups_pairwise(
    df, *, group_col: str, value_col: str, pair_on: list[str],
) -> "pd.DataFrame":  # noqa: F821 - pandas imported lazily below
    """For every pair of distinct values in `df[group_col]`, aligns rows
    by `pair_on` (must NOT include `group_col` itself or anything derived
    from it - see the module docstring) and runs `paired_comparison` on
    `value_col`. Returns one row per group-pair with the full
    `PairedComparisonResult` plus a Holm-adjusted p-value across all
    pairs compared in this call (section 13.2 - correction is applied
    across the whole family of comparisons, not per-pair in isolation).

    Pairs where `value_col` is NaN on either side (e.g. a REJECTED trial
    that never ran a simulation, so `delivered_pairs`/`average_fidelity`
    are undefined) are dropped before comparison - found empirically
    (Fase J10) via `scipy.stats.wilcoxon` silently returning `nan` for an
    all-NaN input instead of raising, which `holm_correction`'s
    running-max step then masked as a spuriously significant `p ~ 0`.
    Comparing "no simulation ran" against another "no simulation ran" is
    not a defined paired difference; use a 0/1 outcome column (e.g.
    `satisfied`) to compare REJECTED-vs-not instead."""
    import itertools

    import pandas as pd

    groups = sorted(df[group_col].dropna().unique())
    rows = []
    for group_a, group_b in itertools.combinations(groups, 2):
        rows_a = df[df[group_col] == group_a].set_index(pair_on)[value_col]
        rows_b = df[df[group_col] == group_b].set_index(pair_on)[value_col]
        common_keys = rows_a.index.intersection(rows_b.index)
        aligned_a = rows_a.loc[common_keys]
        aligned_b = rows_b.loc[common_keys]
        valid = aligned_a.notna().to_numpy() & aligned_b.notna().to_numpy()
        values_a = aligned_a[valid].tolist()
        values_b = aligned_b[valid].tolist()
        if len(values_a) < 2:
            continue
        result = paired_comparison(values_a, values_b)
        rows.append({
            "group_a": group_a, "group_b": group_b, "n": result.n,
            "mean_a": result.mean_a, "mean_b": result.mean_b,
            "median_a": result.median_a, "median_b": result.median_b,
            "mean_difference_b_minus_a": result.mean_difference,
            "ci95_low": result.ci95_low, "ci95_high": result.ci95_high,
            "test_used": result.test_used, "p_value": result.p_value,
            "effect_size": result.effect_size, "effect_size_name": result.effect_size_name,
        })
    result_df = pd.DataFrame(rows)
    if len(result_df) > 0:
        result_df["p_value_holm_adjusted"] = holm_correction(result_df["p_value"].tolist())
    return result_df
