"""Tests for pre-market gap scanner source separation."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import ANY, Mock, patch

import pandas as pd
import pytest

from tradex.data.fetcher import ProviderCapabilityError
from tradex.premarket import gap_scanner, sources


def _make_daily_history(values, start: str = "2024-01-02") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(values), freq="B")
    return pd.DataFrame(
        {
            "open": values,
            "high": [v + 1 for v in values],
            "low": [v - 1 for v in values],
            "close": values,
            "volume": [1000] * len(values),
        },
        index=pd.DatetimeIndex(dates, name="datetime"),
        dtype=float,
    )


def test_get_prev_close_propagates_provider():
    """_get_prev_close passes the provider and resolves the previous session date."""
    captured = []

    def fake_history(ticker, start, end, provider=None, *, settings=None):
        captured.append((ticker, start, end, provider))
        return _make_daily_history([100.0, 101.0, 102.0])

    # 2024-01-05 is Friday; previous completed session is 2024-01-04.
    as_of = datetime(2024, 1, 5, 13, 30, tzinfo=UTC)
    with patch.object(gap_scanner, "fetch_daily_history", side_effect=fake_history):
        close = gap_scanner._get_prev_close("AAPL", provider="schwab", as_of=as_of)

    assert close == 102.0
    prev_session = date(2024, 1, 4)
    assert captured == [("AAPL", prev_session, prev_session, "schwab")]


def test_get_prev_close_returns_none_on_missing_data():
    with patch.object(gap_scanner, "fetch_daily_history", return_value=pd.DataFrame()):
        assert gap_scanner._get_prev_close("AAPL", provider="yahoo") is None


def test_get_premarket_price_yahoo():
    """Yahoo pre-market price uses 1m prepost history and returns the last pre-9:30am ET bar."""
    # 2024-01-03 is a Wednesday. 09:00/09:30/10:00 UTC = 04:00/04:30/05:00 ET.
    # The 04:00, 04:30 and 05:00 ET bars are valid pre-market; the latest valid close is 103.0.
    times = pd.date_range("2024-01-03 09:00", periods=3, freq="30min", tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 103.0],
            "High": [101.0, 102.0, 104.0],
            "Low": [99.0, 100.0, 102.0],
            "Close": [101.0, 102.0, 103.0],
            "Volume": [100, 100, 100],
        },
        index=times,
    )

    fake_ticker = Mock()
    fake_ticker.history.return_value = df
    fake_tk_cls = Mock(return_value=fake_ticker)

    # 10:30 UTC = 05:30 ET, before the 09:30 ET open, so all bars are in the past.
    as_of = datetime(2024, 1, 3, 10, 30, tzinfo=UTC)
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        price = gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of)

    assert price == 103.0
    fake_ticker.history.assert_called_once()
    _, kwargs = fake_ticker.history.call_args
    assert kwargs["start"] == as_of.date() - timedelta(days=1)
    assert kwargs["end"] == as_of.date() + timedelta(days=1)
    assert kwargs["interval"] == "1m"
    assert kwargs["prepost"] is True


def test_get_premarket_price_unsupported_provider():
    with pytest.raises(ProviderCapabilityError):
        gap_scanner.get_premarket_price("AAPL", provider="schwab")


def test_get_premarket_price_returns_none_for_empty():
    fake_ticker = Mock()
    fake_ticker.history.return_value = pd.DataFrame()
    fake_tk_cls = Mock(return_value=fake_ticker)

    # 10:30 UTC = 05:30 ET on a trading day, so the date is valid and the empty response
    # is the reason ``None`` is returned.
    as_of = datetime(2024, 1, 3, 10, 30, tzinfo=UTC)
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        assert gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of) is None


def test_scan_gaps_propagates_provider():
    """scan_gaps delegates to scan_gaps_with_report and preserves public columns."""
    as_of = datetime(2024, 1, 5, 13, 30, tzinfo=UTC)
    baseline = gap_scanner.DailyLiquidityBaseline(
        previous_session_date=date(2024, 1, 4),
        previous_close=100.0,
        lookback_sessions_requested=20,
        lookback_sessions_available=20,
        average_daily_volume=1_000_000.0,
        median_daily_volume=1_000_000.0,
        average_daily_dollar_volume=100_000_000.0,
        median_daily_dollar_volume=100_000_000.0,
    )
    bars = pd.DataFrame({
        "open": [104.0],
        "high": [106.0],
        "low": [103.0],
        "close": [105.0],
        "volume": [1000],
    }, index=pd.DatetimeIndex([datetime(2024, 1, 5, 13, 0, tzinfo=UTC)], name="datetime"))
    bars_result = gap_scanner.PremarketBarsResult(
        ticker="AAPL",
        requested_provider="yahoo",
        actual_provider="yahoo",
        session_date=date(2024, 1, 5),
        bars=bars,
        attempts=1,
        retries=0,
        error=None,
    )
    with (
        patch.object(gap_scanner, "fetch_daily_liquidity_baseline", return_value=baseline) as mock_base,
        patch.object(gap_scanner, "fetch_premarket_bars", return_value=bars_result) as mock_bars,
    ):
        result = gap_scanner.scan_gaps(["AAPL"], min_gap_pct=2.0, provider="yahoo", as_of=as_of)

    mock_base.assert_called_once()
    mock_bars.assert_called_once()
    assert not result.empty
    assert result.iloc[0]["ticker"] == "AAPL"
    assert result.iloc[0]["gap_pct"] == 5.0
    assert result.iloc[0]["actual_provider"] == "yahoo"


def test_scan_gaps_unsupported_provider_raises():
    """scan_gaps must not silently fall back when an unsupported provider is selected."""
    with pytest.raises(ProviderCapabilityError):
        gap_scanner.scan_gaps(["AAPL"], min_gap_pct=2.0, provider="schwab")


def test_scan_gaps_empty_returns_empty_df():
    as_of = datetime(2024, 1, 5, 13, 30, tzinfo=UTC)
    baseline = gap_scanner.DailyLiquidityBaseline(
        previous_session_date=date(2024, 1, 4),
        previous_close=100.0,
        lookback_sessions_requested=20,
        lookback_sessions_available=20,
        average_daily_volume=1_000_000.0,
        median_daily_volume=1_000_000.0,
        average_daily_dollar_volume=100_000_000.0,
        median_daily_dollar_volume=100_000_000.0,
    )
    bars = pd.DataFrame({
        "open": [100.0],
        "high": [100.0],
        "low": [100.0],
        "close": [100.0],
        "volume": [1000],
    }, index=pd.DatetimeIndex([datetime(2024, 1, 5, 13, 0, tzinfo=UTC)], name="datetime"))
    bars_result = gap_scanner.PremarketBarsResult(
        ticker="AAPL",
        requested_provider="yahoo",
        actual_provider="yahoo",
        session_date=date(2024, 1, 5),
        bars=bars,
        attempts=1,
        retries=0,
        error=None,
    )
    with (
        patch.object(gap_scanner, "fetch_daily_liquidity_baseline", return_value=baseline),
        patch.object(gap_scanner, "fetch_premarket_bars", return_value=bars_result),
    ):
        result = gap_scanner.scan_gaps(["AAPL"], min_gap_pct=2.0, provider="yahoo", as_of=as_of)
    assert result.empty


def test_run_gap_alerts_propagates_provider():
    """run_gap_alerts passes provider and as_of to scan_gaps and surfaces provider errors safely."""
    as_of = datetime(2024, 1, 5, 13, 30, tzinfo=UTC)
    with (
        patch.object(gap_scanner, "scan_gaps", return_value=pd.DataFrame()) as mock_scan,
        patch("tradex.alerts.notifier.alert_gap") as mock_alert,
    ):
        gap_scanner.run_gap_alerts(["AAPL"], min_gap_pct=4.0, provider="yahoo", as_of=as_of)

    mock_scan.assert_called_once_with(["AAPL"], min_gap_pct=4.0, provider="yahoo", as_of=as_of, settings=ANY)
    mock_alert.assert_not_called()


def test_run_gap_alerts_returns_empty_on_provider_error():
    with patch.object(gap_scanner, "scan_gaps", side_effect=ProviderCapabilityError("unsupported")):
        result = gap_scanner.run_gap_alerts(["AAPL"], min_gap_pct=4.0, provider="schwab")
    assert result.empty


def _ny(*args) -> datetime:
    from zoneinfo import ZoneInfo

    return datetime(*args, tzinfo=ZoneInfo("America/New_York"))


def test_get_premarket_price_winter_bars():
    """Pre-market filtering works in EST: only 04:00-09:30 ET bars count."""
    # 2024-01-03 04:00/05:00/06:00 ET = 09:00/10:00/11:00 UTC (EST)
    times = pd.DatetimeIndex(["2024-01-03 09:00", "2024-01-03 10:00", "2024-01-03 11:00"], tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 103.0],
            "High": [101.0, 102.0, 104.0],
            "Low": [99.0, 100.0, 102.0],
            "Close": [101.0, 102.0, 103.0],
            "Volume": [100, 100, 100],
        },
        index=times,
    )

    fake_ticker = Mock()
    fake_ticker.history.return_value = df
    fake_tk_cls = Mock(return_value=fake_ticker)

    # 11:30 UTC = 06:30 ET, after the latest bar but before the 09:30 ET open.
    as_of = datetime(2024, 1, 3, 11, 30, tzinfo=UTC)
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        price = gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of)

    assert price == 103.0
    _, kwargs = fake_ticker.history.call_args
    assert kwargs["start"] == as_of.date() - timedelta(days=1)
    assert kwargs["end"] == as_of.date() + timedelta(days=1)


def test_get_premarket_price_summer_bars():
    """Pre-market filtering works in EDT: only 04:00-09:30 ET bars count."""
    # 2024-07-03 04:00/05:00/06:00 EDT = 08:00/09:00/10:00 UTC
    times = pd.DatetimeIndex(["2024-07-03 08:00", "2024-07-03 09:00", "2024-07-03 10:00"], tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 103.0],
            "High": [101.0, 102.0, 104.0],
            "Low": [99.0, 100.0, 102.0],
            "Close": [101.0, 102.0, 103.0],
            "Volume": [100, 100, 100],
        },
        index=times,
    )

    fake_ticker = Mock()
    fake_ticker.history.return_value = df
    fake_tk_cls = Mock(return_value=fake_ticker)

    # 11:30 UTC = 07:30 EDT, after the latest bar but before the 09:30 ET open.
    as_of = datetime(2024, 7, 3, 11, 30, tzinfo=UTC)
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        price = gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of)

    assert price == 103.0


def test_get_premarket_price_excludes_exact_open():
    """A bar exactly at the regular-session open is excluded."""
    # 2024-01-03 09:30 ET = 14:30 UTC
    times = pd.DatetimeIndex(["2024-01-03 14:00", "2024-01-03 14:30"], tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [100.0, 103.0],
            "High": [101.0, 104.0],
            "Low": [99.0, 102.0],
            "Close": [101.0, 103.0],
            "Volume": [100, 100],
        },
        index=times,
    )

    fake_ticker = Mock()
    fake_ticker.history.return_value = df
    fake_tk_cls = Mock(return_value=fake_ticker)

    as_of = datetime(2024, 1, 3, 14, 15, tzinfo=UTC)  # 09:15 ET
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        price = gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of)

    assert price == 101.0


def test_get_premarket_price_excludes_prior_after_hours():
    """A bar from the previous day's after-hours session is excluded."""
    # 2024-01-02 17:00 ET = 22:00 UTC (after previous close)
    # 2024-01-03 09:30 ET = 14:30 UTC (regular-session open)
    times = pd.DatetimeIndex(["2024-01-02 22:00", "2024-01-03 14:30"], tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [99.0, 103.0],
            "High": [100.0, 104.0],
            "Low": [98.0, 102.0],
            "Close": [99.5, 103.0],
            "Volume": [100, 100],
        },
        index=times,
    )

    fake_ticker = Mock()
    fake_ticker.history.return_value = df
    fake_tk_cls = Mock(return_value=fake_ticker)

    as_of = datetime(2024, 1, 3, 13, 30, tzinfo=UTC)  # 08:30 ET
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        price = gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of)

    assert price is None


