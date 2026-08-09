"""XNYS regular-session grid and session construction helpers."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from tradex.market.hours import get_market_session

from .models import Session

MARKET_TIMEZONE = ZoneInfo("America/New_York")
BAR_INTERVAL = timedelta(minutes=5)


class CalendarError(Exception):
    """Raised for unsupported session conditions."""


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("Naive datetime is not accepted")
    return dt.astimezone(UTC)


def _regular_grid(opens: datetime, closes: datetime) -> list[datetime]:
    """Return bar-start UTC timestamps for the regular session grid."""
    opens_local = opens.astimezone(MARKET_TIMEZONE)
    closes_local = closes.astimezone(MARKET_TIMEZONE)
    if closes_local.time() < time(16, 0):
        raise CalendarError("Early-close sessions are excluded from the primary study")
    grid = pd.date_range(
        start=opens_local,
        end=closes_local,
        freq="5min",
        inclusive="left",
        tz=MARKET_TIMEZONE,
    )
    return [t.to_pydatetime().astimezone(UTC) for t in grid]


def build_session(day: date, *, exclude_early_close: bool = True) -> Session | None:
    """Return a ``Session`` for ``day`` or ``None`` if not a regular session."""
    from .models import Session

    market = get_market_session(day)
    if market is None:
        return None
    if exclude_early_close and market.is_early_close:
        return None
    opens_utc = _as_utc(market.opens_at)
    closes_utc = _as_utc(market.closes_at)
    grid = _regular_grid(opens_utc, closes_utc)
    return Session(
        session_date=market.session_date,
        opens_at=opens_utc,
        closes_at=closes_utc,
        is_early_close=market.is_early_close,
        grid=grid,
    )


def build_sessions(
    start: date, end: date, *, exclude_early_close: bool = True
) -> list[Session]:
    """Build sessions for every trading day in ``[start, end]``."""
    sessions: list[Session] = []
    current = start
    while current <= end:
        session = build_session(current, exclude_early_close=exclude_early_close)
        if session is not None:
            sessions.append(session)
        current += timedelta(days=1)
    return sessions


def prior_sessions(
    sessions: list[Any], current_date: date, n: int
) -> list[Any]:
    """Return up to ``n`` complete sessions strictly before ``current_date``."""
    prior = [s for s in sessions if s.session_date < current_date]
    prior.sort(key=lambda s: s.session_date)
    return prior[-n:]


def bar_available_at(bar_start: datetime) -> datetime:
    return _as_utc(bar_start.astimezone(MARKET_TIMEZONE) + BAR_INTERVAL)


def next_bar_start(bar_start: datetime) -> datetime:
    return _as_utc(bar_start.astimezone(MARKET_TIMEZONE) + BAR_INTERVAL)


def is_on_grid(bar_start: datetime, grid: list[datetime], tolerance_seconds: int = 1) -> bool:
    """Return True if ``bar_start`` matches a 5-minute grid point."""
    if not grid:
        return False
    start_utc = _as_utc(bar_start)
    for g in grid:
        if abs((start_utc - g).total_seconds()) <= tolerance_seconds:
            return True
    return False


def grid_index(bar_start: datetime, grid: list[datetime]) -> int:
    """Return the index of ``bar_start`` in ``grid`` or raise ``ValueError``."""
    start_utc = _as_utc(bar_start)
    for i, g in enumerate(grid):
        if abs((start_utc - g).total_seconds()) <= 1:
            return i
    raise ValueError(f"{bar_start} not on session grid")
