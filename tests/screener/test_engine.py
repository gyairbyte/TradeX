"""Tests for the screener engine."""
from unittest.mock import patch

import pandas as pd

from tradex.data.fetcher import FetchAttempt, FetchReport, ProviderTransientError
from tradex.screener import engine


def _make_result(score: int = 80):
    return {
        "score": score,
        "last_close": 100.0,
        "volume_ratio": 2.0,
        "rsi": 60.0,
        "reasons": ["momentum"],
    }


def _make_fetch_report(
    tickers,
    data=None,
    provider="yahoo",
    actual_provider=None,
    fallback_used=False,
    failures=None,
    providers_attempted=None,
    retries=0,
    total_fetch_attempted=None,
    attempt_log=None,
):
    data = data or {}
    failures = failures or {}
    actual = actual_provider or provider
    providers = providers_attempted or (actual,)
    total_fetch_attempted = total_fetch_attempted if total_fetch_attempted is not None else len(tickers)
    return FetchReport(
        data=data,
        requested_provider=provider,
        actual_provider=actual,
        fallback_used=fallback_used,
        providers_attempted=providers,
        failures=failures,
        attempts={t: 1 for t in tickers},
        total_requested=len(tickers),
        total_fetched=len(data),
        total_fetch_attempted=total_fetch_attempted,
        retries=retries,
        attempt_log=attempt_log or [],
    )


def test_engine_reports_provider_failures():
    """When every fetch fails, run_with_report exposes an error summary, not just an empty DataFrame."""
    failures = {
        "AAPL": ProviderTransientError("network"),
        "MSFT": ProviderTransientError("network"),
    }

    def fake_fetch_multi_report(*args, **kwargs):
        return _make_fetch_report(["AAPL", "MSFT"], provider="yahoo", failures=failures)

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
    ):
        report = engine.run_with_report(["AAPL", "MSFT"], timeframe="intraday")

    assert report.results.empty
    assert report.total_requested == 2
    assert report.total_signals == 0
    assert report.total_fetched == 0
    assert "AAPL" in report.failures
    assert "MSFT" in report.failures


def test_engine_propagates_schwab_provider_to_fetch():
    """An explicit provider argument must reach the batch fetch call."""
    captured = {}

    def fake_score(df):
        return _make_result(85)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        captured["provider"] = provider
        captured["tickers"] = tickers
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        result = engine.run(
            ["AAPL", "MSFT"], timeframe="intraday", provider="schwab"
        )

    assert captured["provider"] == "schwab"
    assert captured["tickers"] == ["AAPL", "MSFT"]
    assert "AAPL" in result["ticker"].values
    assert "MSFT" in result["ticker"].values


def test_engine_propagates_yahoo_provider_to_fetch():
    """An explicit yahoo provider must be forwarded unchanged."""
    captured = {}

    def fake_score(df):
        return _make_result(70)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        captured["provider"] = provider
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        engine.run(["TSLA"], timeframe="intraday", provider="yahoo")

    assert captured["provider"] == "yahoo"


def test_engine_resolves_default_provider_before_fetch(monkeypatch):
    """Without an explicit provider, the resolved default provider is passed to fetch."""
    monkeypatch.setenv("DATA_PROVIDER", "schwab")
    captured = {}

    def fake_score(df):
        return _make_result(60)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        captured["provider"] = provider
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        engine.run(["NVDA"], timeframe="intraday")

    assert captured["provider"] == "schwab"


def test_engine_result_includes_effective_provider():
    """A successful scan row must include the resolved OHLCV provider."""

    def fake_score(df):
        return _make_result(70)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        result = engine.run(["AAPL"], timeframe="intraday", provider="schwab")

    assert "provider" in result.columns
    assert result["provider"].tolist() == ["schwab"]


def test_engine_empty_result_schema_includes_provider():
    """Even an empty result must expose the provider column."""

    def fake_score(df):
        return _make_result(20)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(tickers, provider=provider, actual_provider=provider)

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        result = engine.run(["AAPL"], timeframe="intraday", provider="yahoo", min_score=40)

    assert result.empty
    assert "provider" in result.columns


def test_engine_single_provider_for_all_rows():
    """All rows from one scan must share the same effective provider."""

    def fake_score(df):
        return _make_result(60)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        result = engine.run(["A", "B", "C"], timeframe="intraday", provider="alpaca")

    assert result["provider"].unique().tolist() == ["alpaca"]


def test_engine_run_returns_dataframe():
    """The compatibility ``run()`` wrapper still returns a DataFrame."""

    def fake_score(df):
        return _make_result(60)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        result = engine.run(["AAPL"], timeframe="intraday")

    assert isinstance(result, pd.DataFrame)
    assert "provider" in result.columns


