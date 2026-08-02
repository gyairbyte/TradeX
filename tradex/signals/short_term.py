"""
Short-term signals (days to weeks): trend momentum + volume confirmation.
"""
import pandas as pd
from .indicators import add_indicators
from .weights import ShortWeights, load as load_weights


def _evaluate_components(df: pd.DataFrame, weights: ShortWeights) -> dict:
    """Return component flags, point contributions, and reasons for the most recent bar.

    The returned ``raw_score`` is the sum of the awarded component points *before*
    the existing 100-point cap. This preserves additive component accounting while
    keeping the public ``score`` capped at ``min(raw_score, 100)``.
    """
    df = add_indicators(df)
    last = df.iloc[-1]

    components = {
        "ema_structure": False,
        "volume_confirmation": False,
        "rsi_momentum": False,
        "macd_positive": False,
        "pullback_ema": False,
    }
    component_points = {
        "ema_structure": 0,
        "volume_confirmation": 0,
        "rsi_momentum": 0,
        "macd_positive": 0,
        "pullback_ema": 0,
    }
    reasons = []

    if last["close"] > last["ema_20"] > last["ema_50"]:
        components["ema_structure"] = True
        component_points["ema_structure"] = weights.ema_structure
        reasons.append("Price above EMA20 > EMA50 — bullish structure")

    if last["volume_ratio"] >= 1.3:
        components["volume_confirmation"] = True
        component_points["volume_confirmation"] = weights.volume_confirmation
        reasons.append(f"Volume confirming move ({last['volume_ratio']:.1f}x avg)")

    if 50 <= last["rsi"] <= 70:
        components["rsi_momentum"] = True
        component_points["rsi_momentum"] = weights.rsi_momentum
        reasons.append(f"RSI in momentum zone ({last['rsi']:.0f})")

    if last["macd"] > 0 and last["macd_diff"] > 0:
        components["macd_positive"] = True
        component_points["macd_positive"] = weights.macd_positive
        reasons.append("MACD positive and expanding")

    ema_proximity = abs(last["close"] - last["ema_20"]) / last["ema_20"]
    if ema_proximity < 0.015 and last["ema_20"] > last["ema_50"]:
        components["pullback_ema"] = True
        component_points["pullback_ema"] = weights.pullback_ema
        reasons.append("Pullback to EMA20 in uptrend — entry opportunity")

    return {
        "components": components,
        "component_points": component_points,
        "raw_score": sum(component_points.values()),
        "reasons": reasons,
        "last_close": last["close"],
        "volume_ratio": last["volume_ratio"],
        "rsi": last["rsi"],
    }


def score(df: pd.DataFrame, weights: ShortWeights | None = None) -> dict:
    if weights is None:
        weights = load_weights().short

    result = _evaluate_components(df, weights)
    return {
        "score": min(result["raw_score"], 100),
        "reasons": result["reasons"],
        "last_close": result["last_close"],
        "volume_ratio": result["volume_ratio"],
        "rsi": result["rsi"],
        "components": result["components"],
        "component_points": result["component_points"],
    }
