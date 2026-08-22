"""Tests for earnings-calendar source policy and failure handling."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from tradex.config import settings_from_mapping
from tradex.data.fetcher import ProviderCapabilityError
from tradex.earnings import calendar
from tradex.earnings.calendar import EarningsDataUnavailableError


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
    """1. Valid future date from get_earnings_dates -> known date, cached."""
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


def test_get_next_earnings_first_fails_calendar_fallback_succeeds(tmp_path):
    """2. First Yahoo method fails, calendar fallback returns valid future date -> known date."""
    settings = _make_earnings_db(tmp_path)
    future = datetime.now(UTC).date() + timedelta(days=10)
    fake_ticker = Mock(
        get_earnings_dates=Mock(side_effect=RuntimeError("Yahoo API connection reset")),
        calendar={"Earnings Date": [future]},
    )

    with patch.object(calendar.yf, "Ticker", return_value=fake_ticker):
        result = calendar.get_next_earnings("MSFT", source="yahoo", settings=settings)

    assert result == future


def test_get_next_earnings_both_methods_fail_raises_unavailable(tmp_path):
    """3. Both lookup methods fail -> explicit unavailable/failure, not None."""
    settings = _make_earnings_db(tmp_path)
    fake_ticker = Mock(
        get_earnings_dates=Mock(side_effect=RuntimeError("Yahoo API connection reset")),
        calendar=Mock(side_effect=RuntimeError("calendar endpoint error")),
    )

    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(EarningsDataUnavailableError) as exc_info,
    ):
        calendar.get_next_earnings("BADTICKER", source="yahoo", settings=settings)

    assert "Upcoming earnings date unavailable for BADTICKER" in str(exc_info.value)
    # Verify no row was cached for BADTICKER
    with calendar._conn(settings.paths.earnings_cache_db) as c:
        row = c.execute("SELECT * FROM earnings_cache WHERE ticker = ?", ("BADTICKER",)).fetchone()
    assert row is None


def test_get_next_earnings_both_methods_return_no_future_date_raises_unavailable(tmp_path):
    """4. Both methods return no usable future date -> explicit unavailable/unknown."""
    settings = _make_earnings_db(tmp_path)
    past = datetime.now(UTC).date() - timedelta(days=30)
    past_df = pd.DataFrame(
        {"Reported EPS": [1.0]},
        index=pd.to_datetime([past.isoformat()], utc=True),
    )
    fake_ticker = Mock(
        get_earnings_dates=Mock(return_value=past_df),
        calendar={"Earnings Date": [past]},
    )

    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(EarningsDataUnavailableError) as exc_info,
    ):
        calendar.get_next_earnings("SPY", source="yahoo", settings=settings)

    assert "Upcoming earnings date unavailable for SPY" in str(exc_info.value)
    # 5. No unavailable/unknown state is cached as authoritative absence.
    with calendar._conn(settings.paths.earnings_cache_db) as c:
        row = c.execute("SELECT * FROM earnings_cache WHERE ticker = ?", ("SPY",)).fetchone()
    assert row is None


def test_get_next_earnings_unsupported_source():
    with pytest.raises(ProviderCapabilityError):
        calendar.get_next_earnings("AAPL", source="schwab")


def test_days_until_earnings():
    future = datetime.now(UTC).date() + timedelta(days=14)
    with patch.object(calendar, "get_next_earnings", return_value=future):
        days = calendar.days_until_earnings("AAPL")
    assert days == 14


def test_days_until_earnings_raises_when_unavailable():
    with (
        patch.object(
            calendar,
            "get_next_earnings",
            side_effect=EarningsDataUnavailableError("Upcoming earnings date unavailable for AAPL"),
        ),
        pytest.raises(EarningsDataUnavailableError),
    ):
        calendar.days_until_earnings("AAPL")


def test_is_within_earnings_window():
    """is_within_earnings_window returns boolean when date is known, raises when unavailable."""
    future_in_window = datetime.now(UTC).date() + timedelta(days=3)
    with patch.object(calendar, "get_next_earnings", return_value=future_in_window):
        assert calendar.is_within_earnings_window("AAPL", within_days=5) is True
        assert calendar.is_within_earnings_window("AAPL", within_days=2) is False

    with (
        patch.object(
            calendar,
            "get_next_earnings",
            side_effect=EarningsDataUnavailableError("Upcoming earnings date unavailable for AAPL"),
        ),
        pytest.raises(EarningsDataUnavailableError),
    ):
        calendar.is_within_earnings_window("AAPL", within_days=5)


def test_annotate_preserves_explicit_status_and_columns():
    """annotate returns known status for valid dates, unavailable for failures, and preserves existing columns."""
    future = datetime.now(UTC).date() + timedelta(days=10)

    def fake_get_next_earnings(ticker, **_):
        if ticker == "AAPL":
            return future
        if ticker == "FAIL":
            raise EarningsDataUnavailableError(f"Upcoming earnings date unavailable for {ticker}")
        if ticker == "BADSRC":
            raise ProviderCapabilityError("Earnings source 'schwab' is not supported")
        return future

    with patch.object(calendar, "get_next_earnings", side_effect=fake_get_next_earnings):
        df = calendar.annotate(["AAPL", "FAIL", "BADSRC"], source="yahoo")

    assert len(df) == 3
    # AAPL: known
    aapl = df[df["ticker"] == "AAPL"].iloc[0]
    assert aapl["next_earnings"] == future
    assert aapl["days_until"] == 10
    assert aapl["earnings_status"] == "known"
    assert pd.isna(aapl["error_category"]) or aapl["error_category"] is None
    assert pd.isna(aapl["error_message"]) or aapl["error_message"] is None

    # FAIL: unavailable
    fail = df[df["ticker"] == "FAIL"].iloc[0]
    assert pd.isna(fail["next_earnings"]) or fail["next_earnings"] is None
    assert pd.isna(fail["days_until"]) or fail["days_until"] is None
    assert fail["earnings_status"] == "unavailable"
    assert fail["error_category"] == "EarningsDataUnavailableError"
    assert "Upcoming earnings date unavailable for FAIL" in fail["error_message"]

    # BADSRC: capability error
    badsrc = df[df["ticker"] == "BADSRC"].iloc[0]
    assert pd.isna(badsrc["next_earnings"]) or badsrc["next_earnings"] is None
    assert badsrc["earnings_status"] == "unavailable"
    assert badsrc["error_category"] == "ProviderCapabilityError"
    assert "not supported" in badsrc["error_message"]


def test_cache_null_not_treated_as_fresh(tmp_path):
    """6. Cached NULL/empty rows are treated as stale/non-authoritative."""
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


def test_safe_error_text_contains_no_secrets():
    """7. Safe error text contains no raw secret/token/body."""
    err = EarningsDataUnavailableError("Upcoming earnings date unavailable for SECRET_TICKER")
    msg = str(err)
    assert "SECRET_TICKER" in msg
    assert "token" not in msg.lower()
    assert "key" not in msg.lower()
    assert "password" not in msg.lower()
    assert "secret" not in msg.lower() or "SECRET_TICKER" in msg
