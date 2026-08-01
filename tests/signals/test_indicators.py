"""Sanity tests for shared indicator computation."""
import numpy as np
import pandas as pd

from tradex.signals import indicators


def test_add_indicators_outputs_expected_columns():
    """add_indicators should return a DataFrame with the standard indicator columns."""
    n = 100
    df = pd.DataFrame({
        "open": np.linspace(100, 120, n) + np.random.normal(0, 0.5, n),
        "high": np.linspace(102, 122, n) + np.random.normal(0, 0.5, n),
        "low": np.linspace(98, 118, n) + np.random.normal(0, 0.5, n),
        "close": np.linspace(100, 121, n) + np.random.normal(0, 0.5, n),
        "volume": np.ones(n) * 1_000_000,
    })
    result = indicators.add_indicators(df)
    expected = {
        "rsi", "macd", "macd_signal", "macd_diff",
        "ema_20", "ema_50", "bb_upper", "bb_lower",
        "bb_width", "atr", "volume_sma20", "volume_ratio",
    }
    assert expected.issubset(set(result.columns))
