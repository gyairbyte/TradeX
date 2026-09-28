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
    verify_dataset_manifest,
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
    assert manifest.acquisition_provenance["logical_calls"] == 0
    assert manifest.acquisition_provenance["http_pages"] == 0
    assert manifest.acquisition_provenance["http_attempts"] == 0
    assert manifest.acquisition_provenance["retries"] == 0
    assert manifest.acquisition_provenance["http_429s"] == 0
    assert manifest.acquisition_provenance["http_errors"] == 0
    assert manifest.compute_sha256() == manifest.manifest_sha256

    # Verify canonical file layout: dry-run writes manifest.dry-run.json and NOT manifest.lock.json
    dry_run_file = temp_dataset_root / "preholdout" / "manifest.dry-run.json"
    formal_file = temp_dataset_root / "preholdout" / "manifest.lock.json"
    assert dry_run_file.is_file()
    assert not formal_file.is_file()
    assert manifest.source_files == {}


def test_dry_run_preserves_existing_manifest_lock(locked_spec: DaytradeSpec, temp_dataset_root: Path) -> None:
    """Verify dry-run does NOT overwrite an existing formal manifest.lock.json."""
    pre_dir = temp_dataset_root / "preholdout"
    pre_dir.mkdir(parents=True, exist_ok=True)
    formal_lock = pre_dir / "manifest.lock.json"
    formal_lock.write_text("{\"original\": true}", encoding="utf-8")

    acquire_partition_data(
        partition="preholdout",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
        execute_provider=False,
    )

    assert formal_lock.is_file()
    assert formal_lock.read_text(encoding="utf-8") == "{\"original\": true}"
    dry_run_file = pre_dir / "manifest.dry-run.json"
    assert dry_run_file.is_file()


def test_verify_dataset_manifest_rejects_dry_run(locked_spec: DaytradeSpec, temp_dataset_root: Path) -> None:
    """Verify verify_dataset_manifest fails closed on a dry-run manifest."""
    manifest = acquire_partition_data(
        partition="preholdout",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
        execute_provider=False,
    )
    with pytest.raises(DatasetSecurityError, match="dry-run cannot be verified"):
        verify_dataset_manifest(manifest, spec=locked_spec, partition_dir=temp_dataset_root / "preholdout")


