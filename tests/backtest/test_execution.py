"""Tests for the execution model: entries, exits, costs, and overlap rules."""
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


def _base_bars(n: int = 60) -> pd.DataFrame:
    close = np.full(n, 100.0)
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": close.copy(),
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )


def _entry_bars(n: int = 60, entry_idx: int = 50, **kwargs) -> pd.DataFrame:
    bars = _base_bars(n)
    for k, v in kwargs.items():
        bars.iloc[entry_idx, bars.columns.get_loc(k)] = v
    return bars


def test_target_only_hit():
    bars = _entry_bars(60, 50, high=120.0)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05, take_profit_pct=0.10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    assert len(result.trade_ledger) == 1
    trade = result.trade_ledger[0]
    assert trade.exit_reason == "target"
    assert trade.raw_exit_price == pytest.approx(110.0)
    assert trade.net_return_pct == pytest.approx(10.0, abs=1e-9)


def test_stop_only_hit():
    bars = _entry_bars(60, 50, low=80.0)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05, take_profit_pct=0.10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    assert len(result.trade_ledger) == 1
    trade = result.trade_ledger[0]
    assert trade.exit_reason == "stop"
    assert trade.raw_exit_price == pytest.approx(95.0)


def test_gap_through_stop():
    # Entry at bar 50 with fill 100; the following bar gaps down below the stop.
    bars = _base_bars(60)
    bars.iloc[50, bars.columns.get_loc("open")] = 100.0
    bars.iloc[51, bars.columns.get_loc("open")] = 90.0
    bars.iloc[51, bars.columns.get_loc("high")] = 90.0
    bars.iloc[51, bars.columns.get_loc("low")] = 90.0
    bars.iloc[51, bars.columns.get_loc("close")] = 90.0
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05, take_profit_pct=0.10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    assert trade.exit_reason == "gap_stop"
    assert trade.raw_exit_price == pytest.approx(90.0)
    # Stop level is anchored to the entry fill, not the signal close.
    assert trade.stop_price == pytest.approx(100.0 * (1 - 0.05))


def test_gap_through_target():
    # Entry at bar 50 with fill 100; the following bar gaps up above the target.
    bars = _base_bars(60)
    bars.iloc[50, bars.columns.get_loc("open")] = 100.0
    bars.iloc[51, bars.columns.get_loc("open")] = 120.0
    bars.iloc[51, bars.columns.get_loc("high")] = 120.0
    bars.iloc[51, bars.columns.get_loc("low")] = 120.0
    bars.iloc[51, bars.columns.get_loc("close")] = 120.0
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05, take_profit_pct=0.10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    assert trade.exit_reason == "gap_target"
    assert trade.raw_exit_price == pytest.approx(120.0)
    assert trade.target_price == pytest.approx(100.0 * (1 + 0.10))


def test_both_hit_stop_first():
    bars = _entry_bars(60, 50, high=120.0, low=80.0)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05, take_profit_pct=0.10, intrabar_policy="stop_first")
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    assert trade.exit_reason == "stop"
    assert trade.raw_exit_price == pytest.approx(95.0)


def test_both_hit_target_first():
    bars = _entry_bars(60, 50, high=120.0, low=80.0)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05, take_profit_pct=0.10, intrabar_policy="target_first")
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    assert trade.exit_reason == "target"
    assert trade.raw_exit_price == pytest.approx(110.0)


def test_time_exit():
    bars = _base_bars(60)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05, take_profit_pct=0.10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    assert result.trade_ledger[0].exit_reason == "time_exit"
    assert result.trade_ledger[0].bars_held == 3


def test_entry_bar_exit():
    bars = _entry_bars(60, 50, low=90.0)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05, take_profit_pct=0.10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    assert trade.bars_held == 1
    assert trade.exit_reason == "stop"


def test_holding_bar_count():
    bars = _base_bars(60)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=5, stop_loss_pct=0.05, take_profit_pct=0.10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    assert trade.bars_held == 5


