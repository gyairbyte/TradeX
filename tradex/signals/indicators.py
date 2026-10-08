"""
Computes technical indicators used across all timeframes.
"""
import pandas as pd
import ta


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Momentum
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_diff"] = macd.macd_diff()

    # Trend
    df["ema_20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["ema_50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    df["ema_200"] = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()
    df["ema20_slope_5"] = df["ema_20"] - df["ema_20"].shift(5)
    df["ema_20_slope_5"] = df["ema20_slope_5"]

    # Volatility
    bb = ta.volatility.BollingerBands(df["close"])
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = bb.bollinger_wband()
    df["atr"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"]).average_true_range()
    df["atr_pct"] = df["atr"] / df["close"]

    # Volume & Liquidity
    df["volume_sma20"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma20"]
    df["volume_ratio_20"] = df["volume_ratio"]
    df["median_dollar_volume_20"] = (df["close"] * df["volume"]).rolling(20).median()

    # Returns / Momentum
    df["return_5"] = df["close"] / df["close"].shift(5) - 1.0
    df["return_20"] = df["close"] / df["close"].shift(20) - 1.0
    df["return_60"] = df["close"] / df["close"].shift(60) - 1.0

    # Price Structure (point-in-time safe: strictly excludes current bar)
    df["prior_5d_high"] = df["high"].shift(1).rolling(5).max()
    df["prior_20d_high"] = df["high"].shift(1).rolling(20).max()
    df["distance_to_ema20_pct"] = (df["close"] - df["ema_20"]) / df["ema_20"]
    df["distance_to_20d_high_pct"] = (df["prior_20d_high"] - df["close"]) / df["prior_20d_high"]

    return df
