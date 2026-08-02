"""Offline CSV input for the backtest harness."""
from __future__ import annotations

import pandas as pd

from tradex.backtest.models import BacktestDataError
from tradex.backtest.validation import canonicalize_bars


def load_csv(path: str, *, timezone: str | None = None) -> pd.DataFrame:
    """Load a canonical OHLCV DataFrame from a CSV file.

    Supported columns:

    * ``datetime``
    * ``date`` (treated as an alias for ``datetime``)
    * ``open``, ``high``, ``low``, ``close``, ``volume``

    The index is parsed as datetime, localized if naive using ``timezone``,
    converted to UTC, and validated. The source CSV is never modified or
    overwritten.
    """
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        raise BacktestDataError(f"CSV file not found: {path}")
    except Exception as exc:  # noqa: BLE001
        raise BacktestDataError(f"Failed to read CSV {path!r}: {exc}") from None

    if "date" in df.columns and "datetime" not in df.columns:
        df = df.rename(columns={"date": "datetime"})

    if "datetime" not in df.columns:
        raise BacktestDataError(
            f"CSV must contain a 'datetime' or 'date' column; got columns: {list(df.columns)}"
        )

    try:
        df["datetime"] = pd.to_datetime(df["datetime"])
    except Exception as exc:  # noqa: BLE001
        raise BacktestDataError(f"Failed to parse datetime column in {path!r}: {exc}") from None

    df = df.set_index("datetime")

    return canonicalize_bars(df, timezone=timezone)
