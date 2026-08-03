"""Context-study specification loading and validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradex.market.models import ShortContextPolicy
from tradex.research.short_context.models import (
    ShortContextSpec,
    ValidationError,
    _require_finite_nonnegative_number,
    _require_percentage,
    _require_positive_int,
)

_ALLOWED_TOP_KEYS = {
    "schema_version",
    "study_name",
    "target_tickers",
    "default_market_proxy",
    "ticker_context",
    "candidate_policies",
    "primary_horizon_bars",
    "primary_slippage_bps",
    "horizons",
    "slippage_scenarios_bps",
    "commission_bps",
    "minimum_validation_events",
    "minimum_holdout_events",
    "minimum_holdout_tickers",
    "minimum_event_retention_pct",
    "minimum_ticker_coverage_pct",
    "baseline_score_threshold",
}

_ALLOWED_CONTEXT_KEYS = {"market_proxy", "sector_proxy"}


def load_spec(path: str | Path) -> tuple[ShortContextSpec, bytes]:
    """Load and validate a context-study specification from ``path``.

    Returns the parsed ``ShortContextSpec`` and the raw file bytes so callers can
    compute a SHA-256 lock.
    """
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValidationError(f"Context spec not found: {path}")
    raw_bytes = path.read_bytes()
    data = json.loads(raw_bytes.decode("utf-8"))
    spec = _parse_spec(data)
    return spec, raw_bytes


def _parse_spec(data: dict[str, Any]) -> ShortContextSpec:
    if not isinstance(data, dict):
        raise ValidationError("Context spec must be a JSON object")

    unknown = set(data.keys()) - _ALLOWED_TOP_KEYS
    if unknown:
        raise ValidationError(f"Context spec contains unknown top-level keys: {sorted(unknown)}")

    schema_version = data.get("schema_version", 1)
    _validate_no_bool("schema_version", schema_version)
    _require_positive_int("schema_version", schema_version)

    study_name = data.get("study_name")
    if not study_name or not isinstance(study_name, str):
        raise ValidationError("study_name must be a nonempty string")

    target_tickers = data.get("target_tickers")
    if not isinstance(target_tickers, list) or not target_tickers:
        raise ValidationError("target_tickers must be a nonempty list")
    for t in target_tickers:
        if not isinstance(t, str) or not t:
            raise ValidationError(f"target ticker must be a nonempty string; got {t!r}")
        if t != t.upper():
            raise ValidationError(f"target ticker must be uppercase; got {t!r}")

    default_market_proxy = data.get("default_market_proxy")
    if not default_market_proxy or not isinstance(default_market_proxy, str):
        raise ValidationError("default_market_proxy must be a nonempty string")
    if default_market_proxy != default_market_proxy.upper():
        raise ValidationError("default_market_proxy must be uppercase")

    ticker_context_raw = data.get("ticker_context")
    if not isinstance(ticker_context_raw, dict) or not ticker_context_raw:
        raise ValidationError("ticker_context must be a nonempty object")
    ticker_context: dict[str, dict[str, str | None]] = {}
    for t in target_tickers:
        ctx = ticker_context_raw.get(t)
        if ctx is None:
            raise ValidationError(f"missing ticker_context for {t}")
        if not isinstance(ctx, dict):
            raise ValidationError(f"ticker_context[{t!r}] must be an object")
        unknown_ctx = set(ctx.keys()) - _ALLOWED_CONTEXT_KEYS
        if unknown_ctx:
            raise ValidationError(f"ticker_context[{t}] contains unknown keys: {sorted(unknown_ctx)}")
        market = ctx.get("market_proxy")
        if market is None or not isinstance(market, str) or not market:
            raise ValidationError(f"ticker_context[{t}].market_proxy must be a nonempty string")
        if market != market.upper():
            raise ValidationError(f"ticker_context[{t}].market_proxy must be uppercase")
        if market == t:
            raise ValidationError(f"target {t} cannot be its own market_proxy")
        sector = ctx.get("sector_proxy")
        if sector is not None and (not isinstance(sector, str) or not sector):
            raise ValidationError(f"ticker_context[{t}].sector_proxy must be a nonempty string or null")
        if sector is not None and sector != sector.upper():
            raise ValidationError(f"ticker_context[{t}].sector_proxy must be uppercase")
        if sector is not None and sector == t:
            raise ValidationError(f"target {t} cannot be its own sector_proxy")
        ticker_context[t] = {"market_proxy": market, "sector_proxy": sector}

    candidate_policies_raw = data.get("candidate_policies")
    if not isinstance(candidate_policies_raw, list) or not candidate_policies_raw:
        raise ValidationError("candidate_policies must be a nonempty list")
    candidate_policies: list[ShortContextPolicy] = []
    seen_policies: set[str] = set()
    for p in candidate_policies_raw:
        if not isinstance(p, str):
            raise ValidationError(f"candidate policy must be a string; got {p!r}")
        try:
            policy = ShortContextPolicy(p)
        except ValueError as exc:
            raise ValidationError(f"unknown candidate policy: {p}") from exc
        if policy == ShortContextPolicy.OFF:
            raise ValidationError("candidate policy cannot be 'off'")
        if policy.value in seen_policies:
            raise ValidationError(f"duplicate candidate policy: {p}")
        seen_policies.add(policy.value)
        candidate_policies.append(policy)

    primary_horizon_bars = data.get("primary_horizon_bars", 3)
    _validate_no_bool("primary_horizon_bars", primary_horizon_bars)
    _require_positive_int("primary_horizon_bars", primary_horizon_bars)

    primary_slippage_bps = data.get("primary_slippage_bps", 5.0)
    _validate_no_bool("primary_slippage_bps", primary_slippage_bps)
    _require_finite_nonnegative_number("primary_slippage_bps", primary_slippage_bps)

    horizons = data.get("horizons", (1, 3, 5))
    if isinstance(horizons, list):
        horizons = tuple(horizons)
    for h in horizons:
        _validate_no_bool("horizons element", h)
        _require_positive_int("horizons element", h)
    if sorted(set(horizons)) != list(horizons):
        raise ValidationError(f"horizons must be unique and sorted; got {horizons}")

    slippage_scenarios_bps = data.get("slippage_scenarios_bps", (0.0, 5.0, 10.0))
    if isinstance(slippage_scenarios_bps, list):
        slippage_scenarios_bps = tuple(slippage_scenarios_bps)
    for s in slippage_scenarios_bps:
        _validate_no_bool("slippage_scenarios_bps element", s)
        _require_finite_nonnegative_number("slippage_scenarios_bps element", s)

    commission_bps = data.get("commission_bps", 0.0)
    _validate_no_bool("commission_bps", commission_bps)
    _require_finite_nonnegative_number("commission_bps", commission_bps)

    minimum_validation_events = data.get("minimum_validation_events", None)
    if minimum_validation_events is not None:
        _validate_no_bool("minimum_validation_events", minimum_validation_events)
        _require_positive_int("minimum_validation_events", minimum_validation_events)

    minimum_holdout_events = data.get("minimum_holdout_events", 100)
    _validate_no_bool("minimum_holdout_events", minimum_holdout_events)
    _require_positive_int("minimum_holdout_events", minimum_holdout_events)

    minimum_holdout_tickers = data.get("minimum_holdout_tickers", 10)
    _validate_no_bool("minimum_holdout_tickers", minimum_holdout_tickers)
    _require_positive_int("minimum_holdout_tickers", minimum_holdout_tickers)

    minimum_event_retention_pct = data.get("minimum_event_retention_pct", 25.0)
    _validate_no_bool("minimum_event_retention_pct", minimum_event_retention_pct)
    _require_percentage("minimum_event_retention_pct", minimum_event_retention_pct)

    minimum_ticker_coverage_pct = data.get("minimum_ticker_coverage_pct", 50.0)
    _validate_no_bool("minimum_ticker_coverage_pct", minimum_ticker_coverage_pct)
    _require_percentage("minimum_ticker_coverage_pct", minimum_ticker_coverage_pct)

    baseline_score_threshold = data.get("baseline_score_threshold", 40)
    _validate_no_bool("baseline_score_threshold", baseline_score_threshold)
    _require_positive_int("baseline_score_threshold", baseline_score_threshold)
    if not (0 <= baseline_score_threshold <= 100):
        raise ValidationError(f"baseline_score_threshold must be 0-100; got {baseline_score_threshold}")

    if primary_horizon_bars not in horizons:
        raise ValidationError(
            f"primary_horizon_bars {primary_horizon_bars} must be one of {list(horizons)}"
        )
    if primary_slippage_bps not in slippage_scenarios_bps:
        raise ValidationError(
            f"primary_slippage_bps {primary_slippage_bps} must be one of {list(slippage_scenarios_bps)}"
        )

    return ShortContextSpec(
        study_name=study_name,
        target_tickers=tuple(target_tickers),
        ticker_context=ticker_context,
        candidate_policies=tuple(candidate_policies),
        default_market_proxy=default_market_proxy,
        primary_horizon_bars=primary_horizon_bars,
        primary_slippage_bps=primary_slippage_bps,
        horizons=horizons,
        slippage_scenarios_bps=slippage_scenarios_bps,
        commission_bps=commission_bps,
        minimum_validation_events=minimum_validation_events,
        minimum_holdout_events=minimum_holdout_events,
        minimum_holdout_tickers=minimum_holdout_tickers,
        minimum_event_retention_pct=minimum_event_retention_pct,
        minimum_ticker_coverage_pct=minimum_ticker_coverage_pct,
        baseline_score_threshold=baseline_score_threshold,
        schema_version=schema_version,
    )


def _validate_no_bool(name: str, value: Any) -> None:
    if isinstance(value, bool):
        raise ValidationError(f"{name} must not be a boolean; got {value}")


def _require_int(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or isinstance(value, float):
        raise ValidationError(f"{name} must be an integer; got {value!r} ({type(value).__name__})")

