"""Tests for OHLCV provider error taxonomy, retry policy, and batch reporting."""

from unittest.mock import patch

import pandas as pd
import pytest

from tradex.data.fetcher import (
    FetchPolicy,
    FetchResult,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderDataUnavailableError,
    ProviderResponseError,
    ProviderTransientError,
    _classify_exception,
    _fetch_with_retry,
    fetch_multi,
    fetch_multi_report,
)


def _make_df(rows=30):
    return pd.DataFrame({
        "open": [1.0] * rows,
        "high": [1.0] * rows,
        "low": [1.0] * rows,
        "close": [1.0] * rows,
        "volume": [1000] * rows,
    })


def _fake_providers(**funcs):
    base = {
        "yahoo": funcs.get("yahoo", lambda t, f, *, settings=None: _make_df()),
        "alpaca": funcs.get("alpaca", lambda t, f, *, settings=None: _make_df()),
        "ibkr": funcs.get("ibkr", lambda t, f, *, settings=None: _make_df()),
        "schwab": funcs.get("schwab", lambda t, f, *, settings=None: _make_df()),
    }
    return base


# ─── Error classification ────────────────────────────────────────────────

def test_classify_missing_credentials_as_non_retryable():
    exc = _classify_exception(
        OSError("ALPACA_API_KEY missing"), "AAPL", "short"
    )
    assert isinstance(exc, ProviderAuthenticationError)
    assert "Missing environment configuration" in str(exc)


def test_classify_authentication_failure_as_non_retryable():
    exc = _classify_exception(
        RuntimeError("invalid refresh token"), "AAPL", "short"
    )
    assert isinstance(exc, ProviderResponseError)
    assert "Provider request failed" in str(exc)


def test_classify_unsupported_capability_as_non_retryable():
    exc = _classify_exception(
        ValueError("Unsupported timeframe for provider"), "AAPL", "short"
    )
    assert isinstance(exc, ProviderConfigurationError)
    assert "Invalid provider configuration" in str(exc)


def test_classify_transient_network_as_retryable():
    exc = _classify_exception(
        ConnectionError("connection reset"), "AAPL", "short"
    )
    assert isinstance(exc, ProviderTransientError)


def test_classify_preserves_provider_errors():
    original = ProviderTransientError("boom")
    assert _classify_exception(original, "AAPL", "short") is original


def test_classify_safe_message_no_secret():
    exc = _classify_exception(
        RuntimeError("oauth token is super-secret-token"), "AAPL", "short"
    )
    assert "super-secret-token" not in str(exc)


# ─── Retry behavior ──────────────────────────────────────────────────────

def test_zero_retries_means_one_attempt():
    calls = []
    policy = FetchPolicy(max_retries=0)

    def provider():
        calls.append(1)
        raise ProviderTransientError("network")

    result = _fetch_with_retry(provider, policy)
    assert isinstance(result, FetchResult)
    assert result.error is not None
    assert isinstance(result.error, ProviderTransientError)
    assert result.attempts == 1
    assert result.retries == 0
    assert len(calls) == 1


def test_one_retry_means_at_most_two_attempts():
    calls = []
    policy = FetchPolicy(max_retries=1)

    def provider():
        calls.append(1)
        if len(calls) == 1:
            raise ProviderTransientError("network")
        return _make_df()

    result = _fetch_with_retry(provider, policy, sleeper=lambda _: None)
    assert result.error is None
    assert result.attempts == 2
    assert result.retries == 1
    assert len(result.df) == 30
    assert len(calls) == 2


def test_transient_success_after_retry():
    calls = []
    policy = FetchPolicy(max_retries=2, backoff=lambda attempt: 0.01)

    def provider():
        calls.append(1)
        if len(calls) < 3:
            raise ProviderTransientError("network")
        return _make_df()

    result = _fetch_with_retry(provider, policy, sleeper=lambda _: None)
    assert result.error is None
    assert result.attempts == 3
    assert result.retries == 2
    assert len(result.df) == 30


def test_retry_exhaustion_raises_last_error():
    calls = []
    policy = FetchPolicy(max_retries=2)

    def provider():
        calls.append(1)
        raise ProviderTransientError("network")

    result = _fetch_with_retry(provider, policy, sleeper=lambda _: None)
    assert isinstance(result.error, ProviderTransientError)
    assert "network" in str(result.error)
    assert result.attempts == 3
    assert result.retries == 2


def test_non_retryable_failure_attempted_once():
    calls = []
    policy = FetchPolicy(max_retries=3)

    def provider():
        calls.append(1)
        raise ProviderAuthenticationError("bad creds")

    result = _fetch_with_retry(provider, policy)
    assert isinstance(result.error, ProviderAuthenticationError)
    assert result.attempts == 1
    assert result.retries == 0
    assert len(calls) == 1


