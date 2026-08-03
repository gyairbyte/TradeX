"""Tests for the structured ``scan_gaps_with_report`` orchestrator."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pandas as pd
import pytest

from tradex.data.fetcher import ProviderCapabilityError
from tradex.premarket.config import GapScanConfig
from tradex.premarket.gap_scanner import scan_gaps_with_report
from tradex.premarket.models import (
    DailyLiquidityBaseline,
    GapCatalystContext,
    PremarketBarsResult,
    PremarketSnapshot,
    SpreadSnapshot,
)


def _baseline(prev_close: float, avg_vol: float = 1_000_000.0) -> DailyLiquidityBaseline:
    return DailyLiquidityBaseline(
        previous_session_date=date(2024, 1, 2),
        previous_close=prev_close,
        lookback_sessions_requested=20,
        lookback_sessions_available=20,
        average_daily_volume=avg_vol,
        median_daily_volume=avg_vol,
        average_daily_dollar_volume=prev_close * avg_vol,
        median_daily_dollar_volume=prev_close * avg_vol,
    )


def _snapshot(last: float, volume: int = 1000) -> PremarketSnapshot:
    return PremarketSnapshot(
        ticker="AAPL",
        session_date=date(2024, 1, 3),
        requested_provider="yahoo",
        actual_provider="yahoo",
        first_bar_time=datetime(2024, 1, 3, 9, 0, tzinfo=UTC),
        last_bar_time=datetime(2024, 1, 3, 13, 0, tzinfo=UTC),
        bar_count=10,
        premarket_open=last - 1.0,
        premarket_high=last + 1.0,
        premarket_low=last - 1.0,
        premarket_last=last,
        premarket_volume=volume,
        premarket_dollar_volume=last * volume,
        premarket_vwap=last,
        data_age_minutes=5.0,
    )


def _make_bars() -> pd.DataFrame:
    times = pd.DatetimeIndex(["2024-01-03 09:00", "2024-01-03 10:00", "2024-01-03 13:00"], tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [100, 200, 300],
        },
        index=times,
    )


def _bars() -> PremarketBarsResult:
    return PremarketBarsResult(
        ticker="AAPL",
        requested_provider="yahoo",
        actual_provider="yahoo",
        session_date=date(2024, 1, 3),
        bars=_make_bars(),
    )


def test_scan_gaps_with_report_qualifies():
    config = GapScanConfig(min_abs_gap_pct=2.0)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=_snapshot(105.0)
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )

    assert report.counts()["qualified"] == 1
    assert report.counts()["failed"] == 0
    assert not report.results.empty
    assert report.results.iloc[0]["gap_pct"] == pytest.approx(5.0)
    assert report.results.iloc[0]["tier"] == "large"
    assert report.results.iloc[0]["direction"] == "up"


def test_scan_gaps_with_report_range_uses_previous_close():
    """Range % uses the previous close as the denominator, not the pre-market open."""
    # prev_close=100, pre_market open=150, high=160, low=140.
    # Range using prev_close: (160 - 140) / 100 * 100 = 20.0
    # Range using open: (160 - 140) / 150 * 100 ≈ 13.33
    snapshot = PremarketSnapshot(
        ticker="AAPL",
        session_date=date(2024, 1, 3),
        requested_provider="yahoo",
        actual_provider="yahoo",
        first_bar_time=datetime(2024, 1, 3, 9, 0, tzinfo=UTC),
        last_bar_time=datetime(2024, 1, 3, 13, 0, tzinfo=UTC),
        bar_count=10,
        premarket_open=150.0,
        premarket_high=160.0,
        premarket_low=140.0,
        premarket_last=155.0,
        premarket_volume=1000,
        premarket_dollar_volume=155_000.0,
        premarket_vwap=155.0,
        data_age_minutes=5.0,
    )
    config = GapScanConfig(min_abs_gap_pct=2.0)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=snapshot
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )
    assert report.results.iloc[0]["premarket_range_pct"] == pytest.approx(20.0)


def test_scan_gaps_with_report_filters_below_min_gap():
    config = GapScanConfig(min_abs_gap_pct=10.0)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=_snapshot(105.0)
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )

    assert report.counts()["qualified"] == 0
    assert report.counts()["filtered"] == 1
    assert "gap below 10.0%" in report.observations.iloc[0]["filter_reasons"]


def test_scan_gaps_with_report_outside_window_before_premarket():
    config = GapScanConfig()
    as_of = datetime(2024, 1, 3, 7, 0, tzinfo=UTC)  # 02:00 ET
    report = scan_gaps_with_report(["AAPL"], config=config, as_of=as_of)
    assert report.counts()["outside_window"] == 1
    assert report.counts()["qualified"] == 0
    assert "before pre-market session" in report.observations.iloc[0]["filter_reasons"]


def test_scan_gaps_with_report_outside_window_after_open():
    config = GapScanConfig(allow_after_open=False)
    as_of = datetime(2024, 1, 3, 14, 45, tzinfo=UTC)  # 09:45 ET
    report = scan_gaps_with_report(["AAPL"], config=config, as_of=as_of)
    assert report.counts()["outside_window"] == 1
    assert "regular session has opened" in report.observations.iloc[0]["filter_reasons"]


def test_scan_gaps_with_report_allow_after_open():
    config = GapScanConfig(min_abs_gap_pct=2.0, allow_after_open=True)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=_snapshot(105.0)
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        as_of = datetime(2024, 1, 3, 14, 45, tzinfo=UTC)
        report = scan_gaps_with_report(["AAPL"], config=config, as_of=as_of)

    assert report.counts()["outside_window"] == 0
    assert report.counts()["qualified"] == 1


def test_scan_gaps_with_report_propagates_provider_error():
    config = GapScanConfig()
    error = ProviderCapabilityError("schwab premarket unsupported")
    with (
        patch("tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline", side_effect=error),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars") as mock_bars,
    ):
        report = scan_gaps_with_report(
            ["AAPL"],
            config=config,
            provider="schwab",
            as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC),
        )

    assert report.counts()["failed"] == 1
    assert "AAPL" in report.provider_errors
    mock_bars.assert_not_called()


def test_scan_gaps_with_report_filters_by_volume_ratio():
    config = GapScanConfig(min_abs_gap_pct=2.0, min_premarket_volume_ratio=1.0)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0, avg_vol=10_000.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot",
            return_value=_snapshot(105.0, volume=1000),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )

    assert report.counts()["qualified"] == 0
    assert report.counts()["filtered"] == 1
    assert "volume ratio" in str(report.observations.iloc[0]["filter_reasons"])


def test_scan_gaps_with_report_to_dict_json_safe():
    config = GapScanConfig()
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=_snapshot(105.0)
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )

    d = report.to_dict()
    assert d["session_date"] == "2024-01-03"
    assert d["as_of"].endswith("+00:00")
    assert "results" in d
    assert "observations" in d
    for obs in d["observations"]:
        assert "filter_reasons" in obs
        assert "gap_pct" in obs


def _baseline_with_error(error: Exception) -> DailyLiquidityBaseline:
    return DailyLiquidityBaseline(
        previous_session_date=None,
        previous_close=None,
        lookback_sessions_requested=20,
        lookback_sessions_available=0,
        average_daily_volume=0.0,
        median_daily_volume=0.0,
        average_daily_dollar_volume=0.0,
        median_daily_dollar_volume=0.0,
        requested_provider="yahoo",
        actual_provider=None,
        error=error,
    )


def test_scan_gaps_with_report_partial_failure_and_success():
    """One ticker failing does not hide another qualifying ticker."""
    config = GapScanConfig(min_abs_gap_pct=2.0)
    side_effects = [
        _baseline_with_error(ProviderCapabilityError("yahoo history failed")),
        _baseline(100.0),
    ]
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            side_effect=side_effects,
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=_snapshot(105.0)
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["TSLA", "AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )

    assert report.counts()["requested"] == 2
    assert report.counts()["qualified"] == 1
    assert report.counts()["failed"] == 1
    assert "TSLA" in report.provider_errors
    assert report.actual_provider == "yahoo"


def test_scan_gaps_with_report_filters_by_min_price():
    config = GapScanConfig(min_abs_gap_pct=2.0, min_price=110.0)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=_snapshot(105.0)
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )
    assert report.counts()["filtered"] == 1
    assert "price below $110.0" in report.observations.iloc[0]["filter_reasons"]


def test_scan_gaps_with_report_filters_by_premarket_volume():
    config = GapScanConfig(min_abs_gap_pct=2.0, min_premarket_volume=10_000)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot",
            return_value=_snapshot(105.0, volume=1000),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )
    assert report.counts()["filtered"] == 1
    assert "pre-market volume 1000 below 10000" in report.observations.iloc[0]["filter_reasons"]


def test_scan_gaps_with_report_filters_by_premarket_dollar_volume():
    config = GapScanConfig(min_abs_gap_pct=2.0, min_premarket_dollar_volume=1_000_000.0)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot",
            return_value=_snapshot(105.0, volume=1000),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )
    assert report.counts()["filtered"] == 1
    assert any("pre-market dollar volume below" in r for r in report.observations.iloc[0]["filter_reasons"])


def test_scan_gaps_with_report_filters_by_data_age():
    config = GapScanConfig(min_abs_gap_pct=2.0, max_data_age_minutes=1.0)
    snap = _snapshot(105.0)
    snap = snap.__class__(**{**snap.__dict__, "data_age_minutes": 5.0})
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch("tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=snap),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )
    assert report.counts()["filtered"] == 1
    assert any("data age" in r for r in report.observations.iloc[0]["filter_reasons"])


def test_scan_gaps_with_report_filters_by_spread_bps():
    config = GapScanConfig(min_abs_gap_pct=2.0, max_spread_bps=10.0)
    spread = SpreadSnapshot(available=True, bid=100.0, ask=100.5, spread_bps=50.0)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=_snapshot(105.0)
        ),
        patch("tradex.premarket.gap_scanner.fetch_spread_snapshot", return_value=spread),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )
    assert report.counts()["filtered"] == 1
    assert any("spread" in r for r in report.observations.iloc[0]["filter_reasons"])


def test_scan_gaps_with_report_requires_spread():
    config = GapScanConfig(min_abs_gap_pct=2.0, require_spread=True)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=_snapshot(105.0)
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )
    assert report.counts()["filtered"] == 1
    assert any("spread data required" in r for r in report.observations.iloc[0]["filter_reasons"])


def test_scan_gaps_with_report_requires_catalyst():
    config = GapScanConfig(min_abs_gap_pct=2.0, require_catalyst=True)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=_snapshot(105.0)
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3), earnings_status="none_detected", headline_status="none_detected"),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )
    assert report.counts()["filtered"] == 1
    assert any("catalyst context required" in r for r in report.observations.iloc[0]["filter_reasons"])


def test_scan_gaps_with_report_stage_counts():
    """Stage-specific failure counts are exposed and do not depend on final status."""
    config = GapScanConfig(min_abs_gap_pct=2.0)
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot", return_value=_snapshot(105.0)
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False, error=Exception("no quote")),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(
                ticker="AAPL",
                session_date=date(2024, 1, 3),
                earnings_status="unavailable",
                error=Exception("no earnings"),
            ),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )

    counts = report.counts()
    assert counts["qualified"] == 1
    assert counts["baseline_failures"] == 0
    assert counts["premarket_failures"] == 0
    assert counts["spread_failures"] == 1
    assert counts["catalyst_failures"] == 1
    assert counts["calculation_failures"] == 0
    assert "AAPL" not in report.provider_errors

    obs = report.observations.iloc[0]
    assert pd.isna(obs["baseline_error"])
    assert pd.isna(obs["premarket_error"])
    assert obs["spread_error"] is not None and "no quote" in obs["spread_error"]
    assert obs["catalyst_error"] is not None and "no earnings" in obs["catalyst_error"]
    assert pd.isna(obs["calculation_error"])


def test_scan_gaps_with_report_calculation_failure_not_provider_error():
    """A snapshot calculation failure is a calculation failure, not a provider error."""
    config = GapScanConfig()
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            return_value=_baseline(100.0),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars", return_value=_bars()),
        patch(
            "tradex.premarket.gap_scanner.build_premarket_snapshot",
            side_effect=RuntimeError("snapshot exploded"),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_spread_snapshot",
            return_value=SpreadSnapshot(available=False),
        ),
        patch(
            "tradex.premarket.gap_scanner.fetch_catalyst_context",
            return_value=GapCatalystContext(ticker="AAPL", session_date=date(2024, 1, 3)),
        ),
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )

    assert report.counts()["calculation_failure"] == 1
    assert report.counts()["provider_failure"] == 0
    assert report.counts()["calculation_failures"] == 1
    assert report.counts()["baseline_failures"] == 0
    assert report.counts()["premarket_failures"] == 0
    assert "AAPL" not in report.provider_errors
    assert "snapshot exploded" in str(report.observations.iloc[0]["calculation_error"])


def test_scan_gaps_with_report_baseline_failure_stage_count():
    """A baseline provider failure increments baseline_failures and provider_errors."""
    config = GapScanConfig()
    with (
        patch(
            "tradex.premarket.gap_scanner.fetch_daily_liquidity_baseline",
            side_effect=ProviderCapabilityError("yahoo history failed"),
        ),
        patch("tradex.premarket.gap_scanner.fetch_premarket_bars") as mock_bars,
    ):
        report = scan_gaps_with_report(
            ["AAPL"], config=config, as_of=datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
        )

    assert report.counts()["provider_failure"] == 1
    assert report.counts()["baseline_failures"] == 1
    assert report.counts()["premarket_failures"] == 0
    assert report.counts()["calculation_failures"] == 0
    assert "AAPL" in report.provider_errors
    assert "yahoo history failed" in report.provider_errors["AAPL"]
    mock_bars.assert_not_called()


def test_scan_gaps_with_report_rejects_empty_ticker_list():
    with pytest.raises(ValueError):
        scan_gaps_with_report([], config=GapScanConfig())