def test_zero_os_environ_read_on_non_provider_paths(
    locked_spec: DaytradeSpec, temp_dataset_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify neither ALPACA_API_KEY nor ALPACA_SECRET_KEY is accessed on dry-run or manifest sanitization."""
    import os

    accessed_keys: list[str] = []
    original_getitem = os.environ.__getitem__
    original_get = os.environ.get

    def forbidden_get(key: str, default: object = None) -> object:
        if "ALPACA" in key.upper():
            accessed_keys.append(key)
            raise AssertionError(f"FORBIDDEN ENV ACCESS: Attempted to read '{key}' on non-provider code path!")
        return original_get(key, default)

    def forbidden_getitem(key: str) -> str:
        if "ALPACA" in key.upper():
            accessed_keys.append(key)
            raise AssertionError(f"FORBIDDEN ENV ACCESS: Attempted to read '{key}' on non-provider code path!")
        return original_getitem(key)

    monkeypatch.setattr(os.environ, "get", forbidden_get)
    monkeypatch.setattr(os.environ, "__getitem__", forbidden_getitem)

    # 1. Dry run acquisition
    manifest = acquire_partition_data(
        partition="preholdout",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
        execute_provider=False,
    )

    # 2. Manifest sanitization
    sanitized = sanitize_manifest_data(manifest.to_dict())
    assert "alpaca_api_key" not in str(sanitized).lower()

    # 3. Serialization and hashing
    _ = manifest.to_dict()
    _ = manifest.compute_sha256()

    # Verify no credential env keys were accessed
    assert len(accessed_keys) == 0


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
    """Verify acquisition adapter calls client.get_bars with SIP/1Min/split and returns (df, safe_metadata)."""
    from datetime import UTC, datetime

    mock_client = MagicMock()
    mock_client.max_retries = 1
    empty_df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    mock_client.get_bars.return_value = ({"SPY": empty_df}, {"pagination_complete": True})

    adapter = DaytradeDatasetAcquisitionAdapter(client=mock_client)

    start_utc = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    end_utc = datetime(2026, 1, 31, 23, 59, tzinfo=UTC)
    res_df, safe_meta = adapter.fetch_symbol_month_bars("SPY", start_utc, end_utc)

    assert isinstance(res_df, pd.DataFrame)
    assert safe_meta["symbol"] == "SPY"
    assert safe_meta["logical_calls"] == 1
    assert safe_meta["http_pages"] == 0
    assert safe_meta["http_attempts"] == 0
    assert safe_meta["retries"] == 0
    assert safe_meta["http_429s"] == 0
    assert safe_meta["http_errors"] == 0
    assert safe_meta["malformed_timestamp_count"] == 0
    assert safe_meta["pagination_complete"] is True
    assert safe_meta["safe_error_classification"] == "none"

    mock_client.get_bars.assert_called_once_with(
        symbols=["SPY"],
        start_utc=start_utc,
        end_utc=end_utc,
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        max_pages=100,
    )


def test_acquisition_adapter_aggregates_provenance_across_months() -> None:
    """Verify adapter safe metadata aggregates correctly across multiple chunks."""
    from datetime import UTC, datetime

    mock_client = MagicMock()
    mock_client.max_retries = 1
    chunk_df = pd.DataFrame([
        {"timestamp": "2026-01-02T14:30:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0}
    ])
    mock_client.get_bars.side_effect = [
        ({"SPY": chunk_df}, {"pagination_complete": True, "pages_retrieved": 2, "attempts": 2, "retries": 1, "rate_limits_hit": 1, "network_errors": 0}),
        ({"SPY": chunk_df}, {"pagination_complete": True, "pages_retrieved": 3, "attempts": 3, "retries": 0, "rate_limits_hit": 0, "network_errors": 1}),
    ]

    adapter = DaytradeDatasetAcquisitionAdapter(client=mock_client)

    dt1_start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    dt1_end = datetime(2026, 1, 31, 23, 59, tzinfo=UTC)
    dt2_start = datetime(2026, 2, 1, 0, 0, tzinfo=UTC)
    dt2_end = datetime(2026, 2, 28, 23, 59, tzinfo=UTC)

    _, meta1 = adapter.fetch_symbol_month_bars("SPY", dt1_start, dt1_end)
    _, meta2 = adapter.fetch_symbol_month_bars("SPY", dt2_start, dt2_end)

    total_pages = meta1["http_pages"] + meta2["http_pages"]
    total_retries = meta1["retries"] + meta2["retries"]
    total_429s = meta1["http_429s"] + meta2["http_429s"]
    total_errors = meta1["http_errors"] + meta2["http_errors"]

    assert total_pages == 5
    assert total_retries == 1
    assert total_429s == 1
    assert total_errors == 1


def test_acquisition_adapter_rejects_unexpected_response_symbol() -> None:
    """Verify acquisition adapter raises DatasetSecurityError if response symbol doesn't match requested."""
    from datetime import UTC, datetime

    mock_client = MagicMock()
    mock_client.max_retries = 1
    mock_client.get_bars.return_value = ({"QQQ": pd.DataFrame()}, {"pagination_complete": True})

    adapter = DaytradeDatasetAcquisitionAdapter(client=mock_client)

    start_utc = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    end_utc = datetime(2026, 1, 31, 23, 59, tzinfo=UTC)
    with pytest.raises(DatasetSecurityError, match="missing from client response"):
        adapter.fetch_symbol_month_bars("SPY", start_utc, end_utc)


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
