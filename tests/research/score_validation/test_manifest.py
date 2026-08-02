"""Manifest loading and validation tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradex.research.score_validation.manifest import load_manifest
from tradex.research.score_validation.models import ValidationError

from .conftest import write_bars_and_manifest


def test_valid_manifest_round_trip(tmp_path: Path):
    manifest_path, _df, sha = write_bars_and_manifest(tmp_path)
    manifest = load_manifest(manifest_path)
    assert manifest.schema_version == 1
    assert manifest.dataset_name == "test"
    assert len(manifest.entries) == 1
    assert manifest.entries[0].ticker == "TEST"
    assert manifest.entries[0].sha256 == sha


def test_unsupported_schema_version(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["schema_version"] = 99
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="Unsupported manifest schema"):
        load_manifest(manifest_path)


def test_missing_entries(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["entries"] = []
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="nonempty"):
        load_manifest(manifest_path)


def test_duplicate_ticker(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    entry = data["entries"][0].copy()
    data["entries"].append(entry)
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="Duplicate ticker"):
        load_manifest(manifest_path)


def test_invalid_ticker(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["entries"][0]["ticker"] = ""
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="invalid ticker"):
        load_manifest(manifest_path)


def test_absolute_path_rejected(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["entries"][0]["path"] = "/etc/passwd"
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="relative"):
        load_manifest(manifest_path)


def test_parent_traversal_rejected(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["entries"][0]["path"] = "../TEST.csv"
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="\\.\\."):
        load_manifest(manifest_path)


def test_path_escaping_manifest_directory(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["entries"][0]["path"] = "subdir/../../TEST.csv"
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="\\.\\."):
        load_manifest(manifest_path)


def test_missing_file(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["entries"][0]["path"] = "MISSING.csv"
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="CSV not found"):
        load_manifest(manifest_path)


def test_checksum_mismatch(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["entries"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="SHA-256 mismatch"):
        load_manifest(manifest_path)


def test_row_count_mismatch(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["entries"][0]["rows"] = 999
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="row count mismatch"):
        load_manifest(manifest_path)


def test_start_mismatch(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["entries"][0]["start"] = "2010-01-01T00:00:00+00:00"
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="start mismatch"):
        load_manifest(manifest_path)


def test_end_mismatch(tmp_path: Path):
    manifest_path, _df, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    # Set manifest end to a later date after the actual data end.
    data["entries"][0]["end"] = "2025-01-01T00:00:00+00:00"
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="end mismatch"):
        load_manifest(manifest_path)


def test_overlapping_splits_rejected(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["splits"]["validation"]["start"] = "2021-12-01"
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="before previous split end"):
        load_manifest(manifest_path)


def test_out_of_order_splits_rejected(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    # Holdout dates fall between development and validation chronologically.
    data["splits"] = {
        "development": {"start": "2018-01-01", "end": "2022-12-31"},
        "holdout": {"start": "2023-01-01", "end": "2023-12-31"},
        "validation": {"start": "2025-01-01", "end": "2025-12-31"},
    }
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="before previous split end"):
        load_manifest(manifest_path)


def test_invalid_split_date(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    data = json.loads(manifest_path.read_text())
    data["splits"]["development"]["start"] = "not-a-date"
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="valid ISO date"):
        load_manifest(manifest_path)


def test_deterministic_entry_order(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path)
    manifest = load_manifest(manifest_path)
    assert [e.ticker for e in manifest.entries] == ["TEST"]
