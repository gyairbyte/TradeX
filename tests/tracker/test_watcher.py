"""Tests for provider propagation through the scheduled watcher."""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradex.screener.engine import ScanReport
from tradex.tracker import store, watcher


def _scan_report(results_df, provider, total_fetched=None, fallback_used=False):
    total_fetched = total_fetched if total_fetched is not None else len(results_df)
    return ScanReport(
        results=results_df,
        requested_provider=provider,
        actual_provider=provider,
        fallback_used=fallback_used,
        providers_attempted=(provider,),
        failures={},
        total_requested=1,
        total_fetch_attempted=1,
        total_fetched=total_fetched,
        total_scored=0,
        total_signals=len(results_df),
        total_below_threshold=0,
        total_insufficient_data=0,
        total_earnings_excluded=0,
    )


def test_run_once_passes_provider_to_screener(fresh_signal_db):
    """run_once must forward the provider argument to the structured screener report."""
    captured = {}

    def fake_screener_run(*args, **kwargs):
        captured["kwargs"] = kwargs
        empty = pd.DataFrame(columns=[
            "ticker", "score", "last_close", "volume_ratio", "rsi",
            "days_until_earnings", "reasons", "provider",
        ])
        return _scan_report(empty, kwargs.get("provider"), total_fetched=0)

    with (
        patch.object(watcher, "screener_run_with_report", side_effect=fake_screener_run),
        patch.object(watcher, "_check_alerts"),
        patch.object(watcher, "run_outcome_pass"),
    ):
        watcher.run_once(
            ["AAPL"],
            timeframe="intraday",
            min_score=30,
            provider="alpaca",
        )

    assert captured["kwargs"]["provider"] == "alpaca"


def test_run_once_passes_provider_to_confluence_and_pattern(fresh_signal_db):
    """run_once must forward the actual provider to downstream OHLCV workflows."""
    confluence_captured = {}
    matcher_captured = {}

    def fake_confluence(tickers, **kwargs):
        confluence_captured["kwargs"] = kwargs
        return MagicMock(empty=True)

    def fake_matcher(tickers, **kwargs):
        matcher_captured["kwargs"] = kwargs
        return MagicMock(empty=True)

    empty = pd.DataFrame(columns=[
        "ticker", "score", "last_close", "volume_ratio", "rsi",
        "days_until_earnings", "reasons", "provider",
    ])

    with (
        patch.object(watcher, "screener_run_with_report", return_value=_scan_report(empty, "schwab", total_fetched=1)),
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
    """start_loop must pass the provider and policy args into the scheduled run_once calls."""
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

    mock_run_once.assert_called_once_with(
        ["AAPL"], "intraday", 30, "ibkr",
        max_retries=None, fallback_order=None, policy=None,
    )
    mock_schedule.every.return_value.minutes.do.assert_called_once_with(
        mock_run_once,
        tickers=["AAPL"],
        timeframe="intraday",
        min_score=30,
        provider="ibkr",
        max_retries=None,
        fallback_order=None,
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
        patch.object(watcher, "screener_run_with_report", return_value=_scan_report(results, "schwab")),
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
        patch.object(watcher, "screener_run_with_report", return_value=_scan_report(results, "alpaca")),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday")

    with store._conn() as con:
        signal_provider = con.execute("SELECT provider FROM signal_history").fetchone()["provider"]
    assert signal_provider == "alpaca"


def test_run_once_reports_provider_failure_without_persisting(fresh_signal_db, capsys):
    """When every provider fails, run_once prints an error summary and writes no signals."""
    from tradex.data.fetcher import ProviderTransientError

    empty = pd.DataFrame(columns=[
        "ticker", "score", "last_close", "volume_ratio", "rsi",
        "days_until_earnings", "reasons", "provider",
    ])
    report = _scan_report(
        empty,
        provider="yahoo",
        total_fetched=0,
        fallback_used=False,
    )
    report.failures = {"AAPL": ProviderTransientError("network")}

    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", provider="yahoo")

    captured = capsys.readouterr()
    assert "ERROR" in captured.out
    assert "all providers failed" in captured.out
    with store._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM signal_history").fetchone()[0] == 0
