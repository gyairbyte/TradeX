"""Deterministic synthetic fixture generator for DAYTRADE-002B."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from .calendar import (
    build_regular_session_grid,
    to_market_time,
)
from .models import DaytradeSession

_REGULAR_MIN_STRS = [f"{9 + (30 + i) // 60:02d}:{(30 + i) % 60:02d}" for i in range(390)]


def generate_synthetic_session_bars(
    ticker: str,
    session_date: date,
    base_price: float = 100.0,
    prev_15_59_close: float | None = None,
    signal_09_59_close: float | None = None,
    entry_15_30_open: float | None = None,
    exit_15_59_close: float | None = None,
    drop_minutes: list[str] | None = None,
    duplicate_minutes: list[str] | None = None,
    malformed_timestamps: list[str] | None = None,
    malformed_ohlc: list[str] | None = None,
    default_minute_return: float = 0.0001,
) -> pd.DataFrame:
    """Generate raw 1-minute OHLCV DataFrame for testing data-quality and engine mechanics.

    drop_minutes lists 'HH:MM' ET to omit.
    duplicate_minutes lists 'HH:MM' ET to insert twice.
    malformed_timestamps lists 'HH:MM' ET where timestamp is corrupt string.
    malformed_ohlc lists 'HH:MM' ET where close is NaN/negative.
    """
    drop_set = set(drop_minutes or [])
    dup_set = set(duplicate_minutes or [])
    bad_ts_set = set(malformed_timestamps or [])
    bad_ohlc_set = set(malformed_ohlc or [])

    grid = build_regular_session_grid(session_date)
    rows: list[dict[str, Any]] = []
    current_close = base_price

    use_fast_min_strs = len(grid) == 390

    for idx, dt_utc in enumerate(grid):
        if use_fast_min_strs:
            min_str = _REGULAR_MIN_STRS[idx]
        else:
            dt_local = to_market_time(dt_utc)
            min_str = dt_local.strftime("%H:%M")

        # Determine target open/close for key reference bars
        open_px = current_close
        close_px = current_close * (1.0 + default_minute_return)

        if min_str == "09:59" and signal_09_59_close is not None:
            close_px = signal_09_59_close
        elif min_str == "15:30" and entry_15_30_open is not None:
            open_px = entry_15_30_open
            close_px = entry_15_30_open * 1.0001
        elif min_str == "15:59" and exit_15_59_close is not None:
            close_px = exit_15_59_close

        high_px = max(open_px, close_px) + 0.02
        low_px = min(open_px, close_px) - 0.02
        volume = 1000.0

        current_close = close_px

        if min_str in drop_set:
            continue

        row_data = {
            "bar_start": dt_utc.isoformat(),
            "datetime": dt_utc.isoformat(),
            "open": open_px,
            "high": high_px,
            "low": low_px,
            "close": close_px,
            "volume": volume,
        }

        if min_str in bad_ts_set:
            row_data["bar_start"] = "MALFORMED_TIMESTAMP"
            row_data["datetime"] = "MALFORMED_TIMESTAMP"

        if min_str in bad_ohlc_set:
            row_data["close"] = -999.0

        rows.append(row_data)

        if min_str in dup_set:
            rows.append(dict(row_data))

    return pd.DataFrame(rows)


def build_synthetic_session_from_bars(
    ticker: str,
    session_date: date,
    bars_df: pd.DataFrame,
    grid: list[datetime] | None = None,
) -> DaytradeSession:
    """Helper to convert synthetic DataFrame directly to a DaytradeSession."""
    if grid is None:
        grid = build_regular_session_grid(session_date)

    from .quality import audit_ticker_session
    session, _ = audit_ticker_session(ticker, session_date, bars_df, grid)
    return session
