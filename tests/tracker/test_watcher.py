"""Tests for provider propagation through the scheduled watcher."""

import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from tradex.alerts.policy import AlertPolicy
from tradex.config import settings_from_mapping
from tradex.data.fetcher import FetchAttempt, ProviderDataUnavailableError, ProviderTransientError
from tradex.screener.engine import ScanReport
from tradex.tracker import store, watcher


def _scan_report(
    results_df,
    provider,
    tickers=None,
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
    requested_provider=None,
):
    from tradex.screener.engine import ObservationStatus

    total_fetched = total_fetched if total_fetched is not None else len(results_df)
    fetch_failures = fetch_failures or {}
    earnings_failures = earnings_failures or {}
    scoring_failures = scoring_failures or {}
    total_fetch_eligible = (
        total_fetch_eligible
        if total_fetch_eligible is not None
        else total_fetched + len(fetch_failures)
    )
    attempt_log = attempt_log or []
    failures = {**fetch_failures, **scoring_failures}
    requested = requested_provider or provider
    providers = providers_attempted or (requested,)

    # Normalize result frames to the stable signal column contract.
    if not results_df.empty:
        results_df = results_df.copy()
        if "days_until_earnings" not in results_df.columns:
            results_df["days_until_earnings"] = None
        if "provider" not in results_df.columns:
            results_df["provider"] = provider
        else:
            results_df["provider"] = results_df["provider"].fillna(provider)

    observed_tickers = set(results_df["ticker"].tolist())
    observed_tickers.update(fetch_failures)
    observed_tickers.update(earnings_failures)
    observed_tickers.update(scoring_failures)
    requested_tickers = set(tickers) if tickers else observed_tickers
    requested_tickers = {str(t).strip().upper() for t in requested_tickers}

    actual_provider = provider if (total_fetched > 0 or not results_df.empty) else None

    observations: list[dict] = []
    for _, row in results_df.iterrows():
        observations.append(
            {
                "ticker": str(row["ticker"]).strip().upper(),
                "status": ObservationStatus.SIGNAL.value,
                "score": int(row["score"]),
                "last_close": float(row["last_close"]),
                "volume_ratio": float(row["volume_ratio"]),
                "rsi": float(row["rsi"]),
                "days_until_earnings": int(row["days_until_earnings"])
                if pd.notna(row.get("days_until_earnings"))
                else None,
                "reasons": str(row.get("reasons", "")),
                "provider": actual_provider,
                "error_category": None,
                "error_message": None,
            }
        )
    for ticker, err in fetch_failures.items():
        observations.append(
            {
                "ticker": str(ticker).strip().upper(),
                "status": ObservationStatus.FETCH_FAILURE.value,
                "score": None,
                "last_close": None,
                "volume_ratio": None,
                "rsi": None,
                "days_until_earnings": None,
                "reasons": None,
                "provider": None,
                "error_category": type(err).__name__,
                "error_message": str(err),
            }
        )
    for ticker, err in scoring_failures.items():
        observations.append(
            {
                "ticker": str(ticker).strip().upper(),
                "status": ObservationStatus.SCORING_FAILURE.value,
                "score": None,
                "last_close": None,
                "volume_ratio": None,
                "rsi": None,
                "days_until_earnings": None,
                "reasons": None,
                "provider": actual_provider,
                "error_category": type(err).__name__,
                "error_message": str(err),
            }
        )
    for ticker, err in earnings_failures.items():
        observations.append(
            {
                "ticker": str(ticker).strip().upper(),
                "status": ObservationStatus.EARNINGS_FAILURE.value,
                "score": None,
                "last_close": None,
                "volume_ratio": None,
                "rsi": None,
                "days_until_earnings": None,
                "reasons": None,
                "provider": None,
                "error_category": type(err).__name__,
                "error_message": str(err),
            }
        )

    seen = {obs["ticker"] for obs in observations}
    for ticker in requested_tickers - seen:
        if actual_provider is not None:
            observations.append(
                {
                    "ticker": ticker,
                    "status": ObservationStatus.BELOW_THRESHOLD.value,
                    "score": 0,
                    "last_close": 0.0,
                    "volume_ratio": 0.0,
                    "rsi": 0.0,
                    "days_until_earnings": None,
                    "reasons": "",
                    "provider": actual_provider,
                    "error_category": None,
                    "error_message": None,
                }
            )
        else:
            observations.append(
                {
                    "ticker": ticker,
                    "status": ObservationStatus.INSUFFICIENT_DATA.value,
                    "score": None,
                    "last_close": None,
                    "volume_ratio": None,
                    "rsi": None,
                    "days_until_earnings": None,
                    "reasons": None,
                    "provider": None,
                    "error_category": None,
                    "error_message": None,
                }
            )

    observations_df = pd.DataFrame(observations)
    if observations_df.empty:
        observations_df = pd.DataFrame(
            columns=[
                "ticker",
                "status",
                "score",
                "last_close",
                "volume_ratio",
                "rsi",
                "days_until_earnings",
                "reasons",
                "provider",
                "error_category",
                "error_message",
            ]
        )
    else:
        observations_df = observations_df.sort_values("ticker").reset_index(drop=True)

    return ScanReport(
        results=results_df,
        requested_provider=requested,
        actual_provider=actual_provider,
        fallback_used=fallback_used,
        providers_attempted=providers,
        failures=failures,
        total_requested=len(requested_tickers),
        total_fetch_eligible=total_fetch_eligible,
        total_fetch_attempted=total_fetch_attempted,
        total_retries=total_retries,
        total_fetched=total_fetched,
        total_scored=(
            len(results_df)
            + int((observations_df["status"] == ObservationStatus.BELOW_THRESHOLD.value).sum())
            if not observations_df.empty
            else len(results_df)
        ),
        total_signals=len(results_df),
        total_below_threshold=int(
            (observations_df["status"] == ObservationStatus.BELOW_THRESHOLD.value).sum()
        )
        if not observations_df.empty
        else 0,
        total_insufficient_data=int(
            (observations_df["status"] == ObservationStatus.INSUFFICIENT_DATA.value).sum()
        )
        if not observations_df.empty
        else 0,
        total_earnings_excluded=0,
        earnings_failures=earnings_failures,
        fetch_failures=fetch_failures,
        scoring_failures=scoring_failures,
        attempt_log=attempt_log,
        observations=observations_df,
    )


