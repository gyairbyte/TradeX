"""Tests for BacktestConfig and OHLCV validation."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from tradex.backtest.models import BacktestConfig, BacktestError
from tradex.backtest.validation import BacktestDataError, canonicalize_bars


def test_config_defaults():
    cfg = BacktestConfig()
    assert cfg.min_score == 40
    assert cfg.warmup_bars == 60
    assert cfg.max_holding_bars == 3
    assert cfg.stop_loss_pct == 0.05
    assert cfg.take_profit_pct == 0.10


def test_config_min_score_out_of_range():
    with pytest.raises(BacktestError):
        BacktestConfig(min_score=-1)
    with pytest.raises(BacktestError):
        BacktestConfig(min_score=101)


def test_config_warmup_too_low():
    with pytest.raises(BacktestError):
        BacktestConfig(warmup_bars=10)


def test_config_invalid_holding_period():
    with pytest.raises(BacktestError):
        BacktestConfig(max_holding_bars=0)


def test_config_invalid_stop_and_target():
    with pytest.raises(BacktestError):
        BacktestConfig(stop_loss_pct=0.0)
    with pytest.raises(BacktestError):
        BacktestConfig(stop_loss_pct=1.0)
    with pytest.raises(BacktestError):
        BacktestConfig(take_profit_pct=0.0)
    with pytest.raises(BacktestError):
        BacktestConfig(take_profit_pct=1.0)


def test_config_negative_costs():
    with pytest.raises(BacktestError):
        BacktestConfig(commission_bps=-1)
    with pytest.raises(BacktestError):
        BacktestConfig(slippage_bps=-1)


def test_config_invalid_capital():
    with pytest.raises(BacktestError):
        BacktestConfig(initial_capital=0)


def test_config_invalid_intrabar_policy():
    with pytest.raises(BacktestError):
        BacktestConfig(intrabar_policy="close_first")


def test_config_rejects_booleans_as_integers():
    with pytest.raises(BacktestError):
        BacktestConfig(min_score=True)  # type: ignore[arg-type]
    with pytest.raises(BacktestError):
        BacktestConfig(warmup_bars=True)  # type: ignore[arg-type]


def test_config_rejects_booleans_as_numbers():
    with pytest.raises(BacktestError):
        BacktestConfig(stop_loss_pct=True)  # type: ignore[arg-type]
    with pytest.raises(BacktestError):
        BacktestConfig(take_profit_pct=True)  # type: ignore[arg-type]


def test_canonicalize_valid_utc():
    df = _valid_bars()
    out = canonicalize_bars(df)
    assert out.index.tz is not None
    assert str(out.index.tz) == "UTC"
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert len(out) == 60


def test_canonicalize_non_utc_normalized():
    df = _valid_bars().tz_convert("America/New_York")
    out = canonicalize_bars(df)
    assert str(out.index.tz) == "UTC"


def test_canonicalize_naive_rejected():
    df = _valid_bars().tz_localize(None)
    with pytest.raises(BacktestDataError, match="naive"):
        canonicalize_bars(df)


def test_canonicalize_naive_with_timezone():
    df = _valid_bars().tz_localize(None)
    out = canonicalize_bars(df, timezone="America/New_York")
    assert str(out.index.tz) == "UTC"


def test_canonicalize_unsorted_rejected():
    df = _valid_bars().sort_values("close", ascending=False)
    with pytest.raises(BacktestDataError, match="not strictly increasing"):
        canonicalize_bars(df)


def test_canonicalize_duplicates_rejected():
    df = _valid_bars()
    df = pd.concat([df.iloc[:5], df.iloc[4:8]])
    with pytest.raises(BacktestDataError, match="duplicate"):
        canonicalize_bars(df)


def test_canonicalize_missing_columns():
    df = _valid_bars().drop(columns=["high"])
    with pytest.raises(BacktestDataError, match="Missing required"):
        canonicalize_bars(df)


def test_canonicalize_non_numeric_value():
    df = _valid_bars()
    df["close"] = df["close"].astype(object)
    df.iloc[5, df.columns.get_loc("close")] = "abc"
    with pytest.raises(BacktestDataError, match="NaN or non-numeric"):
        canonicalize_bars(df)


def test_canonicalize_nan_value():
    df = _valid_bars()
    df.iloc[5, df.columns.get_loc("close")] = np.nan
    with pytest.raises(BacktestDataError, match="NaN"):
        canonicalize_bars(df)


def test_canonicalize_infinite_value():
    df = _valid_bars()
    df.iloc[5, df.columns.get_loc("close")] = math.inf
    with pytest.raises(BacktestDataError, match="Non-finite"):
        canonicalize_bars(df)


def test_canonicalize_nonpositive_price():
    df = _valid_bars()
    df.iloc[5, df.columns.get_loc("low")] = 0
    with pytest.raises(BacktestDataError, match="Nonpositive"):
        canonicalize_bars(df)


def test_canonicalize_negative_volume():
    df = _valid_bars()
    df.iloc[5, df.columns.get_loc("volume")] = -1
    with pytest.raises(BacktestDataError, match="Negative volume"):
        canonicalize_bars(df)


def test_canonicalize_high_below_low():
    df = _valid_bars()
    df.iloc[5, df.columns.get_loc("high")] = 50
    df.iloc[5, df.columns.get_loc("low")] = 60
    with pytest.raises(BacktestDataError, match="high < low"):
        canonicalize_bars(df)


def test_canonicalize_high_below_open():
    df = _valid_bars()
    df.iloc[5, df.columns.get_loc("high")] = 95
    df.iloc[5, df.columns.get_loc("low")] = 94
    with pytest.raises(BacktestDataError, match="high below open or close"):
        canonicalize_bars(df)


def test_canonicalize_low_above_close():
    df = _valid_bars()
    df.iloc[5, df.columns.get_loc("low")] = 150
    df.iloc[5, df.columns.get_loc("high")] = 160
    with pytest.raises(BacktestDataError, match="low above open or close"):
        canonicalize_bars(df)


def test_canonicalize_defensive_copy():
    df = _valid_bars()
    original_close = df["close"].iloc[0]
    out = canonicalize_bars(df)
    out.iloc[0, out.columns.get_loc("close")] = 999
    assert df["close"].iloc[0] == original_close


def _valid_bars(n: int = 60) -> pd.DataFrame:
    close = np.linspace(100, 130, n)
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )
