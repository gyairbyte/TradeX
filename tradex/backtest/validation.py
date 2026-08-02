"""Canonical OHLCV validation for the backtest harness."""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from tradex.backtest.models import BacktestDataError

_REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


def canonicalize_bars(df: pd.DataFrame, *, timezone: str | None = None) -> pd.DataFrame:
    """Return a defensive, validated copy of ``df`` with canonical OHLCV columns.

    The returned DataFrame has:

    * A strictly increasing, timezone-aware UTC ``DatetimeIndex`` named ``datetime``.
    * Numeric ``open``, ``high``, ``low``, ``close``, ``volume`` columns.
    * No NaN, infinite, or malformed required values.
    * Validated OHLC relationships and non-negative volume.

    Parameters
    ----------
    df:
        Caller-supplied OHLCV data.
    timezone:
        Optional IANA timezone used to localize a naive index. If omitted and
        the index is naive, a ``BacktestDataError`` is raised.

    Raises
    ------
    BacktestDataError
        If any invariant is violated. The message includes the offending
        timestamp so callers can locate the problem.
    """
    if not isinstance(df, pd.DataFrame):
        raise BacktestDataError(f"Expected pandas DataFrame; got {type(df).__name__}")

    bars = df.copy()

    # Index must be datetime-like and named/convertible to 'datetime'.
    if not isinstance(bars.index, pd.DatetimeIndex):
        try:
            bars.index = pd.to_datetime(bars.index)
        except Exception as exc:  # noqa: BLE001
            raise BacktestDataError(f"Index cannot be parsed as datetime: {exc}") from None
    bars.index.name = "datetime"

    # Timezone handling.
    if bars.index.tz is None:
        if timezone is None:
            raise BacktestDataError(
                "DatetimeIndex is naive. Pass an explicit timezone or supply an aware index."
            )
        try:
            bars.index = bars.index.tz_localize(timezone)
        except Exception as exc:  # noqa: BLE001
            raise BacktestDataError(f"Failed to localize naive index to {timezone!r}: {exc}") from None

    bars.index = bars.index.tz_convert("UTC")

    if not bars.index.is_monotonic_increasing:
        if not bars.index.is_unique:
            raise BacktestDataError("DatetimeIndex contains duplicate timestamps")
        raise BacktestDataError("DatetimeIndex is not strictly increasing")

    if not bars.index.is_unique:
        raise BacktestDataError("DatetimeIndex contains duplicate timestamps")

    # Required columns.
    missing = [c for c in _REQUIRED_COLUMNS if c not in bars.columns]
    if missing:
        raise BacktestDataError(f"Missing required columns: {missing}")

    bars = bars[_REQUIRED_COLUMNS].copy()

    # Numeric conversion and NaN/inf checks.
    for col in _REQUIRED_COLUMNS:
        try:
            numeric = pd.to_numeric(bars[col], errors="coerce")
        except Exception as exc:  # noqa: BLE001
            raise BacktestDataError(f"Column '{col}' is not numeric: {exc}") from None

        invalid = (~np.isfinite(numeric.to_numpy(dtype=float))) & (~numeric.isna())
        if invalid.any():
            ts = bars.index[invalid].tolist()
            raise BacktestDataError(f"Non-finite value in '{col}' at timestamp(s): {ts}")

        if numeric.isna().any():
            ts = bars.index[numeric.isna()].tolist()
            raise BacktestDataError(f"NaN or non-numeric value in '{col}' at timestamp(s): {ts}")

        bars[col] = numeric.astype(float)

    # OHLC and volume invariants, row by row.
    for i, ts in enumerate(bars.index):
        row = bars.iloc[i]
        o, h, l, c, v = row["open"], row["high"], row["low"], row["close"], row["volume"]

        if any(x <= 0 for x in (o, h, l, c)):
            raise BacktestDataError(f"Nonpositive OHLC price at {ts}: open={o}, high={h}, low={l}, close={c}")
        if v < 0:
            raise BacktestDataError(f"Negative volume at {ts}: {v}")
        if h < l:
            raise BacktestDataError(f"high < low at {ts}: high={h}, low={l}")
        if h < o or h < c:
            raise BacktestDataError(f"high below open or close at {ts}: high={h}, open={o}, close={c}")
        if l > o or l > c:
            raise BacktestDataError(f"low above open or close at {ts}: low={l}, open={o}, close={c}")

    return bars


def validate_score_output(output: Any) -> dict[str, Any]:
    """Return a validated score mapping from a scorer.

    Required: ``score`` (numeric 0-100). ``reasons`` must be a list of strings.
    """
    if not isinstance(output, Mapping):
        raise BacktestDataError(f"Score function must return a mapping; got {type(output).__name__}")

    if "score" not in output:
        raise BacktestDataError("Score function output missing 'score'")

    score = output["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise BacktestDataError(f"Score must be numeric; got {type(score).__name__}")
    if not math.isfinite(score):
        raise BacktestDataError(f"Score must be finite; got {score}")
    if not (0 <= score <= 100):
        raise BacktestDataError(f"Score must be between 0 and 100; got {score}")

    reasons = output.get("reasons", [])
    if not isinstance(reasons, list) or not all(isinstance(r, str) for r in reasons):
        raise BacktestDataError("Score function 'reasons' must be a list of strings")

    return dict(output)
