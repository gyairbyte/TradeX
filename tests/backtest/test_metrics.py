"""Tests for backtest performance metrics."""
from __future__ import annotations

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
