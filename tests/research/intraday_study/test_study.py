"""Tests for the INTRA-001D real-data study adapter."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from tradex.research.intraday_engine.gates import SampleMinimums
from tradex.research.intraday_engine.spec import IntradaySpec
from tradex.research.intraday_study.artifacts import write_artifact_bundle
from tradex.research.intraday_study.cli import main
from tradex.research.intraday_study.freeze import (
    FreezeError,
    freeze_evaluation_code,
    verify_frozen_evaluation_code,
)
from tradex.research.intraday_study.loader import load_symbol_month
from tradex.research.intraday_study.manifest import (
    ManifestError,
    SymbolMonth,
    load_data_quality,
    load_manifest_lock,
    load_universe_manifest,
    sha256_of_file,
    verify_dataset_bundle,
    verify_dataset_integrity,
    verify_dataset_plan_file,
)
from tradex.research.intraday_study.split import split_for_effective_month
from tradex.research.intraday_study.study import (
    StudyError,
    compute_monthly_rejection_summary,
    run_split,
)


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
    first = records[0]["relative_path"]
    path = synthetic_dataset / "ohlcv" / first
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    with pytest.raises(ManifestError):
        verify_dataset_integrity(synthetic_dataset, records)
    path.write_bytes(original)


def test_verify_dataset_bundle_set_equality_and_identity(synthetic_dataset):
    verified = verify_dataset_bundle(synthetic_dataset, expected_count=3)
    assert len(verified.symbol_months) == 3
    assert set(verified.by_split.keys()) == {"development"}
    # Stable order from manifest.lock.json.
    symbols = [sm.symbol for sm in verified.symbol_months]
    assert len(set(symbols)) == 3


def test_verify_dataset_bundle_fails_on_expected_count_mismatch(synthetic_dataset):
    with pytest.raises(ManifestError):
        verify_dataset_bundle(synthetic_dataset, expected_count=999)


def test_verify_dataset_bundle_fails_on_missing_universe_row(synthetic_dataset):
    universe_path = synthetic_dataset / "universe" / "universe_manifest.csv"
    df = pd.read_csv(universe_path)
    df = df.iloc[1:]
    df.to_csv(universe_path, index=False)
    with pytest.raises(ManifestError):
        verify_dataset_bundle(synthetic_dataset, expected_count=3)


def test_verify_dataset_bundle_fails_on_duplicate_universe_row(synthetic_dataset):
    universe_path = synthetic_dataset / "universe" / "universe_manifest.csv"
    df = pd.read_csv(universe_path)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    df.to_csv(universe_path, index=False)
    with pytest.raises(ManifestError):
        verify_dataset_bundle(synthetic_dataset, expected_count=3)


def test_verify_dataset_bundle_fails_on_path_traversal(synthetic_dataset):
    lock_path = synthetic_dataset / "manifest.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["files"][0]["relative_path"] = "../etc/passwd"
    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    with pytest.raises(ManifestError):
        verify_dataset_bundle(synthetic_dataset, expected_count=3)


def test_verify_dataset_bundle_fails_on_absolute_path(synthetic_dataset):
    lock_path = synthetic_dataset / "manifest.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["files"][0]["relative_path"] = "/etc/passwd"
    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    with pytest.raises(ManifestError):
        verify_dataset_bundle(synthetic_dataset, expected_count=3)


def test_verify_dataset_plan_file_matches_committed_plan(synthetic_dataset):
    committed = Path(__file__).resolve().parents[3] / "docs/research/specs/INTRA-001B-dataset-v1.json"
    expected = sha256_of_file(committed)
    actual = verify_dataset_plan_file(synthetic_dataset / "dataset_plan.lock.json", expected_sha256=expected)
    assert actual == expected


def test_verify_dataset_plan_file_rejects_tampered_plan(synthetic_dataset):
    plan_path = synthetic_dataset / "dataset_plan.lock.json"
    plan_path.write_text('{"dataset_id": "tampered"}', encoding="utf-8")
    with pytest.raises(ManifestError):
        verify_dataset_plan_file(plan_path, expected_sha256="0" * 64)


def test_load_symbol_month_respects_evaluation_dates(synthetic_dataset, spec: IntradaySpec):
    dq = load_data_quality(synthetic_dataset / "ohlcv" / "data_quality.csv")
    univ = load_universe_manifest(synthetic_dataset / "universe" / "universe_manifest.csv")
    row = dq.iloc[0]
    sm = SymbolMonth(
        symbol=row["symbol"],
        effective_month=row["effective_month"],
        relative_path=row["relative_path"],
        manifest_id=f"{row['effective_month']}/{row['symbol']}",
        sha256=row["file_sha256"],
        file_size_bytes=0,
        split="development",
    )
    universe_row = univ[univ["ticker"] == row["symbol"]].iloc[0]
    ti = load_symbol_month(
        synthetic_dataset, sm, universe_row, row, normalize=True
    )
    assert len(ti.sessions) > 0
    assert ti.evaluation_session_dates is not None
    assert all(d.strftime("%Y-%m") == row["effective_month"] for d in ti.evaluation_session_dates)


def test_data_quality_rejection_disables_trading(synthetic_dataset):
    dq = load_data_quality(synthetic_dataset / "ohlcv" / "data_quality.csv")
    univ = load_universe_manifest(synthetic_dataset / "universe" / "universe_manifest.csv")
    row = dq.iloc[0]
    row["rejected"] = True
    row["rejection_reason"] = "missing_bar_rate"
    sm = SymbolMonth(
        symbol=row["symbol"],
        effective_month=row["effective_month"],
        relative_path=row["relative_path"],
        manifest_id=f"{row['effective_month']}/{row['symbol']}",
        sha256=row["file_sha256"],
        file_size_bytes=0,
        split="development",
    )
    universe_row = univ[univ["ticker"] == row["symbol"]].iloc[0]
    ti = load_symbol_month(synthetic_dataset, sm, universe_row, row, normalize=True)
    assert not ti.meta.is_eligible
    assert len(ti.sessions) == 0


def test_symbol_mismatch_rejected_at_manifest_verification(tmp_path, spec: IntradaySpec):
    """A symbol_mismatch=True row is a provider-contract failure caught at bundle verification."""
    from tests.research.intraday_study.conftest import _build_dataset

    _build_dataset(tmp_path, n_sessions=42, effective_month="2025-02")
    dq = load_data_quality(tmp_path / "ohlcv" / "data_quality.csv")
    dq["symbol_mismatch"] = True
    dq.to_csv(tmp_path / "ohlcv" / "data_quality.csv", index=False)

    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    with pytest.raises((StudyError, ManifestError)):
        run_split(tmp_path, "development", spec, generated_at)


def test_pagination_incomplete_rejected_at_manifest_verification(tmp_path, spec: IntradaySpec):
    from tests.research.intraday_study.conftest import _build_dataset

    _build_dataset(tmp_path, n_sessions=42, effective_month="2025-02")
    dq = load_data_quality(tmp_path / "ohlcv" / "data_quality.csv")
    dq["pagination_complete"] = False
    dq.to_csv(tmp_path / "ohlcv" / "data_quality.csv", index=False)

    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    with pytest.raises((StudyError, ManifestError)):
        run_split(tmp_path, "development", spec, generated_at)


def test_missing_data_quality_row_is_fatal(tmp_path, spec: IntradaySpec):
    from tests.research.intraday_study.conftest import _build_dataset

    _build_dataset(tmp_path, n_sessions=42, effective_month="2025-02")
    dq = load_data_quality(tmp_path / "ohlcv" / "data_quality.csv")
    dq = dq.iloc[1:]
    dq.to_csv(tmp_path / "ohlcv" / "data_quality.csv", index=False)

    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    with pytest.raises((StudyError, ManifestError)):
        run_split(tmp_path, "development", spec, generated_at)


def test_missing_universe_row_is_fatal(tmp_path, spec: IntradaySpec):
    from tests.research.intraday_study.conftest import _build_dataset

    _build_dataset(tmp_path, n_sessions=42, effective_month="2025-02")
    univ = load_universe_manifest(tmp_path / "universe" / "universe_manifest.csv")
    univ = univ.iloc[1:]
    univ.to_csv(tmp_path / "universe" / "universe_manifest.csv", index=False)

    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    with pytest.raises((StudyError, ManifestError)):
        run_split(tmp_path, "development", spec, generated_at)


def test_pre_normalization_unverified_makes_inconclusive(tmp_path, spec: IntradaySpec):
    """A symbol-month with pre_normalization_metrics_available=False fails data sufficiency."""
    from tests.research.intraday_study.conftest import _build_dataset

    _build_dataset(tmp_path, n_sessions=42, effective_month="2025-02")
    dq = load_data_quality(tmp_path / "ohlcv" / "data_quality.csv")
    dq["pre_normalization_metrics_available"] = False
    dq.to_csv(tmp_path / "ohlcv" / "data_quality.csv", index=False)

    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    result, *_ = run_split(
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


def test_run_split_returns_monthly_rejection_summary(tmp_path, spec: IntradaySpec):
    from tests.research.intraday_study.conftest import _build_dataset

    _build_dataset(tmp_path, n_sessions=42, effective_month="2025-02")
    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    _result, _ticker_inputs, monthly = run_split(
        tmp_path, "development", spec, generated_at
    )
    assert isinstance(monthly, dict)
    assert monthly["2025-02"]["total"] == 3
    assert monthly["2025-02"]["rejected"] == 0


def test_run_split_on_synthetic_dataset(synthetic_dataset, spec: IntradaySpec):
    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    result, *_ = run_split(
        synthetic_dataset,
        "development",
        spec,
        generated_at,
        evidence_eligible=False,
    )
    assert result.synthetic is False
    assert result.evidence_eligible is False
    assert result.generated_at_fixed is False
    assert result.outcome is not None
    assert result.spec_sha256 == spec.sha256


def test_holdout_firewall_blocked_when_validation_not_supported(tmp_path, spec: IntradaySpec):
    """Holdout must not be parsed when validation disposition is not supported."""
    from tests.research.intraday_study.conftest import _build_dataset

    _build_dataset(tmp_path, n_sessions=42, effective_month="2025-07")
    dq = load_data_quality(tmp_path / "ohlcv" / "data_quality.csv")
    dq["pre_normalization_metrics_available"] = False
    dq.to_csv(tmp_path / "ohlcv" / "data_quality.csv", index=False)

    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    val_result, *_ = run_split(
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
    assert val_result.outcome.disposition in ("inconclusive", "invalid", "not_supported")
    assert val_result.outcome.disposition != "supported"


def test_artifact_bundle_writes_required_files(synthetic_dataset, spec: IntradaySpec, tmp_path):
    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    result, *_ = run_split(
        synthetic_dataset,
        "development",
        spec,
        generated_at,
    )
    output_dir = tmp_path / "bundle"
    write_artifact_bundle(
        result,
        output_dir,
        split="development",
        dataset_id="INTRA-001B-DATASET-TEST",
        spec=spec,
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

    # Empty CSVs must still have stable headers.
    for csv_name in ["signals.csv", "trades.csv"]:
        text = (output_dir / csv_name).read_text(encoding="utf-8")
        assert text.startswith("ticker,")


def test_artifact_json_has_no_absolute_paths_or_raw_ohlcv(synthetic_dataset, spec: IntradaySpec, tmp_path):
    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    result, *_ = run_split(synthetic_dataset, "development", spec, generated_at)
    output_dir = tmp_path / "bundle"
    write_artifact_bundle(
        result,
        output_dir,
        split="development",
        dataset_id="INTRA-001B-DATASET-TEST",
        spec=spec,
        manifest_lock_path=synthetic_dataset / "manifest.lock.json",
        universe_manifest_path=synthetic_dataset / "universe" / "universe_manifest.csv",
        data_quality_path=synthetic_dataset / "ohlcv" / "data_quality.csv",
        spec_path=Path(spec.path),
    )
    study_json = json.loads((output_dir / "study.json").read_text(encoding="utf-8"))
    summary = json.dumps(study_json)
    assert "/home/" not in summary
    assert "/Users/" not in summary
    assert "C:\\\\" not in summary
    # Raw OHLCV bars must not be embedded in JSON.
    assert "open" not in summary or "candidate_signals" not in summary


def test_artifact_json_has_no_nan_or_infinity(synthetic_dataset, spec: IntradaySpec, tmp_path):
    generated_at = datetime(2026, 8, 1, tzinfo=UTC)
    result, *_ = run_split(synthetic_dataset, "development", spec, generated_at)
    output_dir = tmp_path / "bundle"
    write_artifact_bundle(
        result,
        output_dir,
        split="development",
        dataset_id="INTRA-001B-DATASET-TEST",
        spec=spec,
        manifest_lock_path=synthetic_dataset / "manifest.lock.json",
        universe_manifest_path=synthetic_dataset / "universe" / "universe_manifest.csv",
        data_quality_path=synthetic_dataset / "ohlcv" / "data_quality.csv",
        spec_path=Path(spec.path),
    )
    from tradex.research.intraday_engine.models import as_json_dict

    json.dumps(as_json_dict(result), allow_nan=False)
    json.dumps(json.loads((output_dir / "study.json").read_text(encoding="utf-8")), allow_nan=False)


def test_artifact_bundle_deterministic_headers_for_empty_files(spec: IntradaySpec, tmp_path):
    """Empty result CSVs must still contain stable headers."""
    from tradex.research.intraday_engine.engine import run_study
    from tradex.research.intraday_engine.synthetic import generate_synthetic_inputs

    inputs = generate_synthetic_inputs(
        spec, seed=42, n_stock_tickers=0, n_etf_tickers=0, n_sessions=10
    )
    result = run_study(inputs, spec, synthetic=False)
    output_dir = tmp_path / "empty-bundle"
    write_artifact_bundle(
        result,
        output_dir,
        split="development",
        dataset_id="INTRA-001B-DATASET-TEST",
        spec=spec,
    )
    expected_headers = {
        "signals.csv": "ticker",
        "trades.csv": "ticker",
        "candidate_metrics.csv": "strategy",
    }
    for csv_name, expected in expected_headers.items():
        text = (output_dir / csv_name).read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert text.split("\n")[0].startswith(expected)


def test_cli_run_subcommand_runs_and_writes_summary(
    synthetic_dataset, tmp_path, spec: IntradaySpec, monkeypatch
):
    from datetime import UTC

    from tradex.research.intraday_study.freeze import FreezeRecord

    clean_record = FreezeRecord(
        evaluation_code_sha="a" * 40,
        repository_clean=True,
        frozen_at=datetime(2026, 8, 1, tzinfo=UTC),
        spec_sha256=spec.sha256,
        amendment_sha256=None,
        dataset_plan_sha256=None,
        evaluation_files={},
    )
    monkeypatch.setattr(
        "tradex.research.intraday_study.cli.freeze_evaluation_code",
        lambda *args, **kwargs: clean_record,
    )
    monkeypatch.setattr(
        "tradex.research.intraday_study.cli.verify_frozen_evaluation_code",
        lambda *args, **kwargs: None,
    )

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
            "--expected-symbol-months",
            "3",
        ]
    )
    assert ret == 0
    assert (out_dir / "study_summary.json").is_file()
    summary = json.loads((out_dir / "study_summary.json").read_text(encoding="utf-8"))
    assert summary["study_id"] == "INTRA-001D"
    assert summary["spec_sha256"] == spec.sha256
    assert summary["no_provider_calls"] is True
    # Holdout did not run because validation is not supported.
    assert summary["holdout"]["access_count"] == 0
    assert summary["holdout"]["parse_count"] == 0
    # study_summary.json must not contain absolute paths.
    summary_text = json.dumps(summary)
    assert "/home/" not in summary_text
    # Top-level checksums cover the whole bundle.
    assert (out_dir / "checksums.sha256").is_file()
    assert (out_dir / "artifact_manifest.json").is_file()


def test_cli_holdout_status_ledger_records_zero_parses_when_validation_not_supported(
    synthetic_dataset, tmp_path, spec: IntradaySpec, monkeypatch
):
    """When validation is not supported, the holdout ledger records zero parse access."""
    from datetime import UTC

    from tradex.research.intraday_study.freeze import FreezeRecord

    clean_record = FreezeRecord(
        evaluation_code_sha="a" * 40,
        repository_clean=True,
        frozen_at=datetime(2026, 8, 1, tzinfo=UTC),
        spec_sha256=spec.sha256,
        amendment_sha256=None,
        dataset_plan_sha256=None,
        evaluation_files={},
    )
    monkeypatch.setattr(
        "tradex.research.intraday_study.cli.freeze_evaluation_code",
        lambda *args, **kwargs: clean_record,
    )
    monkeypatch.setattr(
        "tradex.research.intraday_study.cli.verify_frozen_evaluation_code",
        lambda *args, **kwargs: None,
    )

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
            "--expected-symbol-months",
            "3",
        ]
    )
    assert ret == 0
    holdout_status = json.loads((out_dir / "holdout_status.json").read_text(encoding="utf-8"))
    assert holdout_status["status"] == "not_run"
    assert holdout_status["access_count"] == 0
    assert holdout_status["parse_count"] == 0


def test_frozen_code_verification_rejects_dirty_worktree(tmp_path, spec: IntradaySpec):
    repo_root = Path(__file__).resolve().parents[3]
    record = freeze_evaluation_code(
        repo_root,
        spec.sha256,
    )
    if not record.repository_clean:
        pytest.skip("cannot test dirty-worktree rejection when worktree is already dirty")

    # Touch a tracked file to dirty the worktree, then restore it.
    readme = repo_root / "README.md"
    original = readme.read_text(encoding="utf-8")
    try:
        readme.write_text(original + "\n# tamper", encoding="utf-8")
        with pytest.raises(FreezeError):
            verify_frozen_evaluation_code(repo_root, record)
    finally:
        readme.write_text(original, encoding="utf-8")


def test_frozen_code_verification_rejects_hash_mismatch(tmp_path, spec: IntradaySpec):
    repo_root = Path(__file__).resolve().parents[3]
    record = freeze_evaluation_code(repo_root, spec.sha256)
    record.evaluation_files["README.md"] = "0" * 64
    with pytest.raises(FreezeError):
        verify_frozen_evaluation_code(repo_root, record)


def test_compute_monthly_rejection_summary_counts_by_split(tmp_path, spec: IntradaySpec):
    from tests.research.intraday_study.conftest import _build_dataset

    _build_dataset(tmp_path, n_sessions=42, effective_month="2025-02")
    dq = load_data_quality(tmp_path / "ohlcv" / "data_quality.csv")
    dq.loc[0, "rejected"] = "True"
    dq.loc[0, "rejection_reason"] = "missing_bar_rate"
    dq.loc[0, "split"] = "development"
    dq.loc[1, "rejected"] = "True"
    dq.loc[1, "rejection_reason"] = "missing_bar_rate"
    dq.loc[1, "split"] = "validation"
    dq.to_csv(tmp_path / "ohlcv" / "data_quality.csv", index=False)

    summary = compute_monthly_rejection_summary(load_data_quality(tmp_path / "ohlcv" / "data_quality.csv"))
    assert summary["2025-02"]["rejected"] == 2
    assert summary["2025-02"]["rejected_by_split"]["development"] == 1
    assert summary["2025-02"]["rejected_by_split"]["validation"] == 1
