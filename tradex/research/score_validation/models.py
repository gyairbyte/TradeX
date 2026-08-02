"""Typed models for the short-term score validation study."""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from tradex.backtest.models import _clean  # noqa: PLC2701


class ValidationError(ValueError):
    """Raised for invalid study configuration, manifests, or inputs."""


@dataclass(frozen=True)
class Split:
    """A temporal partition of the dataset."""

    start: date
    end: date


@dataclass(frozen=True)
class ManifestEntry:
    """One ticker in the offline dataset manifest."""

    ticker: str
    path: str
    sha256: str
    rows: int
    start: datetime
    end: datetime
    data_source: str
    adjustment_policy: str


@dataclass(frozen=True)
class DatasetManifest:
    """Versioned offline dataset description with temporal splits."""

    schema_version: int
    dataset_name: str
    created_at: datetime
    source_description: str
    entries: tuple[ManifestEntry, ...]
    splits: dict[str, Split]


@dataclass(frozen=True)
class ScoreValidationConfig:
    """Immutable configuration for a point-in-time score validation study."""

    warmup_bars: int = 60
    horizons: tuple[int, ...] = (1, 3, 5)
    score_bucket_edges: tuple[int, ...] = (0, 20, 40, 60, 80, 101)
    score_thresholds: tuple[int, ...] = (20, 30, 40, 50, 60, 70, 80)
    slippage_scenarios_bps: tuple[float, ...] = (0.0, 5.0, 10.0)
    commission_bps: float = 0.0
    minimum_group_events: int = 20

    def __post_init__(self) -> None:
        # Defensive-copy mutable input.
        object.__setattr__(self, "horizons", tuple(int(h) for h in self.horizons))
        object.__setattr__(
            self, "score_bucket_edges", tuple(int(e) for e in self.score_bucket_edges)
        )
        object.__setattr__(
            self, "score_thresholds", tuple(int(t) for t in self.score_thresholds)
        )
        object.__setattr__(
            self,
            "slippage_scenarios_bps",
            tuple(float(s) for s in self.slippage_scenarios_bps),
        )

        _require_int("warmup_bars", self.warmup_bars)
        if self.warmup_bars < 50:
            raise ValidationError(f"warmup_bars must be >= 50; got {self.warmup_bars}")

        _require_positive_ints("horizons", self.horizons)
        if sorted(set(self.horizons)) != list(self.horizons):
            raise ValidationError(f"horizons must be unique and sorted; got {self.horizons}")

        _validate_bucket_edges(self.score_bucket_edges)
        _validate_thresholds(self.score_thresholds)

        _require_finite_nonnegative(
            "slippage_scenarios_bps", self.slippage_scenarios_bps
        )
        _require_finite_nonnegative("commission_bps", (self.commission_bps,))
        if not math.isfinite(self.commission_bps) or self.commission_bps < 0:
            raise ValidationError(f"commission_bps must be finite and >= 0; got {self.commission_bps}")

        _require_int("minimum_group_events", self.minimum_group_events)
        if self.minimum_group_events < 1:
            raise ValidationError(
                f"minimum_group_events must be positive; got {self.minimum_group_events}"
            )

    def bucket_for(self, score: float) -> str:
        """Return the label for the score bucket containing ``score``."""
        edges = self.score_bucket_edges
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            if i == len(edges) - 2:
                if lo <= score <= hi - 1:
                    return f"{lo}-{hi - 1}"
            if lo <= score < hi:
                return f"{lo}-{hi - 1}"
        return f"{edges[-2]}-{edges[-1] - 1}"


@dataclass(frozen=True)
class EventOutcome:
    """Forward-return outcome for one event horizon."""

    horizon: int
    exit_time: datetime | None
    raw_exit_price: float | None
    gross_return_pct: float | None
    net_return_pct_by_slippage: dict[float, float | None]
    outcome_status: Literal["complete", "insufficient_future_bars"]


