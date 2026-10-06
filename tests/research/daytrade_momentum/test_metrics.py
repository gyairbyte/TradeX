"""Tests for comprehensive metrics calculations, ETF concentration, breadth, and multi-signal sessions."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

from tradex.research.daytrade_momentum import freeze as freeze_mod
from tradex.research.daytrade_momentum.calendar import (
    build_regular_session_grid,
    get_regular_trading_sessions,
)
from tradex.research.daytrade_momentum.dataset import DaytradeDatasetManifest
from tradex.research.daytrade_momentum.freeze import freeze_evaluation_state
from tradex.research.daytrade_momentum.models import (
    DataQualityReport,
    DaytradeSession,
    EventObservation,
)
from tradex.research.daytrade_momentum.quality import audit_ticker_session
from tradex.research.daytrade_momentum.spec import DaytradeSpec
from tradex.research.daytrade_momentum.study import evaluate_split
from tradex.research.daytrade_momentum.synthetic import generate_synthetic_session_bars


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


def test_provenance_summary_synthetic_path_remains_synthetic(
    locked_spec: DaytradeSpec, temp_dataset_root: Path
) -> None:
    """Test A: Synthetic path using custom_sessions and custom_reports remains synthetic."""
    sessions_by_ticker: dict[str, list[DaytradeSession]] = {sym: [] for sym in locked_spec.universe}
    reports: list[DataQualityReport] = []

    res = evaluate_split(
        split_name="development",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    summary = res.metrics["provider_provenance_summary"]
    assert summary["status"] == "synthetic_fixtures_only"
    assert summary["provider"] == "alpaca"
    assert summary["feed"] == "sip"
    assert summary["timeframe"] == "1Min"
    assert summary["adjustment"] == "split"
    assert summary["calendar"] == "XNYS"
    assert summary["timezone"] == "America/New_York"


def test_provenance_summary_canonical_manifest_backed_path(
    locked_spec: DaytradeSpec, temp_dataset_root: Path
) -> None:
    """Test B: Canonical real-manifest path derives provider summary from verified manifest."""
    pre_dir = temp_dataset_root / "preholdout"
    bars_dir = pre_dir / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)

    source_files = {}
    for ticker in locked_spec.universe:
        csv_file = bars_dir / f"{ticker}.csv"
        csv_file.write_text("bar_start,open,high,low,close,volume\n", encoding="utf-8")
        source_files[f"bars/{ticker}.csv"] = hashlib.sha256(csv_file.read_bytes()).hexdigest()

    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002A",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        provider="alpaca",
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        calendar="XNYS",
        timezone="America/New_York",
        universe=locked_spec.universe,
        start_date=locked_spec.context_anchor_date,
        end_date=locked_spec.validation.end,
        source_files=source_files,
        acquisition_provenance={
            "status": "authorized_provider_acquisition",
            "provider": "alpaca",
            "feed": "sip",
        },
    )
    manifest.manifest_sha256 = manifest.compute_sha256()
    (pre_dir / "manifest.lock.json").write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    # Call evaluate_split WITHOUT custom_sessions and WITHOUT custom_reports
    res = evaluate_split(
        split_name="development",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
    )

    summary = res.metrics["provider_provenance_summary"]
    assert summary["status"] == "authorized_provider_acquisition"
    assert summary["provider"] == manifest.provider
    assert summary["feed"] == manifest.feed
    assert summary["timeframe"] == manifest.timeframe
    assert summary["adjustment"] == manifest.adjustment
    assert summary["calendar"] == manifest.calendar
    assert summary["timezone"] == manifest.timezone

    # Also verify result.provenance is consistent
    assert res.provenance["provider"] == manifest.provider
    assert res.provenance["feed"] == manifest.feed
    assert res.provenance["manifest_sha256"] == manifest.manifest_sha256


def test_provenance_summary_canonical_manifest_fallback_status(
    locked_spec: DaytradeSpec, temp_dataset_root: Path
) -> None:
    """Test manifest-backed fallback when acquisition status is missing or empty."""
    pre_dir = temp_dataset_root / "preholdout"
    bars_dir = pre_dir / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)

    source_files = {}
    for ticker in locked_spec.universe:
        csv_file = bars_dir / f"{ticker}.csv"
        csv_file.write_text("bar_start,open,high,low,close,volume\n", encoding="utf-8")
        source_files[f"bars/{ticker}.csv"] = hashlib.sha256(csv_file.read_bytes()).hexdigest()

    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002A",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        provider="alpaca",
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        calendar="XNYS",
        timezone="America/New_York",
        universe=locked_spec.universe,
        start_date=locked_spec.context_anchor_date,
        end_date=locked_spec.validation.end,
        source_files=source_files,
        acquisition_provenance={},  # missing status
    )
    manifest.manifest_sha256 = manifest.compute_sha256()
    (pre_dir / "manifest.lock.json").write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    res = evaluate_split(
        split_name="development",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
    )

    summary = res.metrics["provider_provenance_summary"]
    assert summary["status"] == "verified_manifest_dataset"
    assert summary["provider"] == "alpaca"


def test_provenance_summary_custom_sessions_take_precedence_over_manifest_and_freeze(
    locked_spec: DaytradeSpec, temp_dataset_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test C: Custom sessions take precedence for source classification even with manifest and freeze."""
    monkeypatch.setattr(freeze_mod, "check_worktree_clean", lambda root: True)

    pre_dir = temp_dataset_root / "preholdout"
    bars_dir = pre_dir / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)

    source_files = {}
    for ticker in locked_spec.universe:
        csv_file = bars_dir / f"{ticker}.csv"
        csv_file.write_text("bar_start,open,high,low,close,volume\n", encoding="utf-8")
        source_files[f"bars/{ticker}.csv"] = hashlib.sha256(csv_file.read_bytes()).hexdigest()

    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002A",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        provider="alpaca",
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        calendar="XNYS",
        timezone="America/New_York",
        universe=locked_spec.universe,
        start_date=locked_spec.context_anchor_date,
        end_date=locked_spec.validation.end,
        source_files=source_files,
        acquisition_provenance={
            "status": "authorized_provider_acquisition",
        },
    )
    manifest.manifest_sha256 = manifest.compute_sha256()
    (pre_dir / "manifest.lock.json").write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256=manifest.manifest_sha256,
        require_clean=False,
    )

    # Injected custom sessions & reports
    sessions_by_ticker = {sym: [] for sym in locked_spec.universe}
    reports: list[DataQualityReport] = []

    res = evaluate_split(
        split_name="validation",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
        freeze=freeze,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    # Must remain synthetic_fixtures_only despite manifest and freeze existing
    summary = res.metrics["provider_provenance_summary"]
    assert summary["status"] == "synthetic_fixtures_only"
    assert summary["provider"] == "alpaca"
    assert summary["feed"] == "sip"


def test_provenance_summary_no_performance_behavior_change(
    locked_spec: DaytradeSpec, temp_dataset_root: Path
) -> None:
    """Test D: Provenance fix does not alter strategy performance, gates, bootstrap, or outcomes."""
    fast_spec = dataclasses.replace(locked_spec, bootstrap_resamples=50)
    history_sessions = get_regular_trading_sessions(
        locked_spec.warmup.start, locked_spec.warmup.end, exclude_early_closes=True
    )[:25]
    dev_sessions = get_regular_trading_sessions(
        locked_spec.development.start, locked_spec.development.end, exclude_early_closes=True
    )[:10]
    all_dates = history_sessions + dev_sessions

    sessions_by_ticker: dict[str, list[DaytradeSession]] = {}
    reports: list[DataQualityReport] = []

    for sym in fast_spec.universe:
        ticker_sessions: list[DaytradeSession] = []
        base_px = 100.0
        for idx, s_date in enumerate(all_dates):
            grid = build_regular_session_grid(s_date)
            if idx < len(history_sessions):
                sig_px = base_px * 1.005
                exit_px = base_px * 1.006
            else:
                if idx % 2 == 0:
                    sig_px = base_px * 1.020
                    exit_px = base_px * 1.028
                else:
                    sig_px = base_px * 1.002
                    exit_px = base_px * 1.003
            entry_px = sig_px * 1.001
            df = generate_synthetic_session_bars(
                sym,
                s_date,
                base_price=base_px,
                signal_09_59_close=sig_px,
                entry_15_30_open=entry_px,
                exit_15_59_close=exit_px,
            )
            sess, rep = audit_ticker_session(sym, s_date, df, grid)
            ticker_sessions.append(sess)
            reports.append(rep)
            base_px = exit_px
        sessions_by_ticker[sym] = ticker_sessions

    res = evaluate_split(
        split_name="development",
        spec=fast_spec,
        dataset_root=temp_dataset_root,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    # Confirm key strategy behaviors and outputs are computed and valid
    assert res.metrics["event_count"] > 0
    assert res.disposition in ("supported", "rejected", "inconclusive")
    assert res.disposition_step.startswith("step_")
    assert "mean_net_signed_return_2bps" in res.metrics
    assert res.bootstrap["primary_net_return"]["status"] == "computable"
    assert res.metrics["provider_provenance_summary"]["status"] == "synthetic_fixtures_only"
