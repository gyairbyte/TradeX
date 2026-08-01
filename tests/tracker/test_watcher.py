"""Tests for provider propagation through the scheduled watcher."""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradex.data.fetcher import FetchAttempt, ProviderDataUnavailableError, ProviderTransientError
from tradex.screener.engine import ScanReport
from tradex.tracker import store, watcher


def _scan_report(
    results_df,
    provider,
    total_fetched=None,
    fallback_used=False,
    fetch_failures=None,
    earnings_failures=None,
    scoring_failures=None,
    total_fetch_eligible=None,
    total_retries=0,
    total_fetch_attempted=1,
    attempt_log=None,
    providers_attempted=None,
):
    total_fetched = total_fetched if total_fetched is not None else len(results_df)
    fetch_failures = fetch_failures or {}
    earnings_failures = earnings_failures or {}
    scoring_failures = scoring_failures or {}
    total_fetch_eligible = total_fetch_eligible if total_fetch_eligible is not None else total_fetched + len(fetch_failures)
    attempt_log = attempt_log or []
    failures = {**fetch_failures, **scoring_failures}
    providers = providers_attempted or (provider,)
    return ScanReport(
        results=results_df,
        requested_provider=provider,
        actual_provider=provider,
        fallback_used=fallback_used,
        providers_attempted=providers,
        failures=failures,
        total_requested=1,
        total_fetch_eligible=total_fetch_eligible,
        total_fetch_attempted=total_fetch_attempted,
        total_retries=total_retries,
        total_fetched=total_fetched,
        total_scored=0,
        total_signals=len(results_df),
        total_below_threshold=0,
        total_insufficient_data=0,
        total_earnings_excluded=0,
        earnings_failures=earnings_failures,
        fetch_failures=fetch_failures,
        scoring_failures=scoring_failures,
        attempt_log=attempt_log,
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
        fetch_failures={"AAPL": ProviderTransientError("network")},
        total_fetch_eligible=1,
    )

    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", provider="yahoo")

    captured = capsys.readouterr()
    assert "ERROR" in captured.out
    assert "all providers failed" in captured.out
    assert "1 symbol(s) that reached OHLCV fetching" in captured.out
    with store._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM signal_history").fetchone()[0] == 0


def test_run_once_logs_actual_retries_not_configured_max(fresh_signal_db, capsys):
    """Watcher logs the actual retry count, not the configured maximum."""
    results = _screener_results("yahoo")
    report = _scan_report(results, "yahoo", total_retries=0)

    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        # max_retries configured to 2, but no retries were actually used
        watcher.run_once(["AAPL"], timeframe="intraday", provider="yahoo", max_retries=2)

    captured = capsys.readouterr()
    assert "max_retries=2" in captured.out
    assert "retries=0, fallback" in captured.out
    assert ", retries=2, fallback" not in captured.out


def test_run_once_logs_retry_then_success(fresh_signal_db, capsys):
    """Watcher reports the actual retries used when a retry eventually succeeds."""
    results = _screener_results("yahoo")
    report = _scan_report(results, "yahoo", total_retries=1)

    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", provider="yahoo")

    captured = capsys.readouterr()
    assert "retries=1" in captured.out


def test_run_once_logs_fallback_history(fresh_signal_db, capsys):
    """Watcher prints a safe per-provider summary from the screener attempt log."""
    results = _screener_results("schwab")
    attempt_log = [
        FetchAttempt(provider="yahoo", ticker="AAPL", attempts=1, retries=0, success=False),
        FetchAttempt(provider="schwab", ticker="AAPL", attempts=2, retries=1, success=True),
    ]
    report = _scan_report(
        results,
        "schwab",
        fallback_used=True,
        providers_attempted=("yahoo", "schwab"),
        total_retries=1,
        total_fetch_attempted=3,
        attempt_log=attempt_log,
    )

    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", provider="yahoo", fallback_order=("schwab",))

    captured = capsys.readouterr()
    assert "fallback=True" in captured.out
    assert "yahoo: 1 attempted, 0 succeeded, 1 failed, 0 retries" in captured.out
    assert "schwab: 1 attempted, 1 succeeded, 0 failed, 1 retries" in captured.out


def test_run_once_surfaces_earnings_failure_with_signals(fresh_signal_db, capsys):
    """Earnings lookup failures are disclosed independently when a signal is also found."""
    results = _screener_results("yahoo")
    report = _scan_report(
        results,
        "yahoo",
        earnings_failures={"MSFT": ProviderDataUnavailableError("earnings lookup failed")},
        total_fetch_eligible=1,
    )

    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL", "MSFT"], timeframe="intraday", provider="yahoo")

    captured = capsys.readouterr()
    assert "1 signals found" in captured.out
    assert "Earnings lookup failures: 1 symbol(s)" in captured.out


def test_run_once_uses_fetch_eligible_count_for_complete_failure(fresh_signal_db, capsys):
    """Complete OHLCV-failure messaging uses the count of symbols that reached fetching."""
    empty = pd.DataFrame(columns=[
        "ticker", "score", "last_close", "volume_ratio", "rsi",
        "days_until_earnings", "reasons", "provider",
    ])
    report = _scan_report(
        empty,
        provider="yahoo",
        total_fetched=0,
        fetch_failures={"MSFT": ProviderTransientError("network")},
        earnings_failures={"AAPL": ProviderDataUnavailableError("earnings lookup failed")},
        total_fetch_eligible=1,
    )

    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL", "MSFT"], timeframe="intraday", provider="yahoo")

    captured = capsys.readouterr()
    assert "all providers failed for 1 symbol(s) that reached OHLCV fetching" in captured.out
    assert "Earnings lookup failures: 1 symbol(s)" in captured.out
    assert "2 symbol(s)" not in captured.out
