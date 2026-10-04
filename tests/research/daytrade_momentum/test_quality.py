"""Tests for per-session and split-level data quality auditing.

Enforces Clarification 1:
- Realizable per-session boundary checks on 390 bars:
  - 19 missing bars (4.87%) PASS, 20 missing bars (5.13%) EXCLUDE
  - 3 duplicate bars (0.77%) PASS, 4 duplicate bars (1.03%) EXCLUDE
- Split-level gate checks exact 5.0% boundary:
  - Exactly 5.0% excluded passes (exceeds_split_gate == False)
  - 5.1% excluded fails (exceeds_split_gate == True)
"""
from __future__ import annotations

from datetime import date

from tradex.research.daytrade_momentum.calendar import (
    build_regular_session_grid,
    to_market_time,
)
from tradex.research.daytrade_momentum.models import DataQualityReport
from tradex.research.daytrade_momentum.quality import (
    audit_missing_ticker_session,
    audit_ticker_session,
    evaluate_split_quality,
)
from tradex.research.daytrade_momentum.synthetic import generate_synthetic_session_bars


def test_clarification1_missing_bars_boundary() -> None:
    """Verify realizable missing-bar boundaries: 19 missing bars PASS, 20 missing bars EXCLUDE."""
    session_d = date(2025, 1, 15)
    grid = build_regular_session_grid(session_d)

    # 19 missing bars (4.8718% <= 5.0%) -> PASS
    drop_19 = [to_market_time(grid[i]).strftime("%H:%M") for i in range(19)]
    df_19 = generate_synthetic_session_bars("SPY", session_d, drop_minutes=drop_19)
    session_19, report_19 = audit_ticker_session("SPY", session_d, df_19, grid)

    assert report_19.missing_bars == 19
    assert round(report_19.missing_rate_pct, 4) == round((19 / 390.0) * 100.0, 4)
    assert report_19.missing_rate_pct <= 5.0
    assert report_19.excluded is False
    assert session_19.is_valid is True

    # 20 missing bars (5.1282% > 5.0%) -> EXCLUDE
    drop_20 = [to_market_time(grid[i]).strftime("%H:%M") for i in range(20)]
    df_20 = generate_synthetic_session_bars("SPY", session_d, drop_minutes=drop_20)
    session_20, report_20 = audit_ticker_session("SPY", session_d, df_20, grid)

    assert report_20.missing_bars == 20
    assert report_20.missing_rate_pct > 5.0
    assert report_20.excluded is True
    assert session_20.is_valid is False
    assert any("missing" in r for r in report_20.exclusion_reasons)


def test_clarification1_duplicate_bars_boundary() -> None:
    """Verify realizable duplicate boundaries: 3 duplicates PASS, 4 duplicates EXCLUDE."""
    session_d = date(2025, 1, 15)
    grid = build_regular_session_grid(session_d)

    # 3 duplicate bars (3 / 390 = 0.7692% <= 1.0%) -> PASS
    dup_3 = [to_market_time(grid[i]).strftime("%H:%M") for i in range(3)]
    df_3 = generate_synthetic_session_bars("SPY", session_d, duplicate_minutes=dup_3)
    session_3, report_3 = audit_ticker_session("SPY", session_d, df_3, grid)

    assert report_3.duplicate_bars == 3
    assert report_3.duplicate_rate_pct <= 1.0
    assert report_3.excluded is False
    assert session_3.is_valid is True

    # 4 duplicate bars (4 / 390 = 1.0256% > 1.0%) -> EXCLUDE
    dup_4 = [to_market_time(grid[i]).strftime("%H:%M") for i in range(4)]
    df_4 = generate_synthetic_session_bars("SPY", session_d, duplicate_minutes=dup_4)
    session_4, report_4 = audit_ticker_session("SPY", session_d, df_4, grid)

    assert report_4.duplicate_bars == 4
    assert report_4.duplicate_rate_pct > 1.0
    assert report_4.excluded is True
    assert session_4.is_valid is False
    assert any("duplicate" in r for r in report_4.exclusion_reasons)


