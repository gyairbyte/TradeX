"""Typed models for the INTRA-001C intraday research engine."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

import numpy as np


@dataclass
class Bar:
    """One completed five-minute bar, stored with UTC timestamps."""

    bar_start: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_valid: bool = True
    invalid_reasons: list[str] = field(default_factory=list)
    typical_price: float | None = None
    cum_price_volume: float | None = None
    cum_volume: float | None = None
    vwap: float | None = None

    def __post_init__(self) -> None:
        if self.bar_start.tzinfo is None or self.available_at.tzinfo is None:
            raise ValueError("Bar timestamps must be timezone-aware")


@dataclass
class Session:
    """A single regular XNYS trading session."""

    session_date: date
    opens_at: datetime
    closes_at: datetime
    is_early_close: bool
    grid: list[datetime]
    bars: dict[datetime, Bar] = field(default_factory=dict)
    quality_counts: dict[str, int] = field(default_factory=dict)
    missing_bars: list[datetime] = field(default_factory=list)

    def expected_count(self) -> int:
        return len(self.grid)

    def valid_bar_count(self) -> int:
        return sum(1 for b in self.bars.values() if b.is_valid)


@dataclass
class TickerMeta:
    """Point-in-time metadata for one ticker used by the engine."""

    ticker: str
    is_etf: bool
    is_eligible: bool
    prior_close: float | None = None
    prior_20_median_dollar_volume: float | None = None
    security_type: str = "common_stock"


@dataclass
class OpeningDriveState:
    """Frozen 10:00 AM opening-drive qualification state."""

    qualified: bool
    return_pct: float | None
    close_at_10am: float | None
    vwap_at_10am: float | None
    cumulative_volume: float | None
    median_prior_cumulative_volume: float | None
    volume_multiple: float | None
    missing_bars: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class CostScenario:
    """Adverse per-side cost assumption."""

    name: str
    entry_slippage_bps: float
    exit_slippage_bps: float
    entry_commission_bps: float = 0.0
    exit_commission_bps: float = 0.0

    def entry_fill(self, entry_open: float) -> float:
        return entry_open * (
            1 + self.entry_slippage_bps / 10000 + self.entry_commission_bps / 10000
        )

    def exit_fill(self, raw_exit_price: float) -> float:
        return raw_exit_price * (
            1 - self.exit_slippage_bps / 10000 - self.exit_commission_bps / 10000
        )


@dataclass
class Signal:
    """A detected but not necessarily executed signal."""

    ticker: str
    session_date: date
    strategy: str
    signal_bar_start: datetime
    signal_time: datetime
    opening_drive_qualified: bool | None
    score: float | None
    stop_price: float | None
    target_price: float | None
    entry_open: float | None
    entry_fill: float | None
    risk_per_share: float | None
    status: Literal[
        "executed",
        "no_signal",
        "rejected_no_next_bar",
        "rejected_entry_at_or_below_stop",
        "rejected_nonpositive_risk",
        "rejected_no_time_exit_fallback",
    ]
    reason: str | None = None
    trade: Trade | None = None


@dataclass
class Trade:
    """One executed trade."""

    ticker: str
    session_date: date
    strategy: str
    signal_time: datetime
    signal_bar_start: datetime
    entry_time: datetime
    entry_bar_start: datetime
    entry_open: float
    entry_fill: float
    stop_price: float
    target_price: float
    risk_per_share: float
    exit_time: datetime | None
    exit_bar_start: datetime | None
    raw_exit_price: float | None
    exit_fill: float | None
    profit: float | None
    net_r: float | None
    exit_type: str | None
    same_bar_ambiguity: bool
    entry_bar_index: int | None = None
    exit_bar_index: int | None = None
    holding_minutes: float = 0.0
    opening_gap_pct: float | None = None
    fallback_reason: str | None = None
    status: Literal["executed", "rejected"] = "executed"
    rejection_reason: str | None = None


@dataclass
class PerSymbolMetrics:
    """Aggregated metrics for a represented symbol."""

    ticker: str
    is_etf: bool
    trade_count: int
    total_return: float
    mean_expectancy: float
    gross_profit: float
    gross_loss: float
    profit_factor_value: float | None
    profit_factor_case: str
    profit_factor_order: float | None
    maximum_drawdown_pct: float
    equity_curve: list[float]
    positive: bool


@dataclass
class StudyMetrics:
    """Aggregate metrics for one strategy under one cost scenario."""

    strategy: str
    cost_scenario: CostScenario
    total_signals: int
    executed_trades: int
    rejected_signals: int
    no_signal_count: int
    total_trades: int
    pooled_expectancy: float
    pooled_total_return: float
    overall_maximum_drawdown_pct: float
    median_per_symbol_expectancy: float | None
    equal_weighted_per_symbol_mean_expectancy: float | None
    positive_symbol_rate: float | None
    median_per_symbol_total_return: float | None
    median_per_symbol_maximum_drawdown_pct: float | None
    median_per_symbol_profit_factor_order: float | None
    median_per_symbol_profit_factor_value: float | None
    trade_count_concentration: float
    net_profit_concentration: float | None
    absolute_loss_concentration: float | None
    stock_stratum_trade_count: int
    etf_stratum_trade_count: int
    stock_stratum_pooled_expectancy: float
    etf_stratum_pooled_expectancy: float
    represented_stock_symbols: int
    represented_etf_symbols: int
    rejection_counts: dict[str, int] = field(default_factory=dict)
    exit_counts: dict[str, int] = field(default_factory=dict)
    positive_trade_rate: float | None = None
    average_holding_minutes: float | None = None
    per_symbol: dict[str, PerSymbolMetrics] = field(default_factory=dict)


@dataclass
class GateResult:
    """Outcome of one validation gate."""

    gate: str
    passed: bool | None
    reason: str


@dataclass
class StudyOutcome:
    """Overall study outcome."""

    disposition: Literal["supported", "not_supported", "inconclusive", "invalid"]
    reason: str
    gate_results: list[GateResult]
    sample_met: bool


@dataclass
class StudyResult:
    """Container for a complete synthetic or real-data evaluation."""

    spec_sha256: str
    engine_version: str
    synthetic: bool
    evidence_eligible: bool
    generated_at: datetime
    cost_scenarios: dict[str, StudyMetrics]
    candidate_signals: list[Signal]
    baseline_a_signals: list[Signal]
    baseline_b_signals: list[Signal]
    trades: dict[str, list[Trade]]
    report_markdown: str
    generated_at_fixed: bool = False
    metrics_by_strategy: dict[str, dict[str, StudyMetrics]] = field(default_factory=dict)
    data_quality_summaries: list[DataQualitySummary] = field(default_factory=list)
    monthly_metrics: dict[str, StudyMetrics] = field(default_factory=dict)
    gap_bucket_metrics: dict[str, StudyMetrics] = field(default_factory=dict)
    outcome: StudyOutcome | None = None
    invalid_reasons: list[str] = field(default_factory=list)


@dataclass
class DataQualitySummary:
    """Observability counts produced during normalization."""

    ticker: str
    total_rows: int
    duplicate_timestamps: int
    naive_timestamps: int
    off_grid_bars: int
    invalid_ohlc_rows: int
    non_finite_rows: int
    zero_volume_bars: int
    missing_bars: int
    valid_bars: int
    sessions: int
    pre_normalization_metrics_available: bool | None = None
    effective_month: str | None = None
    pagination_complete: bool | None = None
    symbol_mismatch: bool | None = None
    file_sha256_match: bool | None = None
    requested_symbol: str | None = None
    returned_symbol: str | None = None


def _json_clean(value: Any) -> Any:
    """Convert numpy/pandas/float artifacts to JSON-safe values."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return None
        return value
    if isinstance(value, np.floating):
        f = float(value)
        if math.isnan(f):
            return None
        if math.isinf(f):
            return None
        return f
    if isinstance(value, (list, tuple)):
        return [as_json_dict(v) for v in value]
    if isinstance(value, dict):
        return {k: as_json_dict(v) for k, v in value.items()}
    if isinstance(value, set):
        return sorted(as_json_dict(v) for v in value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def as_json_dict(obj: Any) -> Any:
    """Recursively convert dataclasses and primitives to a JSON-safe dict."""
    from dataclasses import asdict, is_dataclass

    if is_dataclass(obj):
        return as_json_dict(asdict(obj))
    return _json_clean(obj)
