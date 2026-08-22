"""Tests for earnings-calendar source policy."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from tradex.config import settings_from_mapping
from tradex.data.fetcher import ProviderCapabilityError
from tradex.earnings import calendar


def _make_earnings_db(tmp_path: Path):
    """Point the earnings cache at a temporary SQLite path for the test."""
    db_path = tmp_path / "earnings_cache.db"
    calendar.CACHE_DIR = tmp_path
    calendar.CACHE_DB = db_path
    return settings_from_mapping({"TRADEX_EARNINGS_CACHE_PATH": str(db_path)})


def test_resolve_earnings_source_defaults_to_yahoo(monkeypatch):
    monkeypatch.delenv("EARNINGS_DATA_SOURCE", raising=False)
    assert calendar._resolve_earnings_source(None) == "yahoo"


def test_resolve_earnings_source_rejects_unsupported():
    with pytest.raises(ProviderCapabilityError):
        calendar._resolve_earnings_source("schwab")


def test_get_next_earnings_yahoo_and_cache(tmp_path):
    settings = _make_earnings_db(tmp_path)
    future = datetime.now(UTC).date() + timedelta(days=7)
    df = pd.DataFrame(
        {"Reported EPS": [1.0]},
        index=pd.to_datetime([future.isoformat()], utc=True),
    )
    fake_ticker = Mock(get_earnings_dates=Mock(return_value=df))

    with patch.object(calendar.yf, "Ticker", return_value=fake_ticker):
        result1 = calendar.get_next_earnings("AAPL", source="yahoo", settings=settings)
        result2 = calendar.get_next_earnings("AAPL", source="yahoo", settings=settings)

    assert result1 == future
    assert result2 == future
    # Cache should prevent a second network call.
    fake_ticker.get_earnings_dates.assert_called_once()


def test_get_next_earnings_unsupported_source():
    with pytest.raises(ProviderCapabilityError):
        calendar.get_next_earnings("AAPL", source="schwab")


def test_days_until_earnings():
    future = date(2099, 1, 1)
    with patch.object(calendar, "get_next_earnings", return_value=future):
        days = calendar.days_until_earnings("AAPL")
    assert days is not None
    assert days > 0


def test_annotate_returns_source_agnostic_and_data_provider_not_relabeled():
    """DATA_PROVIDER=schwab must not relabel Yahoo earnings."""
    future = date(2099, 1, 1)
    with patch.object(calendar, "get_next_earnings", return_value=future):
        df = calendar.annotate(["AAPL"], source="yahoo")

    assert df.iloc[0]["ticker"] == "AAPL"
    assert df.iloc[0]["days_until"] is not None


def test_cache_null_not_treated_as_fresh(tmp_path):
    """Cached NULL/empty rows are treated as stale/non-authoritative."""
    settings = _make_earnings_db(tmp_path)
    # Manually insert a row with NULL next_earnings
    with calendar._conn(settings.paths.earnings_cache_db) as c:
        c.execute(
            "INSERT INTO earnings_cache (ticker, source, next_earnings, fetched_at) VALUES (?, ?, ?, ?)",
            ("XYZ", "yahoo", None, datetime.now(UTC).replace(tzinfo=None).isoformat()),
        )
    cached_date, is_fresh = calendar._cache_get("XYZ", "yahoo", settings=settings)
    assert cached_date is None
    assert is_fresh is False


def test_cache_put_does_not_store_none(tmp_path):
    """Calling _cache_put with next_earnings=None must not write to the cache."""
    settings = _make_earnings_db(tmp_path)
    calendar._cache_put("SPY", "yahoo", None, settings=settings)
    with calendar._conn(settings.paths.earnings_cache_db) as c:
        row = c.execute("SELECT * FROM earnings_cache WHERE ticker = ?", ("SPY",)).fetchone()
    assert row is None


def test_get_next_earnings_handles_yfinance_exception_safely(tmp_path):
    """Network or parsing errors return None without crashing or caching NULL."""
    settings = _make_earnings_db(tmp_path)
    fake_ticker = Mock(
        get_earnings_dates=Mock(side_effect=RuntimeError("Yahoo API connection reset")),
        calendar={},
    )
    with patch.object(calendar.yf, "Ticker", return_value=fake_ticker):
        result = calendar.get_next_earnings("BADTICKER", source="yahoo", settings=settings)
    assert result is None
    # Verify no row was cached for BADTICKER
    with calendar._conn(settings.paths.earnings_cache_db) as c:
        row = c.execute("SELECT * FROM earnings_cache WHERE ticker = ?", ("BADTICKER",)).fetchone()
    assert row is None
