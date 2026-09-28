"""Preregistered specification constants and schemas for LONG-002D1."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002D1-v1.json"
EXPECTED_SPEC_SHA256 = "cfa450824d269fb80a276ad9986835faf08f5d1a632722d0824502c68f738381"

DEV_START = "2016-01-01"
DEV_END = "2020-12-31"
POPULATION_CUTOFF = "20:30"
TARGET_PCT = 10.0
HORIZON_SESSIONS = 10
EXPECTED_DENOMINATOR = 758731
EXPECTED_CLEAN_EVENTS = 67257
EXPECTED_BASE_RATE = 0.08864406

EXPECTED_STAGE_C_RUN_ID = "2026-09-27-161243"
EXPECTED_STAGE_C_CODE_SHA = "d6a300e556c690c83ff8b9265833667c02dc94ec"

FROZEN_BASELINE_ID = "volatility_aware_momentum_5"
FROZEN_BASELINE_TOP_10_LIFT = 1.7320
FROZEN_BASELINE_TOP_10_CLEAN_RATE = 0.153533
FROZEN_BASELINE_TOP_25_LIFT = 1.4314
FROZEN_BASELINE_TOP_25_CLEAN_RATE = 0.126881


@dataclass(frozen=True)
class FeatureDefinition:
    """Metadata definition for a preregistered feature."""

    feature_id: str
    role: str  # "reference", "candidate", "candidate_diagnostic"
    formula: str
    price_series: str
    min_lookback_sessions: int
    hypothesized_direction: str  # "HIGHER", "LOWER", "NONE"
    status: str  # "review_pending", "reference"
    diagnostic_type: str | None = None


FEATURE_REGISTRY: list[FeatureDefinition] = [
    FeatureDefinition(
        feature_id="return_5",
        role="reference",
        formula="close_t / close_t-5 - 1",
        price_series="split_normalized_close",
        min_lookback_sessions=5,
        hypothesized_direction="NONE",
        status="reference",
    ),
    FeatureDefinition(
        feature_id="return_20",
        role="reference",
        formula="close_t / close_t-20 - 1",
        price_series="split_normalized_close",
        min_lookback_sessions=20,
        hypothesized_direction="NONE",
        status="reference",
    ),
    FeatureDefinition(
        feature_id="return_60",
        role="reference",
        formula="close_t / close_t-60 - 1",
        price_series="split_normalized_close",
        min_lookback_sessions=60,
        hypothesized_direction="NONE",
        status="reference",
    ),
    FeatureDefinition(
        feature_id="atr_pct_14",
        role="reference",
        formula="Wilder_ATR14_t / close_t",
        price_series="split_normalized_close",
        min_lookback_sessions=14,
        hypothesized_direction="NONE",
        status="reference",
    ),
    FeatureDefinition(
        feature_id="close_vs_sma20",
        role="candidate",
        formula="close_t / SMA20_t - 1",
        price_series="split_normalized_close",
        min_lookback_sessions=20,
        hypothesized_direction="HIGHER",
        status="review_pending",
    ),
    FeatureDefinition(
        feature_id="close_vs_sma60",
        role="candidate",
        formula="close_t / SMA60_t - 1",
        price_series="split_normalized_close",
        min_lookback_sessions=60,
        hypothesized_direction="HIGHER",
        status="review_pending",
    ),
    FeatureDefinition(
        feature_id="sma20_slope_5",
        role="candidate",
        formula="SMA20_t / SMA20_t-5 - 1",
        price_series="split_normalized_close",
        min_lookback_sessions=25,
        hypothesized_direction="HIGHER",
        status="review_pending",
    ),
    FeatureDefinition(
        feature_id="proximity_high20",
        role="candidate",
        formula="close_t / rolling_max_close_20_t - 1",
        price_series="split_normalized_close",
        min_lookback_sessions=20,
        hypothesized_direction="HIGHER",
        status="review_pending",
    ),
    FeatureDefinition(
        feature_id="proximity_high60",
        role="candidate",
        formula="close_t / rolling_max_close_60_t - 1",
        price_series="split_normalized_close",
        min_lookback_sessions=60,
        hypothesized_direction="HIGHER",
        status="review_pending",
    ),
    FeatureDefinition(
        feature_id="true_range_compression_5_20",
        role="candidate",
        formula="median(true_range over latest 5 sessions) / median(true_range over latest 20 sessions)",
        price_series="split_normalized_close",
        min_lookback_sessions=20,
        hypothesized_direction="LOWER",
        status="review_pending",
    ),
    FeatureDefinition(
        feature_id="relative_volume_20",
        role="candidate",
        formula="volume_t / median(volume over PRIOR 20 completed sessions, excluding t)",
        price_series="volume",
        min_lookback_sessions=21,
        hypothesized_direction="HIGHER",
        status="review_pending",
    ),
    FeatureDefinition(
        feature_id="dollar_volume_trend_20_60",
        role="candidate",
        formula="median(as_traded_close * volume over latest 20 sessions) / median(as_traded_close * volume over latest 60 sessions) - 1",
        price_series="as_traded_dollar_volume",
        min_lookback_sessions=60,
        hypothesized_direction="HIGHER",
        status="review_pending",
    ),
    FeatureDefinition(
        feature_id="up_volume_share_20",
        role="candidate",
        formula="sum(volume for sessions in latest 20 where close_t > close_t-1) / sum(volume over latest 20)",
        price_series="split_normalized_close_and_volume",
        min_lookback_sessions=20,
        hypothesized_direction="HIGHER",
        status="review_pending",
    ),
    FeatureDefinition(
        feature_id="spy_return_20",
        role="candidate_diagnostic",
        formula="SPY close_t / SPY close_t-20 - 1",
        price_series="split_normalized_close (SPY)",
        min_lookback_sessions=20,
        hypothesized_direction="HIGHER",
        status="review_pending",
        diagnostic_type="market_regime_date_level",
    ),
    FeatureDefinition(
        feature_id="stock_minus_spy_20",
        role="reference",
        formula="return_20 - spy_return_20",
        price_series="split_normalized_close",
        min_lookback_sessions=20,
        hypothesized_direction="NONE",
        status="reference",
        diagnostic_type="cross_sectional_redundancy_diagnostic",
    ),
]

FEATURE_MAP: dict[str, FeatureDefinition] = {f.feature_id: f for f in FEATURE_REGISTRY}


def load_spec_payload(spec_path: Path | None = None) -> dict[str, Any]:
    """Load and return the machine-readable preregistered specification."""
    p = spec_path or SPEC_PATH
    if not p.exists():
        raise FileNotFoundError(f"Preregistration spec not found at {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def enforce_split_guard(as_of_date: str) -> None:
    """Enforce strict quarantine guard: reject any date past the development split."""
    if as_of_date > DEV_END:
        raise ValueError(
            f"SPLIT QUARANTINE BREACH: as_of_date '{as_of_date}' exceeds development split end '{DEV_END}'. "
            "Validation and holdout splits are strictly quarantined."
        )
