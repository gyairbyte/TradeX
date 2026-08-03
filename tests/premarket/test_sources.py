"""Tests for pre-market source adapters."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from tradex.data.fetcher import ProviderCapabilityError
from tradex.premarket import sources
from tradex.premarket.models import PremarketBarsResult, PremarketSnapshot, SpreadSnapshot


def _make_minute_bars() -> pd.DataFrame:
    times = pd.DatetimeIndex(["2024-01-03 09:00", "2024-01-03 10:00", "2024-01-03 11:00"], tz="UTC")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [101.0, 102.0, 103.0],
            "Volume": [100, 200, 300],
        },
        index=times,
    )


def test_resolve_premarket_provider_yahoo():
    assert sources.resolve_premarket_provider("yahoo") == "yahoo"
    assert sources.resolve_premarket_provider(None) == "yahoo"


def test_resolve_premarket_provider_rejects_unsupported():
    with pytest.raises(ProviderCapabilityError):
        sources.resolve_premarket_provider("schwab")
    with pytest.raises(ProviderCapabilityError):
        sources.resolve_premarket_provider("alpaca")


def test_resolve_premarket_provider_is_case_insensitive():
    assert sources.resolve_premarket_provider("YAHOO") == "yahoo"


def test_filter_premarket_bars_uses_session_date():
    df = _make_minute_bars()
    as_of = datetime(2024, 1, 3, 14, 0, tzinfo=UTC)  # 09:00 ET
    filtered = sources._filter_premarket_bars(df, date(2024, 1, 3), as_of, allow_after_open=False)
    assert len(filtered) == 3
    # 2024-01-03 is a Wednesday. 09:00/10:00/11:00 UTC = 04:00/05:00/06:00 ET.


def test_filter_premarket_bars_excludes_bars_after_as_of():
    df = _make_minute_bars()
    as_of = datetime(2024, 1, 3, 9, 30, tzinfo=UTC)  # 04:30 ET
    filtered = sources._filter_premarket_bars(df, date(2024, 1, 3), as_of, allow_after_open=False)
    assert len(filtered) == 1
    assert filtered["Close"].iloc[-1] == 101.0


def test_filter_premarket_bars_excludes_open_timestamp():
    # 2024-01-03 09:30 ET = 14:30 UTC.
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
    as_of = datetime(2024, 1, 3, 14, 15, tzinfo=UTC)
    filtered = sources._filter_premarket_bars(df, date(2024, 1, 3), as_of, allow_after_open=False)
    assert len(filtered) == 1
    assert filtered.index[0].hour == 14
    assert filtered.index[0].minute == 0


def test_build_premarket_snapshot():
    df = _make_minute_bars()
    df.columns = [c.lower() for c in df.columns]
    snap = sources.build_premarket_snapshot(
        df,
        ticker="AAPL",
        session_date=date(2024, 1, 3),
        as_of=datetime(2024, 1, 3, 14, 0, tzinfo=UTC),
        requested_provider="yahoo",
        actual_provider="yahoo",
    )
    assert isinstance(snap, PremarketSnapshot)
    assert snap.premarket_open == 100.0
    assert snap.premarket_high == 103.0
    assert snap.premarket_low == 99.0
    assert snap.premarket_last == 103.0
    assert snap.premarket_volume == 600
    assert snap.bar_count == 3
    assert snap.data_age_minutes is not None


def test_build_premarket_snapshot_empty_bars():
    snap = sources.build_premarket_snapshot(
        pd.DataFrame(),
        ticker="AAPL",
        session_date=date(2024, 1, 3),
        as_of=datetime(2024, 1, 3, 14, 0, tzinfo=UTC),
        requested_provider="yahoo",
        actual_provider="yahoo",
    )
    assert snap.premarket_last is None
    assert snap.premarket_volume == 0


def test_compute_liquidity_baseline():
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    df = pd.DataFrame(
        {
            "open": [100.0] * 5,
            "high": [101.0] * 5,
            "low": [99.0] * 5,
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            "volume": [1000, 2000, 3000, 4000, 5000],
        },
        index=pd.DatetimeIndex(dates, name="datetime"),
    )
    base = sources.compute_liquidity_baseline(
        df, lookback_sessions=5, target_session_date=date(2024, 1, 9)
    )
    assert base.lookback_sessions_available == 5
    assert base.average_daily_volume == 3000.0
    assert base.previous_close == 104.0  # most recent completed session


def test_fetch_daily_liquidity_baseline_propagates_provider():
    captured = {}

    def fake_daily_history(ticker, start, end, provider=None):
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

    with patch.object(sources, "fetch_daily_history", side_effect=fake_daily_history):
        base = sources.fetch_daily_liquidity_baseline(
            "AAPL",
            date(2025, 1, 7),
            lookback_sessions=1,
            provider="schwab",
        )
    assert captured["provider"] == "schwab"
    assert base.previous_close == 100.0


def test_fetch_premarket_bars_holiday_no_network():
    fake_tk = Mock()
    fake_cls = Mock(return_value=fake_tk)
    as_of = datetime(2025, 1, 1, 13, 0, tzinfo=UTC)
    with patch.object(sources.yf, "Ticker", fake_cls):
        result = sources.fetch_premarket_bars("AAPL", provider="yahoo", as_of=as_of)
    assert isinstance(result, PremarketBarsResult)
    assert result.bars.empty
    fake_cls.assert_not_called()


def test_get_premarket_price_wrapper():
    times = pd.DatetimeIndex(["2024-01-03 09:00", "2024-01-03 10:00", "2024-01-03 11:00"], tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [101.0, 102.0, 103.0],
            "Volume": [100, 200, 300],
        },
        index=times,
    )
    fake_ticker = Mock()
    fake_ticker.history.return_value = df
    fake_cls = Mock(return_value=fake_ticker)
    as_of = datetime(2024, 1, 3, 14, 0, tzinfo=UTC)
    with (
        patch.object(sources.yf, "Ticker", fake_cls),
        patch.object(sources, "_today", return_value=date(2024, 1, 3)),
    ):
        price = sources.get_premarket_price("AAPL", provider="yahoo", as_of=as_of)
    assert price == 103.0
    fake_ticker.history.assert_called_once()
    _, kwargs = fake_ticker.history.call_args
    assert kwargs["start"] == date(2024, 1, 2)
    assert kwargs["end"] == date(2024, 1, 4)
    assert kwargs["interval"] == "1m"
    assert kwargs["prepost"] is True


def test_get_prev_close_wrapper():
    dates = pd.date_range("2024-01-02", periods=2, freq="B")
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000, 1000],
        },
        index=pd.DatetimeIndex(dates, name="datetime"),
        dtype=float,
    )
    with patch.object(sources, "fetch_daily_history", return_value=df):
        close = sources._get_prev_close(
            "AAPL", provider="yahoo", as_of=datetime(2024, 1, 4, 8, 0, tzinfo=UTC)
        )
    assert close == 102.0


def test_fetch_spread_snapshot_from_quote():
    as_of = datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
    snap = sources.fetch_spread_snapshot(
        "AAPL",
        as_of,
        provider="yahoo",
        quote={"bid": 100.0, "ask": 100.05, "as_of": as_of},
    )
    assert snap.available is True
    assert snap.bid == 100.0
    assert snap.ask == 100.05
    assert snap.spread_bps == pytest.approx(5.0, rel=1e-3)


def test_fetch_spread_snapshot_rejects_crossed():
    snap = sources.fetch_spread_snapshot(
        "AAPL",
        datetime(2024, 1, 3, 13, 0, tzinfo=UTC),
        provider="yahoo",
        quote={"bid": 100.05, "ask": 100.0},
    )
    assert snap.available is False
    assert snap.error is not None


def test_fetch_spread_snapshot_default_unavailable():
    snap = sources.fetch_spread_snapshot(
        "AAPL", datetime(2024, 1, 3, 13, 0, tzinfo=UTC), provider="yahoo"
    )
    assert isinstance(snap, SpreadSnapshot)
    assert snap.available is False
    assert snap.source == "yahoo"


def _valid_bars() -> pd.DataFrame:
    times = pd.DatetimeIndex(["2024-01-03 09:00", "2024-01-03 10:00"], tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [100, 200],
        },
        index=times,
    )


def test_validate_ohlcv_rejects_missing_columns():
    df = _valid_bars().drop(columns=["close"])
    with pytest.raises(sources.DataValidationError, match="Missing required"):
        sources.build_premarket_snapshot(
            df, ticker="AAPL", session_date=date(2024, 1, 3),
            as_of=datetime(2024, 1, 3, 14, 0, tzinfo=UTC),
            requested_provider="yahoo", actual_provider="yahoo",
        )


def test_validate_ohlcv_rejects_nonfinite_prices():
    df = _valid_bars()
    df.loc[df.index[0], "open"] = float("nan")
    with pytest.raises(sources.DataValidationError, match="finite"):
        sources.build_premarket_snapshot(
            df, ticker="AAPL", session_date=date(2024, 1, 3),
            as_of=datetime(2024, 1, 3, 14, 0, tzinfo=UTC),
            requested_provider="yahoo", actual_provider="yahoo",
        )


def test_validate_ohlcv_rejects_nonpositive_prices():
    df = _valid_bars()
    df.loc[df.index[0], "low"] = 0.0
    with pytest.raises(sources.DataValidationError, match="positive"):
        sources.build_premarket_snapshot(
            df, ticker="AAPL", session_date=date(2024, 1, 3),
            as_of=datetime(2024, 1, 3, 14, 0, tzinfo=UTC),
            requested_provider="yahoo", actual_provider="yahoo",
        )


def test_validate_ohlcv_rejects_negative_volume():
    df = _valid_bars()
    df.loc[df.index[0], "volume"] = -1
    with pytest.raises(sources.DataValidationError, match="non-negative"):
        sources.build_premarket_snapshot(
            df, ticker="AAPL", session_date=date(2024, 1, 3),
            as_of=datetime(2024, 1, 3, 14, 0, tzinfo=UTC),
            requested_provider="yahoo", actual_provider="yahoo",
        )


def test_validate_ohlcv_rejects_invalid_high_low():
    df = _valid_bars()
    df.loc[df.index[0], "low"] = 102.0
    with pytest.raises(sources.DataValidationError, match="low"):
        sources.build_premarket_snapshot(
            df, ticker="AAPL", session_date=date(2024, 1, 3),
            as_of=datetime(2024, 1, 3, 14, 0, tzinfo=UTC),
            requested_provider="yahoo", actual_provider="yahoo",
        )


def test_validate_ohlcv_rejects_open_outside_high_low():
    df = _valid_bars()
    df.loc[df.index[0], "open"] = 98.0
    with pytest.raises(sources.DataValidationError, match="open"):
        sources.build_premarket_snapshot(
            df, ticker="AAPL", session_date=date(2024, 1, 3),
            as_of=datetime(2024, 1, 3, 14, 0, tzinfo=UTC),
            requested_provider="yahoo", actual_provider="yahoo",
        )


def test_validate_ohlcv_rejects_mixed_valid_invalid_rows():
    """A single malformed row must reject the entire provider response."""
    df = _valid_bars()
    df.loc[df.index[1], "close"] = 200.0  # outside high/low
    with pytest.raises(sources.DataValidationError, match="close"):
        sources.build_premarket_snapshot(
            df, ticker="AAPL", session_date=date(2024, 1, 3),
            as_of=datetime(2024, 1, 3, 14, 0, tzinfo=UTC),
            requested_provider="yahoo", actual_provider="yahoo",
        )