def test_backoff_is_injectable():
    sleeps = []
    policy = FetchPolicy(max_retries=2, backoff=lambda attempt: 0.05 * attempt)

    def provider():
        raise ProviderTransientError("network")

    def sleeper(seconds):
        sleeps.append(seconds)

    result = _fetch_with_retry(provider, policy, sleeper=sleeper)
    assert isinstance(result.error, ProviderTransientError)
    assert sleeps == [0.05, 0.1]


def test_retry_count_does_not_exceed_maximum():
    with pytest.raises(ValueError, match="at most 3"):
        FetchPolicy(max_retries=10)


def test_retry_count_zero_means_one_attempt():
    result = _fetch_with_retry(lambda: _make_df(), FetchPolicy(max_retries=0))
    assert result.error is None
    assert result.attempts == 1
    assert result.retries == 0


# ─── Policy parsing ───────────────────────────────────────────────────────

def test_default_policy_no_retries_no_fallback():
    policy = FetchPolicy.build()
    assert policy.max_retries == 0
    assert policy.fallback_order == ()


def test_explicit_args_override_environment(monkeypatch):
    monkeypatch.setenv("OHLCV_MAX_RETRIES", "2")
    monkeypatch.setenv("OHLCV_FALLBACK_ORDER", "yahoo,schwab")
    policy = FetchPolicy.build(max_retries=1, fallback_order=["alpaca"])
    assert policy.max_retries == 1
    assert policy.fallback_order == ("alpaca",)


def test_environment_variables_parsed(monkeypatch):
    monkeypatch.setenv("OHLCV_MAX_RETRIES", "3")
    monkeypatch.setenv("OHLCV_FALLBACK_ORDER", "  schwab , alpaca ")
    policy = FetchPolicy.build()
    assert policy.max_retries == 3
    assert policy.fallback_order == ("schwab", "alpaca")


def test_invalid_provider_in_fallback_rejected():
    with pytest.raises(ValueError):
        FetchPolicy.build(fallback_order="badprovider")


def test_negative_retries_rejected():
    with pytest.raises(ValueError):
        FetchPolicy.build(max_retries=-1)


def test_fallback_removes_duplicates_and_primary():
    policy = FetchPolicy.build(fallback_order=["schwab", "yahoo", "schwab", "ibkr"])
    assert policy.fallback_for("yahoo") == ("schwab", "ibkr")
    assert policy.fallback_for("schwab") == ("yahoo", "ibkr")


def test_yahoo_is_never_added_automatically():
    policy = FetchPolicy.build()
    assert "yahoo" not in policy.fallback_order


def test_fetch_policy_direct_construction_validates_and_normalizes():
    policy = FetchPolicy(fallback_order="  Yahoo , yahoo, alpaca ")
    assert policy.fallback_order == ("yahoo", "alpaca")


def test_fetch_policy_direct_construction_rejects_invalid_provider():
    with pytest.raises(ValueError):
        FetchPolicy(fallback_order=("badprovider",))


def test_fetch_policy_direct_construction_rejects_excessive_retries():
    with pytest.raises(ValueError, match="at most 3"):
        FetchPolicy(max_retries=5)


# ─── Batch fetch report ───────────────────────────────────────────────────

def test_fetch_multi_report_complete_success():
    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers()):
        report = fetch_multi_report(["AAPL", "MSFT"], "intraday", provider="yahoo")
    assert report.total_fetched == 2
    assert report.failures == {}
    assert report.retries == 0
    assert report.actual_provider == "yahoo"
    assert all(a.success for a in report.attempt_log)


def test_fetch_multi_report_complete_failure():
    def fail(t, f, *, settings=None):
        raise ProviderTransientError("network")

    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers(yahoo=fail)):
        report = fetch_multi_report(["AAPL", "MSFT"], "intraday", provider="yahoo")
    assert report.total_fetched == 0
    assert set(report.failures.keys()) == {"AAPL", "MSFT"}
    assert report.actual_provider is None
    assert report.retries == 0
    assert len(report.attempt_log) == 2


def test_fetch_multi_report_partial_failure():
    calls = []

    def mixed(t, f, *, settings=None):
        calls.append(t)
        if t == "AAPL":
            return _make_df()
        raise ProviderTransientError("network")

    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers(yahoo=mixed)):
        report = fetch_multi_report(["AAPL", "MSFT"], "intraday", provider="yahoo")
    assert report.total_fetched == 1
    assert report.data.keys() == {"AAPL"}
    assert "MSFT" in report.failures
    assert report.actual_provider == "yahoo"
    assert len(report.attempt_log) == 2


