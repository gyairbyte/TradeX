"""Tests for the central OHLCV provider fetcher."""
import pytest

from tradex.data.fetcher import fetch, resolve_provider


def test_resolve_provider_explicit():
    assert resolve_provider("yahoo") == "yahoo"
    assert resolve_provider("schwab") == "schwab"
    assert resolve_provider("alpaca") == "alpaca"
    assert resolve_provider("ibkr") == "ibkr"


def test_resolve_provider_normalizes_case_and_whitespace():
    assert resolve_provider("  Schwab  ") == "schwab"
    assert resolve_provider("YAHOO") == "yahoo"
    assert resolve_provider("  Alpaca ") == "alpaca"


def test_resolve_provider_defaults_to_env(monkeypatch):
    monkeypatch.setattr("tradex.data.fetcher.DEFAULT_PROVIDER", "schwab")
    assert resolve_provider() == "schwab"


def test_resolve_provider_defaults_to_yahoo_when_unset(monkeypatch):
    monkeypatch.setattr("tradex.data.fetcher.DEFAULT_PROVIDER", "yahoo")
    assert resolve_provider() == "yahoo"


def test_resolve_provider_rejects_invalid_value():
    with pytest.raises(ValueError):
        resolve_provider("badprovider")


def test_resolve_provider_rejects_empty_string():
    with pytest.raises(ValueError):
        resolve_provider("")


def test_fetch_uses_resolved_provider(monkeypatch):
    """fetch() should call the correct provider implementation."""
    captured = {}

    def fake_fetch(ticker, timeframe):
        captured["ticker"] = ticker
        captured["timeframe"] = timeframe
        return "placeholder"

    monkeypatch.setattr("tradex.data.fetcher._PROVIDERS", {"schwab": fake_fetch})
    monkeypatch.setattr("tradex.data.fetcher.TIMEFRAMES", {"short": {"period": "60d", "interval": "1d"}})

    result = fetch("AAPL", "short", provider="schwab")

    assert captured["ticker"] == "AAPL"
    assert captured["timeframe"] == "short"
    assert result == "placeholder"


def test_fetch_invalid_provider_raises():
    with pytest.raises(ValueError):
        fetch("AAPL", "short", provider="notaprovider")
