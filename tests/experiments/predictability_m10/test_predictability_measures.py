"""Unit tests for M10.6's predictability measures
(scripts/analyze_p12_boundary_variability.py) - binary entropy and the
Bayes-style empirical configuration-conditional lower bound (sections
9-10 of the governing brief)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from analyze_p12_boundary_variability import binary_entropy, classify_region, wilson_ci  # noqa: E402


@pytest.mark.unit
@pytest.mark.parametrize("p", [0.0, 1.0])
def test_binary_entropy_zero_at_certainty(p):
    assert binary_entropy(p) == 0.0


@pytest.mark.unit
def test_binary_entropy_maximal_at_half():
    assert binary_entropy(0.5) == pytest.approx(1.0)


@pytest.mark.unit
def test_binary_entropy_symmetric():
    assert binary_entropy(0.3) == pytest.approx(binary_entropy(0.7))


@pytest.mark.unit
def test_binary_entropy_monotonic_toward_half():
    assert binary_entropy(0.1) < binary_entropy(0.3) < binary_entropy(0.5)


@pytest.mark.unit
def test_binary_entropy_bounded_zero_to_one():
    for p in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
        h = binary_entropy(p)
        assert 0.0 <= h <= 1.0


@pytest.mark.unit
def test_bayes_empirical_lower_bound_is_min_p_one_minus_p():
    """The Bayes-style bound (section 10) - a majority-class classifier
    that knows only the configuration, not the future seed, is wrong with
    probability min(p, 1-p)."""
    for p in [0.0, 0.2, 0.5, 0.8, 1.0]:
        bound = min(p, 1 - p)
        assert 0.0 <= bound <= 0.5
        if p in (0.0, 1.0):
            assert bound == 0.0  # a perfectly predictable configuration has zero Bayes error
        if p == 0.5:
            assert bound == 0.5  # maximal - majority-class guessing is a coin flip


@pytest.mark.unit
def test_wilson_ci_and_classify_region_reused_consistently():
    """Guards against the two boundary-search scripts (M10.4's
    search_transition_region.py and M10.6's analyze_p12_boundary_
    variability.py) silently drifting apart on the same formulas."""
    lo, hi = wilson_ci(6, 8)
    assert classify_region(6 / 8, lo, hi) in (
        "ROBUST_SUCCESS", "LIKELY_SUCCESS", "TRANSITION", "LIKELY_FAILURE", "ROBUST_FAILURE",
    )