def test_malformed_timestamps_and_prices_discarded() -> None:
    """Verify malformed timestamps and negative/NaN OHLC prices are discarded."""
    session_d = date(2025, 1, 15)
    grid = build_regular_session_grid(session_d)

    bad_ts_min = [to_market_time(grid[5]).strftime("%H:%M")]
    bad_ohlc_min = [to_market_time(grid[10]).strftime("%H:%M")]

    df = generate_synthetic_session_bars(
        "QQQ",
        session_d,
        malformed_timestamps=bad_ts_min,
        malformed_ohlc=bad_ohlc_min,
    )
    _session, report = audit_ticker_session("QQQ", session_d, df, grid)

    # Those 2 bars fail validation and are dropped from valid bars -> missing count becomes 2
    assert report.malformed_timestamp_count == 1
    assert report.malformed_ohlcv_count == 1
    assert report.missing_bars == 2
    assert report.excluded is False  # 2 missing bars (0.5%) does not exceed 5%


def test_missing_ticker_session_audit() -> None:
    """Verify audit of a completely missing ticker-session."""
    session_d = date(2025, 1, 15)
    session, report = audit_missing_ticker_session("DIA", session_d)

    assert report.total_bars == 0
    assert report.missing_bars == 390
    assert report.missing_rate_pct == 100.0
    assert report.excluded is True
    assert session.is_valid is False
    assert "all_bars_missing" in report.exclusion_reasons


def test_split_level_data_quality_boundary() -> None:
    """Verify split-level DQ gate handles exact 5.0% boundary and missing sessions."""
    from datetime import timedelta
    universe = ("SPY", "QQQ")
    # 50 dates * 2 tickers = 100 ticker-sessions expected
    sessions = [date(2025, 1, 1) + timedelta(days=i) for i in range(50)]

    # Exactly 5 excluded out of 100 = 5.0% -> PASS (exceeds_split_gate is False)
    reports_5pct: list[DataQualityReport] = []
    for i, s_date in enumerate(sessions):
        for sym in universe:
            # exclude first 5 reports
            is_exc = len(reports_5pct) < 5
            reports_5pct.append(
                DataQualityReport(
                    ticker=sym,
                    session_date=s_date,
                    total_bars=390,
                    expected_bars=390,
                    missing_bars=0,
                    missing_rate_pct=0.0,
                    duplicate_bars=0,
                    duplicate_rate_pct=0.0,
                    malformed_timestamp_count=0,
                    malformed_ohlcv_count=0,
                    excluded=is_exc,
                    exclusion_reasons=["test_reason"] if is_exc else [],
                )
            )

    summary_5 = evaluate_split_quality("validation", reports_5pct, sessions, universe)
    assert summary_5.total_ticker_sessions == 100
    assert summary_5.excluded_ticker_sessions == 5
    assert summary_5.excluded_rate_pct == 5.0
    assert summary_5.exceeds_split_gate is False

    # 6 excluded out of 100 = 6.0% -> FAILS gate
    reports_6pct = list(reports_5pct)
    # flip the 6th report to excluded
    reports_6pct[5] = DataQualityReport(
        ticker=reports_6pct[5].ticker,
        session_date=reports_6pct[5].session_date,
        total_bars=390,
        expected_bars=390,
        missing_bars=0,
        missing_rate_pct=0.0,
        duplicate_bars=0,
        duplicate_rate_pct=0.0,
        malformed_timestamp_count=0,
        malformed_ohlcv_count=0,
        excluded=True,
        exclusion_reasons=["test_reason"],
    )

    summary_6 = evaluate_split_quality("validation", reports_6pct, sessions, universe)
    assert summary_6.excluded_ticker_sessions == 6
    assert summary_6.excluded_rate_pct == 6.0
    assert summary_6.exceeds_split_gate is True
