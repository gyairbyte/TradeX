"""Typed models for the short-term market context layer."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ShortContextPolicy(str, Enum):
    """Eligibility-filter policies that wrap the existing short-term score."""

    OFF = "off"
    MARKET_RS = "market_rs"
    MARKET_SECTOR_RS = "market_sector_rs"


@dataclass(frozen=True)
class ShortTermMarketContext:
    """Point-in-time market and sector context for one short-term signal.

    All numeric values are the exact computed values before any display rounding.
    Boolean fields are ``None`` when the corresponding context cannot be computed.
    """

    as_of: datetime
    market_proxy: str
    sector_proxy: str | None

    market_regime_available: bool
    market_regime_bullish: bool | None

    sector_regime_available: bool
    sector_regime_bullish: bool | None

    market_relative_strength_available: bool
    market_relative_strength_positive: bool | None

    sector_relative_strength_available: bool
    sector_relative_strength_positive: bool | None

    market_close: float | None
    market_ema20: float | None
    market_ema50: float | None
    market_ema20_slope_5: float | None

    sector_close: float | None
    sector_ema20: float | None
    sector_ema50: float | None
    sector_ema20_slope_5: float | None

    market_rs_ratio: float | None
    market_rs_ema20: float | None
    market_rs_change_20_pct: float | None

    sector_rs_ratio: float | None
    sector_rs_ema20: float | None
    sector_rs_change_20_pct: float | None

    market_context_time: datetime | None = None
    sector_context_time: datetime | None = None

    available_contexts: tuple[str, ...] = ()
    missing_contexts: tuple[str, ...] = ()
    context_complete: bool = False
    errors: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        d = asdict(self)
        d["as_of"] = self.as_of.isoformat()
        if self.market_context_time is not None:
            d["market_context_time"] = self.market_context_time.isoformat()
        if self.sector_context_time is not None:
            d["sector_context_time"] = self.sector_context_time.isoformat()
        return d
