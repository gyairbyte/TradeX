"""Tests for artifact bundle writing, markdown report generation, and checksums verification."""
from __future__ import annotations

import json
from pathlib import Path

from tradex.research.daytrade_momentum.artifacts import (
    generate_markdown_report,
    sha256_of_file,
    write_artifact_bundle,
)
from tradex.research.daytrade_momentum.freeze import freeze_evaluation_state
from tradex.research.daytrade_momentum.models import (
    DataQualityReport,
    DaytradeSession,
)
from tradex.research.daytrade_momentum.spec import DaytradeSpec
from tradex.research.daytrade_momentum.study import evaluate_split


def test_write_artifact_bundle_and_checksums(
    locked_spec: DaytradeSpec, temp_output_dir: Path, temp_dataset_root: Path
) -> None:
    """Verify write_artifact_bundle generates all artifacts and accurate checksums."""
    sessions_by_ticker: dict[str, list[DaytradeSession]] = {sym: [] for sym in locked_spec.universe}
    reports: list[DataQualityReport] = []

    res = evaluate_split(
        split_name="development",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        require_clean=False,
    )

    bundle_dir = temp_output_dir / "bundle"
    _checksums = write_artifact_bundle(
        output_dir=bundle_dir,
        result=res,
        spec=locked_spec,
        freeze=freeze,
    )

    expected_files = [
        "study.json",
        "spec.lock.json",
        "freeze.json",
        "bootstrap.json",
        "metrics.json",
        "data_quality.csv",
        "events.csv",
        "baseline_summary.csv",
        "per_etf.csv",
        "monthly.csv",
        "direction.csv",
        "report.md",
        "checksums.sha256",
    ]

    for fn in expected_files:
        fp = bundle_dir / fn
        assert fp.is_file(), f"Artifact {fn} was not created"

    # Verify every file against checksums.sha256
    checksums_file = bundle_dir / "checksums.sha256"
    lines = checksums_file.read_text(encoding="utf-8").splitlines()
    recorded_checksums: dict[str, str] = {}
    for line in lines:
        if line.strip():
            digest, fname = line.strip().split(maxsplit=1)
            recorded_checksums[fname] = digest

    for fn in expected_files:
        if fn == "checksums.sha256":
            continue
        fp = bundle_dir / fn
        actual_digest = sha256_of_file(fp)
        assert recorded_checksums[fn] == actual_digest


def test_json_artifacts_no_nan_or_infinity(
    locked_spec: DaytradeSpec, temp_output_dir: Path, temp_dataset_root: Path
) -> None:
    """Verify all JSON artifacts serialize strictly valid JSON without NaN or Infinity."""
    sessions_by_ticker: dict[str, list[DaytradeSession]] = {sym: [] for sym in locked_spec.universe}
    reports: list[DataQualityReport] = []

    res = evaluate_split(
        split_name="development",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    bundle_dir = temp_output_dir / "json_bundle"
    write_artifact_bundle(
        output_dir=bundle_dir,
        result=res,
        spec=locked_spec,
    )

    for p in bundle_dir.glob("*.json"):
        text = p.read_text(encoding="utf-8")
        assert "NaN" not in text
        assert "Infinity" not in text
        # Verify strict standard json parsing
        loaded = json.loads(text)
        assert isinstance(loaded, dict)


def test_markdown_report_structure(
    locked_spec: DaytradeSpec, temp_dataset_root: Path
) -> None:
    """Verify markdown report content and structure."""
    sessions_by_ticker: dict[str, list[DaytradeSession]] = {sym: [] for sym in locked_spec.universe}
    reports: list[DataQualityReport] = []

    res = evaluate_split(
        split_name="development",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
        custom_sessions=sessions_by_ticker,
        custom_reports=reports,
    )

    report_text = generate_markdown_report(res)
    assert "# DAYTRADE-002B Early-to-Late Momentum Study Report" in report_text
    assert "DEVELOPMENT" in report_text
    assert "Validation Gates" in report_text
    assert "Core Metrics" in report_text
    assert "Provenance" in report_text
