"""Typed models for the short-term market-context research study."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from tradex.market.models import ShortContextPolicy
from tradex.research.score_validation.models import ScoreValidationConfig


class ValidationError(ValueError):
    """Raised for invalid context-study configuration or inputs."""


@dataclass(frozen=True)
class ShortContextSpec:
    """Versioned specification for a short-term market-context study."""

    study_name: str
    target_tickers: tuple[str, ...]
    ticker_context: dict[str, dict[str, str | None]]
    candidate_policies: tuple[ShortContextPolicy, ...]
    default_market_proxy: str
    primary_horizon_bars: int = 3
    primary_slippage_bps: float = 5.0
    horizons: tuple[int, ...] = (1, 3, 5)
    slippage_scenarios_bps: tuple[float, ...] = (0.0, 5.0, 10.0)
    commission_bps: float = 0.0
    minimum_validation_events: int | None = None
    minimum_holdout_events: int = 100
    minimum_holdout_tickers: int = 10
    minimum_event_retention_pct: float = 25.0
    minimum_ticker_coverage_pct: float = 50.0
    baseline_score_threshold: int = 40
    schema_version: int = 1

    def __post_init__(self) -> None:
        # Default validation sample minimum to the holdout minimum when not specified.
        if self.minimum_validation_events is None:
            object.__setattr__(self, "minimum_validation_events", self.minimum_holdout_events)

        if self.schema_version != 1:
            raise ValidationError(f"Unsupported schema version: {self.schema_version}; expected 1")
        if not self.study_name or not isinstance(self.study_name, str):
            raise ValidationError("study_name must be a nonempty string")
        if not self.target_tickers:
            raise ValidationError("target_tickers must not be empty")
        seen: set[str] = set()
        for t in self.target_tickers:
            if not isinstance(t, str) or not t:
                raise ValidationError(f"target ticker must be a nonempty string; got {t!r}")
            if t != t.upper():
                raise ValidationError(f"target ticker must be uppercase; got {t!r}")
            if t in seen:
                raise ValidationError(f"duplicate target ticker: {t}")
            seen.add(t)

        if not self.default_market_proxy or not isinstance(self.default_market_proxy, str):
            raise ValidationError("default_market_proxy must be a nonempty string")
        if self.default_market_proxy != self.default_market_proxy.upper():
            raise ValidationError("default_market_proxy must be uppercase")

        if not self.ticker_context:
            raise ValidationError("ticker_context must not be empty")
        for t in self.target_tickers:
            ctx = self.ticker_context.get(t)
            if ctx is None:
                raise ValidationError(f"missing ticker_context for {t}")
            if not isinstance(ctx, Mapping):
                raise ValidationError(f"ticker_context[{t!r}] must be an object")
            unknown = set(ctx.keys()) - {"market_proxy", "sector_proxy"}
            if unknown:
                raise ValidationError(f"ticker_context[{t}] contains unknown keys: {sorted(unknown)}")
            market = ctx.get("market_proxy")
            if market is None or not isinstance(market, str) or not market:
                raise ValidationError(f"ticker_context[{t}].market_proxy must be a nonempty string")
            if market != market.upper():
                raise ValidationError(f"ticker_context[{t}].market_proxy must be uppercase")
            if market == t:
                raise ValidationError(f"target {t} cannot be its own market_proxy")
            sector = ctx.get("sector_proxy")
            if sector is not None:
                if not isinstance(sector, str) or not sector:
                    raise ValidationError(f"ticker_context[{t}].sector_proxy must be a nonempty string or null")
                if sector != sector.upper():
                    raise ValidationError(f"ticker_context[{t}].sector_proxy must be uppercase")
                if sector == t:
                    raise ValidationError(f"target {t} cannot be its own sector_proxy")

        if not self.candidate_policies:
            raise ValidationError("candidate_policies must not be empty")
        seen_policies: set[ShortContextPolicy] = set()
        for p in self.candidate_policies:
            if not isinstance(p, ShortContextPolicy):
                raise ValidationError(f"candidate policy must be a ShortContextPolicy; got {p!r}")
            if p in seen_policies:
                raise ValidationError(f"duplicate candidate policy: {p.value}")
            seen_policies.add(p)
            if p == ShortContextPolicy.OFF:
                raise ValidationError("candidate policy cannot be 'off'")

        _require_positive_int("primary_horizon_bars", self.primary_horizon_bars)
        if self.primary_horizon_bars not in self.horizons:
            raise ValidationError(
                f"primary_horizon_bars {self.primary_horizon_bars} must be one of {list(self.horizons)}"
            )

        _require_positive_ints("horizons", self.horizons)

        _require_finite_nonnegative_number("primary_slippage_bps", self.primary_slippage_bps)
        if self.primary_slippage_bps not in self.slippage_scenarios_bps:
            raise ValidationError(
                f"primary_slippage_bps {self.primary_slippage_bps} must be one of {list(self.slippage_scenarios_bps)}"
            )

        if not self.slippage_scenarios_bps:
            raise ValidationError("slippage_scenarios_bps must not be empty")
        for s in self.slippage_scenarios_bps:
            _require_finite_nonnegative_number("slippage_scenarios_bps element", s)

        _require_finite_nonnegative_number("commission_bps", self.commission_bps)

        _require_positive_int("minimum_validation_events", self.minimum_validation_events)
        _require_positive_int("minimum_holdout_events", self.minimum_holdout_events)
        _require_positive_int("minimum_holdout_tickers", self.minimum_holdout_tickers)

        _require_percentage("minimum_event_retention_pct", self.minimum_event_retention_pct)
        _require_percentage("minimum_ticker_coverage_pct", self.minimum_ticker_coverage_pct)

        _require_int("baseline_score_threshold", self.baseline_score_threshold)
        if not (0 <= self.baseline_score_threshold <= 100):
            raise ValidationError(f"baseline_score_threshold must be 0-100; got {self.baseline_score_threshold}")

    def proxy_tickers(self) -> list[str]:
        """Return the sorted union of all market and sector proxies."""
        proxies: set[str] = {self.default_market_proxy}
        for ctx in self.ticker_context.values():
            proxies.add(ctx["market_proxy"])
            if ctx.get("sector_proxy"):
                proxies.add(ctx["sector_proxy"])
        return sorted(proxies)

    def all_tickers(self) -> list[str]:
        """Return target tickers plus proxies, deduplicated, first target order then sorted proxies."""
        seen: set[str] = set()
        result: list[str] = []
        for t in self.target_tickers:
            if t not in seen:
                seen.add(t)
                result.append(t)
        for t in sorted(self.proxy_tickers()):
            if t not in seen:
                seen.add(t)
                result.append(t)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "study_name": self.study_name,
            "target_tickers": list(self.target_tickers),
            "default_market_proxy": self.default_market_proxy,
            "ticker_context": {
                k: {"market_proxy": v["market_proxy"], "sector_proxy": v.get("sector_proxy")}
                for k, v in sorted(self.ticker_context.items())
            },
            "candidate_policies": [p.value for p in self.candidate_policies],
            "primary_horizon_bars": self.primary_horizon_bars,
            "primary_slippage_bps": self.primary_slippage_bps,
            "horizons": list(self.horizons),
            "slippage_scenarios_bps": list(self.slippage_scenarios_bps),
            "commission_bps": self.commission_bps,
            "minimum_validation_events": self.minimum_validation_events,
            "minimum_holdout_events": self.minimum_holdout_events,
            "minimum_holdout_tickers": self.minimum_holdout_tickers,
            "minimum_event_retention_pct": self.minimum_event_retention_pct,
            "minimum_ticker_coverage_pct": self.minimum_ticker_coverage_pct,
            "baseline_score_threshold": self.baseline_score_threshold,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, allow_nan=False, sort_keys=True)


def _require_int(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or isinstance(value, float):
        raise ValidationError(f"{name} must be an integer; got {value!r} ({type(value).__name__})")


def _require_positive_int(name: str, value: Any) -> None:
    _require_int(name, value)
    if value < 1:
        raise ValidationError(f"{name} must be positive; got {value}")


def _require_positive_ints(name: str, values: tuple[int, ...]) -> None:
    if not values:
        raise ValidationError(f"{name} must not be empty")
    for v in values:
        _require_positive_int(f"{name} element", v)
    if sorted(set(values)) != list(values):
        raise ValidationError(f"{name} must be unique and sorted; got {values}")


def _require_finite_nonnegative_number(name: str, value: Any) -> None:
    if isinstance(value, bool):
        raise ValidationError(f"{name} must be a finite number; got boolean")
    if not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValidationError(f"{name} must be a finite number; got {value!r} ({type(value).__name__})")
    f = float(value)
    if not math.isfinite(f):
        raise ValidationError(f"{name} must be finite; got {value}")
    if f < 0:
        raise ValidationError(f"{name} must be nonnegative; got {value}")


def _require_percentage(name: str, value: Any) -> None:
    _require_finite_nonnegative_number(name, value)
    f = float(value)
    if f > 100:
        raise ValidationError(f"{name} must be <= 100; got {value}")


@dataclass(frozen=True)
class ContextEventRecord:
    """One point-in-time short-term score observation with market context."""

    ticker: str
    split: str
    signal_time: datetime
    base_score: int
    baseline_qualifies: bool
    market_proxy: str
    sector_proxy: str | None
    market_regime_bullish: bool | None
    sector_regime_bullish: bool | None
    market_relative_strength_positive: bool | None
    sector_relative_strength_positive: bool | None
    market_rs_eligible: bool
    market_sector_rs_eligible: bool
    context_status: str
    entry_time: datetime | None
    raw_entry_price: float | None
    outcomes: dict[int, Any]
    market_context_time: datetime | None = None
    sector_context_time: datetime | None = None
    market_rs_ratio: float | None = None
    market_rs_ema20: float | None = None
    market_rs_change_20_pct: float | None = None
    sector_rs_ratio: float | None = None
    sector_rs_ema20: float | None = None
    sector_rs_change_20_pct: float | None = None
    market_rs_status: str = ""
    market_sector_rs_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["signal_time"] = _iso(self.signal_time)
        d["entry_time"] = _iso(self.entry_time)
        d["market_context_time"] = _iso(self.market_context_time)
        d["sector_context_time"] = _iso(self.sector_context_time)
        d.pop("outcomes", None)
        d.update(_outcome_columns(self.outcomes))
        return _clean(d)


def _outcome_columns(outcomes: dict[int, Any]) -> dict[str, Any]:
    """Flatten outcome objects into column-shaped keys."""
    flat: dict[str, Any] = {}
    for horizon, o in sorted(outcomes.items()):
        prefix = f"{horizon}_bar"
        if hasattr(o, "to_dict"):
            d = o.to_dict()
        elif is_dataclass(o):
            d = asdict(o)
        else:
            d = dict(o)
        flat[f"{prefix}_exit_time"] = d.get("exit_time")
        flat[f"{prefix}_raw_exit_price"] = d.get("raw_exit_price")
        flat[f"{prefix}_gross_return_pct"] = d.get("gross_return_pct")
        net_by = d.get("net_return_pct_by_slippage") or {}
        for key, value in sorted(net_by.items()):
            flat[f"{prefix}_net_return_pct_{key}bps"] = value
        flat[f"{prefix}_outcome_status"] = d.get("outcome_status")
    return flat


def _clean_outcome(o: Any) -> dict[str, Any]:
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if is_dataclass(o):
        return asdict(o)
    return dict(o)


@dataclass(frozen=True)
class PolicySplitMetrics:
    """Descriptive metrics for one policy on one split."""

    split: str
    policy: str
    event_count: int
    baseline_event_count: int
    retention_pct: float
    unique_tickers: int
    baseline_unique_tickers: int
    coverage_pct: float
    mean_net_return_pct: float | None
    median_net_return_pct: float | None
    positive_return_rate_pct: float | None
    mean_ticker_event_return_pct: float | None
    median_ticker_event_return_pct: float | None


@dataclass(frozen=True)
class CandidateResult:
    """Result of candidate selection on development and validation."""

    selected_policy: str | None
    selection_reason: str
    policy_metrics: dict[str, dict[str, PolicySplitMetrics]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_policy": self.selected_policy,
            "selection_reason": self.selection_reason,
            "policy_metrics": {
                p: {s: _dataclass_or_dict(m) for s, m in split_metrics.items()}
                for p, split_metrics in self.policy_metrics.items()
            },
        }


@dataclass(frozen=True)
class HoldoutResult:
    """Holdout evaluation for the selected policy."""

    passed: bool
    policy: str | None
    metrics: PolicySplitMetrics | None
    baseline_metrics: PolicySplitMetrics | None
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "policy": self.policy,
            "metrics": _dataclass_or_dict(self.metrics) if self.metrics else None,
            "baseline_metrics": _dataclass_or_dict(self.baseline_metrics) if self.baseline_metrics else None,
            "failure_reasons": list(self.failure_reasons),
        }


@dataclass(frozen=True)
class PairedBacktestResult:
    """Summary of paired baseline/candidate backtests across holdout tickers."""

    passed: bool
    baseline_metrics: pd.DataFrame
    candidate_metrics: pd.DataFrame
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "baseline_metrics": _df_records(self.baseline_metrics) if not self.baseline_metrics.empty else [],
            "candidate_metrics": _df_records(self.candidate_metrics) if not self.candidate_metrics.empty else [],
            "failure_reasons": list(self.failure_reasons),
        }


@dataclass
class ContextStudyResult:
    """Complete deterministic result for a short-term context study."""

    spec: ShortContextSpec
    runtime_config: ScoreValidationConfig
    manifest_path: Path
    manifest_sha256: str | None
    context_spec_sha256: str | None
    weight_snapshot: dict[str, Any]
    events: pd.DataFrame
    candidate_comparison: pd.DataFrame
    candidate_selection: CandidateResult
    holdout: HoldoutResult
    paired_backtests: PairedBacktestResult
    ticker_comparison: pd.DataFrame
    data_quality: pd.DataFrame
    report_markdown: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ingestion_spec_sha256: str | None = None
    snapshot_audit_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        from tradex.research.score_validation.models import _config_to_dict
        return _clean({
            "schema_version": 1,
            "generated_at": _iso(self.generated_at),
            "spec": self.spec.to_dict(),
            "runtime_config": _config_to_dict(self.runtime_config),
            "manifest_path": str(self.manifest_path),
            "manifest_sha256": self.manifest_sha256,
            "context_spec_sha256": self.context_spec_sha256,
            "ingestion_spec_sha256": self.ingestion_spec_sha256,
            "snapshot_audit_sha256": self.snapshot_audit_sha256,
            "weight_snapshot": self.weight_snapshot,
            "events": _df_records(self.events) if not self.events.empty else [],
            "candidate_comparison": _df_records(self.candidate_comparison) if not self.candidate_comparison.empty else [],
            "candidate_selection": self.candidate_selection.to_dict(),
            "holdout": self.holdout.to_dict(),
            "paired_backtests": self.paired_backtests.to_dict(),
            "ticker_comparison": _df_records(self.ticker_comparison) if not self.ticker_comparison.empty else [],
            "data_quality": _df_records(self.data_quality) if not self.data_quality.empty else [],
            "report_markdown": self.report_markdown,
        })

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, allow_nan=False, default=_json_default, sort_keys=True)


def _dataclass_or_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if is_dataclass(obj):
        return asdict(obj)
    return dict(obj)


def _df_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [_clean(r) for r in df.to_dict("records")]


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _json_default(obj: Any) -> Any:

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 hex digest of a file's bytes."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