def test_fetch_multi_report_empty_data_counts_as_unavailable():
    def empty(t, f, *, settings=None):
        return pd.DataFrame()

    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers(yahoo=empty)):
        report = fetch_multi_report(["AAPL"], "intraday", provider="yahoo")
    assert report.total_fetched == 0
    assert "AAPL" in report.failures
    assert isinstance(report.failures["AAPL"], ProviderDataUnavailableError)


def test_fetch_multi_report_no_silent_skipping():
    def fail(t, f, *, settings=None):
        raise ProviderTransientError("network")

    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers(yahoo=fail)):
        report = fetch_multi_report(["AAPL", "MSFT"], "intraday", provider="yahoo")
    assert len(report.failures) == 2


def test_fetch_multi_reports_actual_attempt_and_retry_counts():
    calls = []

    def flaky(t, f, *, settings=None):
        calls.append(t)
        if len(calls) == 1:
            raise ProviderTransientError("network")
        return _make_df()

    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers(yahoo=flaky)):
        report = fetch_multi_report(["AAPL"], "intraday", provider="yahoo", policy=FetchPolicy(max_retries=2))

    assert report.total_fetched == 1
    assert report.total_fetch_attempted == 2
    assert report.retries == 1
    assert report.attempts["AAPL"] == 2
    assert report.attempt_log[0].retries == 1


def test_fetch_multi_reports_progress_only_for_primary_provider():
    progress_calls = []
    status_calls = []

    def progress(done, total):
        progress_calls.append((done, total))

    def status(msg):
        status_calls.append(msg)

    def fail(t, f, *, settings=None):
        raise ProviderTransientError("network")

    policy = FetchPolicy(fallback_order=("schwab",), max_retries=0)
    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers(yahoo=fail, schwab=lambda t, f, *, settings=None: _make_df())):
        report = fetch_multi_report(
            ["AAPL", "MSFT"], "intraday", provider="yahoo",
            policy=policy, progress=progress, status=status,
        )

    assert report.actual_provider == "schwab"
    assert sorted(progress_calls) == [(1, 2), (2, 2)]
    assert len(status_calls) == 1
    assert "schwab" in status_calls[0]


def test_fetch_multi_report_partial_failure_progress_zero_signals():
    progress_calls = []

    def progress(done, total):
        progress_calls.append((done, total))

    def mixed(t, f, *, settings=None):
        if t == "AAPL":
            return _make_df()
        raise ProviderTransientError("network")

    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers(yahoo=mixed)):
        report = fetch_multi_report(
            ["AAPL", "MSFT"], "intraday", provider="yahoo", progress=progress,
        )

    assert report.total_fetched == 1
    assert sorted(progress_calls) == [(1, 2), (2, 2)]
    assert "MSFT" in report.failures


def test_fetch_multi_compat_returns_data_dict():
    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers()):
        data = fetch_multi(["AAPL", "MSFT"], "intraday", provider="yahoo")
    assert isinstance(data, dict)
    assert set(data.keys()) == {"AAPL", "MSFT"}
    assert all(isinstance(df, pd.DataFrame) for df in data.values())


# ─── Fallback orchestration ──────────────────────────────────────────────

def test_fallback_disabled_by_default():
    def fail(t, f, *, settings=None):
        raise ProviderTransientError("network")

    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers(yahoo=fail, schwab=lambda t, f, *, settings=None: _make_df())):
        report = fetch_multi_report(["AAPL"], "intraday", provider="yahoo")
    assert report.actual_provider is None
    assert report.fallback_used is False
    assert report.providers_attempted == ("yahoo",)


def test_explicit_fallback_after_complete_primary_failure():
    def fail(t, f, *, settings=None):
        raise ProviderTransientError("network")

    policy = FetchPolicy(fallback_order=("schwab",))
    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers(yahoo=fail, schwab=lambda t, f, *, settings=None: _make_df())):
        report = fetch_multi_report(["AAPL"], "intraday", provider="yahoo", policy=policy)
    assert report.actual_provider == "schwab"
    assert report.fallback_used is True
    assert report.providers_attempted == ("yahoo", "schwab")


def test_fallback_order_followed():
    def fail(t, f, *, settings=None):
        raise ProviderTransientError("network")

    def win(t, f, *, settings=None):
        return _make_df()

    policy = FetchPolicy(fallback_order=("alpaca", "schwab"))
    providers = _fake_providers(yahoo=fail, alpaca=fail, schwab=win)
    with patch("tradex.data.fetcher._PROVIDERS", providers):
        report = fetch_multi_report(["AAPL"], "intraday", provider="yahoo", policy=policy)
    assert report.actual_provider == "schwab"
    assert report.providers_attempted == ("yahoo", "alpaca", "schwab")


