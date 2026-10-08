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
    total_fetch_attempted = (
        total_fetch_attempted if total_fetch_attempted is not None else len(tickers)
    )
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
        result = engine.run(["AAPL", "MSFT"], timeframe="intraday", provider="schwab")

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
    """When filter is disabled, earnings lookup failures allow scoring while preserving earnings uncertainty."""

    def fake_score(df):
        return _make_result(70)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider or "yahoo",
            actual_provider=provider or "yahoo",
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(
            engine, "days_until_earnings", side_effect=RuntimeError("earnings lookup failed")
        ),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(["AAPL"], timeframe="intraday")

    report.validate(expected_tickers=["AAPL"])
    assert report.total_signals == 1
    assert len(report.results) == 1
    assert report.results.iloc[0]["ticker"] == "AAPL"
    assert report.results.iloc[0]["days_until_earnings"] is None
    assert report.total_fetched == 1
    assert report.failures == {}
    assert "AAPL" in report.earnings_failures
    assert "Earnings lookup failed" in str(report.earnings_failures["AAPL"])
    obs = report.observations.iloc[0]
    assert obs["status"] == "signal"
    assert obs["error_category"] == "ProviderDataUnavailableError"
    assert "Earnings lookup failed for AAPL" in obs["error_message"]


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
    """When filter is enabled, earnings lookup failure fails closed while valid zero-signal ticker fetches."""

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
        return 10

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", side_effect=earnings_days),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(
            ["AAPL", "MSFT"], timeframe="intraday", exclude_earnings_within=5
        )

    report.validate(expected_tickers=["AAPL", "MSFT"])
    assert report.results.empty
    assert report.total_fetched == 1
    assert "AAPL" in report.earnings_failures
    assert "MSFT" not in report.earnings_failures
    assert report.failures == {}
    assert report.total_fetch_eligible == 1


def test_run_with_report_mixed_earnings_failure_and_valid_zero_signals_filter_disabled():
    """When filter is disabled, earnings lookup failure does not block OHLCV fetching for either ticker."""

    def fake_score(df):
        return _make_result(30)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    def earnings_days(ticker, **kwargs):
        if ticker == "AAPL":
            raise RuntimeError("lookup failed")
        return 10

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", side_effect=earnings_days),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(
            ["AAPL", "MSFT"], timeframe="intraday", exclude_earnings_within=None
        )

    report.validate(expected_tickers=["AAPL", "MSFT"])
    assert report.results.empty
    assert report.total_fetched == 2
    assert report.total_fetch_eligible == 2
    assert report.total_below_threshold == 2
    assert "AAPL" in report.earnings_failures
    assert "MSFT" not in report.earnings_failures
    assert report.failures == {}


def test_run_with_report_mixed_earnings_failure_and_signal():
    """When filter is enabled, an earnings lookup failure fails closed while eligible ticker scores."""

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
        return 10

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", side_effect=earnings_days),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(
            ["AAPL", "MSFT"], timeframe="intraday", exclude_earnings_within=5
        )

    report.validate(expected_tickers=["AAPL", "MSFT"])
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
        patch.object(
            engine, "days_until_earnings", side_effect=lambda t, **_: 2 if t == "AAPL" else 10
        ),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(
            ["AAPL", "MSFT"], timeframe="intraday", exclude_earnings_within=5
        )

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


def test_earnings_filter_fails_closed_when_enabled_and_date_unknown():
    """When exclude_earnings_within > 0 and earnings date is unknown (None), engine fails closed."""
    fetch_called = []

    def fake_fetch_multi_report(tickers, tf, **kwargs):
        fetch_called.extend(tickers)
        return _make_fetch_report(tickers, data={})

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
    ):
        report = engine.run_with_report(
            ["AAPL"],
            timeframe="intraday",
            exclude_earnings_within=5,
        )

    assert report.total_requested == 1
    assert report.total_fetch_eligible == 0
    assert "AAPL" in report.earnings_failures
    assert fetch_called == []
    obs = report.observations.iloc[0]
    assert obs["status"] == "earnings_failure"
    assert obs["ticker"] == "AAPL"


def test_earnings_filter_passes_through_when_disabled_and_date_unknown():
    """When exclude_earnings_within is 0 or None and earnings date is unknown, engine allows scoring."""

    def fake_score(df):
        return _make_result(80)

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
        report = engine.run_with_report(
            ["AAPL"],
            timeframe="intraday",
            exclude_earnings_within=0,
        )

    assert report.total_requested == 1
    assert report.total_fetch_eligible == 1
    assert report.total_signals == 1
    report.validate(expected_tickers=["AAPL"])
    res = report.results.iloc[0]
    assert res["ticker"] == "AAPL"
    assert res["days_until_earnings"] is None


def test_earnings_filter_disabled_below_threshold_preserves_earnings_uncertainty_in_audit():
    """When filter is disabled and score is below threshold, observation preserves earnings error."""

    def fake_score(df):
        return _make_result(30)  # below 40 default min_score

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(
            engine,
            "days_until_earnings",
            side_effect=RuntimeError("Yahoo earnings rate limited"),
        ),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(
            ["AAPL"],
            timeframe="intraday",
            min_score=40,
            exclude_earnings_within=None,
        )

    report.validate(expected_tickers=["AAPL"])
    assert report.total_signals == 0
    assert report.total_below_threshold == 1
    assert report.results.empty
    obs = report.observations.iloc[0]
    assert obs["status"] == "below_threshold"
    assert obs["error_category"] == "ProviderDataUnavailableError"
    assert "Earnings lookup failed for AAPL" in obs["error_message"]
    assert "AAPL" in report.earnings_failures


def test_earnings_filter_enabled_with_typed_unavailable_exception_fails_closed():
    """When filter is enabled and days_until_earnings raises an exception, engine fails closed."""
    fetch_called = []

    def fake_fetch_multi_report(tickers, tf, **kwargs):
        fetch_called.extend(tickers)
        return _make_fetch_report(tickers, data={})

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(
            engine,
            "days_until_earnings",
            side_effect=RuntimeError("Earnings provider unreachable"),
        ),
    ):
        report = engine.run_with_report(
            ["AAPL"],
            timeframe="intraday",
            exclude_earnings_within=5,
        )

    report.validate(expected_tickers=["AAPL"])
    assert report.total_requested == 1
    assert report.total_fetch_eligible == 0
    assert "AAPL" in report.earnings_failures
    assert fetch_called == []
    obs = report.observations.iloc[0]
    assert obs["status"] == "earnings_failure"
    assert obs["ticker"] == "AAPL"


def test_earnings_filter_enabled_with_known_dates_in_and_out_of_window():
    """Known dates inside window are excluded; outside window are fetched and scored."""

    def fake_score(df):
        return _make_result(85)

    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 31) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    def fake_days(ticker, **kwargs):
        if ticker == "IN_WINDOW":
            return 3
        if ticker == "OUT_WINDOW":
            return 15
        return None

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", side_effect=fake_days),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        report = engine.run_with_report(
            ["IN_WINDOW", "OUT_WINDOW"],
            timeframe="intraday",
            exclude_earnings_within=5,
        )

    report.validate(expected_tickers=["IN_WINDOW", "OUT_WINDOW"])
    assert report.total_requested == 2
    assert report.total_earnings_excluded == 1
    assert report.total_fetch_eligible == 1
    assert report.total_signals == 1
    assert report.results["ticker"].tolist() == ["OUT_WINDOW"]
    assert report.results.iloc[0]["days_until_earnings"] == 15


# ── LONG MVP Screener Engine Tests ───────────────────────────────────────────


def _make_long_result(
    score: int = 75,
    state: str | None = "ENTER NOW",
    qualified: bool = True,
    primary_setup: str | None = "breakout_expansion",
) -> dict:
    return {
        "strategy_id": "long_mvp",
        "strategy_version": "v1",
        "score": score,
        "primary_setup": primary_setup,
        "matched_setups": [primary_setup] if primary_setup else [],
        "state": state,
        "component_scores": {
            "trend_quality": 24,
            "momentum_quality": 20,
            "setup_quality": 16,
            "movement_capacity": 10,
            "participation": 5,
        },
        "reasons": ["Price > EMA20 > EMA50 > EMA200", "Breakout above prior 20-day high"],
        "trigger": "Close above prior 20-session high ($150.00) with volume >= 1.3x",
        "invalidation": "Close below EMA50 ($130.00)",
        "last_close": 155.0,
        "volume_ratio": 1.6,
        "rsi": 62.0,
        "atr_pct": 0.025,
        "return_5": 0.02,
        "return_20": 0.08,
        "return_60": 0.18,
        "qualified": qualified,
    }


