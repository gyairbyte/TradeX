"""Typed, immutable models for the pattern-similarity validation study."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from tradex.patterns.config import PROFILES
from tradex.patterns.matcher import SERIES_WEIGHTS
from tradex.patterns.miner import MINING_UNIVERSE


class ValidationError(ValueError):
    """Raised for invalid study configuration, manifests, or inputs."""


# ── helpers ─────────────────────────────────────────────────────────────────


def _require_int(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or isinstance(value, float):
        raise ValidationError(f"{name} must be an integer; got {value!r} ({type(value).__name__})")


def _require_positive_int(name: str, value: Any) -> None:
    _require_int(name, value)
    if int(value) < 1:
        raise ValidationError(f"{name} must be positive; got {value}")


def _require_finite_number(name: str, value: Any) -> None:
    if isinstance(value, bool):
        raise ValidationError(f"{name} must be a finite number; got boolean")
    if not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValidationError(f"{name} must be a finite number; got {value!r} ({type(value).__name__})")
    f = float(value)
    if not math.isfinite(f):
        raise ValidationError(f"{name} must be finite; got {value}")


def _require_nonnegative_finite(name: str, value: Any) -> None:
    _require_finite_number(name, value)
    if float(value) < 0:
        raise ValidationError(f"{name} must be nonnegative; got {value}")


def _require_percentage(name: str, value: Any) -> None:
    _require_finite_number(name, value)
    f = float(value)
    if not (0 <= f <= 100):
        raise ValidationError(f"{name} must be between 0 and 100; got {f}")


def _clean_value(value: Any) -> Any:
    """Convert NaN/Inf and numpy scalars into JSON-safe Python values."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 6)
    if isinstance(value, np.floating):
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 6)
    if isinstance(value, (np.integer, np.bool_)):
        return int(value) if not isinstance(value, np.bool_) else bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (dict, Mapping)):
        return {str(k): _clean_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_value(v) for v in value]
    return value


