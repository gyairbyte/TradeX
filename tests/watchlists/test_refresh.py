"""Tests for watchlist-refresh source separation."""
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from tradex.data.fetcher import ProviderCapabilityError
from tradex.watchlists import refresh


def test_resolve_market_cap_source_defaults_to_yahoo(monkeypatch):
    monkeypatch.delenv("MARKET_CAP_DATA_SOURCE", raising=False)
    assert refresh._resolve_market_cap_source(None) == "yahoo"


def test_resolve_market_cap_source_from_env(monkeypatch):
    monkeypatch.setenv("MARKET_CAP_DATA_SOURCE", "schwab")
    assert refresh._resolve_market_cap_source(None) == "schwab"


def test_fetch_market_caps_yahoo_source():
    """Yahoo market-cap source uses yfinance fast_info."""
    fake_info = Mock()
    fake_info.market_cap = 1_000_000_000
    fake_ticker = Mock()
    fake_ticker.fast_info = fake_info

    with patch("yfinance.Ticker", return_value=fake_ticker):
        caps = refresh.fetch_market_caps(["AAPL"], source="yahoo")

    assert caps.get("AAPL") == 1_000_000_000


def test_fetch_market_caps_schwab_unconfigured_raises():
    with pytest.raises(ProviderCapabilityError):
        refresh.fetch_market_caps(["AAPL"], source="schwab")


def test_fetch_market_caps_unknown_source_raises():
    with pytest.raises(ProviderCapabilityError):
        refresh.fetch_market_caps(["AAPL"], source="bloomberg")


def test_schwab_liquidity_filter_degrades_gracefully():
    """When Schwab is not configured, the liquidity filter returns all tickers and warns."""
    survivors, warnings = refresh._schwab_liquidity_filter(["AAPL", "MSFT"])
    assert survivors == {"AAPL", "MSFT"}
    assert any("Schwab not configured" in w for w in warnings)


def test_refresh_all_records_sources():
    """refresh_all returns constituent and market-cap sources in RefreshResult."""
    sp500 = pd.DataFrame({"ticker": ["AAPL", "MSFT"], "sector": ["Technology", "Technology"]})
    r1k = sp500.copy()
    caps = {"AAPL": 1_000_000_000, "MSFT": 2_000_000_000}

    with (
        patch.object(refresh, "_fetch_sp500", return_value=sp500),
        patch.object(refresh, "_fetch_dow", return_value=["AAPL"]),
        patch.object(refresh, "_fetch_ndx", return_value=["AAPL", "MSFT"]),
        patch.object(refresh, "_fetch_russell1000", return_value=r1k),
        patch.object(refresh, "fetch_market_caps", return_value=caps),
        patch.object(refresh, "_schwab_liquidity_filter", return_value=({"AAPL", "MSFT"}, [])) as mock_filter,
    ):
        result = refresh.refresh_all(top_n_per_sector=1, market_cap_source="yahoo")

    assert result.constituent_source == "wikipedia"
    assert result.market_cap_source == "yahoo"
    assert "AAPL" in result.sp100 or "MSFT" in result.sp100
    mock_filter.assert_called_once()


def test_refresh_all_market_cap_source_propagated():
    """The selected market-cap source is passed to fetch_market_caps."""
    sp500 = pd.DataFrame({"ticker": ["AAPL"], "sector": ["Technology"]})
    r1k = sp500.copy()

    with (
        patch.object(refresh, "_fetch_sp500", return_value=sp500),
        patch.object(refresh, "_fetch_dow", return_value=["AAPL"]),
        patch.object(refresh, "_fetch_ndx", return_value=["AAPL"]),
        patch.object(refresh, "_fetch_russell1000", return_value=r1k),
        patch.object(refresh, "fetch_market_caps", return_value={"AAPL": 1.0}) as mock_caps,
        patch.object(refresh, "_schwab_liquidity_filter", return_value=({"AAPL"}, [])),
    ):
        refresh.refresh_all(market_cap_source="schwab")

    _, kwargs = mock_caps.call_args
    assert kwargs["source"] == "schwab"
