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
        "ema_20", "ema_50", "ema_200", "bb_upper", "bb_lower",
        "bb_width", "atr", "atr_pct", "volume_sma20", "volume_ratio",
        "volume_ratio_20", "median_dollar_volume_20",
        "return_5", "return_20", "return_60",
        "prior_5d_high", "prior_20d_high",
        "distance_to_ema20_pct", "distance_to_20d_high_pct",
        "ema20_slope_5",
    }
    assert expected.issubset(set(result.columns))


def test_prior_highs_exclude_current_bar():
    """prior_5d_high and prior_20d_high must strictly exclude the current session."""
    n = 30
    highs = [10.0] * n
    # Set the current bar's high to an extreme spike of 50.0
    highs[-1] = 50.0
    # Set bar t-1 to 20.0
    highs[-2] = 20.0
    # Set bar t-6 to 25.0 (outside 5d window [t-5..t-1], inside 20d window)
    highs[-7] = 25.0

    df = pd.DataFrame({
        "open": [10.0] * n,
        "high": highs,
        "low": [9.0] * n,
        "close": [10.0] * n,
        "volume": [1_000_000] * n,
    })

    result = indicators.add_indicators(df)
    last = result.iloc[-1]

    # Current bar high is 50.0, but prior 5d high must NOT see 50.0.
    # Prior 5 bars are t-1 (20.0), t-2 (10.0), t-3 (10.0), t-4 (10.0), t-5 (10.0).
    # So prior_5d_high must be 20.0.
    assert last["prior_5d_high"] == 20.0
    assert last["prior_5d_high"] != 50.0

    # Prior 20 bars include t-6 (25.0), but NOT t (50.0).
    assert last["prior_20d_high"] == 25.0
    assert last["prior_20d_high"] != 50.0


def test_returns_and_median_dollar_volume_formulas():
    """Verify return_5, return_20, return_60 and median_dollar_volume_20 calculations."""
    n = 70
    closes = np.arange(100.0, 100.0 + n)
    volumes = np.full(n, 100_000.0)

    df = pd.DataFrame({
        "open": closes,
        "high": closes + 1.0,
        "low": closes - 1.0,
        "close": closes,
        "volume": volumes,
    })

    result = indicators.add_indicators(df)
    last = result.iloc[-1]

    expected_ret5 = closes[-1] / closes[-6] - 1.0
    expected_ret20 = closes[-1] / closes[-21] - 1.0
    expected_ret60 = closes[-1] / closes[-61] - 1.0

    assert np.isclose(last["return_5"], expected_ret5)
    assert np.isclose(last["return_20"], expected_ret20)
    assert np.isclose(last["return_60"], expected_ret60)

    # Median dollar volume over last 20 bars
    recent_dv = (closes[-20:] * volumes[-20:])
    expected_median_dv = np.median(recent_dv)
    assert np.isclose(last["median_dollar_volume_20"], expected_median_dv)

    # ATR pct = atr / close
    assert np.isclose(last["atr_pct"], last["atr"] / last["close"])

    # EMA20 slope 5 = ema_20 - ema_20.shift(5)
    expected_slope = result["ema_20"].iloc[-1] - result["ema_20"].iloc[-6]
    assert np.isclose(last["ema20_slope_5"], expected_slope)
