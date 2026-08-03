"""Typed, validated configuration for the pre-market gap scanner."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GapScanConfig:
    """Immutable quality controls for a pre-market gap scan.

    All thresholds are opt-in; defaults preserve the original 2% minimum absolute
    gap behavior with no liquidity, spread, freshness, or catalyst filtering.
    """

    min_abs_gap_pct: float = 2.0
    min_price: float = 0.0
    min_premarket_volume: int = 0
    min_premarket_dollar_volume: float = 0.0
    min_premarket_volume_ratio: float = 0.0
    max_data_age_minutes: float | None = None
    max_spread_bps: float | None = None
    require_spread: bool = False
    require_catalyst: bool = False
    catalyst_lookback_hours: float = 24.0
    liquidity_lookback_sessions: int = 20
    allow_after_open: bool = False

    def __post_init__(self) -> None:
        _require_finite_nonnegative("min_abs_gap_pct", self.min_abs_gap_pct)
        _require_finite_nonnegative("min_price", self.min_price)
        _require_nonnegative_int("min_premarket_volume", self.min_premarket_volume)
        _require_finite_nonnegative("min_premarket_dollar_volume", self.min_premarket_dollar_volume)
        _require_finite_nonnegative("min_premarket_volume_ratio", self.min_premarket_volume_ratio)

        if self.max_data_age_minutes is not None:
            _require_positive_finite("max_data_age_minutes", self.max_data_age_minutes)
        if self.max_spread_bps is not None:
            _require_positive_finite("max_spread_bps", self.max_spread_bps)

        _require_bool("require_spread", self.require_spread)
        _require_bool("require_catalyst", self.require_catalyst)

        _require_positive_finite("catalyst_lookback_hours", self.catalyst_lookback_hours)
        _require_int_min("liquidity_lookback_sessions", self.liquidity_lookback_sessions, minimum=5)
        _require_bool("allow_after_open", self.allow_after_open)

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_abs_gap_pct": self.min_abs_gap_pct,
            "min_price": self.min_price,
            "min_premarket_volume": self.min_premarket_volume,
            "min_premarket_dollar_volume": self.min_premarket_dollar_volume,
            "min_premarket_volume_ratio": self.min_premarket_volume_ratio,
            "max_data_age_minutes": self.max_data_age_minutes,
            "max_spread_bps": self.max_spread_bps,
            "require_spread": self.require_spread,
            "require_catalyst": self.require_catalyst,
            "catalyst_lookback_hours": self.catalyst_lookback_hours,
            "liquidity_lookback_sessions": self.liquidity_lookback_sessions,
            "allow_after_open": self.allow_after_open,
        }


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _require_bool(name: str, value: Any) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool; got {type(value).__name__}")


def _require_finite_nonnegative(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite number; got {type(value).__name__}")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative; got {value}")


def _require_nonnegative_int(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer; got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative; got {value}")


def _require_positive_finite(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite positive number; got {type(value).__name__}")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive; got {value}")


def _require_int_min(name: str, value: Any, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer; got {type(value).__name__}")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}; got {value}")