def test_run_once_passes_provider_to_screener(fresh_signal_db):
    """run_once must forward the provider argument to the structured screener report."""
    captured = {}

    def fake_screener_run(tickers, *args, **kwargs):
        captured["kwargs"] = kwargs
        empty = pd.DataFrame(
            columns=[
                "ticker",
                "score",
                "last_close",
                "volume_ratio",
                "rsi",
                "days_until_earnings",
                "reasons",
                "provider",
            ]
        )
        return _scan_report(empty, kwargs.get("provider"), total_fetched=0, tickers=tickers)

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


def test_run_once_passes_provider_to_confluence(fresh_signal_db):
    """run_once must forward the actual provider to downstream confluence workflow."""
    confluence_captured = {}

    def fake_confluence(tickers, **kwargs):
        confluence_captured["kwargs"] = kwargs
        return MagicMock(empty=True)

    empty = pd.DataFrame(
        columns=[
            "ticker",
            "score",
            "last_close",
            "volume_ratio",
            "rsi",
            "days_until_earnings",
            "reasons",
            "provider",
        ]
    )

    with (
        patch.object(
            watcher,
            "screener_run_with_report",
            return_value=_scan_report(empty, "schwab", total_fetched=1, tickers=["AAPL"]),
        ),
        patch.object(watcher, "run_outcome_pass"),
        patch.object(watcher, "run_confluence_screen", side_effect=fake_confluence),
        patch.object(watcher, "alert_coil"),
        patch.object(watcher, "alert_confluence"),
    ):
        watcher.run_once(
            ["AAPL"],
            timeframe="intraday",
            min_score=30,
            provider="schwab",
        )

    assert confluence_captured["kwargs"].get("provider") == "schwab"


def test_start_loop_schedules_run_once_with_provider():
    """start_loop runs an initial scan and registers a wrapper that forwards provider/policy."""
    mock_schedule = MagicMock()

    with (
        patch.object(watcher, "run_once") as mock_run_once,
        patch.object(watcher, "schedule", mock_schedule),
        patch.object(watcher.time, "sleep", side_effect=SystemExit),
        pytest.raises(SystemExit),
    ):
        watcher.start_loop(
            ["AAPL"],
            timeframe="intraday",
            interval_minutes=5,
            min_score=30,
            provider="ibkr",
        )

    # The scheduled callback is a no-argument wrapper that resolves the provider.
    scheduled_callback = mock_schedule.every.return_value.minutes.do.call_args[0][0]
    assert callable(scheduled_callback)

    # Re-patch run_once and invoke the captured callback to verify forwarding.
    with patch.object(watcher, "run_once") as mock_run_once:
        scheduled_callback()

    mock_run_once.assert_called_once()
    assert mock_run_once.call_args.args == (["AAPL"], "intraday", 30, "ibkr")
    assert mock_run_once.call_args.kwargs == {
        "max_retries": None,
        "fallback_order": None,
        "policy": None,
        "market_hours_only": False,
        "alert_policy": mock_run_once.call_args.kwargs["alert_policy"],
        "now": mock_run_once.call_args.kwargs["now"],
        "settings": mock_run_once.call_args.kwargs["settings"],
    }
    assert isinstance(mock_run_once.call_args.kwargs["now"], datetime)


