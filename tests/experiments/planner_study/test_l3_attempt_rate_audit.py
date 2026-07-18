"""Unit tests for `scripts/audit_l3_attempt_rate.py`'s core logic -
the naive attempt-rate formula's round-trip-multiplier parameterization,
using small synthetic data (the real audit's numbers come from frozen
F02/F03 data - see docs/l3_attempt_rate_audit.md for those)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from audit_l3_attempt_rate import CLASSICAL_DELAY_S, naive_attempt_rate  # noqa: E402


@pytest.mark.unit
def test_naive_attempt_rate_scales_with_reserved_memory_slots():
    rate_1 = naive_attempt_rate(reserved_memory_slots=1, round_trip_multiplier=2)
    rate_10 = naive_attempt_rate(reserved_memory_slots=10, round_trip_multiplier=2)
    assert rate_10 == pytest.approx(rate_1 * 10)


@pytest.mark.unit
def test_naive_attempt_rate_decreases_with_round_trip_multiplier():
    rate_m2 = naive_attempt_rate(reserved_memory_slots=10, round_trip_multiplier=2)
    rate_m7 = naive_attempt_rate(reserved_memory_slots=10, round_trip_multiplier=7)
    assert rate_m7 < rate_m2


@pytest.mark.unit
def test_naive_attempt_rate_matches_hand_computed_value():
    # 10 slots / (2 * 1e-4) = 50000
    assert naive_attempt_rate(reserved_memory_slots=10, round_trip_multiplier=2) == pytest.approx(50000.0)
    # 10 slots / (7.32 * 1e-4) ~= 13661.2
    assert naive_attempt_rate(reserved_memory_slots=10, round_trip_multiplier=7.32) == pytest.approx(13661.2, rel=1e-3)


@pytest.mark.unit
def test_classical_delay_constant_matches_project_scenarios():
    """The audit's fixed classical_delay_s must match what the actual
    frozen F02/F03 campaigns used (configs/campaigns/scenarios/*.yaml,
    demos.topologies default) - if this drifts, the whole audit is
    comparing against the wrong baseline."""
    assert CLASSICAL_DELAY_S == 1e-4
