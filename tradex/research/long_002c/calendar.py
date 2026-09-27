"""Exchange calendar (XNYS) handling, trading session walking, and timezone conversions.

Handles America/New_York DST transitions, early closes (13:00 ET), and forward horizon purging.
"""
from __future__ import annotations

from datetime import datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as ec
import pandas as pd

from tradex.research.long_002c.spec import (
    DEV_END,
    TOTAL_FORWARD_SESSIONS_REQUIRED,
)

NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")


@lru_cache(maxsize=1)
def get_xnys_calendar() -> ec.ExchangeCalendar:
    """Return cached XNYS exchange calendar."""
    return ec.get_calendar("XNYS")


def get_trading_sessions(start_date: str, end_date: str) -> list[str]:
    """Return list of XNYS trading session dates (YYYY-MM-DD) inclusive."""
    cal = get_xnys_calendar()
    sessions = cal.sessions_in_range(start_date, end_date)
    return [s.strftime("%Y-%m-%d") for s in sessions]


def is_trading_session(date_str: str) -> bool:
    """Return True if date_str is an XNYS trading session."""
    cal = get_xnys_calendar()
    ts = pd.Timestamp(date_str)
    return cal.is_session(ts)


def get_next_session(date_str: str) -> str:
    """Return the next regular XNYS trading session after date_str."""
    cal = get_xnys_calendar()
    ts = pd.Timestamp(date_str)
    next_ts = cal.next_session(ts)
    return next_ts.strftime("%Y-%m-%d")


def get_forward_sessions(date_str: str, n_sessions: int) -> list[str]:
    """Return the next n_sessions trading session dates strictly after date_str."""
    cal = get_xnys_calendar()
    ts = pd.Timestamp(date_str)
    # Get range from next session forward
    next_ts = cal.next_session(ts)
    # To be safe, look ahead up to n_sessions * 3 calendar days
    end_lookahead = next_ts + pd.Timedelta(days=n_sessions * 3 + 10)
    sessions = cal.sessions_in_range(next_ts, end_lookahead)
    forward_list = [s.strftime("%Y-%m-%d") for s in sessions[:n_sessions]]
    if len(forward_list) < n_sessions:
        raise ValueError(f"Could not find {n_sessions} forward sessions after {date_str}")
    return forward_list


def is_early_close(session_date: str) -> bool:
    """Return True if session_date has a scheduled early close (e.g. 13:00 ET)."""
    cal = get_xnys_calendar()
    ts = pd.Timestamp(session_date)
    if not cal.is_session(ts):
        return False
    close_dt = cal.session_close(ts)
    # Convert close_dt to New York timezone
    ny_close = close_dt.tz_convert(NY_TZ)
    return ny_close.time() < time(16, 0)


def get_decision_timestamp_utc(session_date: str, cutoff_time: str = "20:30") -> str:
    """Convert session date and cutoff time (in America/New_York) to ISO-8601 UTC timestamp.

    Cutoff time format: "20:30" or "09:00".
    """
    parts = cutoff_time.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    dt_parts = [int(p) for p in session_date.split("-")]

    local_dt = datetime(dt_parts[0], dt_parts[1], dt_parts[2], hour, minute, tzinfo=NY_TZ)
    utc_dt = local_dt.astimezone(UTC_TZ)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def check_split_boundary_purge(
    as_of_date: str,
    dev_end: str = DEV_END,
    forward_sessions_required: int = TOTAL_FORWARD_SESSIONS_REQUIRED,
) -> bool:
    """Determine whether an observation must be purged due to forward window crossing 2021-01-01.

    Requires 26 forward sessions (5 entry window + 21 outcome window) to end on or before dev_end.
    If the 26th forward session is > dev_end, returns True (purged).
    """
    forward_sessions = get_forward_sessions(as_of_date, forward_sessions_required)
    final_session = forward_sessions[-1]
    return final_session > dev_end
