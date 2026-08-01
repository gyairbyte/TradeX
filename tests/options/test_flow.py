"""Tests for options-flow source policy."""
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from tradex.data.fetcher import ProviderCapabilityError
from tradex.options import flow


def _make_yahoo_chain(ticker: str = "AAPL") -> pd.DataFrame:
    """Return a mock yfinance-style options chain DataFrame."""
    calls = pd.DataFrame({
        "strike": [150.0],
        "expiration": ["2024-02-16"],
        "volume": [1000.0],
        "openInterest": [100.0],
        "lastPrice": [5.0],
    })
    puts = pd.DataFrame({
        "strike": [150.0],
        "expiration": ["2024-02-16"],
        "volume": [500.0],
        "openInterest": [50.0],
        "lastPrice": [4.0],
    })
    return calls, puts


def test_resolve_options_source_rejects_unknown():
    with pytest.raises(ProviderCapabilityError):
        flow._resolve_options_source("bloomberg")


def test_resolve_options_source_defaults_from_env(monkeypatch):
    monkeypatch.setattr(flow, "OPTIONS_DATA_SOURCE", "yahoo")
    assert flow._resolve_options_source(None) == "yahoo"


def test_get_flow_yahoo_source():
    """Explicit yahoo source calls yfinance without paid-source credentials."""
    calls, puts = _make_yahoo_chain()
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with patch.object(flow.yf, "Ticker", return_value=fake_ticker):
        df = flow.get_flow("AAPL", source="yahoo")

    assert not df.empty
    assert (df["source"] == "yahoo").all()
    fake_ticker.option_chain.assert_called_once_with("2024-02-16")


def test_get_flow_unusual_whales_requires_key():
    with patch.object(flow, "UNUSUAL_WHALES_KEY", ""), pytest.raises(ProviderCapabilityError):
        flow.get_flow("AAPL", source="unusual_whales")


def test_get_flow_tradier_requires_key():
    with patch.object(flow, "TRADIER_KEY", ""), pytest.raises(ProviderCapabilityError):
        flow.get_flow("AAPL", source="tradier")


def test_get_flow_auto_falls_back_to_yahoo_when_no_paid_keys():
    """auto mode should use Yahoo when paid keys are missing."""
    calls, puts = _make_yahoo_chain()
    fake_chain = Mock(calls=calls, puts=puts)
    fake_ticker = Mock(options=("2024-02-16",), option_chain=Mock(return_value=fake_chain))

    with (
        patch.object(flow, "UNUSUAL_WHALES_KEY", ""),
        patch.object(flow, "TRADIER_KEY", ""),
        patch.object(flow.yf, "Ticker", return_value=fake_ticker),
    ):
        df = flow.get_flow("AAPL", source="auto")

    assert not df.empty
    assert (df["source"] == "yahoo").all()


def test_scan_unusual_flow_propagates_source_and_filters():
    """scan_unusual_flow passes source to get_flow and returns rows above the threshold."""
    data = pd.DataFrame({
        "ticker": ["AAPL", "AAPL"],
        "source": ["yahoo", "yahoo"],
        "type": ["CALL", "PUT"],
        "strike": [150.0, 150.0],
        "expiry": ["2024-02-16", "2024-02-16"],
        "premium": [None, None],
        "volume": [1000, 500],
        "open_interest": [100, 50],
        "vol_oi_ratio": [10.0, 1.0],
        "is_sweep": [False, False],
        "sentiment": ["", ""],
        "timestamp": ["", ""],
        "last": [5.0, 4.0],
        "bid": [None, None],
        "ask": [None, None],
    })

    with patch.object(flow, "get_flow", return_value=data) as mock_get:
        result = flow.scan_unusual_flow(["AAPL"], min_vol_oi=3.0, source="yahoo")

    mock_get.assert_called_once_with("AAPL", source="yahoo")
    assert len(result) == 1
    assert result.iloc[0]["vol_oi_ratio"] == 10.0


def test_get_put_call_sentiment_returns_source():
    data = pd.DataFrame({
        "ticker": ["AAPL"],
        "source": ["yahoo"],
        "type": ["CALL"],
        "volume": [1000.0],
    })
    with patch.object(flow, "get_flow", return_value=data):
        result = flow.get_put_call_sentiment("AAPL", source="yahoo")

    assert result["data_source"] == "yahoo"
    assert result["sentiment"] == "bullish"
    assert result["put_call_ratio"] == 0.0


def test_get_put_call_sentiment_unavailable_source_is_structured():
    with pytest.raises(ProviderCapabilityError):
        flow._resolve_options_source("bad")

    result = flow.get_put_call_sentiment("AAPL", source="unusual_whales")
    assert result["sentiment"] == "unavailable"
    assert result["data_source"] == "unusual_whales"
    assert "UNUSUAL_WHALES_API_KEY" in result["error"]
