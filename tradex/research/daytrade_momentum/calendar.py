"""Exchange calendar, session adjacency, and regular-session grid utilities."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

CALENDAR_KEY = "XNYS"
MARKET_TIMEZONE = ZoneInfo("America/New_York")
REGULAR_MARKET_OPEN = time(9, 30)
REGULAR_MARKET_CLOSE = time(16, 0)
EXPECTED_REGULAR_MINUTES = 390

_CALENDAR_INSTANCE: Any = None


def get_exchange_calendar() -> Any:
    """Return the cached exchange_calendars instance for XNYS."""
    global _CALENDAR_INSTANCE
    if _CALENDAR_INSTANCE is None:
        _CALENDAR_INSTANCE = xcals.get_calendar(CALENDAR_KEY)
    return _CALENDAR_INSTANCE


def to_market_time(dt: datetime) -> datetime:
    """Convert any aware or naive UTC datetime to America/New_York timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(MARKET_TIMEZONE)


def to_utc(dt: datetime) -> datetime:
    """Convert any datetime to UTC timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MARKET_TIMEZONE)
    return dt.astimezone(UTC)


def is_regular_trading_session(session_date: date) -> bool:
    """Return True if session_date is a regular XNYS trading session."""
    cal = get_exchange_calendar()
    return bool(cal.is_session(str(session_date)))


is_trading_session = is_regular_trading_session


def is_early_close_session(session_date: date) -> bool:
    """Return True if session_date is an XNYS session that closes before 16:00 ET."""
    if not is_regular_trading_session(session_date):
        return False
    cal = get_exchange_calendar()
    ts = pd.Timestamp(session_date)
    close_local = cal.session_close(ts).to_pydatetime().astimezone(MARKET_TIMEZONE)
    return close_local.time() < REGULAR_MARKET_CLOSE


def get_regular_trading_sessions(
    start_date: date | str,
    end_date: date | str,
    exclude_early_closes: bool = True,
) -> list[date]:
    """Return chronologically ordered list of valid regular trading sessions.

    Excludes weekends, exchange holidays, and optionally early-close sessions.
    """
    cal = get_exchange_calendar()
    start_str = str(start_date)
    end_str = str(end_date)
    sessions_ts = cal.sessions_in_range(start_str, end_str)

    sessions: list[date] = []
    for s_ts in sessions_ts:
        d = s_ts.date()
        if exclude_early_closes and is_early_close_session(d):
            continue
        sessions.append(d)
    return sessions


def get_immediately_preceding_regular_session(
    session_date: date,
    exclude_early_closes: bool = True,
) -> date | None:
    """Return the exact immediately preceding regular XNYS session.

    Under XNYS:
    Monday -> Friday (intervening weekend days are skipped).
    Next day after holiday -> session prior to holiday.
    Does not jump over missing or defect sessions in dataset; strictly returns the calendar predecessor.
    """
    cal = get_exchange_calendar()
    ts = pd.Timestamp(session_date)
    if not cal.is_session(ts):
        # Find latest session strictly before session_date
        sessions = cal.sessions_in_range(
            str(session_date - timedelta(days=30)),
            str(session_date - timedelta(days=1)),
        )
        if len(sessions) == 0:
            return None
        candidate = sessions[-1].date()
    else:
        prev_ts = cal.previous_session(ts)
        candidate = prev_ts.date()

    if exclude_early_closes and is_early_close_session(candidate):
        # If the immediately preceding session was an early close and early closes are excluded from regular study
        return candidate

    return candidate


def build_regular_session_grid(session_date: date) -> list[datetime]:
    """Generate the exact 390 expected 1-minute bar start timestamps for an XNYS regular session.

    Timestamps represent interval left edge [09:30:00 ET, 15:59:00 ET] inclusive.
    Returned as timezone-aware UTC datetimes.
    """
    dt_start = datetime.combine(session_date, REGULAR_MARKET_OPEN, tzinfo=MARKET_TIMEZONE)
    grid_utc: list[datetime] = []
    for minute_idx in range(EXPECTED_REGULAR_MINUTES):
        dt_local = dt_start + timedelta(minutes=minute_idx)
        grid_utc.append(dt_local.astimezone(UTC))
    return grid_utc
