"""Tests for provider-aware pattern mining."""
from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from tradex.data.fetcher import ProviderCapabilityError
from tradex.patterns import miner
from tradex.patterns.config import PatternConfig


def _make_history(n: int = 60) -> pd.DataFrame:
    """Return a canonical daily-history DataFrame long enough for mining."""
    dates = pd.date_range("2021-01-04", periods=n, freq="B")
    # Create a run-up at the end so _find_events has at least one event.
    closes = list(np.linspace(100.0, 110.0, n - 5)) + [115.0, 120.0, 130.0, 135.0, 140.0]
    opens = [c for c in closes]
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    volumes = [1000] * n
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    }, index=pd.DatetimeIndex(dates, name="datetime"), dtype=float)


def test_fetch_history_propagates_provider():
    """_fetch_history must call fetch_daily_history with the selected provider."""
    captured = []

    def fake_fetch_daily(ticker, start, end, provider=None, *, settings=None):
        captured.append((ticker, provider))
        return _make_history(80)

    cfg = PatternConfig(history_years=1, lookback_days=10, move_days=5, runup_pct=10.0, min_events=1)

    with patch.object(miner, "fetch_daily_history", side_effect=fake_fetch_daily):
        result = miner.mine_events(tickers=["AAPL"], cfg=cfg, event_type="runup", verbose=False, provider="schwab")

    assert captured == [("AAPL", "schwab")]
    assert not result.empty
    assert result["ticker"].iloc[0] == "AAPL"


def test_mine_events_default_provider():
    """When provider is None, mine_events uses the default (yahoo) without crashing."""
    with patch.object(miner, "fetch_daily_history", return_value=_make_history(80)):
        result = miner.mine_events(tickers=["AAPL"], cfg=PatternConfig(runup_pct=10.0, min_events=1), event_type="runup", verbose=False)

    assert not result.empty


def test_mine_events_unsupported_provider_raises():
    """An unsupported provider must surface a ProviderCapabilityError."""
    cfg = PatternConfig(history_years=1, lookback_days=10, move_days=5, min_events=1)

    def fake_fetch(ticker, start, end, provider=None, *, settings=None):
        from tradex.data.fetcher import ProviderCapabilityError
        raise ProviderCapabilityError("unsupported")

    with (
        patch.object(miner, "fetch_daily_history", side_effect=fake_fetch),
        pytest.raises(ProviderCapabilityError),
    ):
        miner.mine_events(tickers=["AAPL"], cfg=cfg, event_type="runup", verbose=False, provider="alpaca")


def test_no_direct_yahoo_call_in_miner():
    """miner.py should not call yfinance directly; it uses fetch_daily_history."""
    assert not hasattr(miner, "yf")


def test_run_full_build_propagates_provider_and_source():
    """run_full_build passes provider to mine_events and stores source in the fingerprint."""
    from tradex.patterns import fingerprint

    fake_events = pd.DataFrame({
        "ticker": ["AAPL"],
        "event_type": ["runup"],
        "event_date": [str(date(2024, 1, 1))],
        "move_pct": [20.0],
        "price_pct": [[1.0, 2.0]],
        "volume_ratio": [[1.0, 1.0]],
        "rsi": [[50.0, 50.0]],
        "macd_diff": [[0.0, 0.0]],
        "bb_width": [[0.1, 0.1]],
        "atr": [[0.5, 0.5]],
    })

    with (
        patch("tradex.patterns.miner.mine_events") as mock_mine,
        patch.object(fingerprint, "build_fingerprint") as mock_build,
    ):
        mock_mine.return_value = fake_events
        mock_build.return_value = {"n_events": 1, "source": "schwab"}
        fingerprint.run_full_build(tickers=["AAPL"], profile="standard", event_type="runup", verbose=False, provider="schwab")

    assert mock_mine.call_count == 1
    kwargs = mock_mine.call_args.kwargs
    assert kwargs["provider"] == "schwab"
    mock_build.assert_called_once()
    kwargs = mock_build.call_args.kwargs
    assert kwargs["source"] == "schwab"
