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

PIT_CAPTURE_CONTRACT_VERSION: int = 2
# Currently active production capture-write contract pinned to v1 until authorized PR B.
PIT_CAPTURE_WRITE_CONTRACT_VERSION: int = 1


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
    NOT_APPLICABLE = "not_applicable"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class ReferenceObservationStatus(str, Enum):
    """Point-in-time security/reference observation outcome for a single symbol."""

    KNOWN = "known"
    UNAVAILABLE = "unavailable"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


class PITEvidenceCompletenessTier(str, Enum):
    """Categorical evidence completeness tier."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    SPARSE = "sparse"


@dataclass(frozen=True, slots=True)
class PITFamilyCompleteness:
    """Read model representing evidence completeness for one capture family."""

    tier: PITEvidenceCompletenessTier
    ratio: float
    pct: float
    applicable_n: int
    known_n: int
    all_not_applicable: bool

    def __post_init__(self) -> None:
        if self.applicable_n < 0:
            raise ValueError(f"applicable_n must be >= 0, got {self.applicable_n}")
        if not (0 <= self.known_n <= self.applicable_n):
            raise ValueError(
                f"known_n must satisfy 0 <= known_n <= applicable_n, "
                f"got known_n={self.known_n} vs applicable_n={self.applicable_n}"
            )


@dataclass(frozen=True, slots=True)
class PITSlotCompleteness:
    """Read model representing aggregated evidence completeness across the slot."""

    overall_tier: PITEvidenceCompletenessTier
    pooled_ratio: float
    pooled_pct: float
    total_applicable_n: int
    total_known_n: int


REFERENCE_CONTRACT_FIELDS: tuple[str, ...] = (
    "active",
    "cik",
    "composite_figi",
    "delisted_utc",
    "last_updated_utc",
    "locale",
    "market",
    "name",
    "primary_exchange",
    "share_class_figi",
    "ticker",
    "type",
)


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


def build_not_applicable_earnings_fact_payload() -> dict[str, Any]:
    """Build normalized canonical fact payload for a manifest-origin not_applicable earnings observation."""
    return {
        "applicability_source": "manifest",
        "error_category": None,
        "error_message": None,
        "next_earnings_date": None,
        "status_reason": "manifest_not_applicable",
    }


def build_known_reference_fact_payload(
    *,
    active: bool | None,
    cik: str | None,
    composite_figi: str | None,
    delisted_utc: str | None,
    last_updated_utc: str | None,
    locale: str | None,
    market: str | None,
    name: str | None,
    primary_exchange: str | None,
    share_class_figi: str | None,
    ticker: str,
    type_code: str | None,
) -> dict[str, Any]:
    """Build normalized canonical fact payload for a known security/reference observation."""
    return {
        "active": active,
        "cik": cik,
        "composite_figi": composite_figi,
        "delisted_utc": delisted_utc,
        "last_updated_utc": last_updated_utc,
        "locale": locale,
        "market": market,
        "name": name,
        "primary_exchange": primary_exchange,
        "share_class_figi": share_class_figi,
        "ticker": ticker,
        "type_code": type_code,
    }


def build_unavailable_reference_fact_payload(
    *,
    ticker: str,
    error_category: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Build normalized canonical fact payload for an unavailable reference observation."""
    return {
        "error_category": error_category,
        "error_message": error_message,
        "ticker": ticker,
    }


def _parse_iso_utc(ts_str: str | None) -> datetime | None:
    """Parse ISO8601 provider timestamp and normalize to UTC if timezone-aware.

    Returns None if absent, malformed, or naive (naive timestamps MUST NOT be assumed UTC).
    """
    if not ts_str or not isinstance(ts_str, str):
        return None
    cleaned = ts_str.strip()
    if not cleaned:
        return None
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            # Naive timestamp - MUST NOT be interpreted as UTC
            return None
        return dt.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        return None


