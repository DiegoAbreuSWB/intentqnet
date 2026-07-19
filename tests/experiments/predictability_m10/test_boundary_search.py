"""Unit tests for M10.4-M10.5's boundary-search helpers
(scripts/search_transition_region.py) - Wilson confidence intervals and
the five-region classification (section 7 of the governing brief)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from search_transition_region import classify_region, wilson_ci  # noqa: E402


@pytest.mark.unit
def test_wilson_ci_zero_trials_returns_full_range():
    lo, hi = wilson_ci(0, 0)
    assert lo == 0.0
    assert hi == 1.0


@pytest.mark.unit
def test_wilson_ci_all_successes_has_lower_bound_below_one():
    """Even 100% observed success with finite n never yields a
    zero-width [1,1] interval - Wilson correctly reflects residual
    uncertainty from a finite sample."""
    lo, hi = wilson_ci(10, 10)
    assert 0.0 < lo < 1.0
    assert hi == pytest.approx(1.0)


@pytest.mark.unit
def test_wilson_ci_all_failures_has_upper_bound_above_zero():
    lo, hi = wilson_ci(0, 10)
    assert lo == 0.0
    assert 0.0 < hi < 1.0


@pytest.mark.unit
def test_wilson_ci_widens_with_fewer_trials():
    lo_small, hi_small = wilson_ci(5, 10)
    lo_large, hi_large = wilson_ci(50, 100)
    assert (hi_small - lo_small) > (hi_large - lo_large)


@pytest.mark.unit
def test_wilson_ci_brackets_point_estimate():
    lo, hi = wilson_ci(7, 10)
    assert lo <= 0.7 <= hi


@pytest.mark.unit
@pytest.mark.parametrize("p_hat,ci_lo,ci_hi,expected", [
    (1.0, 0.95, 1.0, "ROBUST_SUCCESS"),
    (0.0, 0.0, 0.05, "ROBUST_FAILURE"),
    (0.8, 0.5, 0.94, "LIKELY_SUCCESS"),
    (0.5, 0.2, 0.8, "TRANSITION"),
    (0.15, 0.06, 0.3, "LIKELY_FAILURE"),
])
def test_classify_region_matches_section_7_definitions(p_hat, ci_lo, ci_hi, expected):
    assert classify_region(p_hat, ci_lo, ci_hi) == expected


@pytest.mark.unit
def test_classify_region_never_uses_point_estimate_alone_for_robust_categories():
    """A point estimate of exactly 1.0 with a WIDE CI (small n, e.g.
    lower bound well below 0.95) must NOT be classified ROBUST_SUCCESS -
    section 7 explicitly requires the CI bound, not just the estimate."""
    # p_hat=1.0 but only 2/2 trials -> Wilson CI lower bound is well below 0.95
    lo, hi = wilson_ci(2, 2)
    assert lo < 0.95
    assert classify_region(1.0, lo, hi) != "ROBUST_SUCCESS"
    assert classify_region(1.0, lo, hi) == "LIKELY_SUCCESS"
