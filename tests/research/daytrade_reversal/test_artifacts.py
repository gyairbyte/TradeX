"""Tests for artifact generation, report truthfulness, and CSV content integrity."""
from __future__ import annotations

import csv
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tradex.research.daytrade_reversal.artifacts import (
    generate_markdown_report,
    sha256_of_file,
    write_artifact_bundle,
)
from tradex.research.daytrade_reversal.models import (
    DataQualityReport,
    EventObservation,
    GateEvaluationResult,
    HorizonOutcome,
    StudyResult,
)
from tradex.research.daytrade_reversal.spec import DaytradeSpec


def _make_sample_event(event_id: str, ticker: str, split: str = "validation") -> EventObservation:
    t = datetime(2025, 7, 10, 10, 0, tzinfo=UTC)
    ev = EventObservation(
        event_id=event_id,
        ticker=ticker,
        session_date=t.date(),
        split=split,
        event_bar_start=t,
        event_available_at=t + timedelta(minutes=1),
        event_return=-0.015,
        threshold=-0.012,
        analysis_window_start=t + timedelta(minutes=1),
        analysis_window_end=t + timedelta(minutes=6),
        is_overlapping=False,
        matched_baseline_1m_net=0.0001,
        uplift_1m_net=0.0019,
    )
    ev.outcomes[1] = HorizonOutcome(
        horizon_minutes=1,
        entry_time=t + timedelta(minutes=1),
        exit_time=t + timedelta(minutes=2),
        entry_price=100.0,
        exit_price=100.2,
        gross_return=0.002,
        net_return_0bps=0.002,
        net_return_2bps=0.0016,
        net_return_5bps=0.001,
    )
    return ev


def _make_sample_dq(ticker: str) -> DataQualityReport:
    return DataQualityReport(
        ticker=ticker,
        session_date=date(2025, 7, 10),
        total_bars=390,
        expected_bars=390,
        missing_bars=0,
        missing_rate_pct=0.0,
        duplicate_bars=0,
        duplicate_rate_pct=0.0,
        malformed_timestamp_count=0,
        excluded=False,
        exclusion_reasons=[],
        malformed_ohlcv_count=0,
    )