def test_get_premarket_price_excludes_before_4am():
    """A same-day bar before 04:00 ET is excluded."""
    times = pd.DatetimeIndex(["2024-01-03 08:30"], tz="UTC")  # 03:30 ET
    df = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [101.0],
            "Volume": [100],
        },
        index=times,
    )

    fake_ticker = Mock()
    fake_ticker.history.return_value = df
    fake_tk_cls = Mock(return_value=fake_ticker)

    as_of = datetime(2024, 1, 3, 8, 0, tzinfo=UTC)
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        price = gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of)

    assert price is None


def test_get_premarket_price_excludes_post_market():
    """A post-market bar on the session date is excluded."""
    # 2024-01-03 16:00 ET = 21:00 UTC
    times = pd.DatetimeIndex(["2024-01-03 21:00"], tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [101.0],
            "Volume": [100],
        },
        index=times,
    )

    fake_ticker = Mock()
    fake_ticker.history.return_value = df
    fake_tk_cls = Mock(return_value=fake_ticker)

    as_of = datetime(2024, 1, 3, 21, 0, tzinfo=UTC)  # 16:00 ET
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        price = gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of)

    assert price is None


def test_get_premarket_price_holiday_returns_none():
    """A full XNYS holiday must short-circuit before any Yahoo network call."""
    fake_ticker = Mock()
    fake_ticker.history.return_value = pd.DataFrame()
    fake_tk_cls = Mock(return_value=fake_ticker)

    # New Year's Day 2025 is not an XNYS session.
    as_of = datetime(2025, 1, 1, 13, 0, tzinfo=UTC)
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        assert gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of) is None

    fake_tk_cls.assert_not_called()
    fake_ticker.history.assert_not_called()


