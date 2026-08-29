"""Executable Journal domain models, enums, and exceptions (MVP-ARCH-001-R6).

Defines immutable, typed representations for JournalTrade, TradePlan, JournalEvent,
JournalOutcome, ExecutionProvenance, and associated lifecycle enums and exceptions.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypeVar


class JournalState(StrEnum):
    """Lifecycle states for executable journal trade plans."""

    PLANNED = "planned"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class ExitReason(StrEnum):
    """Reason for closing an open trade position."""

    STOP = "stop"
    TARGET = "target"
    EXPIRATION = "expiration"
    INVALIDATION = "invalidation"
    DISCRETIONARY = "discretionary"


class ExecutionProvenanceType(StrEnum):
    """Provenance category for fill and exit execution observations."""

    MANUAL = "manual"
    SIMULATED = "simulated"
    BROKER_CONFIRMED = "broker_confirmed"


class OutcomeConfidence(StrEnum):
    """Confidence level assigned to realized outcome calculations."""

    CONFIRMED = "confirmed"
    PROVISIONAL = "provisional"
    UNKNOWN = "unknown"


class JournalEventType(StrEnum):
    """Append-only lifecycle event types."""

    CREATED = "created"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    EXITED = "exited"


# ── Domain Exceptions ────────────────────────────────────────────────────────


class JournalError(Exception):
    """Base exception for Journal domain and lifecycle errors."""


class StrategyNotAuthorizedError(JournalError):
    """Raised when a strategy identity is unauthorized for journal execution."""


class CandidateNotFoundError(JournalError):
    """Raised when a referenced candidate snapshot does not exist in the store."""


class JournalNotFoundError(JournalError):
    """Raised when a referenced journal trade does not exist."""


class IdempotencyConflictError(JournalError):
    """Raised when an idempotency key is reused with divergent material payload."""


class InvalidTransitionError(JournalError):
    """Raised when an illegal lifecycle state transition is attempted."""


class ConflictingFillError(JournalError):
    """Raised when a subsequent fill differs materially from an existing fill."""


class ConflictingExitError(JournalError):
    """Raised when a subsequent exit differs materially from an existing exit."""


# ── Normalization & Validation Helpers ───────────────────────────────────────

T = TypeVar("T", bound=StrEnum)


def _normalize_enum(value: object, enum_cls: type[T], field_name: str) -> T:
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


def _normalize_aware_dt(dt: datetime, field_name: str) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError(f"{field_name} must be a datetime instance, got {type(dt).__name__}")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{field_name} must be timezone-aware; naive datetimes are rejected")
    return dt.astimezone(UTC)


def _validate_positive_finite_float(val: object, field_name: str) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise TypeError(f"{field_name} must be a numeric float/int, got {type(val).__name__}")
    f_val = float(val)
    if not math.isfinite(f_val):
        raise ValueError(f"{field_name} must be finite (got {f_val})")
    if f_val <= 0:
        raise ValueError(f"{field_name} must be strictly positive (> 0), got {f_val}")
    return f_val


def _validate_non_negative_finite_float(val: object, field_name: str) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise TypeError(f"{field_name} must be a numeric float/int, got {type(val).__name__}")
    f_val = float(val)
    if not math.isfinite(f_val):
        raise ValueError(f"{field_name} must be finite (got {f_val})")
    if f_val < 0:
        raise ValueError(f"{field_name} must be non-negative (>= 0), got {f_val}")
    return f_val


def _normalize_provider(value: object, field_name: str = "provider") -> str:
    """Normalize provider identity: None/blank becomes 'unknown', nonblank preserved verbatim."""
    if value is None:
        return "unknown"
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None, got {type(value).__name__}")
    if not value.strip():
        return "unknown"
    return value


def _validate_non_blank_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_and_canonicalize_json_dict(data: object, field_name: str) -> dict[str, Any]:
    if isinstance(data, bool) or not isinstance(data, dict):
        raise TypeError(f"{field_name} must be a dict, got {type(data).__name__}")

    def _check_keys_and_values(obj: object) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, bool) or not isinstance(k, str):
                    raise TypeError(
                        f"{field_name} dictionary keys must be str, got key {k!r} of type {type(k).__name__}"
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


# ── Domain Models ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class InvalidationRule:
    """Structured invalidation rule for a planned trade setup."""

    rule_id: str
    rule_version: str
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _validate_non_blank_str(self.rule_id, "rule_id"))
        object.__setattr__(
            self, "rule_version", _validate_non_blank_str(self.rule_version, "rule_version")
        )
        canonical_params = _validate_and_canonicalize_json_dict(self.params, "params")
        object.__setattr__(self, "params", canonical_params)


@dataclass(frozen=True, slots=True)
class TradePlan:
    """Immutable trade plan definition."""

    planned_entry: float
    stop_price: float | None = None
    target_price: float | None = None
    expiration: datetime | None = None
    invalidation_rule: InvalidationRule | None = None

    def __post_init__(self) -> None:
        entry = _validate_positive_finite_float(self.planned_entry, "planned_entry")
        object.__setattr__(self, "planned_entry", entry)

        if self.stop_price is not None:
            stop = _validate_positive_finite_float(self.stop_price, "stop_price")
            if stop >= entry:
                raise ValueError(
                    f"stop_price ({stop}) must be strictly less than planned_entry ({entry})"
                )
            object.__setattr__(self, "stop_price", stop)

        if self.target_price is not None:
            target = _validate_positive_finite_float(self.target_price, "target_price")
            if target <= entry:
                raise ValueError(
                    f"target_price ({target}) must be strictly greater than planned_entry ({entry})"
                )
            object.__setattr__(self, "target_price", target)

        if self.expiration is not None:
            exp = _normalize_aware_dt(self.expiration, "expiration")
            object.__setattr__(self, "expiration", exp)

        if self.invalidation_rule is not None and not isinstance(
            self.invalidation_rule, InvalidationRule
        ):
            raise TypeError("invalidation_rule must be an InvalidationRule instance")


@dataclass(frozen=True, slots=True)
class ExecutionProvenance:
    """Execution provenance for fill and exit observations."""

    execution_provenance: ExecutionProvenanceType | str
    provider: str = "unknown"
    observed_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    observer: str = ""
    simulation_rule: str | None = None

    def __post_init__(self) -> None:
        prov_type = _normalize_enum(
            self.execution_provenance, ExecutionProvenanceType, "execution_provenance"
        )
        object.__setattr__(self, "execution_provenance", prov_type)

        # Provider: nonblank string preserved verbatim; None/blank normalized to "unknown"; non-string rejected
        norm_provider = _normalize_provider(self.provider, "provider")
        object.__setattr__(self, "provider", norm_provider)

        obs_at = _normalize_aware_dt(self.observed_at, "observed_at")
        object.__setattr__(self, "observed_at", obs_at)

        obs_str = _validate_non_blank_str(self.observer, "observer")
        object.__setattr__(self, "observer", obs_str)

        if prov_type == ExecutionProvenanceType.SIMULATED:
            sim_rule = _validate_non_blank_str(self.simulation_rule or "", "simulation_rule")
            object.__setattr__(self, "simulation_rule", sim_rule)
        elif self.simulation_rule is not None:
            clean_sim = self.simulation_rule.strip() or None
            object.__setattr__(self, "simulation_rule", clean_sim)


@dataclass(frozen=True, slots=True)
class JournalTrade:
    """Domain representation of an executable journal trade."""

    journal_id: str
    idempotency_key: str
    candidate_id: str
    strategy_id: str
    strategy_version: str
    decision_timestamp: datetime
    plan_created_at: datetime
    planned_entry: float
    contract_version: int = 1
    side: str = "long"
    state: JournalState | str = JournalState.PLANNED
    stop_price: float | None = None
    target_price: float | None = None
    expiration: datetime | None = None
    invalidation_rule: InvalidationRule | None = None
    quantity: float | None = None
    fill_price: float | None = None
    fill_timestamp: datetime | None = None
    fill_provenance: ExecutionProvenance | None = None
    exit_price: float | None = None
    exit_timestamp: datetime | None = None
    exit_reason: ExitReason | str | None = None
    exit_provenance: ExecutionProvenance | None = None
    terminal_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "journal_id", _validate_non_blank_str(self.journal_id, "journal_id"))
        object.__setattr__(
            self, "idempotency_key", _validate_non_blank_str(self.idempotency_key, "idempotency_key")
        )
        object.__setattr__(
            self, "candidate_id", _validate_non_blank_str(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self, "strategy_id", _validate_non_blank_str(self.strategy_id, "strategy_id")
        )
        object.__setattr__(
            self, "strategy_version", _validate_non_blank_str(self.strategy_version, "strategy_version")
        )

        if self.side != "long":
            raise ValueError(f"side must be 'long', got '{self.side}'")

        norm_state = _normalize_enum(self.state, JournalState, "state")
        object.__setattr__(self, "state", norm_state)

        norm_dec_ts = _normalize_aware_dt(self.decision_timestamp, "decision_timestamp")
        object.__setattr__(self, "decision_timestamp", norm_dec_ts)

        norm_plan_created = _normalize_aware_dt(self.plan_created_at, "plan_created_at")
        object.__setattr__(self, "plan_created_at", norm_plan_created)

        if norm_dec_ts > norm_plan_created:
            raise ValueError(
                f"decision_timestamp ({norm_dec_ts.isoformat()}) cannot be after "
                f"plan_created_at ({norm_plan_created.isoformat()})"
            )

        entry = _validate_positive_finite_float(self.planned_entry, "planned_entry")
        object.__setattr__(self, "planned_entry", entry)

        if self.stop_price is not None:
            stop = _validate_positive_finite_float(self.stop_price, "stop_price")
            if stop >= entry:
                raise ValueError(f"stop_price ({stop}) must be less than planned_entry ({entry})")
            object.__setattr__(self, "stop_price", stop)

        if self.target_price is not None:
            target = _validate_positive_finite_float(self.target_price, "target_price")
            if target <= entry:
                raise ValueError(
                    f"target_price ({target}) must be greater than planned_entry ({entry})"
                )
            object.__setattr__(self, "target_price", target)

        if self.expiration is not None:
            exp = _normalize_aware_dt(self.expiration, "expiration")
            object.__setattr__(self, "expiration", exp)

        if self.invalidation_rule is not None and not isinstance(
            self.invalidation_rule, InvalidationRule
        ):
            raise TypeError("invalidation_rule must be an InvalidationRule instance")

        if self.quantity is not None:
            qty = _validate_positive_finite_float(self.quantity, "quantity")
            object.__setattr__(self, "quantity", qty)

        if self.fill_price is not None:
            fp = _validate_positive_finite_float(self.fill_price, "fill_price")
            object.__setattr__(self, "fill_price", fp)

        if self.fill_timestamp is not None:
            fts = _normalize_aware_dt(self.fill_timestamp, "fill_timestamp")
            object.__setattr__(self, "fill_timestamp", fts)

        if self.fill_provenance is not None and not isinstance(
            self.fill_provenance, ExecutionProvenance
        ):
            raise TypeError("fill_provenance must be an ExecutionProvenance instance")

        if self.exit_price is not None:
            ep = _validate_positive_finite_float(self.exit_price, "exit_price")
            object.__setattr__(self, "exit_price", ep)

        if self.exit_timestamp is not None:
            ets = _normalize_aware_dt(self.exit_timestamp, "exit_timestamp")
            object.__setattr__(self, "exit_timestamp", ets)

        if self.exit_reason is not None:
            norm_exit_reason = _normalize_enum(self.exit_reason, ExitReason, "exit_reason")
            object.__setattr__(self, "exit_reason", norm_exit_reason)

        if self.exit_provenance is not None and not isinstance(
            self.exit_provenance, ExecutionProvenance
        ):
            raise TypeError("exit_provenance must be an ExecutionProvenance instance")

        if self.terminal_reason is not None:
            object.__setattr__(
                self, "terminal_reason", self.terminal_reason.strip() or None
            )

        norm_created = _normalize_aware_dt(self.created_at, "created_at")
        object.__setattr__(self, "created_at", norm_created)

        norm_updated = _normalize_aware_dt(self.updated_at, "updated_at")
        object.__setattr__(self, "updated_at", norm_updated)

        # State-based integrity checks
        if norm_state == JournalState.OPEN:
            if self.fill_price is None or self.fill_timestamp is None or self.quantity is None:
                raise ValueError("State 'open' requires fill_price, fill_timestamp, and quantity")
        elif norm_state == JournalState.CLOSED:
            if (
                self.fill_price is None
                or self.quantity is None
                or self.exit_price is None
                or self.exit_timestamp is None
                or self.exit_reason is None
            ):
                raise ValueError(
                    "State 'closed' requires fill_price, quantity, exit_price, exit_timestamp, and exit_reason"
                )
        elif norm_state in (
            JournalState.PLANNED,
            JournalState.CANCELLED,
            JournalState.EXPIRED,
            JournalState.INVALIDATED,
        ) and (self.fill_price is not None or self.exit_price is not None):
            raise ValueError(
                f"State '{norm_state.value}' must not have fill_price or exit_price"
            )

    @property
    def plan(self) -> TradePlan:
        return TradePlan(
            planned_entry=self.planned_entry,
            stop_price=self.stop_price,
            target_price=self.target_price,
            expiration=self.expiration,
            invalidation_rule=self.invalidation_rule,
        )


@dataclass(frozen=True, slots=True)
class JournalEvent:
    """Append-only lifecycle audit event for a journal trade."""

    event_id: str
    journal_id: str
    seq: int
    event_type: JournalEventType | str
    event_timestamp: datetime
    recorded_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _validate_non_blank_str(self.event_id, "event_id"))
        object.__setattr__(self, "journal_id", _validate_non_blank_str(self.journal_id, "journal_id"))

        if isinstance(self.seq, bool) or not isinstance(self.seq, int) or self.seq <= 0:
            raise ValueError(f"seq must be a positive integer (>= 1), got {self.seq!r}")

        norm_event_type = _normalize_enum(self.event_type, JournalEventType, "event_type")
        object.__setattr__(self, "event_type", norm_event_type)

        norm_event_ts = _normalize_aware_dt(self.event_timestamp, "event_timestamp")
        object.__setattr__(self, "event_timestamp", norm_event_ts)

        norm_recorded_at = _normalize_aware_dt(self.recorded_at, "recorded_at")
        object.__setattr__(self, "recorded_at", norm_recorded_at)

        canonical_payload = _validate_and_canonicalize_json_dict(self.payload, "payload")
        object.__setattr__(self, "payload", canonical_payload)


@dataclass(frozen=True, slots=True)
class JournalOutcome:
    """Deterministic, versioned outcome calculation for a closed journal trade."""

    outcome_id: str
    journal_id: str
    computation_version: str
    computed_at: datetime
    source_event_seq: int
    inputs_hash: str
    entry_slippage: float | None
    costs: float | None
    gross_return_pct: float | None
    net_return_pct: float | None
    outcome_confidence: OutcomeConfidence | str
    inputs: dict[str, Any] = field(default_factory=dict)
    strategy_drawdown: float | None = None  # Always None in R6 v1

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome_id", _validate_non_blank_str(self.outcome_id, "outcome_id"))
        object.__setattr__(self, "journal_id", _validate_non_blank_str(self.journal_id, "journal_id"))
        object.__setattr__(
            self,
            "computation_version",
            _validate_non_blank_str(self.computation_version, "computation_version"),
        )
        norm_computed_at = _normalize_aware_dt(self.computed_at, "computed_at")
        object.__setattr__(self, "computed_at", norm_computed_at)

        if (
            isinstance(self.source_event_seq, bool)
            or not isinstance(self.source_event_seq, int)
            or self.source_event_seq <= 0
        ):
            raise ValueError(
                f"source_event_seq must be a positive integer, got {self.source_event_seq!r}"
            )

        object.__setattr__(
            self, "inputs_hash", _validate_non_blank_str(self.inputs_hash, "inputs_hash")
        )

        if self.entry_slippage is not None:
            if isinstance(self.entry_slippage, bool) or not isinstance(
                self.entry_slippage, (int, float)
            ):
                raise TypeError("entry_slippage must be a float or None")
            if not math.isfinite(float(self.entry_slippage)):
                raise ValueError("entry_slippage must be finite")
            object.__setattr__(self, "entry_slippage", float(self.entry_slippage))

        if self.costs is not None:
            c = _validate_non_negative_finite_float(self.costs, "costs")
            object.__setattr__(self, "costs", c)

        if self.gross_return_pct is not None:
            if isinstance(self.gross_return_pct, bool) or not isinstance(
                self.gross_return_pct, (int, float)
            ):
                raise TypeError("gross_return_pct must be a float or None")
            if not math.isfinite(float(self.gross_return_pct)):
                raise ValueError("gross_return_pct must be finite")
            object.__setattr__(self, "gross_return_pct", float(self.gross_return_pct))

        if self.net_return_pct is not None:
            if isinstance(self.net_return_pct, bool) or not isinstance(
                self.net_return_pct, (int, float)
            ):
                raise TypeError("net_return_pct must be a float or None")
            if not math.isfinite(float(self.net_return_pct)):
                raise ValueError("net_return_pct must be finite")
            object.__setattr__(self, "net_return_pct", float(self.net_return_pct))

        norm_conf = _normalize_enum(self.outcome_confidence, OutcomeConfidence, "outcome_confidence")
        object.__setattr__(self, "outcome_confidence", norm_conf)

        canonical_inputs = _validate_and_canonicalize_json_dict(self.inputs, "inputs")
        object.__setattr__(self, "inputs", canonical_inputs)

        # Strategy drawdown must be None in R6 v1
        if self.strategy_drawdown is not None:
            raise ValueError(
                "strategy_drawdown is not supported in R6 v1 and must be None"
            )
