"""Characterization tests for confluence scoring."""
from unittest.mock import patch

import pandas as pd
import pytest

from tradex.tracker import confluence


def _make_bars(n: int = 30) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame that satisfies the 30-bar minimum."""
    return pd.DataFrame({
        "open": [1.0] * n,
        "high": [2.0] * n,
        "low": [0.5] * n,
        "close": [1.5] * n,
        "volume": [10] * n,
    })


@pytest.mark.xfail(strict=True, reason="Empty rows create a column-less DataFrame (COR-001)")
def test_empty_confluence_returns_empty_dataframe():
    """run_confluence_screen must return an empty DataFrame with expected columns when nothing passes."""
    result = confluence.run_confluence_screen([], min_confluence=50)
    assert isinstance(result, pd.DataFrame)
    assert result.empty
    assert "confluence_score" in result.columns


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

    assert result["confluence_score"] == 95
    assert result["tier"] != "all timeframes aligned"
    assert set(result["scores"].keys()) != {"intraday"} or result["tier"] == "weak / single timeframe"