def test_fallback_stops_at_first_usable_provider():
    def fail(t, f, *, settings=None):
        raise ProviderTransientError("network")

    def win(t, f, *, settings=None):
        return _make_df()

    policy = FetchPolicy(fallback_order=("alpaca", "schwab"))
    providers = _fake_providers(yahoo=fail, alpaca=win, schwab=win)
    with patch("tradex.data.fetcher._PROVIDERS", providers):
        report = fetch_multi_report(["AAPL"], "intraday", provider="yahoo", policy=policy)
    assert report.actual_provider == "alpaca"
    assert report.providers_attempted == ("yahoo", "alpaca")


def test_partial_primary_success_prevents_fallback():
    def mixed(t, f, *, settings=None):
        if t == "AAPL":
            return _make_df()
        raise ProviderTransientError("network")

    policy = FetchPolicy(fallback_order=("schwab",))
    providers = _fake_providers(yahoo=mixed, schwab=lambda t, f, *, settings=None: _make_df())
    with patch("tradex.data.fetcher._PROVIDERS", providers):
        report = fetch_multi_report(["AAPL", "MSFT"], "intraday", provider="yahoo", policy=policy)
    assert report.actual_provider == "yahoo"
    assert report.fallback_used is False
    assert "AAPL" in report.data
    assert "MSFT" in report.failures


def test_all_provider_failures_visible():
    def fail(t, f, *, settings=None):
        raise ProviderTransientError("network")

    policy = FetchPolicy(fallback_order=("schwab",))
    providers = _fake_providers(yahoo=fail, schwab=fail)
    with patch("tradex.data.fetcher._PROVIDERS", providers):
        report = fetch_multi_report(["AAPL"], "intraday", provider="yahoo", policy=policy)
    assert report.actual_provider is None
    assert report.failures
    assert "AAPL" in report.failures
    assert len(report.attempt_log) == 2


def test_fallback_preserves_attempt_history():
    def yahoo_fail(t, f, *, settings=None):
        raise ProviderTransientError("network")

    def schwab_partial(t, f, *, settings=None):
        if t == "AAPL":
            return _make_df()
        raise ProviderTransientError("network")

    policy = FetchPolicy(fallback_order=("schwab",), max_retries=1)
    providers = _fake_providers(yahoo=yahoo_fail, schwab=schwab_partial)
    with patch("tradex.data.fetcher._PROVIDERS", providers):
        report = fetch_multi_report(["AAPL", "MSFT"], "intraday", provider="yahoo", policy=policy)

    assert report.actual_provider == "schwab"
    by_ticker_provider = {(a.ticker, a.provider): a for a in report.attempt_log}
    assert ("AAPL", "yahoo") in by_ticker_provider
    assert ("MSFT", "yahoo") in by_ticker_provider
    assert ("AAPL", "schwab") in by_ticker_provider
    assert ("MSFT", "schwab") in by_ticker_provider
    assert by_ticker_provider[("AAPL", "schwab")].success is True
    assert by_ticker_provider[("MSFT", "schwab")].success is False


def test_no_implicit_yahoo_fallback():
    def fail(t, f, *, settings=None):
        raise ProviderTransientError("network")

    providers = _fake_providers(schwab=fail)
    with patch("tradex.data.fetcher._PROVIDERS", providers):
        report = fetch_multi_report(["AAPL"], "intraday", provider="schwab")
    assert report.actual_provider is None
    assert report.providers_attempted == ("schwab",)


def test_explicit_yahoo_fallback_allowed():
    def fail(t, f, *, settings=None):
        raise ProviderTransientError("network")

    policy = FetchPolicy(fallback_order=("yahoo",))
    providers = _fake_providers(schwab=fail, yahoo=lambda t, f, *, settings=None: _make_df())
    with patch("tradex.data.fetcher._PROVIDERS", providers):
        report = fetch_multi_report(["AAPL"], "intraday", provider="schwab", policy=policy)
    assert report.actual_provider == "yahoo"
    assert report.fallback_used is True


# ─── Safe failure messages ─────────────────────────────────────────────

def test_fetch_report_failure_messages_safe():
    def fail(t, f, *, settings=None):
        raise RuntimeError("oauth token 'secret-token-123' in /secrets/schwab.json")

    with patch("tradex.data.fetcher._PROVIDERS", _fake_providers(yahoo=fail)):
        report = fetch_multi_report(["AAPL"], "intraday", provider="yahoo")
    msg = str(report.failures["AAPL"])
    assert "secret-token-123" not in msg
    assert "/secrets" not in msg
