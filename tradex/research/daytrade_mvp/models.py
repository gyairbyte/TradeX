"""Data models for multi-resolution intraday research (DAYTRADE-001A)."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class Resolution(str, Enum):
    """Supported resolutions for multi-resolution day trading."""

    DAILY = "daily"
    TICK_133 = "133_tick"
    MINUTE_1 = "1_minute"
    TICK_50 = "50_tick"


@dataclass(frozen=True, slots=True)
class CompletedBar:
    """Normalized completed bar across time or tick resolutions."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    resolution: Resolution
    bar_start: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(f"Bar timestamp must be timezone-aware: {self.timestamp}")
        if self.bar_start is not None and self.bar_start.tzinfo is None:
            raise ValueError(f"Bar start must be timezone-aware: {self.bar_start}")
        if self.bar_start is not None and self.bar_start > self.timestamp:
            raise ValueError(
                f"Bar start ({self.bar_start}) cannot be later than bar completion ({self.timestamp})"
            )
        if self.high < self.low:
            raise ValueError(f"Bar high ({self.high}) cannot be less than low ({self.low})")
        if self.volume < 0.0:
            raise ValueError(f"Bar volume cannot be negative: {self.volume}")
        if not isinstance(self.resolution, Resolution):
            try:
                object.__setattr__(self, "resolution", Resolution(self.resolution))
            except ValueError:
                raise ValueError(f"Unsupported resolution: {self.resolution}")


class MultiResolutionSeries:
    """Container holding independent completed-bar sequences across multiple resolutions.

    Guarantees strict point-in-time access and facilitates materializing fully isolated
    as-of filtered instances with no back-references to future data.
    """

    def __init__(
        self,
        ticker: str,
        session_date: date | None = None,
        bars: dict[Resolution, list[CompletedBar]] | None = None,
    ) -> None:
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("ticker must be a non-empty string")
        self.ticker: str = ticker.strip().upper()
        self.session_date: date | None = session_date
        self._bars: dict[Resolution, list[CompletedBar]] = {
            res: [] for res in Resolution
        }
        if bars:
            for res, bar_list in bars.items():
                if res in self._bars:
                    self._bars[res] = list(bar_list)

    def add_bar(self, bar: CompletedBar) -> None:
        """Add a single completed bar to the appropriate resolution series."""
        if not isinstance(bar, CompletedBar):
            raise TypeError(f"Expected CompletedBar, got {type(bar).__name__}")
        self._bars[bar.resolution].append(bar)

    def add_bars(self, bars: Iterable[CompletedBar]) -> None:
        """Add multiple completed bars."""
        for bar in bars:
            self.add_bar(bar)

    def get_bars(
        self, resolution: Resolution, as_of: datetime | None = None
    ) -> tuple[CompletedBar, ...]:
        """Return chronological completed bars for the specified resolution.

        If as_of is provided, returns strictly those bars where bar.timestamp <= as_of.
        """
        if not isinstance(resolution, Resolution):
            try:
                resolution = Resolution(resolution)
            except ValueError:
                raise ValueError(f"Unsupported resolution: {resolution}")

        raw_bars = self._bars.get(resolution, [])
        sorted_bars = sorted(raw_bars, key=lambda b: b.timestamp)

        if as_of is None:
            return tuple(sorted_bars)

        if as_of.tzinfo is None:
            raise ValueError(f"as_of timestamp must be timezone-aware: {as_of}")

        return tuple(b for b in sorted_bars if b.timestamp <= as_of)

    def filter_as_of(self, as_of: datetime) -> MultiResolutionSeries:
        """Create a newly materialized MultiResolutionSeries containing only bars <= as_of.

        The resulting object is completely isolated with no back-references or access paths
        to future bars from the parent series.
        """
        if as_of.tzinfo is None:
            raise ValueError(f"as_of timestamp must be timezone-aware: {as_of}")

        filtered_bars: dict[Resolution, list[CompletedBar]] = {}
        for res in Resolution:
            bars_subset = [b for b in self._bars[res] if b.timestamp <= as_of]
            bars_subset.sort(key=lambda b: b.timestamp)
            filtered_bars[res] = bars_subset

        return MultiResolutionSeries(
            ticker=self.ticker,
            session_date=self.session_date,
            bars=filtered_bars,
        )

    def available_resolutions(self) -> frozenset[Resolution]:
        """Return resolutions that have at least one completed bar."""
        return frozenset(res for res, bars in self._bars.items() if len(bars) > 0)

    def bar_count(self, resolution: Resolution | None = None) -> int:
        """Return bar count for a specific resolution or aggregate total across all resolutions."""
        if resolution is not None:
            return len(self._bars.get(resolution, []))
        return sum(len(bars) for bars in self._bars.values())


class SetupEvaluationStatus(str, Enum):
    """Outcome status for a setup evaluation."""

    NO_SETUP = "no_setup"
    SETUP_DETECTED = "setup_detected"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True, slots=True)
class SetupEvaluationResult:
    """Immutable research result returned by a day-trading setup evaluation."""

    status: SetupEvaluationStatus
    setup_id: str
    setup_version: str
    as_of: datetime
    reasons: tuple[str, ...] = field(default_factory=tuple)
    evidence: dict[str, Any] = field(default_factory=dict)
    detected_entry: float | None = None
    detected_stop: float | None = None
    detected_target: float | None = None

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError(f"as_of timestamp must be timezone-aware: {self.as_of}")
        if not isinstance(self.status, SetupEvaluationStatus):
            try:
                object.__setattr__(self, "status", SetupEvaluationStatus(self.status))
            except ValueError:
                raise ValueError(f"Unsupported SetupEvaluationStatus: {self.status}")
        if not isinstance(self.reasons, tuple):
            object.__setattr__(self, "reasons", tuple(self.reasons))