def test_get_premarket_price_good_friday_returns_none():
    """Good Friday is an XNYS holiday and must not reach Yahoo."""
    fake_ticker = Mock()
    fake_ticker.history.return_value = pd.DataFrame()
    fake_tk_cls = Mock(return_value=fake_ticker)

    as_of = datetime(2024, 3, 29, 13, 0, tzinfo=UTC)
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        assert gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of) is None

    fake_tk_cls.assert_not_called()
    fake_ticker.history.assert_not_called()


def test_get_premarket_price_saturday_returns_none():
    """Saturday must return None without constructing a Yahoo Ticker."""
    fake_ticker = Mock()
    fake_ticker.history.return_value = pd.DataFrame()
    fake_tk_cls = Mock(return_value=fake_ticker)

    as_of = datetime(2025, 1, 4, 13, 0, tzinfo=UTC)  # Saturday
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        assert gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of) is None

    fake_tk_cls.assert_not_called()
    fake_ticker.history.assert_not_called()


def test_get_premarket_price_sunday_returns_none():
    """Sunday must return None without constructing a Yahoo Ticker."""
    fake_ticker = Mock()
    fake_ticker.history.return_value = pd.DataFrame()
    fake_tk_cls = Mock(return_value=fake_ticker)

    as_of = datetime(2025, 1, 5, 13, 0, tzinfo=UTC)  # Sunday
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        assert gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of) is None

    fake_tk_cls.assert_not_called()
    fake_ticker.history.assert_not_called()


