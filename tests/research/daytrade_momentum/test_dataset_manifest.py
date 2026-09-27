"""Tests for dataset storage security bounds, manifest contract, and dry-run adapter."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.research.daytrade_momentum.dataset import (
    DatasetPaginationLimitError,
    DatasetSecurityError,
    DaytradeDatasetAcquisitionAdapter,
    DaytradeDatasetManifest,
    acquire_partition_data,
    read_normalized_bars_csv,
    sanitize_manifest_data,
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


def test_manifest_roundtrip_and_sha256(locked_spec: DaytradeSpec) -> None:
    """Verify manifest serialization, deserialization, and deterministic SHA-256."""
    source_files = {f"bars/{ticker}.csv": "a" * 64 for ticker in locked_spec.universe}
    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002B",
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


def test_credential_sanitization_fails_closed() -> None:
    """Verify recursive sanitization strictly raises DatasetSecurityError on forbidden keys/tokens."""
    # Forbidden key patterns
    for bad_key in ["api_key", "secret_key", "authorization", "password", "raw_response"]:
        with pytest.raises(DatasetSecurityError, match="Prohibited key pattern"):
            sanitize_manifest_data({bad_key: "value"})

    # Prohibited bearer token value
    with pytest.raises(DatasetSecurityError, match="Prohibited authorization token value"):
        sanitize_manifest_data({"headers": "Bearer secret_token_xyz"})

    # Safe keys are allowed
    safe = {
        "manifest_sha256": "abcdef123456",
        "spec_sha256": "abcdef123456",
        "preholdout_manifest_sha256": "abcdef123456",
        "token_sequence_sha256": "abcdef123456",
        "token_hashes": ["hash1", "hash2"],
        "safe_int": 42,
    }
    assert sanitize_manifest_data(safe) == safe


def test_manifest_from_dict_tamper_detection(locked_spec: DaytradeSpec) -> None:
    """Verify tampering with internal manifest_sha256 raises DatasetSecurityError."""
    source_files = {f"bars/{ticker}.csv": "a" * 64 for ticker in locked_spec.universe}
    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002B",
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
    )
    d = manifest.to_dict()
    d["manifest_sha256"] = "0" * 64  # Tampered hash

    with pytest.raises(DatasetSecurityError, match="Manifest SHA-256 mismatch"):
        DaytradeDatasetManifest.from_dict(d)


def test_manifest_validation_rejects_wrong_dates(locked_spec: DaytradeSpec) -> None:
    """Verify validate_against_spec enforces context_anchor_date start for preholdout."""
    source_files = {f"bars/{ticker}.csv": "a" * 64 for ticker in locked_spec.universe}

    # Wrong preholdout start (e.g. 2026-01-02 instead of context anchor 2025-12-31)
    bad_manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        provider="alpaca",
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        calendar="XNYS",
        timezone="America/New_York",
        universe=locked_spec.universe,
        start_date="2026-01-02",
        end_date=locked_spec.validation.end,
        source_files=source_files,
    )
    with pytest.raises(DatasetSecurityError, match="Preholdout partition dates .* must match"):
        bad_manifest.validate_against_spec(locked_spec)


def test_manifest_validation_rejects_path_traversal_and_malformed_paths(locked_spec: DaytradeSpec) -> None:
    """Verify validate_against_spec rejects non-canonical paths and directory traversal."""
    # Path traversal
    bad_files = {f"bars/{ticker}.csv": "a" * 64 for ticker in locked_spec.universe}
    bad_files["../secret.csv"] = "a" * 64
    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002B",
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
        source_files=bad_files,
    )
    with pytest.raises(DatasetSecurityError, match="Path traversal detected"):
        manifest.validate_against_spec(locked_spec)


def test_read_normalized_bars_csv_unparseable_timestamp_discard(temp_output_dir: Path) -> None:
    """Verify unparseable timestamps are discarded without fabricating session attribution."""
    csv_file = temp_output_dir / "test_bars.csv"
    content = (
        "bar_start,open,high,low,close,volume\n"
        "2026-01-02T14:30:00Z,100.0,100.5,99.5,100.2,1000\n"
        "MALFORMED_TIMESTAMP_ROW,100.0,100.5,99.5,100.2,1000\n"
        "2026-01-02T14:31:00Z,100.2,100.6,100.1,100.5,1200\n"
    )
    csv_file.write_text(content, encoding="utf-8")

    df, malformed_count = read_normalized_bars_csv(csv_file)
    assert malformed_count == 1
    assert len(df) == 2
    assert "MALFORMED_TIMESTAMP_ROW" not in df["bar_start"].values


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

    # Verify canonical file layout
    expected_manifest = temp_dataset_root / "preholdout" / "manifest.lock.json"
    assert expected_manifest.is_file()
    assert manifest.source_files == {}


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


def test_acquisition_adapter_mock_client_pagination_and_chunks() -> None:
    """Verify acquisition adapter calls client.get_bars with SIP/1Min/split and enforces 100-page limit."""
    from datetime import UTC, datetime

    mock_client = MagicMock()
    mock_client.max_retries = 1
    empty_df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    mock_client.get_bars.return_value = ({"SPY": empty_df}, {"pagination_complete": True})

    adapter = DaytradeDatasetAcquisitionAdapter(client=mock_client)

    start_utc = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    end_utc = datetime(2026, 1, 31, 23, 59, tzinfo=UTC)
    res_df = adapter.fetch_symbol_month_bars("SPY", start_utc, end_utc)

    assert isinstance(res_df, pd.DataFrame)
    mock_client.get_bars.assert_called_once_with(
        symbols=["SPY"],
        start_utc=start_utc,
        end_utc=end_utc,
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        max_pages=100,
    )


def test_acquisition_adapter_page_limit_exceeded() -> None:
    """Verify acquisition adapter raises DatasetPaginationLimitError when pagination exceeds 100 pages."""
    from datetime import UTC, datetime

    mock_client = MagicMock()
    mock_client.max_retries = 1
    mock_client.get_bars.return_value = (
        {"SPY": pd.DataFrame()},
        {"pagination_complete": False, "safe_error_classification": "max_pages_exceeded"},
    )

    adapter = DaytradeDatasetAcquisitionAdapter(client=mock_client)

    start_utc = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    end_utc = datetime(2026, 1, 31, 23, 59, tzinfo=UTC)
    with pytest.raises(DatasetPaginationLimitError, match="Pagination hard limit of 100 pages exceeded"):
        adapter.fetch_symbol_month_bars("SPY", start_utc, end_utc)


def test_acquisition_adapter_rejects_retry_limit_greater_than_one() -> None:
    """Verify acquisition adapter rejects client with max_retries > 1."""
    mock_client = MagicMock()
    mock_client.max_retries = 2
    with pytest.raises(DatasetSecurityError, match="exceeds locked limit of 1"):
        DaytradeDatasetAcquisitionAdapter(client=mock_client)
