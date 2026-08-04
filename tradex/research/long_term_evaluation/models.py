"""Typed models and helpers for the LONG-001 research study."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from tradex.market.hours import get_market_session
from tradex.signals.weights import LongWeights

LONG_TERM_STOCK_UNIVERSE: tuple[str, ...] = (
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "NVDA",
    "JPM",
    "BAC",
    "GS",
    "XOM",
    "CVX",
    "JNJ",
    "MRK",
    "PFE",
    "UNH",
    "PG",
    "KO",
    "WMT",
    "COST",
    "HD",
    "CAT",
    "HON",
    "IBM",
    "CSCO",
    "ORCL",
    "MCD",
    "NKE",
    "DIS",
    "BA",
    "MMM",
    "UPS",
)

LONG_TERM_ETF_UNIVERSE: tuple[str, ...] = (
    "QQQ",
    "IWM",
    "DIA",
    "XLB",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
)

LONG_TERM_BENCHMARK: str = "SPY"
LONG_TERM_UNIVERSE: tuple[str, ...] = LONG_TERM_STOCK_UNIVERSE + LONG_TERM_ETF_UNIVERSE

CONCLUSION_ORDER: tuple[str, ...] = (
    "supports_further_research",
    "reject_or_deprioritize",
    "inconclusive",
)


class StudyError(Exception):
    """Raised for invalid study configuration, manifests, or inputs."""


@dataclass(frozen=True)
class ManifestEntry:
    """One ticker in the locked daily dataset manifest."""

    ticker: str
    path: str
    sha256: str
    rows: int
    start: datetime
    end: datetime
    data_source: str
    adjustment_policy: str
    failure: str | None = None
    quality: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["start"] = _iso(d["start"])
        d["end"] = _iso(d["end"])
        return _clean(d)


@dataclass(frozen=True)
class DatasetManifest:
    """Locked offline dataset description with temporal splits."""

    schema_version: int = 1
    dataset_name: str = "long-term-evaluation"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    provider: str = "yahoo"
    timeframe: str = "1d"
    adjustment_policy: str = "provider_adjusted"
    package_version: str = "unknown"
    request_metadata: dict[str, Any] = field(default_factory=dict)
    source_description: str = (
        "Yahoo Finance daily adjusted OHLCV via fetch_daily_history, auto_adjust=True, "
        "weekly XNYS market-calendar aggregation"
    )
    requested_start: date | None = None
    requested_end: date | None = None
    requested_universe: tuple[str, ...] = field(default_factory=tuple)
    benchmark_ticker: str | None = None
    successful_tickers: tuple[str, ...] = field(default_factory=tuple)
    missing_tickers: tuple[str, ...] = field(default_factory=tuple)
    failed_tickers: tuple[str, ...] = field(default_factory=tuple)
    failure_policy: str = "record_and_continue"
    entries: tuple[ManifestEntry, ...] = field(default_factory=tuple)
    splits: dict[str, dict[str, date | str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "created_at": _iso(self.created_at),
            "provider": self.provider,
            "timeframe": self.timeframe,
            "adjustment_policy": self.adjustment_policy,
            "package_version": self.package_version,
            "request_metadata": self.request_metadata,
            "source_description": self.source_description,
            "requested_start": _iso_date(self.requested_start),
            "requested_end": _iso_date(self.requested_end),
            "requested_universe": list(self.requested_universe),
            "benchmark_ticker": self.benchmark_ticker,
            "successful_tickers": list(self.successful_tickers),
            "missing_tickers": list(self.missing_tickers),
            "failed_tickers": list(self.failed_tickers),
            "failure_policy": self.failure_policy,
            "entries": [e.to_dict() for e in self.entries],
            "splits": {
                name: {"start": _iso_date(s["start"]), "end": _iso_date(s["end"])}
                for name, s in self.splits.items()
            },
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def verify_data_files(self, data_dir: Path) -> bool:
        """Return True if all on-disk CSV files match their manifest hashes and rows."""
        data_dir = Path(data_dir)
        for entry in self.entries:
            if entry.failure:
                continue
            path = data_dir / entry.path
            if not path.exists():
                return False
            if _file_sha256(path) != entry.sha256:
                return False
            df = pd.read_csv(path, index_col="datetime", parse_dates=True)
            if len(df) != entry.rows:
                return False
        return True

    def verify_metadata(self, spec: LongTermStudySpec) -> bool:
        """Fail-closed check that manifest metadata matches the locked spec."""
        if self.provider != spec.provider:
            return False
        if self.timeframe != spec.timeframe:
            return False
        if self.adjustment_policy != spec.adjustment_policy:
            return False
        if self.requested_start != spec.start:
            return False
        if self.requested_end != spec.end:
            return False
        if set(self.requested_universe) != set(spec.universe):
            return False
        if self.benchmark_ticker != spec.benchmark_ticker:
            return False
        expected_splits = _build_split_dates(spec)
        if set(self.splits.keys()) != set(expected_splits.keys()):
            return False
        for name, split in expected_splits.items():
            if name not in self.splits:
                return False
            if self.splits[name]["start"] != split["start"]:
                return False
            if self.splits[name]["end"] != split["end"]:
                return False
        expected_successful = set(spec.universe) | {spec.benchmark_ticker}
        if set(self.successful_tickers) != expected_successful:
            return False
        if self.failure_policy != "record_and_continue":
            return False
        if not self.package_version or self.package_version == "unknown":
            return False
        return True


@dataclass(frozen=True)
class EventOutcome:
    """Forward-return outcome for one event horizon."""

    horizon: int
    exit_time: datetime | None
    raw_exit_price: float | None
    gross_return_pct: float | None
    net_return_pct_by_slippage: dict[str, float | None]
    spy_return_pct: float | None
    spy_net_return_pct_by_slippage: dict[str, float | None]
    outcome_status: Literal[
        "complete", "insufficient_future_bars", "cross_split_excluded"
    ]

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class EventRecord:
    """One point-in-time long-term signal or benchmark observation."""

    ticker: str
    split: str
    rule: str
    group: str
    overlap_policy: str
    cohort: str
    signal_time: datetime
    score: float | None
    reasons: list[str]
    signal_close: float
    ma40: float | None
    entry_time: datetime | None
    raw_entry_price: float | None
    data_source: str
    outcomes: dict[int, EventOutcome]

    def to_dict(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "ticker": self.ticker,
            "split": self.split,
            "rule": self.rule,
            "group": self.group,
            "overlap_policy": self.overlap_policy,
            "cohort": self.cohort,
            "signal_time": _iso(self.signal_time),
            "score": self.score,
            "reasons": list(self.reasons),
            "signal_close": self.signal_close,
            "ma40": self.ma40,
            "entry_time": _iso(self.entry_time) if self.entry_time else None,
            "raw_entry_price": self.raw_entry_price,
            "data_source": self.data_source,
        }
        for h, o in sorted(self.outcomes.items()):
            base[f"{h}_bar_exit_time"] = _iso(o.exit_time)
            base[f"{h}_bar_raw_exit_price"] = o.raw_exit_price
            base[f"{h}_bar_gross_return_pct"] = o.gross_return_pct
            base[f"{h}_bar_spy_return_pct"] = o.spy_return_pct
            for key, value in o.net_return_pct_by_slippage.items():
                base[f"{h}_bar_net_return_pct_{key}bps"] = value
            for key, value in o.spy_net_return_pct_by_slippage.items():
                base[f"{h}_bar_spy_net_return_pct_{key}bps"] = value
            base[f"{h}_bar_outcome_status"] = o.outcome_status
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
    complete_outcomes: dict[str, int]
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


@dataclass(frozen=True)
class StudyResult:
    """Complete deterministic result for a LONG-001 evaluation."""

    spec: LongTermStudySpec
    manifest: DatasetManifest
    protocol_sha256: str
    protocol_commit: str | None
    weight_snapshot: dict[str, Any]
    events: pd.DataFrame
    trades: pd.DataFrame
    summary: dict[str, Any]
    aggregates: dict[str, pd.DataFrame]
    bootstrap: pd.DataFrame
    data_quality: pd.DataFrame
    report_markdown: str
    conclusion: Literal[
        "supports_further_research",
        "reject_or_deprioritize",
        "inconclusive",
    ]
    production_promotion_eligible: bool = False
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self, include_records: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": _iso(self.generated_at),
            "conclusion": self.conclusion,
            "production_promotion_eligible": self.production_promotion_eligible,
            "event_count": len(self.events),
            "trade_count": len(self.trades),
            "protocol_sha256": self.protocol_sha256,
            "protocol_commit": self.protocol_commit,
            "spec": self.spec.to_dict(),
            "manifest": self.manifest.to_dict(),
            "weight_snapshot": self.weight_snapshot,
            "summary": self.summary,
            "aggregates": {
                name: _df_records(df) if not df.empty else []
                for name, df in self.aggregates.items()
            },
            "bootstrap": _df_records(self.bootstrap) if not self.bootstrap.empty else [],
            "data_quality": _df_records(self.data_quality) if not self.data_quality.empty else [],
            "report_markdown": self.report_markdown,
        }
        if include_records:
            d["events"] = _df_records(self.events) if not self.events.empty else []
            d["trades"] = _df_records(self.trades) if not self.trades.empty else []
        return _clean(d)

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(
            self.to_dict(include_records=False),
            indent=indent,
            default=_json_default,
            allow_nan=False,
            sort_keys=True,
        )


@dataclass(frozen=True)
class LongTermStudySpec:
    """Immutable, hash-locked LONG-001 study specification."""

    provider: str = "yahoo"
    timeframe: str = "1wk"
    adjustment_policy: str = "provider_adjusted"
    start: date = field(default_factory=lambda: date(2007, 1, 1))
    end: date = field(default_factory=lambda: date(2025, 12, 19))
    warmup_end: date = field(default_factory=lambda: date(2009, 12, 31))
    development_end: date = field(default_factory=lambda: date(2016, 12, 31))
    validation_end: date = field(default_factory=lambda: date(2020, 12, 31))
    hold_weeks: tuple[int, ...] = (13, 26)
    score_thresholds: tuple[int, ...] = (40,)
    score_bucket_edges: tuple[int, ...] = (0, 25, 40, 60, 80, 101)
    slippage_scenarios_bps: tuple[float, ...] = (0.0, 10.0, 25.0)
    commission_bps: float = 0.0
    decision_slippage_bps: float = 5.0
    min_events_per_group: int = 20
    min_ticker_trades_for_cohort_gate: int = 5
    entry_delay_bars: int = 1
    universe: tuple[str, ...] = LONG_TERM_UNIVERSE
    benchmark_ticker: str = LONG_TERM_BENCHMARK
    warmup_weeks: int = 60
    min_required_weekly_bars: int = 60
    bootstrap_seed: int = 20260805
    bootstrap_resamples: int = 5_000
    minimum_signals: int = 200
    minimum_stock_tickers: int = 20
    minimum_etf_tickers: int = 8
    minimum_lift_bps: float = 50.0
    q10_support_max_worse_bps: float = 100.0
    q10_reject_worse_bps: float = 200.0
    reject_point_estimate_worse_bps: float = 50.0
    ticker_positive_fraction_stock: float = 0.6
    ticker_positive_fraction_etf: float = 0.6
    cost_sensitivity_slippage_bps: float = 25.0
    weights: LongWeights = field(default_factory=LongWeights)
    protocol_source: str = "PR #25 comment 5182648133"
    protocol_path: str = "docs/research/LONG-001.json"

    def __post_init__(self) -> None:
        if self.warmup_weeks < self.min_required_weekly_bars:
            raise StudyError(
                f"warmup_weeks must be >= {self.min_required_weekly_bars}; got {self.warmup_weeks}"
            )
        if len(self.hold_weeks) < 1:
            raise StudyError("hold_weeks must not be empty")
        if sorted(set(self.hold_weeks)) != list(self.hold_weeks):
            raise StudyError(f"hold_weeks must be unique and sorted; got {self.hold_weeks}")
        if not self.score_thresholds:
            raise StudyError("score_thresholds must not be empty")
        _validate_bucket_edges(self.score_bucket_edges)
        _require_finite_nonnegative("commission_bps", (self.commission_bps,))
        _require_finite_nonnegative(
            "slippage_scenarios_bps", self.slippage_scenarios_bps
        )
        _require_finite_nonnegative(
            "decision_slippage_bps", (self.decision_slippage_bps,)
        )
        if self.min_events_per_group < 1:
            raise StudyError(
                f"min_events_per_group must be positive; got {self.min_events_per_group}"
            )
        if self.min_ticker_trades_for_cohort_gate < 1:
            raise StudyError(
                f"min_ticker_trades_for_cohort_gate must be positive; got {self.min_ticker_trades_for_cohort_gate}"
            )
        if self.entry_delay_bars < 0:
            raise StudyError("entry_delay_bars must be >= 0")
        if self.benchmark_ticker in self.universe:
            raise StudyError(
                f"benchmark_ticker {self.benchmark_ticker} must not be in the candidate universe"
            )
        if not self.universe:
            raise StudyError("universe must not be empty")
        if self.minimum_lift_bps < 0:
            raise StudyError(f"minimum_lift_bps must be nonnegative; got {self.minimum_lift_bps}")

        # Defensive-copy mutable inputs without coercion.
        object.__setattr__(self, "hold_weeks", tuple(int(h) for h in self.hold_weeks))
        object.__setattr__(self, "score_thresholds", tuple(int(s) for s in self.score_thresholds))
        object.__setattr__(self, "score_bucket_edges", tuple(int(s) for s in self.score_bucket_edges))
        object.__setattr__(
            self, "slippage_scenarios_bps", tuple(float(s) for s in self.slippage_scenarios_bps)
        )
        object.__setattr__(self, "commission_bps", float(self.commission_bps))
        object.__setattr__(self, "decision_slippage_bps", float(self.decision_slippage_bps))
        object.__setattr__(self, "universe", tuple(str(t).upper() for t in self.universe))

    def cohort_for(self, ticker: str) -> str:
        return "etf" if ticker in LONG_TERM_ETF_UNIVERSE else "stock"

    def bucket_for(self, score: float) -> str:
        """Return the label for the score bucket containing ``score``."""
        edges = self.score_bucket_edges
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            if i == len(edges) - 2 and lo <= score <= hi - 1:
                return f"{lo}-{hi - 1}"
            if lo <= score < hi:
                return f"{lo}-{hi - 1}"
        return f"{edges[-2]}-{edges[-1] - 1}"

    def bucket_labels(self) -> tuple[str, ...]:
        """Return all configured score-bucket labels in order."""
        edges = self.score_bucket_edges
        return tuple(f"{edges[i]}-{edges[i + 1] - 1}" for i in range(len(edges) - 1))

    def slippage_key(self, slippage_bps: float) -> str:
        s = float(slippage_bps)
        if s.is_integer():
            return f"{int(s)}"
        return repr(s)

    def split_for(self, dt: datetime | date | str) -> str:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        d = dt.date() if isinstance(dt, datetime) else dt
        if d <= self.warmup_end:
            return "warmup"
        if d <= self.development_end:
            return "development"
        if d <= self.validation_end:
            return "validation"
        if d <= self.end:
            return "holdout"
        return "out_of_range"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat()
        d["warmup_end"] = self.warmup_end.isoformat()
        d["development_end"] = self.development_end.isoformat()
        d["validation_end"] = self.validation_end.isoformat()
        d["universe"] = list(self.universe)
        d["hold_weeks"] = list(self.hold_weeks)
        d["score_thresholds"] = list(self.score_thresholds)
        d["score_bucket_edges"] = list(self.score_bucket_edges)
        d["slippage_scenarios_bps"] = list(self.slippage_scenarios_bps)
        d["weights"] = {
            "secular_uptrend": self.weights.secular_uptrend,
            "rsi_healthy": self.weights.rsi_healthy,
            "volume_accumulation": self.weights.volume_accumulation,
            "macd_bullish": self.weights.macd_bullish,
            "bb_coil": self.weights.bb_coil,
        }
        return _clean(d)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def _build_split_dates(spec: LongTermStudySpec) -> dict[str, dict[str, date]]:
    splits: dict[str, dict[str, date]] = {}
    splits["warmup"] = {"start": spec.start, "end": spec.warmup_end}
    splits["development"] = {
        "start": spec.warmup_end + timedelta(days=1),
        "end": spec.development_end,
    }
    splits["validation"] = {
        "start": spec.development_end + timedelta(days=1),
        "end": spec.validation_end,
    }
    splits["holdout"] = {
        "start": spec.validation_end + timedelta(days=1),
        "end": spec.end,
    }
    return splits


def _iso_date(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        return value
    return value.isoformat()


def _iso(dt: datetime | date | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return dt.isoformat()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def _df_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [_clean(r) for r in df.to_dict("records")]


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype.kind in "f":
            df[col] = df[col].where(df[col].notna(), None)
    return df


def _df_to_markdown(df: pd.DataFrame) -> str:
    """Render a DataFrame as a Markdown table without optional dependencies."""
    if df.empty:
        return "_No rows._"
    df = _clean_df(df)
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    lines = [header, sep]
    for _idx, row in df.iterrows():
        lines.append("| " + " | ".join(_clean_cell(row.get(c)) for c in cols) + " |")
    return "\n".join(lines)


def _clean_cell(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return _clean(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return _clean(asdict(obj))
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _clean(obj: Any) -> Any:
    """JSON-safe cleaning of numpy/pandas/float artifacts."""
    if isinstance(obj, (np.floating, np.integer)):
        return float(obj) if isinstance(obj, np.floating) else int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        if math.isnan(obj):
            return None
        if math.isinf(obj):
            return None
        return obj
    if isinstance(obj, Mapping):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


def _validate_bucket_edges(edges: tuple[int, ...]) -> None:
    if len(edges) < 2:
        raise StudyError("score_bucket_edges must have at least two values")
    if edges[0] != 0:
        raise StudyError("score_bucket_edges must start at 0")
    if edges[-1] != 101:
        raise StudyError("score_bucket_edges must end at 101")
    if sorted(set(edges)) != list(edges):
        raise StudyError("score_bucket_edges must be strictly increasing")
    for i in range(len(edges) - 1):
        if edges[i] >= edges[i + 1]:
            raise StudyError(f"score_bucket_edges must be strictly increasing: {edges}")


def _require_finite_nonnegative(name: str, values: tuple[float, ...]) -> None:
    for v in values:
        if not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v) or v < 0:
            raise StudyError(f"{name} values must be finite and nonnegative; got {values}")


def _require_int(name: str, value: int) -> None:
    if not isinstance(value, int):
        raise StudyError(f"{name} must be an int; got {type(value)}")


def _validate_bars(
    df: pd.DataFrame, ticker: str
) -> tuple[pd.DataFrame, int, int, int]:
    """Canonicalize and validate an OHLCV DataFrame.

    Returns the cleaned DataFrame plus counts for duplicate timestamps,
    missing required values, and invalid OHLC rows.
    """
    df = df.copy()
    df.index = pd.to_datetime(df.index, utc=True)
    duplicate_timestamps = int(df.index.duplicated(keep="first").sum())
    df = df[~df.index.duplicated(keep="first")].sort_index()

    # Flatten MultiIndex columns that yfinance may return.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    # Normalize to lowercase, replace spaces/underscores.
    df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]

    # If both adj_close and close are present, prefer close (provider_default / adjusted).
    if "adj_close" in df.columns and "close" in df.columns:
        df = df.drop(columns=["adj_close"])

    required = {"open", "high", "low", "close", "volume"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        raise StudyError(f"{ticker}: missing required columns {missing_cols}")

    missing_required_values = 0
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        missing_required_values += int(df[col].isna().sum())

    df = df.dropna(subset=list(required))
    invalid_ohlc_rows = int(
        (
            (df["high"] < df["low"])
            | (df["close"] > df["high"])
            | (df["close"] < df["low"])
            | (df["open"] > df["high"])
            | (df["open"] < df["low"])
        ).sum()
    )
    df = df[
        (df["high"] >= df["low"])
        & (df["close"] <= df["high"])
        & (df["close"] >= df["low"])
        & (df["open"] <= df["high"])
        & (df["open"] >= df["low"])
    ]
    # Ensure canonical column order.
    df = df[list(required)]
    return df, duplicate_timestamps, missing_required_values, invalid_ohlc_rows


def _aggregate_daily_to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Deterministic XNYS weekly aggregation from daily UTC index.

    Each weekly bar is built from the actual XNYS sessions in that calendar
    week (Mon-Sun).  The bar is indexed by the final session's closing
    timestamp in UTC and carries an extra ``first_session_open_time`` column
    for the following week's executable open.
    """
    from exchange_calendars import get_calendar

    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "first_session_open_time"])

    cal = get_calendar("XNYS")
    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")

    # Map each daily bar to an XNYS session date.  Bars on non-sessions
    # (unexpected data) are mapped to the previous session so they do not
    # create phantom weeks.
    session_dates: list[date] = []
    keep = []
    for ts in df.index:
        d = ts.to_pydatetime().astimezone(UTC).date()
        if not cal.is_session(d):
            try:
                d = cal.date_to_session(d, direction="previous").date()
            except ValueError:
                keep.append(False)
                session_dates.append(d)
                continue
        keep.append(True)
        session_dates.append(d)
    df = df.loc[keep].copy()
    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "first_session_open_time"])
    df["session_date"] = session_dates[: len(df)]
    df = df.set_index("session_date").sort_index()

    # Determine the last XNYS session of the calendar week (Mon-Sun) for each
    # session date.  The calendar week ends on Sunday; its last trading
    # session is the Friday (or Thursday/holiday-shortened) session.
    def _week_end(d: date) -> date:
        sunday = d + timedelta(days=(6 - d.weekday()))
        return cal.date_to_session(sunday, direction="previous").date()

    df["week_end"] = df.index.map(_week_end)

    # The trailing week is incomplete if its expected week-end session has not
    # yet appeared in the dataset.
    max_session = df.index.max()
    present_sessions = set(df.index)
    df = df[df["week_end"].isin(present_sessions) & (df["week_end"] <= max_session)].copy()
    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "first_session_open_time"])

    records: list[dict[str, Any]] = []
    for week_end, sub in df.groupby("week_end", sort=True):
        sub = sub.sort_index()
        first_session = sub.index[0]
        last_session = sub.index[-1]
        first_market = get_market_session(first_session)
        last_market = get_market_session(last_session)
        if first_market is None or last_market is None:
            continue
        records.append({
            "open": float(sub["open"].iloc[0]),
            "high": float(sub["high"].max()),
            "low": float(sub["low"].min()),
            "close": float(sub["close"].iloc[-1]),
            "volume": float(sub["volume"].sum()),
            "first_session_open_time": first_market.opens_at.astimezone(UTC),
            "last_session_close_time": last_market.closes_at.astimezone(UTC),
        })

    if not records:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "first_session_open_time"])

    weekly = pd.DataFrame(records)
    weekly.index = pd.DatetimeIndex(weekly["last_session_close_time"], tz="UTC")
    weekly = weekly.sort_index()
    weekly = weekly[["open", "high", "low", "close", "volume", "first_session_open_time"]]
    return weekly


