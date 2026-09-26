"""Dataset manifest contract, security sanitization, and safety bounds tests."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradex.research.daytrade_reversal.dataset import (
    DatasetPaginationLimitError,
    DatasetSecurityError,
    DaytradeDatasetAcquisitionAdapter,
    DaytradeDatasetManifest,
    get_repo_root,
    sanitize_manifest_data,
    validate_dataset_root,
)
from tradex.research.daytrade_reversal.spec import DaytradeSpec


def test_dataset_root_inside_repo_is_rejected(tmp_path: Path) -> None:
    """Refuse to write raw/normalized OHLCV if destination is inside git repo/worktree."""
    repo_root = get_repo_root()
    in_repo_path = repo_root / "data" / "raw_ohlcv"

    with pytest.raises(DatasetSecurityError, match="inside the tracked repository"):
        validate_dataset_root(in_repo_path, repo_root=repo_root)


def test_dataset_root_outside_repo_is_accepted(tmp_path: Path) -> None:
    """An external directory (e.g. tmp_path outside repo) is accepted."""
    repo_root = get_repo_root()
    validated = validate_dataset_root(tmp_path, repo_root=repo_root)
    assert validated == tmp_path.resolve()


def test_manifest_prohibits_secrets_and_api_keys() -> None:
    """Manifest serialization fails closed if representative API keys or secrets are present."""
    leaked_data = {
        "study_id": "DAYTRADE-001B",
        "APCA-API-KEY-ID": "LEAKED_KEY_12345",
    }
    with pytest.raises(DatasetSecurityError, match="Prohibited key pattern"):
        sanitize_manifest_data(leaked_data)


def test_manifest_prohibits_nested_secrets_and_raw_bodies() -> None:
    """Recursive sanitization catches nested keys and bearer tokens."""
    nested_secret = {
        "metadata": {
            "auth": {
                "secret_key": "super_secret_value",
            }
        }
    }
    with pytest.raises(DatasetSecurityError, match="Prohibited key pattern"):
        sanitize_manifest_data(nested_secret)

    nested_body = {
        "debug": [
            {"response_body": "<html>raw</html>"}
        ]
    }
    with pytest.raises(DatasetSecurityError, match="Prohibited key pattern"):
        sanitize_manifest_data(nested_body)

    bearer_val = {"auth_header": "Bearer secret_jwt_token"}
    with pytest.raises(DatasetSecurityError, match="Prohibited authorization token value"):
        sanitize_manifest_data(bearer_val)


def test_manifest_serialization_and_hash_roundtrip() -> None:
    """Valid dataset manifest computes deterministic SHA-256 and round-trips cleanly."""
    manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256="0651e075ff0641510788582a67827e065347f851e9363964f85a193a3d166620",
        universe=["AAPL", "MSFT"],
        start_date="2024-12-02",
        end_date="2025-09-30",
    )
    d = manifest.to_dict()
    assert "manifest_sha256" in d
    assert len(d["manifest_sha256"]) == 64

    reloaded = DaytradeDatasetManifest.from_dict(d)
    assert reloaded.study_id == "DAYTRADE-001B"
    assert reloaded.universe == ["AAPL", "MSFT"]
    assert reloaded.manifest_sha256 == d["manifest_sha256"]


def _valid_source_files(spec: DaytradeSpec) -> dict[str, str]:
    return {f"bars/{t}.csv": "a" * 64 for t in spec.universe}


def test_manifest_validate_against_spec_rejects_mutations(locked_spec: DaytradeSpec) -> None:
    """Mutating locked fields fails contract validation against the DaytradeSpec."""
    valid_manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.warmup.start,
        end_date=locked_spec.validation.end,
        source_files=_valid_source_files(locked_spec),
    )
    valid_manifest.validate_against_spec(locked_spec)

    # 1. Mutate study_id
    bad_study_id = DaytradeDatasetManifest(
        study_id="DAYTRADE-001",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        source_files=_valid_source_files(locked_spec),
    )
    with pytest.raises(DatasetSecurityError, match="must be strictly 'DAYTRADE-001B'"):
        bad_study_id.validate_against_spec(locked_spec)

    # 2. Mutate provider
    bad_provider = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        provider="yahoo",
        partition="preholdout",
        universe=list(locked_spec.universe),
        source_files=_valid_source_files(locked_spec),
    )
    with pytest.raises(DatasetSecurityError, match="provider 'yahoo' mismatch"):
        bad_provider.validate_against_spec(locked_spec)

    # 3. Mutate universe
    bad_universe = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=["AAPL"],
        source_files={"bars/AAPL.csv": "a" * 64},
    )
    with pytest.raises(DatasetSecurityError, match="universe mismatch"):
        bad_universe.validate_against_spec(locked_spec)

    # 4. Empty source files
    empty_files = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        source_files={},
    )
    with pytest.raises(DatasetSecurityError, match="at least one source file record"):
        empty_files.validate_against_spec(locked_spec)


def test_pagination_hard_stop_exceeding_100_pages_fails_closed() -> None:
    """Month-chunk fetch exceeding 100 pages terminates with DatasetPaginationLimitError."""
    mock_client = MagicMock()
    mock_client.max_retries = 1
    mock_client.get_bars.return_value = (
        {},
        {
            "safe_error_classification": "max_pages_exceeded",
            "pagination_complete": False,
            "next_page_token_present": True,
        },
    )

    adapter = DaytradeDatasetAcquisitionAdapter(client=mock_client)

    with pytest.raises(DatasetPaginationLimitError, match="hard limit of 100 pages exceeded"):
        adapter.fetch_symbol_month_bars(
            symbol="AAPL",
            start_utc=datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
            end_utc=datetime(2025, 1, 31, 23, 59, tzinfo=UTC),
        )


def test_adapter_rejects_client_with_excessive_retries() -> None:
    """Acquisition adapter fails closed if client max_retries > 1."""
    mock_client = MagicMock()
    mock_client.max_retries = 3

    with pytest.raises(DatasetSecurityError, match="exceeds locked limit of 1"):
        DaytradeDatasetAcquisitionAdapter(client=mock_client)


def test_actual_provider_dataframe_normalization_and_csv_writer(tmp_path: Path) -> None:
    """Actual provider DataFrame shape from DatasetAlpacaClient._normalize_bars writes valid CSV with no KeyError."""
    from tradex.research.daytrade_reversal.dataset import (
        read_normalized_bars_csv,
        write_normalized_bars_csv,
    )
    from tradex.research.intraday_dataset.alpaca_client import DatasetAlpacaClient

    client = DatasetAlpacaClient(api_key="k", secret_key="s", request_func=lambda *a, **kw: None)
    provider_raw_bars = [
        {"t": "2025-01-02T14:31:00Z", "o": 100.0, "h": 101.0, "l": 99.5, "c": 100.5, "v": 1000},
        {"t": "2025-01-02T14:30:00Z", "o": 99.0, "h": 100.0, "l": 98.5, "c": 99.5, "v": 500},
    ]
    df, malformed_ts = client._normalize_bars(provider_raw_bars)
    assert malformed_ts == 0
    # Crucial assertion: provider DataFrame has DatetimeIndex named 'datetime', not a 'bar_start' column
    assert "bar_start" not in df.columns
    assert df.index.name == "datetime"

    out_csv = tmp_path / "bars" / "AAPL.csv"
    write_normalized_bars_csv(out_csv, df)

    assert out_csv.is_file()
    read_df = read_normalized_bars_csv(out_csv)
    assert list(read_df.columns) == ["bar_start", "open", "high", "low", "close", "volume"]
    # Check deterministic ascending UTC sort
    assert read_df["bar_start"].iloc[0] == "2025-01-02T14:30:00Z"
    assert read_df["bar_start"].iloc[1] == "2025-01-02T14:31:00Z"


def test_manifest_source_file_contract_rejections(locked_spec: DaytradeSpec) -> None:
    """Strict manifest source-file rules: path traversal, absolute path, malformed digest, missing/unexpected tickers."""
    # 1. Path traversal
    bad_traversal = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.warmup.start,
        end_date=locked_spec.validation.end,
        source_files={**_valid_source_files(locked_spec), "bars/../evil.csv": "a" * 64},
    )
    with pytest.raises(DatasetSecurityError, match="Path traversal detected"):
        bad_traversal.validate_against_spec(locked_spec)

    # 2. Absolute path
    bad_abs = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.warmup.start,
        end_date=locked_spec.validation.end,
        source_files={"/etc/bars.csv": "a" * 64},
    )
    with pytest.raises(DatasetSecurityError, match="Absolute or malformed path"):
        bad_abs.validate_against_spec(locked_spec)

    # 3. Malformed digest
    bad_digest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.warmup.start,
        end_date=locked_spec.validation.end,
        source_files={**_valid_source_files(locked_spec), f"bars/{locked_spec.universe[0]}.csv": "short_hash"},
    )
    with pytest.raises(DatasetSecurityError, match="Malformed SHA-256 digest"):
        bad_digest.validate_against_spec(locked_spec)

    # 4. Missing ticker source file
    partial_files = _valid_source_files(locked_spec)
    partial_files.pop(f"bars/{locked_spec.universe[0]}.csv")
    missing_ticker_manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.warmup.start,
        end_date=locked_spec.validation.end,
        source_files=partial_files,
    )
    with pytest.raises(DatasetSecurityError, match="Missing expected ticker source files"):
        missing_ticker_manifest.validate_against_spec(locked_spec)

    # 5. Unexpected source file
    unexpected_manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.warmup.start,
        end_date=locked_spec.validation.end,
        source_files={**_valid_source_files(locked_spec), "bars/EXTRA.csv": "a" * 64},
    )
    with pytest.raises(DatasetSecurityError, match="Unexpected source files in manifest"):
        unexpected_manifest.validate_against_spec(locked_spec)


def test_unmanifested_bars_file_rejected_by_loader(tmp_path: Path, locked_spec: DaytradeSpec) -> None:
    """An unmanifested on-disk CSV in partition/bars fails closed upon dataset load."""
    import json

    import pandas as pd

    from tradex.research.daytrade_reversal.dataset import (
        load_private_dataset,
        write_normalized_bars_csv,
    )

    preholdout_dir = tmp_path / "preholdout"
    bars_dir = preholdout_dir / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)

    source_files: dict[str, str] = {}
    for ticker in locked_spec.universe:
        csv_file = bars_dir / f"{ticker}.csv"
        write_normalized_bars_csv(csv_file, pd.DataFrame(columns=["bar_start", "open", "high", "low", "close", "volume"]))
        source_files[f"bars/{ticker}.csv"] = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.warmup.start,
        end_date=locked_spec.validation.end,
        source_files=source_files,
    )
    man_file = preholdout_dir / "manifest.lock.json"
    man_file.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    # Add an unmanifested CSV file
    unmanifested_csv = bars_dir / "UNMANIFESTED.csv"
    write_normalized_bars_csv(unmanifested_csv, pd.DataFrame(columns=["bar_start", "open", "high", "low", "close", "volume"]))

    with pytest.raises(DatasetSecurityError, match="Unmanifested OHLCV file found"):
        load_private_dataset(tmp_path, "development", locked_spec)


def test_holdout_acquisition_blocked_before_provider_call(tmp_path: Path, locked_spec: DaytradeSpec) -> None:
    """Provider call count must remain 0 when validation artifact is not supported or missing."""
    import json

    from tradex.research.daytrade_reversal.dataset import acquire_dataset_partition

    pre_dir = tmp_path / "preholdout"
    pre_dir.mkdir(parents=True, exist_ok=True)
    pre_manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.warmup.start,
        end_date=locked_spec.validation.end,
        source_files=_valid_source_files(locked_spec),
    )
    (pre_dir / "manifest.lock.json").write_text(json.dumps(pre_manifest.to_dict(), indent=2), encoding="utf-8")

    mock_client = MagicMock()
    mock_client.max_retries = 1

    # Missing validation bundle dir
    with pytest.raises(DatasetSecurityError, match="requires validation_bundle_dir"):
        acquire_dataset_partition(
            spec=locked_spec,
            dataset_root=tmp_path,
            partition="holdout",
            client=mock_client,
            validation_bundle_dir=None,
        )

    assert mock_client.get_bars.call_count == 0
