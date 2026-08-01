"""Tests for the screener engine."""
from unittest.mock import patch

import pytest

from tradex.screener import engine


@pytest.mark.xfail(strict=True, reason="Engine returns empty DataFrame instead of an error summary when all fetches fail (COR-013)")
def test_engine_reports_provider_failures():
    """When every fetch fails, the engine should distinguish fetch errors from zero signals."""
    with patch.object(engine, "fetch", side_effect=RuntimeError("network")):
        result = engine.run(["AAPL", "MSFT"], timeframe="intraday")

    # Desired behavior: result should expose an error count or error summary
    assert hasattr(result, "errors") or "errors" in result
    assert result.errors["AAPL"] is not None
    assert result.total_scanned == 2
    assert result.total_signals == 0


def _make_result(score: int = 80):
    return {
        "score": score,
        "last_close": 100.0,
        "volume_ratio": 2.0,
        "rsi": 60.0,
        "reasons": ["momentum"],
    }


def test_engine_propagates_schwab_provider_to_fetch():
    """An explicit provider argument must reach every fetch call in the engine."""
    captured = []

    def fake_fetch(ticker, timeframe, provider=None):
        captured.append((ticker, timeframe, provider))
        return [0] * 31  # scorer is mocked, so df shape doesn't matter

    def fake_score(df):
        return _make_result(85)

    with (
        patch.object(engine, "fetch", side_effect=fake_fetch),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        result = engine.run(
            ["AAPL", "MSFT"], timeframe="intraday", provider="schwab"
        )

    assert len(captured) == 2
    assert all(call[2] == "schwab" for call in captured)
    assert "AAPL" in result["ticker"].values
    assert "MSFT" in result["ticker"].values


def test_engine_propagates_yahoo_provider_to_fetch():
    """An explicit yahoo provider must also be forwarded unchanged."""
    captured = []

    def fake_fetch(ticker, timeframe, provider=None):
        captured.append(provider)
        return [0] * 31

    def fake_score(df):
        return _make_result(70)

    with (
        patch.object(engine, "fetch", side_effect=fake_fetch),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        engine.run(["TSLA"], timeframe="intraday", provider="yahoo")

    assert captured == ["yahoo"]


def test_engine_passes_none_provider_when_not_specified():
    """Without an explicit provider, None should be forwarded so the fetcher uses env default."""
    captured = []

    def fake_fetch(ticker, timeframe, provider=None):
        captured.append(provider)
        return [0] * 31

    def fake_score(df):
        return _make_result(60)

    with (
        patch.object(engine, "fetch", side_effect=fake_fetch),
        patch.object(engine, "days_until_earnings", return_value=None),
        patch.object(engine, "SIGNAL_MAP", {"intraday": (fake_score, "intraday")}),
    ):
        engine.run(["NVDA"], timeframe="intraday")

    assert captured == [None]
