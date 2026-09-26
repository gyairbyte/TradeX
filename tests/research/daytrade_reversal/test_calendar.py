"""Calendar and session normalization tests."""
from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from tradex.research.daytrade_reversal.calendar import (
    CalendarError,
    bar_available_at,
    build_regular_session_grid,
    get_regular_trading_sessions,
    is_early_close_session,
    is_trading_session,
    to_market_time,
)


def test_regular_session_has_390_bars() -> None:
    """A standard full NYSE session (2025-01-02) has exactly 390 1-minute bars."""
    session_d = date(2025, 1, 2)
    assert is_trading_session(session_d)
    assert not is_early_close_session(session_d)

    grid = build_regular_session_grid(session_d)
    assert len(grid) == 390

    # First bar starts at 09:30 ET
    first_local = to_market_time(grid[0])
    assert first_local.time() == time(9, 30)

    # Last bar starts at 15:59 ET
    last_local = to_market_time(grid[-1])
    assert last_local.time() == time(15, 59)


def test_bar_available_at_is_plus_one_minute() -> None:
    """available_at is exactly bar_start + 1 minute."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)
    first_bar = grid[0]
    avail = bar_available_at(first_bar)
    assert avail == first_bar + timedelta(minutes=1)


def test_early_close_sessions_excluded_in_full() -> None:
    """Early close session (e.g. 2024-12-24 Christmas Eve) raises CalendarError."""
    christmas_eve = date(2024, 12, 24)
    assert is_trading_session(christmas_eve)
    assert is_early_close_session(christmas_eve)

    with pytest.raises(CalendarError, match="early-close session"):
        build_regular_session_grid(christmas_eve)


def test_weekend_raises_calendar_error() -> None:
    """A weekend date (2025-01-04) raises CalendarError."""
    weekend = date(2025, 1, 4)
    assert not is_trading_session(weekend)
    with pytest.raises(CalendarError, match="not an XNYS trading session"):
        build_regular_session_grid(weekend)


def test_get_regular_trading_sessions_excludes_early_closes() -> None:
    """Session search excludes early close sessions by default."""
    # Thanksgiving week 2024: 2024-11-28 (closed), 2024-11-29 (early close 13:00)
    start = date(2024, 11, 25)
    end = date(2024, 11, 29)
    sessions = get_regular_trading_sessions(start, end, exclude_early_close=True)
    assert date(2024, 11, 29) not in sessions