def test_run_with_report_valid_zero_signals():
    """A successful data fetch with no qualifying signals is distinguishable from a failure."""

    def fake_score(df):
        return _make_result(20)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL"], timeframe="intraday", min_score=40)

    assert report.results.empty
    assert report.total_fetched == 1
    assert report.total_signals == 0
    assert report.failures == {}


def test_run_with_report_partial_fetch_failure():
    """Partial fetch failure keeps successful results and reports failed symbols."""

    def fake_score(df):
        return _make_result(70)

    failures = {"MSFT": ProviderTransientError("network")}

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={"AAPL": pd.DataFrame([0] * 31)},
            provider=provider,
            actual_provider=provider,
            failures=failures,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL", "MSFT"], timeframe="intraday")

    assert report.total_signals == 1
    assert report.results["ticker"].tolist() == ["AAPL"]
    assert "MSFT" in report.failures


def test_run_with_report_insufficient_data_different_from_provider_failure():
    """A fetch returning too few rows is reported as insufficient data, not a provider outage."""

    def fake_score(df):
        return _make_result(70)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={"AAPL": pd.DataFrame([0] * 5)},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL"], timeframe="intraday")

    assert report.results.empty
    assert report.total_insufficient_data == 1
    assert report.total_fetched == 1
    assert "AAPL" in report.failures
    assert "Insufficient" in str(report.failures["AAPL"])


def test_run_with_report_scoring_error_different_from_fetch_failure():
    """A scoring error is reported separately from a fetch failure."""

    def fake_score(df):
        raise RuntimeError("scorer bug")

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={"AAPL": pd.DataFrame([0] * 31)},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL"], timeframe="intraday")

    assert report.results.empty
    assert report.total_fetched == 1
    assert report.total_signals == 0
    assert "AAPL" in report.failures
    assert "Scoring failed" in str(report.failures["AAPL"])


def test_run_with_report_earnings_exclusion_different_from_provider_failure():
    """An earnings exclusion is counted separately and not as a provider failure."""

    def fake_score(df):
        return _make_result(70)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(tickers, provider=provider, actual_provider=provider)

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=2),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL"], timeframe="intraday", exclude_earnings_within=5)

    assert report.results.empty
    assert report.total_earnings_excluded == 1
    assert report.total_fetched == 0
    assert "AAPL" not in report.failures


def test_run_with_report_fallback_provider_in_rows_and_report():
    """When fallback is used, every row and the report reflect the actual provider."""

    def fake_score(df):
        return _make_result(70)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider="schwab",
            actual_provider="yahoo",
            fallback_used=True,
            providers_attempted=("schwab", "yahoo"),
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL"], timeframe="intraday", provider="schwab")

    assert report.requested_provider == "schwab"
    assert report.actual_provider == "yahoo"
    assert report.fallback_used is True
    assert report.results["provider"].tolist() == ["yahoo"]


def test_run_with_report_no_mixed_provider_results():
    """A scan cannot produce rows with different providers."""

    def fake_score(df):
        return _make_result(70)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider="schwab",
            actual_provider="yahoo",
            fallback_used=True,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["A", "B"], timeframe="intraday", provider="schwab")

    assert report.results["provider"].unique().tolist() == ["yahoo"]


def test_run_with_report_preserves_days_until_earnings():
    """Successful rows retain the per-ticker days_until_earnings value."""

    def fake_score(df):
        return _make_result(70)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=7),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL"], timeframe="intraday")

    assert report.results["days_until_earnings"].tolist() == [7]


def test_run_with_report_earnings_source_failure_not_provider_outage():
    """Earnings lookup failures are tracked separately, not as OHLCV provider failures."""

    def fake_score(df):
        return _make_result(70)

    def fake_fetch_multi_report(*args, **kwargs):
        return _make_fetch_report(["AAPL"], provider="yahoo")

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", side_effect=RuntimeError("earnings lookup failed")),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL"], timeframe="intraday")

    assert report.results.empty
    assert report.total_fetched == 0
    assert report.failures == {}
    assert "AAPL" in report.earnings_failures
    assert "Earnings lookup failed" in str(report.earnings_failures["AAPL"])


def test_run_with_report_all_earnings_excluded_is_normal_zero_result():
    """When all tickers are validly earnings-excluded, report a normal zero-result state."""

    def fake_score(df):
        return _make_result(70)

    def fake_fetch_multi_report(*args, **kwargs):
        return _make_fetch_report(["AAPL"], provider="yahoo")

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=2),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL"], timeframe="intraday", exclude_earnings_within=5)

    assert report.results.empty
    assert report.total_earnings_excluded == 1
    assert report.total_fetched == 0
    assert report.failures == {}
    assert report.earnings_failures == {}


