"""Data models and JSON-safe serialization for DAYTRADE-002B."""
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


class HoldoutAccessDeniedError(PermissionError):
    """Raised when holdout data access is requested without satisfying all validation prerequisites."""


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

    def get_bar_by_time(self, t: time) -> DaytradeBar | None:
        """Find bar whose local ET start time matches t."""
        for b in self.bars:
            if b.bar_start.time() == t:
                return b
        return None

    def get_15_59_close(self) -> float | None:
        """Return close of 15:59 ET minute bar if valid, finite, and positive."""
        bar = self.get_bar_by_time(time(15, 59))
        if bar is not None and not math.isnan(bar.close) and not math.isinf(bar.close) and bar.close > 0:
            return bar.close
        return None

    def get_09_59_close(self) -> float | None:
        """Return close of 09:59 ET minute bar if valid, finite, and positive."""
        bar = self.get_bar_by_time(time(9, 59))
        if bar is not None and not math.isnan(bar.close) and not math.isinf(bar.close) and bar.close > 0:
            return bar.close
        return None

    def get_15_30_open(self) -> float | None:
        """Return open of 15:30 ET minute bar if valid, finite, and positive."""
        bar = self.get_bar_by_time(time(15, 30))
        if bar is not None and not math.isnan(bar.open) and not math.isinf(bar.open) and bar.open > 0:
            return bar.open
        return None


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


@dataclass
class EventObservation:
    """A qualified early-to-late intraday momentum event."""

    ticker: str
    session_date: date
    direction: str  # 'LONG' or 'SHORT'
    signal_return: float
    threshold: float
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    gross_return: float
    net_return_0bps: float
    net_return_2bps: float
    net_return_5bps: float
    matched_baseline_net_2bps: float | None = None
    uplift_net_2bps: float | None = None
    split: str = ""


@dataclass(frozen=True)
class BaselineObservation:
    """A qualified non-event session for matched baseline comparison."""

    ticker: str
    session_date: date
    direction: str  # 'LONG' or 'SHORT' (based on first_half_hour_return sign)
    signal_return: float
    threshold: float
    entry_price: float
    exit_price: float
    gross_return: float
    net_return_0bps: float
    net_return_2bps: float
    net_return_5bps: float
    split: str = ""


@dataclass(frozen=True)
class BootstrapCI:
    """Confidence interval from deterministic cluster bootstrap."""

    point_estimate: float | None
    ci_lower: float | None
    ci_upper: float | None
    resamples: int
    seed: int
    status: str  # 'computable' or 'non_computable'
    error_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateEvaluationResult:
    """Outcome of a single validation gate evaluation."""

    gate_name: str
    passed: bool
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StudyResult:
    """Comprehensive results for a dataset split evaluation."""

    task_id: str
    study_name: str
    split: str
    disposition: str  # 'supported', 'rejected', 'inconclusive', 'invalid'
    disposition_step: str  # 'step_1_invalidity', 'step_2_evidence_sufficiency', etc.
    disposition_reason: str
    gates: dict[str, GateEvaluationResult]
    metrics: dict[str, Any]
    bootstrap: dict[str, Any]
    quality_summary: SplitDataQualitySummary
    provenance: dict[str, Any]
    events: list[EventObservation] = field(default_factory=list)
    non_events: list[BaselineObservation] = field(default_factory=list)
    quality_reports: list[DataQualityReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-safe dictionary representation."""
        return sanitize_json_value({
            "task_id": self.task_id,
            "study_name": self.study_name,
            "split": self.split,
            "disposition": self.disposition,
            "disposition_step": self.disposition_step,
            "disposition_reason": self.disposition_reason,
            "gates": {k: v.to_dict() for k, v in self.gates.items()},
            "metrics": self.metrics,
            "bootstrap": self.bootstrap,
            "quality_summary": asdict(self.quality_summary),
            "provenance": self.provenance,
        })
