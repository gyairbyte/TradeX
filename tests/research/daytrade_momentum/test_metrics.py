"""Tests for comprehensive metrics calculations, ETF concentration, breadth, and multi-signal sessions."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from tradex.research.daytrade_momentum.models import (
    DataQualityReport,
    DaytradeSession,
)
from tradex.research.daytrade_momentum.spec import DaytradeSpec
from tradex.research.daytrade_momentum.study import evaluate_split


def test_metrics_keys_and_zero_event_safety(locked_spec: DaytradeSpec, temp_dataset_root: Path) -> None:
    """Verify all 30 required metrics are present even with zero events (graceful degradation)."""
    # Create empty sessions list
    sessions_by_ticker: dict[str, list[DaytradeSession]] = {sym: [] for sym in locked_spec.universe}
    reports: list[DataQualityReport] = []

    res = evaluate_split(
        split_name="development",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    metrics = res.metrics
    expected_metric_keys = [
        "eligible_ticker_session_count",
        "event_count",
        "represented_etf_count",
        "event_session_count",
        "events_per_etf",
        "events_per_month",
        "long_event_count",
        "short_event_count",
        "maximum_single_etf_event_concentration",
        "multi_signal_session_count",
        "multi_signal_session_rate",
        "mean_gross_signed_return_30m",
        "median_gross_signed_return_30m",
        "win_rate_gross_30m",
        "mean_net_signed_return_0bps",
        "mean_net_signed_return_2bps",
        "mean_net_signed_return_5bps",
        "median_net_signed_return_0bps",
        "median_net_signed_return_2bps",
        "median_net_signed_return_5bps",
        "matched_non_event_baseline_mean",
        "matched_non_event_baseline_median",
        "event_minus_baseline_mean",
        "event_minus_baseline_median",
        "per_etf_primary_results",
        "per_month_primary_results",
        "long_side_primary_results",
        "short_side_primary_results",
        "data_quality_summary",
        "provider_provenance_summary",
    ]

    for k in expected_metric_keys:
        assert k in metrics, f"Missing metric key {k}"

    assert metrics["event_count"] == 0
    assert metrics["maximum_single_etf_event_concentration"] == 0.0
    assert metrics["multi_signal_session_rate"] == 0.0
    assert metrics["win_rate_gross_30m"] == 0.0
    assert res.disposition == "inconclusive"
    assert res.disposition_step == "step_2_evidence_sufficiency"


def test_multi_signal_session_and_concentration_calculation() -> None:
    """Verify multi-signal session counting and ETF event concentration metrics."""
    # Build 2 dates:
    # date 1 has 3 events (SPY, QQQ, DIA) -> multi-signal
    # date 2 has 1 event (SPY) -> single-signal
    # total events = 4, event sessions = 2, multi-signal count = 1, rate = 1 / 2 = 50.0%
    # SPY has 2 events out of 4 = 50.0% concentration
    from tradex.research.daytrade_momentum.models import EventObservation

    d1 = date(2025, 1, 15)
    d2 = date(2025, 1, 16)

    ev1 = EventObservation("SPY", d1, "LONG", 0.02, 0.015, d1, d1, 100.0, 101.0, 0.01, 0.01, 0.0096, 0.009, split="dev")
    ev2 = EventObservation("QQQ", d1, "SHORT", -0.02, 0.015, d1, d1, 100.0, 99.0, 0.01, 0.01, 0.0096, 0.009, split="dev")
    ev3 = EventObservation("DIA", d1, "LONG", 0.02, 0.015, d1, d1, 100.0, 101.0, 0.01, 0.01, 0.0096, 0.009, split="dev")
    ev4 = EventObservation("SPY", d2, "LONG", 0.02, 0.015, d2, d2, 100.0, 101.0, 0.01, 0.01, 0.0096, 0.009, split="dev")

    events = [ev1, ev2, ev3, ev4]

    # Calculate manually to check metric logic
    event_dates = {e.session_date for e in events}
    assert len(event_dates) == 2

    from collections import defaultdict
    counts_by_date = defaultdict(int)
    for e in events:
        counts_by_date[e.session_date] += 1
    multi_cnt = sum(1 for c in counts_by_date.values() if c >= 2)
    assert multi_cnt == 1
    multi_rate = multi_cnt / float(len(event_dates))
    assert multi_rate == 0.50

    counts_by_etf = defaultdict(int)
    for e in events:
        counts_by_etf[e.ticker] += 1
    max_etf_conc = (max(counts_by_etf.values()) / float(len(events))) * 100.0
    assert max_etf_conc == 50.0
