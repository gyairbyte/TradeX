"""Candidate snapshot domain models and typed taxonomies for MVP-ARCH-001-R5A.

Defines the immutable point-in-time CandidateSnapshot domain, evaluator envelopes,
structured evidence/provenance, explainability reasons, typed missing-data records,
and the aggregate CandidateDossier container.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypeVar

from tradex.market.hours import is_trading_day, normalize_market_datetime


class CandidateDimension(StrEnum):
    """Architectural dimensions for candidate evaluation."""

    ELIGIBILITY = "eligibility"
    SETUP_QUALITY = "setup_quality"
    MOVE_POTENTIAL = "move_potential"
    ENTRY_READINESS = "entry_readiness"
    CONTEXT = "context"
    DOWNSIDE_RISK = "downside_risk"
    DATA_CONFIDENCE = "data_confidence"


class ReasonPolarity(StrEnum):
    """Explainability polarity emitted by an evaluator."""

    SUPPORTING = "supporting"
    BLOCKING = "blocking"
    NEUTRAL = "neutral"


class ReasonSeverity(StrEnum):
    """Explainability severity emitted by an evaluator."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class MissingDataStatus(StrEnum):
    """Explicit point-in-time record of unavailable or unknown inputs."""

    NOT_REQUESTED = "not_requested"
    NOT_APPLICABLE = "not_applicable"
    PROVIDER_UNSUPPORTED = "provider_unsupported"
    PROVIDER_FAILED = "provider_failed"
    STALE = "stale"
    INSUFFICIENT_HISTORY = "insufficient_history"
    OUTSIDE_WINDOW = "outside_window"
    UNKNOWN = "unknown"


class SecurityIdentityStatus(StrEnum):
    """Truthful representation of whether a prospective security identity is known."""

    KNOWN = "known"
    UNKNOWN = "unknown"


T = TypeVar("T", bound=StrEnum)


def _normalize_enum(value: object, enum_cls: type[T], field_name: str) -> T:
    """Normalize a value to an enum instance, rejecting invalid types and values."""
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a {enum_cls.__name__} instance or str, got {type(value).__name__}"
        )
    clean_val = value.strip().lower()
    if not clean_val:
        raise ValueError(f"{field_name} cannot be empty")
    for member in enum_cls:
        if member.value.lower() == clean_val or member.name.lower() == clean_val:
            return member
    valid = [m.value for m in enum_cls]
    raise ValueError(f"Unknown {enum_cls.__name__} '{value}'. Valid values are: {valid}")


