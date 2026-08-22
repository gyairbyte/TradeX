"""Tests for outcome-tracker timing and price resolution."""

from datetime import UTC, datetime
from unittest.mock import patch

import numpy as np
import pandas as pd

from tradex.tracker import outcome_tracker, store


def _make_ohlcv(
    closes,
    start: str = "2024-01-02",
    ticker: str | None = None,
    multiindex: bool = False,
) -> pd.DataFrame:
    """Return a yfinance-style daily DataFrame with full OHLCV columns.

    If ``multiindex`` is True, columns follow yfinance's (Field, Ticker) shape.
    NaN values in ``closes`` produce rows with a missing close but valid
    open/high/low/volume so the outcome tracker can count the session.
    """
    dates = pd.date_range(start, periods=len(closes), freq="B")
    base = [100.0 if pd.isna(c) else float(c) for c in closes]
    opens = [b for b in base]
    highs = [b + 1.0 for b in base]
    lows = [b - 1.0 for b in base]
    volumes = [1000] * len(closes)

    if multiindex:
        columns = pd.MultiIndex.from_tuples(
            [(field, ticker or "AAPL") for field in ["Open", "High", "Low", "Close", "Volume"]]
        )
        data = np.column_stack([opens, highs, lows, closes, volumes])
        return pd.DataFrame(data, index=dates, columns=columns)

    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=dates,
    )


def _make_close(values, start: str = "2024-01-02") -> pd.DataFrame:
    """Return a single-level DataFrame from a list of close values."""
    return _make_ohlcv(values, start=start)


def _make_history_df(closes, start: str = "2024-01-02") -> pd.DataFrame:
    """Return a canonical, lowercase-column history DataFrame as returned by
    ``fetch_daily_history``."""
    dates = pd.date_range(start, periods=len(closes), freq="B")
    base = [100.0 if pd.isna(c) else float(c) for c in closes]
    return pd.DataFrame(
        {
            "open": base,
            "high": [b + 1.0 for b in base],
            "low": [b - 1.0 for b in base],
            "close": closes,
            "volume": [1000] * len(closes),
        },
        index=pd.DatetimeIndex(dates, name="datetime", tz="UTC"),
    )


