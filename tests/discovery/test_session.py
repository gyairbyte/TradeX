"""Tests for completed-session determination and daily bar filtering (LONG-MVP-003)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from tradex.discovery.session import (
    filter_completed_daily_bars,
    get_applicable_completed_session,
)
from tradex.market.hours import MARKET_TIMEZONE


def test_get_applicable_completed_session_rejects_naive():
    """Naive datetime raises ValueError."""
    with pytest.raises(ValueError, match="timezone-aware"):
        get_applicable_completed_session(datetime(2026, 10, 21, 8, 0, 0))  # noqa: DTZ001


def test_pre_market_8am_uses_previous_trading_day():
    """At 8:00 AM ET on Wednesday Oct 21 2026, completed session is Tuesday Oct 20 2026."""
    # 2026-10-21 was a Wednesday.
    wed_8am = datetime(2026, 10, 21, 8, 0, 0, tzinfo=MARKET_TIMEZONE)
    session = get_applicable_completed_session(wed_8am)
    assert session.session_date == date(2026, 10, 20)


def test_during_regular_hours_uses_previous_trading_day():
    """At 2:00 PM ET on Wednesday Oct 21 2026, today's candle is incomplete -> Tuesday session."""
    wed_2pm = datetime(2026, 10, 21, 14, 0, 0, tzinfo=MARKET_TIMEZONE)
    session = get_applicable_completed_session(wed_2pm)
    assert session.session_date == date(2026, 10, 20)


def test_after_market_close_uses_current_trading_day():
    """At 5:00 PM ET on Wednesday Oct 21 2026, Wednesday's session is completed."""
    wed_5pm = datetime(2026, 10, 21, 17, 0, 0, tzinfo=MARKET_TIMEZONE)
    session = get_applicable_completed_session(wed_5pm)
    assert session.session_date == date(2026, 10, 21)


def test_weekend_uses_previous_friday():
    """On Saturday Oct 24 2026 at 11:00 AM ET, completed session is Friday Oct 23 2026."""
    sat_11am = datetime(2026, 10, 24, 11, 0, 0, tzinfo=MARKET_TIMEZONE)
    session = get_applicable_completed_session(sat_11am)
    assert session.session_date == date(2026, 10, 23)

    sun_11am = datetime(2026, 10, 25, 11, 0, 0, tzinfo=MARKET_TIMEZONE)
    session_sun = get_applicable_completed_session(sun_11am)
    assert session_sun.session_date == date(2026, 10, 23)


def test_exchange_holiday_uses_previous_trading_session():
    """On Labor Day (Monday Sep 7 2026), completed session is Friday Sep 4 2026."""
    labor_day = datetime(2026, 9, 7, 10, 0, 0, tzinfo=MARKET_TIMEZONE)
    session = get_applicable_completed_session(labor_day)
    assert session.session_date == date(2026, 9, 4)


def test_filter_completed_daily_bars_excludes_incomplete_today_bar():
    """Bars after the completed session date are dropped from daily data."""
    # Suppose completed session is 2026-10-20.
    # Provider returns bars up to 2026-10-21 (today's incomplete bar).
    dates = pd.date_range("2026-10-15", "2026-10-21", freq="B", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0] * len(dates),
            "high": [105.0] * len(dates),
            "low": [99.0] * len(dates),
            "close": [102.0] * len(dates),
            "volume": [1_000_000] * len(dates),
        },
        index=dates,
    )
    completed_session = date(2026, 10, 20)

    filtered_df, latest_bar_date, is_current = filter_completed_daily_bars(df, completed_session)
    assert is_current is True
    assert latest_bar_date == date(2026, 10, 20)
    assert len(filtered_df) == len(df) - 1
    assert filtered_df.index[-1].date() == date(2026, 10, 20)


def test_filter_completed_daily_bars_detects_stale_provider_data():
    """If provider's latest bar date is older than completed session, flagged as not current."""
    completed_session = date(2026, 10, 20)
    # Stale dataset ending on 2026-10-16
    dates = pd.date_range("2026-10-10", "2026-10-16", freq="B", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0] * len(dates),
            "high": [105.0] * len(dates),
            "low": [99.0] * len(dates),
            "close": [102.0] * len(dates),
            "volume": [1_000_000] * len(dates),
        },
        index=dates,
    )

    filtered_df, latest_bar_date, is_current = filter_completed_daily_bars(df, completed_session)
    assert is_current is False
    assert latest_bar_date == date(2026, 10, 16)
    assert len(filtered_df) == len(df)


def test_filter_completed_daily_bars_handles_tz_differences():
    """UTC vs America/New_York timestamps correctly map to market session dates."""
    # Daily bars at 04:00 UTC (which corresponds to 00:00 EDT)
    dates = pd.DatetimeIndex([
        datetime(2026, 10, 19, 4, 0, tzinfo=UTC),
        datetime(2026, 10, 20, 4, 0, tzinfo=UTC),
    ])
    df = pd.DataFrame(
        {
            "open": [10.0, 11.0],
            "high": [12.0, 13.0],
            "low": [9.0, 10.0],
            "close": [11.0, 12.0],
            "volume": [500000, 600000],
        },
        index=dates,
    )
    completed_session = date(2026, 10, 20)

    filtered_df, latest_bar_date, is_current = filter_completed_daily_bars(df, completed_session)
    assert is_current is True
    assert latest_bar_date == date(2026, 10, 20)
    assert len(filtered_df) == 2