def _screener_results(provider: str = "schwab") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "score": 80,
                "last_close": 100.0,
                "volume_ratio": 2.0,
                "rsi": 60.0,
                "reasons": "test",
                "provider": provider,
            }
        ]
    )


def test_run_once_persists_screener_provider(fresh_signal_db):
    """run_once must write the resolved provider to signal_history and scan_sessions."""
    results = _screener_results("schwab")

    with (
        patch.object(
            watcher, "screener_run_with_report", return_value=_scan_report(results, "schwab")
        ),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", provider="schwab")

    with store._conn() as con:
        signal_provider = con.execute("SELECT provider FROM signal_history").fetchone()["provider"]
        run_provider = con.execute("SELECT actual_provider FROM scan_sessions").fetchone()[
            "actual_provider"
        ]
    assert signal_provider == "schwab"
    assert run_provider == "schwab"


def test_run_once_persists_env_default_provider(fresh_signal_db, monkeypatch):
    """When no provider is supplied, the resolved default provider is persisted."""
    monkeypatch.setenv("DATA_PROVIDER", "alpaca")
    results = _screener_results("alpaca")

    with (
        patch.object(
            watcher, "screener_run_with_report", return_value=_scan_report(results, "alpaca")
        ),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday")

    with store._conn() as con:
        signal_provider = con.execute("SELECT provider FROM signal_history").fetchone()["provider"]
    assert signal_provider == "alpaca"


def test_run_once_reports_provider_failure_without_persisting(fresh_signal_db, capsys):
    """When every provider fails, run_once prints an error summary and writes no signals."""
    from tradex.data.fetcher import ProviderTransientError

    empty = pd.DataFrame(
        columns=[
            "ticker",
            "score",
            "last_close",
            "volume_ratio",
            "rsi",
            "days_until_earnings",
            "reasons",
            "provider",
        ]
    )
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
        watcher.run_once(
            ["AAPL"], timeframe="intraday", provider="yahoo", fallback_order=("schwab",)
        )

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
    empty = pd.DataFrame(
        columns=[
            "ticker",
            "score",
            "last_close",
            "volume_ratio",
            "rsi",
            "days_until_earnings",
            "reasons",
            "provider",
        ]
    )
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


def _ny(*args) -> datetime:
    return datetime(*args, tzinfo=ZoneInfo("America/New_York"))


def test_run_once_manual_default_runs_outside_market_hours(fresh_signal_db, capsys):
    """Default run_once (market_hours_only=False) runs even when the market is closed."""
    empty = pd.DataFrame(
        columns=[
            "ticker",
            "score",
            "last_close",
            "volume_ratio",
            "rsi",
            "days_until_earnings",
            "reasons",
            "provider",
        ]
    )
    report = _scan_report(empty, provider="yahoo", total_fetched=0, tickers=["AAPL"])

    # Saturday 10:00 AM ET
    now = _ny(2025, 1, 18, 10, 0)
    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", now=now)

    captured = capsys.readouterr()
    assert "Scanning" in captured.out


def test_run_once_market_hours_only_skips_before_open(fresh_signal_db, capsys):
    now = _ny(2025, 1, 15, 9, 0)
    with patch.object(watcher, "screener_run_with_report") as mock_screener:
        watcher.run_once(["AAPL"], timeframe="intraday", market_hours_only=True, now=now)
    assert mock_screener.call_count == 0
    captured = capsys.readouterr()
    assert "Market closed" in captured.out
    assert "Before regular session" in captured.out
    assert "Next regular session opens" in captured.out


def test_run_once_market_hours_only_skips_after_close(fresh_signal_db, capsys):
    now = _ny(2025, 1, 15, 17, 0)
    with patch.object(watcher, "screener_run_with_report") as mock_screener:
        watcher.run_once(["AAPL"], timeframe="intraday", market_hours_only=True, now=now)
    assert mock_screener.call_count == 0
    captured = capsys.readouterr()
    assert "After regular session" in captured.out


def test_run_once_market_hours_only_skips_weekend(fresh_signal_db, capsys):
    now = _ny(2025, 1, 18, 10, 0)
    with patch.object(watcher, "screener_run_with_report") as mock_screener:
        watcher.run_once(["AAPL"], timeframe="intraday", market_hours_only=True, now=now)
    assert mock_screener.call_count == 0
    captured = capsys.readouterr()
    assert "Market closed" in captured.out
    assert "Weekend" in captured.out


def test_run_once_market_hours_only_skips_holiday(fresh_signal_db, capsys):
    now = _ny(2025, 1, 1, 10, 0)
    with patch.object(watcher, "screener_run_with_report") as mock_screener:
        watcher.run_once(["AAPL"], timeframe="intraday", market_hours_only=True, now=now)
    assert mock_screener.call_count == 0
    captured = capsys.readouterr()
    assert "Weekend or exchange holiday" in captured.out


def test_run_once_market_hours_only_runs_during_session(fresh_signal_db, capsys):
    results = _screener_results("yahoo")
    now = _ny(2025, 1, 15, 10, 0)
    with (
        patch.object(
            watcher,
            "screener_run_with_report",
            return_value=_scan_report(results, "yahoo", total_fetched=1),
        ),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", market_hours_only=True, now=now)

    captured = capsys.readouterr()
    assert "Scanning" in captured.out


def test_run_once_market_hours_only_before_early_close_runs(fresh_signal_db):
    results = _screener_results("yahoo")
    # Black Friday 2025 12:00 PM ET is before the early 13:00 close.
    now = _ny(2025, 11, 28, 12, 0)
    with (
        patch.object(
            watcher,
            "screener_run_with_report",
            return_value=_scan_report(results, "yahoo", total_fetched=1),
        ),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", market_hours_only=True, now=now)


def test_run_once_market_hours_only_after_early_close_skips(fresh_signal_db, capsys):
    now = _ny(2025, 11, 28, 13, 1)
    with patch.object(watcher, "screener_run_with_report") as mock_screener:
        watcher.run_once(["AAPL"], timeframe="intraday", market_hours_only=True, now=now)
    assert mock_screener.call_count == 0
    captured = capsys.readouterr()
    assert "After regular session" in captured.out


def test_run_once_skip_does_not_touch_store_or_alerts(fresh_signal_db, capsys):
    now = _ny(2025, 1, 15, 17, 0)
    with (
        patch.object(watcher, "screener_run_with_report") as mock_screener,
        patch.object(watcher.store, "record_scan") as mock_record,
        patch.object(watcher, "_check_alerts") as mock_alerts,
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", market_hours_only=True, now=now)

    assert mock_screener.call_count == 0
    assert mock_record.call_count == 0
    assert mock_alerts.call_count == 0


def test_run_once_uses_new_york_timestamp_format(fresh_signal_db, capsys):
    """Timestamps are printed in New York time with a timezone abbreviation."""
    empty = pd.DataFrame(
        columns=[
            "ticker",
            "score",
            "last_close",
            "volume_ratio",
            "rsi",
            "days_until_earnings",
            "reasons",
            "provider",
        ]
    )
    # 2025-07-02 10:00 EDT
    now = datetime(2025, 7, 2, 14, 0, tzinfo=UTC)
    with (
        patch.object(
            watcher,
            "screener_run_with_report",
            return_value=_scan_report(empty, "yahoo", total_fetched=0, tickers=["AAPL"]),
        ),
        patch.object(watcher, "_check_alerts"),
        patch.object(watcher.store, "record_scan"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", now=now)
    captured = capsys.readouterr()
    # 14:00 UTC in July is 10:00 EDT
    assert "2025-07-02 10:00 EDT" in captured.out


def test_start_loop_daily_jobs_use_new_york_timezone():
    """Daily pre-market and outcome jobs are scheduled in America/New_York."""
    mock_schedule = MagicMock()
    with (
        patch.object(watcher, "run_once"),
        patch.object(watcher, "schedule", mock_schedule),
        patch.object(watcher.time, "sleep", side_effect=SystemExit),
        pytest.raises(SystemExit),
    ):
        watcher.start_loop(["AAPL"], interval_minutes=5)

    mock_schedule.every.return_value.day.at.assert_any_call("08:00", "America/New_York")
    mock_schedule.every.return_value.day.at.assert_any_call("16:30", "America/New_York")


def test_scheduled_premarket_skips_non_trading_day(capsys):
    now = datetime(2025, 1, 1, 13, 0, tzinfo=UTC)  # New Year's morning ET
    with patch.object(watcher, "scan_gaps_with_report") as mock_report:
        watcher._run_scheduled_premarket(["AAPL"], provider="yahoo", now=now)
    assert mock_report.call_count == 0
    captured = capsys.readouterr()
    assert "Skipping pre-market gap scan" in captured.out


def test_scheduled_premarket_runs_on_trading_day():
    now = datetime(2025, 1, 15, 13, 0, tzinfo=UTC)  # 08:00 ET
    mock_report = MagicMock()
    mock_report.counts.return_value = {
        "requested": 1,
        "qualified": 1,
        "filtered": 0,
        "failed": 0,
        "outside_window": 0,
    }
    mock_report.provider_errors = {}
    mock_report.results.iterrows.return_value = [
        (
            0,
            pd.Series(
                {
                    "ticker": "AAPL",
                    "gap_pct": 5.0,
                    "direction": "up",
                    "tier": "large",
                    "prev_close": 100.0,
                    "pre_market": 105.0,
                }
            ),
        ),
    ]
    with (
        patch.object(watcher, "scan_gaps_with_report", return_value=mock_report) as mock_scan,
        patch("tradex.tracker.watcher.alert_gap") as mock_alert,
    ):
        watcher._run_scheduled_premarket(["AAPL"], provider="yahoo", now=now)
    assert mock_scan.call_count == 1
    _, kwargs = mock_scan.call_args
    assert kwargs["provider"] == "yahoo"
    assert kwargs["as_of"] == now
    assert mock_alert.call_count == 1


def test_scheduled_outcomes_skips_non_trading_day(capsys):
    now = datetime(2025, 1, 1, 21, 30, tzinfo=UTC)
    with patch.object(watcher, "run_outcome_pass") as mock_outcome:
        watcher._run_scheduled_outcomes(provider="schwab", now=now)
    assert mock_outcome.call_count == 0
    captured = capsys.readouterr()
    assert "Skipping outcome pass" in captured.out


def test_scheduled_outcomes_runs_on_trading_day():
    now = datetime(2025, 1, 15, 21, 30, tzinfo=UTC)  # 16:30 ET
    with patch.object(watcher, "run_outcome_pass") as mock_outcome:
        watcher._run_scheduled_outcomes(provider="schwab", now=now)
    assert mock_outcome.call_count == 1
    _, kwargs = mock_outcome.call_args
    assert kwargs["provider"] == "schwab"


def test_cli_flag_propagates_market_hours_only():
    """The --market-hours-only flag is parsed and passed to start_loop."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "tradex.tracker.watcher", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "--market-hours-only" in result.stdout


# ── COR-012 scan-audit integration tests ─────────────────────────────────────


def _assert_scan_audit_row(timeframe="intraday"):
    """Return the single audit row for a watcher-initiated scan."""
    runs = store.get_recent_scan_runs(timeframe=timeframe)
    assert len(runs) == 1, f"expected one audit row, got {len(runs)}"
    return runs.iloc[0]


def test_watcher_successful_signal_scan_creates_audit_row(fresh_signal_db):
    """A scan that produces qualifying signals writes one native audit row."""
    results = _screener_results("schwab")
    with (
        patch.object(
            watcher, "screener_run_with_report", return_value=_scan_report(results, "schwab")
        ),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", provider="schwab")

    run = _assert_scan_audit_row()
    assert run["tickers_n"] == 1
    assert run["hits_n"] == 1
    assert run["status"] == "completed"
    assert run["counts_complete"] == 1
    assert run["source"] == "native"
    assert run["requested_provider"] == "schwab"
    assert run["actual_provider"] == "schwab"
    assert run["provider"] == "schwab"


def test_watcher_zero_signal_scan_creates_audit_row(fresh_signal_db):
    """A scan with no qualifying signals still writes a native audit row."""
    results = pd.DataFrame(
        columns=[
            "ticker",
            "score",
            "last_close",
            "volume_ratio",
            "rsi",
            "days_until_earnings",
            "reasons",
            "provider",
        ]
    )
    report = _scan_report(results, "yahoo", total_fetched=1, tickers=["AAPL"])
    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", provider="yahoo")

    run = _assert_scan_audit_row()
    assert run["tickers_n"] == 1
    assert run["hits_n"] == 0
    assert run["status"] == "completed"


def test_watcher_all_earnings_excluded_creates_audit_row(fresh_signal_db):
    """A scan where every ticker is earnings-excluded writes a zero-hit audit row."""
    from tradex.screener.engine import ObservationStatus, ScanReport

    scan_time = _ny(2025, 1, 15, 10, 0)
    observations = pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "status": ObservationStatus.EARNINGS_EXCLUDED.value,
                "score": None,
                "last_close": None,
                "volume_ratio": None,
                "rsi": None,
                "days_until_earnings": 2,
                "reasons": None,
                "provider": None,
                "error_category": None,
                "error_message": None,
            },
            {
                "ticker": "MSFT",
                "status": ObservationStatus.EARNINGS_EXCLUDED.value,
                "score": None,
                "last_close": None,
                "volume_ratio": None,
                "rsi": None,
                "days_until_earnings": 1,
                "reasons": None,
                "provider": None,
                "error_category": None,
                "error_message": None,
            },
        ]
    )
    report = ScanReport(
        results=pd.DataFrame(
            columns=[
                "ticker",
                "score",
                "last_close",
                "volume_ratio",
                "rsi",
                "days_until_earnings",
                "reasons",
                "provider",
            ]
        ),
        requested_provider="yahoo",
        actual_provider="yahoo",
        fallback_used=False,
        providers_attempted=("yahoo",),
        failures={},
        total_requested=2,
        total_fetch_attempted=2,
        total_fetched=2,
        total_scored=0,
        total_signals=0,
        total_below_threshold=0,
        total_insufficient_data=0,
        total_earnings_excluded=2,
        earnings_failures={},
        fetch_failures={},
        scoring_failures={},
        total_fetch_eligible=2,
        total_retries=0,
        attempt_log=[],
        observations=observations,
    )

    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL", "MSFT"], timeframe="intraday", provider="yahoo", now=scan_time)

    run = _assert_scan_audit_row()
    assert run["tickers_n"] == 2
    assert run["hits_n"] == 0
    assert run["status"] == "completed"
    assert run["actual_provider"] == "yahoo"


def test_watcher_partial_scan_creates_audit_row(fresh_signal_db):
    """A scan with some signals and some fetch failures writes a partial audit row."""
    from tradex.data.fetcher import ProviderTransientError

    results = _screener_results("yahoo")
    report = _scan_report(
        results,
        "yahoo",
        tickers=["AAPL", "MSFT"],
        fetch_failures={"MSFT": ProviderTransientError("network")},
        total_fetched=1,
    )

    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL", "MSFT"], timeframe="intraday", provider="yahoo")

    run = _assert_scan_audit_row()
    assert run["tickers_n"] == 2
    assert run["hits_n"] == 1
    assert run["status"] == "partial"


def test_watcher_complete_provider_failure_creates_audit_row(fresh_signal_db, capsys):
    """A scan where every provider fails writes a failed audit row."""
    from tradex.data.fetcher import ProviderTransientError

    results = pd.DataFrame(
        columns=[
            "ticker",
            "score",
            "last_close",
            "volume_ratio",
            "rsi",
            "days_until_earnings",
            "reasons",
            "provider",
        ]
    )
    report = _scan_report(
        results,
        "yahoo",
        tickers=["AAPL"],
        fetch_failures={"AAPL": ProviderTransientError("network")},
        total_fetched=0,
    )

    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", provider="yahoo")

    run = _assert_scan_audit_row()
    assert run["tickers_n"] == 1
    assert run["hits_n"] == 0
    assert run["status"] == "failed"
    assert run["actual_provider"] is None


def test_watcher_market_hours_skip_writes_no_audit_row(fresh_signal_db, capsys):
    """A market-hours skip must not create any session, observation, signal, or audit state."""
    now = _ny(2025, 1, 15, 17, 0)
    with (
        patch.object(watcher, "screener_run_with_report") as mock_screener,
        patch.object(watcher.store, "record_scan") as mock_record,
        patch.object(watcher, "_check_alerts") as mock_alerts,
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", market_hours_only=True, now=now)

    assert mock_screener.call_count == 0
    assert mock_record.call_count == 0
    assert mock_alerts.call_count == 0
    with store._conn() as con:
        for table in ("scan_sessions", "scan_observations", "signal_history", "scan_runs"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_watcher_duplicate_input_tickers_count_once(fresh_signal_db):
    """The watchlist passed to record_scan is normalized and deduplicated."""
    results = _screener_results("yahoo")
    with (
        patch.object(
            watcher, "screener_run_with_report", return_value=_scan_report(results, "yahoo")
        ) as mock_screener,
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL", "aapl", "AAPL"], timeframe="intraday", provider="yahoo")

    # The screener receives the normalized, deduplicated watchlist.
    assert mock_screener.call_args.args[0] == ["AAPL"]
    run = _assert_scan_audit_row()
    assert run["tickers_n"] == 1
    assert run["hits_n"] == 1


def test_watcher_injected_timestamp_is_audit_timestamp(fresh_signal_db):
    """The aware datetime injected into run_once becomes the audit run_time."""
    now = _ny(2025, 6, 15, 10, 30)
    results = _screener_results("yahoo")
    with (
        patch.object(
            watcher, "screener_run_with_report", return_value=_scan_report(results, "yahoo")
        ),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(["AAPL"], timeframe="intraday", provider="yahoo", now=now)

    run = _assert_scan_audit_row()
    assert run["run_time"] == now.astimezone(UTC).isoformat()


def _premarket_report(
    requested: int = 1,
    qualified: int = 0,
    filtered: int = 0,
    failed: int = 0,
    outside_window: int = 0,
    provider_failure: int = 0,
    no_previous_close: int = 0,
    no_premarket_data: int = 0,
    non_trading_day: int = 0,
    provider_errors: dict | None = None,
    results: pd.DataFrame | None = None,
) -> MagicMock:
    report = MagicMock()
    report.counts.return_value = {
        "requested": requested,
        "qualified": qualified,
        "filtered": filtered,
        "failed": failed,
        "outside_window": outside_window,
        "provider_failure": provider_failure,
        "no_previous_close": no_previous_close,
        "no_premarket_data": no_premarket_data,
        "non_trading_day": non_trading_day,
    }
    report.provider_errors = provider_errors or {}
    report.results = results if results is not None else pd.DataFrame()
    return report


def test_scheduled_premarket_default_threshold_is_4_percent():
    """The scheduled pre-market scan keeps the original 4% alert threshold."""
    now = datetime(2025, 1, 15, 13, 0, tzinfo=UTC)  # 08:00 ET
    report = _premarket_report()
    with patch.object(watcher, "scan_gaps_with_report", return_value=report) as mock_scan:
        watcher._run_scheduled_premarket(["AAPL"], provider="yahoo", now=now)
    assert mock_scan.call_count == 1
    _, kwargs = mock_scan.call_args
    assert kwargs["config"].min_abs_gap_pct == 4.0


def test_scheduled_premarket_filtered_rows_do_not_alert(capsys):
    """A ticker that is filtered out must never trigger an alert."""
    now = datetime(2025, 1, 15, 13, 0, tzinfo=UTC)
    report = _premarket_report(requested=1, qualified=0, filtered=1, failed=0)
    with (
        patch.object(watcher, "scan_gaps_with_report", return_value=report),
        patch("tradex.tracker.watcher.alert_gap") as mock_alert,
    ):
        watcher._run_scheduled_premarket(["AAPL"], provider="yahoo", now=now)
    mock_alert.assert_not_called()
    captured = capsys.readouterr()
    assert "No qualifying gaps" in captured.out


def test_scheduled_premarket_zero_results_not_provider_failure(capsys):
    """A scan with no qualifying gaps is a normal zero result, not a provider failure."""
    now = datetime(2025, 1, 15, 13, 0, tzinfo=UTC)
    report = _premarket_report(requested=1, qualified=0, filtered=0, failed=0, outside_window=0)
    with patch.object(watcher, "scan_gaps_with_report", return_value=report):
        watcher._run_scheduled_premarket(["AAPL"], provider="yahoo", now=now)
    captured = capsys.readouterr()
    assert "No qualifying gaps" in captured.out
    assert "All tickers failed" not in captured.out


def test_scheduled_premarket_partial_failure_surfaces(capsys):
    """Partial provider failures are surfaced while still alerting qualifying rows."""
    now = datetime(2025, 1, 15, 13, 0, tzinfo=UTC)
    results = pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "gap_pct": 5.0,
                "direction": "up",
                "tier": "large",
                "prev_close": 100.0,
                "pre_market": 105.0,
            }
        ]
    )
    report = _premarket_report(
        requested=2,
        qualified=1,
        filtered=0,
        failed=1,
        provider_errors={"TSLA": "data unavailable"},
        results=results,
    )
    with (
        patch.object(watcher, "scan_gaps_with_report", return_value=report),
        patch("tradex.tracker.watcher.alert_gap") as mock_alert,
    ):
        watcher._run_scheduled_premarket(["AAPL", "TSLA"], provider="yahoo", now=now)
    mock_alert.assert_called_once()
    captured = capsys.readouterr()
    assert "provider errors" in captured.out
    assert "data unavailable" in captured.out


def test_scheduled_premarket_complete_provider_failure_surfaces(capsys):
    """When every ticker fails, the watcher reports a complete failure."""
    now = datetime(2025, 1, 15, 13, 0, tzinfo=UTC)
    report = _premarket_report(
        requested=2,
        qualified=0,
        filtered=0,
        failed=2,
        provider_failure=2,
        provider_errors={"AAPL": "outage", "TSLA": "outage"},
    )
    with patch.object(watcher, "scan_gaps_with_report", return_value=report):
        watcher._run_scheduled_premarket(["AAPL", "TSLA"], provider="yahoo", now=now)
    captured = capsys.readouterr()
    assert "All tickers failed" in captured.out


def test_scheduled_premarket_unsupported_capability_error_explicit(capsys):
    """Unsupported providers produce an explicit capability error, not a traceback."""
    from tradex.data.fetcher import ProviderCapabilityError

    now = datetime(2025, 1, 15, 13, 0, tzinfo=UTC)
    with patch.object(
        watcher,
        "scan_gaps_with_report",
        side_effect=ProviderCapabilityError("schwab premarket unsupported"),
    ):
        watcher._run_scheduled_premarket(["AAPL"], provider="schwab", now=now)
    captured = capsys.readouterr()
    assert "schwab premarket unsupported" in captured.out


def test_watcher_requested_and_actual_provider_distinct_after_fallback(fresh_signal_db, capsys):
    """When the watcher falls back, requested_provider and actual_provider differ."""
    from tradex.data.fetcher import FetchAttempt

    results = _screener_results("schwab")
    attempt_log = [
        FetchAttempt(provider="yahoo", ticker="AAPL", attempts=1, retries=0, success=False),
        FetchAttempt(provider="schwab", ticker="AAPL", attempts=1, retries=0, success=True),
    ]
    report = _scan_report(
        results,
        "schwab",
        fallback_used=True,
        providers_attempted=("yahoo", "schwab"),
        attempt_log=attempt_log,
        requested_provider="yahoo",
    )

    with (
        patch.object(watcher, "screener_run_with_report", return_value=report),
        patch.object(watcher, "_check_alerts"),
    ):
        watcher.run_once(
            ["AAPL"], timeframe="intraday", provider="yahoo", fallback_order=("schwab",)
        )

    captured = capsys.readouterr()
    assert "fallback=True" in captured.out
    run = _assert_scan_audit_row()
    assert run["requested_provider"] == "yahoo"
    assert run["actual_provider"] == "schwab"
    assert run["provider"] == "schwab"


def test_start_loop_reuses_provided_settings():
    """start_loop must not call load_runtime_settings when an explicit settings object is supplied.

    The same settings object must reach the initial run_once, the scheduled
    interval callback, the daily outcome job, and the daily pre-market job.
    """
    settings = settings_from_mapping({"DATA_PROVIDER": "yahoo"})
    alert_policy = AlertPolicy(settings.alert_cooldown, settings=settings)
    mock_schedule = MagicMock()

    with (
        patch.object(watcher, "run_once") as mock_run_once,
        patch.object(watcher, "load_runtime_settings") as mock_load,
        patch.object(watcher, "schedule", mock_schedule),
        patch.object(watcher.time, "sleep", side_effect=SystemExit),
        pytest.raises(SystemExit),
    ):
        watcher.start_loop(
            ["AAPL"],
            timeframe="intraday",
            interval_minutes=5,
            min_score=30,
            provider="yahoo",
            settings=settings,
            alert_policy=alert_policy,
        )

    assert mock_load.call_count == 0
    assert mock_run_once.call_count == 1
    assert mock_run_once.call_args.kwargs["settings"] is settings

    # Interval callback forwards the same settings object.
    scheduled_callback = mock_schedule.every.return_value.minutes.do.call_args[0][0]
    with patch.object(watcher, "run_once") as mock_run_once2:
        scheduled_callback()
    assert mock_run_once2.call_args.kwargs["settings"] is settings

    # Daily scheduled jobs are wired with the same settings object.
    outcome_do = mock_schedule.every.return_value.day.at.return_value.do
    # Both jobs are scheduled via the same chained mock; collect their calls.
    calls = outcome_do.call_args_list
    assert len(calls) == 2
    for call in calls:
        assert call.kwargs.get("settings") is settings


def test_start_loop_schedules_premarket_with_yahoo_provider():
    """start_loop must schedule the 8:00 AM pre-market job with provider='yahoo' even when watcher provider is schwab."""
    settings = settings_from_mapping({"DATA_PROVIDER": "schwab"})
    alert_policy = AlertPolicy(settings.alert_cooldown, settings=settings)
    mock_schedule = MagicMock()

    with (
        patch.object(watcher, "run_once"),
        patch.object(watcher, "schedule", mock_schedule),
        patch.object(watcher.time, "sleep", side_effect=SystemExit),
        pytest.raises(SystemExit),
    ):
        watcher.start_loop(
            ["AAPL"],
            timeframe="intraday",
            interval_minutes=5,
            min_score=30,
            provider="schwab",
            settings=settings,
            alert_policy=alert_policy,
        )

    # Find the call to do(_run_scheduled_premarket, ...)
    do_calls = mock_schedule.every.return_value.day.at.return_value.do.call_args_list
    premarket_call = next(
        (c for c in do_calls if c.args and c.args[0] == watcher._run_scheduled_premarket),
        None,
    )
    assert premarket_call is not None
    assert premarket_call.kwargs.get("provider") == "yahoo"
