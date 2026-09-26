"""XNYS regular-session grid and market-calendar normalization."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as ec
import pandas as pd

MARKET_TIMEZONE = ZoneInfo("America/New_York")
CALENDAR_NAME = "XNYS"
EXPECTED_REGULAR_MINUTES = 390
BAR_TIMEFRAME = timedelta(minutes=1)


class CalendarError(Exception):
    """Raised for unsupported or abnormal calendar conditions."""


@lru_cache(maxsize=1)
def get_exchange_calendar() -> ec.ExchangeCalendar:
    """Return the cached XNYS exchange calendar."""
    return ec.get_calendar(CALENDAR_NAME)


def to_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware and converted to UTC."""
    if dt.tzinfo is None:
        raise ValueError("Naive datetime is prohibited; timezone-aware required.")
    return dt.astimezone(UTC)


def to_market_time(dt: datetime) -> datetime:
    """Convert a timezone-aware datetime to America/New_York."""
    if dt.tzinfo is None:
        raise ValueError("Naive datetime is prohibited; timezone-aware required.")
    return dt.astimezone(MARKET_TIMEZONE)


def is_trading_session(session_date: date) -> bool:
    """Return True if session_date is a valid XNYS trading session."""
    cal = get_exchange_calendar()
    ts = pd.Timestamp(session_date)
    return bool(cal.is_session(ts))


def is_early_close_session(session_date: date) -> bool:
    """Return True if session_date is an early-close XNYS session."""
    cal = get_exchange_calendar()
    ts = pd.Timestamp(session_date)
    if not cal.is_session(ts):
        return False
    close_dt = cal.session_close(ts).to_pydatetime().astimezone(MARKET_TIMEZONE)
    return close_dt.time() < time(16, 0)


def build_regular_session_grid(session_date: date) -> list[datetime]:
    """Construct the exact 390 1-minute regular-session bar-start timestamps (UTC).

    Raises CalendarError if session_date is not a session or is an early close.
    """
    if not is_trading_session(session_date):
        raise CalendarError(f"{session_date} is not an XNYS trading session")
    if is_early_close_session(session_date):
        raise CalendarError(f"{session_date} is an early-close session; excluded in full")

    cal = get_exchange_calendar()
    ts = pd.Timestamp(session_date)
    open_local = cal.session_open(ts).to_pydatetime().astimezone(MARKET_TIMEZONE)
    close_local = cal.session_close(ts).to_pydatetime().astimezone(MARKET_TIMEZONE)

    grid = pd.date_range(
        start=open_local,
        end=close_local,
        freq="1min",
        inclusive="left",
        tz=MARKET_TIMEZONE,
    )
    if len(grid) != EXPECTED_REGULAR_MINUTES:
        raise CalendarError(
            f"Expected {EXPECTED_REGULAR_MINUTES} bars for {session_date}, got {len(grid)}"
        )

    return [t.to_pydatetime().astimezone(UTC) for t in grid]


def get_regular_trading_sessions(
    start_date: date,
    end_date: date,
    *,
    exclude_early_close: bool = True,
) -> list[date]:
    """Return sorted list of regular trading session dates in [start_date, end_date]."""
    cal = get_exchange_calendar()
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    sessions = cal.sessions_in_range(start_ts, end_ts)

    valid_dates: list[date] = []
    for s in sessions:
        d = s.date()
        if exclude_early_close and is_early_close_session(d):
            continue
        valid_dates.append(d)
    return sorted(valid_dates)


def bar_available_at(bar_start: datetime) -> datetime:
    """Return available_at timestamp for a 1-minute bar (bar_start + 1 minute)."""
    return to_utc(bar_start + BAR_TIMEFRAME)
