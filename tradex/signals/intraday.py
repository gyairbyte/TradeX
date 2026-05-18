"""
Intraday opportunity signals: unusual volume + price momentum building toward a big swing.
Looks for multi-day volume/volatility accumulation that precedes intraday breakouts.
"""
import pandas as pd
from .indicators import add_indicators
from .weights import IntradayWeights, load as load_weights


def score(df: pd.DataFrame, weights: IntradayWeights | None = None) -> dict:
    """
    Returns a signal dict for intraday swing setups.
    Scores 0-100; higher = stronger opportunity.
    """
    if weights is None:
        weights = load_weights().intraday

    df = add_indicators(df)
    last = df.iloc[-1]
    signals = []
    reasons = []

    if last["volume_ratio"] >= 2.0:
        signals.append(weights.volume_surge)
        reasons.append(f"Volume surge {last['volume_ratio']:.1f}x avg")
    elif last["volume_ratio"] >= 1.5:
        signals.append(weights.volume_surge // 2)
        reasons.append(f"Elevated volume {last['volume_ratio']:.1f}x avg")

    bb_width_pct = df["bb_width"].rank(pct=True).iloc[-1]
    if bb_width_pct > 0.8:
        signals.append(weights.bb_expansion)
        reasons.append("BB expanding after squeeze — volatility breakout")

    if 55 <= last["rsi"] <= 75:
        signals.append(weights.rsi_momentum)
        reasons.append(f"RSI bullish momentum ({last['rsi']:.0f})")
    elif 25 <= last["rsi"] <= 45:
        signals.append(round(weights.rsi_momentum * 0.75))
        reasons.append(f"RSI oversold bounce setup ({last['rsi']:.0f})")

    if last["macd_diff"] > 0 and df["macd_diff"].iloc[-2] <= 0:
        signals.append(weights.macd_crossover)
        reasons.append("MACD bullish crossover")

    return {
        "score": min(sum(signals), 100),
        "reasons": reasons,
        "last_close": last["close"],
        "volume_ratio": last["volume_ratio"],
        "rsi": last["rsi"],
    }
