"""Characterization tests for confluence scoring."""
from unittest.mock import patch

import pandas as pd
import pytest

from tradex.tracker import confluence


def _make_bars(n: int = 31) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame that satisfies the 30-bar minimum."""
    return pd.DataFrame({
        "open": [1.0] * n,
        "high": [2.0] * n,
        "low": [0.5] * n,
        "close": [1.5] * n,
        "volume": [10] * n,
    })


EXPECTED_COLUMNS = {
    "ticker",
    "confluence_score",
    "tier",
    "active_timeframes",
    "score_intraday",
    "score_short",
    "score_long",
    "days_until_earnings",
    "last_close",
}


def test_empty_confluence_returns_empty_dataframe():
    """run_confluence_screen must return an empty DataFrame with the stable output schema."""
    low_result = {
        "ticker": "AAPL",
        "confluence_score": 10,
        "tier": "weak / single timeframe",
        "active_timeframes": [],
        "scores": {"intraday": 10, "short": 0, "long": 0},
        "reasons": {"intraday": ["none"]},
        "last_close": 100.0,
        "errors": {},
    }

    with patch.object(confluence, "days_until_earnings", return_value=None), \
         patch.object(confluence, "score_confluence", return_value=low_result):
        result = confluence.run_confluence_screen(["AAPL"], min_confluence=50)

    assert isinstance(result, pd.DataFrame)
    assert result.empty
    assert set(result.columns) == EXPECTED_COLUMNS

    # An empty ticker list should produce the same stable schema.
    empty = confluence.run_confluence_screen([], min_confluence=50)
    assert isinstance(empty, pd.DataFrame)
    assert empty.empty
    assert set(empty.columns) == EXPECTED_COLUMNS


def test_confluence_propagates_provider_to_all_timeframes():
    """score_confluence must pass the provider to fetch for intraday, short, and long."""
    captured = []

    def fake_fetch(ticker, timeframe, provider=None):
        captured.append((ticker, timeframe, provider))
        return _make_bars(31)

    def fake_score(df):
        return {"score": 60, "reasons": ["momentum"], "last_close": 100.0, "volume_ratio": 2.0, "rsi": 60.0}

    with (
        patch.object(confluence, "fetch", side_effect=fake_fetch),
        patch.object(confluence.intraday, "score", side_effect=fake_score),
        patch.object(confluence.short_term, "score", side_effect=fake_score),
        patch.object(confluence.long_term, "score", side_effect=fake_score),
        patch.object(confluence, "days_until_earnings", return_value=None),
    ):
        confluence.score_confluence("AAPL", provider="schwab")

    assert len(captured) == 3
    timeframes = {call[1] for call in captured}
    assert timeframes == {"intraday", "short", "long"}
    assert all(call[2] == "schwab" for call in captured)


def test_run_confluence_screen_propagates_provider():
    """run_confluence_screen must pass provider to score_confluence."""
    captured = []

    def fake_score_confluence(ticker, provider=None):
        captured.append(provider)
        return {
            "ticker": ticker,
            "confluence_score": 0,
            "tier": "no data",
            "active_timeframes": [],
            "scores": {},
            "reasons": {},
            "last_close": 100.0,
            "errors": {},
        }

    with (
        patch.object(confluence, "score_confluence", side_effect=fake_score_confluence),
        patch.object(confluence, "days_until_earnings", return_value=None),
    ):
        result = confluence.run_confluence_screen(["AAPL"], provider="alpaca")

    assert captured == ["alpaca"]
    assert isinstance(result, pd.DataFrame)


@pytest.mark.xfail(strict=True, reason="Confluence mislabels missing timeframes as 'all timeframes aligned' (COR-006)")
def test_confluence_does_not_claim_all_timeframes_when_one_is_missing():
    """If short and long data are unavailable, the result must not claim all timeframes are aligned."""

    def fake_fetch(ticker: str, timeframe: str, provider=None):
        if timeframe == "intraday":
            return _make_bars(30)
        raise RuntimeError("no data")

    def fake_score(df: pd.DataFrame):
        return {"score": 95, "reasons": ["bullish"], "last_close": 100.0, "volume_ratio": 2.0, "rsi": 60.0}

    with patch.object(confluence, "fetch", side_effect=fake_fetch), \
         patch.object(confluence.intraday, "score", side_effect=fake_score), \
         patch.object(confluence.short_term, "score", side_effect=fake_score), \
         patch.object(confluence.long_term, "score", side_effect=fake_score), \
         patch.object(confluence, "days_until_earnings", return_value=None):
        result = confluence.score_confluence("TEST")

    assert result.get("tier") != "all timeframes aligned"
    # Missing timeframes must remain visible in the result or error metadata.
    assert "short" in result.get("errors", {})
    assert "long" in result.get("errors", {})
