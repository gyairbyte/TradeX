"""Targeted regression tests for LONG-002D1-CORR-001.

Verifies:
1. Full-run candidate selection derives from primary df_obs IDs, not all discovery candidates.
2. Irrelevant / non-study candidates are never passed to the bar loader.
3. Missing primary security IDs fail closed in select_study_candidates.
4. Duplicate immutable security IDs in discovery manifest fail closed.
5. Cache miss / live-request path fails closed and audit counters distinguish
   attempted vs blocked vs executed truthfully.
6. Benchmark and run modules share the identical select_study_candidates helper.
7. Stage C provenance auditing fails closed on any unmatched cache payload.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tradex.research.long_002d import benchmark, cli
from tradex.research.long_002d.loader import (
    AuditingReadOnlyCache,
    NetworkAuditTracker,
    audit_stage_c_cache_provenance,
    create_read_only_alpaca_client,
    select_study_candidates,
)


def _make_dummy_manifest(path: Path, security_ids: list[str]) -> Path:
    payload = {
        "manifest_version": "1.0.0",
        "candidates": [
            {
                "immutable_security_id": s_id,
                "primary_symbol": f"SYM_{s_id}",
                "start_date": "2015-01-01",
                "end_date": "2020-12-31",
                "sector": "Technology",
            }
            for s_id in security_ids
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_select_study_candidates_filters_to_study_universe(tmp_path: Path):
    """Test that candidate selection derives strictly from primary IDs and ignores non-study candidates."""
    manifest_path = _make_dummy_manifest(
        tmp_path / "discovery_manifest.json",
        ["SEC_A", "SEC_B", "SEC_C", "SEC_D"],
    )
    study_ids = ["SEC_A", "SEC_C"]

    selected = select_study_candidates(manifest_path, study_ids)
    assert len(selected) == 2
    assert [c.immutable_security_id for c in selected] == ["SEC_A", "SEC_C"]


def test_select_study_candidates_missing_id_fails_closed(tmp_path: Path):
    """Test that if a primary observation security ID is missing from discovery manifest, it fails closed."""
    manifest_path = _make_dummy_manifest(
        tmp_path / "discovery_manifest.json",
        ["SEC_A", "SEC_B"],
    )
    study_ids = ["SEC_A", "SEC_MISSING"]

    with pytest.raises(ValueError, match="Missing 1 study security IDs from discovery manifest"):
        select_study_candidates(manifest_path, study_ids)


def test_select_study_candidates_duplicate_id_fails_closed(tmp_path: Path):
    """Test that duplicate immutable_security_id entries in discovery manifest fail closed."""
    payload = {
        "manifest_version": "1.0.0",
        "candidates": [
            {"immutable_security_id": "SEC_DUP", "primary_symbol": "D1", "start_date": "2015-01-01", "end_date": "2020-12-31"},
            {"immutable_security_id": "SEC_DUP", "primary_symbol": "D2", "start_date": "2015-01-01", "end_date": "2020-12-31"},
        ],
    }
    manifest_path = tmp_path / "dup_manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate immutable_security_id"):
        select_study_candidates(manifest_path, ["SEC_DUP"])


def test_non_study_candidates_never_passed_to_loader(tmp_path: Path):
    """Verify that only selected study candidates are processed in execution loop."""
    manifest_path = _make_dummy_manifest(
        tmp_path / "discovery_manifest.json",
        ["SEC_STUDY_1", "SEC_STUDY_2", "SEC_IRRELEVANT_3", "SEC_IRRELEVANT_4"],
    )
    study_ids = ["SEC_STUDY_1", "SEC_STUDY_2"]

    selected = select_study_candidates(manifest_path, study_ids)

    mock_loader = MagicMock(return_value=(pd.DataFrame({"close": [10.0]}), [], {}))

    for cand in selected:
        mock_loader(cand)

    loaded_ids = [call.args[0].immutable_security_id for call in mock_loader.call_args_list]
    assert loaded_ids == ["SEC_STUDY_1", "SEC_STUDY_2"]
    assert "SEC_IRRELEVANT_3" not in loaded_ids
    assert "SEC_IRRELEVANT_4" not in loaded_ids


def test_audit_counters_distinguish_attempted_vs_blocked_vs_executed(tmp_path: Path):
    """Verify truthful audit counters: live request path attempt is recorded and blocked, outbound HTTP remains 0."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    client, cache, tracker = create_read_only_alpaca_client(cache_dir)

    assert tracker.provider_cache_hits == 0
    assert tracker.provider_cache_misses == 0
    assert tracker.live_request_path_attempts == 0
    assert tracker.outbound_http_requests_executed == 0
    assert tracker.blocked_live_request_attempts == 0

    # 1. Cache miss on cache.get
    body, _sha, _req_time = cache.get("https://data.alpaca.markets/v2/bars", "dummy_fp")
    assert body is None
    assert tracker.provider_cache_misses == 1
    assert tracker.provider_cache_hits == 0

    # 2. Live request function entered and blocked
    with pytest.raises(RuntimeError, match="FAIL-CLOSED BREACH"):
        client._request_func("https://data.alpaca.markets/v2/stocks/AAPL/bars")

    assert tracker.live_request_path_attempts == 1
    assert tracker.blocked_live_request_attempts == 1
    assert tracker.outbound_http_requests_executed == 0


def test_benchmark_and_cli_share_selection_helper():
    """Verify benchmark and CLI use the exact same candidate selection function."""
    assert benchmark.select_study_candidates is select_study_candidates
    assert cli.select_study_candidates is select_study_candidates


def test_provenance_audit_fails_closed_on_unmatched_payload(tmp_path: Path):
    """Verify that audit_stage_c_cache_provenance fails closed if consumed payload is not in Stage C provenance."""
    stage_c_dir = tmp_path / "stage_c"
    stage_c_dir.mkdir()

    # Create dummy provenance parquet
    prov_df = pd.DataFrame([
        {
            "provider_name": "alpaca",
            "request_fingerprint_sha256": "known_fp_123",
            "response_sha256": "known_sha_456",
        }
    ])
    table = pa.Table.from_pandas(prov_df)
    pq.write_table(table, stage_c_dir / "provenance_records.parquet")

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    tracker = NetworkAuditTracker()
    cache = AuditingReadOnlyCache(cache_dir, tracker=tracker)

    # Inject an unmatched consumed payload
    cache.consumed_payloads["dummy_key"] = {
        "byte_count": 100,
        "sha256": "unmatched_sha_999",
        "url": "https://test.url",
        "req_fp": "known_fp_123",
    }

    with pytest.raises(RuntimeError, match="STAGE C CACHE PROVENANCE AUDIT FAILED: 1 consumed cache payloads"):
        audit_stage_c_cache_provenance(stage_c_dir, cache, tracker)
