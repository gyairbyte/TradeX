"""Per-ticker-session and split-level data quality auditing."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import pandas as pd

from .calendar import (
    EXPECTED_REGULAR_MINUTES,
    to_market_time,
    to_utc,
)
from .models import DataQualityReport, DaytradeBar, DaytradeSession, SplitDataQualitySummary

MAX_MISSING_RATE_PCT = 5.0   # > 5.0% (> 19 missing bars out of 390) excludes ticker-session
MAX_DUPLICATE_RATE_PCT = 1.0  # > 1.0% (> 3 duplicate bars out of 390) excludes ticker-session
MAX_SPLIT_EXCLUDED_RATE_PCT = 5.0  # > 5.0% excluded ticker-sessions fails split support gate


class DataQualityError(Exception):
    """Raised when an unrecoverable data quality or format error occurs."""


def is_valid_numeric_price(val: Any) -> bool:
    """Return True if val is finite numeric and strictly positive."""
    if val is None or pd.isna(val):
        return False
    try:
        f = float(val)
        return not math.isnan(f) and not math.isinf(f) and f > 0.0
    except (ValueError, TypeError):
        return False


def is_valid_numeric_volume(val: Any) -> bool:
    """Return True if val is finite numeric and non-negative."""
    if val is None or pd.isna(val):
        return False
    try:
        f = float(val)
        return not math.isnan(f) and not math.isinf(f) and f >= 0.0
    except (ValueError, TypeError):
        return False


def audit_missing_ticker_session(
    ticker: str,
    session_date: date,
) -> tuple[DaytradeSession, DataQualityReport]:
    """Generate quality report and session for a completely missing ticker-session."""
    session = DaytradeSession(
        ticker=ticker,
        session_date=session_date,
        bars=[],
        is_valid=False,
        exclusion_reasons=["all_bars_missing"],
    )
    report = DataQualityReport(
        ticker=ticker,
        session_date=session_date,
        total_bars=0,
        expected_bars=EXPECTED_REGULAR_MINUTES,
        missing_bars=EXPECTED_REGULAR_MINUTES,
        missing_rate_pct=100.0,
        duplicate_bars=0,
        duplicate_rate_pct=0.0,
        malformed_timestamp_count=0,
        malformed_ohlcv_count=0,
        excluded=True,
        exclusion_reasons=["all_bars_missing"],
    )
    return session, report


def audit_ticker_session(
    ticker: str,
    session_date: date,
    bars_df: pd.DataFrame,
    grid: list[datetime],
) -> tuple[DaytradeSession, DataQualityReport]:
    """Audit raw 1-minute OHLCV rows for one ticker-session against the 390-bar regular grid.

    Examines malformed timestamps, duplicates, and missing bars before any dedup or drop.
    Returns normalized DaytradeSession and DataQualityReport.
    """
    grid_set = set(grid)
    total_raw_rows = len(bars_df)
    malformed_timestamp_count = 0
    malformed_ohlcv_count = 0
    valid_grid_bars: list[DaytradeBar] = []
    seen_starts: set[datetime] = set()
    duplicate_count = 0
    exclusion_reasons: list[str] = []

    if total_raw_rows == 0:
        return audit_missing_ticker_session(ticker, session_date)

    for _, row in bars_df.iterrows():
        raw_ts = row.get("datetime") or row.get("timestamp") or row.get("t")
        if raw_ts is None or pd.isna(raw_ts):
            malformed_timestamp_count += 1
            continue

        try:
            if isinstance(raw_ts, str):
                dt = pd.to_datetime(raw_ts, utc=True).to_pydatetime()
            elif isinstance(raw_ts, datetime):
                dt = to_utc(raw_ts)
            elif isinstance(raw_ts, pd.Timestamp):
                dt = raw_ts.to_pydatetime().astimezone(datetime.timezone.utc)
            else:
                dt = pd.to_datetime(raw_ts, utc=True).to_pydatetime()
        except (ValueError, TypeError, pd.errors.OutOfBoundsDatetime):
            malformed_timestamp_count += 1
            continue

        # Check if timestamp falls within regular-session grid
        if dt not in grid_set:
            # Row outside expected regular-session grid; ignore from regular session
            continue

        # Check for duplicates
        if dt in seen_starts:
            duplicate_count += 1
            continue
        seen_starts.add(dt)

        # Validate numeric OHLCV
        o = row.get("open") or row.get("o")
        h = row.get("high") or row.get("h")
        low_val = row.get("low") or row.get("l")
        c = row.get("close") or row.get("c")
        v = row.get("volume") or row.get("v") or 0.0

        if not (
            is_valid_numeric_price(o)
            and is_valid_numeric_price(h)
            and is_valid_numeric_price(low_val)
            and is_valid_numeric_price(c)
            and is_valid_numeric_volume(v)
        ):
            malformed_ohlcv_count += 1
            continue

        # Bar is valid
        # Localize available_at = bar_start + 1 minute
        avail_dt = dt + pd.Timedelta(minutes=1)
        # Store bar with local time accessible
        bar = DaytradeBar(
            ticker=ticker,
            session_date=session_date,
            bar_start=to_market_time(dt),
            available_at=to_market_time(avail_dt),
            open=float(o),
            high=float(h),
            low=float(low_val),
            close=float(c),
            volume=float(v),
        )
        valid_grid_bars.append(bar)

    # Sort valid bars chronologically
    valid_grid_bars.sort(key=lambda b: b.bar_start)

    observed_valid_bars = len(valid_grid_bars)
    missing_bars = EXPECTED_REGULAR_MINUTES - observed_valid_bars
    missing_rate_pct = (missing_bars / float(EXPECTED_REGULAR_MINUTES)) * 100.0
    duplicate_rate_pct = (duplicate_count / float(EXPECTED_REGULAR_MINUTES)) * 100.0

    # Locked exclusion rules (Clarification 1):
    # missing rate > 5.0% (19 missing bars is 4.87% <= 5% -> PASS; 20 missing bars is 5.13% > 5% -> EXCLUDE)
    if missing_rate_pct > MAX_MISSING_RATE_PCT:
        exclusion_reasons.append(
            f"excess_missing_bars_{missing_bars}_pct_{missing_rate_pct:.2f}"
        )

    # duplicate rate > 1.0% (3 duplicates is 0.77% <= 1% -> PASS; 4 duplicates is 1.03% > 1% -> EXCLUDE)
    if duplicate_rate_pct > MAX_DUPLICATE_RATE_PCT:
        exclusion_reasons.append(
            f"excess_duplicate_bars_{duplicate_count}_pct_{duplicate_rate_pct:.2f}"
        )

    is_excluded = len(exclusion_reasons) > 0
    session = DaytradeSession(
        ticker=ticker,
        session_date=session_date,
        bars=valid_grid_bars,
        is_valid=not is_excluded,
        exclusion_reasons=exclusion_reasons,
    )
    report = DataQualityReport(
        ticker=ticker,
        session_date=session_date,
        total_bars=observed_valid_bars,
        expected_bars=EXPECTED_REGULAR_MINUTES,
        missing_bars=missing_bars,
        missing_rate_pct=missing_rate_pct,
        duplicate_bars=duplicate_count,
        duplicate_rate_pct=duplicate_rate_pct,
        malformed_timestamp_count=malformed_timestamp_count,
        malformed_ohlcv_count=malformed_ohlcv_count,
        excluded=is_excluded,
        exclusion_reasons=exclusion_reasons,
    )
    return session, report


def evaluate_split_quality(
    split_name: str,
    quality_reports: list[DataQualityReport],
    expected_sessions: list[date],
    universe_symbols: tuple[str, ...],
) -> SplitDataQualitySummary:
    """Compute split-level data-quality summary against the full expected ticker-session grid.

    Total expected denominator = len(universe_symbols) * len(expected_sessions).
    Missing ticker-sessions from the reports are counted as excluded.
    """
    total_expected = len(universe_symbols) * len(expected_sessions)
    if total_expected == 0:
        return SplitDataQualitySummary(
            split=split_name,
            total_ticker_sessions=0,
            excluded_ticker_sessions=0,
            excluded_rate_pct=0.0,
            exceeds_split_gate=False,
            exclusion_breakdown={},
            is_valid=True,
        )

    # Map (ticker, session_date) -> report
    reports_by_key = {(r.ticker, r.session_date): r for r in quality_reports}

    excluded_count = 0
    breakdown: dict[str, int] = {}

    for sym in universe_symbols:
        for s_date in expected_sessions:
            rep = reports_by_key.get((sym, s_date))
            if rep is None or rep.excluded:
                excluded_count += 1
                reason = "completely_missing" if rep is None else (
                    ", ".join(rep.exclusion_reasons) or "excluded"
                )
                breakdown[reason] = breakdown.get(reason, 0) + 1

    excluded_rate_pct = (excluded_count / float(total_expected)) * 100.0
    # Gate fails if excluded_rate_pct > 5.0%
    exceeds_gate = excluded_rate_pct > MAX_SPLIT_EXCLUDED_RATE_PCT

    return SplitDataQualitySummary(
        split=split_name,
        total_ticker_sessions=total_expected,
        excluded_ticker_sessions=excluded_count,
        excluded_rate_pct=excluded_rate_pct,
        exceeds_split_gate=exceeds_gate,
        exclusion_breakdown=breakdown,
        is_valid=True,
    )
