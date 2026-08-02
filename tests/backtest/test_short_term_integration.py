"""Integration tests for the production short-term scorer in the backtest."""
from __future__ import annotations

import json
from unittest import mock

import pandas as pd

import tradex.backtest.engine
from tradex.backtest.engine import run_short_term_backtest
from tradex.backtest.models import BacktestConfig
from tradex.signals import weights as weights_module
from tradex.signals.weights import ShortWeights


def test_short_term_fixture_generates_qualifying_score(short_term_qualifying_bars):
    config = BacktestConfig(min_score=40, warmup_bars=60, max_holding_bars=3)
    result = run_short_term_backtest("TEST", short_term_qualifying_bars, config=config)
    assert result.metrics.qualifying_signals > 0


def test_short_term_uses_production_scorer(short_term_qualifying_bars):
    called = False
    original_score = tradex.backtest.engine.short_term_score

    def _wrapped(*args, **kwargs):
        nonlocal called
        called = True
        return original_score(*args, **kwargs)

    with mock.patch("tradex.backtest.engine.short_term_score", side_effect=_wrapped):
        config = BacktestConfig(min_score=40, warmup_bars=60, max_holding_bars=3)
        run_short_term_backtest("TEST", short_term_qualifying_bars, config=config)
    assert called


def test_default_weights_are_stable_fresh_snapshot(short_term_qualifying_bars):
    config = BacktestConfig(min_score=40, warmup_bars=60, max_holding_bars=3)
    result = run_short_term_backtest("TEST", short_term_qualifying_bars, config=config)
    assert result.weight_snapshot == {
        "ema_structure": 25,
        "volume_confirmation": 20,
        "rsi_momentum": 20,
        "macd_positive": 20,
        "pullback_ema": 15,
    }


def test_saved_user_weights_do_not_affect_default(tmp_path, short_term_qualifying_bars, monkeypatch):
    fake_path = tmp_path / "weights.json"
    fake_path.write_text(json.dumps({
        "intraday": {},
        "short": {
            "ema_structure": 99,
            "volume_confirmation": 0,
            "rsi_momentum": 0,
            "macd_positive": 0,
            "pullback_ema": 0,
        },
        "long": {},
    }))
    monkeypatch.setattr(weights_module, "WEIGHTS_PATH", fake_path)

    config = BacktestConfig(min_score=40, warmup_bars=60, max_holding_bars=3)
    result = run_short_term_backtest("TEST", short_term_qualifying_bars, config=config)
    assert result.weight_snapshot == {
        "ema_structure": 25,
        "volume_confirmation": 20,
        "rsi_momentum": 20,
        "macd_positive": 20,
        "pullback_ema": 15,
    }


def test_explicit_weights_change_snapshot_and_can_change_signals(short_term_qualifying_bars):
    custom = ShortWeights(
        ema_structure=0,
        volume_confirmation=0,
        rsi_momentum=0,
        macd_positive=0,
        pullback_ema=15,
    )
    config = BacktestConfig(min_score=40, warmup_bars=60, max_holding_bars=3)
    result = run_short_term_backtest("TEST", short_term_qualifying_bars, config=config, weights=custom)
    assert result.weight_snapshot["ema_structure"] == 0
    assert result.metrics.total_signals >= 0


def test_no_future_bars_passed_to_scorer(short_term_qualifying_bars):
    seen: list[pd.Timestamp] = []
    original = tradex.backtest.engine.short_term_score

    def _wrapped(df, weights=None):
        seen.append(df.index[-1])
        return original(df, weights=weights)

    with mock.patch("tradex.backtest.engine.short_term_score", side_effect=_wrapped):
        config = BacktestConfig(min_score=40, warmup_bars=60, max_holding_bars=3)
        run_short_term_backtest("TEST", short_term_qualifying_bars, config=config)

    for i, ts in enumerate(seen):
        assert ts == short_term_qualifying_bars.index[config.warmup_bars - 1 + i]
