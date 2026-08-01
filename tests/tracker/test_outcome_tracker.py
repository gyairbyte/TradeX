"""Characterization tests for outcome tracking."""
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import numpy as np
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


def _fetch(close_value, *, after_date=datetime(2024, 1, 1, tzinfo=UTC), days_forward=3):
    """Call _fetch_close_after with a mocked yfinance download returning `close_value`."""
    df: pd.DataFrame
    if close_value is None:
        df = pd.DataFrame()
    elif isinstance(close_value, pd.DataFrame):
        df = close_value
    else:
        dates = pd.date_range("2024-01-02", periods=len(close_value), freq="B")
        df = pd.DataFrame({"Close": close_value}, index=dates)

    with patch.object(outcome_tracker.yf, "download", return_value=df):
        return outcome_tracker._fetch_close_after(
            "AAPL",
            after_date,
            days_forward=days_forward,
        )


def test_fetch_close_with_multiindex_columns():
    """_fetch_close_after must handle yfinance column shapes and missing/NaN closes."""
    # MultiIndex columns (Close, ticker)
    multi_df = _make_multiindex_close(5, "AAPL")
    close = _fetch(multi_df)
    assert isinstance(close, float)
    assert close == 102.0

    # Single-level columns (Close, ...)
    single_df = _make_simple_close(5, "AAPL")
    close = _fetch(single_df)
    assert isinstance(close, float)
    assert close == 102.0

    # Empty response
    assert _fetch(None) is None

    # Missing close column
    missing_close = pd.DataFrame({
        "Open": [1.0, 2.0],
        "High": [2.0, 3.0],
        "Low": [0.5, 1.5],
        "Volume": [100, 200],
    })
    assert _fetch(missing_close) is None

    # NaN at target day with a later valid close
    close = _fetch([np.nan, 102.0, 103.0], days_forward=1)
    assert isinstance(close, float)
    assert close == 102.0

    # No valid close at all
    assert _fetch([np.nan, np.nan, np.nan], days_forward=1) is None


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

    with patch("tradex.tracker.outcome_tracker.datetime") as mock_datetime, \
         patch.object(outcome_tracker.yf, "download", return_value=df):
        mock_datetime.now.return_value = now
        close = outcome_tracker._fetch_close_after(
            "AAPL",
            signal_time,
            days_forward=1,
        )

    assert close is not None
    assert isinstance(close, float)
