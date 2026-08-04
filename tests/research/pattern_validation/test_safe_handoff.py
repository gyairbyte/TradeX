"""Lightweight integrity checks for the committed PATTERN-001 safe-handoff bundle.

This test does not rerun the research engine; it verifies that the preserved
aggregate artifacts are intact, consistent with the locked spec, and do not
contain excluded raw/per-observation files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tradex.research.pattern_validation.models import load_manifest, load_spec

_SAFE_HANDOFF_DIR = (
    Path(__file__).parents[3]
    / "docs"
    / "research"
    / "artifacts"
    / "PATTERN-001"
    / "2026-08-03-9ea40e85"
)

_EXPECTED = {
    "zip_sha256": "b0171d7e221c4e21e808eca0ffa27dba30d7ef7a835598133c3ef63cd1e5e424",
    "spec_sha256": "68a3d59cf4b06f21889207dde67e217d2a61916ec7c331adb9fe629c521bf8c7",
    "manifest_sha256": "9ea40e85d3c2388ec33f582988a79e66b8f0e5d18a04800c714db358db3080ef",
    "universe_sha256": "554c6933750be1f10716ce45912e70ff6c963cc190157f730ef1d7ddbd850404",
    "provider": "schwab",
    "start_date": "2018-01-02",
    "end_date": "2026-07-31",
    "overall_classification": "rejected",
    "runup_classification": "rejected",
    "decline_classification": "rejected",
}

_ALLOWED_FILES = {
    "README.txt",
    "artifact_manifest.json",
    "baseline_comparison.csv",
    "data_quality.csv",
    "development_fingerprints.json",
    "manifest.lock.json",
    "period_summary.csv",
    "promotion_decision.json",
    "report.md",
    "study_spec.lock.json",
    "ticker_summary.csv",
}

_EXCLUDED_FILES = {
    "observations.csv",
    "qualifying_signals.csv",
    "frequency_matched_controls.csv",
    "event_study.csv",
    "executable_trades.csv",
    "study.json",
}


@pytest.fixture
def handoff_dir() -> Path:
    assert _SAFE_HANDOFF_DIR.is_dir(), f"safe-handoff dir not found: {_SAFE_HANDOFF_DIR}"
    return _SAFE_HANDOFF_DIR


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def test_safe_handoff_bundle_includes_only_allowed_files(handoff_dir: Path) -> None:
    found = {p.name for p in handoff_dir.iterdir() if p.is_file()}
    assert found == _ALLOWED_FILES, f"unexpected files in safe-handoff dir: {found ^ _ALLOWED_FILES}"
    for excluded in _EXCLUDED_FILES:
        assert not (handoff_dir / excluded).exists(), f"excluded file must not be committed: {excluded}"


def test_safe_handoff_artifact_hashes_match_manifest(handoff_dir: Path) -> None:
    manifest_path = handoff_dir / "artifact_manifest.json"
    artifact_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, expected_hash in artifact_manifest["files"].items():
        file_path = handoff_dir / name
        if not file_path.exists():
            # The artifact manifest may reference intentionally excluded row-level files.
            assert name in _EXCLUDED_FILES, f"missing file {name} is not in excluded list"
            continue
        assert _file_hash(file_path) == expected_hash, f"hash mismatch for {name}"


def test_safe_handoff_spec_matches_expected(handoff_dir: Path) -> None:
    spec_path = handoff_dir / "study_spec.lock.json"
    spec = load_spec(spec_path)
    assert spec.sha256 == _EXPECTED["spec_sha256"]
    assert spec.universe_hash == _EXPECTED["universe_sha256"]
    assert spec.provider == _EXPECTED["provider"]
    assert spec.start_date.isoformat() == _EXPECTED["start_date"]
    assert spec.end_date.isoformat() == _EXPECTED["end_date"]
    assert spec.research_test_mode is False
    assert spec.production_promotion_eligible is False


def test_safe_handoff_manifest_matches_expected(handoff_dir: Path) -> None:
    spec_path = handoff_dir / "study_spec.lock.json"
    spec = load_spec(spec_path)
    manifest_path = handoff_dir / "manifest.lock.json"
    manifest = load_manifest(manifest_path)
    assert manifest.verify_integrity()
    assert manifest.manifest_sha256 == _EXPECTED["manifest_sha256"]
    assert manifest.provider == _EXPECTED["provider"]
    assert manifest.request_start.isoformat() == _EXPECTED["start_date"]
    assert manifest.request_end.isoformat() == _EXPECTED["end_date"]
    assert manifest.adjustment_policy == "provider_default"
    assert tuple(manifest.requested_tickers) == tuple(spec.tickers)


def test_safe_handoff_promotion_decision(handoff_dir: Path) -> None:
    decision_path = handoff_dir / "promotion_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["classification"] == _EXPECTED["overall_classification"]
    assert decision["production_promotion_eligible"] is False
    gate_results = decision["gate_results"]
    assert gate_results["overall_classification"] == _EXPECTED["overall_classification"]
    assert gate_results["runup_classification"] == _EXPECTED["runup_classification"]
    assert gate_results["decline_classification"] == _EXPECTED["decline_classification"]
    assert gate_results["no_leakage_or_integrity_failures"] is True
