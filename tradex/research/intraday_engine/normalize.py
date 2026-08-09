"""Normalize raw OHLCV rows into session-aware, validated ``Bar`` objects."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

import pandas as pd

from .calendar import MARKET_TIMEZONE, build_session, is_on_grid, next_bar_start
from .models import Bar, DataQualitySummary, Session

_REQUIRED = {"open", "high", "low", "close", "volume"}


class NormalizationError(Exception):
    """Raised when input cannot be normalized into usable sessions."""


def _is_valid_ohlc(row: pd.Series) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    o = float(row["open"])
    h = float(row["high"])
    l = float(row["low"])
    c = float(row["close"])
    if h < l:
        reasons.append("high<low")
    if c > h:
        reasons.append("close>high")
    if c < l:
        reasons.append("close<low")
    if o > h:
        reasons.append("open>high")
    if o < l:
        reasons.append("open<low")
    return (not reasons), reasons


def _localize_index(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Convert the DataFrame index to timezone-aware UTC, rejecting naive input."""
    if df.index.tzinfo is None:
        raise NormalizationError(f"{ticker}: timestamps are timezone-naive")
    df = df.copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[~df.index.isna()]
    df = df.sort_index()
    return df


def normalize_to_sessions(
    df: pd.DataFrame,
    ticker: str,
    *,
    exclude_early_close: bool = True,
) -> tuple[list[Session], DataQualitySummary]:
    """Return validated ``Session`` objects and observability counts."""
    df = _localize_index(df, ticker)
    cols = {str(c).lower().strip().replace(" ", "_"): c for c in df.columns}
    df = df.rename(columns={v: k for k, v in cols.items()})
    missing = _REQUIRED - set(df.columns)
    if missing:
        raise NormalizationError(f"{ticker}: missing required columns {missing}")

    total_rows = len(df)

    # Count and remove duplicate timestamps before other validation.
    dup_mask = df.index.duplicated(keep="first")
    duplicate_timestamps = int(dup_mask.sum())
    df = df[~dup_mask]

    # Convert numeric columns and drop rows with non-finite required values.
    for col in _REQUIRED:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    non_finite_mask = df[list(_REQUIRED)].isna().any(axis=1)
    non_finite_rows = int(non_finite_mask.sum())
    df = df[~non_finite_mask]

    # Classify invalid OHLC rows; keep them as invalid records.
    invalid_mask = pd.Series(False, index=df.index)
    for idx, row in df.iterrows():
        valid, _ = _is_valid_ohlc(row)
        if not valid:
            invalid_mask.loc[idx] = True

    sessions_by_date: dict[datetime, Session] = {}
    bars_by_session: dict[datetime, dict[datetime, Bar]] = defaultdict(dict)
    quality_by_session: dict[datetime, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )

    off_grid_bars = 0
    zero_volume_bars = 0

    for idx, row in df.iterrows():
        bar_utc = idx.to_pydatetime().astimezone(UTC)
        bar_et = bar_utc.astimezone(MARKET_TIMEZONE)
        day = bar_et.date()

        if day not in sessions_by_date:
            session = build_session(day, exclude_early_close=exclude_early_close)
            if session is None:
                off_grid_bars += 1
                continue
            sessions_by_date[day] = session

        session = sessions_by_date[day]

        if not is_on_grid(bar_utc, session.grid):
            off_grid_bars += 1
            quality_by_session[day]["off_grid_bars"] += 1
            continue

        if float(row["volume"]) == 0:
            zero_volume_bars += 1
            quality_by_session[day]["zero_volume_bars"] += 1

        is_invalid = bool(invalid_mask.loc[idx])
        invalid_reasons: list[str] = []
        if is_invalid:
            _, reasons = _is_valid_ohlc(row)
            invalid_reasons = reasons
            quality_by_session[day]["invalid_ohlc_rows"] += 1

        bar = Bar(
            bar_start=bar_utc,
            available_at=next_bar_start(bar_utc),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            is_valid=not is_invalid,
            invalid_reasons=invalid_reasons,
        )

        if bar.bar_start in bars_by_session[day]:
            duplicate_timestamps += 1
            quality_by_session[day]["duplicate_timestamps"] += 1
            continue

        bars_by_session[day][bar.bar_start] = bar
        if bar.is_valid:
            quality_by_session[day]["valid_bars"] += 1

    sessions: list[Session] = []
    total_missing = 0
    total_valid = 0
    total_invalid = 0
    total_zero = 0
    total_off_grid = off_grid_bars

    for day in sorted(sessions_by_date):
        session = sessions_by_date[day]
        session.bars = dict(bars_by_session[day])
        q = dict(quality_by_session[day])
        session.quality_counts = q

        # Missing bars are expected grid positions with no valid bar.
        missing_in_session = 0
        for g in session.grid:
            if g not in session.bars or not session.bars[g].is_valid:
                session.missing_bars.append(g)
                missing_in_session += 1
            else:
                total_valid += 1
        total_missing += missing_in_session
        total_invalid += q.get("invalid_ohlc_rows", 0)
        total_zero += q.get("zero_volume_bars", 0)
        total_off_grid += q.get("off_grid_bars", 0)
        sessions.append(session)

    summary = DataQualitySummary(
        ticker=ticker,
        total_rows=total_rows,
        duplicate_timestamps=duplicate_timestamps,
        naive_timestamps=0,
        off_grid_bars=total_off_grid,
        invalid_ohlc_rows=total_invalid,
        non_finite_rows=non_finite_rows,
        zero_volume_bars=total_zero,
        missing_bars=total_missing,
        valid_bars=total_valid,
        sessions=len(sessions),
    )
    return sessions, summary


def bars_to_dataframe(bars: list[Bar]) -> pd.DataFrame:
    """Convert a list of ``Bar`` objects into an OHLCV DataFrame."""
    if not bars:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume", "vwap"]
        ).astype(float)
    data = {
        "open": [b.open for b in bars],
        "high": [b.high for b in bars],
        "low": [b.low for b in bars],
        "close": [b.close for b in bars],
        "volume": [b.volume for b in bars],
        "vwap": [b.vwap for b in bars],
    }
    index = pd.DatetimeIndex([b.bar_start for b in bars], tz="UTC")
    return pd.DataFrame(data, index=index)
