"""Per-ticker-session and split-level data quality auditing."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import pandas as pd

from .calendar import (
    EXPECTED_REGULAR_MINUTES,
    bar_available_at,
    get_regular_trading_sessions,
    to_utc,
)
from .models import DataQualityReport, DaytradeBar, DaytradeSession, SplitDataQualitySummary

MAX_MISSING_RATE_PCT = 5.0  # > 5% (> 19 missing bars) excludes ticker-session
MAX_DUPLICATE_RATE_PCT = 1.0  # > 1% (> 3 duplicate bars) excludes ticker-session
MAX_SPLIT_EXCLUDED_RATE_PCT = 5.0  # > 5% excluded ticker-sessions fails split support gate


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

    # Inspect timestamps and OHLCV rows
    for _, row in bars_df.iterrows():
        raw_ts = row.get("datetime") or row.get("timestamp") or row.get("bar_start")
        ts_utc = None
        try:
            if isinstance(raw_ts, str):
                ts = datetime.fromisoformat(raw_ts)
            elif isinstance(raw_ts, pd.Timestamp):
                ts = raw_ts.to_pydatetime()
            elif isinstance(raw_ts, datetime):
                ts = raw_ts
            else:
                ts = None

            if ts is not None:
                ts_utc = to_utc(ts)
        except (ValueError, TypeError, AttributeError):
            ts_utc = None

        if ts_utc is None:
            malformed_timestamp_count += 1
            continue

        if ts_utc not in grid_set:
            # Bar is premarket, postmarket, or off-grid; ignored from regular session
            continue

        # Check OHLCV validity: reject NaN, Inf, non-numeric, <=0 prices, <0 volume
        raw_o = row.get("open")
        raw_h = row.get("high")
        raw_l = row.get("low")
        raw_c = row.get("close")
        raw_v = row.get("volume")

        if not (
            is_valid_numeric_price(raw_o)
            and is_valid_numeric_price(raw_h)
            and is_valid_numeric_price(raw_l)
            and is_valid_numeric_price(raw_c)
            and is_valid_numeric_volume(raw_v)
        ):
            malformed_ohlcv_count += 1
            continue

        if ts_utc in seen_starts:
            duplicate_count += 1
            # Keep first occurrence, do not overwrite
            continue

        seen_starts.add(ts_utc)
        valid_grid_bars.append(
            DaytradeBar(
                ticker=ticker,
                session_date=session_date,
                bar_start=ts_utc,
                available_at=bar_available_at(ts_utc),
                open=float(raw_o),
                high=float(raw_h),
                low=float(raw_l),
                close=float(raw_c),
                volume=float(raw_v),
            )
        )

    valid_grid_bars.sort(key=lambda b: b.bar_start)

    unique_on_grid = len(valid_grid_bars)
    missing_count = EXPECTED_REGULAR_MINUTES - unique_on_grid
    missing_rate_pct = (missing_count / float(EXPECTED_REGULAR_MINUTES)) * 100.0
    duplicate_rate_pct = (duplicate_count / float(EXPECTED_REGULAR_MINUTES)) * 100.0

    # Rule 1: Duplicate bars rate > 1.0% (> 3 duplicate bars)
    if duplicate_rate_pct > MAX_DUPLICATE_RATE_PCT:
        exclusion_reasons.append(
            f"duplicate_rate_{duplicate_rate_pct:.2f}%_exceeds_{MAX_DUPLICATE_RATE_PCT}%"
        )

    # Rule 2: Missing bars rate > 5.0% (> 19 missing bars)
    if missing_rate_pct > MAX_MISSING_RATE_PCT:
        exclusion_reasons.append(
            f"missing_rate_{missing_rate_pct:.2f}%_exceeds_{MAX_MISSING_RATE_PCT}%"
        )

    excluded = len(exclusion_reasons) > 0

    session = DaytradeSession(
        ticker=ticker,
        session_date=session_date,
        bars=valid_grid_bars,
        is_valid=not excluded,
        exclusion_reasons=exclusion_reasons,
    )

    report = DataQualityReport(
        ticker=ticker,
        session_date=session_date,
        total_bars=total_raw_rows,
        expected_bars=EXPECTED_REGULAR_MINUTES,
        missing_bars=missing_count,
        missing_rate_pct=missing_rate_pct,
        duplicate_bars=duplicate_count,
        duplicate_rate_pct=duplicate_rate_pct,
        malformed_timestamp_count=malformed_timestamp_count,
        malformed_ohlcv_count=malformed_ohlcv_count,
        excluded=excluded,
        exclusion_reasons=exclusion_reasons,
    )

    return session, report


def get_expected_split_sessions(
    start_date_str: str,
    end_date_str: str,
) -> list[date]:
    """Return all eligible regular XNYS trading sessions between start and end date (inclusive)."""
    start_d = date.fromisoformat(start_date_str)
    end_d = date.fromisoformat(end_date_str)
    return get_regular_trading_sessions(start_d, end_d, exclude_early_close=True)


def evaluate_split_quality(
    reports: list[DataQualityReport],
    split_name: str,
    total_expected_ticker_sessions: int | None = None,
) -> SplitDataQualitySummary:
    """Summarize data-quality audits across all ticker-sessions in a split."""
    total = total_expected_ticker_sessions if total_expected_ticker_sessions is not None else len(reports)
    excluded = sum(1 for r in reports if r.excluded)

    if total_expected_ticker_sessions is not None and total_expected_ticker_sessions > len(reports):
        unobserved = total_expected_ticker_sessions - len(reports)
        excluded += unobserved

    excluded_rate_pct = (excluded / float(total) * 100.0) if total > 0 else 0.0
    exceeds_gate = excluded_rate_pct > MAX_SPLIT_EXCLUDED_RATE_PCT

    breakdown: dict[str, int] = {}
    for r in reports:
        for reason in r.exclusion_reasons:
            cat = reason.split("_")[0]
            breakdown[cat] = breakdown.get(cat, 0) + 1

    return SplitDataQualitySummary(
        split=split_name,
        total_ticker_sessions=total,
        excluded_ticker_sessions=excluded,
        excluded_rate_pct=excluded_rate_pct,
        exceeds_split_gate=exceeds_gate,
        exclusion_breakdown=breakdown,
        is_valid=not exceeds_gate,
    )
