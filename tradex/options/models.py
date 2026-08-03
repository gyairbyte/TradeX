"""Typed options data source, capability, and scan report models."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd


class OptionsDataKind(str, Enum):
    TRUE_FLOW = "true_flow"
    CHAIN_SNAPSHOT = "chain_snapshot"


class OptionsScanStatus(str, Enum):
    COMPLETED = "completed"
    NO_MATCHES = "no_matches"
    SOURCE_UNAVAILABLE = "source_unavailable"
    NOT_FLOW_CAPABLE = "not_flow_capable"
    PARTIAL_FAILURE = "partial_failure"
    COMPLETE_FAILURE = "complete_failure"


@dataclass(frozen=True)
class OptionsSourceStatus:
    """Immutable description of what an options source can and cannot provide."""

    requested_source: str
    actual_source: str | None
    configured: bool
    available: bool
    data_kind: OptionsDataKind | None
    freshness: str
    delayed: bool | None
    supports_event_timestamps: bool
    supports_trade_side: bool
    supports_premium: bool
    supports_sweeps: bool
    supports_chain_volume: bool
    supports_open_interest: bool
    limitations: tuple[str, ...]
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_source": self.requested_source,
            "actual_source": self.actual_source,
            "configured": self.configured,
            "available": self.available,
            "data_kind": self.data_kind.value if self.data_kind else None,
            "freshness": self.freshness,
            "delayed": self.delayed,
            "supports_event_timestamps": self.supports_event_timestamps,
            "supports_trade_side": self.supports_trade_side,
            "supports_premium": self.supports_premium,
            "supports_sweeps": self.supports_sweeps,
            "supports_chain_volume": self.supports_chain_volume,
            "supports_open_interest": self.supports_open_interest,
            "limitations": list(self.limitations),
            "error": self.error,
        }


@dataclass
class OptionsActivityReport:
    """Structured, deterministic, JSON-safe scan result for options activity."""

    requested_source: str
    actual_source: str | None
    data_kind: OptionsDataKind | None
    status: OptionsScanStatus
    results: pd.DataFrame
    source_status: OptionsSourceStatus
    total_requested: int
    total_fetched: int
    total_matches: int
    failures: Mapping[str, str]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_source": self.requested_source,
            "actual_source": self.actual_source,
            "data_kind": self.data_kind.value if self.data_kind else None,
            "status": self.status.value,
            "source_status": self.source_status.to_dict(),
            "total_requested": self.total_requested,
            "total_fetched": self.total_fetched,
            "total_matches": self.total_matches,
            "failures": dict(self.failures),
            "limitations": list(self.limitations),
            "results": _records_from_frame(self.results),
        }


def _records_from_frame(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Return a JSON-safe list of records with NaN/Infinity converted to None."""
    if df.empty:
        return []
    records = []
    for row in df.to_dict(orient="records"):
        safe: dict[str, Any] = {}
        for key, value in row.items():
            if pd.isna(value) or (isinstance(value, float) and not math.isfinite(value)):
                safe[key] = None
            else:
                safe[key] = value
        records.append(safe)
    return records