def test_get_premarket_price_ignores_bars_after_as_of():
    """A scan at 08:00 ET must not select later pre-market bars available in the frame."""
    # 2024-01-03. Bars at 12:59/13:00/13:30/14:00 UTC = 07:59/08:00/08:30/09:00 ET.
    times = pd.DatetimeIndex(
        [
            "2024-01-03 12:59",
            "2024-01-03 13:00",
            "2024-01-03 13:30",
            "2024-01-03 14:00",
        ],
        tz="UTC",
    )
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0, 103.0],
            "High": [101.0, 102.0, 103.0, 104.0],
            "Low": [99.0, 100.0, 101.0, 102.0],
            "Close": [101.0, 102.0, 103.0, 104.0],
            "Volume": [100, 100, 100, 100],
        },
        index=times,
    )

    fake_ticker = Mock()
    fake_ticker.history.return_value = df
    fake_tk_cls = Mock(return_value=fake_ticker)

    # as_of at 08:00 ET = 13:00 UTC. The 08:30 and 09:00 ET bars must be excluded.
    as_of = datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
    with (
        patch("tradex.premarket.sources.yf.Ticker", fake_tk_cls),
        patch.object(sources, "_today", return_value=as_of.date()),
    ):
        price = gap_scanner.get_premarket_price("AAPL", provider="yahoo", as_of=as_of)

    assert price == 102.0
    fake_tk_cls.assert_called_once()


def test_get_premarket_price_rejects_naive_as_of():
    with pytest.raises(ValueError):
        gap_scanner.get_premarket_price(
            "AAPL",
            provider="yahoo",
            as_of=datetime(2024, 1, 3, 8, 0),  # noqa: DTZ001
        )


def test_get_prev_close_rejects_naive_as_of():
    with pytest.raises(ValueError):
        gap_scanner._get_prev_close(
            "AAPL",
            provider="yahoo",
            as_of=datetime(2024, 1, 3, 8, 0),  # noqa: DTZ001
        )