def normalize_reference_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Extract and validate only approved reference contract fields for a candidate record."""
    if not isinstance(candidate, dict):
        raise TypeError(f"Candidate item must be a dict, got {type(candidate).__name__}")

    # Validate active
    active = candidate.get("active")
    if active is not None and not isinstance(active, bool):
        raise TypeError(f"Candidate active must be bool or None, got {type(active).__name__}")

    # Validate type
    type_val = candidate.get("type")
    if type_val is not None and not isinstance(type_val, str):
        raise TypeError(f"Candidate type must be str or None, got {type(type_val).__name__}")

    # Validate ticker
    ticker = candidate.get("ticker")
    if ticker is not None and not isinstance(ticker, str):
        raise TypeError(f"Candidate ticker must be str or None, got {type(ticker).__name__}")

    # Validate other textual fields
    str_fields = (
        "cik",
        "composite_figi",
        "delisted_utc",
        "last_updated_utc",
        "locale",
        "market",
        "name",
        "primary_exchange",
        "share_class_figi",
    )
    extracted_text: dict[str, str | None] = {}
    for f in str_fields:
        val = candidate.get(f)
        if val is not None and not isinstance(val, str):
            raise TypeError(f"Candidate field {f} must be str or None, got {type(val).__name__}")
        extracted_text[f] = val

    # For last_updated_utc, if not valid ISO with timezone, normalize to ISO or None
    last_upd = extracted_text["last_updated_utc"]
    if last_upd is not None:
        parsed_dt = _parse_iso_utc(last_upd)
        last_upd_iso = parsed_dt.isoformat() if parsed_dt is not None else None
    else:
        last_upd_iso = None

    return {
        "active": active,
        "cik": extracted_text["cik"],
        "composite_figi": extracted_text["composite_figi"],
        "delisted_utc": extracted_text["delisted_utc"],
        "last_updated_utc": last_upd_iso,
        "locale": extracted_text["locale"],
        "market": extracted_text["market"],
        "name": extracted_text["name"],
        "primary_exchange": extracted_text["primary_exchange"],
        "share_class_figi": extracted_text["share_class_figi"],
        "ticker": ticker or "",
        "type_code": type_val,
    }


def build_ambiguous_reference_fact_payload(
    *,
    ticker: str,
    candidates: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Build normalized canonical fact payload for an ambiguous reference observation."""
    normalized_candidates = [normalize_reference_candidate(c) for c in candidates]
    sorted_candidates = sorted(
        normalized_candidates,
        key=lambda c: (
            c.get("ticker") or "",
            c.get("name") or "",
            c.get("primary_exchange") or "",
            c.get("composite_figi") or "",
            c.get("cik") or "",
            c.get("share_class_figi") or "",
        ),
    )
    return {
        "candidates": list(sorted_candidates),
        "ticker": ticker,
    }


