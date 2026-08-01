"""Tests for outcome-tracker timing and price resolution."""
from datetime import UTC, datetime
from unittest.mock import patch

import numpy as np
import pandas as pd

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


def _make_close(values, start: str = "2024-01-02") -> pd.DataFrame:
    """Return a single-level DataFrame from a list of close values."""
    dates = pd.date_range(start, periods=len(values), freq="B")
    return pd.DataFrame({"Close": values}, index=dates)


def _fetch(close_value, *, after_date=datetime(2024, 1, 1, tzinfo=UTC), days_forward=3,
           current=datetime(2026, 8, 1, tzinfo=UTC)):
    """Call _fetch_close_after with a mocked yfinance download and current time."""
    if close_value is None:
        df = pd.DataFrame()
    elif isinstance(close_value, pd.DataFrame):
        df = close_value
    else:
        df = _make_close(close_value)

    with (
        patch.object(outcome_tracker.yf, "download", return_value=df),
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        return outcome_tracker._fetch_close_after(
            "AAPL", after_date, days_forward=days_forward
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

    # NaN before the target session still counts as a trading session; the
    # target is the third session and the fourth session provides the close.
    close = _fetch([np.nan, 101.0, 102.0, 103.0], days_forward=3)
    assert isinstance(close, float)
    assert close == 102.0


def test_nan_before_target_session_counts_as_trading_session():
    """A missing close before the target must not shift the target row index."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 5, tzinfo=UTC)

    # Three trading sessions: NaN on session 1, valid closes on sessions 2/3.
    # The 3-session outcome should be session 3 (103.0), not session 2 (102.0).
    close = _fetch([np.nan, 101.0, 102.0],
                   after_date=signal_time, days_forward=3, current=current)
    assert close == 102.0


def test_nan_target_session_falls_back_to_later_valid_close():
    """A missing close on the target session should fall back to the next valid close."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 4, tzinfo=UTC)

    # Two sessions: session 2 (target) is NaN, session 3 is valid.
    close = _fetch([101.0, np.nan, 103.0],
                   after_date=signal_time, days_forward=2, current=current)
    assert isinstance(close, float)
    assert close == 103.0


def test_one_trading_day_outcome_resolves_immediately():
    """A 1-session outcome resolves as soon as one trading row is available."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 3, tzinfo=UTC)
    close = _fetch([101.0], after_date=signal_time, days_forward=1, current=current)
    assert close == 101.0


def test_one_day_outcome_does_not_wait_for_full_buffer():
    """A 1-session outcome should not be blocked by the +7 calendar-day buffer."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 3, tzinfo=UTC)
    close = _fetch([101.0], after_date=signal_time, days_forward=1, current=current)
    assert close is not None


def test_three_day_outcome_requires_three_sessions():
    """A 3-session outcome resolves only when three trading rows are available."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 5, tzinfo=UTC)

    close = _fetch([101.0, 102.0, 103.0], after_date=signal_time, days_forward=3, current=current)
    assert close == 103.0

    # Two rows is not enough.
    close = _fetch([101.0, 102.0], after_date=signal_time, days_forward=3, current=current)
    assert close is None


def test_five_day_outcome_requires_five_sessions():
    """A 5-session outcome resolves only when five trading rows are available."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 8, tzinfo=UTC)

    close = _fetch([101.0, 102.0, 103.0, 104.0, 105.0],
                    after_date=signal_time, days_forward=5, current=current)
    assert close == 105.0

    close = _fetch([101.0, 102.0, 103.0, 104.0],
                    after_date=signal_time, days_forward=5, current=current)
    assert close is None


def test_weekend_signal_resolves_on_next_trading_session():
    """A Friday signal with a Monday close resolves as the 1-session outcome."""
    friday = datetime(2024, 1, 5, tzinfo=UTC)  # Friday
    current = datetime(2024, 1, 8, tzinfo=UTC)  # Monday after close
    # Jan 8 is the next business day after Jan 5.
    close = _fetch([101.0], after_date=friday, days_forward=1, current=current)
    assert close == 101.0


def test_holiday_or_missing_session_gaps_do_not_count():
    """Calendar gaps are not counted toward days_forward; only returned rows are."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 8, tzinfo=UTC)
    # Three trading sessions: Jan 2, Jan 3, Jan 5 (Jan 4 missing as a gap)
    values = [101.0, 102.0, 103.0]
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-05"])
    df = pd.DataFrame({"Close": values}, index=dates)
    close = _fetch(df, after_date=signal_time, days_forward=3, current=current)
    assert close == 103.0


def test_future_signal_returns_none_without_fetch():
    """A signal whose first eligible date is in the future must not call yfinance."""
    signal_time = datetime(2026, 8, 5, tzinfo=UTC)
    current = datetime(2026, 8, 1, tzinfo=UTC)

    with (
        patch.object(outcome_tracker.yf, "download") as mock_download,
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        close = outcome_tracker._fetch_close_after(
            "AAPL", signal_time, days_forward=1
        )

    assert close is None
    mock_download.assert_not_called()


def test_signal_today_returns_none():
    """A signal from today cannot have an outcome because the next session has not closed."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 1, tzinfo=UTC)

    with (
        patch.object(outcome_tracker.yf, "download") as mock_download,
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        close = outcome_tracker._fetch_close_after(
            "AAPL", signal_time, days_forward=1
        )

    assert close is None
    mock_download.assert_not_called()


def test_empty_response_and_too_few_rows_remain_pending():
    """Empty DataFrames or too few trading rows return None without errors."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 3, tzinfo=UTC)

    assert _fetch(None, after_date=signal_time, days_forward=1, current=current) is None
    assert _fetch([101.0], after_date=signal_time, days_forward=3, current=current) is None


def test_request_boundaries_respect_available_data():
    """yf.download should receive start one day after the signal and end bounded by availability."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 4, tzinfo=UTC)
    df = _make_close([101.0, 102.0])

    with (
        patch.object(outcome_tracker.yf, "download", return_value=df) as mock_download,
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        outcome_tracker._fetch_close_after("AAPL", signal_time, days_forward=1)

    assert mock_download.call_count == 1
    _, kwargs = mock_download.call_args
    assert kwargs["start"] == "2024-01-02"
    # Current is Jan 4, so the exclusive end is Jan 5 (available_end = current + 1 day).
    assert kwargs["end"] == "2024-01-05"


def test_request_boundaries_use_buffered_end_when_within_range():
    """When the buffered end is earlier than the currently available end, the request is limited by the buffer."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 25, tzinfo=UTC)
    df = _make_close([101.0, 102.0, 103.0])

    with (
        patch.object(outcome_tracker.yf, "download", return_value=df) as mock_download,
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        outcome_tracker._fetch_close_after("AAPL", signal_time, days_forward=3)

    _, kwargs = mock_download.call_args
    assert kwargs["start"] == "2024-01-02"
    # buffer_end = 2024-01-11, available_end = 2024-01-26; request_end is the buffer.
    assert kwargs["end"] == "2024-01-11"


def test_outcome_resolves_at_earliest_valid_date():
    """An intraday signal resolves as soon as the next trading-day close is available.

    Previously the function added `days_forward + 7` calendar days and refused to
    fetch until that entire buffer had elapsed. With the fix, a signal from two
    calendar days ago (one trading day) returns the first eligible close.
    """
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 3, tzinfo=UTC)
    close = _fetch([101.0], after_date=signal_time, days_forward=1, current=current)

    assert close is not None
    assert isinstance(close, float)
    assert close == 101.0
