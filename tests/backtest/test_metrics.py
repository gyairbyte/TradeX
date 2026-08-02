"""Tests for backtest performance metrics."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from tests.backtest.conftest import make_bars
from tradex.backtest.engine import run_backtest
from tradex.backtest.models import BacktestConfig


def _perfect_score_fn():
    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 100, "reasons": ["test"], "last_close": float(df["close"].iloc[-1])}

    return _fn


def _score_at(indices: set[int]):
    def _fn(df: pd.DataFrame) -> dict[str, object]:
        idx = len(df) - 1
        score = 100 if idx in indices else 0
        return {"score": score, "reasons": ["test"], "last_close": float(df["close"].iloc[-1])}

    return _fn


def test_no_trade_metrics():
    bars = make_bars(80)

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 0, "reasons": [], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=1, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")
    assert result.metrics.total_trades == 0
    assert result.metrics.win_rate_pct is None
    assert result.metrics.expectancy_pct is None
    assert result.metrics.profit_factor is None
    assert result.metrics.sharpe_ratio is None
    assert result.metrics.total_return_pct == pytest.approx(0.0, abs=1e-12)
    assert result.metrics.ending_capital == result.metrics.initial_capital


def test_flat_equity():
    bars = make_bars(80)

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 0, "reasons": [], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=1, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")
    assert (result.equity_curve["equity"] == config.initial_capital).all()


def test_known_total_return():
    n = 60
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    opens = np.full(n, 100.0)
    highs = np.full(n, 101.0)
    lows = np.full(n, 99.0)
    closes = np.full(n, 100.0)
    highs[50] = 120.0
    closes[50] = 105.0
    bars = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, take_profit_pct=0.10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    assert result.metrics.total_return_pct == pytest.approx(10.0, abs=1e-9)


def test_known_win_rate():
    n = 75
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    opens = np.full(n, 100.0)
    highs = np.full(n, 101.0)
    lows = np.full(n, 99.0)
    closes = np.full(n, 100.0)
    # Trade 1 at entry 50: target hit (win).
    highs[50] = 120.0
    closes[50] = 105.0
    # Trade 2 at entry 54: stop hit (loss).
    lows[54] = 80.0
    closes[54] = 85.0
    # Trade 3 at entry 58: time exit (breakeven-ish).
    closes[58] = 100.0
    closes[59] = 100.0
    closes[60] = 100.0
    bars = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05, take_profit_pct=0.10)
    result = run_backtest("TEST", bars, _score_at({49, 53, 57}), config=config, strategy_name="test", data_source="test")
    assert result.metrics.total_trades >= 2
    assert result.metrics.winning_trades >= 1
    assert result.metrics.losing_trades >= 1
    assert result.metrics.win_rate_pct == pytest.approx(
        (result.metrics.winning_trades / result.metrics.total_trades) * 100
    )


def test_profit_factor_no_losses():
    n = 60
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    opens = np.full(n, 100.0)
    highs = np.full(n, 101.0)
    lows = np.full(n, 99.0)
    closes = np.full(n, 100.0)
    highs[50] = 120.0
    closes[50] = 105.0
    bars = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, take_profit_pct=0.10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    assert result.metrics.total_trades > 0
    assert result.metrics.losing_trades == 0
    assert result.metrics.profit_factor is None


def test_profit_factor_no_wins():
    n = 60
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    opens = np.full(n, 100.0)
    highs = np.full(n, 101.0)
    lows = np.full(n, 99.0)
    closes = np.full(n, 100.0)
    lows[50] = 80.0
    closes[50] = 85.0
    bars = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    assert result.metrics.total_trades > 0
    assert result.metrics.winning_trades == 0
    assert result.metrics.profit_factor == 0.0


def test_sharpe_zero_variance():
    bars = make_bars(80)

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 0, "reasons": [], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=1, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")
    assert result.metrics.sharpe_ratio is None


def test_sharpe_insufficient_history():
    n = 50
    close = np.full(n, 100.0)
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": close.copy(),
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 0, "reasons": [], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=1, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")
    assert result.metrics.sharpe_ratio is None


def _make_sharpe_bars(n: int, changes: list[float]) -> pd.DataFrame:
    """Return bars with the open set to the previous close and a controlled close jump.

    changes[i] is the fractional close change at warmup+i relative to the previous
    close. The first close is always 100.0, so each entry open equals the prior
    close and the realized return equals the requested close change.
    """
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    close = np.full(n, 100.0)
    for i, change in enumerate(changes, start=50):
        close[i] = close[i - 1] * (1 + change)
    open_ = np.empty_like(close)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + 1.0,
            "low": np.minimum(open_, close) - 1.0,
            "close": close,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )


def test_sharpe_one_change_two_rows_is_none():
    # warmup=50, first_idx=49, equity rows at i=49 (initial) and i=50 (after trade).
    # Only one actual equity change exists, so Sharpe is undefined.
    bars = _make_sharpe_bars(51, [0.10])
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=1)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    assert len(result.equity_curve) == 2
    assert result.metrics.sharpe_ratio is None


def test_sharpe_two_known_changes_exact():
    # Equity: 100k -> 110k -> 110k. Returns: 0.1, 0.0.
    bars = _make_sharpe_bars(52, [0.10, 0.0])
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=1)
    result = run_backtest("TEST", bars, _score_at({49, 50}), config=config, strategy_name="test", data_source="test")
    assert len(result.equity_curve) == 3
    returns = result.equity_curve["daily_return"].dropna().to_numpy(dtype=float)
    np.testing.assert_allclose(returns, [0.10, 0.0])
    mean = 0.05
    std = math.sqrt(0.005)
    expected = math.sqrt(252) * mean / std
    assert result.metrics.sharpe_ratio == pytest.approx(expected)


def test_later_flat_bars_contribute_zero_returns():
    # Equity: 100k -> 110k -> 110k -> 110k. Returns: 0.1, 0.0, 0.0.
    bars = _make_sharpe_bars(53, [0.10, 0.0, 0.0])
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=1)
    result = run_backtest("TEST", bars, _score_at({49, 50, 51}), config=config, strategy_name="test", data_source="test")
    assert len(result.equity_curve) == 4
    returns = result.equity_curve["daily_return"].dropna().to_numpy(dtype=float)
    assert len(returns) == 3
    np.testing.assert_allclose(returns, [0.10, 0.0, 0.0])
    assert result.metrics.sharpe_ratio is not None
    assert math.isfinite(result.metrics.sharpe_ratio)


def test_first_undefined_daily_return_serializes_as_null():
    bars = _make_sharpe_bars(51, [0.10])
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=1)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    data = json.loads(result.to_json())
    assert data["equity_curve"][0]["daily_return"] is None
    # No NaN or Infinity may appear in the JSON output.
    for curve_row in data["equity_curve"]:
        for v in curve_row.values():
            assert v is None or isinstance(v, (str, int, float, bool))
            if isinstance(v, float):
                assert math.isfinite(v)


def test_known_drawdown():
    n = 60
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    opens = np.full(n, 100.0)
    highs = np.full(n, 101.0)
    lows = np.full(n, 99.0)
    closes = np.full(n, 100.0)
    lows[50] = 94.0
    closes[50] = 95.0
    closes[51:] = 95.0
    lows[51:] = 94.0
    bars = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    assert result.metrics.max_drawdown_pct < 0


def test_exposure_calculation():
    bars = make_bars(80)
    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _perfect_score_fn(), config=config, strategy_name="test", data_source="test")
    expected = (result.equity_curve["position_open"].sum() / len(result.equity_curve)) * 100
    assert result.metrics.exposure_pct == pytest.approx(expected)


def test_equity_curve_has_position_ticker():
    bars = make_bars(80)
    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _perfect_score_fn(), config=config, strategy_name="test", data_source="test")
    assert "position_ticker" in result.equity_curve.columns
    # When a position is active, the ticker is recorded; otherwise it is None/NaN.
    open_rows = result.equity_curve[result.equity_curve["position_open"]]
    assert (open_rows["position_ticker"] == "TEST").all()


def test_one_bar_trade_counts_entry_bar_exposed():
    # max_holding_bars=1 forces a time-exit on the entry bar.
    n = 60
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    close = np.full(n, 100.0)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=1)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    assert result.trade_ledger[0].bars_held == 1
    entry_time = result.trade_ledger[0].entry_time
    exit_time = result.trade_ledger[0].exit_time
    assert entry_time == exit_time
    row = result.equity_curve.loc[entry_time]
    assert bool(row["position_open"]) is True
    assert row["position_ticker"] == "TEST"


def test_multi_bar_time_exit_counts_entry_and_exit_bars_exposed():
    n = 70
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    close = np.full(n, 100.0)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=5)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    assert trade.bars_held == 5
    held_bars = result.equity_curve.loc[trade.entry_time:trade.exit_time]
    assert held_bars["position_open"].all()
    assert (held_bars["position_ticker"] == "TEST").all()
    # The bar immediately before entry has no position.
    prev_bar = result.equity_curve.iloc[result.equity_curve.index.get_loc(trade.entry_time) - 1]
    assert not prev_bar["position_open"]


def test_equity_reconciles_with_trade_returns():
    bars = make_bars(80)
    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3, commission_bps=10, slippage_bps=5)
    result = run_backtest("TEST", bars, _perfect_score_fn(), config=config, strategy_name="test", data_source="test")
    final_equity = result.equity_curve["equity"].iloc[-1]
    assert final_equity == pytest.approx(result.metrics.ending_capital)


def test_buy_and_hold_known_return():
    n = 50
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    opens = np.full(n, 100.0)
    closes = np.full(n, 100.0)
    closes[-1] = 110.0
    highs = np.maximum(opens, closes) + 1.0
    lows = np.minimum(opens, closes) - 1.0
    bars = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 0, "reasons": [], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=1, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")
    assert result.metrics.buy_and_hold_return_pct == pytest.approx(10.0, abs=1e-9)
    assert result.metrics.excess_return_pct == pytest.approx(-10.0, abs=1e-9)
