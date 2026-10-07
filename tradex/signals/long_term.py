"""
Production-Target Long Opportunity Strategy v1 (LONG-MVP-001 / LONG-MVP-002).

Implements the deterministic, explainable, three-archetype long opportunity engine
on daily OHLCV bars over ~2 years (minimum 220 usable daily sessions).

Archetypes:
  1. momentum_continuation
  2. trend_pullback
  3. breakout_expansion

Execution states:
  - ENTER NOW (score >= 75 + actionable confirmation trigger met)
  - ARMED (score >= 70 + armed proximity condition met)
  - QUALIFIED WAITLIST (score >= 60 + archetype qualified)
  - NOT SURFACED (score < 60, failing archetype, or failing eligibility floor)

Scoring:
  100 points maximum:
    Trend Quality:      30 pts (universal)
    Momentum Quality:   25 pts (archetype-aware)
    Setup Quality:      20 pts (archetype-specific)
    Movement Capacity:  15 pts (universal)
    Participation:      10 pts (universal)

Contract invariant:
  Scoring is strictly locked by the strategy contract. No user weights,
  config files (~/.tradex/weights.json), or ML models can alter long scoring.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .indicators import add_indicators

STRATEGY_ID = "long_mvp"
STRATEGY_VERSION = "v1"

MIN_BARS = 220
MIN_PRICE = 5.00
MIN_MEDIAN_DOLLAR_VOLUME = 20_000_000.0  # $20M floor

ARCHETYPE_BREAKOUT = "breakout_expansion"
ARCHETYPE_MOMENTUM = "momentum_continuation"
ARCHETYPE_PULLBACK = "trend_pullback"

ORDERED_ARCHETYPES = [
    ARCHETYPE_BREAKOUT,
    ARCHETYPE_MOMENTUM,
    ARCHETYPE_PULLBACK,
]

STATE_ENTER_NOW = "ENTER NOW"
STATE_ARMED = "ARMED"
STATE_QUALIFIED_WAITLIST = "QUALIFIED WAITLIST"


def _score_trend_quality(
    close: float, ema_20: float, ema_50: float, ema_200: float, ema20_slope_5: float
) -> int:
    """Trend Quality (30 Points Universal): evaluate moving average stacking and slope."""
    pts = 0
    if close > ema_20:
        pts += 8
    if ema_20 > ema_50:
        pts += 8
    if ema_50 > ema_200:
        pts += 8
    if ema20_slope_5 > 0:
        pts += 6
    return pts


def _score_movement_capacity(atr_pct: float) -> int:
    """Movement Capacity (15 Points Universal): swing percentage capacity using ATR / close."""
    if 0.020 <= atr_pct <= 0.060:
        return 15
    if (0.015 <= atr_pct < 0.020) or (0.060 < atr_pct <= 0.080):
        return 10
    if (0.010 <= atr_pct < 0.015) or (atr_pct > 0.080):
        return 5
    return 0


def _score_participation(volume_ratio: float) -> int:
    """Participation (10 Points Universal): relative volume turnover."""
    if volume_ratio >= 1.50:
        return 10
    if 1.20 <= volume_ratio < 1.50:
        return 8
    if 1.00 <= volume_ratio < 1.20:
        return 6
    if 0.80 <= volume_ratio < 1.00:
        return 3
    return 0


def _score_momentum_quality(
    archetype: str,
    return_5: float,
    return_20: float,
    return_60: float,
    rsi: float,
) -> int:
    """Momentum Quality (25 Points Archetype-Aware)."""
    pts = 0
    if archetype in (ARCHETYPE_MOMENTUM, ARCHETYPE_BREAKOUT):
        if return_20 > 0:
            pts += 5
        if return_20 >= 0.05:
            pts += 5
        if return_60 > 0:
            pts += 5
        if return_60 >= 0.10:
            pts += 5
        if return_5 > 0:
            pts += 5
    elif archetype == ARCHETYPE_PULLBACK:
        if return_60 > 0:
            pts += 5
        if return_60 >= 0.10:
            pts += 5
        if return_20 > 0:
            pts += 5
        if -0.08 <= return_5 <= 0.0:
            pts += 5
        if 40.0 <= rsi <= 60.0:
            pts += 5
    return pts


def _score_setup_quality(
    archetype: str,
    close: float,
    close_prev: float,
    ema_20: float,
    prior_20d_high: float,
    return_5: float,
    rsi: float,
    volume_ratio: float,
) -> int:
    """Setup Quality (20 Points Archetype-Specific)."""
    pts = 0
    if archetype == ARCHETYPE_MOMENTUM:
        if close >= 0.97 * prior_20d_high:
            pts += 8
        if 55.0 <= rsi <= 70.0:
            pts += 6
        if 0.0 <= return_5 <= 0.08:
            pts += 6
    elif archetype == ARCHETYPE_PULLBACK:
        if abs(close - ema_20) / ema_20 <= 0.02:
            pts += 8
        if close > ema_20:
            pts += 6
        if -0.06 <= return_5 <= 0.0:
            pts += 6
    elif archetype == ARCHETYPE_BREAKOUT:
        if close > prior_20d_high:
            pts += 10
        if volume_ratio >= 1.30:
            pts += 6
        if close > close_prev:
            pts += 4
    return pts


def _build_archetype_eval(
    archetype: str,
    close: float,
    close_prev: float,
    high_prev: float,
    ema_20: float,
    ema_50: float,
    ema_200: float,
    prior_5d_high: float,
    prior_20d_high: float,
    return_5: float,
    return_20: float,
    return_60: float,
    rsi: float,
    atr_pct: float,
    volume_ratio: float,
    ema20_slope_5: float,
) -> dict[str, Any]:
    """Compute score, component breakdown, triggers, and state for one archetype."""
    trend_q = _score_trend_quality(close, ema_20, ema_50, ema_200, ema20_slope_5)
    mom_q = _score_momentum_quality(archetype, return_5, return_20, return_60, rsi)
    setup_q = _score_setup_quality(
        archetype, close, close_prev, ema_20, prior_20d_high, return_5, rsi, volume_ratio
    )
    move_c = _score_movement_capacity(atr_pct)
    part_q = _score_participation(volume_ratio)

    total_score = min(trend_q + mom_q + setup_q + move_c + part_q, 100)

    # Actionable and armed conditions
    if archetype == ARCHETYPE_MOMENTUM:
        actionable = close > prior_5d_high
        armed = (0.98 * prior_5d_high <= close <= prior_5d_high)
        trigger = f"Hold/reclaim above prior 5-session high (${prior_5d_high:.2f})"
        invalidation = f"Close below EMA50 (${ema_50:.2f})"
    elif archetype == ARCHETYPE_PULLBACK:
        actionable = (close >= ema_20) and (close > high_prev)
        armed = (abs(close - ema_20) / ema_20 <= 0.02) and (close > ema_50)
        trigger = (
            f"Reclaim EMA20 (${ema_20:.2f}) and close above prior-session high (${high_prev:.2f})"
        )
        invalidation = f"Close below EMA50 (${ema_50:.2f})"
    elif archetype == ARCHETYPE_BREAKOUT:
        actionable = (close > prior_20d_high) and (volume_ratio >= 1.30)
        armed = (0.98 * prior_20d_high <= close <= prior_20d_high)
        trigger = (
            f"Close above prior 20-session high (${prior_20d_high:.2f}) with volume >= 1.3x 20-day average"
        )
        invalidation = (
            f"Close back below EMA20 (${ema_20:.2f}) after breakout confirmation OR close below EMA50 (${ema_50:.2f})"
        )
    else:
        actionable = False
        armed = False
        trigger = None
        invalidation = None

    if total_score >= 75 and actionable:
        state = STATE_ENTER_NOW
    elif total_score >= 70 and not actionable and armed:
        state = STATE_ARMED
    elif total_score >= 60:
        state = STATE_QUALIFIED_WAITLIST
    else:
        state = None

    # Factual reasons
    reasons: list[str] = []
    if close > ema_20 > ema_50 > ema_200:
        reasons.append("Price > EMA20 > EMA50 > EMA200")
    elif ema_20 > ema_50 > ema_200:
        reasons.append("EMA20 > EMA50 > EMA200")
    else:
        reasons.append("Price > EMA50 > EMA200")

    reasons.append(f"20-day return {return_20:+.1%}; 60-day return {return_60:+.1%}")

    if close >= prior_20d_high:
        reasons.append(f"Trading at/above prior 20-day high (${prior_20d_high:.2f})")
    else:
        dist_20d = (prior_20d_high - close) / prior_20d_high
        reasons.append(f"Trading {dist_20d:.1%} below prior 20-day high (${prior_20d_high:.2f})")

    if archetype == ARCHETYPE_PULLBACK:
        dist_ema20 = (close - ema_20) / ema_20
        reasons.append(
            f"Pullback is {abs(dist_ema20):.1%} from EMA20 while primary trend remains intact"
        )
    elif archetype == ARCHETYPE_BREAKOUT:
        if close > prior_20d_high and volume_ratio >= 1.30:
            reasons.append(f"Breakout above prior 20-day high on {volume_ratio:.1f}x volume")
        else:
            reasons.append(f"Consolidating at resistance on {volume_ratio:.2f}x volume")
    elif archetype == ARCHETYPE_MOMENTUM:
        reasons.append(f"5-day return {return_5:+.1%}; RSI at {rsi:.1f}")

    reasons.append(f"Volume ratio {volume_ratio:.2f}x; ATR {atr_pct:.1%} of price")

    return {
        "score": total_score,
        "state": state,
        "component_scores": {
            "trend_quality": trend_q,
            "momentum_quality": mom_q,
            "setup_quality": setup_q,
            "movement_capacity": move_c,
            "participation": part_q,
        },
        "trigger": trigger,
        "invalidation": invalidation,
        "reasons": reasons,
    }


def score(df: pd.DataFrame, weights: Any = None) -> dict[str, Any]:
    """Score a stock using the LONG MVP v1 strategy.

    The ``weights`` parameter is preserved for call-site backward compatibility,
    but is strictly ignored. LONG MVP v1 scoring is locked by contract.

    Returns the contract dictionary specified in docs/product/LONG-MVP-001.md.
    """
    empty_components = {
        "trend_quality": 0,
        "momentum_quality": 0,
        "setup_quality": 0,
        "movement_capacity": 0,
        "participation": 0,
    }

    # 1. Gate: Minimum usable daily bars (fail closed)
    if df is None or len(df) < MIN_BARS:
        last_close = float(df["close"].iloc[-1]) if df is not None and not df.empty else 0.0
        return {
            "strategy_id": STRATEGY_ID,
            "strategy_version": STRATEGY_VERSION,
            "score": 0,
            "primary_setup": None,
            "matched_setups": [],
            "state": None,
            "component_scores": empty_components,
            "reasons": [f"Insufficient daily history ({len(df) if df is not None else 0} bars < {MIN_BARS} required)"],
            "trigger": None,
            "invalidation": None,
            "last_close": last_close,
            "volume_ratio": 0.0,
            "rsi": 0.0,
            "atr_pct": 0.0,
            "return_5": 0.0,
            "return_20": 0.0,
            "return_60": 0.0,
            "qualified": False,
            "insufficient_data": True,
        }

    # 2. Compute indicator feature set
    df_ind = add_indicators(df)
    last = df_ind.iloc[-1]
    prev = df_ind.iloc[-2]

    # Required scalar values
    try:
        close = float(last["close"])
        close_prev = float(prev["close"])
        high_prev = float(prev["high"])
        ema_20 = float(last["ema_20"])
        ema_50 = float(last["ema_50"])
        ema_200 = float(last["ema_200"])
        rsi = float(last["rsi"])
        atr = float(last["atr"])
        atr_pct = float(last["atr_pct"])
        volume_ratio = float(last["volume_ratio"])
        median_dv_20 = float(last["median_dollar_volume_20"])
        return_5 = float(last["return_5"])
        return_20 = float(last["return_20"])
        return_60 = float(last["return_60"])
        prior_5d_high = float(last["prior_5d_high"])
        prior_20d_high = float(last["prior_20d_high"])
        ema20_slope_5 = float(last["ema20_slope_5"])
    except (KeyError, ValueError, TypeError) as exc:
        return {
            "strategy_id": STRATEGY_ID,
            "strategy_version": STRATEGY_VERSION,
            "score": 0,
            "primary_setup": None,
            "matched_setups": [],
            "state": None,
            "component_scores": empty_components,
            "reasons": [f"Malformed indicator feature data: {exc}"],
            "trigger": None,
            "invalidation": None,
            "last_close": float(last.get("close", 0.0)),
            "volume_ratio": 0.0,
            "rsi": 0.0,
            "atr_pct": 0.0,
            "return_5": 0.0,
            "return_20": 0.0,
            "return_60": 0.0,
            "qualified": False,
            "insufficient_data": True,
        }

    # Verify all required indicators are valid finite numbers
    required_scalars = [
        close, close_prev, high_prev, ema_20, ema_50, ema_200, rsi, atr, atr_pct,
        volume_ratio, median_dv_20, return_5, return_20, return_60,
        prior_5d_high, prior_20d_high, ema20_slope_5,
    ]
    if any(not np.isfinite(x) for x in required_scalars):
        return {
            "strategy_id": STRATEGY_ID,
            "strategy_version": STRATEGY_VERSION,
            "score": 0,
            "primary_setup": None,
            "matched_setups": [],
            "state": None,
            "component_scores": empty_components,
            "reasons": ["Non-finite or missing required indicator value (EMA200, returns, or volatility)"],
            "trigger": None,
            "invalidation": None,
            "last_close": round(close, 4) if np.isfinite(close) else 0.0,
            "volume_ratio": round(volume_ratio, 2) if np.isfinite(volume_ratio) else 0.0,
            "rsi": round(rsi, 1) if np.isfinite(rsi) else 0.0,
            "atr_pct": round(atr_pct, 4) if np.isfinite(atr_pct) else 0.0,
            "return_5": round(return_5, 4) if np.isfinite(return_5) else 0.0,
            "return_20": round(return_20, 4) if np.isfinite(return_20) else 0.0,
            "return_60": round(return_60, 4) if np.isfinite(return_60) else 0.0,
            "qualified": False,
            "insufficient_data": True,
        }

    # 3. Eligibility Floor Verification
    # Floor gates:
    #   1. >= 220 bars (checked above)
    #   2. close >= $5.00
    #   3. median_dollar_volume_20 >= $20,000,000
    #   4. EMA200 finite & available (checked above)
    #   5. close > EMA50
    #   6. EMA50 > EMA200
    floor_failures: list[str] = []
    if close < MIN_PRICE:
        floor_failures.append(f"Price (${close:.2f}) below ${MIN_PRICE:.2f} floor")
    if median_dv_20 < MIN_MEDIAN_DOLLAR_VOLUME:
        floor_failures.append(
            f"20-day median dollar volume (${median_dv_20:,.0f}) below ${MIN_MEDIAN_DOLLAR_VOLUME:,.0f} floor"
        )
    if close <= ema_50:
        floor_failures.append(f"Price (${close:.2f}) below EMA50 (${ema_50:.2f})")
    if ema_50 <= ema_200:
        floor_failures.append(f"EMA50 (${ema_50:.2f}) below EMA200 (${ema_200:.2f})")

    if floor_failures:
        return {
            "strategy_id": STRATEGY_ID,
            "strategy_version": STRATEGY_VERSION,
            "score": 0,
            "primary_setup": None,
            "matched_setups": [],
            "state": None,
            "component_scores": empty_components,
            "reasons": floor_failures,
            "trigger": None,
            "invalidation": None,
            "last_close": round(close, 4),
            "volume_ratio": round(volume_ratio, 2),
            "rsi": round(rsi, 1),
            "atr_pct": round(atr_pct, 4),
            "return_5": round(return_5, 4),
            "return_20": round(return_20, 4),
            "return_60": round(return_60, 4),
            "qualified": False,
            "insufficient_data": False,
        }

    # 4. Archetype Qualification Evaluation
    matched_setups: list[str] = []

    # Archetype 1: Momentum Continuation
    # - close > EMA20 > EMA50 > EMA200
    # - return_20 >= 0.05
    # - return_60 >= 0.10
    # - close >= 0.95 * prior_20d_high
    # - 50 <= RSI14 <= 75
    if (
        close > ema_20 > ema_50 > ema_200
        and return_20 >= 0.05
        and return_60 >= 0.10
        and close >= 0.95 * prior_20d_high
        and 50.0 <= rsi <= 75.0
    ):
        matched_setups.append(ARCHETYPE_MOMENTUM)

    # Archetype 2: Trend Pullback
    # - EMA20 > EMA50 > EMA200
    # - return_60 >= 0.10
    # - close > EMA50
    # - -0.08 <= return_5 <= 0.02
    # - abs(close - EMA20) / EMA20 <= 0.04
    # - 40 <= RSI14 <= 62
    if (
        ema_20 > ema_50 > ema_200
        and return_60 >= 0.10
        and close > ema_50
        and -0.08 <= return_5 <= 0.02
        and (abs(close - ema_20) / ema_20) <= 0.04
        and 40.0 <= rsi <= 62.0
    ):
        matched_setups.append(ARCHETYPE_PULLBACK)

    # Archetype 3: Breakout / Expansion
    # - EMA20 > EMA50 > EMA200
    # - close >= 0.98 * prior_20d_high
    # - 50 <= RSI14 <= 78
    if (
        ema_20 > ema_50 > ema_200
        and close >= 0.98 * prior_20d_high
        and 50.0 <= rsi <= 78.0
    ):
        matched_setups.append(ARCHETYPE_BREAKOUT)

    # If no archetype matched:
    if not matched_setups:
        return {
            "strategy_id": STRATEGY_ID,
            "strategy_version": STRATEGY_VERSION,
            "score": 0,
            "primary_setup": None,
            "matched_setups": [],
            "state": None,
            "component_scores": empty_components,
            "reasons": ["Passed eligibility floor but matched no active setup archetype"],
            "trigger": None,
            "invalidation": None,
            "last_close": round(close, 4),
            "volume_ratio": round(volume_ratio, 2),
            "rsi": round(rsi, 1),
            "atr_pct": round(atr_pct, 4),
            "return_5": round(return_5, 4),
            "return_20": round(return_20, 4),
            "return_60": round(return_60, 4),
            "qualified": False,
            "insufficient_data": False,
        }

    # Deterministic ordering for matched setups: breakout -> momentum -> pullback
    ordered_matches = [a for a in ORDERED_ARCHETYPES if a in matched_setups]

    # Evaluate scoring and state for every matched archetype
    evaluations: dict[str, dict[str, Any]] = {}
    for arch in ordered_matches:
        evaluations[arch] = _build_archetype_eval(
            arch,
            close=close,
            close_prev=close_prev,
            high_prev=high_prev,
            ema_20=ema_20,
            ema_50=ema_50,
            ema_200=ema_200,
            prior_5d_high=prior_5d_high,
            prior_20d_high=prior_20d_high,
            return_5=return_5,
            return_20=return_20,
            return_60=return_60,
            rsi=rsi,
            atr_pct=atr_pct,
            volume_ratio=volume_ratio,
            ema20_slope_5=ema20_slope_5,
        )

    # Primary setup selection:
    # Archetype with the highest score.
    # Tie-break: ORDERED_ARCHETYPES (breakout -> momentum -> pullback)
    best_score = max(evaluations[a]["score"] for a in ordered_matches)
    primary_setup = next(a for a in ordered_matches if evaluations[a]["score"] == best_score)
    primary_eval = evaluations[primary_setup]

    return {
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "score": int(primary_eval["score"]),
        "primary_setup": primary_setup,
        "matched_setups": ordered_matches,
        "state": primary_eval["state"],
        "component_scores": primary_eval["component_scores"],
        "reasons": primary_eval["reasons"],
        "trigger": primary_eval["trigger"],
        "invalidation": primary_eval["invalidation"],
        "last_close": round(close, 4),
        "volume_ratio": round(volume_ratio, 2),
        "rsi": round(rsi, 1),
        "atr_pct": round(atr_pct, 4),
        "return_5": round(return_5, 4),
        "return_20": round(return_20, 4),
        "return_60": round(return_60, 4),
        "qualified": True,
        "insufficient_data": False,
    }