def test_long_screener_requires_220_bars():
    """Long timeframe requires at least 220 bars; <220 marks INSUFFICIENT_DATA."""
    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        # Return 219 bars for AAPL, 225 bars for MSFT
        return _make_fetch_report(
            tickers,
            data={
                "AAPL": pd.DataFrame([0] * 219),
                "MSFT": pd.DataFrame([0] * 225),
            },
            provider=provider,
            actual_provider=provider,
        )

    def fake_score(df):
        return _make_long_result(80)

    with (
        patch.object(engine, "fetch_multi_report", side_effect=fake_fetch_multi_report),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"long": (fake_score, "long")}),
    ):
        report = engine.run_with_report(["AAPL", "MSFT"], timeframe="long")

    report.validate(expected_tickers=["AAPL", "MSFT"])
    assert report.total_requested == 2
    assert report.total_insufficient_data == 1
    assert report.total_signals == 1
    assert report.results["ticker"].tolist() == ["MSFT"]
    aapl_obs = report.observations[report.observations["ticker"] == "AAPL"].iloc[0]
    assert aapl_obs["status"] == "insufficient_data"


def test_long_signal_qualification_and_min_score():
    """Score < 60 cannot surface even if caller min_score is lower; caller min_score > 60 filters further."""
    def fake_fetch_multi_report(tickers, tf, provider=None, **kwargs):
        return _make_fetch_report(
            tickers,
            data={t: pd.DataFrame([0] * 225) for t in tickers},
            provider=provider,
            actual_provider=provider,
        )

    # AAA has score 55 (qualified but below 60 -> state None)
    # BBB has score 65 (QUALIFIED WAITLIST)
    # CCC has score 80 (ENTER NOW)
    def fake_score(df):
        # We can map by df or by mock side effect
        pass

    results_map = {
        "AAA": _make_long_result(score=55, state=None, qualified=False),
        "BBB": _make_long_result(score=65, state="QUALIFIED WAITLIST", qualified=True),
        "CCC": _make_long_result(score=80, state="ENTER NOW", qualified=True),
    }

    def mock_scorer(df):
        # Return based on which ticker this df belongs to
        ticker = getattr(df, "_ticker", "BBB")
        return results_map[ticker]

    def patched_fetch(tickers, tf, provider=None, **kwargs):
        data = {}
        for t in tickers:
            df = pd.DataFrame([0] * 225)
            df._ticker = t
            data[t] = df
        return _make_fetch_report(tickers, data=data, provider=provider, actual_provider=provider)

    # Case 1: min_score = 30 -> AAA (55) still NOT surfaced, only BBB and CCC surfaced
    with (
        patch.object(engine, "fetch_multi_report", side_effect=patched_fetch),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"long": (mock_scorer, "long")}),
    ):
        report1 = engine.run_with_report(["AAA", "BBB", "CCC"], timeframe="long", min_score=30)

    report1.validate(expected_tickers=["AAA", "BBB", "CCC"])
    assert report1.total_signals == 2
    assert "AAA" not in report1.results["ticker"].tolist()
    assert set(report1.results["ticker"].tolist()) == {"BBB", "CCC"}

    # Case 2: min_score = 75 -> BBB (65) filtered out, only CCC (80) surfaced
    with (
        patch.object(engine, "fetch_multi_report", side_effect=patched_fetch),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"long": (mock_scorer, "long")}),
    ):
        report2 = engine.run_with_report(["AAA", "BBB", "CCC"], timeframe="long", min_score=75)

    report2.validate(expected_tickers=["AAA", "BBB", "CCC"])
    assert report2.total_signals == 1
    assert report2.results["ticker"].tolist() == ["CCC"]
    # BBB is marked below_threshold
    bbb_obs = report2.observations[report2.observations["ticker"] == "BBB"].iloc[0]
    assert bbb_obs["status"] == "below_threshold"
    # State remains "QUALIFIED WAITLIST" on the observation
    assert bbb_obs["state"] == "QUALIFIED WAITLIST"


