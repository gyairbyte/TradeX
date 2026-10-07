"""Two-stage dataset contract, manifest schema, and cryptographic hashing tests."""
from __future__ import annotations

from tradex.research.daytrade_orb import (
    TwoStageDatasetManifest,
    compute_manifest_sha256,
    manifest_from_json,
    manifest_to_json,
    validate_dataset_manifest_invariants,
)


def _make_valid_manifest() -> TwoStageDatasetManifest:
    return TwoStageDatasetManifest(
        task_id="DAYTRADE-003C-ORB-EVALUATOR-001",
        strategy_id="DAYTRADE-003B-ORB-SIP5M",
        upstream_spec_sha256="62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0",
        resolution_spec_sha256="00641c084dd5b40537587f8c2e1d15a5b1094a54fa3fdd9ba6f721a97f4d0ef6",
        provider_identity="massive_reference_alpaca_sip",
        feed="sip",
        adjustment_mode="raw",
        timezone="America/New_York",
        calendar_version="XNYS",
        universe_provider="massive_v3_reference",
        universe_query_date="2025-01-02",
        universe_symbol_count=7124,
        universe_hash="a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0",
        exchange_filters=("NYSE", "NASDAQ"),
        type_code_distribution={"CS": 6500, "ADRC": 500, "ETF": 124},
        daily_data_hashes_and_counts={"row_count": 100000, "sha256": "abcdef123456"},
        opening_range_data_hashes_and_counts={"row_count": 50000, "sha256": "bcdefa123456"},
        top_20_selection_artifact_hash="cdefab1234567890123456789012345678901234567890123456789012345678",
        full_path_selected_symbol_data_hashes_and_counts={"row_count": 150000, "sha256": "defabc123456"},
        session_coverage=("2025-01-02", "2025-12-31"),
        excluded_sessions=("2025-11-28", "2025-12-24"),  # Early closes excluded
        dq_reasons=("early_close_excluded",),
        provider_request_ids=("req-001", "req-002"),
        pagination_completeness=True,
        acquisition_timestamps={"stage_a": "2026-10-06T12:00:00Z", "stage_b": "2026-10-06T12:30:00Z"},
        holdout_status="quarantined_unopened",
    )


def test_manifest_json_serialization_round_trip() -> None:
    """Requirement: Manifest serializes to deterministic JSON and deserializes identically."""
    manifest = _make_valid_manifest()
    json_str = manifest_to_json(manifest)
    reloaded = manifest_from_json(json_str)

    assert reloaded == manifest
    hash1 = compute_manifest_sha256(manifest)
    hash2 = compute_manifest_sha256(reloaded)
    assert hash1 == hash2


def test_manifest_validation_invariants() -> None:
    """Requirement: Invariant validator catches improper adjustments, timezones, or incomplete pagination."""
    valid = _make_valid_manifest()
    assert validate_dataset_manifest_invariants(valid) == []

    # Corrupt adjustment mode
    bad_adj = TwoStageDatasetManifest(**{**valid.__dict__, "adjustment_mode": "split_adjusted"})
    errors = validate_dataset_manifest_invariants(bad_adj)
    assert any("Adjustment mode must be 'raw'" in e for e in errors)

    # Corrupt timezone
    bad_tz = TwoStageDatasetManifest(**{**valid.__dict__, "timezone": "UTC"})
    errors_tz = validate_dataset_manifest_invariants(bad_tz)
    assert any("Timezone must be 'America/New_York'" in e for e in errors_tz)

    # Incomplete pagination
    bad_page = TwoStageDatasetManifest(**{**valid.__dict__, "pagination_completeness": False})
    errors_page = validate_dataset_manifest_invariants(bad_page)
    assert any("Pagination completeness" in e for e in errors_page)