def build_error_reference_fact_payload(
    *,
    ticker: str,
    error_category: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Build normalized canonical fact payload for an error reference observation."""
    return {
        "error_category": error_category,
        "error_message": error_message,
        "ticker": ticker,
    }


def audit_missing_reference_fields(provider_data: dict[str, Any]) -> tuple[str, ...]:
    """Audit provider fact fields and return tuple of missing field names deterministically sorted."""
    missing: list[str] = []
    for field_name in sorted(REFERENCE_CONTRACT_FIELDS):
        val = provider_data.get(field_name)
        if (
            val is None
            or (isinstance(val, str) and not val.strip())
            or (field_name == "last_updated_utc" and _parse_iso_utc(val) is None)
        ):
            missing.append(field_name)
    return tuple(missing)


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
    manifest_hash: str | None = None,
) -> str:
    """Compute SHA-256 request fingerprint from canonical JSON representation."""
    if contract_version == 1:
        if manifest_hash is not None:
            raise ValueError("manifest_hash must be None for contract_version=1")
        canonical_dict: dict[str, Any] = {
            "capture_date": capture_date,
            "capture_kind": capture_kind,
            "capture_slot": capture_slot,
            "contract_version": 1,
            "requested_provider": requested_provider,
            "scheduled_for": scheduled_for_iso,
            "symbols": list(normalized_symbols),
        }
    elif contract_version == 2:
        if not manifest_hash or not isinstance(manifest_hash, str) or not manifest_hash.strip():
            raise ValueError("manifest_hash is required and must be non-empty for contract_version=2")
        canonical_dict = {
            "capture_date": capture_date,
            "capture_kind": capture_kind,
            "capture_slot": capture_slot,
            "contract_version": 2,
            "manifest_hash": manifest_hash.strip(),
            "requested_provider": requested_provider,
            "scheduled_for": scheduled_for_iso,
            "symbols": list(normalized_symbols),
        }
    else:
        raise ValueError(f"Unsupported contract_version {contract_version}; expected 1 or 2")

    raw_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


def compute_default_idempotency_key(
    capture_date: str,
    slot: CaptureSlot,
    request_fingerprint: str,
) -> str:
    """Derive deterministic default idempotency key for earnings capture."""
    return f"pit-earnings-{capture_date}-{slot.value}-{request_fingerprint[:16]}"


def compute_reference_default_idempotency_key(
    capture_date: str,
    slot: CaptureSlot,
    request_fingerprint: str,
) -> str:
    """Derive deterministic default idempotency key for reference capture."""
    return f"pit-reference-{capture_date}-{slot.value}-{request_fingerprint[:16]}"


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
    provider: str | None
    provider_observed_at: datetime | None
    request_started_at: datetime | None
    response_received_at: datetime | None
    fact_hash: str
    fact_json: str
    error_category: str | None
    error_message: str | None
    created_at: datetime
    observation_origin: str = "provider"
    applicability_source: str | None = None
    provider_call_attempted: bool = True
    contract_version: int = PIT_CAPTURE_WRITE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version not in (1, 2):
            raise ValueError(
                f"Invalid contract_version {self.contract_version}; must be 1 or 2"
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

        if not self.fact_json or not isinstance(self.fact_json, str):
            raise ValueError("fact_json must be a non-empty string")

        expected_hash = compute_fact_hash(self.fact_json)
        if self.fact_hash != expected_hash:
            raise ValueError(
                f"fact_hash {self.fact_hash!r} does not match SHA-256 of fact_json {expected_hash!r}"
            )

        created = _normalize_aware_utc(self.created_at, "created_at")
        object.__setattr__(self, "created_at", created)

        if self.contract_version == 1:
            if self.observation_status == ObservationStatus.NOT_APPLICABLE:
                raise ValueError("NOT_APPLICABLE observation_status is forbidden in contract_version=1")
            if self.observation_origin != "provider":
                raise ValueError(f"observation_origin must be 'provider' for contract_version=1, got {self.observation_origin!r}")
            if self.applicability_source is not None:
                raise ValueError("applicability_source must be None for contract_version=1")
            if not self.provider_call_attempted:
                raise ValueError("provider_call_attempted must be True for contract_version=1")
            if not self.provider or not isinstance(self.provider, str) or not self.provider.strip():
                raise ValueError("provider must be a non-empty string for contract_version=1")
            if self.request_started_at is None or self.response_received_at is None:
                raise ValueError("request_started_at and response_received_at are required for contract_version=1")
            started = _normalize_aware_utc(self.request_started_at, "request_started_at")
            received = _normalize_aware_utc(self.response_received_at, "response_received_at")
            if started > received:
                raise ValueError("request_started_at must be <= response_received_at")
            object.__setattr__(self, "request_started_at", started)
            object.__setattr__(self, "response_received_at", received)
            if self.provider_observed_at is not None:
                prov_obs = _normalize_aware_utc(self.provider_observed_at, "provider_observed_at")
                object.__setattr__(self, "provider_observed_at", prov_obs)

        elif self.contract_version == 2:
            if self.observation_origin not in ("provider", "manifest"):
                raise ValueError(f"observation_origin must be 'provider' or 'manifest', got {self.observation_origin!r}")

            if self.observation_origin == "manifest":
                if self.observation_status != ObservationStatus.NOT_APPLICABLE:
                    raise ValueError(f"manifest origin requires observation_status 'not_applicable', got {self.observation_status.value!r}")
                if self.applicability_source != "manifest":
                    raise ValueError(f"manifest origin requires applicability_source 'manifest', got {self.applicability_source!r}")
                if self.provider_call_attempted:
                    raise ValueError("provider_call_attempted must be False for manifest-origin observation")
                if self.provider is not None:
                    raise ValueError("provider must be None for manifest-origin observation")
                if self.provider_observed_at is not None:
                    raise ValueError("provider_observed_at must be None for manifest-origin observation")
                if self.request_started_at is not None:
                    raise ValueError("request_started_at must be None for manifest-origin observation")
                if self.response_received_at is not None:
                    raise ValueError("response_received_at must be None for manifest-origin observation")
                if self.next_earnings_date is not None:
                    raise ValueError("next_earnings_date must be None for manifest-origin observation")
                if self.error_category is not None or self.error_message is not None:
                    raise ValueError("error fields must be None for manifest-origin observation")
                canonical_na_json = serialize_canonical_fact_json(build_not_applicable_earnings_fact_payload())
                if self.fact_json != canonical_na_json:
                    raise ValueError(
                        f"fact_json does not match canonical not_applicable payload: {self.fact_json!r} != {canonical_na_json!r}"
                    )

            elif self.observation_origin == "provider":
                if self.observation_status == ObservationStatus.NOT_APPLICABLE:
                    raise ValueError("provider origin cannot have observation_status 'not_applicable'")
                if self.applicability_source is not None:
                    raise ValueError("applicability_source must be None for provider-origin observation")
                if not self.provider_call_attempted:
                    raise ValueError("provider_call_attempted must be True for provider-origin observation")
                if not self.provider or not isinstance(self.provider, str) or not self.provider.strip():
                    raise ValueError("provider must be a non-empty string for provider-origin observation")
                if self.request_started_at is None or self.response_received_at is None:
                    raise ValueError("request_started_at and response_received_at are required for provider-origin observation")
                started = _normalize_aware_utc(self.request_started_at, "request_started_at")
                received = _normalize_aware_utc(self.response_received_at, "response_received_at")
                if started > received:
                    raise ValueError("request_started_at must be <= response_received_at")
                object.__setattr__(self, "request_started_at", started)
                object.__setattr__(self, "response_received_at", received)
                if self.provider_observed_at is not None:
                    prov_obs = _normalize_aware_utc(self.provider_observed_at, "provider_observed_at")
                    object.__setattr__(self, "provider_observed_at", prov_obs)


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
    contract_version: int = PIT_CAPTURE_WRITE_CONTRACT_VERSION
    manifest_hash: str | None = None
    not_applicable_n: int = 0

    def __post_init__(self) -> None:
        if self.contract_version not in (1, 2):
            raise ValueError(
                f"Invalid contract_version {self.contract_version}; must be 1 or 2"
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
        if self.known_n < 0 or self.unavailable_n < 0 or self.error_n < 0 or self.not_applicable_n < 0:
            raise ValueError("counts must be non-negative")

        if self.contract_version == 1:
            if self.manifest_hash is not None:
                raise ValueError("manifest_hash must be None for contract_version=1")
            if self.not_applicable_n != 0:
                raise ValueError("not_applicable_n must be 0 for contract_version=1")
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

        elif self.contract_version == 2:
            if not self.manifest_hash or not isinstance(self.manifest_hash, str) or not self.manifest_hash.strip():
                raise ValueError("manifest_hash is required and must be non-empty for contract_version=2")
            if self.status != CaptureRunStatus.STARTED:
                if self.completed_at is None:
                    raise ValueError("completed_at is required for terminal capture run statuses")
                comp = _normalize_aware_utc(self.completed_at, "completed_at")
                object.__setattr__(self, "completed_at", comp)
                total_resolved = self.known_n + self.not_applicable_n + self.unavailable_n + self.error_n
                if total_resolved != self.requested_n:
                    raise ValueError(
                        f"Count mismatch: requested_n ({self.requested_n}) != known_n ({self.known_n}) + "
                        f"not_applicable_n ({self.not_applicable_n}) + unavailable_n ({self.unavailable_n}) + "
                        f"error_n ({self.error_n}) = {total_resolved}"
                    )
            elif self.completed_at is not None:
                comp = _normalize_aware_utc(self.completed_at, "completed_at")
                object.__setattr__(self, "completed_at", comp)


@dataclass(frozen=True, slots=True)
class PITCaptureResult:
    """Read-model result of a completed or replayed capture run."""

    run: PITCaptureRun
    snapshots: tuple[PITEarningsSnapshot, ...]


@dataclass(frozen=True, slots=True)
class PITReferenceSnapshot:
    """Immutable point-in-time security/reference observation for a single symbol."""

    snapshot_id: str
    capture_run_id: str
    symbol: str
    observation_status: ReferenceObservationStatus
    provider: str
    provider_query_date: date
    provider_request_ids: tuple[str, ...]
    provider_ticker: str | None
    provider_name: str | None
    provider_market: str | None
    provider_locale: str | None
    provider_active: bool | None
    provider_type_code: str | None
    provider_primary_exchange: str | None
    provider_cik: str | None
    provider_composite_figi: str | None
    provider_share_class_figi: str | None
    provider_last_updated_at: datetime | None
    provider_delisted_at: str | None
    missing_fields: tuple[str, ...]
    request_started_at: datetime
    response_received_at: datetime
    fact_hash: str
    fact_json: str
    error_category: str | None
    error_message: str | None
    created_at: datetime
    contract_version: int = PIT_CAPTURE_WRITE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version not in (1, 2):
            raise ValueError(
                f"Invalid contract_version {self.contract_version}; must be 1 or 2"
            )
        if not self.snapshot_id or not isinstance(self.snapshot_id, str):
            raise ValueError("snapshot_id must be a non-empty string")
        if not self.capture_run_id or not isinstance(self.capture_run_id, str):
            raise ValueError("capture_run_id must be a non-empty string")

        cleaned_symbol = self.symbol.strip().upper() if isinstance(self.symbol, str) else ""
        if not cleaned_symbol or cleaned_symbol != self.symbol:
            raise ValueError(f"symbol must be non-empty and uppercase, got {self.symbol!r}")

        if not isinstance(self.observation_status, ReferenceObservationStatus):
            raise TypeError(f"Invalid observation_status: {self.observation_status!r}")

        if not self.provider or not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("provider must be a non-empty string")

        if not isinstance(self.provider_query_date, date):
            raise TypeError(f"provider_query_date must be a date instance, got {type(self.provider_query_date)}")

        if not isinstance(self.provider_request_ids, tuple):
            object.__setattr__(self, "provider_request_ids", tuple(self.provider_request_ids))
        for rid in self.provider_request_ids:
            if not isinstance(rid, str):
                raise TypeError(f"provider_request_ids elements must be str, got {type(rid)}")

        if not isinstance(self.missing_fields, tuple):
            object.__setattr__(self, "missing_fields", tuple(self.missing_fields))
        for mf in self.missing_fields:
            if not isinstance(mf, str):
                raise TypeError(f"missing_fields elements must be str, got {type(mf)}")

        if self.provider_active is not None and not isinstance(self.provider_active, bool):
            raise TypeError(f"provider_active must be bool or None, got {type(self.provider_active).__name__}")

        text_field_checks = {
            "provider_ticker": self.provider_ticker,
            "provider_name": self.provider_name,
            "provider_market": self.provider_market,
            "provider_locale": self.provider_locale,
            "provider_type_code": self.provider_type_code,
            "provider_primary_exchange": self.provider_primary_exchange,
            "provider_cik": self.provider_cik,
            "provider_composite_figi": self.provider_composite_figi,
            "provider_share_class_figi": self.provider_share_class_figi,
            "provider_delisted_at": self.provider_delisted_at,
            "error_category": self.error_category,
            "error_message": self.error_message,
        }
        for fname, fval in text_field_checks.items():
            if fval is not None and not isinstance(fval, str):
                raise TypeError(f"{fname} must be str or None, got {type(fval).__name__}")

        started = _normalize_aware_utc(self.request_started_at, "request_started_at")
        received = _normalize_aware_utc(self.response_received_at, "response_received_at")
        if started > received:
            raise ValueError("request_started_at must be <= response_received_at")

        created = _normalize_aware_utc(self.created_at, "created_at")

        object.__setattr__(self, "request_started_at", started)
        object.__setattr__(self, "response_received_at", received)
        object.__setattr__(self, "created_at", created)

        if self.provider_last_updated_at is not None:
            last_upd = _normalize_aware_utc(self.provider_last_updated_at, "provider_last_updated_at")
            object.__setattr__(self, "provider_last_updated_at", last_upd)

        if not self.fact_json or not isinstance(self.fact_json, str):
            raise ValueError("fact_json must be a non-empty string")

        expected_hash = compute_fact_hash(self.fact_json)
        if self.fact_hash != expected_hash:
            raise ValueError(
                f"fact_hash {self.fact_hash!r} does not match SHA-256 of fact_json {expected_hash!r}"
            )


@dataclass(frozen=True, slots=True)
class PITReferenceCaptureRun:
    """Immutable point-in-time reference capture run record."""

    capture_run_id: str
    idempotency_key: str
    request_fingerprint: str
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
    ambiguous_n: int = 0
    error_n: int = 0
    status: CaptureRunStatus = CaptureRunStatus.STARTED
    created_at: datetime = datetime(1970, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(1970, 1, 1, tzinfo=UTC)
    contract_version: int = PIT_CAPTURE_WRITE_CONTRACT_VERSION
    manifest_hash: str | None = None

    def __post_init__(self) -> None:
        if self.contract_version not in (1, 2):
            raise ValueError(
                f"Invalid contract_version {self.contract_version}; must be 1 or 2"
            )
        if not self.capture_run_id or not isinstance(self.capture_run_id, str):
            raise ValueError("capture_run_id must be a non-empty string")
        if not self.idempotency_key or not isinstance(self.idempotency_key, str):
            raise ValueError("idempotency_key must be a non-empty string")
        if not self.request_fingerprint or not isinstance(self.request_fingerprint, str):
            raise ValueError("request_fingerprint must be a non-empty string")

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
        if (
            self.known_n < 0
            or self.unavailable_n < 0
            or self.ambiguous_n < 0
            or self.error_n < 0
        ):
            raise ValueError("counts must be non-negative")

        if self.contract_version == 1 and self.manifest_hash is not None:
            raise ValueError("manifest_hash must be None for contract_version=1")
        elif self.contract_version == 2 and (
            not self.manifest_hash or not isinstance(self.manifest_hash, str) or not self.manifest_hash.strip()
        ):
            raise ValueError("manifest_hash is required and must be non-empty for contract_version=2")

        if self.status != CaptureRunStatus.STARTED:
            if self.completed_at is None:
                raise ValueError("completed_at is required for terminal capture run statuses")
            comp = _normalize_aware_utc(self.completed_at, "completed_at")
            object.__setattr__(self, "completed_at", comp)
            total_resolved = self.known_n + self.unavailable_n + self.ambiguous_n + self.error_n
            if total_resolved != self.requested_n:
                raise ValueError(
                    f"Count mismatch: requested_n ({self.requested_n}) != known_n ({self.known_n}) + "
                    f"unavailable_n ({self.unavailable_n}) + ambiguous_n ({self.ambiguous_n}) + "
                    f"error_n ({self.error_n}) = {total_resolved}"
                )
        elif self.completed_at is not None:
            comp = _normalize_aware_utc(self.completed_at, "completed_at")
            object.__setattr__(self, "completed_at", comp)


@dataclass(frozen=True, slots=True)
class PITReferenceCaptureResult:
    """Read-model result of a completed or replayed reference capture run."""

    run: PITReferenceCaptureRun
    snapshots: tuple[PITReferenceSnapshot, ...]
