"""Data quality evaluation tests."""
from __future__ import annotations

from datetime import date

from tradex.research.daytrade_reversal.calendar import build_regular_session_grid
from tradex.research.daytrade_reversal.quality import (
    audit_missing_ticker_session,
    audit_ticker_session,
    evaluate_split_quality,
)
from tradex.research.daytrade_reversal.synthetic import generate_synthetic_session_bars


def test_clean_session_passes_quality_audit() -> None:
    """A clean 390-bar session passes with 0 missing, 0 duplicates, and excluded=False."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)
    raw_df = generate_synthetic_session_bars("AAPL", session_d)

    session, report = audit_ticker_session("AAPL", session_d, raw_df, grid)
    assert not report.excluded
    assert report.missing_bars == 0
    assert report.missing_rate_pct == 0.0
    assert report.duplicate_bars == 0
    assert report.malformed_timestamp_count == 0
    assert report.malformed_ohlcv_count == 0
    assert session.is_valid
    assert len(session.bars) == 390


def test_missing_bars_over_5pct_excludes_session() -> None:
    """Missing bar rate > 5.0% (> 19 missing bars out of 390) excludes the entire ticker-session."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)

    # Drop 20 bars: 20 / 390 = 5.13% > 5.0%
    drop_mins = [f"10:{i:02d}" for i in range(20)]
    raw_df = generate_synthetic_session_bars("AAPL", session_d, drop_minutes=drop_mins)

    session, report = audit_ticker_session("AAPL", session_d, raw_df, grid)
    assert report.excluded
    assert report.missing_bars == 20
    assert report.missing_rate_pct > 5.0
    assert not session.is_valid
    assert any("missing_rate" in r for r in report.exclusion_reasons)


def test_missing_bars_under_5pct_retained() -> None:
    """Missing bar rate <= 5.0% (e.g. 10 missing bars: 10/390 = 2.56%) retains the ticker-session."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)

    drop_mins = [f"10:{i:02d}" for i in range(10)]
    raw_df = generate_synthetic_session_bars("AAPL", session_d, drop_minutes=drop_mins)

    session, report = audit_ticker_session("AAPL", session_d, raw_df, grid)
    assert not report.excluded
    assert report.missing_bars == 10
    assert report.missing_rate_pct <= 5.0
    assert session.is_valid
    assert len(session.bars) == 380


def test_duplicate_bars_over_1pct_excludes_session() -> None:
    """Duplicate bar rate > 1.0% (> 3 duplicates: e.g. 5 duplicates: 5/390 = 1.28%) excludes session."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)

    dup_mins = [f"11:{i:02d}" for i in range(5)]
    raw_df = generate_synthetic_session_bars("AAPL", session_d, duplicate_minutes=dup_mins)

    session, report = audit_ticker_session("AAPL", session_d, raw_df, grid)
    assert report.excluded
    assert report.duplicate_bars == 5
    assert report.duplicate_rate_pct > 1.0
    assert not session.is_valid
    assert any("duplicate_rate" in r for r in report.exclusion_reasons)


def test_malformed_timestamps_below_5pct_retained() -> None:
    """Malformed timestamps are discarded; if total missing <= 5.0%, session remains usable."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)

    raw_df = generate_synthetic_session_bars(
        "AAPL", session_d, malformed_timestamps=["10:15", "10:16"]
    )

    session, report = audit_ticker_session("AAPL", session_d, raw_df, grid)
    assert not report.excluded
    assert report.malformed_timestamp_count == 2
    assert report.missing_bars == 2
    assert session.is_valid
    assert len(session.bars) == 388


def test_malformed_timestamps_over_5pct_excludes_session() -> None:
    """Malformed timestamps causing missing rate > 5.0% exclude the session."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)

    malformed = [f"10:{i:02d}" for i in range(25)]
    raw_df = generate_synthetic_session_bars(
        "AAPL", session_d, malformed_timestamps=malformed
    )

    session, report = audit_ticker_session("AAPL", session_d, raw_df, grid)
    assert report.excluded
    assert report.malformed_timestamp_count == 25
    assert report.missing_bars == 25
    assert report.missing_rate_pct > 5.0
    assert not session.is_valid


def test_malformed_ohlcv_values_dropped_and_audited() -> None:
    """Non-numeric, NaN, infinite, <=0 price, or <0 volume rows are dropped and counted."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)
    raw_df = generate_synthetic_session_bars("AAPL", session_d)

    # Mutate 3 rows with invalid OHLCV
    raw_df.loc[10, "open"] = float("nan")
    raw_df.loc[20, "close"] = -5.0
    raw_df.loc[30, "volume"] = -100

    session, report = audit_ticker_session("AAPL", session_d, raw_df, grid)
    assert not report.excluded
    assert report.malformed_ohlcv_count == 3
    assert report.missing_bars == 3
    assert session.is_valid
    assert len(session.bars) == 387


def test_missing_ticker_session_audit() -> None:
    """audit_missing_ticker_session produces a 100% missing, excluded report."""
    session_d = date(2025, 1, 2)
    session, report = audit_missing_ticker_session("MSFT", session_d)
    assert not session.is_valid
    assert len(session.bars) == 0
    assert report.excluded is True
    assert report.missing_bars == 390
    assert report.missing_rate_pct == 100.0
    assert "all_bars_missing" in report.exclusion_reasons


def test_split_level_quality_gate() -> None:
    """Split where > 5.0% of ticker-sessions are excluded marks exceeds_split_gate = True."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)

    # 100 sessions: 6 excluded (6.0% > 5.0%)
    reports = []
    for i in range(100):
        if i < 6:
            df = generate_synthetic_session_bars(
                "AAPL", session_d, drop_minutes=[f"10:{m:02d}" for m in range(25)]
            )
        else:
            df = generate_synthetic_session_bars("AAPL", session_d)
        _, rep = audit_ticker_session(f"TICKER_{i}", session_d, df, grid)
        reports.append(rep)

    split_summary = evaluate_split_quality(reports, "validation")
    assert split_summary.total_ticker_sessions == 100
    assert split_summary.excluded_ticker_sessions == 6
    assert split_summary.excluded_rate_pct == 6.0
    assert split_summary.exceeds_split_gate is True
    assert split_summary.is_valid is False
