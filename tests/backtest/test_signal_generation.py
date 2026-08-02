"""Tests for point-in-time signal generation and entry timing."""
from __future__ import annotations

import pandas as pd
import pytest

from tests.backtest.conftest import make_bars
from tradex.backtest.engine import run_backtest
from tradex.backtest.models import BacktestConfig
from tradex.backtest.validation import BacktestDataError


def test_scorer_receives_only_historical_rows():
    n = 80
    bars = make_bars(n)
    state = {"max_ts": None}

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        state["max_ts"] = df.index[-1]
        return {"score": 100, "reasons": ["test"], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")
    signal_times = [s.signal_time for s in result.signal_ledger]
    assert state["max_ts"] in signal_times


def test_no_future_bar_visible():
    n = 80
    bars = make_bars(n)
    seen: list[pd.Timestamp] = []

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        seen.append(df.index[-1])
        return {"score": 100, "reasons": ["test"], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3)
    run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")
    for i, ts in enumerate(seen):
        assert ts == bars.index[config.warmup_bars - 1 + i]


def test_entry_is_next_bar_open():
    bars = make_bars(80)

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 100, "reasons": ["test"], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")
    executed = [s for s in result.signal_ledger if s.execution_status == "executed"]
    assert len(executed) > 0
    for sig in executed:
        signal_idx = bars.index.get_loc(sig.signal_time)
        assert sig.entry_time == bars.index[signal_idx + 1]
        trade = next(t for t in result.trade_ledger if t.signal_time == sig.signal_time)
        assert trade.raw_entry_price == bars.iloc[signal_idx + 1]["open"]


def test_same_close_entry_never_occurs():
    bars = make_bars(80)

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 100, "reasons": ["test"], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")
    for trade in result.trade_ledger:
        assert trade.signal_time != trade.entry_time


def test_final_row_signal_no_next_bar():
    bars = make_bars(80)

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 100, "reasons": ["test"], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")
    last_signal = result.signal_ledger[-1]
    assert last_signal.signal_time == bars.index[-1]
    assert last_signal.execution_status == "skipped"
    assert last_signal.skip_reason == "no_next_bar"


def test_score_below_threshold_produces_no_trade(empty_score_fn):
    bars = make_bars(80)
    config = BacktestConfig(min_score=1, warmup_bars=50, max_holding_bars=3)
    result = run_backtest("TEST", bars, empty_score_fn, config=config, strategy_name="test", data_source="test")
    assert all(s.skip_reason == "below_threshold" for s in result.signal_ledger)
    assert len(result.trade_ledger) == 0
    assert result.metrics.total_trades == 0


def test_malformed_score_output_rejected():
    bars = make_bars(80)

    def _fn_bad_score(df: pd.DataFrame) -> dict[str, object]:
        return {"score": "high", "reasons": ["test"], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3)
    with pytest.raises(BacktestDataError, match="numeric"):
        run_backtest("TEST", bars, _fn_bad_score, config=config, strategy_name="test", data_source="test")


def test_score_out_of_range_rejected():
    bars = make_bars(80)

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 150, "reasons": ["test"], "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3)
    with pytest.raises(BacktestDataError, match="between 0 and 100"):
        run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")


def test_malformed_reasons_rejected():
    bars = make_bars(80)

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 100, "reasons": 123, "last_close": float(df["close"].iloc[-1])}

    config = BacktestConfig(min_score=0, warmup_bars=50, max_holding_bars=3)
    with pytest.raises(BacktestDataError, match="reasons"):
        run_backtest("TEST", bars, _fn, config=config, strategy_name="test", data_source="test")