def load_manifest(path: Path) -> DatasetManifest:
    """Load a manifest from JSON."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = []
    for e in raw.get("entries", []):
        entries.append(
            ManifestEntry(
                ticker=e["ticker"],
                path=e["path"],
                sha256=e["sha256"],
                rows=e["rows"],
                start=datetime.fromisoformat(e["start"]),
                end=datetime.fromisoformat(e["end"]),
                data_source=e.get("data_source", "unknown"),
                adjustment_policy=e.get("adjustment_policy", "unknown"),
                failure=e.get("failure"),
                quality=e.get("quality", {}),
                warnings=e.get("warnings", []),
            )
        )
    splits: dict[str, dict[str, date]] = {}
    for name, s in raw.get("splits", {}).items():
        splits[name] = {
            "start": date.fromisoformat(s["start"]),
            "end": date.fromisoformat(s["end"]),
        }
    return DatasetManifest(
        schema_version=raw.get("schema_version", 1),
        dataset_name=raw.get("dataset_name", "unknown"),
        created_at=datetime.fromisoformat(raw["created_at"]),
        provider=raw.get("provider", "unknown"),
        timeframe=raw.get("timeframe", "unknown"),
        adjustment_policy=raw.get("adjustment_policy", "unknown"),
        package_version=raw.get("package_version", "unknown"),
        request_metadata=raw.get("request_metadata", {}),
        source_description=raw.get("source_description", ""),
        requested_start=date.fromisoformat(raw["requested_start"]) if raw.get("requested_start") else None,
        requested_end=date.fromisoformat(raw["requested_end"]) if raw.get("requested_end") else None,
        requested_universe=tuple(raw.get("requested_universe", [])),
        benchmark_ticker=raw.get("benchmark_ticker"),
        successful_tickers=tuple(raw.get("successful_tickers", [])),
        missing_tickers=tuple(raw.get("missing_tickers", [])),
        failed_tickers=tuple(raw.get("failed_tickers", [])),
        failure_policy=raw.get("failure_policy", "unknown"),
        entries=tuple(entries),
        splits=splits,
    )
