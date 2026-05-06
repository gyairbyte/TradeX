"""
Short-term signals (days to weeks): trend momentum + volume confirmation.
"""
import pandas as pd
from .indicators import add_indicators


def score(df: pd.DataFrame) -> dict:
    df = add_indicators(df)
    last = df.iloc[-1]
    signals = []
    reasons = []

    # Price above both EMAs (uptrend structure)
    if last["close"] > last["ema_20"] > last["ema_50"]:
        signals.append(25)
        reasons.append("Price above EMA20 > EMA50 — bullish structure")

    # Volume confirmation on recent move
    if last["volume_ratio"] >= 1.3:
        signals.append(20)
        reasons.append(f"Volume confirming move ({last['volume_ratio']:.1f}x avg)")

    # RSI in momentum zone
    if 50 <= last["rsi"] <= 70:
        signals.append(20)
        reasons.append(f"RSI in momentum zone ({last['rsi']:.0f})")

    # MACD positive and rising
    if last["macd"] > 0 and last["macd_diff"] > 0:
        signals.append(20)
        reasons.append("MACD positive and expanding")

    # Pullback to EMA20 in uptrend (buy-the-dip)
    ema_proximity = abs(last["close"] - last["ema_20"]) / last["ema_20"]
    if ema_proximity < 0.015 and last["ema_20"] > last["ema_50"]:
        signals.append(15)
        reasons.append("Pullback to EMA20 in uptrend — entry opportunity")

    return {
        "score": min(sum(signals), 100),
        "reasons": reasons,
        "last_close": last["close"],
        "volume_ratio": last["volume_ratio"],
        "rsi": last["rsi"],
    }