def test_long_ranking_order():
    """Long results rank: ENTER NOW -> ARMED -> QUALIFIED WAITLIST, then score desc, then ticker asc."""
    tickers = ["T_WAIT_80", "T_ENTER_75", "T_ARMED_75", "T_ENTER_90", "T_ARMED_70"]
    results_map = {
        "T_WAIT_80": _make_long_result(80, state="QUALIFIED WAITLIST"),
        "T_ENTER_75": _make_long_result(75, state="ENTER NOW"),
        "T_ARMED_75": _make_long_result(75, state="ARMED"),
        "T_ENTER_90": _make_long_result(90, state="ENTER NOW"),
        "T_ARMED_70": _make_long_result(70, state="ARMED"),
    }

    def mock_scorer(df):
        return results_map[df._ticker]

    def patched_fetch(tickers, tf, provider=None, **kwargs):
        data = {}
        for t in tickers:
            df = pd.DataFrame([0] * 225)
            df._ticker = t
            data[t] = df
        return _make_fetch_report(tickers, data=data, provider=provider, actual_provider=provider)

    with (
        patch.object(engine, "fetch_multi_report", side_effect=patched_fetch),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"long": (mock_scorer, "long")}),
    ):
        report = engine.run_with_report(tickers, timeframe="long", min_score=60)

    report.validate(expected_tickers=tickers)
    # Expected ranking:
    # 1. ENTER NOW (score 90: T_ENTER_90)
    # 2. ENTER NOW (score 75: T_ENTER_75)
    # 3. ARMED (score 75: T_ARMED_75)
    # 4. ARMED (score 70: T_ARMED_70)
    # 5. QUALIFIED WAITLIST (score 80: T_WAIT_80)
    expected_order = ["T_ENTER_90", "T_ENTER_75", "T_ARMED_75", "T_ARMED_70", "T_WAIT_80"]
    assert report.results["ticker"].tolist() == expected_order


def test_long_focus_caps_helper_does_not_truncate_telemetry():
    """Display caps (7 / 12 / 12, max 31) cap the display list without truncating ScanReport."""
    # Build 10 ENTER NOW, 15 ARMED, 15 WAITLIST (total 40 signals)
    enter_tickers = [f"E_{i:02d}" for i in range(10)]
    armed_tickers = [f"A_{i:02d}" for i in range(15)]
    wait_tickers = [f"W_{i:02d}" for i in range(15)]
    all_tickers = enter_tickers + armed_tickers + wait_tickers

    results_map = {}
    for t in enter_tickers:
        results_map[t] = _make_long_result(85, state="ENTER NOW")
    for t in armed_tickers:
        results_map[t] = _make_long_result(72, state="ARMED")
    for t in wait_tickers:
        results_map[t] = _make_long_result(65, state="QUALIFIED WAITLIST")

    def mock_scorer(df):
        return results_map[df._ticker]

    def patched_fetch(tickers, tf, provider=None, **kwargs):
        data = {}
        for t in tickers:
            df = pd.DataFrame([0] * 225)
            df._ticker = t
            data[t] = df
        return _make_fetch_report(tickers, data=data, provider=provider, actual_provider=provider)

    with (
        patch.object(engine, "fetch_multi_report", side_effect=patched_fetch),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"long": (mock_scorer, "long")}),
    ):
        report = engine.run_with_report(all_tickers, timeframe="long", min_score=60)

    report.validate(expected_tickers=all_tickers)
    # Underlying report preserves all 40 signals
    assert len(report.results) == 40
    assert report.total_signals == 40
    assert len(report.observations) == 40

    # Display helper caps at 7 ENTER NOW, 12 ARMED, 12 WAITLIST = 31 total
    focus = engine.build_long_focus_list(report.results)
    assert len(focus) == 31
    assert len(focus[focus["state"] == "ENTER NOW"]) == 7
    assert len(focus[focus["state"] == "ARMED"]) == 12
    assert len(focus[focus["state"] == "QUALIFIED WAITLIST"]) == 12
