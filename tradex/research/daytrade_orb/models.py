"""Typed immutable domain models for the deterministic research-only ORB evaluator."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

MARKET_TIMEZONE = ZoneInfo("America/New_York")



class Direction(str, Enum):
    """Direction of the opening range breakout setup."""

    LONG = "LONG"
    SHORT = "SHORT"
    DOJI = "DOJI"


class ExitReason(str, Enum):
    """Reason for closing an executed trade."""

    STOP_LOSS = "STOP_LOSS"
    END_OF_DAY = "END_OF_DAY"


class OrderStatus(str, Enum):
    """Lifecycle status of an opening range breakout order intent."""

    NO_ORDER_DOJI = "NO_ORDER_DOJI"
    ORDER_NOT_TRIGGERED = "ORDER_NOT_TRIGGERED"
    FILLED = "FILLED"
    CAPACITY_REJECTED = "CAPACITY_REJECTED"
    NON_COMPUTABLE = "NON_COMPUTABLE"


class ValidationDisposition(str, Enum):
    """Prospective validation disposition taxonomy."""

    INVALID = "INVALID"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    PROMISING_NOT_CONFIRMED = "PROMISING_NOT_CONFIRMED"
    SUPPORTED = "SUPPORTED"


class HoldoutAccessDeniedError(RuntimeError):
    """Raised when holdout data or partition access is requested without SUPPORTED validation."""


class DataIntegrityError(ValueError):
    """Raised when bar, universe, or session data fails strict integrity checks."""


@dataclass(frozen=True)
class DailyBar:
    """Immutable daily price/volume bar."""

    symbol: str
    session_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise DataIntegrityError("DailyBar symbol must be a non-empty string")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise DataIntegrityError(
                f"DailyBar prices must be strictly positive for {self.symbol} on {self.session_date}: "
                f"O={self.open}, H={self.high}, L={self.low}, C={self.close}"
            )
        if self.high < max(self.open, self.close):
            raise DataIntegrityError(
                f"DailyBar high {self.high} must be >= max(open={self.open}, close={self.close}) for {self.symbol}"
            )
        if self.low > min(self.open, self.close):
            raise DataIntegrityError(
                f"DailyBar low {self.low} must be <= min(open={self.open}, close={self.close}) for {self.symbol}"
            )
        if self.volume < 0:
            raise DataIntegrityError(
                f"DailyBar volume must be non-negative for {self.symbol}: {self.volume}"
            )


@dataclass(frozen=True)
class MinuteBar:
    """Immutable 1-minute intraday price/volume bar."""

    symbol: str
    timestamp: datetime
    session_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise DataIntegrityError("MinuteBar symbol must be a non-empty string")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if self.timestamp.tzinfo is None:
            raise DataIntegrityError(
                f"MinuteBar timestamp must be timezone-aware for {self.symbol} at {self.timestamp}"
            )
        ny_date = self.timestamp.astimezone(MARKET_TIMEZONE).date()
        if ny_date != self.session_date:
            raise DataIntegrityError(
                f"MinuteBar New York date {ny_date} does not match session_date {self.session_date} for {self.symbol}"
            )
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise DataIntegrityError(
                f"MinuteBar prices must be strictly positive for {self.symbol} at {self.timestamp}: "
                f"O={self.open}, H={self.high}, L={self.low}, C={self.close}"
            )
        if self.high < max(self.open, self.close):
            raise DataIntegrityError(
                f"MinuteBar high {self.high} must be >= max(open={self.open}, close={self.close}) for {self.symbol}"
            )
        if self.low > min(self.open, self.close):
            raise DataIntegrityError(
                f"MinuteBar low {self.low} must be <= min(open={self.open}, close={self.close}) for {self.symbol}"
            )
        if self.volume < 0:
            raise DataIntegrityError(
                f"MinuteBar volume must be non-negative for {self.symbol}: {self.volume}"
            )


@dataclass(frozen=True)
class OpeningRangeVolumeObservation:
    """Historical opening-range volume observation for Relative Volume calculation."""

    symbol: str
    session_date: date
    volume: float

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise DataIntegrityError(
                "OpeningRangeVolumeObservation symbol must be a non-empty string"
            )
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if self.volume < 0:
            raise DataIntegrityError(
                f"OpeningRangeVolumeObservation volume must be non-negative for {self.symbol}: {self.volume}"
            )



@dataclass(frozen=True)
class UniverseMember:
    """Point-in-time universe member active as of a session date."""

    symbol: str
    primary_exchange: str
    active_on_date: bool
    security_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OpeningRange:
    """Evaluated first 5-minute regular-session opening range (09:30-09:34)."""

    symbol: str
    session_date: date
    or_open: float
    or_high: float
    or_low: float
    or_close: float
    or_volume: float
    direction: Direction
    stop_level: float | None


@dataclass(frozen=True)
class Candidate:
    """Filter evaluation result for a single universe member as of 09:35."""

    symbol: str
    session_date: date
    opening_price: float
    adv14: float
    atr14: float
    or_volume: float
    mean_prior_or_volume: float
    relative_volume: float
    price_passed: bool
    adv_passed: bool
    atr_passed: bool
    rv_passed: bool
    is_eligible: bool
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrderIntent:
    """Sized stop-entry order intent created at 09:35 ET."""

    symbol: str
    session_date: date
    direction: Direction
    stop_level: float | None
    atr14: float
    protective_stop_offset: float
    desired_shares: int
    risk_per_share: float
    status: OrderStatus
    reason: str = ""


@dataclass(frozen=True)
class RankedCandidate:
    """Top-20 ranked candidate holding its evaluated opening range and order intent."""

    rank: int
    candidate: Candidate
    opening_range: OpeningRange
    order_intent: OrderIntent


@dataclass(frozen=True)
class Trade:
    """Completed execution record for a triggered position."""

    symbol: str
    direction: Direction
    session_date: date
    entry_timestamp: datetime
    raw_entry_price: float
    exit_timestamp: datetime
    raw_exit_price: float
    shares: int
    protective_stop_price: float
    exit_reason: ExitReason
    same_bar_ambiguity: bool
    gross_pnl: float
    entry_commission: float
    exit_commission: float
    total_commission: float
    entry_slippage_cost_a: float
    exit_slippage_cost_a: float
    net_pnl_a: float
    entry_slippage_cost_b: float
    exit_slippage_cost_b: float
    net_pnl_b: float
    entry_slippage_cost_c: float
    exit_slippage_cost_c: float
    net_pnl_c: float
    r_multiple: float


@dataclass(frozen=True)
class SessionResult:
    """Summary result of simulating one trading session."""

    session_date: date
    is_valid: bool
    status: str
    error_reason: str | None
    candidate_count: int
    qualified_candidate_count: int
    top_20_count: int
    orders_placed_count: int
    trades_triggered_count: int
    capacity_rejected_count: int
    trades: tuple[Trade, ...]
    session_start_equity: float
    session_end_equity_a: float
    session_end_equity_b: float
    session_end_equity_c: float
    session_net_pnl_a: float
    session_net_pnl_b: float
    session_net_pnl_c: float
    session_net_return_a: float
    session_net_return_b: float
    session_net_return_c: float
    max_gross_exposure: float
    max_leverage_used: float
    same_bar_ambiguity_count: int


@dataclass(frozen=True)
class DataQualityIssue:
    """Record of a data quality or completeness issue."""

    symbol: str | None
    session_date: date | None
    issue_type: str
    description: str


@dataclass(frozen=True)
class BootstrapCI:
    """Result of a block bootstrap confidence interval calculation."""

    point_estimate: float | None
    ci_lower: float | None
    ci_upper: float | None
    resamples: int
    seed: int
    status: str
    error_reason: str | None = None


@dataclass(frozen=True)
class GateEvaluationResult:
    """Result of evaluating a single validation gate."""

    gate_name: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StudyMetrics:
    """Aggregated portfolio and execution metrics across sessions."""

    total_sessions_included: int
    trading_sessions_count: int
    zero_trade_sessions_count: int
    qualified_candidates_count: int
    selected_top_20_count: int
    orders_placed_count: int
    triggered_trades_count: int
    capacity_rejected_count: int
    long_trades_count: int
    short_trades_count: int
    wins_count: int
    losses_count: int
    win_rate: float
    gross_pnl: float
    net_pnl_a: float
    net_pnl_b: float
    net_pnl_c: float
    mean_r_multiple: float
    median_r_multiple: float
    stop_out_rate: float
    eod_exit_rate: float
    same_bar_ambiguity_count: int
    non_computable_count: int
    max_gross_exposure: float
    max_leverage_used: float
    mean_daily_return_a: float
    mean_daily_return_b: float
    mean_daily_return_c: float
    cumulative_net_return_b: float
    annualized_return_b: float
    annualized_volatility_b: float
    sharpe_ratio_b: float
    max_drawdown_b: float
    worst_day_return_b: float
    daily_turnover: float


@dataclass(frozen=True)
class StudyResult:
    """Overall study result across all evaluated sessions."""

    study_name: str
    session_results: tuple[SessionResult, ...]
    metrics: StudyMetrics
    bootstrap_ci: BootstrapCI
    disposition: ValidationDisposition
    disposition_step: str
    disposition_reason: str
    gates: dict[str, GateEvaluationResult]


@dataclass(frozen=True)
class HoldoutAccessProof:
    """Cryptographic/token proof verifying holdout authorization."""

    validation_disposition: str
    authorized: bool
    proof_timestamp: datetime
