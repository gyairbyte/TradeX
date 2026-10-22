"""Data models and enums for market opportunity discovery (LONG-MVP-003)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

import pandas as pd


class Scope(str, Enum):
    """Supported scan scopes for opportunity discovery."""

    MY_WATCHLIST = "My Watchlist"
    SP500 = "S&P 500"
    NASDAQ100 = "Nasdaq 100"
    ALL_US_STOCKS = "All U.S. Listed Stocks"


class ScanStatus(str, Enum):
    """High-level discovery scan execution status."""

    NOT_STARTED = "NOT STARTED"
    IN_PROGRESS = "IN PROGRESS"
    COMPLETE = "COMPLETE"
    COMPLETE_WITH_FAILURES = "COMPLETE WITH FAILURES"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    STALE = "STALE"


@dataclass(frozen=True)
class UniverseProvenance:
    """Provenance and audit metadata for a resolved ticker universe."""

    universe_id: str
    scope: Scope
    source_urls: tuple[str, ...]
    retrieval_timestamp: str
    source_file_generation_timestamp: str | None
    snapshot_hash: str
    original_listing_counts: dict[str, int]
    included_ticker_count: int
    excluded_counts_by_reason: dict[str, int]
    unsupported_symbol_count: int
    unsupported_symbols: tuple[str, ...] = ()
    is_stale: bool = False
    stale_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe_id": self.universe_id,
            "scope": self.scope.value,
            "source_urls": list(self.source_urls),
            "retrieval_timestamp": self.retrieval_timestamp,
            "source_file_generation_timestamp": self.source_file_generation_timestamp,
            "snapshot_hash": self.snapshot_hash,
            "original_listing_counts": dict(self.original_listing_counts),
            "included_ticker_count": self.included_ticker_count,
            "excluded_counts_by_reason": dict(self.excluded_counts_by_reason),
            "unsupported_symbol_count": self.unsupported_symbol_count,
            "unsupported_symbols": list(self.unsupported_symbols),
            "is_stale": self.is_stale,
            "stale_reason": self.stale_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UniverseProvenance:
        return cls(
            universe_id=str(data["universe_id"]),
            scope=Scope(data["scope"]),
            source_urls=tuple(data.get("source_urls", ())),
            retrieval_timestamp=str(data["retrieval_timestamp"]),
            source_file_generation_timestamp=data.get("source_file_generation_timestamp"),
            snapshot_hash=str(data["snapshot_hash"]),
            original_listing_counts=dict(data.get("original_listing_counts", {})),
            included_ticker_count=int(data.get("included_ticker_count", 0)),
            excluded_counts_by_reason=dict(data.get("excluded_counts_by_reason", {})),
            unsupported_symbol_count=int(data.get("unsupported_symbol_count", 0)),
            unsupported_symbols=tuple(data.get("unsupported_symbols", ())),
            is_stale=bool(data.get("is_stale", False)),
            stale_reason=data.get("stale_reason"),
        )


@dataclass
class DiscoveryCheckpoint:
    """Persistent, versioned state of a discovery scan for same-session resumption."""

    version: int
    cache_key: str
    universe_id: str
    universe_hash: str
    session_date: str
    provider: str
    earnings_source: str
    earnings_buffer: int
    min_score: int
    strategy_id: str
    strategy_version: str
    attempted_tickers: list[str]
    completed_tickers: list[str]
    failed_tickers: dict[str, dict[str, Any]]
    observations: list[dict[str, Any]]
    results: list[dict[str, Any]]
    status: str
    updated_at: str
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "cache_key": self.cache_key,
            "universe_id": self.universe_id,
            "universe_hash": self.universe_hash,
            "session_date": self.session_date,
            "provider": self.provider,
            "earnings_source": self.earnings_source,
            "earnings_buffer": self.earnings_buffer,
            "min_score": self.min_score,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "attempted_tickers": list(self.attempted_tickers),
            "completed_tickers": list(self.completed_tickers),
            "failed_tickers": dict(self.failed_tickers),
            "observations": list(self.observations),
            "results": list(self.results),
            "status": self.status,
            "updated_at": self.updated_at,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryCheckpoint:
        return cls(
            version=int(data.get("version", 1)),
            cache_key=str(data["cache_key"]),
            universe_id=str(data["universe_id"]),
            universe_hash=str(data["universe_hash"]),
            session_date=str(data["session_date"]),
            provider=str(data["provider"]),
            earnings_source=str(data["earnings_source"]),
            earnings_buffer=int(data["earnings_buffer"]),
            min_score=int(data["min_score"]),
            strategy_id=str(data["strategy_id"]),
            strategy_version=str(data["strategy_version"]),
            attempted_tickers=list(data.get("attempted_tickers", [])),
            completed_tickers=list(data.get("completed_tickers", [])),
            failed_tickers=dict(data.get("failed_tickers", {})),
            observations=list(data.get("observations", [])),
            results=list(data.get("results", [])),
            status=str(data.get("status", ScanStatus.NOT_STARTED.value)),
            updated_at=str(data.get("updated_at", "")),
            checksum=str(data.get("checksum", "")),
        )


@dataclass
class DiscoveryResult:
    """Aggregated output of a discovery scan run across a universe."""

    scope: Scope
    universe_provenance: UniverseProvenance
    session_date: date
    provider: str
    actual_provider: str | None
    total_tickers: int
    completed_count: int
    remaining_count: int
    scored_count: int
    qualifying_count: int
    insufficient_data_count: int
    failed_count: int
    cached_count: int
    status: ScanStatus
    focus_list: pd.DataFrame
    all_qualifying: pd.DataFrame
    all_observations: pd.DataFrame
    failures: dict[str, str] = field(default_factory=dict)
    is_partial: bool = False
    is_stale_universe: bool = False
    status_message: str | None = None
