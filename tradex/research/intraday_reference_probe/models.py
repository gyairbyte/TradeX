"""Typed dataclasses for INTRA-001B reference-provider probe."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class PaginationPage:
    """One page of a paginated PIT snapshot."""

    provider: str
    pit_date: str
    state: str
    page_number: int
    row_count: int
    provider_reported_count: int | None
    page_sha256: str
    next_url_present: bool
    next_cursor_sha256: str | None
    http_status: int | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "pit_date": self.pit_date,
            "state": self.state,
            "page_number": self.page_number,
            "row_count": self.row_count,
            "provider_reported_count": self.provider_reported_count,
            "page_sha256": self.page_sha256,
            "next_url_present": self.next_url_present,
            "next_cursor_sha256": self.next_cursor_sha256,
            "http_status": self.http_status,
            "error": self.error,
        }


@dataclass(frozen=True)
class PITObservation:
    """One point-in-time listing fetch for a single date and state."""

    provider: str
    pit_date: str
    state: str
    requested_at: str
    elapsed_seconds: float
    row_count: int
    column_headers: tuple[str, ...]
    raw_sha256: str
    repeat_sha256: str | None = None
    repeat_match: bool | None = None
    repeat_seconds: float | None = None
    http_status: int | None = None
    error: str | None = None
    # Pagination metadata
    page_count: int = 0
    first_page_count: int = 0
    last_page_count: int = 0
    provider_reported_count: int | None = None
    pagination_complete: bool = False
    max_pages_reached: bool = False
    repeated_cursor_detected: bool = False
    repeated_next_url_detected: bool = False
    cycle_detected: bool = False
    unexpected_next_url: bool = False
    full_snapshot_sha256: str | None = None
    canonical_ticker_count: int = 0
    blank_ticker_count: int = 0
    duplicate_ticker_count: int = 0
    unresolved_duplicate_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "pit_date": self.pit_date,
            "state": self.state,
            "requested_at": self.requested_at,
            "elapsed_seconds": self.elapsed_seconds,
            "row_count": self.row_count,
            "column_headers": list(self.column_headers),
            "raw_sha256": self.raw_sha256,
            "repeat_sha256": self.repeat_sha256,
            "repeat_match": self.repeat_match,
            "repeat_seconds": self.repeat_seconds,
            "http_status": self.http_status,
            "error": self.error,
            "page_count": self.page_count,
            "first_page_count": self.first_page_count,
            "last_page_count": self.last_page_count,
            "provider_reported_count": self.provider_reported_count,
            "pagination_complete": self.pagination_complete,
            "max_pages_reached": self.max_pages_reached,
            "repeated_cursor_detected": self.repeated_cursor_detected,
            "repeated_next_url_detected": self.repeated_next_url_detected,
            "cycle_detected": self.cycle_detected,
            "unexpected_next_url": self.unexpected_next_url,
            "full_snapshot_sha256": self.full_snapshot_sha256,
            "canonical_ticker_count": self.canonical_ticker_count,
            "blank_ticker_count": self.blank_ticker_count,
            "duplicate_ticker_count": self.duplicate_ticker_count,
            "unresolved_duplicate_count": self.unresolved_duplicate_count,
        }


@dataclass(frozen=True)
class CapabilityEvidence:
    """A single row in the provider capability matrix."""

    provider: str
    capability: str
    supported: bool
    evidence_class: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "capability": self.capability,
            "supported": self.supported,
            "evidence_class": self.evidence_class,
            "note": self.note,
        }


@dataclass(frozen=True)
class ProviderDisposition:
    """Final disposition for one provider/dataset attempt."""

    provider: str
    dataset: str
    pit_dates: tuple[str, ...]
    credential_available: bool
    probe_executed: bool
    disposition: str
    reason: str
    logical_request_count: int = 0
    http_request_count: int = 0
    http_error_count: int = 0
    selected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "dataset": self.dataset,
            "pit_dates": list(self.pit_dates),
            "credential_available": self.credential_available,
            "probe_executed": self.probe_executed,
            "disposition": self.disposition,
            "reason": self.reason,
            "logical_request_count": self.logical_request_count,
            "http_request_count": self.http_request_count,
            "http_error_count": self.http_error_count,
            "selected": self.selected,
        }


@dataclass(frozen=True)
class ProviderCandidateResult:
    """Aggregated probe results for one reference provider."""

    provider: str
    target_entitlement: str
    probe_version: int
    observations: tuple[PITObservation, ...]
    capability_rows: tuple[CapabilityEvidence, ...]
    pagination_pages: tuple[PaginationPage, ...] = ()
    security_type_counts: dict[str, int] = field(default_factory=dict)
    exchange_counts: dict[str, int] = field(default_factory=dict)
    primary_exchange_field: str | None = None
    security_type_field: str | None = None
    delisting_date_field: str | None = None
    listing_date_field: str | None = None
    error: str | None = None
    # V3 additions
    ticker_types: tuple[dict[str, Any], ...] = ()
    taxonomy_mapping: dict[str, str] = field(default_factory=dict)
    taxonomy_endpoint_verified: bool = False
    taxonomy_sha256: str | None = None
    stock_type_allowlist: tuple[str, ...] = ()
    blank_symbol_count: int = 0
    duplicate_symbol_count: int = 0
    unresolved_duplicate_count: int = 0
    duplicate_details: tuple[dict[str, Any], ...] = ()
    max_pages_active: int = 0
    max_pages_inactive: int = 0
    estimated_http_calls_48_months: int | None = None
    estimated_collection_time_48_months_seconds: float | None = None
    full_snapshot_repeat_match: bool = False
    lifecycle_fields_present: tuple[str, ...] = ()
    stable_identity_fields: tuple[str, ...] = ()
    cross_provider_join_field: str | None = None
    date_semantics_note: str = ""
    otc_rule_note: str = ""
    exchange_or_otc_policy_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "target_entitlement": self.target_entitlement,
            "probe_version": self.probe_version,
            "observations": [o.to_dict() for o in self.observations],
            "capability_rows": [r.to_dict() for r in self.capability_rows],
            "pagination_pages": [p.to_dict() for p in self.pagination_pages],
            "security_type_counts": dict(sorted(self.security_type_counts.items())),
            "exchange_counts": dict(sorted(self.exchange_counts.items())),
            "primary_exchange_field": self.primary_exchange_field,
            "security_type_field": self.security_type_field,
            "delisting_date_field": self.delisting_date_field,
            "listing_date_field": self.listing_date_field,
            "error": self.error,
            "ticker_types": list(self.ticker_types),
            "taxonomy_mapping": dict(sorted(self.taxonomy_mapping.items())),
            "taxonomy_endpoint_verified": self.taxonomy_endpoint_verified,
            "taxonomy_sha256": self.taxonomy_sha256,
            "stock_type_allowlist": list(self.stock_type_allowlist),
            "blank_symbol_count": self.blank_symbol_count,
            "duplicate_symbol_count": self.duplicate_symbol_count,
            "unresolved_duplicate_count": self.unresolved_duplicate_count,
            "duplicate_details": [dict(d) for d in self.duplicate_details],
            "max_pages_active": self.max_pages_active,
            "max_pages_inactive": self.max_pages_inactive,
            "estimated_http_calls_48_months": self.estimated_http_calls_48_months,
            "estimated_collection_time_48_months_seconds": self.estimated_collection_time_48_months_seconds,
            "full_snapshot_repeat_match": self.full_snapshot_repeat_match,
            "lifecycle_fields_present": list(self.lifecycle_fields_present),
            "stable_identity_fields": list(self.stable_identity_fields),
            "cross_provider_join_field": self.cross_provider_join_field,
            "date_semantics_note": self.date_semantics_note,
            "otc_rule_note": self.otc_rule_note,
            "exchange_or_otc_policy_version": self.exchange_or_otc_policy_version,
        }


@dataclass(frozen=True)
class ReferenceProbeDecision:
    """Final locked decision from the reference provider probe."""

    probe_version: int
    task_id: str
    provider: str | None
    outcome: str
    approved_as_reference_provider: bool
    reason: str
    candidate_order: tuple[str, ...]
    # Provenance
    starting_main_sha: str | None = None
    branch: str | None = None
    live_run_head: str | None = None
    final_pr_head: str | None = None
    v1_pre_registration_commit: str | None = None
    v2_pre_registration_commit: str | None = None
    v3_pre_registration_commit: str | None = None
    v4_pre_registration_commit: str | None = None
    strategy_spec_sha256: str | None = None
    alpaca_v2_decision_sha256: str | None = None
    probe_spec_sha256: str | None = None
    mixed_provider_amendment_sha256: str | None = None
    mixed_provider_amendment_status_before_run: str | None = None
    mixed_provider_approved_by_gary: bool = True
    original_dataset_start: str | None = None
    original_dataset_end: str | None = None
    fallback_dataset_start: str | None = None
    fallback_dataset_end: str | None = None
    fallback_evaluated: bool = False
    fallback_activation_reason: str | None = None
    dataset_used: str | None = None
    # Provider availability
    alpha_vantage_credentials_available: bool = False
    alpha_vantage_probe_executed: bool = False
    alpha_vantage_disposition: str = "not_attempted"
    massive_credentials_available: bool = False
    massive_probe_executed: bool = False
    massive_disposition: str = "not_attempted"
    selected_reference_provider: str | None = None
    authoritative_ohlcv_provider: str = "alpaca"
    authoritative_ohlcv_feed: str = "sip"
    reference_provider_role: tuple[str, ...] = ()
    # Contract invariants
    no_ohlcv_provider_mixing: bool = True
    no_composite_reference_stack: bool = True
    no_silent_fallback: bool = True
    no_paid_upgrade: bool = True
    # Dataset / pagination summary
    pit_dates: tuple[str, ...] = ()
    fallback_probe_dates: tuple[str, ...] = ()
    pagination_verified: bool = False
    maximum_pages_active: int = 0
    maximum_pages_inactive: int = 0
    repeatability_passed: bool = False
    taxonomy_endpoint_verified: bool = False
    taxonomy_sha256: str | None = None
    stock_type_allowlist: tuple[str, ...] = ()
    exchange_or_otc_policy_version: str = ""
    duplicate_symbol_count: int = 0
    unresolved_duplicate_count: int = 0
    lifecycle_evidence: str = ""
    historical_2022_entitlement: bool = False
    no_present_day_reconstruction: bool = False
    estimated_http_calls_48_months: int | None = None
    estimated_collection_time_48_months_seconds: float | None = None
    # Gate results (one boolean each)
    pit_date_support_for_all_probe_dates: bool = False
    active_state_complete: bool = False
    inactive_or_delisted_state_complete: bool = False
    pagination_exhausted_to_terminal: bool = False
    no_pagination_cycles_or_repeated_cursors: bool = False
    exact_historical_date_semantics: bool = False
    common_stock_classification: bool = False
    etf_classification: bool = False
    warrant_exclusion: bool = False
    right_exclusion: bool = False
    unit_exclusion: bool = False
    preferred_stock_exclusion: bool = False
    otc_exclusion: bool = False
    primary_listing_provenance: bool = False
    symbol_presence_and_determinism: bool = False
    lifecycle_evidence_gate: bool = False
    duplicate_symbol_behavior_and_resolution: bool = False
    repeatability: bool = False
    hashability: bool = False
    no_present_day_reconstruction_gate: bool = False
    historical_2022_entitlement_under_current_plan: bool = False
    feasible_for_all_48_monthly_pit_snapshots: bool = False
    feasible_for_all_probe_monthly_pit_snapshots: bool = False
    all_mandatory_gates_passed: bool = False
    not_required_gates: tuple[str, ...] = ()
    # Audit / artifacts
    blockers: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    recommended_next_assignment: str = ""
    production_behavior_changed: bool = False
    candidate_dispositions: tuple[ProviderDisposition, ...] = ()
    ran_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="microseconds"))

    def __post_init__(self) -> None:
        for name in ("blockers", "limitations"):
            value = getattr(self, name)
            if value is None:
                object.__setattr__(self, name, ())
                continue
            if isinstance(value, str):
                raise ValueError(f"{name} must be a tuple of strings, not a single string")
            if not isinstance(value, tuple):
                raise ValueError(f"{name} must be a tuple of strings")
            for item in value:
                if not isinstance(item, str):
                    raise ValueError(f"{name} must be a tuple of strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_version": self.probe_version,
            "task_id": self.task_id,
            "provider": self.provider,
            "outcome": self.outcome,
            "approved_as_reference_provider": self.approved_as_reference_provider,
            "reason": self.reason,
            "candidate_order": list(self.candidate_order),
            "starting_main_sha": self.starting_main_sha,
            "branch": self.branch,
            "live_run_head": self.live_run_head,
            "v1_pre_registration_commit": self.v1_pre_registration_commit,
            "v2_pre_registration_commit": self.v2_pre_registration_commit,
            "v3_pre_registration_commit": self.v3_pre_registration_commit,
            "v4_pre_registration_commit": self.v4_pre_registration_commit,
            "strategy_spec_sha256": self.strategy_spec_sha256,
            "alpaca_v2_decision_sha256": self.alpaca_v2_decision_sha256,
            "probe_spec_sha256": self.probe_spec_sha256,
            "mixed_provider_amendment_sha256": self.mixed_provider_amendment_sha256,
            "mixed_provider_amendment_status_before_run": self.mixed_provider_amendment_status_before_run,
            "mixed_provider_approved_by_gary": self.mixed_provider_approved_by_gary,
            "original_dataset_start": self.original_dataset_start,
            "original_dataset_end": self.original_dataset_end,
            "fallback_dataset_start": self.fallback_dataset_start,
            "fallback_dataset_end": self.fallback_dataset_end,
            "fallback_evaluated": self.fallback_evaluated,
            "fallback_activation_reason": self.fallback_activation_reason,
            "dataset_used": self.dataset_used,
            "alpha_vantage_credentials_available": self.alpha_vantage_credentials_available,
            "alpha_vantage_probe_executed": self.alpha_vantage_probe_executed,
            "alpha_vantage_disposition": self.alpha_vantage_disposition,
            "massive_credentials_available": self.massive_credentials_available,
            "massive_probe_executed": self.massive_probe_executed,
            "massive_disposition": self.massive_disposition,
            "selected_reference_provider": self.selected_reference_provider,
            "authoritative_ohlcv_provider": self.authoritative_ohlcv_provider,
            "authoritative_ohlcv_feed": self.authoritative_ohlcv_feed,
            "reference_provider_role": list(self.reference_provider_role),
            "no_ohlcv_provider_mixing": self.no_ohlcv_provider_mixing,
            "no_composite_reference_stack": self.no_composite_reference_stack,
            "no_silent_fallback": self.no_silent_fallback,
            "no_paid_upgrade": self.no_paid_upgrade,
            "pit_dates": list(self.pit_dates),
            "fallback_probe_dates": list(self.fallback_probe_dates),
            "pagination_verified": self.pagination_verified,
            "maximum_pages_active": self.maximum_pages_active,
            "maximum_pages_inactive": self.maximum_pages_inactive,
            "repeatability_passed": self.repeatability_passed,
            "taxonomy_endpoint_verified": self.taxonomy_endpoint_verified,
            "taxonomy_sha256": self.taxonomy_sha256,
            "stock_type_allowlist": list(self.stock_type_allowlist),
            "exchange_or_otc_policy_version": self.exchange_or_otc_policy_version,
            "duplicate_symbol_count": self.duplicate_symbol_count,
            "unresolved_duplicate_count": self.unresolved_duplicate_count,
            "lifecycle_evidence": self.lifecycle_evidence,
            "historical_2022_entitlement": self.historical_2022_entitlement,
            "no_present_day_reconstruction": self.no_present_day_reconstruction,
            "estimated_http_calls_48_months": self.estimated_http_calls_48_months,
            "estimated_collection_time_48_months_seconds": self.estimated_collection_time_48_months_seconds,
            "pit_date_support_for_all_probe_dates": self.pit_date_support_for_all_probe_dates,
            "active_state_complete": self.active_state_complete,
            "inactive_or_delisted_state_complete": self.inactive_or_delisted_state_complete,
            "pagination_exhausted_to_terminal": self.pagination_exhausted_to_terminal,
            "no_pagination_cycles_or_repeated_cursors": self.no_pagination_cycles_or_repeated_cursors,
            "exact_historical_date_semantics": self.exact_historical_date_semantics,
            "common_stock_classification": self.common_stock_classification,
            "etf_classification": self.etf_classification,
            "warrant_exclusion": self.warrant_exclusion,
            "right_exclusion": self.right_exclusion,
            "unit_exclusion": self.unit_exclusion,
            "preferred_stock_exclusion": self.preferred_stock_exclusion,
            "otc_exclusion": self.otc_exclusion,
            "primary_listing_provenance": self.primary_listing_provenance,
            "symbol_presence_and_determinism": self.symbol_presence_and_determinism,
            "lifecycle_evidence_gate": self.lifecycle_evidence_gate,
            "duplicate_symbol_behavior_and_resolution": self.duplicate_symbol_behavior_and_resolution,
            "repeatability": self.repeatability,
            "hashability": self.hashability,
            "no_present_day_reconstruction_gate": self.no_present_day_reconstruction_gate,
            "historical_2022_entitlement_under_current_plan": self.historical_2022_entitlement_under_current_plan,
            "feasible_for_all_48_monthly_pit_snapshots": self.feasible_for_all_48_monthly_pit_snapshots,
            "feasible_for_all_probe_monthly_pit_snapshots": self.feasible_for_all_probe_monthly_pit_snapshots,
            "all_mandatory_gates_passed": self.all_mandatory_gates_passed,
            "not_required_gates": list(self.not_required_gates),
            "blockers": list(self.blockers),
            "limitations": list(self.limitations),
            "recommended_next_assignment": self.recommended_next_assignment,
            "production_behavior_changed": self.production_behavior_changed,
            "candidate_dispositions": [d.to_dict() for d in self.candidate_dispositions],
            "ran_at": self.ran_at,
        }


def hash_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 of bytes."""
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    """Return lowercase hex SHA-256 of normalized text."""
    return hash_bytes(text.encode("utf-8"))


def json_hash(obj: Any) -> str:
    """Deterministic SHA-256 hash of a JSON-serializable object."""
    encoded = json.dumps(obj, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hash_bytes(encoded)


def now_utc_iso() -> str:
    """Current UTC time as ISO string with microseconds."""
    return datetime.now(UTC).isoformat(timespec="microseconds")
