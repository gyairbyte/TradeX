"""Typed dataclasses for INTRA-001B reference-provider probe."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


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
class ProviderCandidateResult:
    """Aggregated probe results for one reference provider."""

    provider: str
    target_entitlement: str
    probe_version: int
    observations: tuple[PITObservation, ...]
    capability_rows: tuple[CapabilityEvidence, ...]
    security_type_counts: dict[str, int] = field(default_factory=dict)
    exchange_counts: dict[str, int] = field(default_factory=dict)
    primary_exchange_field: str | None = None
    security_type_field: str | None = None
    delisting_date_field: str | None = None
    listing_date_field: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "target_entitlement": self.target_entitlement,
            "probe_version": self.probe_version,
            "observations": [o.to_dict() for o in self.observations],
            "capability_rows": [r.to_dict() for r in self.capability_rows],
            "security_type_counts": dict(sorted(self.security_type_counts.items())),
            "exchange_counts": dict(sorted(self.exchange_counts.items())),
            "primary_exchange_field": self.primary_exchange_field,
            "security_type_field": self.security_type_field,
            "delisting_date_field": self.delisting_date_field,
            "listing_date_field": self.listing_date_field,
            "error": self.error,
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
    target_entitlement: str | None = None
    pit_dates: tuple[str, ...] = ()
    pit_date_support: bool = False
    active_delisted_coverage: bool = False
    security_type_exclusions_possible: bool = False
    security_type_taxonomy_granular: bool = False
    primary_exchange_provenance: bool = False
    reproducible: bool = False
    free_under_current_entitlement: bool = False
    no_paid_upgrade: bool = True
    no_silent_fallback: bool = True
    full_repeatability_passed: bool = False
    no_composite_reference_stack: bool = True
    v1_pre_registration_commit: str | None = None
    final_head: str | None = None
    branch: str | None = None
    candidate_dispositions: tuple[tuple[str, str], ...] = ()
    fallback_probe_dates: tuple[str, ...] = ()
    dataset_used: str | None = None
    ran_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="microseconds"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_version": self.probe_version,
            "task_id": self.task_id,
            "provider": self.provider,
            "outcome": self.outcome,
            "approved_as_reference_provider": self.approved_as_reference_provider,
            "reason": self.reason,
            "candidate_order": list(self.candidate_order),
            "target_entitlement": self.target_entitlement,
            "pit_dates": list(self.pit_dates),
            "pit_date_support": self.pit_date_support,
            "active_delisted_coverage": self.active_delisted_coverage,
            "security_type_exclusions_possible": self.security_type_exclusions_possible,
            "security_type_taxonomy_granular": self.security_type_taxonomy_granular,
            "primary_exchange_provenance": self.primary_exchange_provenance,
            "reproducible": self.reproducible,
            "free_under_current_entitlement": self.free_under_current_entitlement,
            "no_paid_upgrade": self.no_paid_upgrade,
            "no_silent_fallback": self.no_silent_fallback,
            "full_repeatability_passed": self.full_repeatability_passed,
            "no_composite_reference_stack": self.no_composite_reference_stack,
            "v1_pre_registration_commit": self.v1_pre_registration_commit,
            "final_head": self.final_head,
            "branch": self.branch,
            "candidate_dispositions": [list(t) for t in self.candidate_dispositions],
            "fallback_probe_dates": list(self.fallback_probe_dates),
            "dataset_used": self.dataset_used,
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