def _fetch(
    close_value,
    *,
    after_date=datetime(2024, 1, 1, tzinfo=UTC),
    days_forward=3,
    current=datetime(2026, 8, 1, tzinfo=UTC),
    provider="yahoo",
):
    """Call _fetch_close_after with a mocked daily-history abstraction and current time."""
    if close_value is None:
        df = pd.DataFrame()
    elif isinstance(close_value, pd.DataFrame):
        df = close_value
    else:
        df = _make_close(close_value)

    with (
        patch("tradex.data.history.yf.download", return_value=df),
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        return outcome_tracker._fetch_close_after(
            "AAPL", after_date, days_forward=days_forward, provider=provider
        )


def test_fetch_close_with_multiindex_columns():
    """_fetch_close_after must handle yfinance column shapes and missing/NaN closes."""
    # MultiIndex columns (Close, ticker)
    multi_df = _make_ohlcv([100.0, 101.0, 102.0, 103.0, 104.0], multiindex=True, ticker="AAPL")
    close = _fetch(multi_df)
    assert isinstance(close, float)
    assert close == 102.0

    # Single-level columns (Close, ...)
    single_df = _make_ohlcv([100.0, 101.0, 102.0, 103.0, 104.0])
    close = _fetch(single_df)
    assert isinstance(close, float)
    assert close == 102.0

    # Empty response
    assert _fetch(None) is None

    # Missing close column
    missing_close = pd.DataFrame(
        {
            "Open": [1.0, 2.0],
            "High": [2.0, 3.0],
            "Low": [0.5, 1.5],
            "Volume": [100, 200],
        }
    )
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
    close = _fetch([np.nan, 101.0, 102.0], after_date=signal_time, days_forward=3, current=current)
    assert close == 102.0


def test_nan_target_session_falls_back_to_later_valid_close():
    """A missing close on the target session should fall back to the next valid close."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 4, tzinfo=UTC)

    # Two sessions: session 2 (target) is NaN, session 3 is valid.
    close = _fetch([101.0, np.nan, 103.0], after_date=signal_time, days_forward=2, current=current)
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

    close = _fetch(
        [101.0, 102.0, 103.0, 104.0, 105.0], after_date=signal_time, days_forward=5, current=current
    )
    assert close == 105.0

    close = _fetch(
        [101.0, 102.0, 103.0, 104.0], after_date=signal_time, days_forward=5, current=current
    )
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
    df = pd.DataFrame(
        {
            "Open": values,
            "High": [v + 1 for v in values],
            "Low": [v - 1 for v in values],
            "Close": values,
            "Volume": [1000, 1000, 1000],
        },
        index=dates,
    )
    close = _fetch(df, after_date=signal_time, days_forward=3, current=current)
    assert close == 103.0


def test_future_signal_returns_none_without_fetch():
    """A signal whose first eligible date is in the future must not call yfinance."""
    signal_time = datetime(2026, 8, 5, tzinfo=UTC)
    current = datetime(2026, 8, 1, tzinfo=UTC)

    with (
        patch("tradex.data.history.yf.download") as mock_download,
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        close = outcome_tracker._fetch_close_after("AAPL", signal_time, days_forward=1)

    assert close is None
    mock_download.assert_not_called()


def test_signal_today_returns_none():
    """A signal from today cannot have an outcome because the next session has not closed."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 1, tzinfo=UTC)

    with (
        patch("tradex.data.history.yf.download") as mock_download,
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        close = outcome_tracker._fetch_close_after("AAPL", signal_time, days_forward=1)

    assert close is None
    mock_download.assert_not_called()


def test_empty_response_and_too_few_rows_remain_pending():
    """Empty DataFrames or too few trading rows return None without errors."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 3, tzinfo=UTC)

    assert _fetch(None, after_date=signal_time, days_forward=1, current=current) is None
    assert _fetch([101.0], after_date=signal_time, days_forward=3, current=current) is None


def test_request_boundaries_respect_available_data():
    """The daily-history abstraction receives start one day after the signal and end bounded by availability."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 4, tzinfo=UTC)
    df = _make_close([101.0, 102.0])

    with (
        patch("tradex.data.history.yf.download", return_value=df) as mock_download,
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        outcome_tracker._fetch_close_after("AAPL", signal_time, days_forward=1, provider="yahoo")

    assert mock_download.call_count == 1
    _, kwargs = mock_download.call_args
    assert kwargs["start"] == "2024-01-02"
    # _fetch_close_after passes an inclusive end date of Jan 4; the abstraction
    # adds one day because yfinance's end argument is exclusive.
    assert kwargs["end"] == "2024-01-05"


def test_request_boundaries_use_buffered_end_when_within_range():
    """When the buffered end is earlier than the currently available end, the request is limited by the buffer."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 25, tzinfo=UTC)
    df = _make_close([101.0, 102.0, 103.0])

    with (
        patch("tradex.data.history.yf.download", return_value=df) as mock_download,
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        outcome_tracker._fetch_close_after("AAPL", signal_time, days_forward=3, provider="yahoo")

    _, kwargs = mock_download.call_args
    assert kwargs["start"] == "2024-01-02"
    # buffer_end = 2024-01-11 (inclusive); the abstraction passes end+1 to yfinance.
    assert kwargs["end"] == "2024-01-12"


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


def test_provider_reaches_daily_history_abstraction():
    """The provider argument is forwarded to the daily-history abstraction."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 3, tzinfo=UTC)
    df = _make_close([101.0])

    with (
        patch("tradex.tracker.outcome_tracker.fetch_daily_history", return_value=df) as mock_fetch,
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        outcome_tracker._fetch_close_after("AAPL", signal_time, days_forward=1, provider="schwab")

    mock_fetch.assert_called_once()
    args, kwargs = mock_fetch.call_args
    assert args[0] == "AAPL"
    assert kwargs["provider"] == "schwab"


def test_schwab_missing_close_before_target_session_counts():
    """A Schwab daily-history row with a missing close but other OHLCV data
    still counts as a trading session for COR-003 timing."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 5, tzinfo=UTC)
    # Three sessions; session 1 has a missing close, session 3 is the target.
    df = _make_history_df([float("nan"), 101.0, 102.0])

    with (
        patch("tradex.tracker.outcome_tracker.fetch_daily_history", return_value=df) as mock_fetch,
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        close = outcome_tracker._fetch_close_after(
            "AAPL", signal_time, days_forward=3, provider="schwab"
        )

    assert close == 102.0
    mock_fetch.assert_called_once()
    assert mock_fetch.call_args.kwargs["provider"] == "schwab"


def test_schwab_missing_close_on_target_session_falls_back():
    """A missing close on the target session for Schwab daily history falls
    back to the next valid close within the window."""
    signal_time = datetime(2024, 1, 1, tzinfo=UTC)
    current = datetime(2024, 1, 5, tzinfo=UTC)
    # Three sessions; target (session 2) is NaN, session 3 is valid.
    df = _make_history_df([101.0, float("nan"), 103.0])

    with (
        patch("tradex.tracker.outcome_tracker.fetch_daily_history", return_value=df) as mock_fetch,
        patch.object(outcome_tracker, "_utc_now", return_value=current),
    ):
        close = outcome_tracker._fetch_close_after(
            "AAPL", signal_time, days_forward=2, provider="schwab"
        )

    assert close == 103.0
    mock_fetch.assert_called_once()
    assert mock_fetch.call_args.kwargs["provider"] == "schwab"


def test_provider_failure_increments_errors(fresh_signal_db):
    """A provider/auth/network failure from fetch_daily_history must reach the
    existing run_outcome_pass error boundary and increment `errors`, not `pending`."""
    from tradex.tracker import store

    with store._conn() as con:
        con.execute(
            "INSERT INTO signal_history (ticker, timeframe, scan_time, score, last_close, volume_ratio, rsi, reasons) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "AAPL",
                "intraday",
                datetime(2024, 1, 1, tzinfo=UTC).isoformat(),
                50,
                100.0,
                1.0,
                50.0,
                "test",
            ),
        )

    with (
        patch("tradex.tracker.outcome_tracker.fetch_daily_history") as mock_fetch,
        patch.object(outcome_tracker, "_utc_now", return_value=datetime(2024, 1, 3, tzinfo=UTC)),
    ):
        mock_fetch.side_effect = RuntimeError("Schwab authentication failed")
        summary = outcome_tracker.run_outcome_pass(verbose=False, provider="schwab")

    assert summary["errors"] == 1
    assert summary["pending"] == 0
    assert summary["resolved"] == 0
    mock_fetch.assert_called_once()
    assert mock_fetch.call_args.kwargs["provider"] == "schwab"


def _insert_signal(
    ticker: str = "AAPL",
    timeframe: str = "intraday",
    scan_time: str = "2024-01-01T00:00:00+00:00",
    score: int = 60,
    last_close: float = 100.0,
    provider: str = "yahoo",
):
    with store._conn() as con:
        con.execute(
            """
            INSERT INTO signal_history
              (ticker, timeframe, scan_time, score, last_close, volume_ratio, rsi, reasons, provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker, timeframe, scan_time, score, last_close, 1.0, 50.0, "test", provider),
        )


def test_run_outcome_pass_writes_outcome_provider(fresh_signal_db):
    """A resolved outcome records both the signal provider and the outcome provider."""
    _insert_signal(provider="yahoo")

    df = _make_history_df([101.0], start="2024-01-02")
    with (
        patch("tradex.tracker.outcome_tracker.fetch_daily_history", return_value=df),
        patch.object(outcome_tracker, "_utc_now", return_value=datetime(2024, 1, 3, tzinfo=UTC)),
    ):
        summary = outcome_tracker.run_outcome_pass(verbose=False, provider="schwab")

    assert summary["resolved"] == 1
    with store._conn() as con:
        row = con.execute("SELECT * FROM signal_history WHERE ticker = ?", ("AAPL",)).fetchone()
    assert row["provider"] == "yahoo"
    assert row["outcome_provider"] == "schwab"
    assert row["outcome_close"] == 101.0


def test_run_outcome_pass_does_not_write_outcome_provider_when_pending(fresh_signal_db):
    """A pending outcome leaves outcome_provider unset."""
    _insert_signal(provider="yahoo")

    with (
        patch("tradex.tracker.outcome_tracker.fetch_daily_history", return_value=pd.DataFrame()),
        patch.object(outcome_tracker, "_utc_now", return_value=datetime(2024, 1, 2, tzinfo=UTC)),
    ):
        summary = outcome_tracker.run_outcome_pass(verbose=False, provider="schwab")

    assert summary["pending"] == 1
    assert summary["resolved"] == 0
    with store._conn() as con:
        row = con.execute(
            "SELECT outcome_provider FROM signal_history WHERE ticker = ?", ("AAPL",)
        ).fetchone()
    assert row["outcome_provider"] is None


def test_run_outcome_pass_does_not_write_outcome_provider_on_failure(fresh_signal_db):
    """A provider failure leaves outcome_provider unset."""
    _insert_signal(provider="yahoo")

    with (
        patch(
            "tradex.tracker.outcome_tracker.fetch_daily_history",
            side_effect=RuntimeError("network"),
        ),
        patch.object(outcome_tracker, "_utc_now", return_value=datetime(2024, 1, 3, tzinfo=UTC)),
    ):
        summary = outcome_tracker.run_outcome_pass(verbose=False, provider="schwab")

    assert summary["errors"] == 1
    with store._conn() as con:
        row = con.execute(
            "SELECT outcome_provider FROM signal_history WHERE ticker = ?", ("AAPL",)
        ).fetchone()
    assert row["outcome_provider"] is None


def test_run_outcome_pass_resolves_duplicate_rows_independently(fresh_signal_db):
    """Two pending rows with the same ticker/timeframe/scan_time are both updated by id."""
    scan_time = "2024-01-01T00:00:00+00:00"
    _insert_signal(provider="yahoo", scan_time=scan_time)
    _insert_signal(provider="yahoo", scan_time=scan_time)

    df = _make_history_df([101.0, 102.0], start="2024-01-02")
    with (
        patch("tradex.tracker.outcome_tracker.fetch_daily_history", return_value=df),
        patch.object(outcome_tracker, "_utc_now", return_value=datetime(2024, 1, 5, tzinfo=UTC)),
    ):
        summary = outcome_tracker.run_outcome_pass(verbose=False, provider="schwab")

    assert summary["resolved"] == 2
    with store._conn() as con:
        rows = con.execute(
            "SELECT provider, outcome_provider, outcome_close FROM signal_history WHERE ticker = ?",
            ("AAPL",),
        ).fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row["provider"] == "yahoo"
        assert row["outcome_provider"] == "schwab"
        assert row["outcome_close"] is not None
