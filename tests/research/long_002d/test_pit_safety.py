"""Tests for point-in-time safety, no future bar leakage, and split boundary enforcement."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradex.research.long_002d.features import compute_features_for_security_df
from tradex.research.long_002d.spec import enforce_split_guard


def test_no_future_bar_leakage():
    """Verify that feature values at session t are identical whether future bars exist or not."""
    dates_full = pd.date_range("2016-01-04", periods=100, freq="B").strftime("%Y-%m-%d").tolist()
    closes = np.array([50.0 + 0.5 * i + np.sin(i) for i in range(100)], dtype=float)
    highs = closes + 1.5
    lows = closes - 1.2
    opens = closes - 0.2
    volumes = np.array([5000.0 + 50.0 * (i % 7) for i in range(100)], dtype=float)

    df_full = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
            "as_traded_close": closes,
        },
        index=dates_full,
    )

    # Compute on full 100 bars
    feat_full = compute_features_for_security_df(df_full)

    # Compute on truncated history up to bar 60
    t_target = 60
    df_truncated = df_full.iloc[: t_target + 1].copy()
    feat_truncated = compute_features_for_security_df(df_truncated)

    # Compare row 60 across all features
    row_full = feat_full.iloc[t_target].to_dict()
    row_trunc = feat_truncated.iloc[t_target].to_dict()

    for col in feat_full.columns:
        val_full = row_full[col]
        val_trunc = row_trunc[col]
        if np.isnan(val_full):
            assert np.isnan(val_trunc), f"Mismatch for {col}: full is NaN, trunc is {val_trunc}"
        else:
            assert pytest.approx(val_full, rel=1e-7) == val_trunc, f"Leakage detected in {col}!"


def test_current_completed_bar_usable_at_2030():
    """Verify that at 20:30 ET, the current completed session's close is reflected in return_5."""
    dates = ["2016-01-04", "2016-01-05", "2016-01-06", "2016-01-07", "2016-01-08", "2016-01-11"]
    closes = [10.0, 11.0, 12.0, 13.0, 14.0, 20.0]
    df = pd.DataFrame(
        {
            "open": closes,
            "high": [c + 1.0 for c in closes],
            "low": [c - 1.0 for c in closes],
            "close": closes,
            "volume": [1000.0] * 6,
            "as_traded_close": closes,
        },
        index=dates,
    )

    feat = compute_features_for_security_df(df)
    # At index 5 (date 2016-01-11), close is 20.0, close 5 sessions ago (index 0) is 10.0
    # return_5 = 20.0 / 10.0 - 1 = 1.0 (100% gain)
    assert pytest.approx(feat["return_5"].iloc[5]) == 1.0


def test_split_guard_enforcement():
    """Verify that enforce_split_guard rejects dates past 2020-12-31."""
    enforce_split_guard("2020-12-31")  # Valid development date
    with pytest.raises(ValueError, match="SPLIT QUARANTINE BREACH"):
        enforce_split_guard("2021-01-04")
