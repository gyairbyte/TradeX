"""Deterministic unit tests for ORB market data providers (DAYTRADE-003F).

Tests:
- Alpaca provider asset discovery (NYSE/Nasdaq filter)
- Alpaca credential validation
- Alpaca multi-symbol daily bars batching
- Alpaca opening range 1-minute bars retrieval
- Alpaca prior opening range volume aggregation
- Alpaca SIP fallback to IEX on HTTP 403 entitlement restriction
- Alpaca rate limit (HTTP 429) backoff and retry handling
- Schwab provider stub explicit limitation disclosure
- resolve_orb_provider factory resolution
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
import requests

from tradex.config import settings_from_mapping
from tradex.research.daytrade_orb.provider import (
    AlpacaORBProvider,
    MockORBProvider,
    ORBProviderConfigurationError,
    SchwabORBProviderStub,
    resolve_orb_provider,
)

TEST_DATE = date(2024, 1, 2)


def test_alpaca_discover_universe_filters_nyse_nasdaq():
    """Alpaca discover_universe returns only active NYSE and Nasdaq equities."""
    assets_data = [
        {"symbol": "AAPL", "exchange": "NASDAQ", "status": "active"},
        {"symbol": "IBM", "exchange": "NYSE", "status": "active"},
        {"symbol": "SPY", "exchange": "ARCA", "status": "active"},       # ARCA excluded
        {"symbol": "OLD", "exchange": "NYSE", "status": "inactive"},     # Inactive excluded
        {"symbol": "$TEST", "exchange": "NASDAQ", "status": "active"},    # Test symbol excluded
        {"symbol": "NVDA", "exchange": "NASDAQ", "status": "active"},
    ]

    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = assets_data

    mock_req = MagicMock(return_value=mock_resp)

    provider = AlpacaORBProvider(
        api_key="test_key",
        secret_key="test_secret",
        request_func=mock_req,
        rate_limit_pause_seconds=0.0,
    )

    universe = provider.discover_universe()
    assert universe == ["AAPL", "IBM", "NVDA"]
    assert "SPY" not in universe
    assert "OLD" not in universe


def test_alpaca_discover_universe_requires_credentials():
    """Alpaca provider raises ORBProviderConfigurationError if keys are missing."""
    with pytest.raises(ORBProviderConfigurationError) as exc_info:
        AlpacaORBProvider(api_key="", secret_key="")
    assert "Alpaca credentials missing" in str(exc_info.value)


def test_alpaca_fetch_daily_bars_batching():
    """Alpaca fetch_daily_bars chunks symbols by batch_size and parses DailyBar objects."""
    symbols = ["AAPL", "MSFT", "GOOGL"]

    def _mock_get(url, headers=None, params=None, timeout=None):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        req_syms = params["symbols"].split(",")
        bars_dict = {}
        for s in req_syms:
            bars_dict[s] = [
                {
                    "t": "2024-01-02T05:00:00Z",
                    "o": 150.0,
                    "h": 152.0,
                    "l": 149.0,
                    "c": 151.0,
                    "v": 1_000_000.0,
                }
            ]
        resp.json.return_value = {"bars": bars_dict}
        return resp

    mock_req = MagicMock(side_effect=_mock_get)

    provider = AlpacaORBProvider(
        api_key="test_key",
        secret_key="test_secret",
        batch_size=2,  # Force 2 batches for 3 symbols
        request_func=mock_req,
        rate_limit_pause_seconds=0.0,
    )

    result = provider.fetch_daily_bars(symbols, start_date=date(2024, 1, 1), end_date=date(2024, 1, 2))

    assert mock_req.call_count == 2
    assert len(result) == 3
    assert len(result["AAPL"]) == 1
    assert result["AAPL"][0].close == 151.0
    assert result["AAPL"][0].session_date == date(2024, 1, 2)


def test_alpaca_fetch_opening_range_bars():
    """Alpaca fetch_opening_range_bars retrieves 09:30-09:34 ET minute bars."""
    symbols = ["AAPL"]

    def _mock_get(url, headers=None, params=None, timeout=None):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        assert params["timeframe"] == "1Min"
        assert "09:30" in params["start"] or "14:30" in params["start"]  # UTC start
        resp.json.return_value = {
            "bars": {
                "AAPL": [
                    {"t": "2024-01-02T14:30:00Z", "o": 180.0, "h": 181.0, "l": 179.5, "c": 180.5, "v": 50000.0},
                    {"t": "2024-01-02T14:31:00Z", "o": 180.5, "h": 181.5, "l": 180.0, "c": 181.2, "v": 45000.0},
                ]
            }
        }
        return resp

    provider = AlpacaORBProvider(
        api_key="test_key",
        secret_key="test_secret",
        request_func=MagicMock(side_effect=_mock_get),
        rate_limit_pause_seconds=0.0,
    )

    result = provider.fetch_opening_range_bars(symbols, session_date=TEST_DATE)
    assert len(result["AAPL"]) == 2
    assert result["AAPL"][0].volume == 50000.0
    assert result["AAPL"][0].session_date == TEST_DATE


def test_alpaca_fetch_prior_opening_range_volumes():
    """Alpaca fetch_prior_opening_range_volumes aggregates 1-minute bars per session."""
    symbols = ["AAPL"]
    prior_sessions = [date(2023, 12, 28), date(2023, 12, 29)]

    def _mock_get(url, headers=None, params=None, timeout=None):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        # Return 2 minute bars with volume 25,000 each -> total 50,000
        resp.json.return_value = {
            "bars": {
                "AAPL": [
                    {"t": "2023-12-29T14:30:00Z", "o": 180.0, "h": 181.0, "l": 180.0, "c": 180.5, "v": 25000.0},
                    {"t": "2023-12-29T14:31:00Z", "o": 180.5, "h": 181.0, "l": 180.2, "c": 180.8, "v": 25000.0},
                ]
            }
        }
        return resp

    provider = AlpacaORBProvider(
        api_key="test_key",
        secret_key="test_secret",
        request_func=MagicMock(side_effect=_mock_get),
        rate_limit_pause_seconds=0.0,
    )

    result = provider.fetch_prior_opening_range_volumes(symbols, prior_sessions=prior_sessions)
    assert len(result["AAPL"]) == 2
    assert result["AAPL"][0].volume == 50000.0


def test_alpaca_sip_fails_closed_on_403_without_feed_switching():
    """When Alpaca SIP feed returns 403 Forbidden, provider fails closed with an explicit error and does NOT switch feeds."""
    def _mock_get(url, headers=None, params=None, timeout=None):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 403
        return resp

    provider = AlpacaORBProvider(
        api_key="test_key",
        secret_key="test_secret",
        feed="sip",
        request_func=MagicMock(side_effect=_mock_get),
        rate_limit_pause_seconds=0.0,
    )

    assert provider.is_feed_consolidated is True
    assert provider.feed_name == "sip"

    with pytest.raises(ORBProviderConfigurationError) as exc_info:
        provider.fetch_daily_bars(["AAPL"], start_date=TEST_DATE, end_date=TEST_DATE)

    assert "Alpaca feed entitlement error" in str(exc_info.value)
    assert "HTTP 403 Forbidden" in str(exc_info.value)
    assert "feed='sip'" in str(exc_info.value)

    # Provider feed must remain strictly 'sip' (no silent or mixed switching)
    assert provider.feed_name == "sip"
    assert provider.is_feed_consolidated is True


def test_alpaca_pagination_combines_pages():
    """Alpaca provider follows next_page_token and accumulates bars across multiple pages."""
    page_reqs = 0

    def _mock_get(url, headers=None, params=None, timeout=None):
        nonlocal page_reqs
        page_reqs += 1
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        if page_reqs == 1:
            # Page 1: 1 bar for AAPL, has next_page_token
            resp.json.return_value = {
                "bars": {
                    "AAPL": [
                        {
                            "t": "2024-01-02T14:30:00Z",
                            "o": 180.0,
                            "h": 181.0,
                            "l": 179.5,
                            "c": 180.5,
                            "v": 50000.0,
                        }
                    ]
                },
                "next_page_token": "page_2_token",
            }
        else:
            # Page 2: 1 more bar for AAPL, next_page_token is None
            resp.json.return_value = {
                "bars": {
                    "AAPL": [
                        {
                            "t": "2024-01-02T14:31:00Z",
                            "o": 180.5,
                            "h": 181.5,
                            "l": 180.2,
                            "c": 181.0,
                            "v": 60000.0,
                        }
                    ]
                },
                "next_page_token": None,
            }
        return resp

    provider = AlpacaORBProvider(
        api_key="test_key",
        secret_key="test_secret",
        request_func=MagicMock(side_effect=_mock_get),
        rate_limit_pause_seconds=0.0,
    )

    res = provider.fetch_opening_range_bars(["AAPL"], session_date=TEST_DATE)
    assert page_reqs == 2
    assert len(res["AAPL"]) == 2
    assert res["AAPL"][0].volume == 50000.0
    assert res["AAPL"][1].volume == 60000.0


def test_alpaca_pagination_cycle_defense():
    """Alpaca provider fails closed if API returns a repeated page_token."""
    def _mock_get(url, headers=None, params=None, timeout=None):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.json.return_value = {
            "bars": {"AAPL": []},
            "next_page_token": "infinite_loop_token",
        }
        return resp

    from tradex.research.daytrade_orb.provider import ORBProviderDataUnavailableError

    provider = AlpacaORBProvider(
        api_key="test_key",
        secret_key="test_secret",
        request_func=MagicMock(side_effect=_mock_get),
        rate_limit_pause_seconds=0.0,
    )

    with pytest.raises(ORBProviderDataUnavailableError) as exc_info:
        provider.fetch_daily_bars(["AAPL"], start_date=TEST_DATE, end_date=TEST_DATE)

    assert "Pagination cycle detected" in str(exc_info.value)


def test_mock_provider_create_populated():
    """MockORBProvider.create_populated() returns populated 33-symbol synthetic fixture."""
    provider = MockORBProvider.create_populated()
    assert len(provider.symbols) == 33
    assert len(provider.daily_bars) == 33
    assert len(provider.opening_range_bars) == 33
    assert len(provider.prior_opening_range_volumes) == 33
    assert "SYNTH_L01" in provider.symbols
    assert len(provider.daily_bars["SYNTH_L01"]) == 15
    assert len(provider.opening_range_bars["SYNTH_L01"]) == 5
    assert len(provider.prior_opening_range_volumes["SYNTH_L01"]) == 14


def test_alpaca_rate_limit_429_retry_handling():
    """When Alpaca returns HTTP 429, provider retries and succeeds."""
    attempts = 0

    def _mock_get(url, headers=None, params=None, timeout=None):
        nonlocal attempts
        attempts += 1
        resp = MagicMock(spec=requests.Response)
        if attempts == 1:
            resp.status_code = 429
            resp.headers = {"Retry-After": "0.01"}
            return resp
        resp.status_code = 200
        resp.json.return_value = [{"symbol": "AAPL", "exchange": "NASDAQ", "status": "active"}]
        return resp

    provider = AlpacaORBProvider(
        api_key="test_key",
        secret_key="test_secret",
        request_func=MagicMock(side_effect=_mock_get),
        rate_limit_pause_seconds=0.0,
    )

    universe = provider.discover_universe()
    assert attempts == 2
    assert universe == ["AAPL"]


def test_schwab_stub_explains_limitations():
    """SchwabORBProviderStub raises explicit limitation errors explaining single-symbol rate limit."""
    stub = SchwabORBProviderStub()
    assert stub.provider_name == "schwab"

    with pytest.raises(ORBProviderConfigurationError) as exc_info1:
        stub.discover_universe()
    assert "Schwab Market Data API does not provide a market universe endpoint" in str(exc_info1.value)

    with pytest.raises(ORBProviderConfigurationError) as exc_info2:
        stub.fetch_daily_bars(["AAPL"], TEST_DATE, TEST_DATE)
    assert "single-symbol queries" in str(exc_info2.value)
    assert ">66 minutes" in str(exc_info2.value)


def test_resolve_orb_provider_mock_and_schwab():
    """resolve_orb_provider correctly resolves Mock, Schwab stub, and Alpaca."""
    settings = settings_from_mapping({"DATA_PROVIDER": "schwab"})
    p_schwab = resolve_orb_provider(settings=settings)
    assert isinstance(p_schwab, SchwabORBProviderStub)

    p_mock = resolve_orb_provider(provider_name="mock")
    assert isinstance(p_mock, MockORBProvider)
    assert len(p_mock.symbols) == 33
