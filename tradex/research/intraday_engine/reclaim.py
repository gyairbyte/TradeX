"""Pullback/reclaim detection for the INTRA-001 candidate and Baseline B."""
from __future__ import annotations

from datetime import datetime, time

from .calendar import MARKET_TIMEZONE
from .models import Bar, OpeningDriveState, Session
from .spec import IntradaySpec


def _grid_in_window(session: Session, start: time, end: time) -> list[datetime]:
    """Return UTC bar-start times whose ET time is in ``[start, end)``."""

    result: list[datetime] = []
    for g in session.grid:
        et_time = g.astimezone(MARKET_TIMEZONE).time()
        if start <= et_time < end:
            result.append(g)
    return result


def find_first_reclaim(
    session: Session,
    opening_drive: OpeningDriveState,
    spec: IntradaySpec,
    *,
    require_opening_drive: bool = True,
) -> Bar | None:
    """Return the first reclaim bar in the search window, or ``None``."""
    if session.grid:
        session_open = session.bars.get(session.grid[0])
        session_open_price = session_open.open if session_open else None
    else:
        session_open_price = None

    if require_opening_drive and not opening_drive.qualified:
        return None

    window = _grid_in_window(
        session,
        spec.reclaim_search_start_time,
        spec.reclaim_search_end_time,
    )

    for bar_start in window:
        bar = session.bars.get(bar_start)
        if bar is None or not bar.is_valid or bar.vwap is None:
            continue

        low_below_vwap = bar.low <= bar.vwap
        close_above_vwap = bar.close > bar.vwap
        close_above_open = bar.close > bar.open
        close_at_or_above_open_930 = (
            session_open_price is not None and bar.close >= session_open_price
        )

        if (
            low_below_vwap
            and close_above_vwap
            and close_above_open
            and close_at_or_above_open_930
        ):
            return bar
    return None
