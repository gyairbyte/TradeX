"""Tests for pre-market data models."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from tradex.premarket.gap_scanner import _classify_gap, _gap_note
from tradex.premarket.models import (
    GAP_TIERS,
    DailyLiquidityBaseline,
    GapCatalystContext,
    GapScanReport,
    SpreadSnapshot,
    _clean_value,
)


def test_gap_tiers():
    assert GAP_TIERS["massive"] == 8.0
    assert GAP_TIERS["large"] == 4.0
    assert GAP_TIERS["moderate"] == 2.0


def test_classify_gap():
    assert _classify_gap(9.0) == ("massive", "up")
    assert _classify_gap(5.0) == ("large", "up")
    assert _classify_gap(2.5) == ("moderate", "up")
    assert _classify_gap(1.0) == ("small", "up")
    assert _classify_gap(-9.0) == ("massive", "down")
    assert _classify_gap(-0.5) == ("small", "down")


def test_gap_note():
    note = _gap_note(5.0, "large", "up", None)
    assert "Large up gap" in note
    note2 = _gap_note(-8.0, "massive", "down", "earnings_today")
    assert "earnings date noted" in note2


def test_catalyst_context_status_combinations():
    ctx = GapCatalystContext(
        ticker="AAPL",
        session_date=date(2024, 1, 3),
        earnings_status="earnings_today",
        headline_status="recent_headline",
    )
    assert ctx.status == "earnings_and_recent_headline"

    ctx = GapCatalystContext(
        ticker="AAPL", session_date=date(2024, 1, 3), earnings_status="earnings_soon"
    )
    assert ctx.status == "earnings_soon"

    ctx = GapCatalystContext(
        ticker="AAPL", session_date=date(2024, 1, 3), headline_status="recent_headline"
    )
    assert ctx.status == "recent_headline"

    ctx = GapCatalystContext(
        ticker="AAPL",
        session_date=date(2024, 1, 3),
        earnings_status="none_detected",
        headline_status="none_detected",
    )
    assert ctx.status == "none_detected"

    ctx = GapCatalystContext(
        ticker="AAPL", session_date=date(2024, 1, 3), earnings_status="unavailable"
    )
    assert ctx.status == "unavailable"

    ctx = GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3))
    assert ctx.status == "not_requested"


def test_clean_value():
    assert _clean_value(float("nan")) is None
    assert _clean_value(float("inf")) is None
    assert _clean_value(date(2024, 1, 3)) == "2024-01-03"
    assert _clean_value(datetime(2024, 1, 3, 12, 0, tzinfo=UTC)) == "2024-01-03T12:00:00+00:00"
    assert _clean_value([float("nan"), 1.0]) == [None, 1.0]
    assert _clean_value("foo") == "foo"


def test_gap_scan_report_counts_and_to_dict():
    from tradex.premarket.config import GapScanConfig

    observations = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "status": ["qualified", "filtered", "failed", "outside_window"],
            "gap_pct": [5.0, 1.0, None, None],
            "filter_reasons": [[], ["gap below 2.0%"], None, None],
        }
    )
    results = observations[observations["status"] == "qualified"].drop(columns=["status"])
    report = GapScanReport(
        session_date=date(2024, 1, 3),
        as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC),
        requested_provider="yahoo",
        actual_provider="yahoo",
        config=GapScanConfig(),
        requested_tickers=["A", "B", "C", "D"],
        results=results,
        observations=observations,
    )
    counts = report.counts()
    assert counts["requested"] == 4
    assert counts["qualified"] == 1
    assert counts["filtered"] == 1
    assert counts["failed"] == 1
    assert counts["outside_window"] == 1

    d = report.to_dict()
    assert d["session_date"] == "2024-01-03"
    assert d["requested_provider"] == "yahoo"
    assert len(d["results"]) == 1
    assert len(d["observations"]) == 4
    assert d["counts"]["qualified"] == 1


def test_spread_snapshot_validation():
    snap = SpreadSnapshot(
        available=True, bid=10.0, ask=10.05, midpoint=10.025, spread_bps=5.0, source="injected"
    )
    assert snap.available is True
    assert snap.spread_bps == pytest.approx(5.0)


def test_daily_liquidity_baseline_fields():
    base = DailyLiquidityBaseline(
        previous_session_date=date(2024, 1, 2),
        previous_close=100.0,
        lookback_sessions_requested=20,
        lookback_sessions_available=19,
        average_daily_volume=1_000_000.0,
        median_daily_volume=900_000.0,
        average_daily_dollar_volume=50_000_000.0,
        median_daily_dollar_volume=45_000_000.0,
    )
    assert base.previous_close == 100.0
