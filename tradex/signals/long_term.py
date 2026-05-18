"""
Long-term signals (weeks to months): macro trend, value, and accumulation patterns.
"""
import pandas as pd
from .indicators import add_indicators
from .weights import LongWeights, load as load_weights


def score(df: pd.DataFrame, weights: LongWeights | None = None) -> dict:
    if weights is None:
        weights = load_weights().long

    df = add_indicators(df)
    last = df.iloc[-1]
    signals = []
    reasons = []

    if last["close"] > last["ema_50"]:
        signals.append(weights.secular_uptrend)
        reasons.append("Price above long-term EMA50 — secular uptrend")

    if 40 <= last["rsi"] <= 65:
        signals.append(weights.rsi_healthy)
        reasons.append(f"RSI healthy, not overbought ({last['rsi']:.0f})")

    recent_vol_ratio = df["volume_ratio"].iloc[-8:].mean()
    if recent_vol_ratio >= 1.15:
        signals.append(weights.volume_accumulation)
        reasons.append(f"8-period volume accumulation ({recent_vol_ratio:.2f}x avg)")

    if last["macd"] > last["macd_signal"]:
        signals.append(weights.macd_bullish)
        reasons.append("MACD above signal on weekly — bullish bias")

    bb_width_pct = df["bb_width"].rank(pct=True).iloc[-1]
    if bb_width_pct < 0.25:
        signals.append(weights.bb_coil)
        reasons.append("Tight BB on weekly — coiling for breakout")

    return {
        "score": min(sum(signals), 100),
        "reasons": reasons,
        "last_close": last["close"],
        "volume_ratio": last["volume_ratio"],
        "rsi": last["rsi"],
    }
