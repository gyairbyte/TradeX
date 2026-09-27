"""Tests for XNYS calendar, DST, early close, and boundary purge logic."""
from __future__ import annotations

from tradex.research.long_002c.calendar import (
    check_split_boundary_purge,
    get_decision_timestamp_utc,
    get_forward_sessions,
    get_next_session,
    is_early_close,
    is_trading_session,
)


def test_xnys_trading_sessions() -> None:
    """Verify standard session detection and holidays."""
    assert is_trading_session("2016-01-04") is True
    # Weekend
    assert is_trading_session("2016-01-02") is False
    assert is_trading_session("2016-01-03") is False
    # Martin Luther King Jr. Day 2016-01-18
    assert is_trading_session("2016-01-18") is False


def test_next_and_forward_sessions() -> None:
    """Verify session walking across weekends and holidays."""
    # Next session after Friday 2016-01-15 is Tuesday 2016-01-19 (Monday was MLK)
    next_s = get_next_session("2016-01-15")
    assert next_s == "2016-01-19"

    forward_5 = get_forward_sessions("2016-01-04", 5)
    assert len(forward_5) == 5
    assert forward_5 == ["2016-01-05", "2016-01-06", "2016-01-07", "2016-01-08", "2016-01-11"]


def test_early_close_detection() -> None:
    """Verify early close (13:00 ET) on Black Friday 2016-11-25."""
    assert is_early_close("2016-11-25") is True
    # Normal day
    assert is_early_close("2016-11-23") is False


def test_decision_timestamp_dst_conversion() -> None:
    """Verify America/New_York DST transitions to UTC."""
    # EDT (summer): UTC-4 -> 20:30 EDT is 00:30 UTC next day
    ts_edt = get_decision_timestamp_utc("2016-06-15", "20:30")
    assert ts_edt == "2016-06-16T00:30:00Z"

    # EST (winter): UTC-5 -> 20:30 EST is 01:30 UTC next day
    ts_est = get_decision_timestamp_utc("2016-01-15", "20:30")
    assert ts_est == "2016-01-16T01:30:00Z"

    # Morning cutoff 09:00 EDT -> 13:00 UTC
    ts_morning = get_decision_timestamp_utc("2016-06-15", "09:00")
    assert ts_morning == "2016-06-15T13:00:00Z"


def test_boundary_purge_forward_walk() -> None:
    """Verify 26-session boundary purge logic at the end of development split."""
    # Mid-2020: 26 forward sessions finish comfortably in 2020 -> not purged
    assert check_split_boundary_purge("2020-06-01") is False

    # 2020-12-30: 26 forward sessions cross into 2021 -> PURGED
    assert check_split_boundary_purge("2020-12-30") is True

    # November 2020: 26 forward sessions reach 2021 -> PURGED
    assert check_split_boundary_purge("2020-11-25") is True