def test_overlapping_signal_skipped():
    bars = make_bars(80)
    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=20)
    result = run_backtest("TEST", bars, _perfect_score_fn(), config=config, strategy_name="test", data_source="test")
    overlaps = [s for s in result.signal_ledger if s.skip_reason == "overlap"]
    assert len(overlaps) > 0
    assert all(s.entry_time is None for s in overlaps)


def test_entry_only_after_prior_exit():
    bars = make_bars(80)
    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _perfect_score_fn(), config=config, strategy_name="test", data_source="test")
    if len(result.trade_ledger) >= 2:
        for t1, t2 in zip(result.trade_ledger, result.trade_ledger[1:]):
            # A new signal may fire on the same bar a prior trade exits, but entry
            # must always occur on a later bar.
            assert t2.entry_time > t1.exit_time


def test_fractional_quantity():
    bars = _base_bars(60)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, commission_bps=10, slippage_bps=5)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    assert trade.quantity > 0
    assert abs(trade.quantity - round(trade.quantity)) > 1e-9


def test_entry_slippage():
    bars = _base_bars(60)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, slippage_bps=10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    assert trade.entry_fill_price == pytest.approx(100 * (1 + 10 / 10_000))


def test_exit_slippage():
    bars = _entry_bars(70, 50, high=120.0)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, take_profit_pct=0.10, slippage_bps=10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    # Target is anchored to the slippage-inflated entry fill; exit fill applies
    # adverse slippage on top of the raw (target) exit price.
    assert trade.target_price == pytest.approx(trade.entry_fill_price * (1 + 0.10))
    assert trade.exit_fill_price == pytest.approx(trade.target_price * (1 - 10 / 10_000))


def test_entry_commission():
    bars = _base_bars(60)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, commission_bps=10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    cash_per_share = trade.entry_fill_price * (1 + 10 / 10_000)
    assert trade.starting_cash / trade.quantity == pytest.approx(cash_per_share)


def test_net_return_reconciles_to_account_cash():
    bars = _base_bars(60)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, commission_bps=10, slippage_bps=5)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    expected_net = trade.ending_cash / trade.starting_cash - 1
    assert trade.net_return_pct == pytest.approx(expected_net * 100, rel=1e-12)


def test_gross_return_excludes_costs():
    bars = _entry_bars(70, 50, high=120.0)
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, take_profit_pct=0.10, commission_bps=10, slippage_bps=5)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    expected_gross = (trade.raw_exit_price / trade.raw_entry_price - 1) * 100
    assert trade.gross_return_pct == pytest.approx(expected_gross, abs=1e-9)
    assert trade.net_return_pct < trade.gross_return_pct


def test_stop_and_target_anchored_to_entry_fill_with_slippage():
    # Signal close is 100 but the entry opens at 90 with 10 bps slippage.
    # Stop/target must be anchored to the entry fill, not the signal close.
    bars = _base_bars(60)
    for col in ["open", "high", "low", "close"]:
        bars.iloc[50:53, bars.columns.get_loc(col)] = 90.0
    config = BacktestConfig(min_score=40, warmup_bars=50, max_holding_bars=3, stop_loss_pct=0.05, take_profit_pct=0.10, slippage_bps=10)
    result = run_backtest("TEST", bars, _score_at({49}), config=config, strategy_name="test", data_source="test")
    trade = result.trade_ledger[0]
    entry_fill = 90.0 * (1 + 10 / 10_000)
    assert trade.entry_fill_price == pytest.approx(entry_fill)
    assert trade.stop_price == pytest.approx(entry_fill * (1 - 0.05))
    assert trade.target_price == pytest.approx(entry_fill * (1 + 0.10))
    # The entry open (90) is above the stop, so this is not a gap exit even though
    # the signal-close-based stop would have been 95.
    assert trade.exit_reason != "gap_stop"
    assert trade.exit_reason == "time_exit"
