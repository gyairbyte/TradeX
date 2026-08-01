"""Characterization tests for outcome tracking."""
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from tradex.tracker import outcome_tracker


def _make_multiindex_close(n: int = 5, ticker: str = "AAPL") -> pd.DataFrame:
    """Return a yfinance-style MultiIndex-column DataFrame."""
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({("Close", ticker): [100 + i for i in range(n)]}, index=dates)


def _make_simple_close(n: int = 5, ticker: str = "AAPL") -> pd.DataFrame:
    """Return a single-level-column DataFrame like yfinance for an ordinary ticker."""
    _ = ticker
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({"Close": [100 + i for i in range(n)]}, index=dates)


@pytest.mark.xfail(strict=True, reason="MultiIndex yfinance columns crash outcome fetch (COR-002)")
def test_fetch_close_with_multiindex_columns():
    """_fetch_close_after must handle yfinance MultiIndex columns without crashing."""
    df = _make_multiindex_close(5, "AAPL")
    with patch.object(outcome_tracker.yf, "download", return_value=df):
        close = outcome_tracker._fetch_close_after(
            "AAPL",
            datetime(2024, 1, 1, tzinfo=UTC),
            days_forward=3,
        )
    assert isinstance(close, float)
    assert close == 102.0


@pytest.mark.xfail(strict=True, reason="Outcome tracker waits too long before resolving (COR-003)")
def test_outcome_resolves_at_earliest_valid_date():
    """An intraday signal should resolve as soon as one trading day has passed.

    `_fetch_close_after` currently adds `days_forward + 7` calendar days of buffer
    and refuses to fetch until that buffer has elapsed. This test pins that
    behavior: a signal from two days ago with `days_forward=1` still returns `None`
    even though one trading day has already passed.
    """
    now = datetime(2024, 1, 8, tzinfo=UTC)
    signal_time = now - timedelta(days=2)  # two calendar days ago, enough for 1 trading day
    df = _make_simple_close(5, "AAPL")

    with patch.object(outcome_tracker.datetime, "now", return_value=now), \
         patch.object(outcome_tracker.yf, "download", return_value=df):
        close = outcome_tracker._fetch_close_after(
            "AAPL",
            signal_time,
            days_forward=1,
        )

    assert close is not None
    assert isinstance(close, float)