@dataclass(frozen=True)
class EventRecord:
    """One point-in-time short-term score observation with forward outcomes."""

    ticker: str
    split: str
    signal_time: datetime
    score: float
    reasons: list[str]
    components: dict[str, bool]
    component_points: dict[str, int]
    signal_close: float
    entry_time: datetime | None
    raw_entry_price: float | None
    data_source: str
    outcomes: dict[int, EventOutcome]

    def to_dict(self) -> dict[str, Any]:
        """Flatten the event and its outcomes into a JSON-safe row dictionary."""
        base: dict[str, Any] = {
            "ticker": self.ticker,
            "split": self.split,
            "signal_time": _iso(self.signal_time),
            "score": self.score,
            "reasons": list(self.reasons),
            "components": dict(self.components),
            "component_points": dict(self.component_points),
            "signal_close": self.signal_close,
            "entry_time": _iso(self.entry_time) if self.entry_time else None,
            "raw_entry_price": self.raw_entry_price,
            "data_source": self.data_source,
        }
        for name in ["ema_structure", "volume_confirmation", "rsi_momentum", "macd_positive", "pullback_ema"]:
            base[f"component_{name}"] = bool(self.components.get(name, False))
        for horizon in sorted(self.outcomes):
            o = self.outcomes[horizon]
            base[f"{horizon}_bar_exit_time"] = _iso(o.exit_time)
            base[f"{horizon}_bar_raw_exit_price"] = o.raw_exit_price
            base[f"{horizon}_bar_gross_return_pct"] = o.gross_return_pct
            for slip in sorted(o.net_return_pct_by_slippage):
                slip_label = f"{horizon}_bar_net_return_pct_{int(slip)}bps"
                base[slip_label] = o.net_return_pct_by_slippage[slip]
            base[f"{horizon}_bar_outcome_status"] = o.outcome_status
        return _clean(base)


@dataclass(frozen=True)
class DataQualityRow:
    """Per-ticker data-quality summary."""

    ticker: str
    data_source: str
    sha256: str
    manifest_rows: int
    validated_rows: int
    data_start: datetime | None
    data_end: datetime | None
    duplicate_timestamps: int
    missing_required_values: int
    invalid_ohlc_rows: int
    split_event_counts: dict[str, int]
    complete_1_bar_outcomes: int
    complete_3_bar_outcomes: int
    complete_5_bar_outcomes: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["data_start"] = _iso(d["data_start"])
        d["data_end"] = _iso(d["data_end"])
        return _clean(d)


@dataclass(frozen=True)
class AggregateRow:
    """One row of an aggregated result table."""

    group: dict[str, Any]
    metrics: dict[str, Any]
    sample_status: str = "sufficient_sample"

    def to_dict(self) -> dict[str, Any]:
        return _clean({**self.group, **self.metrics, "sample_status": self.sample_status})


@dataclass
class StudyResult:
    """Complete deterministic result for one score-validation study."""

    config: ScoreValidationConfig
    manifest: DatasetManifest
    weight_snapshot: dict[str, Any]
    events: pd.DataFrame
    score_buckets: pd.DataFrame
    thresholds: pd.DataFrame
    components: pd.DataFrame
    score_distribution: pd.DataFrame
    component_frequency: pd.DataFrame
    ticker_summary: pd.DataFrame
    data_quality: pd.DataFrame
    report_markdown: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize the study to a JSON-safe dictionary."""
        return _clean(
            {
                "schema_version": 1,
                "generated_at": _iso(self.generated_at),
                "config": _config_to_dict(self.config),
                "weight_snapshot": self.weight_snapshot,
                "manifest": _manifest_to_dict(self.manifest),
                "events": _df_records(self.events) if not self.events.empty else [],
                "score_buckets": _df_records(self.score_buckets) if not self.score_buckets.empty else [],
                "thresholds": _df_records(self.thresholds) if not self.thresholds.empty else [],
                "components": _df_records(self.components) if not self.components.empty else [],
                "score_distribution": _df_records(self.score_distribution)
                if not self.score_distribution.empty
                else [],
                "component_frequency": _df_records(self.component_frequency)
                if not self.component_frequency.empty
                else [],
                "ticker_summary": _df_records(self.ticker_summary)
                if not self.ticker_summary.empty
                else [],
                "data_quality": _df_records(self.data_quality) if not self.data_quality.empty else [],
                "report_markdown": self.report_markdown,
                "limitations": [
                    "Events are not independent and may overlap.",
                    "Multiple daily observations from the same ticker are correlated.",
                    "Event counts are not trade counts from an executable portfolio.",
                    "Pooled results can be dominated by tickers with longer histories.",
                    "Event returns do not model capital allocation, stops, targets, or position sizing.",
                    "The existing backtest engine remains the executable-strategy tool.",
                ],
            }
        )

    def to_json(self, indent: int | None = None) -> str:
        """Serialize to a standards-compliant JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=_json_default, allow_nan=False)


