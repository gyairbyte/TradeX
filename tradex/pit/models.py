"""Domain models and contracts for point-in-time capture (MVP-ARCH-001-R7-PIT-001A).

Defines immutable capture contracts, enums, canonical fact payload serialization,
SHA-256 hashing, symbol universe normalization, and request fingerprinting.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

PIT_CAPTURE_CONTRACT_VERSION: int = 1


class CaptureSlot(str, Enum):
    """Canonical observation slot in America/New_York."""

    EVENING = "evening"  # 20:30 America/New_York (8:30 PM)
    MORNING = "morning"  # 09:00 America/New_York (9:00 AM)


class CaptureKind(str, Enum):
    """Point-in-time capture domain kind."""

    EARNINGS = "earnings"


class CaptureRunStatus(str, Enum):
    """Lifecycle state of a capture run."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class ObservationStatus(str, Enum):
    """Point-in-time observation outcome for a single symbol."""

    KNOWN = "known"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


def serialize_canonical_fact_json(payload: dict[str, Any]) -> str:
    """Serialize a fact payload dictionary to deterministic canonical JSON string."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def compute_fact_hash(fact_json: str) -> str:
    """Compute SHA-256 hex digest of the UTF-8 encoded canonical fact JSON."""
    return hashlib.sha256(fact_json.encode("utf-8")).hexdigest()


def build_known_fact_payload(next_earnings_date: date) -> dict[str, Any]:
    """Build normalized canonical fact payload for a known earnings observation."""
    return {"next_earnings_date": next_earnings_date.isoformat()}


def build_unavailable_fact_payload(
    error_category: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Build normalized canonical fact payload for an unavailable or error observation."""
    return {
        "error_category": error_category,
        "error_message": error_message,
        "next_earnings_date": None,
    }


def normalize_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    """Normalize, deduplicate, and sort a symbol universe.

    Raises:
        TypeError: If symbols is not a sequence of strings.
        ValueError: If any symbol is blank or the final normalized universe is empty.
    """
    if not isinstance(symbols, Sequence) or isinstance(symbols, (str, bytes)):
        raise TypeError("symbols must be a sequence of strings")

    normalized_set: set[str] = set()
    for s in symbols:
        if not isinstance(s, str):
            raise TypeError(f"Symbol item {s!r} must be a str")
        cleaned = s.strip().upper()
        if not cleaned:
            raise ValueError("Blank or whitespace-only symbols are not allowed")
        normalized_set.add(cleaned)

    if not normalized_set:
        raise ValueError("Normalized symbol universe cannot be empty")

    return tuple(sorted(normalized_set))


def compute_universe_hash(normalized_symbols: Sequence[str]) -> str:
    """Compute SHA-256 hash of the normalized sorted symbol universe."""
    payload = ",".join(normalized_symbols)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_request_fingerprint(
    *,
    contract_version: int,
    capture_kind: str,
    capture_slot: str,
    capture_date: str,
    scheduled_for_iso: str,
    requested_provider: str,
    normalized_symbols: Sequence[str],
) -> str:
    """Compute SHA-256 request fingerprint from canonical JSON representation."""
    canonical_dict = {
        "capture_date": capture_date,
        "capture_kind": capture_kind,
        "capture_slot": capture_slot,
        "contract_version": contract_version,
        "requested_provider": requested_provider,
        "scheduled_for": scheduled_for_iso,
        "symbols": list(normalized_symbols),
    }
    raw_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


def compute_default_idempotency_key(
    capture_date: str,
    slot: CaptureSlot,
    request_fingerprint: str,
) -> str:
    """Derive deterministic default idempotency key from slot date and request fingerprint."""
    return f"pit-earnings-{capture_date}-{slot.value}-{request_fingerprint[:16]}"


def _normalize_aware_utc(dt: datetime, field_name: str) -> datetime:
    """Ensure datetime is timezone-aware and convert to UTC."""
    if not isinstance(dt, datetime):
        raise TypeError(f"{field_name} must be a datetime instance")
    if dt.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware; naive datetimes are rejected")
    return dt.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class PITEarningsSnapshot:
    """Immutable point-in-time earnings observation for a single symbol."""

    snapshot_id: str
    capture_run_id: str
    symbol: str
    observation_status: ObservationStatus
    next_earnings_date: date | None
    provider: str
    provider_observed_at: datetime | None
    request_started_at: datetime
    response_received_at: datetime
    fact_hash: str
    fact_json: str
    error_category: str | None
    error_message: str | None
    created_at: datetime
    contract_version: int = PIT_CAPTURE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != PIT_CAPTURE_CONTRACT_VERSION:
            raise ValueError(
                f"Invalid contract_version {self.contract_version}; must be {PIT_CAPTURE_CONTRACT_VERSION}"
            )
        if not self.snapshot_id or not isinstance(self.snapshot_id, str):
            raise ValueError("snapshot_id must be a non-empty string")
        if not self.capture_run_id or not isinstance(self.capture_run_id, str):
            raise ValueError("capture_run_id must be a non-empty string")

        cleaned_symbol = self.symbol.strip().upper() if isinstance(self.symbol, str) else ""
        if not cleaned_symbol or cleaned_symbol != self.symbol:
            raise ValueError(f"symbol must be non-empty and uppercase, got {self.symbol!r}")

        if not isinstance(self.observation_status, ObservationStatus):
            raise TypeError(f"Invalid observation_status: {self.observation_status!r}")

        if self.observation_status == ObservationStatus.KNOWN:
            if self.next_earnings_date is None or not isinstance(self.next_earnings_date, date):
                raise ValueError("next_earnings_date is required when observation_status is 'known'")
        else:
            if self.next_earnings_date is not None:
                raise ValueError(
                    f"next_earnings_date must be None when observation_status is '{self.observation_status.value}'"
                )

        if not self.provider or not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("provider must be a non-empty string")

        started = _normalize_aware_utc(self.request_started_at, "request_started_at")
        received = _normalize_aware_utc(self.response_received_at, "response_received_at")
        if started > received:
            raise ValueError("request_started_at must be <= response_received_at")

        created = _normalize_aware_utc(self.created_at, "created_at")

        object.__setattr__(self, "request_started_at", started)
        object.__setattr__(self, "response_received_at", received)
        object.__setattr__(self, "created_at", created)

        if self.provider_observed_at is not None:
            prov_obs = _normalize_aware_utc(self.provider_observed_at, "provider_observed_at")
            object.__setattr__(self, "provider_observed_at", prov_obs)

        if not self.fact_json or not isinstance(self.fact_json, str):
            raise ValueError("fact_json must be a non-empty string")

        expected_hash = compute_fact_hash(self.fact_json)
        if self.fact_hash != expected_hash:
            raise ValueError(
                f"fact_hash {self.fact_hash!r} does not match SHA-256 of fact_json {expected_hash!r}"
            )


