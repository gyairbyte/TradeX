"""Tests for provider propagation through the scheduled watcher."""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradex.tracker import store, watcher


def test_run_once_passes_provider_to_screener(fresh_signal_db):
    """run_once must forward the provider argument to screener_run."""
    captured = {}

    def fake_screener_run(*args, **kwargs):
        captured["kwargs"] = kwargs
        return MagicMock(empty=True)

    with (
        patch.object(watcher, "screener_run", side_effect=fake_screener_run),
        patch.object(watcher, "_check_alerts"),
        patch.object(watcher, "run_outcome_pass"),
    ):
        watcher.run_once(
            ["AAPL"],
            timeframe="intraday",
            min_score=30,
            provider="alpaca",
        )

    assert "provider" in captured["kwargs"]
    assert captured["kwargs"]["provider"] == "alpaca"


def test_run_once_passes_provider_to_confluence_and_pattern(fresh_signal_db):
    """run_once must forward the provider to downstream OHLCV workflows."""
    confluence_captured = {}
    matcher_captured = {}

    def fake_confluence(tickers, **kwargs):
        confluence_captured["kwargs"] = kwargs
        return MagicMock(empty=True)

    def fake_matcher(tickers, **kwargs):
        matcher_captured["kwargs"] = kwargs
        return MagicMock(empty=True)

    with (
        patch.object(watcher, "screener_run", return_value=MagicMock(empty=True)),
        patch.object(watcher, "run_outcome_pass"),
        patch.object(watcher, "run_confluence_screen", side_effect=fake_confluence),
        patch.object(watcher, "run_match_screen", side_effect=fake_matcher),
        patch.object(watcher, "alert_coil"),
        patch.object(watcher, "alert_confluence"),
        patch.object(watcher, "alert_pattern_match"),
    ):
        watcher.run_once(
            ["AAPL"],
            timeframe="intraday",
            min_score=30,
            provider="schwab",
        )

    assert confluence_captured["kwargs"].get("provider") == "schwab"
    assert matcher_captured["kwargs"].get("provider") == "schwab"


def test_start_loop_schedules_run_once_with_provider():
    """start_loop must pass the provider into the scheduled run_once calls."""
    mock_schedule = MagicMock()
    mock_schedule.every.return_value.minutes.do.side_effect = SystemExit

    with (
        patch.object(watcher, "run_once") as mock_run_once,
        patch.object(watcher, "schedule", mock_schedule),
        pytest.raises(SystemExit),
    ):
        watcher.start_loop(
            ["AAPL"],
            timeframe="intraday",
            interval_minutes=5,
            min_score=30,
            provider="ibkr",
        )

    mock_run_once.assert_called_once_with(["AAPL"], "intraday", 30, "ibkr")
    mock_schedule.every.return_value.minutes.do.assert_called_once_with(
        mock_run_once,
        tickers=["AAPL"],
        timeframe="intraday",
        min_score=30,
        provider="ibkr",
    )


def _screener_results(provider: str = "schwab") -> pd.DataFrame:
    return pd.DataFrame([{
        "ticker": "AAPL",
        "score": 80,
        "last_close": 100.0,
        "volume_ratio": 2.0,
        "rsi": 60.0,
        "reasons": "test",
        "provider": provider,
    }])


def test_run_once_persists_screener_provider(fresh_signal_db):
    """run_once must write the resolved provider to both signals and scan_runs."""
    results = _screener_results("schwab")

    with (
        patch.object(watcher, "screener_run", return_value=results),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", provider="schwab")

    with store._conn() as con:
        signal_provider = con.execute("SELECT provider FROM signal_history").fetchone()["provider"]
        run_provider = con.execute("SELECT provider FROM scan_runs").fetchone()["provider"]
    assert signal_provider == "schwab"
    assert run_provider == "schwab"


def test_run_once_persists_env_default_provider(fresh_signal_db, monkeypatch):
    """When no provider is supplied, the resolved default provider is persisted."""
    monkeypatch.setattr("tradex.data.fetcher.DEFAULT_PROVIDER", "alpaca")
    results = _screener_results("alpaca")

    with (
        patch.object(watcher, "screener_run", return_value=results),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday")

    with store._conn() as con:
        signal_provider = con.execute("SELECT provider FROM signal_history").fetchone()["provider"]
    assert signal_provider == "alpaca"
