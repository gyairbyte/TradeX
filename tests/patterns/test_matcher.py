"""Tests for provider propagation through pattern matching."""
from unittest.mock import patch

import pandas as pd

from tradex.patterns import matcher


def _make_bars(n: int = 30) -> pd.DataFrame:
    """Return a DataFrame with the columns _extract_live_window expects."""
    return pd.DataFrame({
        "open": [1.0] * n,
        "high": [2.0] * n,
        "low": [0.5] * n,
        "close": [1.0 + i * 0.1 for i in range(n)],
        "volume": [10] * n,
        "rsi": [50.0] * n,
        "macd_diff": [0.0] * n,
        "bb_width": [0.1] * n,
    })


def _fake_fingerprint(lookback: int = 10):
    return {
        "lookback_days": lookback,
        "n_events": 5,
        "series": {
            key: {"mean": [0.0] * lookback, "std": [0.1] * lookback}
            for key in ["price_pct", "volume_ratio", "rsi", "macd_diff", "bb_width"]
        },
    }


def test_match_ticker_propagates_provider_to_fetch():
    """match_ticker must call fetch with the provided provider."""
    captured = []

    def fake_fetch(ticker, timeframe, provider=None):
        captured.append((ticker, timeframe, provider))
        return _make_bars(30)

    with (
        patch.object(matcher, "fetch", side_effect=fake_fetch),
        patch.object(matcher, "load_fingerprint", return_value=_fake_fingerprint(10)),
        patch.object(matcher, "_series_similarity", return_value=80.0),
    ):
        result = matcher.match_ticker("AAPL", provider="schwab")

    assert len(captured) == 1
    assert captured[0] == ("AAPL", "short", "schwab")
    assert result["ticker"] == "AAPL"


def test_run_match_screen_propagates_provider_to_match_ticker():
    """run_match_screen must pass provider to each match_ticker call."""
    captured = []

    def fake_match_ticker(ticker, **kwargs):
        captured.append((ticker, kwargs.get("provider")))
        return {
            "ticker": ticker,
            "event_type": kwargs.get("event_type", "runup"),
            "profile": kwargs.get("profile", "standard"),
            "similarity_score": 85.0,
            "match_tier": "strong",
            "series_scores": {"price_pct": 80.0},
            "fingerprint_events": 5,
            "interpretation": "test",
            "live_series": {},
            "fp_series": {},
        }

    with (
        patch.object(matcher, "match_ticker", side_effect=fake_match_ticker),
        patch.object(matcher, "load_fingerprint", return_value=_fake_fingerprint(10)),
    ):
        matcher.run_match_screen(
            ["AAPL", "MSFT"], event_type="runup", profile="standard", provider="alpaca"
        )

    assert len(captured) == 2
    assert all(call[1] == "alpaca" for call in captured)
    assert {call[0] for call in captured} == {"AAPL", "MSFT"}


def test_match_ticker_uses_provider_as_fingerprint_source():
    """match_ticker must load the fingerprint for the same source used for live data."""
    captured = []

    def fake_fetch(*args, **kwargs):
        return _make_bars(30)

    def capture_load_fingerprint(event_type, profile, source=None):
        captured.append(source)
        return _fake_fingerprint(10)

    with (
        patch.object(matcher, "fetch", side_effect=fake_fetch),
        patch.object(matcher, "load_fingerprint", side_effect=capture_load_fingerprint),
        patch.object(matcher, "_series_similarity", return_value=80.0),
    ):
        result = matcher.match_ticker("AAPL", provider="schwab")

    assert captured == ["schwab"]
    assert result["source"] == "schwab"


def test_run_match_screen_returns_stable_empty_dataframe():
    """run_match_screen must return an empty DataFrame with the expected columns
    when no fingerprint or no matches are found, not a columnless frame."""
    with (
        patch.object(matcher, "fetch", return_value=_make_bars(30)),
        patch.object(matcher, "load_fingerprint", return_value=None),
    ):
        df = matcher.run_match_screen(["AAPL", "MSFT"])

    assert df.empty
    assert list(df.columns) == [
        "ticker", "similarity_score", "match_tier", "event_type", "profile",
        "fp_events", "score_price", "score_volume", "score_rsi", "interpretation",
    ]
