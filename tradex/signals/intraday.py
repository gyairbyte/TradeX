"""
Intraday opportunity signals: unusual volume + price momentum building toward a big swing.
Looks for multi-day volume/volatility accumulation that precedes intraday breakouts.
"""
import pandas as pd
from .indicators import add_indicators


def score(df: pd.DataFrame) -> dict:
    """
    Returns a signal dict for intraday swing setups.
    Scores 0-100; higher = stronger opportunity.
    """
    df = add_indicators(df)
    last = df.iloc[-1]
    signals = []
    reasons = []

    # Volume surge: current bar volume > 2x 20-period average
    if last["volume_ratio"] >= 2.0:
        signals.append(30)
        reasons.append(f"Volume surge {last['volume_ratio']:.1f}x avg")
    elif last["volume_ratio"] >= 1.5:
        signals.append(15)
        reasons.append(f"Elevated volume {last['volume_ratio']:.1f}x avg")

    # Bollinger Band squeeze then expansion (coiling before breakout)
    bb_width_pct = df["bb_width"].rank(pct=True).iloc[-1]
    if bb_width_pct > 0.8:
        signals.append(20)
        reasons.append("BB expanding after squeeze — volatility breakout")

    # RSI momentum without being overbought
    if 55 <= last["rsi"] <= 75:
        signals.append(20)
        reasons.append(f"RSI bullish momentum ({last['rsi']:.0f})")
    elif 25 <= last["rsi"] <= 45:
        signals.append(15)
        reasons.append(f"RSI oversold bounce setup ({last['rsi']:.0f})")

    # MACD bullish crossover
    if last["macd_diff"] > 0 and df["macd_diff"].iloc[-2] <= 0:
        signals.append(30)
        reasons.append("MACD bullish crossover")

    return {
        "score": min(sum(signals), 100),
        "reasons": reasons,
        "last_close": last["close"],
        "volume_ratio": last["volume_ratio"],
        "rsi": last["rsi"],
    }
