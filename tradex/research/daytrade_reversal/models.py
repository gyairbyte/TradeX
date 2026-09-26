"""Data models and JSON-safe serialization for DAYTRADE-001C1."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from typing import Any


def sanitize_json_value(val: Any) -> Any:
    """Recursively convert float NaN/Inf to None so all serialized outputs are JSON-safe."""
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    if isinstance(val, dict):
        return {k: sanitize_json_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [sanitize_json_value(v) for v in val]
    if isinstance(val, tuple):
        return [sanitize_json_value(v) for v in val]
    if isinstance(val, (datetime, date, time)):
        return val.isoformat()
    return val


@dataclass(frozen=True)
class DaytradeBar:
    """A normalized 1-minute regular-session bar."""

    ticker: str
    session_date: date
    bar_start: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class DaytradeSession:
    """A collection of normalized bars for one ticker on one trading session."""

    ticker: str
    session_date: date
    bars: list[DaytradeBar] = field(default_factory=list)
    is_valid: bool = True
    exclusion_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DataQualityReport:
    """Quality evaluation record for a single ticker-session."""

    ticker: str
    session_date: date
    total_bars: int
    expected_bars: int
    missing_bars: int
    missing_rate_pct: float
    duplicate_bars: int
    duplicate_rate_pct: float
    malformed_timestamp_count: int
    excluded: bool
    exclusion_reasons: list[str]
    malformed_ohlcv_count: int = 0


@dataclass(frozen=True)
class SplitDataQualitySummary:
    """Summary of data-quality exclusions across a dataset split."""

    split: str
    total_ticker_sessions: int
    excluded_ticker_sessions: int
    excluded_rate_pct: float
    exceeds_split_gate: bool  # True if excluded_rate_pct > 5.0%
    exclusion_breakdown: dict[str, int]
    is_valid: bool = True


@dataclass(frozen=True)
class HorizonOutcome:
    """Calculated returns for a specific forward horizon (1m, 2m, or 5m)."""

    horizon_minutes: int
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    gross_return: float
    net_return_0bps: float
    net_return_2bps: float
    net_return_5bps: float


@dataclass
class EventObservation:
    """An identified extreme downside 1-minute event and its measured outcomes."""

    event_id: str
    ticker: str
    session_date: date
    split: str
    event_bar_start: datetime
    event_available_at: datetime
    event_return: float
    threshold: float
    outcomes: dict[int, HorizonOutcome] = field(default_factory=dict)
    analysis_window_start: datetime | None = None
    analysis_window_end: datetime | None = None
    is_overlapping: bool = False
    same_ticker_overlap: bool = False
    cross_ticker_overlap: bool = False
    matched_baseline_1m_net: float | None = None
    uplift_1m_net: float | None = None


@dataclass(frozen=True)
class BaselineObservation:
    """An eligible non-event intraday observation for matched control comparison."""

    ticker: str
    session_date: date
    split: str
    minute_of_day: str  # HH:MM ET
    bar_start: datetime
    available_at: datetime
    outcomes: dict[int, HorizonOutcome]


@dataclass(frozen=True)
class BootstrapCI:
    """Percentile bootstrap confidence interval results."""

    point_estimate: float | None
    ci_lower: float | None
    ci_upper: float | None
    resamples: int
    seed: int
    status: str  # "computable" | "non_computable"
    error_reason: str | None = None


@dataclass(frozen=True)
class GateEvaluationResult:
    """Evaluation result for one of the locked validation gates."""

    gate_name: str
    passed: bool
    detail: dict[str, Any]


@dataclass
class StudyResult:
    """Complete, self-contained record of a study execution on a split."""

    task_id: str
    split: str
    disposition: str  # "supported" | "rejected" | "inconclusive" | "invalid"
    disposition_step: str  # e.g., "step_1_invalidity", "step_2_evidence_sufficiency", etc.
    disposition_reason: str
    metrics: dict[str, Any] = field(default_factory=dict)
    gates: dict[str, GateEvaluationResult] = field(default_factory=dict)
    bootstrap: dict[str, Any] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    events: list[EventObservation] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        """Return a strictly JSON-safe dictionary representation."""
        raw = asdict(self)
        raw.pop("events", None)
        prov = raw.get("provenance", {})
        for k, v in prov.items():
            if k not in raw:
                raw[k] = v
        return sanitize_json_value(raw)
