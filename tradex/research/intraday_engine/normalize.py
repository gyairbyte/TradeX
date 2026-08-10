"""Normalize raw OHLCV rows into session-aware, validated ``Bar`` objects."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

import numpy as np
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
    """Return validated ``Session`` objects and observability counts.

    Duplicate and malformed rows are counted *before* deduplication so that the
    data-quality summary reflects the provider input.  Bars are deduplicated
    deterministically by session and bar-start time.
    """
    df = _localize_index(df, ticker)
    cols = {str(c).lower().strip().replace(" ", "_"): c for c in df.columns}
    df = df.rename(columns={v: k for k, v in cols.items()})
    missing = _REQUIRED - set(df.columns)
    if missing:
        raise NormalizationError(f"{ticker}: missing required columns {missing}")

    total_rows = len(df)

    # Count duplicate timestamps on the raw input before any validation/dedup.
    dup_mask = df.index.duplicated(keep="first")
    duplicate_timestamps = int(dup_mask.sum())

    # Convert numeric columns and identify non-finite required values.
    for col in _REQUIRED:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    required_df = df[list(_REQUIRED)]
    non_finite_mask = required_df.isna().any(axis=1) | np.isinf(required_df.values).any(axis=1)
    non_finite_rows = int(non_finite_mask.sum())

    # Classify invalid OHLC rows on finite rows only; non-finite rows are counted above.
    invalid_mask = pd.Series(False, index=df.index)
    for idx, row in df[~non_finite_mask].iterrows():
        valid, _ = _is_valid_ohlc(row)
        if not valid:
            invalid_mask.loc[idx] = True

    sessions_by_date: dict[datetime, Session] = {}
    bars_by_session: dict[datetime, dict[datetime, Bar]] = defaultdict(dict)
    quality_by_session: dict[datetime, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )

    seen_no_session: set[datetime] = set()
    seen_per_session: dict[datetime, set[datetime]] = defaultdict(set)
    off_grid_total = 0

    rows = list(df.iterrows())
    for (idx, row), is_non_finite, is_invalid in zip(
        rows,
        non_finite_mask.values,
        invalid_mask.values,
    ):
        if is_non_finite:
            continue

        bar_utc = idx.to_pydatetime().astimezone(UTC)
        bar_et = bar_utc.astimezone(MARKET_TIMEZONE)
        day = bar_et.date()

        if day not in sessions_by_date:
            session = build_session(day, exclude_early_close=exclude_early_close)
            if session is None:
                # Off-grid rows with no corresponding regular session are counted once
                # per unique timestamp; duplicates are already counted above.
                if bar_utc not in seen_no_session:
                    off_grid_total += 1
                    seen_no_session.add(bar_utc)
                continue
            sessions_by_date[day] = session

        session = sessions_by_date[day]

        # Deduplicate by timestamp within a session; only the first occurrence is
        # processed, but all duplicates have already been counted in duplicate_timestamps.
        if bar_utc in seen_per_session[day]:
            continue
        seen_per_session[day].add(bar_utc)

        if not is_on_grid(bar_utc, session.grid):
            quality_by_session[day]["off_grid_bars"] += 1
            continue

        if float(row["volume"]) == 0:
            quality_by_session[day]["zero_volume_bars"] += 1

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

        bars_by_session[day][bar.bar_start] = bar
        if bar.is_valid:
            quality_by_session[day]["valid_bars"] += 1

    sessions: list[Session] = []
    total_missing = 0
    total_valid = 0
    total_invalid = 0
    total_zero = 0
    total_off_grid = off_grid_total

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
        pre_normalization_metrics_available=True,
    )
    return sessions, summary


def evaluate_data_contract(summary: DataQualitySummary) -> tuple[bool, list[str]]:
    """Return (valid, reasons) for data-contract violations that invalidate a study.

    Data-sufficiency shortfalls (missing/zero-volume/duplicate bars beyond thresholds)
    are handled separately; this function flags provider/contract violations.
    """
    reasons: list[str] = []
    if summary.naive_timestamps > 0:
        reasons.append(f"naive_timestamps={summary.naive_timestamps}")
    if summary.off_grid_bars > 0:
        reasons.append(f"off_grid_bars={summary.off_grid_bars}")
    if summary.invalid_ohlc_rows > 0:
        reasons.append(f"invalid_ohlc_rows={summary.invalid_ohlc_rows}")
    if summary.non_finite_rows > 0:
        reasons.append(f"non_finite_rows={summary.non_finite_rows}")
    if summary.symbol_mismatch:
        reasons.append(
            f"symbol_mismatch requested={summary.requested_symbol} returned={summary.returned_symbol}"
        )
    if summary.file_sha256_match is False:
        reasons.append("file_sha256_mismatch")
    if summary.pagination_complete is False:
        reasons.append("pagination_incomplete")
    return (not reasons), reasons


def evaluate_data_sufficiency(
    summary: DataQualitySummary,
    *,
    expected_bars_per_session: int = 78,
) -> tuple[bool, list[str]]:
    """Return (passed, reasons) against the locked per-symbol data-sufficiency thresholds.

    Thresholds are taken from ``docs/research/specs/INTRA-001-v1.json``:
    - missing-bar rate <= 5%
    - zero-volume-bar rate <= 10%
    - duplicate-bar rate <= 1%
    """
    reasons: list[str] = []
    if summary.pre_normalization_metrics_available is False:
        reasons.append("pre_normalization_metrics_unavailable")
    expected = summary.sessions * expected_bars_per_session
    if expected > 0:
        missing_rate = summary.missing_bars / expected
        if missing_rate > 0.05:
            reasons.append(f"missing_bar_rate_{missing_rate:.4f}_above_5%")
        zero_rate = (
            summary.zero_volume_bars / expected if expected else 0.0
        )
        if zero_rate > 0.10:
            reasons.append(f"zero_volume_rate_{zero_rate:.4f}_above_10%")
    if summary.total_rows > 0:
        dup_rate = summary.duplicate_timestamps / summary.total_rows
        if dup_rate > 0.01:
            reasons.append(f"duplicate_rate_{dup_rate:.4f}_above_1%")
    return (not reasons), reasons


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
