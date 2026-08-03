"""Typed data models for the quality-aware pre-market gap scanner."""
from __future__ import annotations

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


@dataclass(frozen=True)
class SpreadSnapshot:
    """Optional bid/ask spread context for a pre-market quote."""

    available: bool
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
    headline_published_at: datetime | None = None
    headline_url: str | None = None
    error: Exception | None = None

    @property
    def status(self) -> str:
        """Combined stable status for display."""
        if self.earnings_status in ("earnings_today",) and self.headline_status == "recent_headline":
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
    prev_close: float | None = None
    premarket_last: float | None = None
    premarket_open: float | None = None
    premarket_high: float | None = None
    premarket_low: float | None = None
    premarket_volume: int | None = None
    premarket_dollar_volume: float | None = None
    premarket_vwap: float | None = None
    data_age_minutes: float | None = None
    average_daily_volume: float | None = None
    premarket_volume_ratio: float | None = None
    spread_bps: float | None = None
    spread_available: bool = False
    catalyst_status: str | None = None
    filter_reasons: list[str] = field(default_factory=list)
    error: str | None = None
    gap_pct: float | None = None
    direction: str | None = None
    tier: str | None = None
    note: str | None = None


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
        """Requested, qualified, filtered, failed, and outside-window counts."""
        obs = self.observations
        return {
            "requested": len(self.requested_tickers),
            "qualified": len(obs[obs["status"] == "qualified"]),
            "filtered": len(obs[obs["status"] == "filtered"]),
            "failed": len(obs[obs["status"] == "failed"]),
            "outside_window": len(obs[obs["status"] == "outside_window"]),
        }


_COMMON_COLUMNS: dict[str, Any] = {
    "ticker": "string",
    "session_date": "string",
    "prev_close": "float64",
    "pre_market": "float64",
    "premarket_last": "float64",
    "premarket_open": "float64",
    "premarket_high": "float64",
    "premarket_low": "float64",
    "premarket_volume": "int64",
    "premarket_dollar_volume": "float64",
    "premarket_vwap": "float64",
    "data_age_minutes": "float64",
    "average_daily_volume": "float64",
    "premarket_volume_ratio": "float64",
    "spread_bps": "float64",
    "spread_available": "bool",
    "catalyst_status": "string",
    "gap_pct": "float64",
    "direction": "string",
    "tier": "string",
    "note": "string",
    "filter_reasons": object,
    "error": "string",
    "requested_provider": "string",
    "actual_provider": "string",
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