def _clean(data: Any) -> Any:
    """Recursively clean a structure for JSON serialization."""
    if isinstance(data, (dict, Mapping)):
        return {str(k): _clean(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_clean(v) for v in data]
    if is_dataclass(data) and not isinstance(data, type):
        return _clean(asdict(data))
    return _clean_value(data)


class FrozenMapping(Mapping):
    """Immutable mapping that is not a dict subclass.

    All standard mutation paths raise ``TypeError``. The object implements
    ``collections.abc.Mapping``, so it supports read-only item access,
    iteration, and ``dict()`` conversion, but cannot be mutated through
    inherited ``dict`` internals.
    """

    __slots__ = ("_d",)

    def __init__(self, mapping: Mapping | None = None) -> None:
        object.__setattr__(self, "_d", dict(mapping) if mapping is not None else {})

    def __getstate__(self) -> dict:
        return {"_d": self._d}

    def __setstate__(self, state: dict) -> None:
        object.__setattr__(self, "_d", state["_d"])

    def __getitem__(self, key: Any) -> Any:
        return self._d[key]

    def __iter__(self) -> Any:
        return iter(self._d)

    def __len__(self) -> int:
        return len(self._d)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._d!r})"

    def __setattr__(self, key: str, value: Any) -> None:
        raise TypeError(f"{self.__class__.__name__} is immutable")

    def __delattr__(self, key: str) -> None:
        raise TypeError(f"{self.__class__.__name__} is immutable")

    def __setitem__(self, key: Any, value: Any) -> None:
        raise TypeError(f"{self.__class__.__name__} does not support item assignment")

    def __delitem__(self, key: Any) -> None:
        raise TypeError(f"{self.__class__.__name__} does not support item deletion")

    def __ior__(self, other: Any) -> "FrozenMapping":  # type: ignore[override]
        raise TypeError(f"{self.__class__.__name__} does not support |=")

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        raise TypeError(f"{self.__class__.__name__} does not support update")

    def pop(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        raise TypeError(f"{self.__class__.__name__} does not support pop")

    def popitem(self) -> Any:  # type: ignore[override]
        raise TypeError(f"{self.__class__.__name__} does not support popitem")

    def clear(self) -> None:
        raise TypeError(f"{self.__class__.__name__} does not support clear")

    def setdefault(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        raise TypeError(f"{self.__class__.__name__} does not support setdefault")

    def __deepcopy__(self, memo: dict[int, Any]) -> "FrozenMapping":
        return FrozenMapping({deepcopy(k, memo): deepcopy(v, memo) for k, v in self._d.items()})

    def to_dict(self) -> dict:
        return dict(self._d)


def _canonical_json_sha256(obj: Any) -> str:
    """Return SHA-256 of a canonical JSON serialization of ``obj``."""
    payload = json.dumps(_clean(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _iso(dt: datetime | date | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


# ── core data classes ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Split:
    """A temporal partition of the dataset."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if not isinstance(self.start, date) or not isinstance(self.end, date):
            raise ValidationError("Split start/end must be date objects")
        if self.end < self.start:
            raise ValidationError(f"Split end {self.end} must be >= start {self.start}")

    def to_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}

    def overlaps(self, other: Split) -> bool:
        return self.start <= other.end and other.start <= self.end


# Locked canonical contract for the real Schwab PATTERN-001 study.
_LOCKED_PROVIDER = "schwab"
_LOCKED_START_DATE = date(2018, 1, 2)
_LOCKED_END_DATE = date(2026, 7, 31)
_LOCKED_SPLITS = {
    "development": Split(_LOCKED_START_DATE, date(2021, 12, 31)),
    "validation": Split(date(2022, 1, 3), date(2023, 12, 29)),
    "holdout": Split(date(2024, 1, 2), _LOCKED_END_DATE),
}
_LOCKED_UNIVERSE = tuple(MINING_UNIVERSE)


@dataclass(frozen=True)
class BootstrapConfig:
    """Ticker-cluster bootstrap configuration."""

    method: str = "ticker-cluster"
    resamples: int = 5000
    seed: int = 20260803

    def __post_init__(self) -> None:
        _require_int("resamples", self.resamples)
        if self.resamples < 1:
            raise ValidationError(f"resamples must be positive; got {self.resamples}")
        _require_int("seed", self.seed)
        if self.method not in {"ticker-cluster"}:
            raise ValidationError(f"unknown bootstrap method {self.method!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method, "resamples": self.resamples, "seed": self.seed}


def _validate_locked_contract(spec: StudySpec) -> None:
    """Enforce the exact locked PATTERN-001 Schwab study contract."""
    errors: list[str] = []

    if spec.tickers != _LOCKED_UNIVERSE:
        errors.append(f"tickers must be the exact ordered MINING_UNIVERSE; got {spec.tickers}")
    if spec.provider != _LOCKED_PROVIDER:
        errors.append(f"provider must be '{_LOCKED_PROVIDER}'; got {spec.provider}")
    if spec.start_date != _LOCKED_START_DATE:
        errors.append(f"start_date must be {_LOCKED_START_DATE}; got {spec.start_date}")
    if spec.end_date != _LOCKED_END_DATE:
        errors.append(f"end_date must be {_LOCKED_END_DATE}; got {spec.end_date}")

    expected_splits = _LOCKED_SPLITS
    if set(spec.splits.keys()) != set(expected_splits.keys()):
        errors.append(f"splits must be {list(expected_splits.keys())}; got {list(spec.splits.keys())}")
    else:
        for name, expected in expected_splits.items():
            actual = spec.splits[name]
            if actual.start != expected.start or actual.end != expected.end:
                errors.append(
                    f"split '{name}' must be {expected.start} to {expected.end}; "
                    f"got {actual.start} to {actual.end}"
                )

    locked_scalar_checks = {
        "profile": ("standard", spec.profile),
        "runup_pct": (15.0, spec.runup_pct),
        "decline_pct": (12.0, spec.decline_pct),
        "move_days": (5, spec.move_days),
        "lookback_days": (10, spec.lookback_days),
        "min_events": (20, spec.min_events),
        "holding_days": (5, spec.holding_days),
        "similarity_threshold": (75.0, spec.similarity_threshold),
        "decision_slippage_bps": (10.0, spec.decision_slippage_bps),
        "commission_bps": (0.0, spec.commission_bps),
        "minimum_validation_signals": (100, spec.minimum_validation_signals),
        "minimum_holdout_signals": (100, spec.minimum_holdout_signals),
        "minimum_tickers": (15, spec.minimum_tickers),
        "max_ticker_concentration": (0.20, spec.max_ticker_concentration),
        "minimum_lift_bps": (25.0, spec.minimum_lift_bps),
        "random_seed": (20260803, spec.random_seed),
        "baseline_definition": ("frequency_matched", spec.baseline_definition),
        "adjustment_policy": ("provider_default", spec.adjustment_policy),
        "universe_classification": ("fixed_convenience_cohort_not_point_in_time", spec.universe_classification),
    }
    for name, (expected, actual) in locked_scalar_checks.items():
        if actual != expected:
            errors.append(f"{name} must be {expected!r}; got {actual!r}")

    if tuple(spec.event_types) != ("runup", "decline"):
        errors.append(f"event_types must be ('runup', 'decline'); got {spec.event_types}")

    if tuple(spec.slippage_scenarios_bps) != (0.0, 5.0, 10.0):
        errors.append(f"slippage_scenarios_bps must be (0.0, 5.0, 10.0); got {spec.slippage_scenarios_bps}")

    if dict(sorted(spec.series_weights.items())) != dict(sorted(SERIES_WEIGHTS.items())):
        errors.append(f"series_weights must match SERIES_WEIGHTS; got {spec.series_weights}")

    if spec.bootstrap.to_dict() != BootstrapConfig().to_dict():
        errors.append(f"bootstrap must match the locked default; got {spec.bootstrap.to_dict()}")

    if spec.production_promotion_eligible is not False:
        errors.append("production_promotion_eligible must be false")

    if errors:
        raise ValidationError("locked study contract violation: " + "; ".join(errors))


@dataclass(frozen=True)
class StudySpec:
    """Immutable, validated study specification for pattern-similarity validation."""

    tickers: tuple[str, ...]
    dataset_name: str = "pattern-similarity-validation"
    provider: str = "schwab"
    start_date: date = field(default_factory=lambda: date(2018, 1, 2))
    end_date: date = field(default_factory=lambda: date(2026, 7, 31))
    splits: dict[str, Split] = field(default_factory=dict)
    event_types: tuple[str, ...] = ("runup", "decline")
    profile: str = "standard"
    runup_pct: float = 15.0
    decline_pct: float = 12.0
    move_days: int = 5
    lookback_days: int = 10
    min_events: int = 20
    holding_days: int = 5
    similarity_threshold: float = 75.0
    series_weights: dict[str, float] = field(default_factory=lambda: dict(SERIES_WEIGHTS))
    slippage_scenarios_bps: tuple[float, ...] = (0.0, 5.0, 10.0)
    decision_slippage_bps: float = 10.0
    commission_bps: float = 0.0
    minimum_validation_signals: int = 100
    minimum_holdout_signals: int = 100
    minimum_tickers: int = 15
    max_ticker_concentration: float = 0.20
    minimum_lift_bps: float = 25.0
    bootstrap: BootstrapConfig = field(default_factory=BootstrapConfig)
    random_seed: int = 20260803
    baseline_definition: str = "frequency_matched"
    adjustment_policy: str = "provider_default"
    universe_classification: str = "fixed_convenience_cohort_not_point_in_time"
    production_promotion_eligible: bool = False
    research_test_mode: bool = False

    def __post_init__(self) -> None:
        # Validate and normalize mutable inputs.  Numeric strings are rejected.
        object.__setattr__(self, "tickers", tuple(str(t).strip().upper() for t in self.tickers))
        object.__setattr__(self, "event_types", tuple(self.event_types))

        validated_slippage: list[float] = []
        for s in self.slippage_scenarios_bps:
            _require_nonnegative_finite("slippage_scenarios_bps element", s)
            validated_slippage.append(float(s))
        object.__setattr__(self, "slippage_scenarios_bps", tuple(validated_slippage))

        validated_weights: dict[str, float] = {}
        for k, v in self.series_weights.items():
            _require_finite_number(f"series_weights[{k}]", v)
            validated_weights[str(k)] = float(v)
        object.__setattr__(self, "series_weights", FrozenMapping(validated_weights))
        object.__setattr__(
            self, "splits", FrozenMapping({k: Split(start=s.start, end=s.end) for k, s in self.splits.items()})
        )

        if not self.tickers:
            raise ValidationError("tickers must not be empty")
        if len(set(self.tickers)) != len(self.tickers):
            raise ValidationError(f"tickers contains duplicates: {self.tickers}")

        for t in self.tickers:
            if not t.isalnum():
                raise ValidationError(f"ticker must be alphanumeric; got {t!r}")

        if not isinstance(self.start_date, date) or not isinstance(self.end_date, date):
            raise ValidationError("start_date and end_date must be date objects")
        if self.end_date < self.start_date:
            raise ValidationError(f"end_date {self.end_date} must be >= start_date {self.start_date}")

        if self.profile not in PROFILES:
            raise ValidationError(f"profile must be one of {list(PROFILES)}; got {self.profile}")

        for et in self.event_types:
            if et not in {"runup", "decline"}:
                raise ValidationError(f"event_types must be 'runup' and/or 'decline'; got {et!r}")

        _require_positive_int("move_days", self.move_days)
        _require_positive_int("lookback_days", self.lookback_days)
        _require_positive_int("min_events", self.min_events)
        _require_positive_int("holding_days", self.holding_days)
        _require_percentage("similarity_threshold", self.similarity_threshold)

        if set(self.series_weights.keys()) != set(SERIES_WEIGHTS):
            raise ValidationError(
                f"series_weights must contain exactly {sorted(SERIES_WEIGHTS)}; got {sorted(self.series_weights)}"
            )
        total_weight = sum(self.series_weights.values())
        if not math.isclose(total_weight, 1.0, abs_tol=1e-9):
            raise ValidationError(f"series_weights must sum to 1.0; got {total_weight}")

        if not self.slippage_scenarios_bps:
            raise ValidationError("slippage_scenarios_bps must not be empty")
        for s in self.slippage_scenarios_bps:
            _require_nonnegative_finite("slippage_scenarios_bps element", s)

        _require_nonnegative_finite("decision_slippage_bps", self.decision_slippage_bps)
        _require_nonnegative_finite("commission_bps", self.commission_bps)

        _require_positive_int("minimum_validation_signals", self.minimum_validation_signals)
        _require_positive_int("minimum_holdout_signals", self.minimum_holdout_signals)
        _require_positive_int("minimum_tickers", self.minimum_tickers)
        _require_nonnegative_finite("max_ticker_concentration", self.max_ticker_concentration)
        _require_nonnegative_finite("minimum_lift_bps", self.minimum_lift_bps)

        # Splits must be non-overlapping and inside the overall date range.
        for name, split in self.splits.items():
            if not isinstance(split, Split):
                raise ValidationError(f"split '{name}' must be a Split; got {type(split)}")
            if split.start < self.start_date or split.end > self.end_date:
                raise ValidationError(
                    f"split '{name}' ({split.start} to {split.end}) must be within "
                    f"study range [{self.start_date}, {self.end_date}]"
                )
        split_names = list(self.splits.keys())
        for i in range(len(split_names)):
            for j in range(i + 1, len(split_names)):
                if self.splits[split_names[i]].overlaps(self.splits[split_names[j]]):
                    raise ValidationError(
                        f"splits '{split_names[i]}' and '{split_names[j]}' overlap"
                    )

        # Default to mandatory false; reject any attempt to set true.
        if self.production_promotion_eligible is not False:
            raise ValidationError("production_promotion_eligible must be false for this study")

        if self.baseline_definition not in {"frequency_matched", "unconditional"}:
            raise ValidationError(f"unknown baseline_definition {self.baseline_definition!r}")

        if not self.research_test_mode:
            _validate_locked_contract(self)

    @property
    def universe_hash(self) -> str:
        """SHA-256 of the ordered ticker list."""
        return _canonical_json_sha256(list(self.tickers))

    @property
    def sha256(self) -> str:
        """SHA-256 of the entire locked specification."""
        return _canonical_json_sha256(self.to_lock_dict())

    @property
    def decision_slippage_key(self) -> str:
        """Lossless string key for the decision slippage scenario."""
        s = float(self.decision_slippage_bps)
        return f"{int(s)}" if s.is_integer() else repr(s)

    def slippage_key(self, slippage_bps: float) -> str:
        """Lossless string key for an arbitrary slippage value in bps."""
        s = float(slippage_bps)
        return f"{int(s)}" if s.is_integer() else repr(s)

    def to_lock_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "tickers": list(self.tickers),
            "universe_hash": self.universe_hash,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "splits": {name: split.to_dict() for name, split in sorted(self.splits.items())},
            "event_types": list(self.event_types),
            "profile": self.profile,
            "runup_pct": self.runup_pct,
            "decline_pct": self.decline_pct,
            "move_days": self.move_days,
            "lookback_days": self.lookback_days,
            "min_events": self.min_events,
            "holding_days": self.holding_days,
            "similarity_threshold": self.similarity_threshold,
            "series_weights": dict(sorted(self.series_weights.items())),
            "slippage_scenarios_bps": list(self.slippage_scenarios_bps),
            "decision_slippage_bps": self.decision_slippage_bps,
            "commission_bps": self.commission_bps,
            "minimum_validation_signals": self.minimum_validation_signals,
            "minimum_holdout_signals": self.minimum_holdout_signals,
            "minimum_tickers": self.minimum_tickers,
            "max_ticker_concentration": self.max_ticker_concentration,
            "minimum_lift_bps": self.minimum_lift_bps,
            "bootstrap": self.bootstrap.to_dict(),
            "random_seed": self.random_seed,
            "baseline_definition": self.baseline_definition,
            "adjustment_policy": self.adjustment_policy,
            "universe_classification": self.universe_classification,
            "production_promotion_eligible": self.production_promotion_eligible,
            "research_test_mode": self.research_test_mode,
        }

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(_clean(self.to_lock_dict()), indent=indent, sort_keys=True, allow_nan=False)


@dataclass(frozen=True)
class ManifestEntry:
    """One ticker in the offline snapshot manifest."""

    ticker: str
    path: str
    sha256: str
    rows: int
    start: datetime | None
    end: datetime | None
    data_source: str
    adjustment_policy: str
    failure: str | None = None
    quality: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "quality", dict(self.quality))
        object.__setattr__(self, "warnings", list(self.warnings))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "path": self.path,
            "sha256": self.sha256,
            "rows": self.rows,
            "start": _iso(self.start),
            "end": _iso(self.end),
            "data_source": self.data_source,
            "adjustment_policy": self.adjustment_policy,
            "failure": self.failure,
            "quality": _clean(self.quality),
            "warnings": _clean(self.warnings),
        }


@dataclass(frozen=True)
class DatasetManifest:
    """Versioned offline snapshot manifest with temporal splits."""

    schema_version: int
    dataset_name: str
    created_at: datetime
    source_description: str
    provider: str
    adjustment_policy: str
    request_start: date
    request_end: date
    entries: tuple[ManifestEntry, ...]
    splits: dict[str, Split]
    requested_tickers: tuple[str, ...]
    successful_tickers: tuple[str, ...]
    failed_tickers: tuple[str, ...]
    failure_categories: tuple[str, ...]
    manifest_sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))
        object.__setattr__(self, "requested_tickers", tuple(self.requested_tickers))
        object.__setattr__(self, "successful_tickers", tuple(self.successful_tickers))
        object.__setattr__(self, "failed_tickers", tuple(self.failed_tickers))
        object.__setattr__(self, "failure_categories", tuple(self.failure_categories))
        object.__setattr__(
            self, "splits", FrozenMapping({k: Split(start=s.start, end=s.end) for k, s in self.splits.items()})
        )
        if not self.manifest_sha256:
            object.__setattr__(self, "manifest_sha256", _canonical_json_sha256(self.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "created_at": _iso(self.created_at),
            "source_description": self.source_description,
            "provider": self.provider,
            "adjustment_policy": self.adjustment_policy,
            "request_start": self.request_start.isoformat(),
            "request_end": self.request_end.isoformat(),
            "requested_tickers": list(self.requested_tickers),
            "successful_tickers": list(self.successful_tickers),
            "failed_tickers": list(self.failed_tickers),
            "failure_categories": list(self.failure_categories),
            "entries": [e.to_dict() for e in self.entries],
            "splits": {name: split.to_dict() for name, split in sorted(self.splits.items())},
            "manifest_sha256": self.manifest_sha256,
        }

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(_clean(self.to_dict()), indent=indent, sort_keys=True, allow_nan=False)

    def verify_integrity(self) -> bool:
        """Recompute the canonical SHA-256 and compare to the stored value."""
        d = self.to_dict()
        d["manifest_sha256"] = ""
        return _canonical_json_sha256(d) == self.manifest_sha256


@dataclass(frozen=True)
class Fingerprint:
    """A development-only fingerprint for one event type."""

    event_type: str
    profile: str
    source: str
    n_events: int
    ticker_count: int
    lookback_days: int
    earliest_event_date: date | None
    latest_event_date: date | None
    config_hash: str
    series: dict[str, dict[str, list[float]]]
    fingerprint_sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "series", {k: dict(v) for k, v in self.series.items()})
        if not self.fingerprint_sha256:
            object.__setattr__(self, "fingerprint_sha256", _canonical_json_sha256(self.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "profile": self.profile,
            "source": self.source,
            "n_events": self.n_events,
            "ticker_count": self.ticker_count,
            "lookback_days": self.lookback_days,
            "earliest_event_date": self.earliest_event_date.isoformat() if self.earliest_event_date else None,
            "latest_event_date": self.latest_event_date.isoformat() if self.latest_event_date else None,
            "config_hash": self.config_hash,
            "series": dict(sorted(self.series.items())),
            "fingerprint_sha256": self.fingerprint_sha256,
        }


@dataclass(frozen=True)
class Observation:
    """One point-in-time pattern-similarity observation with forward outcomes."""

    ticker: str
    split: str
    event_type: str
    decision_date: date
    signal_time: datetime
    similarity_score: float
    series_scores: dict[str, float]
    is_qualifying: bool
    data_source: str
    signal_close: float
    entry_date: date | None
    raw_entry_price: float | None
    exit_date: date | None
    raw_exit_price: float | None
    gross_return_pct: float | None
    net_return_pct_by_slippage: dict[str, float | None]
    outcome_status: Literal["complete", "insufficient_future_bars", "missing_signal_data"]

    def __post_init__(self) -> None:
        object.__setattr__(self, "series_scores", dict(self.series_scores))
        object.__setattr__(self, "net_return_pct_by_slippage", dict(self.net_return_pct_by_slippage))

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "ticker": self.ticker,
            "split": self.split,
            "event_type": self.event_type,
            "decision_date": self.decision_date.isoformat(),
            "signal_time": _iso(self.signal_time),
            "similarity_score": self.similarity_score,
            "series_scores": dict(self.series_scores),
            "is_qualifying": self.is_qualifying,
            "data_source": self.data_source,
            "signal_close": self.signal_close,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "raw_entry_price": self.raw_entry_price,
            "exit_date": self.exit_date.isoformat() if self.exit_date else None,
            "raw_exit_price": self.raw_exit_price,
            "gross_return_pct": self.gross_return_pct,
            "net_return_pct_by_slippage": dict(self.net_return_pct_by_slippage),
            "outcome_status": self.outcome_status,
        })


@dataclass(frozen=True)
class Trade:
    """One executable per-ticker simulated trade."""

    ticker: str
    split: str
    event_type: str
    decision_date: date
    entry_date: date
    exit_date: date
    signal_close: float
    raw_entry_price: float
    raw_exit_price: float
    gross_return_pct: float
    net_return_pct_by_slippage: dict[str, float | None]

    def __post_init__(self) -> None:
        object.__setattr__(self, "net_return_pct_by_slippage", dict(self.net_return_pct_by_slippage))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class TickerMetrics:
    """Per-ticker summary for one split/event-type."""

    ticker: str
    split: str
    event_type: str
    observations: int
    qualifying_signals: int
    executed_trades: int
    mean_gross_return_pct: float | None
    mean_net_return_pct: float | None  # decision slippage (event-study / qualifying)
    executable_mean_net_return_pct: float | None  # non-overlapping executable trades
    executable_win_rate: float | None
    mean_baseline_return_pct: float | None
    lift_bps: float | None
    win_rate: float | None

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class PeriodMetrics:
    """Aggregate metrics for one split/event-type."""

    split: str
    event_type: str
    eligible_observations: int
    qualifying_signals: int
    executed_trades: int
    ticker_count: int
    date_start: date | None
    date_end: date | None
    mean_similarity: float | None
    similarity_p05: float | None
    similarity_p25: float | None
    similarity_p50: float | None
    similarity_p75: float | None
    similarity_p95: float | None
    component_scores: dict[str, dict[str, float | None]]
    mean_gross_return_pct: float | None
    median_gross_return_pct: float | None
    mean_net_return_pct: float | None  # decision slippage
    median_net_return_pct: float | None
    win_rate: float | None  # qualifying-signal win rate
    executable_mean_net_return_pct: float | None  # non-overlapping executable trades
    executable_win_rate: float | None
    returns_by_slippage: dict[str, dict[str, float | None]]
    baseline_mean_return_pct: float | None
    baseline_lift_bps: float | None
    baseline_lift_ci_lower: float | None
    baseline_lift_ci_upper: float | None
    mean_return_ci_lower: float | None
    mean_return_ci_upper: float | None
    win_rate_lift: float | None
    max_ticker_concentration: float | None
    max_contribution_concentration: float | None
    overlap_count: int
    missing_data_count: int
    first_half_mean_return_pct: float | None
    second_half_mean_return_pct: float | None
    median_ticker_lift_bps: float | None
    pct_tickers_positive_lift: float | None
    control_selection_audit: list[dict[str, Any]] = field(default_factory=list)
    baseline_underfilled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "returns_by_slippage", {str(k): dict(v) for k, v in (self.returns_by_slippage or {}).items()})
        normalized_components: dict[str, dict[str, float | None]] = {}
        for key, dist in (self.component_scores or {}).items():
            normalized_components[str(key)] = {str(k): v for k, v in dict(dist).items()}
        object.__setattr__(self, "component_scores", normalized_components)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class DataQualityRow:
    """Per-ticker data-quality summary."""

    ticker: str
    data_source: str
    sha256: str
    manifest_rows: int
    validated_rows: int
    data_start: datetime | None
    data_end: datetime | None
    duplicate_timestamps: int
    missing_required_values: int
    invalid_ohlc_rows: int
    bars_outside_range: int
    complete_lookbacks: int
    complete_forward_bars: int
    eligible_observations_per_split: dict[str, int]
    split_event_counts: dict[str, int]
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "eligible_observations_per_split", dict(self.eligible_observations_per_split))
        object.__setattr__(self, "split_event_counts", dict(self.split_event_counts))
        object.__setattr__(self, "warnings", list(self.warnings))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["data_start"] = _iso(d["data_start"])
        d["data_end"] = _iso(d["data_end"])
        return _clean(d)


@dataclass(frozen=True)
class PromotionDecision:
    """Locked evidence classification and gate results."""

    classification: Literal["supported", "rejected", "inconclusive"]
    production_promotion_eligible: bool = False
    gate_results: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "gate_results", dict(self.gate_results))
        if self.production_promotion_eligible is not False:
            raise ValidationError("production_promotion_eligible must be false")
        if self.classification not in {"supported", "rejected", "inconclusive"}:
            raise ValidationError(f"classification must be supported/rejected/inconclusive; got {self.classification!r}")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class ControlAudit:
    """Audit record for one frequency-matched control selection group."""

    ticker: str
    split: str
    year: int
    event_type: str
    requested: int
    available: int
    selected: int
    underfilled: bool

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class BaselineSelection:
    """Frequency-matched or unconditional control selection with audit metadata."""

    controls: list[Observation] = field(default_factory=list)
    audit: list[ControlAudit] = field(default_factory=list)
    underfilled_keys: list[tuple[str, str, int, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "controls", list(self.controls))
        object.__setattr__(self, "audit", list(self.audit))
        object.__setattr__(self, "underfilled_keys", list(self.underfilled_keys))

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "controls": [o.to_dict() for o in self.controls],
            "audit": [a.to_dict() for a in self.audit],
            "underfilled_keys": list(self.underfilled_keys),
        })


@dataclass
class StudyResult:
    """Complete deterministic result for one pattern-similarity validation study."""

    spec: StudySpec
    manifest: DatasetManifest
    fingerprints: dict[str, Fingerprint]
    observations: pd.DataFrame
    qualifying_signals: pd.DataFrame
    frequency_matched_controls: pd.DataFrame
    event_study: pd.DataFrame
    executable_trades: pd.DataFrame
    ticker_summary: pd.DataFrame
    period_summary: pd.DataFrame
    baseline_comparison: pd.DataFrame
    data_quality: pd.DataFrame
    promotion_decision: PromotionDecision
    report_markdown: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "limitations", list(self.limitations))

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "schema_version": 1,
            "generated_at": _iso(self.generated_at),
            "spec": self.spec.to_lock_dict(),
            "spec_sha256": self.spec.sha256,
            "manifest": self.manifest.to_dict(),
            "fingerprints": {k: fp.to_dict() for k, fp in sorted(self.fingerprints.items())},
            "observations": self._df_records(self.observations),
            "qualifying_signals": self._df_records(self.qualifying_signals),
            "frequency_matched_controls": self._df_records(self.frequency_matched_controls),
            "event_study": self._df_records(self.event_study),
            "executable_trades": self._df_records(self.executable_trades),
            "ticker_summary": self._df_records(self.ticker_summary),
            "period_summary": self._df_records(self.period_summary),
            "baseline_comparison": self._df_records(self.baseline_comparison),
            "data_quality": self._df_records(self.data_quality),
            "promotion_decision": self.promotion_decision.to_dict(),
            "report_markdown": self.report_markdown,
            "limitations": self.limitations,
        })

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True, default=str, allow_nan=False)

    @staticmethod
    def _df_records(df: pd.DataFrame) -> list[dict[str, Any]]:
        if df is None or df.empty:
            return []
        return [_clean(r) for r in df.to_dict("records")]


def load_spec(path: str | Path, research_test_mode: bool | None = None) -> StudySpec:
    """Load a StudySpec from a JSON lock file."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # Reconstruct Split objects.
    data["splits"] = {name: Split(start=date.fromisoformat(s["start"]), end=date.fromisoformat(s["end"])) for name, s in data.get("splits", {}).items()}
    data["start_date"] = date.fromisoformat(data["start_date"])
    data["end_date"] = date.fromisoformat(data["end_date"])
    data["tickers"] = tuple(data["tickers"])
    data["event_types"] = tuple(data["event_types"])
    data["slippage_scenarios_bps"] = tuple(data["slippage_scenarios_bps"])
    data["series_weights"] = {k: float(v) for k, v in data["series_weights"].items()}
    data["bootstrap"] = BootstrapConfig(**data.get("bootstrap", {}))
    # Drop computed fields that are not constructor arguments.
    data.pop("universe_hash", None)
    data.pop("schema_version", None)
    if research_test_mode is not None:
        data["research_test_mode"] = research_test_mode
    return StudySpec(**data)


def load_manifest(path: str | Path) -> DatasetManifest:
    """Load a DatasetManifest from a JSON lock file."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    data["request_start"] = date.fromisoformat(data["request_start"])
    data["request_end"] = date.fromisoformat(data["request_end"])
    entries = []
    for e in data["entries"]:
        if e.get("start"):
            e["start"] = datetime.fromisoformat(e["start"])
        else:
            e["start"] = None
        if e.get("end"):
            e["end"] = datetime.fromisoformat(e["end"])
        else:
            e["end"] = None
        entries.append(ManifestEntry(**e))
    data["entries"] = tuple(entries)
    data["requested_tickers"] = tuple(data["requested_tickers"])
    data["successful_tickers"] = tuple(data["successful_tickers"])
    data["failed_tickers"] = tuple(data["failed_tickers"])
    data["failure_categories"] = tuple(data["failure_categories"])
    data["splits"] = {name: Split(start=date.fromisoformat(s["start"]), end=date.fromisoformat(s["end"])) for name, s in data.get("splits", {}).items()}
    return DatasetManifest(**data)