def test_run_with_report_partial_failure_zero_signals():
    """Partial fetch failure is surfaced even when no ticker meets the score threshold."""

    def fake_score(df):
        return _make_result(30)

    failures = {"MSFT": ProviderTransientError("network")}

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={"AAPL": pd.DataFrame([0] * 31)},
            provider=provider,
            actual_provider=provider,
            failures=failures,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL", "MSFT"], timeframe="intraday")

    assert report.results.empty
    assert report.total_fetched == 1
    assert report.total_below_threshold == 1
    assert "MSFT" in report.failures
    assert report.failures["MSFT"] is failures["MSFT"]


def test_run_with_report_mixed_earnings_failure_and_valid_zero_signals():
    """An earnings lookup failure is surfaced independently of a valid zero-signal ticker."""

    def fake_score(df):
        return _make_result(30)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={"MSFT": pd.DataFrame([0] * 31)},
            provider=provider,
            actual_provider=provider,
        )

    def earnings_days(ticker, **kwargs):
        if ticker == "AAPL":
            raise RuntimeError("lookup failed")

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", side_effect=earnings_days),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL", "MSFT"], timeframe="intraday")

    assert report.results.empty
    assert report.total_fetched == 1
    assert "AAPL" in report.earnings_failures
    assert "MSFT" not in report.earnings_failures
    assert report.failures == {}
    assert report.total_fetch_eligible == 1


def test_run_with_report_mixed_earnings_failure_and_signal():
    """An earnings lookup failure is surfaced alongside a successful signal."""

    def fake_score(df):
        return _make_result(70)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={"MSFT": pd.DataFrame([0] * 31)},
            provider=provider,
            actual_provider=provider,
        )

    def earnings_days(ticker, **kwargs):
        if ticker == "AAPL":
            raise RuntimeError("lookup failed")

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", side_effect=earnings_days),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL", "MSFT"], timeframe="intraday")

    assert report.total_signals == 1
    assert report.results["ticker"].tolist() == ["MSFT"]
    assert "AAPL" in report.earnings_failures
    assert report.failures == {}
    assert report.total_fetch_eligible == 1


def test_run_with_report_earnings_exclusion_plus_fetch_failure():
    """An excluded ticker and a fetch failure are counted in their respective stages."""

    def fake_score(df):
        return _make_result(70)

    fetch_failures = {"MSFT": ProviderTransientError("network")}

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={},
            provider=provider,
            actual_provider=provider,
            failures=fetch_failures,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", side_effect=lambda t, **_: 2 if t == "AAPL" else None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL", "MSFT"], timeframe="intraday", exclude_earnings_within=5)

    assert report.results.empty
    assert report.total_earnings_excluded == 1
    assert report.total_fetched == 0
    assert report.total_fetch_eligible == 1
    assert "MSFT" in report.fetch_failures
    assert report.failures == report.fetch_failures


def test_run_with_report_propagates_retry_and_attempt_history():
    """FetchReport retry/attempt/fallback history is carried through ScanReport."""

    def fake_score(df):
        return _make_result(70)

    attempt_log = [
        FetchAttempt(provider="yahoo", ticker="AAPL", attempts=1, retries=0, success=False),
        FetchAttempt(provider="schwab", ticker="AAPL", attempts=2, retries=1, success=True),
    ]

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={"AAPL": pd.DataFrame([0] * 31)},
            provider="yahoo",
            actual_provider="schwab",
            fallback_used=True,
            providers_attempted=("yahoo", "schwab"),
            retries=1,
            total_fetch_attempted=3,
            attempt_log=attempt_log,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL"], timeframe="intraday")

    assert report.total_retries == 1
    assert report.total_fetch_attempted == 3
    assert report.attempt_log == attempt_log
    assert report.fallback_used is True
    assert report.actual_provider == "schwab"


def test_run_with_report_canonicalizes_non_round_scored_metrics():
    """Scored metrics with many decimals are canonicalized once and reused for both results and signal observations."""

    def fake_score(df):
        return {
            "score": 75,
            "last_close": 100.12345678,
            "volume_ratio": 2.345678,
            "rsi": 60.6789,
            "reasons": ["volume", "momentum"],
        }

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL"], timeframe="intraday", min_score=50)

    report.validate(expected_tickers=["AAPL"])
    assert report.total_signals == 1
    obs = report.observations.iloc[0]
    res = report.results.iloc[0]
    assert res["last_close"] == 100.1235
    assert res["volume_ratio"] == 2.35
    assert res["rsi"] == 60.7
    assert obs["last_close"] == res["last_close"]
    assert obs["volume_ratio"] == res["volume_ratio"]
    assert obs["rsi"] == res["rsi"]
