"""
Long-term signals (weeks to months): macro trend, value, and accumulation patterns.
"""
import pandas as pd
from .indicators import add_indicators


def score(df: pd.DataFrame) -> dict:
    df = add_indicators(df)
    last = df.iloc[-1]
    signals = []
    reasons = []

    # Strong long-term uptrend
    if last["close"] > last["ema_50"]:
        signals.append(25)
        reasons.append("Price above long-term EMA50 — secular uptrend")

    # RSI not overbought on weekly
    if 40 <= last["rsi"] <= 65:
        signals.append(20)
        reasons.append(f"RSI healthy, not overbought ({last['rsi']:.0f})")

    # Consistent volume accumulation (average volume_ratio > 1 over last 8 bars)
    recent_vol_ratio = df["volume_ratio"].iloc[-8:].mean()
    if recent_vol_ratio >= 1.15:
        signals.append(25)
        reasons.append(f"8-period volume accumulation ({recent_vol_ratio:.2f}x avg)")

    # MACD long-term bullish
    if last["macd"] > last["macd_signal"]:
        signals.append(15)
        reasons.append("MACD above signal on weekly — bullish bias")

    # Low Bollinger Band width (consolidation before potential breakout)
    bb_width_pct = df["bb_width"].rank(pct=True).iloc[-1]
    if bb_width_pct < 0.25:
        signals.append(15)
        reasons.append("Tight BB on weekly — coiling for breakout")

    return {
        "score": min(sum(signals), 100),
        "reasons": reasons,
        "last_close": last["close"],
        "volume_ratio": last["volume_ratio"],
        "rsi": last["rsi"],
    }
