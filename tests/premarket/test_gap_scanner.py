"""Tests for pre-market gap scanner source separation."""
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from tradex.data.fetcher import ProviderCapabilityError
from tradex.premarket import gap_scanner


def _make_daily_history(values, start: str = "2024-01-02") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(values), freq="B")
    return pd.DataFrame({
        "open": values, "high": [v + 1 for v in values], "low": [v - 1 for v in values],
        "close": values, "volume": [1000] * len(values),
    }, index=pd.DatetimeIndex(dates, name="datetime"), dtype=float)


def test_get_prev_close_propagates_provider():
    """_get_prev_close passes the provider to fetch_daily_history."""
    captured = []

    def fake_history(ticker, start, end, provider=None):
        captured.append((ticker, start, end, provider))
        return _make_daily_history([100.0, 101.0, 102.0])

    with patch.object(gap_scanner, "fetch_daily_history", side_effect=fake_history):
        close = gap_scanner._get_prev_close("AAPL", provider="schwab")

    assert close == 102.0
    today = datetime.now(UTC).date()
    assert captured == [("AAPL", today - pd.Timedelta(days=7), today, "schwab")]


def test_get_prev_close_returns_none_on_missing_data():
    with patch.object(gap_scanner, "fetch_daily_history", return_value=pd.DataFrame()):
        assert gap_scanner._get_prev_close("AAPL", provider="yahoo") is None


def test_get_premarket_price_yahoo():
    """Yahoo pre-market price uses 1m prepost history and returns the last pre-9:30am bar."""
    times = pd.date_range("2024-01-03 08:30", periods=3, freq="30min", tz="UTC")
    df = pd.DataFrame({
        "Open": [100.0, 101.0, 103.0],
        "High": [101.0, 102.0, 104.0],
        "Low": [99.0, 100.0, 102.0],
        "Close": [101.0, 102.0, 103.0],
        "Volume": [100, 100, 100],
    }, index=times)

    fake_ticker = Mock()
    fake_ticker.history.return_value = df
    fake_tk_cls = Mock(return_value=fake_ticker)

    with patch.object(gap_scanner.yf, "Ticker", fake_tk_cls):
        price = gap_scanner.get_premarket_price("AAPL", provider="yahoo")

    assert price == 103.0
    fake_ticker.history.assert_called_once()
    _, kwargs = fake_ticker.history.call_args
    assert kwargs["period"] == "1d"
    assert kwargs["interval"] == "1m"
    assert kwargs["prepost"] is True


def test_get_premarket_price_unsupported_provider():
    with pytest.raises(ProviderCapabilityError):
        gap_scanner.get_premarket_price("AAPL", provider="schwab")


def test_get_premarket_price_returns_none_for_empty():
    fake_ticker = Mock()
    fake_ticker.history.return_value = pd.DataFrame()
    fake_tk_cls = Mock(return_value=fake_ticker)

    with patch.object(gap_scanner.yf, "Ticker", fake_tk_cls):
        assert gap_scanner.get_premarket_price("AAPL", provider="yahoo") is None


def test_scan_gaps_propagates_provider():
    """scan_gaps passes provider to both previous-close and pre-market quote paths."""
    with (
        patch.object(gap_scanner, "_get_prev_close", return_value=100.0) as mock_prev,
        patch.object(gap_scanner, "get_premarket_price", return_value=105.0) as mock_pre,
    ):
        result = gap_scanner.scan_gaps(["AAPL"], min_gap_pct=2.0, provider="yahoo")

    mock_prev.assert_called_once_with("AAPL", provider="yahoo")
    mock_pre.assert_called_once_with("AAPL", provider="yahoo")
    assert not result.empty
    assert result.iloc[0]["ticker"] == "AAPL"
    assert result.iloc[0]["gap_pct"] == 5.0


def test_scan_gaps_unsupported_provider_raises():
    """scan_gaps must not silently fall back when an unsupported provider is selected."""
    with (
        patch.object(gap_scanner, "_get_prev_close", side_effect=ProviderCapabilityError("no schwab premarket")),
        pytest.raises(ProviderCapabilityError),
    ):
        gap_scanner.scan_gaps(["AAPL"], min_gap_pct=2.0, provider="schwab")


def test_scan_gaps_empty_returns_empty_df():
    with (
        patch.object(gap_scanner, "_get_prev_close", return_value=100.0),
        patch.object(gap_scanner, "get_premarket_price", return_value=100.0),
    ):
        result = gap_scanner.scan_gaps(["AAPL"], min_gap_pct=2.0, provider="yahoo")
    assert result.empty


def test_run_gap_alerts_propagates_provider():
    """run_gap_alerts passes provider to scan_gaps and surfaces provider errors safely."""
    with (
        patch.object(gap_scanner, "scan_gaps", return_value=pd.DataFrame()) as mock_scan,
        patch("tradex.alerts.notifier.alert_gap") as mock_alert,
    ):
        gap_scanner.run_gap_alerts(["AAPL"], min_gap_pct=4.0, provider="yahoo")

    mock_scan.assert_called_once_with(["AAPL"], min_gap_pct=4.0, provider="yahoo")
    mock_alert.assert_not_called()


def test_run_gap_alerts_returns_empty_on_provider_error():
    with patch.object(gap_scanner, "scan_gaps", side_effect=ProviderCapabilityError("unsupported")):
        result = gap_scanner.run_gap_alerts(["AAPL"], min_gap_pct=4.0, provider="schwab")
    assert result.empty
