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


def test_manifest_validate_against_spec_rejects_mutations(locked_spec: DaytradeSpec) -> None:
    """Mutating locked fields fails contract validation against the DaytradeSpec."""
    valid_manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.warmup.start,
        end_date=locked_spec.validation.end,
        source_files={"bars/AAPL.csv": "abc"},
    )
    valid_manifest.validate_against_spec(locked_spec)

    # 1. Mutate study_id
    bad_study_id = DaytradeDatasetManifest(
        study_id="DAYTRADE-001",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        source_files={"bars/AAPL.csv": "abc"},
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
        source_files={"bars/AAPL.csv": "abc"},
    )
    with pytest.raises(DatasetSecurityError, match="provider 'yahoo' mismatch"):
        bad_provider.validate_against_spec(locked_spec)

    # 3. Mutate universe
    bad_universe = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=["AAPL"],
        source_files={"bars/AAPL.csv": "abc"},
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
