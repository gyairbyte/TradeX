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
from pathlib import Path

import pandas as pd

from tradex.research.daytrade_momentum.calendar import (
    build_regular_session_grid,
    to_market_time,
)
from tradex.research.daytrade_momentum.dataset import (
    read_normalized_bars_csv,
    write_normalized_bars_csv,
)
from tradex.research.daytrade_momentum.models import DataQualityReport
from tradex.research.daytrade_momentum.quality import (
    _resolve_bar_timestamp,
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


def test_canonical_roundtrip_persisted_schema_regression(tmp_path: Path) -> None:
    """Mandatory regression reproducing DAYTRADE-002C defect and proving end-to-end fix.

    Exercises the full production serialization path:
        synthetic valid session DataFrame
            -> write_normalized_bars_csv(temp_path)
            -> read_normalized_bars_csv(temp_path)
            -> audit_ticker_session(...)

    Proves:
    - Exactly locked schema is written to disk (bar_start,open,high,low,close,volume);
    - Reader safely loads and creates dt_parsed;
    - Auditor accepts complete 390-bar session without exclusion;
    - Point-in-time bars (09:59 close, 15:30 open, 15:59 close) survive round-trip intact.
    """
    session_d = date(2026, 1, 15)
    grid = build_regular_session_grid(session_d)

    df_synth = generate_synthetic_session_bars(
        "SPY",
        session_d,
        base_price=100.0,
        signal_09_59_close=105.50,
        entry_15_30_open=106.25,
        exit_15_59_close=108.00,
    )
    assert len(df_synth) == 390

    csv_path = tmp_path / "bars" / "SPY.csv"
    write_normalized_bars_csv(csv_path, df_synth)

    # Verify exact locked CSV schema on disk
    with open(csv_path, "r", encoding="utf-8") as f:
        header = f.readline().strip()
    assert header == "bar_start,open,high,low,close,volume"

    # Read through canonical reader
    df_read, malformed_unassigned = read_normalized_bars_csv(csv_path)
    assert malformed_unassigned == 0
    assert list(df_read.columns) == ["bar_start", "open", "high", "low", "close", "volume", "dt_parsed"]
    assert len(df_read) == 390

    # Audit through session auditor
    session, report = audit_ticker_session("SPY", session_d, df_read, grid)

    # Required acceptance criteria
    assert report.total_bars == 390
    assert report.missing_bars == 0
    assert report.malformed_timestamp_count == 0
    assert report.duplicate_bars == 0
    assert report.excluded is False
    assert session.is_valid is True
    assert len(session.bars) == 390

    # Required point-in-time reference bars
    assert session.get_09_59_close() == 105.50
    assert session.get_15_30_open() == 106.25
    assert session.get_15_59_close() == 108.00


def test_direct_bar_start_compatibility() -> None:
    """Verify that an audited DataFrame containing only locked bar_start is accepted directly."""
    session_d = date(2026, 1, 15)
    grid = build_regular_session_grid(session_d)

    # DataFrame with strictly the locked persisted columns (no dt_parsed, no datetime alias)
    rows = []
    for dt in grid:
        rows.append(
            {
                "bar_start": dt.isoformat(),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000.0,
            }
        )
    df_direct = pd.DataFrame(rows)

    session, report = audit_ticker_session("SPY", session_d, df_direct, grid)
    assert report.total_bars == 390
    assert report.missing_bars == 0
    assert report.malformed_timestamp_count == 0
    assert report.duplicate_bars == 0
    assert report.excluded is False
    assert session.is_valid is True
    assert len(session.bars) == 390


def test_dt_parsed_precedence_over_bar_start() -> None:
    """Verify dt_parsed has precedence over bar_start, with clean fallback on None/NaT."""
    # When both are present, dt_parsed takes precedence
    ts_1 = pd.Timestamp("2026-01-02T14:30:00Z")
    ts_2 = "2026-01-02T14:31:00Z"
    row_both = pd.Series({"dt_parsed": ts_1, "bar_start": ts_2})
    res_both = _resolve_bar_timestamp(row_both)
    assert res_both is not None
    assert res_both.strftime("%H:%M") == "14:30"

    # When dt_parsed is None, bar_start is used
    row_none = pd.Series({"dt_parsed": None, "bar_start": ts_2})
    res_none = _resolve_bar_timestamp(row_none)
    assert res_none is not None
    assert res_none.strftime("%H:%M") == "14:31"

    # When dt_parsed is pd.NaT, bar_start is used
    row_nat = pd.Series({"dt_parsed": pd.NaT, "bar_start": ts_2})
    res_nat = _resolve_bar_timestamp(row_nat)
    assert res_nat is not None
    assert res_nat.strftime("%H:%M") == "14:31"


def test_timestamp_candidate_precedence_full_hierarchy() -> None:
    """Verify locked candidate precedence hierarchy: dt_parsed -> bar_start -> datetime -> timestamp -> t."""
    t1 = "2026-01-02T14:30:00Z"
    t2 = "2026-01-02T14:31:00Z"
    t3 = "2026-01-02T14:32:00Z"
    t4 = "2026-01-02T14:33:00Z"
    t5 = "2026-01-02T14:34:00Z"

    # 1. dt_parsed over all
    r = {"dt_parsed": t1, "bar_start": t2, "datetime": t3, "timestamp": t4, "t": t5}
    assert _resolve_bar_timestamp(r).strftime("%H:%M") == "14:30"

    # 2. bar_start over lower
    r = {"bar_start": t2, "datetime": t3, "timestamp": t4, "t": t5}
    assert _resolve_bar_timestamp(r).strftime("%H:%M") == "14:31"

    # 3. datetime over lower
    r = {"datetime": t3, "timestamp": t4, "t": t5}
    assert _resolve_bar_timestamp(r).strftime("%H:%M") == "14:32"

    # 4. timestamp over lower
    r = {"timestamp": t4, "t": t5}
    assert _resolve_bar_timestamp(r).strftime("%H:%M") == "14:33"

    # 5. t standalone
    r = {"t": t5}
    assert _resolve_bar_timestamp(r).strftime("%H:%M") == "14:34"

    # Malformed higher candidate does NOT silently fall back to lower candidate
    r_bad = {"bar_start": "INVALID_TS", "datetime": t3}
    assert _resolve_bar_timestamp(r_bad) is None

    # Unknown timestamp columns are rejected
    r_unknown = {"time": t1, "date": "2026-01-02", "ts": t1}
    assert _resolve_bar_timestamp(r_unknown) is None


def test_existing_alias_compatibility() -> None:
    """Verify existing in-memory aliases (datetime, timestamp, t) remain fully supported."""
    session_d = date(2026, 1, 15)
    grid = build_regular_session_grid(session_d)

    # 1. 'datetime' alias
    df_dt = pd.DataFrame(
        [{"datetime": dt.isoformat(), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0} for dt in grid]
    )
    s_dt, rep_dt = audit_ticker_session("SPY", session_d, df_dt, grid)
    assert rep_dt.total_bars == 390 and s_dt.is_valid is True

    # 2. 'timestamp' alias
    df_ts = pd.DataFrame(
        [{"timestamp": dt.isoformat(), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0} for dt in grid]
    )
    s_ts, rep_ts = audit_ticker_session("SPY", session_d, df_ts, grid)
    assert rep_ts.total_bars == 390 and s_ts.is_valid is True

    # 3. 't' alias
    df_t = pd.DataFrame(
        [{"t": dt.isoformat(), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0} for dt in grid]
    )
    s_t, rep_t = audit_ticker_session("SPY", session_d, df_t, grid)
    assert rep_t.total_bars == 390 and s_t.is_valid is True


def test_canonical_roundtrip_missing_bars_boundary(tmp_path: Path) -> None:
    """Verify 19/20 missing bar boundaries hold through writer -> reader -> auditor round-trip."""
    session_d = date(2026, 1, 15)
    grid = build_regular_session_grid(session_d)

    # 19 missing bars (4.87% <= 5.0%) -> PASS
    drop_19 = [to_market_time(grid[i]).strftime("%H:%M") for i in range(19)]
    df_19 = generate_synthetic_session_bars("SPY", session_d, drop_minutes=drop_19)
    p_19 = tmp_path / "drop_19.csv"
    write_normalized_bars_csv(p_19, df_19)
    df_read_19, _ = read_normalized_bars_csv(p_19)
    sess_19, rep_19 = audit_ticker_session("SPY", session_d, df_read_19, grid)

    assert rep_19.missing_bars == 19
    assert rep_19.missing_rate_pct <= 5.0
    assert rep_19.excluded is False
    assert sess_19.is_valid is True

    # 20 missing bars (5.13% > 5.0%) -> EXCLUDE
    drop_20 = [to_market_time(grid[i]).strftime("%H:%M") for i in range(20)]
    df_20 = generate_synthetic_session_bars("SPY", session_d, drop_minutes=drop_20)
    p_20 = tmp_path / "drop_20.csv"
    write_normalized_bars_csv(p_20, df_20)
    df_read_20, _ = read_normalized_bars_csv(p_20)
    sess_20, rep_20 = audit_ticker_session("SPY", session_d, df_read_20, grid)

    assert rep_20.missing_bars == 20
    assert rep_20.missing_rate_pct > 5.0
    assert rep_20.excluded is True
    assert sess_20.is_valid is False


def test_canonical_roundtrip_duplicate_bars_boundary(tmp_path: Path) -> None:
    """Verify 3/4 duplicate bar boundaries hold through writer -> reader -> auditor round-trip."""
    session_d = date(2026, 1, 15)
    grid = build_regular_session_grid(session_d)

    # 3 duplicate bars (0.77% <= 1.0%) -> PASS
    dup_3 = [to_market_time(grid[i]).strftime("%H:%M") for i in range(3)]
    df_3 = generate_synthetic_session_bars("SPY", session_d, duplicate_minutes=dup_3)
    p_3 = tmp_path / "dup_3.csv"
    write_normalized_bars_csv(p_3, df_3)
    df_read_3, _ = read_normalized_bars_csv(p_3)
    sess_3, rep_3 = audit_ticker_session("SPY", session_d, df_read_3, grid)

    assert rep_3.duplicate_bars == 3
    assert rep_3.duplicate_rate_pct <= 1.0
    assert rep_3.excluded is False
    assert sess_3.is_valid is True

    # 4 duplicate bars (1.03% > 1.0%) -> EXCLUDE
    dup_4 = [to_market_time(grid[i]).strftime("%H:%M") for i in range(4)]
    df_4 = generate_synthetic_session_bars("SPY", session_d, duplicate_minutes=dup_4)
    p_4 = tmp_path / "dup_4.csv"
    write_normalized_bars_csv(p_4, df_4)
    df_read_4, _ = read_normalized_bars_csv(p_4)
    sess_4, rep_4 = audit_ticker_session("SPY", session_d, df_read_4, grid)

    assert rep_4.duplicate_bars == 4
    assert rep_4.duplicate_rate_pct > 1.0
    assert rep_4.excluded is True
    assert sess_4.is_valid is False
