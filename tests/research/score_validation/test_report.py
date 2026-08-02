"""Report and serialization tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tradex.research.score_validation.models import ScoreValidationConfig
from tradex.research.score_validation.report import run_study, write_study

from .conftest import write_bars_and_manifest


def test_all_required_output_files(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    study = run_study(manifest_path, ScoreValidationConfig(warmup_bars=50))
    out = tmp_path / "results"
    paths = write_study(study, out)
    required = {
        "study.json",
        "events.csv",
        "score_buckets.csv",
        "thresholds.csv",
        "components.csv",
        "score_distribution.csv",
        "component_frequency.csv",
        "ticker_summary.csv",
        "data_quality.csv",
        "report.md",
        "manifest.lock.json",
    }
    assert set(paths.keys()) == required
    for path in paths.values():
        assert path.is_file()


def test_empty_csv_retain_headers(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    study = run_study(manifest_path, ScoreValidationConfig(warmup_bars=50))
    # All CSV files should have at least the header row.
    for name in ["events.csv", "score_buckets.csv", "thresholds.csv"]:
        csv_path = tmp_path / name
        study.events.to_csv(csv_path, index=False)
        assert "score" in csv_path.read_text()


def test_study_json_no_nan_or_infinity(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    study = run_study(manifest_path, ScoreValidationConfig(warmup_bars=50))
    text = study.to_json()
    assert "NaN" not in text
    assert "Infinity" not in text
    data = json.loads(text)
    assert data["schema_version"] == 1
    assert "limitations" in data


def test_markdown_contains_required_sections(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    study = run_study(manifest_path, ScoreValidationConfig(warmup_bars=50))
    md = study.report_markdown
    for section in [
        "Study identity",
        "Dataset provenance",
        "Study configuration",
        "Score distribution",
        "Score-bucket results",
        "Threshold results",
        "Current threshold",
        "Component diagnostics",
        "Development results",
        "Validation results",
        "Holdout results",
        "Limitations",
        "Production-change status",
    ]:
        assert section in md
    assert "No production score, weight, or threshold is changed" in md


def test_output_directory_protection(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    study = run_study(manifest_path, ScoreValidationConfig(warmup_bars=50))
    out = tmp_path / "results"
    out.mkdir()
    (out / "existing.txt").write_text("do not overwrite")
    from tradex.research.score_validation.models import ValidationError

    with pytest.raises(ValidationError, match="overwrite"):
        write_study(study, out)


def test_input_files_unchanged(tmp_path: Path):
    manifest_path, _df, sha = write_bars_and_manifest(tmp_path / "data")
    study = run_study(manifest_path, ScoreValidationConfig(warmup_bars=50))
    out = tmp_path / "results"
    write_study(study, out)
    assert hashlib.sha256((tmp_path / "data" / "TEST.csv").read_bytes()).hexdigest() == sha
