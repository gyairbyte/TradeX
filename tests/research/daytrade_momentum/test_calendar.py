"""Tests for calendar, session adjacency, and regular-session grid generation."""
from __future__ import annotations

from datetime import UTC, date, datetime, time

from tradex.research.daytrade_momentum.calendar import (
    EXPECTED_REGULAR_MINUTES,
    MARKET_TIMEZONE,
    build_regular_session_grid,
    get_immediately_preceding_regular_session,
    get_regular_trading_sessions,
    is_early_close_session,
    is_regular_trading_session,
    to_market_time,
    to_utc,
)


def test_regular_session_grid_exact_390_bars() -> None:
    """Verify that a regular XNYS session produces exactly 390 left-edge bars."""
    session_d = date(2025, 1, 15)  # Normal Wednesday
    grid = build_regular_session_grid(session_d)

    assert len(grid) == EXPECTED_REGULAR_MINUTES
    assert len(grid) == 390

    # First bar is 09:30:00 ET
    first_local = to_market_time(grid[0])
    assert first_local.time() == time(9, 30)
    assert first_local.tzinfo == MARKET_TIMEZONE

    # Last bar is 15:59:00 ET (representing interval [15:59:00, 16:00:00))
    last_local = to_market_time(grid[-1])
    assert last_local.time() == time(15, 59)

    # Key signal and execution bars exist at exact expected indices
    bar_09_59 = to_market_time(grid[29])
    assert bar_09_59.time() == time(9, 59)

    bar_15_30 = to_market_time(grid[360])
    assert bar_15_30.time() == time(15, 30)


def test_timezone_conversion_roundtrip() -> None:
    """Verify to_market_time and to_utc timezone conversions."""
    dt_utc = datetime(2025, 1, 15, 14, 30, tzinfo=UTC)  # 09:30 ET
    dt_ny = to_market_time(dt_utc)
    assert dt_ny.hour == 9
    assert dt_ny.minute == 30

    dt_back = to_utc(dt_ny)
    assert dt_back == dt_utc


def test_early_close_and_holiday_detection() -> None:
    """Verify early-close sessions (< 16:00 close) and exchange holidays."""
    # Christmas Eve 2024 was Tuesday 2024-12-24 (early close at 13:00 ET)
    xmas_eve = date(2024, 12, 24)
    assert is_regular_trading_session(xmas_eve) is True
    assert is_early_close_session(xmas_eve) is True

    # Day after Thanksgiving 2024 (Friday 2024-11-29, early close)
    bf = date(2024, 11, 29)
    assert is_early_close_session(bf) is True

    # New Year's Day 2025 (Wednesday 2025-01-01, holiday)
    new_year = date(2025, 1, 1)
    assert is_regular_trading_session(new_year) is False
    assert is_early_close_session(new_year) is False


def test_immediately_preceding_regular_session() -> None:
    """Verify immediately preceding regular session lookup across weekends and holidays."""
    # Monday -> Friday
    mon = date(2025, 1, 13)
    fri = get_immediately_preceding_regular_session(mon)
    assert fri == date(2025, 1, 10)

    # MLK Day was Monday 2025-01-20 (holiday)
    # Tuesday 2025-01-21 -> Friday 2025-01-17
    tue_post_mlk = date(2025, 1, 21)
    prev = get_immediately_preceding_regular_session(tue_post_mlk)
    assert prev == date(2025, 1, 17)


def test_get_regular_trading_sessions_excludes_early_closes() -> None:
    """Verify get_regular_trading_sessions excludes weekends, holidays, and early closes."""
    # Range spanning Thanksgiving 2024 (Thu Nov 28 holiday, Fri Nov 29 early close)
    sessions = get_regular_trading_sessions(
        start_date=date(2024, 11, 27),
        end_date=date(2024, 12, 2),
        exclude_early_closes=True,
    )
    # Wednesday Nov 27 and Monday Dec 2 should be included
    assert date(2024, 11, 27) in sessions
    assert date(2024, 12, 2) in sessions
    # Thanksgiving Nov 28 and Black Friday Nov 29 should NOT be included
    assert date(2024, 11, 28) not in sessions
    assert date(2024, 11, 29) not in sessions
