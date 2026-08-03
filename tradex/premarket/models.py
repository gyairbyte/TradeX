"""Typed data models for the quality-aware pre-market gap scanner."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from tradex.premarket.config import GapScanConfig

GAP_TIERS = {
    "massive": 8.0,
    "large": 4.0,
    "moderate": 2.0,
}

DEFAULT_MIN_GAP = 2.0

# Validated ticker contract shared by CLI, dashboard, and scanner.
# Tickers are 1-10 uppercase characters starting with a letter; dots and hyphens
# are allowed (e.g. BRK.B, BRK-B).  A leading '$' is stripped by callers.
VALID_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

# Stable primary outcome taxonomy for every requested ticker.
GAP_STATUS_QUALIFIED = "qualified"
GAP_STATUS_BELOW_GAP_THRESHOLD = "below_gap_threshold"
GAP_STATUS_PRICE_FILTERED = "price_filtered"
GAP_STATUS_LIQUIDITY_FILTERED = "liquidity_filtered"
GAP_STATUS_STALE_DATA = "stale_data"
GAP_STATUS_SPREAD_FILTERED = "spread_filtered"
GAP_STATUS_SPREAD_UNAVAILABLE = "spread_unavailable"
GAP_STATUS_CATALYST_FILTERED = "catalyst_filtered"
GAP_STATUS_NO_PREVIOUS_CLOSE = "no_previous_close"
GAP_STATUS_NO_PREMARKET_DATA = "no_premarket_data"
GAP_STATUS_PROVIDER_FAILURE = "provider_failure"
GAP_STATUS_CALCULATION_FAILURE = "calculation_failure"
GAP_STATUS_NON_TRADING_DAY = "non_trading_day"
GAP_STATUS_OUTSIDE_WINDOW = "outside_window"
GAP_STATUS_FILTERED = "filtered"
GAP_STATUS_FAILED = "failed"

_FILTER_STATUSES = {
    GAP_STATUS_BELOW_GAP_THRESHOLD,
    GAP_STATUS_PRICE_FILTERED,
    GAP_STATUS_LIQUIDITY_FILTERED,
    GAP_STATUS_STALE_DATA,
    GAP_STATUS_SPREAD_FILTERED,
    GAP_STATUS_SPREAD_UNAVAILABLE,
    GAP_STATUS_CATALYST_FILTERED,
    GAP_STATUS_FILTERED,
}

_FAILURE_STATUSES = {
    GAP_STATUS_NO_PREVIOUS_CLOSE,
    GAP_STATUS_NO_PREMARKET_DATA,
    GAP_STATUS_PROVIDER_FAILURE,
    GAP_STATUS_CALCULATION_FAILURE,
    GAP_STATUS_FAILED,
}

_OUTSIDE_WINDOW_STATUSES = {
    GAP_STATUS_NON_TRADING_DAY,
    GAP_STATUS_OUTSIDE_WINDOW,
}


@dataclass(frozen=True)
class PremarketBarsResult:
    """Result of an OHLCV fetch for the pre-market session."""

    ticker: str
    requested_provider: str | None
    actual_provider: str | None
    session_date: date | None
    bars: pd.DataFrame = field(repr=False)
    attempts: int = 0
    retries: int = 0
    error: Exception | None = None


@dataclass(frozen=True)
class PremarketSnapshot:
    """Summary statistics for a filtered pre-market bar set."""

    ticker: str
    session_date: date | None
    requested_provider: str | None
    actual_provider: str | None
    first_bar_time: datetime | None
    last_bar_time: datetime | None
    bar_count: int
    premarket_open: float | None
    premarket_high: float | None
    premarket_low: float | None
    premarket_last: float | None
    premarket_volume: int
    premarket_dollar_volume: float
    premarket_vwap: float | None
    data_age_minutes: float | None


@dataclass(frozen=True)
class DailyLiquidityBaseline:
    """Recent regular-session volume/dollar-volume reference for a ticker."""

    previous_session_date: date | None
    previous_close: float | None
    lookback_sessions_requested: int
    lookback_sessions_available: int
    average_daily_volume: float
    median_daily_volume: float
    average_daily_dollar_volume: float
    median_daily_dollar_volume: float
    requested_provider: str | None = None
    actual_provider: str | None = None
    error: Exception | None = None


@dataclass(frozen=True)
class SpreadSnapshot:
    """Optional bid/ask spread context for a pre-market quote."""

    available: bool
    requested_source: str | None = None
    actual_source: str | None = None
    bid: float | None = None
    ask: float | None = None
    midpoint: float | None = None
    spread_bps: float | None = None
    source: str | None = None
    as_of: datetime | None = None
    error: Exception | None = None


@dataclass(frozen=True)
class GapCatalystContext:
    """Explicitly sourced, non-causal context for a gap candidate."""

    ticker: str
    session_date: date | None
    requested_earnings_source: str | None = None
    actual_earnings_source: str | None = None
    earnings_status: str | None = None
    earnings_date: date | None = None
    requested_headline_source: str | None = None
    actual_headline_source: str | None = None
    headline_status: str | None = None
    headline_title: str | None = None
    headline_publisher: str | None = None
    headline_published_at: datetime | None = None
    headline_url: str | None = None
    days_until_earnings: int | None = None
    error: Exception | None = None

    @property
    def status(self) -> str:
        """Combined stable status for display."""
        if (
            self.earnings_status in ("earnings_today", "earnings_soon")
            and self.headline_status == "recent_headline"
        ):
            return "earnings_and_recent_headline"
        if self.earnings_status in ("earnings_today", "earnings_soon"):
            return self.earnings_status
        if self.headline_status == "recent_headline":
            return "recent_headline"
        if self.earnings_status == "unavailable" or self.headline_status == "unavailable":
            return "unavailable"
        if self.earnings_status == "none_detected" or self.headline_status == "none_detected":
            return "none_detected"
        if self.earnings_status == "not_requested" and self.headline_status == "not_requested":
            return "not_requested"
        return "not_requested"


@dataclass(frozen=True)
class GapObservation:
    """One per requested ticker; captures qualified, filtered, failed, or outside-window outcomes."""

    ticker: str
    session_date: date | None
    status: str  # qualified, filtered, failed, outside_window
    requested_provider: str | None
    actual_provider: str | None
    previous_session_date: date | None = None
    prev_close: float | None = None
    premarket_open: float | None = None
    premarket_high: float | None = None
    premarket_low: float | None = None
    premarket_last: float | None = None
    premarket_volume: int | None = None
    premarket_dollar_volume: float | None = None
    premarket_vwap: float | None = None
    premarket_move_pct: float | None = None
    premarket_range_pct: float | None = None
    first_bar_time: datetime | None = None
    last_bar_time: datetime | None = None
    bar_count: int | None = None
    data_age_minutes: float | None = None
    average_daily_volume: float | None = None
    median_daily_volume: float | None = None
    average_daily_dollar_volume: float | None = None
    median_daily_dollar_volume: float | None = None
    liquidity_lookback_sessions: int | None = None
    premarket_volume_ratio: float | None = None
    bid: float | None = None
    ask: float | None = None
    midpoint: float | None = None
    spread_bps: float | None = None
    spread_source: str | None = None
    spread_available: bool = False
    catalyst_status: str | None = None
    earnings_date: date | None = None
    days_until_earnings: int | None = None
    headline_title: str | None = None
    headline_publisher: str | None = None
    headline_published_at: datetime | None = None
    headline_source: str | None = None
    headline_url: str | None = None
    gap_pct: float | None = None
    direction: str | None = None
    tier: str | None = None
    note: str | None = None
    filter_reasons: list[str] = field(default_factory=list)
    error: str | None = None
    baseline_error: str | None = None
    premarket_error: str | None = None
    spread_error: str | None = None
    catalyst_error: str | None = None
    calculation_error: str | None = None


@dataclass
class GapScanReport:
    """Structured output of a pre-market gap scan."""

    session_date: date | None
    as_of: datetime | None
    requested_provider: str | None
    actual_provider: str | None
    config: GapScanConfig
    requested_tickers: list[str]
    results: pd.DataFrame = field(repr=False)
    observations: pd.DataFrame = field(repr=False)
    provider_errors: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.results = self._ensure_columns(self.results, _RESULT_COLUMNS)
        self.observations = self._ensure_columns(self.observations, _OBSERVATION_COLUMNS)

    @staticmethod
    def _ensure_columns(df: pd.DataFrame, columns: dict[str, Any]) -> pd.DataFrame:
        df = df.copy()
        for col, dtype in columns.items():
            if col not in df.columns:
                df[col] = pd.Series(dtype=dtype) if dtype is not None else None
        return df[[c for c in columns if c in df.columns]]

    @property
    def qualified(self) -> pd.DataFrame:
        """Alias for ``results``."""
        return self.results

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary with no NaN/Infinity literals."""
        return {
            "session_date": str(self.session_date) if self.session_date else None,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "requested_provider": self.requested_provider,
            "actual_provider": self.actual_provider,
            "config": self.config.to_dict(),
            "requested_tickers": self.requested_tickers,
            "counts": self.counts(),
            "results": _clean_records(self.results),
            "observations": _clean_records(self.observations),
            "provider_errors": self.provider_errors,
        }

    def counts(self) -> dict[str, int]:
        """Return requested, aggregated, and stage-specific outcome counts."""
        obs = self.observations
        statuses = obs["status"].tolist() if not obs.empty else []
        counts: dict[str, int] = {"requested": len(self.requested_tickers)}
        for status in _FILTER_STATUSES | _FAILURE_STATUSES | _OUTSIDE_WINDOW_STATUSES | {GAP_STATUS_QUALIFIED}:
            counts[status] = 0
        for status in statuses:
            counts[status] = counts.get(status, 0) + 1
        counts["qualified"] = counts.get(GAP_STATUS_QUALIFIED, 0)
        counts["filtered"] = sum(counts.get(s, 0) for s in _FILTER_STATUSES)
        counts["failed"] = sum(counts.get(s, 0) for s in _FAILURE_STATUSES)
        counts["outside_window"] = sum(counts.get(s, 0) for s in _OUTSIDE_WINDOW_STATUSES)

        # Stage-specific failure counts derived from stable observation fields.
        for col in ["baseline_error", "premarket_error", "spread_error", "catalyst_error", "calculation_error"]:
            col_values = obs[col] if not obs.empty else pd.Series(dtype="object")
            counts[col] = int(col_values.notna().sum())
        counts["baseline_failures"] = counts["baseline_error"]
        counts["premarket_failures"] = counts["premarket_error"]
        counts["spread_failures"] = counts["spread_error"]
        counts["catalyst_failures"] = counts["catalyst_error"]
        counts["calculation_failures"] = counts["calculation_error"]
        return counts