def _require_int(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValidationError(f"{name} must be an integer; got {value!r} ({type(value).__name__})")


def _require_positive_ints(name: str, values: tuple[int, ...]) -> None:
    for v in values:
        _require_int(f"{name} element", v)
        if v < 1:
            raise ValidationError(f"{name} values must be positive; got {v}")


def _validate_bucket_edges(edges: tuple[int, ...]) -> None:
    if not edges:
        raise ValidationError("score_bucket_edges must not be empty")
    if edges[0] != 0:
        raise ValidationError(f"score_bucket_edges must start at 0; got {edges[0]}")
    if edges[-1] <= 100:
        raise ValidationError(f"score_bucket_edges final edge must exceed 100; got {edges[-1]}")
    prev = None
    for e in edges:
        _require_int("score_bucket_edges element", e)
        if prev is not None and e <= prev:
            raise ValidationError(
                f"score_bucket_edges must be strictly increasing; got {edges}"
            )
        prev = e


def _validate_thresholds(thresholds: tuple[int, ...]) -> None:
    prev = None
    for t in thresholds:
        _require_int("score_thresholds element", t)
        if t < 0 or t > 100:
            raise ValidationError(f"score_thresholds must be within 0-100; got {t}")
        if prev is not None and t <= prev:
            raise ValidationError(f"score_thresholds must be unique and sorted; got {thresholds}")
        prev = t


def _require_finite_nonnegative(name: str, values: tuple[float, ...]) -> None:
    for v in values:
        if not isinstance(v, (int, float, np.integer, np.floating)) or isinstance(v, bool):
            raise ValidationError(f"{name} values must be finite numbers; got {v!r}")
        if not math.isfinite(float(v)):
            raise ValidationError(f"{name} values must be finite; got {v}")
        if float(v) < 0:
            raise ValidationError(f"{name} values must be nonnegative; got {v}")


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _config_to_dict(config: ScoreValidationConfig) -> dict[str, Any]:
    return {
        "warmup_bars": config.warmup_bars,
        "horizons": list(config.horizons),
        "score_bucket_edges": list(config.score_bucket_edges),
        "score_thresholds": list(config.score_thresholds),
        "slippage_scenarios_bps": list(config.slippage_scenarios_bps),
        "commission_bps": config.commission_bps,
        "minimum_group_events": config.minimum_group_events,
    }


def _manifest_to_dict(manifest: DatasetManifest) -> dict[str, Any]:
    return {
        "schema_version": manifest.schema_version,
        "dataset_name": manifest.dataset_name,
        "created_at": _iso(manifest.created_at),
        "source_description": manifest.source_description,
        "entries": [
            {
                "ticker": e.ticker,
                "path": e.path,
                "sha256": e.sha256,
                "rows": e.rows,
                "start": _iso(e.start),
                "end": _iso(e.end),
                "data_source": e.data_source,
                "adjustment_policy": e.adjustment_policy,
            }
            for e in manifest.entries
        ],
        "splits": {
            name: {"start": s.start.isoformat(), "end": s.end.isoformat()}
            for name, s in sorted(manifest.splits.items())
        },
    }


def _df_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records = df.to_dict("records")
    return [_clean(r) for r in records]


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return _clean(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
