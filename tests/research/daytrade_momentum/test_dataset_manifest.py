"""Tests for dataset storage security bounds, manifest contract, and dry-run adapter."""
from __future__ import annotations

from pathlib import Path

import pytest

from tradex.research.daytrade_momentum.dataset import (
    DatasetSecurityError,
    DaytradeDatasetManifest,
    acquire_partition_data,
    sanitize_manifest_dict,
    validate_dataset_root,
)
from tradex.research.daytrade_momentum.spec import DaytradeSpec


def test_validate_dataset_root_rejects_inside_repo(temp_output_dir: Path) -> None:
    """Verify that dataset roots located inside the repository/worktree are strictly rejected."""
    repo_root = temp_output_dir / "mock_repo"
    repo_root.mkdir()

    inside_dir = repo_root / "data" / "intraday"
    inside_dir.mkdir(parents=True)

    with pytest.raises(DatasetSecurityError, match="inside the tracked repository"):
        validate_dataset_root(inside_dir, repo_root=repo_root)


def test_validate_dataset_root_accepts_outside_repo(temp_output_dir: Path) -> None:
    """Verify that dataset roots outside the repository are accepted."""
    repo_root = temp_output_dir / "mock_repo"
    repo_root.mkdir()

    outside_dir = temp_output_dir / "external_data" / "intraday"
    outside_dir.mkdir(parents=True)

    validated = validate_dataset_root(outside_dir, repo_root=repo_root)
    assert validated == outside_dir.resolve()


def test_manifest_roundtrip_and_sha256() -> None:
    """Verify manifest serialization, deserialization, and deterministic SHA-256."""
    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002B",
        spec_sha256="dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127",
        partition="preholdout",
        provider="alpaca",
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        calendar="XNYS",
        timezone="America/New_York",
        universe=("SPY", "QQQ"),
        start_date="2026-01-02",
        end_date="2026-06-30",
        source_files={"SPY.csv": "abc123sha", "QQQ.csv": "def456sha"},
        acquisition_provenance={"run_mode": "dry_run"},
    )

    computed_sha = manifest.compute_sha256()
    assert len(computed_sha) == 64

    # Convert to dict and back
    d = manifest.to_dict()
    assert d["manifest_sha256"] == computed_sha

    restored = DaytradeDatasetManifest.from_dict(d)
    assert restored.task_id == manifest.task_id
    assert restored.universe == manifest.universe
    assert restored.source_files == manifest.source_files
    assert restored.compute_sha256() == computed_sha


def test_credential_sanitization() -> None:
    """Verify recursive sanitization strips credentials while preserving safe keys."""
    dirty = {
        "manifest_sha256": "abcdef123456",
        "api_key": "SECRET_KEY_VALUE",
        "nested": {
            "secret_key": "TOP_SECRET",
            "authorization": "Bearer xyz",
            "safe_value": 42,
            "raw_response": "should_be_stripped",
        },
        "items": [
            {"password": "pw", "spec_sha256": "allowed_spec_hash"},
        ],
    }

    clean = sanitize_manifest_dict(dirty)
    assert "api_key" not in clean
    assert "manifest_sha256" in clean  # safe allowlist
    assert "secret_key" not in clean["nested"]
    assert "authorization" not in clean["nested"]
    assert "raw_response" not in clean["nested"]
    assert clean["nested"]["safe_value"] == 42
    assert "password" not in clean["items"][0]
    assert clean["items"][0]["spec_sha256"] == "allowed_spec_hash"


def test_dry_run_adapter_zero_provider_calls(locked_spec: DaytradeSpec, temp_dataset_root: Path) -> None:
    """Verify dry-run mode executes without provider credentials or network calls."""
    manifest = acquire_partition_data(
        partition="preholdout",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
        execute_provider=False,
    )

    assert manifest.acquisition_provenance["execution_mode"] == "dry_run"
    assert manifest.acquisition_provenance["execute_provider"] is False
    assert manifest.acquisition_provenance["pages_retrieved"] == 0
    assert manifest.acquisition_provenance["rows_retrieved"] == 0
    assert manifest.compute_sha256() == manifest.manifest_sha256


def test_acquire_holdout_guard_without_validation(locked_spec: DaytradeSpec, temp_dataset_root: Path) -> None:
    """Verify holdout partition acquisition is blocked without validation bundle."""
    from tradex.research.daytrade_momentum.study import HoldoutAccessDeniedError

    with pytest.raises(HoldoutAccessDeniedError, match="Holdout acquisition strictly requires"):
        acquire_partition_data(
            partition="holdout",
            spec=locked_spec,
            dataset_root=temp_dataset_root,
            validation_artifact_dir=None,
            execute_provider=False,
        )