_COMMON_COLUMNS: dict[str, Any] = {
    "ticker": "string",
    "session_date": "string",
    "previous_session_date": "string",
    "prev_close": "float64",
    "pre_market": "float64",
    "premarket_last": "float64",
    "premarket_open": "float64",
    "premarket_high": "float64",
    "premarket_low": "float64",
    "premarket_volume": "int64",
    "premarket_dollar_volume": "float64",
    "premarket_vwap": "float64",
    "premarket_move_pct": "float64",
    "premarket_range_pct": "float64",
    "first_bar_time": "string",
    "last_bar_time": "string",
    "bar_count": "int64",
    "data_age_minutes": "float64",
    "average_daily_volume": "float64",
    "median_daily_volume": "float64",
    "average_daily_dollar_volume": "float64",
    "median_daily_dollar_volume": "float64",
    "liquidity_lookback_sessions": "int64",
    "premarket_volume_ratio": "float64",
    "bid": "float64",
    "ask": "float64",
    "midpoint": "float64",
    "spread_bps": "float64",
    "spread_source": "string",
    "spread_available": "bool",
    "catalyst_status": "string",
    "earnings_date": "string",
    "days_until_earnings": "int64",
    "headline_title": "string",
    "headline_publisher": "string",
    "headline_published_at": "string",
    "headline_source": "string",
    "headline_url": "string",
    "gap_pct": "float64",
    "direction": "string",
    "tier": "string",
    "note": "string",
    "filter_reasons": object,
    "error": "string",
    "baseline_error": "string",
    "premarket_error": "string",
    "spread_error": "string",
    "catalyst_error": "string",
    "calculation_error": "string",
    "requested_provider": "string",
    "actual_provider": "string",
    "status": "string",
}

_RESULT_COLUMNS = _COMMON_COLUMNS

_OBSERVATION_COLUMNS = {
    **_COMMON_COLUMNS,
    "status": "string",
}


def _clean_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to JSON-safe records, replacing non-finite floats."""
    if df.empty:
        return []
    records = df.to_dict("records")
    cleaned: list[dict[str, Any]] = []
    for row in records:
        cleaned.append({k: _clean_value(v) for k, v in row.items()})
    return cleaned


def _clean_value(value: Any) -> Any:
    if isinstance(value, float) and (pd.isna(value) or not _finite(value)):
        return None
    if value is pd.NA:
        return None
    if isinstance(value, list):
        return [_clean_value(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _finite(value: float) -> bool:
    import math

    return math.isfinite(value)
