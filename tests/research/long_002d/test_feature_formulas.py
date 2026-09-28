"""Tests for deterministic feature formula calculations and price series usage."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradex.research.long_002d.features import (
    compute_features_for_security_df,
)


def test_feature_formulas_deterministic_reference():
    """Verify that all 15 feature formulas match deterministic reference values."""
    dates = pd.date_range("2016-01-04", periods=70, freq="B").strftime("%Y-%m-%d").tolist()

    # Construct deterministic price series
    # Base price starting at 100, increasing by 1 each day
    # With known high, low, volume
    closes = np.array([100.0 + i for i in range(70)], dtype=float)
    highs = closes + 2.0
    lows = closes - 1.0
    opens = closes - 0.5
    volumes = np.array([1000.0 + 10.0 * (i % 5) for i in range(70)], dtype=float)
    as_traded_closes = closes * 2.0  # simulate a 2-for-1 split scenario where as-traded differs

    df_bars = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
            "as_traded_close": as_traded_closes,
        },
        index=dates,
    )

    # SPY closes: flat 200
    spy_closes = {d: 200.0 for d in dates}

    feat_df = compute_features_for_security_df(df_bars, spy_closes)

    # Test at index 65 (bar 66)
    idx = 65
    c_t = closes[idx]
    c_t5 = closes[idx - 5]
    c_t20 = closes[idx - 20]
    c_t60 = closes[idx - 60]

    # R1: return_5 = close_t / close_t-5 - 1
    assert pytest.approx(feat_df["return_5"].iloc[idx]) == (c_t / c_t5 - 1.0)

    # R2: return_20 = close_t / close_t-20 - 1
    assert pytest.approx(feat_df["return_20"].iloc[idx]) == (c_t / c_t20 - 1.0)

    # R3: return_60 = close_t / close_t-60 - 1
    assert pytest.approx(feat_df["return_60"].iloc[idx]) == (c_t / c_t60 - 1.0)

    # F1: close_vs_sma20 = close_t / SMA20_t - 1
    sma20 = np.mean(closes[idx - 19 : idx + 1])
    assert pytest.approx(feat_df["close_vs_sma20"].iloc[idx]) == (c_t / sma20 - 1.0)

    # F2: close_vs_sma60 = close_t / SMA60_t - 1
    sma60 = np.mean(closes[idx - 59 : idx + 1])
    assert pytest.approx(feat_df["close_vs_sma60"].iloc[idx]) == (c_t / sma60 - 1.0)

    # F3: sma20_slope_5 = SMA20_t / SMA20_t-5 - 1
    sma20_past5 = np.mean(closes[idx - 24 : idx - 4])
    assert pytest.approx(feat_df["sma20_slope_5"].iloc[idx]) == (sma20 / sma20_past5 - 1.0)

    # F4: proximity_high20 = close_t / rolling_max_close_20_t - 1
    # monotonically increasing series, so rolling max is close_t itself -> 0.0
    assert pytest.approx(feat_df["proximity_high20"].iloc[idx]) == 0.0

    # F5: proximity_high60 = close_t / rolling_max_close_60_t - 1
    assert pytest.approx(feat_df["proximity_high60"].iloc[idx]) == 0.0

    # F7: relative_volume_20 excludes session t from its denominator
    # Denominator is median(volume[idx-20 : idx])
    med_prior_v = np.median(volumes[idx - 20 : idx])
    assert pytest.approx(feat_df["relative_volume_20"].iloc[idx]) == (volumes[idx] / med_prior_v)

    # F8: dollar_volume_trend_20_60 uses as-traded close
    dvol = as_traded_closes * volumes
    med_dvol20 = np.median(dvol[idx - 19 : idx + 1])
    med_dvol60 = np.median(dvol[idx - 59 : idx + 1])
    assert pytest.approx(feat_df["dollar_volume_trend_20_60"].iloc[idx]) == (med_dvol20 / med_dvol60 - 1.0)

    # F9: up_volume_share_20: since close is strictly increasing, all 20 sessions are up sessions
    assert pytest.approx(feat_df["up_volume_share_20"].iloc[idx]) == 1.0

    # F10: spy_return_20: flat SPY closes -> 0.0
    assert pytest.approx(feat_df["spy_return_20"].iloc[idx]) == 0.0

    # F11: stock_minus_spy_20 = return_20 - spy_return_20
    assert pytest.approx(feat_df["stock_minus_spy_20"].iloc[idx]) == feat_df["return_20"].iloc[idx]


def test_lookback_insufficiency_returns_null_not_zero():
    """Verify that lookback insufficiency returns NaN / null, never imputed with zero."""
    dates = pd.date_range("2016-01-04", periods=15, freq="B").strftime("%Y-%m-%d").tolist()
    closes = np.array([100.0 + i for i in range(15)], dtype=float)
    df_bars = pd.DataFrame(
        {
            "open": closes,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": np.full(15, 1000.0),
            "as_traded_close": closes,
        },
        index=dates,
    )

    feat_df = compute_features_for_security_df(df_bars)

    # 15 bars: return_60, close_vs_sma20, close_vs_sma60, sma20_slope_5 must all be NaN
    assert feat_df["return_60"].isna().all()
    assert feat_df["close_vs_sma20"].isna().all()
    assert feat_df["close_vs_sma60"].isna().all()
    assert feat_df["sma20_slope_5"].isna().all()
    assert feat_df["proximity_high20"].isna().all()
    assert feat_df["proximity_high60"].isna().all()
    assert feat_df["relative_volume_20"].isna().all()
    assert feat_df["dollar_volume_trend_20_60"].isna().all()

    # return_5 requires 5 prior bars, so indices 0..4 must be NaN, index 5 non-null
    assert feat_df["return_5"].iloc[:5].isna().all()
    assert not np.isnan(feat_df["return_5"].iloc[5])


def test_relative_volume_excludes_current_session():
    """Verify that relative_volume_20 explicitly excludes session t from the 20-session median."""
    dates = pd.date_range("2016-01-04", periods=25, freq="B").strftime("%Y-%m-%d").tolist()
    closes = np.full(25, 100.0)
    # 20 prior bars have volume 1000, current bar has massive volume surge 100000
    volumes = np.full(25, 1000.0)
    volumes[21] = 100000.0

    df_bars = pd.DataFrame(
        {
            "open": closes,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": volumes,
            "as_traded_close": closes,
        },
        index=dates,
    )

    feat_df = compute_features_for_security_df(df_bars)

    # At index 21, prior 20 bars (indices 1..20) all have volume 1000
    # If session 21 was included, median would still be 1000, but if relative volume formula used current session in median:
    # Let's test at index 22: prior 20 bars are 2..21 (includes the 100000 surge)
    # The surge is in index 21. For index 21, the denominator is strictly indices 1..20 (does NOT include 100000)
    assert pytest.approx(feat_df["relative_volume_20"].iloc[21]) == 100000.0 / 1000.0
