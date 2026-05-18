"""
Short-term signals (days to weeks): trend momentum + volume confirmation.
"""
import pandas as pd
from .indicators import add_indicators
from .weights import ShortWeights, load as load_weights


def score(df: pd.DataFrame, weights: ShortWeights | None = None) -> dict:
    if weights is None:
        weights = load_weights().short

    df = add_indicators(df)
    last = df.iloc[-1]
    signals = []
    reasons = []

    if last["close"] > last["ema_20"] > last["ema_50"]:
        signals.append(weights.ema_structure)
        reasons.append("Price above EMA20 > EMA50 — bullish structure")

    if last["volume_ratio"] >= 1.3:
        signals.append(weights.volume_confirmation)
        reasons.append(f"Volume confirming move ({last['volume_ratio']:.1f}x avg)")

    if 50 <= last["rsi"] <= 70:
        signals.append(weights.rsi_momentum)
        reasons.append(f"RSI in momentum zone ({last['rsi']:.0f})")

    if last["macd"] > 0 and last["macd_diff"] > 0:
        signals.append(weights.macd_positive)
        reasons.append("MACD positive and expanding")

    ema_proximity = abs(last["close"] - last["ema_20"]) / last["ema_20"]
    if ema_proximity < 0.015 and last["ema_20"] > last["ema_50"]:
        signals.append(weights.pullback_ema)
        reasons.append("Pullback to EMA20 in uptrend — entry opportunity")

    return {
        "score": min(sum(signals), 100),
        "reasons": reasons,
        "last_close": last["close"],
        "volume_ratio": last["volume_ratio"],
        "rsi": last["rsi"],
    }
