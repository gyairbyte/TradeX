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
from typing import Any

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
    security_identity_status: SecurityIdentityStatus = SecurityIdentityStatus.UNKNOWN
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _validate_non_blank_str(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        norm_ts = _normalize_aware_dt(self.decision_timestamp, "decision_timestamp")
        object.__setattr__(self, "decision_timestamp", norm_ts)
        norm_created = _normalize_aware_dt(self.created_at, "created_at")
        object.__setattr__(self, "created_at", norm_created)

        # Derive or validate trading date using New York market calendar
        derived_td = derive_trading_date(norm_ts)
        if self.trading_date is None:
            object.__setattr__(self, "trading_date", derived_td)
        else:
            if derived_td is not None and self.trading_date != derived_td:
                raise ValueError(
                    f"Supplied trading_date '{self.trading_date}' does not match "
                    f"derived market trading date '{derived_td}'"
                )

        if isinstance(self.security_identity_status, str):
            object.__setattr__(self, "security_identity_status", SecurityIdentityStatus(self.security_identity_status))

        # Security identity consistency validation
        if self.security_identity_version is not None:
            ver = self.security_identity_version.strip()
            if not ver:
                raise ValueError("security_identity_version cannot be empty when provided")
            object.__setattr__(self, "security_identity_version", ver)
            if self.security_identity_status == SecurityIdentityStatus.UNKNOWN:
                object.__setattr__(self, "security_identity_status", SecurityIdentityStatus.KNOWN)
        else:
            if self.security_identity_status == SecurityIdentityStatus.KNOWN:
                raise ValueError("security_identity_status cannot be 'known' when security_identity_version is None")


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
        _validate_json_serializable(self.dimensions)
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
        _validate_json_serializable(self.metadata)
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
    reason_code: str
    human_text: str
    evaluation_id: str | None = None
    dimension: CandidateDimension | str | None = None
    polarity: ReasonPolarity = ReasonPolarity.NEUTRAL
    severity: ReasonSeverity = ReasonSeverity.INFO
    source_evidence_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_id", _validate_non_blank_str(self.reason_id, "reason_id"))
        object.__setattr__(self, "candidate_id", _validate_non_blank_str(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "reason_code", _validate_non_blank_str(self.reason_code, "reason_code"))
        object.__setattr__(self, "human_text", _validate_non_blank_str(self.human_text, "human_text"))
        if self.evaluation_id is not None:
            object.__setattr__(self, "evaluation_id", self.evaluation_id.strip() or None)
        if self.dimension is not None:
            dim_val = self.dimension.value if isinstance(self.dimension, CandidateDimension) else str(self.dimension).strip()
            object.__setattr__(self, "dimension", dim_val or None)
        if isinstance(self.polarity, str):
            object.__setattr__(self, "polarity", ReasonPolarity(self.polarity))
        if isinstance(self.severity, str):
            object.__setattr__(self, "severity", ReasonSeverity(self.severity))
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
    status: MissingDataStatus
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
        if isinstance(self.status, str):
            object.__setattr__(self, "status", MissingDataStatus(self.status))
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

        evals = tuple(self.evaluations) if not isinstance(self.evaluations, tuple) else self.evaluations
        evid = tuple(self.evidence) if not isinstance(self.evidence, tuple) else self.evidence
        reas = tuple(self.reasons) if not isinstance(self.reasons, tuple) else self.reasons
        miss = tuple(self.missing_data) if not isinstance(self.missing_data, tuple) else self.missing_data

        object.__setattr__(self, "evaluations", evals)
        object.__setattr__(self, "evidence", evid)
        object.__setattr__(self, "reasons", reas)
        object.__setattr__(self, "missing_data", miss)

        cand_id = self.snapshot.candidate_id
        eval_ids = {e.evaluation_id for e in evals}
        evid_ids = {ev.evidence_id for ev in evid}

        for e in evals:
            if not isinstance(e, CandidateEvaluation):
                raise TypeError(f"evaluations item must be CandidateEvaluation, got {type(e).__name__}")
            if e.candidate_id != cand_id:
                raise ValueError(f"Evaluation candidate_id '{e.candidate_id}' does not match snapshot '{cand_id}'")

        for ev in evid:
            if not isinstance(ev, CandidateEvidence):
                raise TypeError(f"evidence item must be CandidateEvidence, got {type(ev).__name__}")
            if ev.candidate_id != cand_id:
                raise ValueError(f"Evidence candidate_id '{ev.candidate_id}' does not match snapshot '{cand_id}'")

        for r in reas:
            if not isinstance(r, CandidateReason):
                raise TypeError(f"reasons item must be CandidateReason, got {type(r).__name__}")
            if r.candidate_id != cand_id:
                raise ValueError(f"Reason candidate_id '{r.candidate_id}' does not match snapshot '{cand_id}'")
            if r.evaluation_id is not None and r.evaluation_id not in eval_ids and evals:
                raise ValueError(f"Reason evaluation_id '{r.evaluation_id}' does not match any evaluation in dossier")
            if r.source_evidence_id is not None and r.source_evidence_id not in evid_ids and evid:
                raise ValueError(
                    f"Reason source_evidence_id '{r.source_evidence_id}' does not match any evidence in dossier"
                )

        for m in miss:
            if not isinstance(m, CandidateMissingData):
                raise TypeError(f"missing_data item must be CandidateMissingData, got {type(m).__name__}")
            if m.candidate_id != cand_id:
                raise ValueError(f"MissingData candidate_id '{m.candidate_id}' does not match snapshot '{cand_id}'")
            if m.evaluation_id is not None and m.evaluation_id not in eval_ids and evals:
                raise ValueError(f"MissingData evaluation_id '{m.evaluation_id}' does not match any evaluation in dossier")
