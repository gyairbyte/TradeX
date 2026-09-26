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


def test_dataset_root_inside_repo_is_rejected(tmp_path: Path) -> None:
    """Refuse to write raw/normalized OHLCV if destination is inside git repo/worktree."""
    repo_root = get_repo_root()
    in_repo_path = repo_root / "data" / "raw_ohlcv"

    with pytest.raises(DatasetSecurityError, match="inside the tracked repository"):
        validate_dataset_root(in_repo_path, repo_root=repo_root)


def test_dataset_root_outside_repo_is_accepted(tmp_path: Path) -> None:
    """An external directory (e.g. tmp_path outside repo) is accepted."""
    repo_root = get_repo_root()
    # tmp_path in temp directory is outside repo_root
    validated = validate_dataset_root(tmp_path, repo_root=repo_root)
    assert validated == tmp_path.resolve()


def test_manifest_prohibits_secrets_and_api_keys() -> None:
    """Manifest serialization fails closed if representative API keys or secrets are present."""
    leaked_data = {
        "study_id": "DAYTRADE-001B",
        "APCA-API-KEY-ID": "LEAKED_KEY_12345",
    }
    with pytest.raises(DatasetSecurityError, match="Prohibited header/key"):
        sanitize_manifest_data(leaked_data)


def test_manifest_serialization_and_hash_roundtrip() -> None:
    """Valid dataset manifest computes deterministic SHA-256 and round-trips cleanly."""
    manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256="0651e075ff0641510788582a67827e065347f851e9363964f85a193a3d166620",
        request_count=10,
        http_page_count=15,
        retry_count=1,
    )
    d = manifest.to_dict()
    assert "manifest_sha256" in d
    assert len(d["manifest_sha256"]) == 64

    reloaded = DaytradeDatasetManifest.from_dict(d)
    assert reloaded.study_id == "DAYTRADE-001B"
    assert reloaded.http_page_count == 15


def test_pagination_hard_stop_exceeding_100_pages_fails_closed(tmp_path: Path) -> None:
    """Month-chunk fetch exceeding 100 pages terminates with DatasetPaginationLimitError."""
    mock_client = MagicMock()
    # Mock returns 101 pages
    mock_client.get_bars.return_value = ({}, {"page_count": 101})

    adapter = DaytradeDatasetAcquisitionAdapter(
        alpaca_client=mock_client,
        dataset_root=tmp_path,
    )

    with pytest.raises(DatasetPaginationLimitError, match="exceeded locked hard limit of 100 pages"):
        adapter.fetch_month_chunk(
            symbols=["AAPL"],
            start_utc=datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
            end_utc=datetime(2025, 1, 31, 23, 59, tzinfo=UTC),
        )
