"""Tests for watchlist-refresh source separation and safe logging."""
import logging
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


def test_yahoo_market_cap_logs_do_not_leak_provider_exception(caplog):
    """A failing Yahoo fast_info call must not write the raw exception/traceback to logs."""
    sentinel = "OAUTH_TOKEN_LEAK_SENTINEL_12345"

    def _raise(*args, **kwargs):
        raise RuntimeError(sentinel)

    caplog.set_level(logging.DEBUG, logger="tradex.watchlists.refresh")
    with patch("yfinance.Ticker", side_effect=_raise):
        caps = refresh._fetch_yahoo_market_caps(["AAPL"])

    assert caps == {}
    assert sentinel not in caplog.text
    assert "AAPL" in caplog.text


def test_schwab_client_init_log_does_not_leak_exception_text(caplog, monkeypatch, tmp_path):
    """A failing Schwab client init must not write the raw exception text to logs."""
    sentinel = "SCHWAB_SECRET_LEAK_67890"
    token_file = tmp_path / "token.json"
    token_file.write_text("{}")

    monkeypatch.setenv("SCHWAB_APP_KEY", "app_key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "app_secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(token_file))

    def _raise(*args, **kwargs):
        raise RuntimeError(sentinel)

    with patch("schwab.auth.client_from_token_file", side_effect=_raise):
        caplog.set_level(logging.WARNING, logger="tradex.watchlists.refresh")
        client = refresh._schwab_client_or_none()

    assert client is None
    assert sentinel not in caplog.text
    assert "schwab client init failed" in caplog.text.lower()


def test_schwab_liquidity_filter_debug_logs_do_not_leak_exception_text(caplog, monkeypatch, tmp_path):
    """A failing Schwab quotes batch must not write traceback text to logs."""
    sentinel = "SCHWAB_BATCH_SECRET_LEAK_99999"
    token_file = tmp_path / "token.json"
    token_file.write_text("{}")

    monkeypatch.setenv("SCHWAB_APP_KEY", "app_key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "app_secret")
    monkeypatch.setenv("SCHWAB_TOKEN_PATH", str(token_file))

    fake_client = Mock()
    fake_client.get_instruments.return_value = Mock(
        status_code=200,
        raise_for_status=Mock(),
        json=Mock(return_value={
            "instruments": [{"symbol": "AAPL", "fundamental": {"avg3MonthVolume": 1000000}}]
        }),
    )
    fake_client.get_quotes.side_effect = RuntimeError(sentinel)

    with patch("schwab.auth.client_from_token_file", return_value=fake_client):
        caplog.set_level(logging.DEBUG, logger="tradex.watchlists.refresh")
        _survivors, warnings = refresh._schwab_liquidity_filter(["AAPL"])

    assert sentinel not in caplog.text
    assert any("Schwab quotes batch" in w for w in warnings)


def test_refresh_all_market_cap_warning_does_not_leak_exception_text():
    """A market-cap fetch failure must not propagate raw exception text to user warnings."""
    sentinel = "MARKET_CAP_EXCEPTION_LEAK_77777"
    sp500 = pd.DataFrame({"ticker": ["AAPL"], "sector": ["Technology"]})
    r1k = sp500.copy()

    with (
        patch.object(refresh, "_fetch_sp500", return_value=sp500),
        patch.object(refresh, "_fetch_dow", return_value=["AAPL"]),
        patch.object(refresh, "_fetch_ndx", return_value=["AAPL"]),
        patch.object(refresh, "_fetch_russell1000", return_value=r1k),
        patch.object(refresh, "fetch_market_caps", side_effect=RuntimeError(sentinel)),
        patch.object(refresh, "_schwab_liquidity_filter", return_value=({"AAPL"}, [])),
    ):
        result = refresh.refresh_all(market_cap_source="schwab")

    assert any("Market-cap fetch failed" in w for w in result.warnings)
    assert all(sentinel not in w for w in result.warnings)
