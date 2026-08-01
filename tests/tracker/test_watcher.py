"""Tests for provider propagation through the scheduled watcher."""
from unittest.mock import MagicMock, patch

import pytest

from tradex.tracker import watcher


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
