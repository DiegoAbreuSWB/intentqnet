"""Tests for `ibqn.experiments.statistical_analysis` (Fase J10, section 13)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ibqn.experiments.statistical_analysis import (
    compare_groups_pairwise,
    holm_correction,
    paired_comparison,
)


@pytest.mark.unit
def test_paired_comparison_requires_equal_length_and_at_least_two_pairs():
    with pytest.raises(ValueError, match="same length"):
        paired_comparison([1.0, 2.0], [1.0])
    with pytest.raises(ValueError, match="at least 2 pairs"):
        paired_comparison([1.0], [2.0])


@pytest.mark.unit
def test_paired_comparison_detects_a_clear_normal_difference_with_t_test():
    rng = np.random.default_rng(0)
    a = rng.normal(loc=10.0, scale=1.0, size=30)
    b = a + 5.0 + rng.normal(loc=0.0, scale=0.1, size=30)  # b consistently ~5 higher than a

    result = paired_comparison(a.tolist(), b.tolist())

    assert result.test_used == "paired_t"
    assert result.mean_difference == pytest.approx(5.0, abs=0.5)
    assert result.p_value < 0.001
    assert result.ci95_low < result.mean_difference < result.ci95_high
    assert result.effect_size_name == "cohen_d"
    assert abs(result.effect_size) > 1  # a large, unambiguous effect


@pytest.mark.unit
def test_paired_comparison_finds_no_significant_difference_when_none_exists():
    rng = np.random.default_rng(1)
    a = rng.normal(loc=10.0, scale=2.0, size=30)
    b = rng.normal(loc=10.0, scale=2.0, size=30)  # independent draws from the SAME distribution

    result = paired_comparison(a.tolist(), b.tolist())
    assert result.p_value > 0.05


@pytest.mark.unit
def test_paired_comparison_uses_wilcoxon_for_non_normal_differences():
    rng = np.random.default_rng(2)
    a = rng.normal(loc=10.0, scale=1.0, size=40)
    # a strongly skewed, non-normal difference (exponential)
    b = a + rng.exponential(scale=1.0, size=40)

    result = paired_comparison(a.tolist(), b.tolist(), alpha=0.20)  # stricter alpha for the normality gate makes this more likely to trigger wilcoxon
    assert result.test_used in ("paired_t", "wilcoxon")  # depends on the random draw, but must be one of the two, never something else
    assert result.effect_size_name in ("cohen_d", "matched_pairs_rank_biserial")


@pytest.mark.unit
def test_paired_comparison_handles_all_zero_differences_without_crashing():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = paired_comparison(values, values)
    assert result.mean_difference == pytest.approx(0.0)
    assert result.p_value == pytest.approx(1.0)
    assert result.test_used == "identical"
    assert result.effect_size == pytest.approx(0.0)


@pytest.mark.unit
def test_paired_comparison_handles_all_zero_differences_at_larger_n_without_nan():
    """Regression test (Fase J10): found empirically on real campaign data
    (F03's satisfied_num, identical 0.0 for both purification policies at
    n=20) - scipy.stats.wilcoxon returns p=1.0 for this exact all-zero
    input at n=5 but silently p=nan at n=20 (confirmed by direct
    experimentation), so the fix must not depend on sample size."""
    values = [0.0] * 20
    result = paired_comparison(values, values)
    assert result.p_value == pytest.approx(1.0)
    assert not np.isnan(result.p_value)
    assert result.test_used == "identical"


@pytest.mark.unit
def test_holm_correction_matches_known_values():
    # classic textbook example: raw p-values 0.01, 0.02, 0.03, 0.04
    raw = [0.01, 0.02, 0.03, 0.04]
    adjusted = holm_correction(raw)
    # Holm: sorted ascending, multiply by (n - rank): 4*0.01=0.04, 3*0.02=0.06, 2*0.03=0.06, 1*0.04=0.04
    # then enforce monotonicity (running max): 0.04, 0.06, 0.06, 0.06
    assert adjusted == pytest.approx([0.04, 0.06, 0.06, 0.06])


@pytest.mark.unit
def test_holm_correction_never_exceeds_one():
    adjusted = holm_correction([0.5, 0.6, 0.9])
    assert all(p <= 1.0 for p in adjusted)


@pytest.mark.unit
def test_holm_correction_on_empty_input():
    assert holm_correction([]) == []


@pytest.mark.unit
def test_compare_groups_pairwise_aligns_by_seed_and_applies_holm():
    rng = np.random.default_rng(3)
    seeds = list(range(20))
    rows = []
    for seed in seeds:
        base = rng.normal(loc=100.0, scale=5.0)
        rows.append({"strategy": "a", "seed": seed, "value": base})
        rows.append({"strategy": "b", "seed": seed, "value": base + 20.0})  # clearly better
        rows.append({"strategy": "c", "seed": seed, "value": base + 0.1})  # basically the same as a

    df = pd.DataFrame(rows)
    comparisons = compare_groups_pairwise(df, group_col="strategy", value_col="value", pair_on=["seed"])

    assert len(comparisons) == 3  # a-b, a-c, b-c
    assert "p_value_holm_adjusted" in comparisons.columns
    assert (comparisons["p_value_holm_adjusted"] >= comparisons["p_value"]).all()

    ab_row = comparisons[(comparisons["group_a"] == "a") & (comparisons["group_b"] == "b")].iloc[0]
    assert ab_row["mean_difference_b_minus_a"] == pytest.approx(20.0, abs=2.0)
    assert ab_row["p_value_holm_adjusted"] < 0.01


@pytest.mark.unit
def test_compare_groups_pairwise_skips_pairs_with_too_few_common_keys():
    df = pd.DataFrame([
        {"strategy": "a", "seed": 0, "value": 1.0},
        {"strategy": "b", "seed": 1, "value": 2.0},  # no shared seed with 'a'
    ])
    comparisons = compare_groups_pairwise(df, group_col="strategy", value_col="value", pair_on=["seed"])
    assert len(comparisons) == 0


@pytest.mark.unit
def test_compare_groups_pairwise_drops_nan_pairs_instead_of_reporting_bogus_significance():
    """Regression test (Fase J10): found empirically while analyzing F03 -
    when a whole condition is REJECTED (no simulation ran), its
    delivered_pairs/average_fidelity are NaN in the trial record.
    Comparing all-NaN vs. all-NaN used to silently produce p ~ 0.0 (from
    scipy.stats.wilcoxon returning nan without raising, masked into a
    bogus "significant" result by holm_correction's running-max step) -
    it must instead be skipped (too few valid pairs), and a comparison
    with a few real NaNs mixed in must drop only those pairs."""
    rows = []
    for seed in range(20):
        rows.append({"policy": "rejected_always", "seed": seed, "value": np.nan})
        rows.append({"policy": "rejected_always_2", "seed": seed, "value": np.nan})
    df_all_nan = pd.DataFrame(rows)
    comparisons = compare_groups_pairwise(df_all_nan, group_col="policy", value_col="value", pair_on=["seed"])
    assert len(comparisons) == 0  # no valid pairs to compare at all

    rows = []
    for seed in range(20):
        rows.append({"policy": "a", "seed": seed, "value": 10.0 + seed * 0.01})
        # 'b' fails (NaN) for half the seeds, succeeds for the other half
        b_value = np.nan if seed < 10 else 10.0 + seed * 0.01
        rows.append({"policy": "b", "seed": seed, "value": b_value})
    df_partial_nan = pd.DataFrame(rows)
    comparisons = compare_groups_pairwise(df_partial_nan, group_col="policy", value_col="value", pair_on=["seed"])
    assert len(comparisons) == 1
    assert comparisons.iloc[0]["n"] == 10  # only the 10 seeds where both sides had a real value