def _validate_and_canonicalize_json_dict(data: object, field_name: str) -> dict[str, Any]:
    """Enforce canonical JSON-object representation for dictionary fields."""
    if isinstance(data, bool) or not isinstance(data, dict):
        raise TypeError(f"{field_name} must be a dict, got {type(data).__name__}")

    def _check_keys_and_values(obj: object) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, bool) or not isinstance(k, (str, CandidateDimension)):
                    raise TypeError(
                        f"{field_name} dictionary keys must be str or CandidateDimension, got key {k!r} of type {type(k).__name__}"
                    )
                _check_keys_and_values(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _check_keys_and_values(item)

    _check_keys_and_values(data)

    try:
        serialized = json.dumps(data, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"{field_name} must be JSON serializable without NaN/Infinity: {e}"
        ) from e

    return json.loads(serialized)


def _validate_json_serializable(data: Any) -> str:
    """Ensure data is serializable to canonical JSON without NaN or Infinity."""
    try:
        return json.dumps(data, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"Payload contains non-serializable or non-finite values (NaN/Infinity): {e}"
        ) from e


def _normalize_aware_dt(dt: datetime, field_name: str) -> datetime:
    """Validate that dt is timezone-aware and normalize to UTC."""
    if not isinstance(dt, datetime):
        raise TypeError(f"{field_name} must be a datetime instance, got {type(dt).__name__}")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{field_name} must be timezone-aware; naive datetimes are rejected")
    return dt.astimezone(UTC)


def _normalize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Symbol must be a non-empty string")
    return symbol.strip().upper()


def _validate_non_blank_str(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_trading_date_str(td: str) -> str:
    if not isinstance(td, str):
        raise TypeError(f"trading_date must be a string, got {type(td).__name__}")
    s = td.strip()
    try:
        datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as e:
        raise ValueError(f"Invalid trading_date format: '{td}'. Expected YYYY-MM-DD") from e
    return s


def derive_trading_date(decision_dt: datetime) -> str | None:
    """Derive XNYS trading date from an aware decision timestamp."""
    try:
        ny_dt = normalize_market_datetime(decision_dt)
        day = ny_dt.date()
        if is_trading_day(day):
            return day.isoformat()
    except Exception:  # noqa: BLE001
        return None
    return None


@dataclass(frozen=True)
class CandidateSnapshot:
    """Immutable point-in-time candidate snapshot header."""

    candidate_id: str
    symbol: str
    decision_timestamp: datetime
    contract_version: int = 1
    trading_date: str | None = None
    security_identity_version: str | None = None
    security_identity_status: SecurityIdentityStatus | str = SecurityIdentityStatus.UNKNOWN
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _validate_non_blank_str(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))

        if not isinstance(self.contract_version, int) or isinstance(self.contract_version, bool):
            raise TypeError(f"contract_version must be an int, got {type(self.contract_version).__name__}")
        if self.contract_version <= 0:
            raise ValueError(f"contract_version must be a positive integer, got {self.contract_version}")
        if self.contract_version != 1:
            raise ValueError(f"Unsupported candidate contract_version: {self.contract_version}. Supported: 1")

        norm_ts = _normalize_aware_dt(self.decision_timestamp, "decision_timestamp")
        object.__setattr__(self, "decision_timestamp", norm_ts)
        norm_created = _normalize_aware_dt(self.created_at, "created_at")
        object.__setattr__(self, "created_at", norm_created)

        # Validate supplied trading_date format if provided
        if self.trading_date is not None:
            td_clean = _validate_trading_date_str(self.trading_date)
            object.__setattr__(self, "trading_date", td_clean)

        # Derive or validate trading date using New York market calendar
        derived_td = derive_trading_date(norm_ts)
        if derived_td is not None:
            if self.trading_date is None:
                object.__setattr__(self, "trading_date", derived_td)
            elif self.trading_date != derived_td:
                raise ValueError(
                    f"Supplied trading_date '{self.trading_date}' does not match "
                    f"derived market trading date '{derived_td}'"
                )
        else:
            if self.trading_date is not None:
                raise ValueError(
                    f"decision_timestamp '{norm_ts.isoformat()}' falls on a non-trading day and "
                    f"cannot be assigned trading_date '{self.trading_date}'"
                )
            object.__setattr__(self, "trading_date", None)

        norm_status = _normalize_enum(self.security_identity_status, SecurityIdentityStatus, "security_identity_status")

        # Security identity consistency validation
        if self.security_identity_version is not None:
            ver = self.security_identity_version.strip()
            if not ver:
                raise ValueError("security_identity_version cannot be empty when provided")
            object.__setattr__(self, "security_identity_version", ver)
            norm_status = SecurityIdentityStatus.KNOWN
        else:
            if norm_status == SecurityIdentityStatus.KNOWN:
                raise ValueError("security_identity_status cannot be 'known' when security_identity_version is None")

        object.__setattr__(self, "security_identity_status", norm_status)


@dataclass(frozen=True)
class CandidateEvaluation:
    """Versioned evaluator envelope attached to one immutable candidate snapshot."""

    evaluation_id: str
    candidate_id: str
    evaluator_id: str
    evaluator_version: str
    evidence_state: str
    dimensions: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "evaluation_id", _validate_non_blank_str(self.evaluation_id, "evaluation_id"))
        object.__setattr__(self, "candidate_id", _validate_non_blank_str(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "evaluator_id", _validate_non_blank_str(self.evaluator_id, "evaluator_id"))
        object.__setattr__(self, "evaluator_version", _validate_non_blank_str(self.evaluator_version, "evaluator_version"))
        object.__setattr__(self, "evidence_state", _validate_non_blank_str(self.evidence_state, "evidence_state"))
        canonical_dims = _validate_and_canonicalize_json_dict(self.dimensions, "dimensions")
        object.__setattr__(self, "dimensions", canonical_dims)
        norm_created = _normalize_aware_dt(self.created_at, "created_at")
        object.__setattr__(self, "created_at", norm_created)


@dataclass(frozen=True)
class CandidateEvidence:
    """Structured evidence/provenance metadata associated with the candidate snapshot."""

    evidence_id: str
    candidate_id: str
    evidence_type: str
    source_ref_type: str | None = None
    source_ref_id: str | None = None
    provider: str | None = None
    observed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _validate_non_blank_str(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "candidate_id", _validate_non_blank_str(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "evidence_type", _validate_non_blank_str(self.evidence_type, "evidence_type"))
        if self.source_ref_type is not None:
            object.__setattr__(self, "source_ref_type", self.source_ref_type.strip() or None)
        if self.source_ref_id is not None:
            object.__setattr__(self, "source_ref_id", self.source_ref_id.strip() or None)
        if self.provider is not None:
            object.__setattr__(self, "provider", self.provider.strip() or None)
        if self.observed_at is not None:
            norm_obs = _normalize_aware_dt(self.observed_at, "observed_at")
            object.__setattr__(self, "observed_at", norm_obs)
        canonical_meta = _validate_and_canonicalize_json_dict(self.metadata, "metadata")
        object.__setattr__(self, "metadata", canonical_meta)
        norm_created = _normalize_aware_dt(self.created_at, "created_at")
        object.__setattr__(self, "created_at", norm_created)

    @property
    def data_family(self) -> str:
        return self.evidence_type


@dataclass(frozen=True)
class CandidateReason:
    """Structured explainability reason emitted by an evaluator."""

    reason_id: str
    candidate_id: str
    evaluation_id: str
    dimension: CandidateDimension | str
    reason_code: str
    human_text: str
    polarity: ReasonPolarity | str = ReasonPolarity.NEUTRAL
    severity: ReasonSeverity | str = ReasonSeverity.INFO
    source_evidence_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_id", _validate_non_blank_str(self.reason_id, "reason_id"))
        object.__setattr__(self, "candidate_id", _validate_non_blank_str(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "evaluation_id", _validate_non_blank_str(self.evaluation_id, "evaluation_id"))
        object.__setattr__(self, "dimension", _normalize_enum(self.dimension, CandidateDimension, "dimension"))
        object.__setattr__(self, "reason_code", _validate_non_blank_str(self.reason_code, "reason_code"))
        object.__setattr__(self, "human_text", _validate_non_blank_str(self.human_text, "human_text"))
        object.__setattr__(self, "polarity", _normalize_enum(self.polarity, ReasonPolarity, "polarity"))
        object.__setattr__(self, "severity", _normalize_enum(self.severity, ReasonSeverity, "severity"))
        if self.source_evidence_id is not None:
            object.__setattr__(self, "source_evidence_id", self.source_evidence_id.strip() or None)
        norm_created = _normalize_aware_dt(self.created_at, "created_at")
        object.__setattr__(self, "created_at", norm_created)


@dataclass(frozen=True)
class CandidateMissingData:
    """Explicit point-in-time record of unavailable or unknown inputs."""

    record_id: str
    candidate_id: str
    input_name: str
    data_family: str
    status: MissingDataStatus | str
    evaluation_id: str | None = None
    detail: str | None = None
    provider: str | None = None
    observed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _validate_non_blank_str(self.record_id, "record_id"))
        object.__setattr__(self, "candidate_id", _validate_non_blank_str(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "input_name", _validate_non_blank_str(self.input_name, "input_name"))
        object.__setattr__(self, "data_family", _validate_non_blank_str(self.data_family, "data_family"))
        object.__setattr__(self, "status", _normalize_enum(self.status, MissingDataStatus, "status"))
        if self.evaluation_id is not None:
            object.__setattr__(self, "evaluation_id", self.evaluation_id.strip() or None)
        if self.detail is not None:
            object.__setattr__(self, "detail", self.detail.strip() or None)
        if self.provider is not None:
            object.__setattr__(self, "provider", self.provider.strip() or None)
        if self.observed_at is not None:
            norm_obs = _normalize_aware_dt(self.observed_at, "observed_at")
            object.__setattr__(self, "observed_at", norm_obs)
        norm_created = _normalize_aware_dt(self.created_at, "created_at")
        object.__setattr__(self, "created_at", norm_created)


@dataclass(frozen=True)
class CandidateDossier:
    """Immutable aggregate container for snapshot header and child evidence/evaluations."""

    snapshot: CandidateSnapshot
    evaluations: tuple[CandidateEvaluation, ...] = ()
    evidence: tuple[CandidateEvidence, ...] = ()
    reasons: tuple[CandidateReason, ...] = ()
    missing_data: tuple[CandidateMissingData, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, CandidateSnapshot):
            raise TypeError(f"snapshot must be CandidateSnapshot, got {type(self.snapshot).__name__}")

        raw_evals = tuple(self.evaluations) if not isinstance(self.evaluations, tuple) else self.evaluations
        raw_evid = tuple(self.evidence) if not isinstance(self.evidence, tuple) else self.evidence
        raw_reas = tuple(self.reasons) if not isinstance(self.reasons, tuple) else self.reasons
        raw_miss = tuple(self.missing_data) if not isinstance(self.missing_data, tuple) else self.missing_data

        cand_id = self.snapshot.candidate_id

        # Type checks, candidate_id match, and duplicate primary ID rejection
        seen_evals: set[str] = set()
        for e in raw_evals:
            if not isinstance(e, CandidateEvaluation):
                raise TypeError(f"evaluations item must be CandidateEvaluation, got {type(e).__name__}")
            if e.candidate_id != cand_id:
                raise ValueError(f"Evaluation candidate_id '{e.candidate_id}' does not match snapshot '{cand_id}'")
            if e.evaluation_id in seen_evals:
                raise ValueError(f"Duplicate evaluation_id '{e.evaluation_id}' in dossier")
            seen_evals.add(e.evaluation_id)

        seen_evid: set[str] = set()
        for ev in raw_evid:
            if not isinstance(ev, CandidateEvidence):
                raise TypeError(f"evidence item must be CandidateEvidence, got {type(ev).__name__}")
            if ev.candidate_id != cand_id:
                raise ValueError(f"Evidence candidate_id '{ev.candidate_id}' does not match snapshot '{cand_id}'")
            if ev.evidence_id in seen_evid:
                raise ValueError(f"Duplicate evidence_id '{ev.evidence_id}' in dossier")
            seen_evid.add(ev.evidence_id)

        seen_reas: set[str] = set()
        for r in raw_reas:
            if not isinstance(r, CandidateReason):
                raise TypeError(f"reasons item must be CandidateReason, got {type(r).__name__}")
            if r.candidate_id != cand_id:
                raise ValueError(f"Reason candidate_id '{r.candidate_id}' does not match snapshot '{cand_id}'")
            if r.reason_id in seen_reas:
                raise ValueError(f"Duplicate reason_id '{r.reason_id}' in dossier")
            seen_reas.add(r.reason_id)

        seen_miss: set[str] = set()
        for m in raw_miss:
            if not isinstance(m, CandidateMissingData):
                raise TypeError(f"missing_data item must be CandidateMissingData, got {type(m).__name__}")
            if m.candidate_id != cand_id:
                raise ValueError(f"MissingData candidate_id '{m.candidate_id}' does not match snapshot '{cand_id}'")
            if m.record_id in seen_miss:
                raise ValueError(f"Duplicate record_id '{m.record_id}' in dossier")
            seen_miss.add(m.record_id)

        # Canonical deterministic child ordering by primary identifier
        canonical_evals = tuple(sorted(raw_evals, key=lambda x: x.evaluation_id))
        canonical_evid = tuple(sorted(raw_evid, key=lambda x: x.evidence_id))
        canonical_reas = tuple(sorted(raw_reas, key=lambda x: x.reason_id))
        canonical_miss = tuple(sorted(raw_miss, key=lambda x: x.record_id))

        object.__setattr__(self, "evaluations", canonical_evals)
        object.__setattr__(self, "evidence", canonical_evid)
        object.__setattr__(self, "reasons", canonical_reas)
        object.__setattr__(self, "missing_data", canonical_miss)

        # Point-in-time temporal integrity checks (Blocker 1)
        for ev in canonical_evid:
            if ev.observed_at is not None and ev.observed_at > self.snapshot.decision_timestamp:
                raise ValueError(
                    f"Evidence '{ev.evidence_id}' observed_at '{ev.observed_at.isoformat()}' "
                    f"is after candidate decision_timestamp '{self.snapshot.decision_timestamp.isoformat()}'; "
                    "future observations are rejected"
                )

        for m in canonical_miss:
            if m.observed_at is not None and m.observed_at > self.snapshot.decision_timestamp:
                raise ValueError(
                    f"MissingData '{m.record_id}' observed_at '{m.observed_at.isoformat()}' "
                    f"is after candidate decision_timestamp '{self.snapshot.decision_timestamp.isoformat()}'; "
                    "future observations are rejected"
                )

        eval_ids = {e.evaluation_id for e in canonical_evals}
        evid_ids = {ev.evidence_id for ev in canonical_evid}

        # Unconditional referential integrity checks (Blocker 3)
        for r in canonical_reas:
            if r.evaluation_id not in eval_ids:
                raise ValueError(
                    f"Reason evaluation_id '{r.evaluation_id}' does not match any evaluation in dossier"
                )
            if r.source_evidence_id is not None and r.source_evidence_id not in evid_ids:
                raise ValueError(
                    f"Reason source_evidence_id '{r.source_evidence_id}' does not match any evidence in dossier"
                )

        for m in canonical_miss:
            if m.evaluation_id is not None and m.evaluation_id not in eval_ids:
                raise ValueError(
                    f"MissingData evaluation_id '{m.evaluation_id}' does not match any evaluation in dossier"
                )
