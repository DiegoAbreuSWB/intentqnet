"""Tests for `ibqn.utils.power.keep_system_awake` - it must never get in a
campaign's way, whatever the platform answers."""
from __future__ import annotations

import sys

import pytest

from ibqn.utils.power import keep_system_awake


@pytest.mark.unit
def test_disabled_request_is_a_no_op():
    with keep_system_awake(False) as accepted:
        assert accepted is False


@pytest.mark.unit
def test_request_is_accepted_on_windows_and_harmless_elsewhere():
    with keep_system_awake() as accepted:
        assert accepted is (sys.platform == "win32")
    with keep_system_awake() as again:      # re-entrant: releasing the first request did not break the second
        assert again is (sys.platform == "win32")


@pytest.mark.unit
def test_the_request_is_released_even_when_the_campaign_raises():
    with pytest.raises(RuntimeError, match="campaign failed"):
        with keep_system_awake():
            raise RuntimeError("campaign failed")
    with keep_system_awake() as accepted:   # still usable afterwards
        assert accepted is (sys.platform == "win32")
