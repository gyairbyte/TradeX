"""Deterministic synthetic fixture generator for DAYTRADE-001C1."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from .calendar import (
    MARKET_TIMEZONE,
    bar_available_at,
    get_exchange_calendar,
    to_utc,
)
from .models import DaytradeBar, DaytradeSession


def generate_synthetic_session_bars(
    ticker: str,
    session_date: date,
    base_price: float = 100.0,
    minute_returns: dict[str, float] | None = None,
    drop_minutes: list[str] | None = None,
    duplicate_minutes: list[str] | None = None,
    malformed_timestamps: list[str] | None = None,
    default_minute_return: float = 0.0001,
) -> pd.DataFrame:
    """Generate raw 1-minute OHLCV DataFrame for testing data-quality and engine mechanics.

    minute_returns maps 'HH:MM' ET -> close-to-close return.
    drop_minutes lists 'HH:MM' ET to omit.
    duplicate_minutes lists 'HH:MM' ET to insert twice.
    malformed_timestamps lists 'HH:MM' ET where timestamp is corrupt string.
    """
    minute_returns = minute_returns or {}
    drop_minutes = set(drop_minutes or [])
    duplicate_minutes = set(duplicate_minutes or [])
    malformed_timestamps = set(malformed_timestamps or [])

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

    rows: list[dict[str, Any]] = []
    current_close = base_price

    for dt_local in grid:
        min_str = dt_local.strftime("%H:%M")
        dt_utc = dt_local.to_pydatetime().astimezone(UTC)

        ret = minute_returns.get(min_str, default_minute_return)
        new_close = current_close * (1.0 + ret)
        open_px = current_close
        high_px = max(open_px, new_close) + 0.01
        low_px = min(open_px, new_close) - 0.01
        volume = 1000.0

        current_close = new_close

        if min_str in drop_minutes:
            continue

        row_data = {
            "datetime": dt_utc.isoformat(),
            "open": open_px,
            "high": high_px,
            "low": low_px,
            "close": new_close,
            "volume": volume,
        }

        if min_str in malformed_timestamps:
            row_data["datetime"] = "MALFORMED_TIMESTAMP"

        rows.append(row_data)

        if min_str in duplicate_minutes:
            # Append duplicate row
            rows.append(dict(row_data))

    return pd.DataFrame(rows)


def build_synthetic_session_from_bars(
    ticker: str,
    session_date: date,
    bars_df: pd.DataFrame,
    grid: list[datetime],
) -> DaytradeSession:
    """Helper to convert synthetic DataFrame directly to a DaytradeSession."""
    bars: list[DaytradeBar] = []
    for _, row in bars_df.iterrows():
        try:
            ts = datetime.fromisoformat(row["datetime"])
            ts_utc = to_utc(ts)
            bars.append(
                DaytradeBar(
                    ticker=ticker,
                    session_date=session_date,
                    bar_start=ts_utc,
                    available_at=bar_available_at(ts_utc),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        except (ValueError, TypeError, KeyError):
            pass

    bars.sort(key=lambda b: b.bar_start)
    return DaytradeSession(
        ticker=ticker,
        session_date=session_date,
        bars=bars,
        is_valid=True,
    )