def test_get_prev_close_tuesday_morning():
    """Tuesday pre-market selects Monday's close."""
    captured = {}

    def fake_history(ticker, start, end, provider=None, *, settings=None):
        captured["args"] = (ticker, start, end, provider)
        dates = pd.date_range("2025-01-06", periods=1, freq="B")
        return pd.DataFrame(
            {
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1000],
            },
            index=pd.DatetimeIndex(dates, name="datetime"),
            dtype=float,
        )

    as_of = datetime(2025, 1, 7, 8, 0, tzinfo=UTC)
    with patch.object(gap_scanner, "fetch_daily_history", side_effect=fake_history):
        close = gap_scanner._get_prev_close("AAPL", provider="yahoo", as_of=as_of)

    assert close == 100.0
    assert captured["args"] == ("AAPL", date(2025, 1, 6), date(2025, 1, 6), "yahoo")


def test_get_prev_close_monday_morning():
    """Monday pre-market selects Friday's close."""
    captured = {}

    def fake_history(ticker, start, end, provider=None, *, settings=None):
        captured["args"] = (ticker, start, end, provider)
        dates = pd.date_range("2025-01-03", periods=1, freq="B")
        return pd.DataFrame(
            {
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1000],
            },
            index=pd.DatetimeIndex(dates, name="datetime"),
            dtype=float,
        )

    as_of = datetime(2025, 1, 6, 8, 0, tzinfo=UTC)
    with patch.object(gap_scanner, "fetch_daily_history", side_effect=fake_history):
        close = gap_scanner._get_prev_close("AAPL", provider="yahoo", as_of=as_of)

    assert close == 100.0
    assert captured["args"] == ("AAPL", date(2025, 1, 3), date(2025, 1, 3), "yahoo")


def test_get_prev_close_after_holiday():
    """After a holiday, the most recent completed session is selected."""
    captured = {}

    def fake_history(ticker, start, end, provider=None, *, settings=None):
        captured["args"] = (ticker, start, end, provider)
        dates = pd.date_range("2024-12-31", periods=1, freq="B")
        return pd.DataFrame(
            {
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1000],
            },
            index=pd.DatetimeIndex(dates, name="datetime"),
            dtype=float,
        )

    as_of = datetime(2025, 1, 2, 8, 0, tzinfo=UTC)
    with patch.object(gap_scanner, "fetch_daily_history", side_effect=fake_history):
        close = gap_scanner._get_prev_close("AAPL", provider="yahoo", as_of=as_of)

    assert close == 100.0
    assert captured["args"] == ("AAPL", date(2024, 12, 31), date(2024, 12, 31), "yahoo")


def test_get_prev_close_propagates_provider_to_fetch_daily_history():
    """_get_prev_close forwards the provider to the daily-history abstraction."""
    captured = {}

    def fake_history(ticker, start, end, provider=None, *, settings=None):
        captured["provider"] = provider
        dates = pd.date_range("2025-01-06", periods=1, freq="B")
        return pd.DataFrame(
            {
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1000],
            },
            index=pd.DatetimeIndex(dates, name="datetime"),
            dtype=float,
        )

    as_of = datetime(2025, 1, 7, 8, 0, tzinfo=UTC)
    with patch.object(gap_scanner, "fetch_daily_history", side_effect=fake_history):
        gap_scanner._get_prev_close("AAPL", provider="schwab", as_of=as_of)

    assert captured["provider"] == "schwab"


def test_get_prev_close_empty_history_returns_none():
    as_of = datetime(2025, 1, 7, 8, 0, tzinfo=UTC)
    with patch.object(gap_scanner, "fetch_daily_history", return_value=pd.DataFrame()):
        assert gap_scanner._get_prev_close("AAPL", provider="yahoo", as_of=as_of) is None


def test_normalize_tickers_accepts_valid_symbols():
    assert gap_scanner._normalize_tickers(["aapl", "$AAPL", "BRK.B", "BRK-B"]) == [
        "AAPL",
        "BRK.B",
        "BRK-B",
    ]
    assert gap_scanner._normalize_tickers(["A", "ABCDEFGHIJ"]) == ["A", "ABCDEFGHIJ"]


def test_normalize_tickers_rejects_malformed_symbols():
    for bad in ["", "A@PL", "123", "A B", "ABCDEFGHIJK"]:
        with pytest.raises(ValueError):
            gap_scanner._normalize_tickers([bad])


def test_normalize_tickers_deduplicates():
    assert gap_scanner._normalize_tickers(["AAPL", "aapl", "$AAPL"]) == ["AAPL"]