@dataclass(frozen=True, slots=True)
class PITCaptureRun:
    """Immutable point-in-time capture run record."""

    capture_run_id: str
    idempotency_key: str
    request_fingerprint: str
    capture_kind: CaptureKind
    capture_slot: CaptureSlot
    capture_date: date
    scheduled_for: datetime
    requested_at: datetime
    completed_at: datetime | None
    requested_provider: str
    universe_hash: str
    requested_n: int
    known_n: int = 0
    unavailable_n: int = 0
    error_n: int = 0
    status: CaptureRunStatus = CaptureRunStatus.STARTED
    created_at: datetime = datetime(1970, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(1970, 1, 1, tzinfo=UTC)
    contract_version: int = PIT_CAPTURE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != PIT_CAPTURE_CONTRACT_VERSION:
            raise ValueError(
                f"Invalid contract_version {self.contract_version}; must be {PIT_CAPTURE_CONTRACT_VERSION}"
            )
        if not self.capture_run_id or not isinstance(self.capture_run_id, str):
            raise ValueError("capture_run_id must be a non-empty string")
        if not self.idempotency_key or not isinstance(self.idempotency_key, str):
            raise ValueError("idempotency_key must be a non-empty string")
        if not self.request_fingerprint or not isinstance(self.request_fingerprint, str):
            raise ValueError("request_fingerprint must be a non-empty string")

        if not isinstance(self.capture_kind, CaptureKind):
            raise TypeError(f"Invalid capture_kind: {self.capture_kind!r}")
        if not isinstance(self.capture_slot, CaptureSlot):
            raise TypeError(f"Invalid capture_slot: {self.capture_slot!r}")
        if not isinstance(self.capture_date, date):
            raise TypeError(f"capture_date must be a date instance, got {type(self.capture_date)}")
        if not isinstance(self.status, CaptureRunStatus):
            raise TypeError(f"Invalid status: {self.status!r}")

        sched = _normalize_aware_utc(self.scheduled_for, "scheduled_for")
        req_at = _normalize_aware_utc(self.requested_at, "requested_at")
        created = _normalize_aware_utc(self.created_at, "created_at")
        updated = _normalize_aware_utc(self.updated_at, "updated_at")

        object.__setattr__(self, "scheduled_for", sched)
        object.__setattr__(self, "requested_at", req_at)
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)

        if not self.requested_provider or not isinstance(self.requested_provider, str):
            raise ValueError("requested_provider must be a non-empty string")
        if not self.universe_hash or not isinstance(self.universe_hash, str):
            raise ValueError("universe_hash must be a non-empty string")

        if self.requested_n < 1:
            raise ValueError(f"requested_n must be >= 1, got {self.requested_n}")
        if self.known_n < 0 or self.unavailable_n < 0 or self.error_n < 0:
            raise ValueError("counts must be non-negative")

        if self.status != CaptureRunStatus.STARTED:
            if self.completed_at is None:
                raise ValueError("completed_at is required for terminal capture run statuses")
            comp = _normalize_aware_utc(self.completed_at, "completed_at")
            object.__setattr__(self, "completed_at", comp)
            total_resolved = self.known_n + self.unavailable_n + self.error_n
            if total_resolved != self.requested_n:
                raise ValueError(
                    f"Count mismatch: requested_n ({self.requested_n}) != known_n ({self.known_n}) + "
                    f"unavailable_n ({self.unavailable_n}) + error_n ({self.error_n}) = {total_resolved}"
                )
        elif self.completed_at is not None:
            comp = _normalize_aware_utc(self.completed_at, "completed_at")
            object.__setattr__(self, "completed_at", comp)


@dataclass(frozen=True, slots=True)
class PITCaptureResult:
    """Read-model result of a completed or replayed capture run."""

    run: PITCaptureRun
    snapshots: tuple[PITEarningsSnapshot, ...]
