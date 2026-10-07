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
    monkeypatch.setenv("DATA_PROVIDER", "yahoo")
    assert resolve_provider() == "yahoo"


def test_resolve_provider_defaults_to_schwab_when_unset(monkeypatch):
    monkeypatch.delenv("DATA_PROVIDER", raising=False)
    assert resolve_provider() == "schwab"


def test_resolve_provider_rejects_invalid_value():
    with pytest.raises(ValueError):
        resolve_provider("badprovider")


def test_resolve_provider_rejects_empty_string():
    with pytest.raises(ValueError):
        resolve_provider("")


def test_fetch_uses_resolved_provider(monkeypatch):
    """fetch() should call the correct provider implementation."""
    captured = {}

    def fake_fetch(ticker, timeframe, *, settings=None):
        captured["ticker"] = ticker
        captured["timeframe"] = timeframe
        return "placeholder"

    monkeypatch.setattr("tradex.data.fetcher._PROVIDERS", {"schwab": fake_fetch})
    monkeypatch.setattr(
        "tradex.data.fetcher.TIMEFRAMES", {"short": {"period": "60d", "interval": "1d"}}
    )

    result = fetch("AAPL", "short", provider="schwab")

    assert captured["ticker"] == "AAPL"
    assert captured["timeframe"] == "short"
    assert result == "placeholder"


def test_fetch_invalid_provider_raises():
    with pytest.raises(ValueError):
        fetch("AAPL", "short", provider="notaprovider")


def test_long_timeframe_is_daily_across_all_providers():
    """All supported providers must configure daily bars for long timeframe (LONG-MVP-002)."""
    from tradex.data.fetcher import (
        TIMEFRAMES,
        _ALPACA_INTERVAL_MAP,
        _ALPACA_LIMIT_MAP,
        _IBKR_DURATION_MAP,
        _SCHWAB_TIMEFRAMES,
    )

    # 1. Yahoo preset
    assert TIMEFRAMES["long"]["period"] == "2y"
    assert TIMEFRAMES["long"]["interval"] == "1d"

    # 2. Alpaca
    assert _ALPACA_INTERVAL_MAP["long"] == "1Day"
    assert _ALPACA_LIMIT_MAP["long"] >= 504  # ~2 years of trading days (520)

    # 3. IBKR
    duration, bar_size = _IBKR_DURATION_MAP["long"]
    assert duration == "2 Y"
    assert bar_size == "1 day"

    # 4. Schwab
    method_name, lookback = _SCHWAB_TIMEFRAMES["long"]
    assert method_name == "get_price_history_every_day"
    assert lookback.days >= 700  # 730 days (~2 years)
