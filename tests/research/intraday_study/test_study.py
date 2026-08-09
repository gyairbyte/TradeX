"""Tests for the INTRA-001D real-data study adapter."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from tradex.research.intraday_engine.gates import SampleMinimums
from tradex.research.intraday_engine.spec import IntradaySpec
from tradex.research.intraday_study.artifacts import (
    write_artifact_bundle,
)
from tradex.research.intraday_study.cli import main
from tradex.research.intraday_study.loader import load_symbol_month
from tradex.research.intraday_study.manifest import (
    ManifestError,
    load_data_quality,
    load_manifest_lock,
    load_universe_manifest,
    verify_dataset_integrity,
)
from tradex.research.intraday_study.split import split_for_effective_month
from tradex.research.intraday_study.study import run_split


def test_split_map():
    assert split_for_effective_month("2025-01") == "development"
    assert split_for_effective_month("2025-07") == "validation"
    assert split_for_effective_month("2025-12") == "holdout"


def test_manifest_verification(synthetic_dataset):
    records = load_manifest_lock(synthetic_dataset / "manifest.lock.json")
    assert len(records) == 3
    verified = verify_dataset_integrity(synthetic_dataset, records)
    assert len(verified) == 3


def test_manifest_verification_fails_on_tampered_file(synthetic_dataset):
    records = load_manifest_lock(synthetic_dataset / "manifest.lock.json")
    # Corrupt one file.
    first = records[0]["relative_path"]
    path = synthetic_dataset / "ohlcv" / first
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    with pytest.raises(ManifestError):
        verify_dataset_integrity(synthetic_dataset, records)
    path.write_bytes(original)


def test_load_symbol_month_respects_evaluation_dates(synthetic_dataset, spec: IntradaySpec):
    dq = load_data_quality(synthetic_dataset / "ohlcv" / "data_quality.csv")
    univ = load_universe_manifest(synthetic_dataset / "universe" / "universe_manifest.csv")
    row = dq.iloc[0]
    sm = type(
        "SM",
        (),
        {
            "symbol": row["symbol"],
            "effective_month": row["effective_month"],
            "relative_path": row["relative_path"],
            "manifest_id": f"{row['effective_month']}/{row['symbol']}",
            "sha256": row["file_sha256"],
        },
    )()
    universe_row = univ[univ["ticker"] == row["symbol"]].iloc[0]
    ti = load_symbol_month(
        synthetic_dataset, sm, universe_row, row, normalize=True
    )
    assert len(ti.sessions) > 0
    assert ti.evaluation_session_dates is not None
    assert all(d.strftime("%Y-%m") == row["effective_month"] for d in ti.evaluation_session_dates)


def test_run_split_on_synthetic_dataset(synthetic_dataset, spec: IntradaySpec):
    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    sample_minimums = SampleMinimums(
        executed_candidate_trades_min=1,
        represented_stock_symbols_min=1,
        represented_etfs_min=1,
        stock_stratum_trades_min=1,
        etf_stratum_trades_min=1,
        paired_symbol_overlap_min=1,
    )
    result, _ = run_split(
        synthetic_dataset,
        "development",
        spec,
        generated_at,
        sample_minimums=sample_minimums,
        evidence_eligible=False,
    )
    assert result.synthetic is False
    assert result.evidence_eligible is False
    assert result.generated_at_fixed is False
    assert result.outcome is not None
    assert result.spec_sha256 == spec.sha256


def test_pre_normalization_unverified_makes_inconclusive(tmp_path, spec: IntradaySpec):
    """A symbol-month with pre_normalization_metrics_available=False fails data sufficiency."""
    from tests.research.intraday_study.conftest import _build_dataset

    _build_dataset(tmp_path, n_sessions=42, effective_month="2025-02")
    dq = load_data_quality(tmp_path / "ohlcv" / "data_quality.csv")
    dq["pre_normalization_metrics_available"] = False
    dq.to_csv(tmp_path / "ohlcv" / "data_quality.csv", index=False)

    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    result, _ = run_split(
        tmp_path,
        "development",
        spec,
        generated_at,
        sample_minimums=SampleMinimums(
            executed_candidate_trades_min=1,
            represented_stock_symbols_min=1,
            represented_etfs_min=1,
            stock_stratum_trades_min=1,
            etf_stratum_trades_min=1,
            paired_symbol_overlap_min=1,
        ),
    )
    assert result.outcome.disposition == "inconclusive"
    assert "pre_normalization_metrics_unavailable" in result.outcome.reason


def test_holdout_firewall_blocked_when_validation_not_supported(tmp_path, spec: IntradaySpec):
    """Holdout must not run when validation disposition is not supported."""
    from tests.research.intraday_study.conftest import _build_dataset

    _build_dataset(tmp_path, n_sessions=42, effective_month="2025-02")
    dq = load_data_quality(tmp_path / "ohlcv" / "data_quality.csv")
    # Mark the only month as validation, removing development split.
    dq["split"] = "validation"
    dq["pre_normalization_metrics_available"] = False
    dq.to_csv(tmp_path / "ohlcv" / "data_quality.csv", index=False)

    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    val_result, _ = run_split(
        tmp_path,
        "validation",
        spec,
        generated_at,
        sample_minimums=SampleMinimums(
            executed_candidate_trades_min=1,
            represented_stock_symbols_min=1,
            represented_etfs_min=1,
            stock_stratum_trades_min=1,
            etf_stratum_trades_min=1,
            paired_symbol_overlap_min=1,
        ),
    )
    assert val_result.outcome.disposition == "inconclusive"
    assert val_result.outcome.disposition != "supported"


def test_artifact_bundle_writes_required_files(synthetic_dataset, spec: IntradaySpec, tmp_path):
    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    sample_minimums = SampleMinimums(
        executed_candidate_trades_min=1,
        represented_stock_symbols_min=1,
        represented_etfs_min=1,
        stock_stratum_trades_min=1,
        etf_stratum_trades_min=1,
        paired_symbol_overlap_min=1,
    )
    result, _ = run_split(
        synthetic_dataset,
        "development",
        spec,
        generated_at,
        sample_minimums=sample_minimums,
    )
    output_dir = tmp_path / "bundle"
    write_artifact_bundle(
        result,
        output_dir,
        split="development",
        dataset_id="INTRA-001B-DATASET-TEST",
        manifest_lock_path=synthetic_dataset / "manifest.lock.json",
        universe_manifest_path=synthetic_dataset / "universe" / "universe_manifest.csv",
        data_quality_path=synthetic_dataset / "ohlcv" / "data_quality.csv",
        spec_path=Path(spec.path),
    )
    required = {
        "study.json",
        "spec.lock.json",
        "manifest.lock.json",
        "universe_manifest.csv",
        "data_quality.csv",
        "session_features.csv",
        "signals.csv",
        "trades.csv",
        "candidate_metrics.csv",
        "baseline_metrics.csv",
        "ticker_comparison.csv",
        "monthly_comparison.csv",
        "cost_sensitivity.csv",
        "report.md",
        "artifact_manifest.json",
        "checksums.sha256",
    }
    present = {p.name for p in output_dir.iterdir() if p.is_file()}
    assert required.issubset(present)

    # Verify checksums cover the artifact manifest as well.
    checksum_text = (output_dir / "checksums.sha256").read_text(encoding="utf-8")
    names = [line.split()[1] for line in checksum_text.strip().split("\n") if line]
    assert "artifact_manifest.json" in names


def test_cli_run_subcommand_runs_and_writes_summary(synthetic_dataset, tmp_path, spec: IntradaySpec):
    out_dir = tmp_path / "cli-out"
    ret = main(
        [
            "run",
            "--dataset-root",
            str(synthetic_dataset),
            "--output",
            str(out_dir),
            "--generated-at",
            "2026-08-01T00:00:00+00:00",
            "--manifest-lock",
            str(synthetic_dataset / "manifest.lock.json"),
            "--spec",
            str(spec.path),
        ]
    )
    assert ret == 0
    assert (out_dir / "study_summary.json").is_file()
    summary = pd.read_json(out_dir / "study_summary.json", typ="series")
    assert summary["study_id"] == "INTRA-001D"
    assert summary["spec_sha256"] == spec.sha256
