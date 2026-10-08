"""Machine-readable dataset contract and manifest schema for future two-stage acquisition."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TwoStageDatasetManifest:
    """Cryptographic and provenance manifest for the future two-stage ORB dataset.

    Enforces lean acquisition:
    - Stage A: candidate construction data for all PIT universe symbols (09:30-09:34).
    - Stage B: full 1-minute regular-session path strictly for Top-20 selected symbols.
    """

    task_id: str
    strategy_id: str
    upstream_spec_sha256: str
    resolution_spec_sha256: str
    provider_identity: str
    feed: str
    adjustment_mode: str
    timezone: str
    calendar_version: str
    universe_provider: str
    universe_query_date: str
    universe_symbol_count: int
    universe_hash: str
    exchange_filters: tuple[str, ...]
    type_code_distribution: dict[str, int]
    daily_data_hashes_and_counts: dict[str, Any]
    opening_range_data_hashes_and_counts: dict[str, Any]
    top_20_selection_artifact_hash: str
    full_path_selected_symbol_data_hashes_and_counts: dict[str, Any]
    session_coverage: tuple[str, ...]
    excluded_sessions: tuple[str, ...]
    dq_reasons: tuple[str, ...]
    provider_request_ids: tuple[str, ...]
    pagination_completeness: bool
    acquisition_timestamps: dict[str, str]
    holdout_status: str = "quarantined_unopened"
    schema_version: str = "1.0"
    metadata: dict[str, Any] = field(default_factory=dict)


def manifest_to_dict(manifest: TwoStageDatasetManifest) -> dict[str, Any]:
    """Convert a TwoStageDatasetManifest instance to a canonical dictionary."""
    data = asdict(manifest)
    # Ensure lists/tuples are serialized consistently
    return data


def manifest_to_json(manifest: TwoStageDatasetManifest, indent: int = 2) -> str:
    """Serialize a TwoStageDatasetManifest to deterministic JSON format."""
    return json.dumps(manifest_to_dict(manifest), indent=indent, sort_keys=True)


def manifest_from_dict(data: dict[str, Any]) -> TwoStageDatasetManifest:
    """Parse a TwoStageDatasetManifest from a dictionary."""
    return TwoStageDatasetManifest(
        task_id=data["task_id"],
        strategy_id=data["strategy_id"],
        upstream_spec_sha256=data["upstream_spec_sha256"],
        resolution_spec_sha256=data["resolution_spec_sha256"],
        provider_identity=data["provider_identity"],
        feed=data["feed"],
        adjustment_mode=data["adjustment_mode"],
        timezone=data["timezone"],
        calendar_version=data["calendar_version"],
        universe_provider=data["universe_provider"],
        universe_query_date=data["universe_query_date"],
        universe_symbol_count=int(data["universe_symbol_count"]),
        universe_hash=data["universe_hash"],
        exchange_filters=tuple(data["exchange_filters"]),
        type_code_distribution=dict(data["type_code_distribution"]),
        daily_data_hashes_and_counts=dict(data["daily_data_hashes_and_counts"]),
        opening_range_data_hashes_and_counts=dict(data["opening_range_data_hashes_and_counts"]),
        top_20_selection_artifact_hash=data["top_20_selection_artifact_hash"],
        full_path_selected_symbol_data_hashes_and_counts=dict(
            data["full_path_selected_symbol_data_hashes_and_counts"]
        ),
        session_coverage=tuple(data["session_coverage"]),
        excluded_sessions=tuple(data["excluded_sessions"]),
        dq_reasons=tuple(data["dq_reasons"]),
        provider_request_ids=tuple(data["provider_request_ids"]),
        pagination_completeness=bool(data["pagination_completeness"]),
        acquisition_timestamps=dict(data["acquisition_timestamps"]),
        holdout_status=data.get("holdout_status", "quarantined_unopened"),
        schema_version=data.get("schema_version", "1.0"),
        metadata=dict(data.get("metadata", {})),
    )


def manifest_from_json(json_str: str) -> TwoStageDatasetManifest:
    """Parse a TwoStageDatasetManifest from a JSON string."""
    data = json.loads(json_str)
    return manifest_from_dict(data)


def compute_manifest_sha256(manifest: TwoStageDatasetManifest) -> str:
    """Compute the cryptographic SHA-256 hash of a serialized manifest."""
    serialized = manifest_to_json(manifest, indent=2).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def validate_dataset_manifest_invariants(manifest: TwoStageDatasetManifest) -> list[str]:
    """Validate that all required invariants for the future dataset contract are satisfied.

    Returns a list of error strings; empty list indicates full compliance.
    """
    errors: list[str] = []

    if manifest.adjustment_mode != "raw":
        errors.append(f"Adjustment mode must be 'raw', got '{manifest.adjustment_mode}'")

    if manifest.timezone != "America/New_York":
        errors.append(f"Timezone must be 'America/New_York', got '{manifest.timezone}'")

    if not manifest.pagination_completeness:
        errors.append("Pagination completeness flag must be True")

    if manifest.universe_symbol_count <= 0:
        errors.append("Universe symbol count must be positive")

    if not manifest.universe_hash:
        errors.append("Universe hash must not be empty")

    if not manifest.top_20_selection_artifact_hash:
        errors.append("Top-20 selection artifact hash must not be empty")

    if manifest.holdout_status not in ("quarantined_unopened", "authorized_opened"):
        errors.append(f"Invalid holdout status: '{manifest.holdout_status}'")

    return errors
