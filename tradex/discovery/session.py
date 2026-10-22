"""Market session utilities for completed-session daily discovery (LONG-MVP-003).

Ensures all market-wide discovery and daily-bar scoring evaluate the applicable
completed regular-market NYSE/XNYS session. Never mixes incomplete current-session
candles with completed historical sessions.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

import pandas as pd

from tradex.market.hours import (
    MARKET_TIMEZONE,
    MarketSession,
    get_market_session,
    is_trading_day,
    previous_trading_session,
)


def get_applicable_completed_session(as_of: datetime | None = None) -> MarketSession:
    """Identify the applicable completed U.S. regular-market trading session.

    Rules:
      - All evaluations convert to ``America/New_York``. Naive datetimes raise ValueError.
      - If ``as_of`` is omitted, the current aware UTC time converted to NY is used.
      - If the evaluation day is an NYSE trading day and ``as_of >= session.closes_at``,
        today's session is completed and returned.
      - If the evaluation day is an NYSE trading day but ``as_of < session.closes_at``
        (e.g., 8:00 AM ET pre-market or during the active session), today's candle
        is incomplete, so the previous completed session is returned.
      - If the evaluation day is a weekend or market holiday, the previous completed
        session is returned.
    """
    if as_of is None:
        as_of = datetime.now(UTC)
    if as_of.tzinfo is None:
        raise ValueError("as_of must be a timezone-aware datetime; naive datetimes are not accepted.")

    ny_dt = as_of.astimezone(MARKET_TIMEZONE)
    day = ny_dt.date()

    if is_trading_day(day):
        session = get_market_session(day)
        if session is not None and ny_dt >= session.closes_at:
            return session
        return previous_trading_session(day)

    return previous_trading_session(day)


def _bar_date_in_market_tz(ts: Any) -> date:
    """Extract calendar date in America/New_York for a pandas Timestamp or datetime."""
    if isinstance(ts, pd.Timestamp):
        if ts.tz is not None:
            if ts.time() == time(0, 0, 0) and str(ts.tz) == "UTC":
                return ts.date()
            return ts.tz_convert(MARKET_TIMEZONE).date()
        return ts.date()
    if isinstance(ts, datetime):
        if ts.tzinfo is not None:
            if ts.time() == time(0, 0, 0) and ts.tzinfo == UTC:
                return ts.date()
            return ts.astimezone(MARKET_TIMEZONE).date()
        return ts.date()
    if isinstance(ts, date):
        return ts
    parsed = pd.to_datetime(ts)
    if parsed.tz is not None:
        if parsed.time() == time(0, 0, 0) and str(parsed.tz) == "UTC":
            return parsed.date()
        return parsed.tz_convert(MARKET_TIMEZONE).date()
    return parsed.date()


def filter_completed_daily_bars(
    df: pd.DataFrame, session_date: date
) -> tuple[pd.DataFrame, date | None, bool]:
    """Filter daily bars to exclude incomplete sessions and detect stale provider data.

    Returns:
      (filtered_df, latest_bar_date, is_current)
      where:
        - filtered_df: slice of df retaining bars on or before session_date.
        - latest_bar_date: the calendar date of the latest bar in filtered_df, or None if empty.
        - is_current: True if latest_bar_date equals session_date; False if stale or empty.
    """
    if df.empty:
        return df.copy(), None, False

    # Extract NY date for each bar in the index.
    dates = [_bar_date_in_market_tz(idx) for idx in df.index]
    dates_series = pd.Series(dates, index=df.index)

    # Exclude any bar strictly after session_date (incomplete current-session candle).
    valid_mask = dates_series <= session_date
    if not valid_mask.any():
        empty_slice = df.iloc[0:0].copy()
        return empty_slice, None, False

    filtered_df = df[valid_mask].copy()
    latest_bar_date = dates_series[valid_mask].iloc[-1]
    is_current = (latest_bar_date == session_date)

    return filtered_df, latest_bar_date, is_current