def test_write_artifact_bundle_defaults_to_result_events_and_dq(
    tmp_path: Path,
    locked_spec: DaytradeSpec,
) -> None:
    """write_artifact_bundle must default to result.events and result.data_quality_reports when omitted."""
    ev = _make_sample_event("AAPL_20250710_1000", "AAPL")
    dq = _make_sample_dq("AAPL")

    metrics = {
        "eligible_minute_count": 360,
        "event_count": 1,
        "represented_ticker_count": 1,
        "events_per_ticker": {"AAPL": 1},
        "events_per_month": {"2025-07": 1},
        "maximum_single_ticker_event_concentration": 100.0,
        "overlapping_event_count": 0,
        "overlapping_event_rate": 0.0,
        "mean_gross_forward_return_1m": 0.002,
        "mean_gross_forward_return_2m": None,
        "mean_gross_forward_return_5m": None,
        "median_gross_forward_return_1m": 0.002,
        "median_gross_forward_return_2m": None,
        "median_gross_forward_return_5m": None,
        "win_rate_1m": 1.0,
        "win_rate_2m": 0.0,
        "win_rate_5m": 0.0,
        "mean_net_forward_return_0bps": 0.002,
        "mean_net_forward_return_2bps": 0.0016,
        "mean_net_forward_return_5bps": 0.001,
        "median_net_forward_return_0bps": 0.002,
        "median_net_forward_return_2bps": 0.0016,
        "median_net_forward_return_5bps": 0.001,
        "same_ticker_time_of_day_baseline_mean": 0.0001,
        "same_ticker_time_of_day_baseline_median": 0.0001,
        "event_minus_baseline_difference_mean": 0.0019,
        "event_minus_baseline_difference_median": 0.0019,
        "per_ticker_primary_results": {"AAPL": {"event_count": 1, "mean_net_return_2bps": 0.0016}},
        "monthly_primary_results": {"2025-07": {"event_count": 1, "mean_net_return_2bps": 0.0016}},
        "data_quality_summary": {"total_ticker_sessions": 1, "excluded_ticker_sessions": 0},
        "provider_provenance_summary": {"total_requests": 5, "total_pages": 5, "total_retries": 0},
    }

    result = StudyResult(
        task_id="DAYTRADE-001B",
        split="validation",
        disposition="supported",
        disposition_step="step_5_support",
        disposition_reason="All gates pass",
        metrics=metrics,
        gates={"sample_gate": GateEvaluationResult("sample_gate", True, {})},
        bootstrap={"primary_net_return": {"point_estimate": 0.0016}},
        data_quality={"total_ticker_sessions": 1},
        provenance={
            "provider": "alpaca",
            "feed": "sip",
            "timeframe": "1Min",
            "split": "validation",
            "spec_sha256": locked_spec.sha256,
            "evaluator_code_sha": "test_sha_1234",
            "manifest_sha256": "manifest_sha_5678",
            "evidence_confidence_cap": "limited_but_usable_evidence",
        },
        events=[ev],
        data_quality_reports=[dq],
    )

    out_dir = tmp_path / "artifacts"
    checksums = write_artifact_bundle(
        output_dir=out_dir,
        result=result,
        spec=locked_spec,
    )

    # 1. Verify data_quality.csv contains the report
    dq_csv = out_dir / "data_quality.csv"
    assert dq_csv.is_file()
    with dq_csv.open("r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert len(reader) == 2  # header + 1 row
        assert reader[1][0] == "AAPL"

    # 2. Verify events.csv contains the event
    ev_csv = out_dir / "events.csv"
    assert ev_csv.is_file()
    with ev_csv.open("r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert len(reader) == 2  # header + 1 row
        assert reader[1][0] == "AAPL_20250710_1000"
        assert reader[1][1] == "AAPL"

    # 3. Verify baseline_summary.csv has mean and median
    base_csv = out_dir / "baseline_summary.csv"
    assert base_csv.is_file()
    with base_csv.open("r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        metrics_dict = {row[0]: row[1] for row in reader[1:]}
        assert "mean_baseline_net_2bps" in metrics_dict
        assert "median_baseline_net_2bps" in metrics_dict
        assert "mean_uplift_net_2bps" in metrics_dict
        assert "median_uplift_net_2bps" in metrics_dict

    # 4. Verify per_ticker.csv and monthly.csv
    pt_csv = out_dir / "per_ticker.csv"
    with pt_csv.open("r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert len(reader) == 2
        assert reader[1][0] == "AAPL"

    m_csv = out_dir / "monthly.csv"
    with m_csv.open("r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert len(reader) == 2
        assert reader[1][0] == "2025-07"

    # 5. Verify checksums.sha256 covers all files
    chk_file = out_dir / "checksums.sha256"
    assert chk_file.is_file()
    for fn, digest in checksums.items():
        assert sha256_of_file(out_dir / fn) == digest


def test_markdown_report_is_truthful_without_hardcoded_claims(
    locked_spec: DaytradeSpec,
) -> None:
    """Report must not contain hardcoded 'zero live provider calls' or 'C2 unauthorized' claims."""
    metrics = {
        "eligible_minute_count": 1000,
        "event_count": 10,
        "represented_ticker_count": 5,
        "maximum_single_ticker_event_concentration": 20.0,
        "overlapping_event_count": 1,
        "overlapping_event_rate": 0.1,
        "mean_net_forward_return_2bps": 0.0015,
        "median_net_forward_return_2bps": 0.0012,
        "same_ticker_time_of_day_baseline_mean": 0.0002,
        "same_ticker_time_of_day_baseline_median": 0.0001,
        "event_minus_baseline_difference_mean": 0.0013,
        "event_minus_baseline_difference_median": 0.0011,
        "win_rate_1m": 0.60,
        "win_rate_2m": 0.65,
        "win_rate_5m": 0.70,
        "provider_provenance_summary": {
            "total_symbols": 30,
            "total_requests": 60,
            "total_pages": 120,
            "total_retries": 1,
            "total_errors": 0,
            "total_malformed_timestamps": 0,
            "pagination_complete": True,
        },
    }

    result = StudyResult(
        task_id="DAYTRADE-001B",
        split="validation",
        disposition="supported",
        disposition_step="step_5_support",
        disposition_reason="Passing all gates",
        metrics=metrics,
        gates={},
        bootstrap={},
        data_quality={},
        provenance={
            "provider": "alpaca",
            "feed": "sip",
            "timeframe": "1Min",
            "adjustment": "split",
            "calendar": "XNYS",
            "timezone": "America/New_York",
            "spec_sha256": locked_spec.sha256,
            "evaluator_code_sha": "eval_code_sha_1234",
            "manifest_sha256": "manifest_sha_5678",
            "evidence_confidence_cap": "limited_but_usable_evidence",
            "production_promotion_eligible": False,
        },
    )

    report = generate_markdown_report(result)
    assert "zero live provider calls" not in report.lower()
    assert "c2 real-data execution unauthorized" not in report.lower()
    assert "DAYTRADE-001C2" not in report
    assert "**Total Requests:** 60" in report
    assert "**Total HTTP Pages:** 120" in report
    assert "**Spec SHA-256:**" in report
    assert "**Evaluator Code SHA:**" in report
    assert "**Manifest SHA-256:**" in report
