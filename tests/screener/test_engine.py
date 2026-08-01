"""Tests for the screener engine."""
from unittest.mock import patch

import pandas as pd

from tradex.data.fetcher import FetchReport, ProviderTransientError
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
):
    data = data or {}
    failures = failures or {}
    actual = actual_provider or provider
    providers = providers_attempted or (actual,)
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
        total_fetch_attempted=len(tickers),
        retries=0,
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
    monkeypatch.setattr("tradex.data.fetcher.DEFAULT_PROVIDER", "schwab")
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
