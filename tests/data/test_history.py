"""Tests for the date-ranged daily-history abstraction."""
from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from tradex.data import history
from tradex.data.fetcher import ProviderCapabilityError


def _make_yahoo_ohlcv(values, start: str = "2024-01-02", ticker: str = "AAPL") -> pd.DataFrame:
    """Return a yfinance-style DataFrame with full OHLCV columns."""
    dates = pd.date_range(start, periods=len(values), freq="B")
    return pd.DataFrame({
        "Open": values,
        "High": [v + 1.0 for v in values],
        "Low": [v - 1.0 for v in values],
        "Close": values,
        "Volume": [1000] * len(values),
    }, index=dates)


def _make_multiindex_yahoo(values, ticker: str = "AAPL") -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=len(values), freq="B")
    columns = pd.MultiIndex.from_tuples(
        [(field, ticker) for field in ["Open", "High", "Low", "Close", "Volume"]]
    )
    data = {
        "Open": values,
        "High": [v + 1.0 for v in values],
        "Low": [v - 1.0 for v in values],
        "Close": values,
        "Volume": [1000] * len(values),
    }
    df = pd.DataFrame(data, index=dates)
    df.columns = columns
    return df


def test_fetch_daily_history_resolves_default_provider(monkeypatch):
    """When provider is None, DATA_PROVIDER env var is used."""
    monkeypatch.setattr(history, "DEFAULT_PROVIDER", "alpaca")
    with pytest.raises(ProviderCapabilityError):
        history.fetch_daily_history("AAPL", date(2024, 1, 1), date(2024, 1, 5))


def test_fetch_daily_history_rejects_invalid_provider():
    with pytest.raises(ValueError):
        history.fetch_daily_history("AAPL", date(2024, 1, 1), date(2024, 1, 5), provider="bad")


def test_fetch_daily_history_yahoo_normalization():
    values = [100.0, 101.0, 102.0]
    df_in = _make_yahoo_ohlcv(values)

    with patch.object(history.yf, "download", return_value=df_in) as mock_download:
        df = history.fetch_daily_history("AAPL", date(2024, 1, 2), date(2024, 1, 4))

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert list(df.index) == list(df_in.index)
    assert df["close"].tolist() == values
    assert df.index.name == "datetime"
    assert df.index.tz is not None

    # Yahoo's end argument is exclusive; the abstraction adds one day.
    _, kwargs = mock_download.call_args
    assert kwargs["start"] == "2024-01-02"
    assert kwargs["end"] == "2024-01-05"


def test_fetch_daily_history_multiindex_columns():
    df_in = _make_multiindex_yahoo([100.0, 101.0, 102.0])

    with patch.object(history.yf, "download", return_value=df_in):
        df = history.fetch_daily_history("AAPL", date(2024, 1, 2), date(2024, 1, 4))

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["close"].tolist() == [100.0, 101.0, 102.0]


def test_fetch_daily_history_empty_data():
    with patch.object(history.yf, "download", return_value=pd.DataFrame()):
        df = history.fetch_daily_history("AAPL", date(2024, 1, 2), date(2024, 1, 4))

    assert df.empty
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.name == "datetime"


def test_fetch_daily_history_missing_fields():
    # Only close provided; the abstraction fills missing columns and preserves the row.
    df_in = pd.DataFrame({"Close": [100.0, 101.0]}, index=pd.date_range("2024-01-02", periods=2, freq="B"))
    with patch.object(history.yf, "download", return_value=df_in):
        df = history.fetch_daily_history("AAPL", date(2024, 1, 2), date(2024, 1, 3))
    assert df["close"].tolist() == [100.0, 101.0]


def test_fetch_daily_history_sorts_and_deduplicates():
    dates = ["2024-01-04", "2024-01-02", "2024-01-03", "2024-01-03"]
    values = [103.0, 101.0, 102.0, 999.0]
    df_in = pd.DataFrame({
        "Open": values, "High": [v + 1 for v in values], "Low": [v - 1 for v in values],
        "Close": values, "Volume": [1000] * 4,
    }, index=pd.to_datetime(dates))

    with patch.object(history.yf, "download", return_value=df_in):
        df = history.fetch_daily_history("AAPL", date(2024, 1, 2), date(2024, 1, 4))

    # Duplicates keep the last occurrence, then rows are sorted oldest-to-newest.
    assert df["close"].tolist() == [101.0, 999.0, 103.0]
    assert len(df) == 3


def test_fetch_daily_history_unsupported_providers_raise():
    for provider in ("alpaca", "ibkr"):
        with pytest.raises(ProviderCapabilityError):
            history.fetch_daily_history("AAPL", date(2024, 1, 1), date(2024, 1, 5), provider=provider)


def test_fetch_daily_history_schwab_path():
    """Schwab daily history should use the read-only market-data endpoint."""
    fake_client = Mock()
    fake_client.get_price_history_every_day.return_value = Mock(
        status_code=200,
        raise_for_status=Mock(),
        json=Mock(return_value={
            "candles": [
                {"datetime": 1704153600000, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
                {"datetime": 1704240000000, "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1100},
            ]
        }),
    )

    with patch("tradex.data.history._get_schwab_client", return_value=fake_client):
        df = history.fetch_daily_history("AAPL", date(2024, 1, 2), date(2024, 1, 3), provider="schwab")

    assert len(df) == 2
    assert df["close"].tolist() == [100.5, 101.5]
    call = fake_client.get_price_history_every_day.call_args
    assert call.kwargs["start_datetime"].date() == date(2024, 1, 2)
    assert call.kwargs["end_datetime"].date() == date(2024, 1, 3)


def test_fetch_daily_history_schwab_retains_session_with_missing_close():
    """Daily history should keep a session that has other data but a missing close
    so COR-003 outcome counting does not shift."""
    fake_client = Mock()
    fake_client.get_price_history_every_day.return_value = Mock(
        status_code=200,
        raise_for_status=Mock(),
        json=Mock(return_value={
            "candles": [
                {"datetime": 1704153600000, "open": 100.0, "high": 101.0, "low": 99.0, "close": None, "volume": 1000},
                {"datetime": 1704240000000, "open": 101.0, "high": 102.0, "low": 100.0, "close": 102.0, "volume": 1100},
            ]
        }),
    )

    with patch("tradex.data.history._get_schwab_client", return_value=fake_client):
        df = history.fetch_daily_history("AAPL", date(2024, 1, 2), date(2024, 1, 3), provider="schwab")

    assert len(df) == 2
    assert pd.isna(df["close"].iloc[0])
    assert df["close"].iloc[1] == 102.0
    assert df["volume"].iloc[0] == 1000


def test_fetch_daily_history_schwab_bad_response():
    fake_client = Mock()
    fake_client.get_price_history_every_day.return_value = Mock(
        status_code=500,
        raise_for_status=Mock(side_effect=Exception("server error")),
        json=Mock(),
    )

    with (
        patch("tradex.data.history._get_schwab_client", return_value=fake_client),
        pytest.raises(RuntimeError),
    ):
        history.fetch_daily_history("AAPL", date(2024, 1, 2), date(2024, 1, 3), provider="schwab")
