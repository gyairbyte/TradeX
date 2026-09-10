"""Tests for earnings-calendar source policy and failure handling."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from tradex.config import settings_from_mapping
from tradex.data.fetcher import ProviderCapabilityError
from tradex.earnings import calendar
from tradex.earnings.calendar import (
    EarningsDataUnavailableError,
    EarningsProviderLookupError,
    EarningsProviderResponseError,
)


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


class FakeTicker:
    """Explicit fake for yfinance Ticker that cleanly simulates method and property behavior."""

    def __init__(
        self,
        *,
        dates_df: Any = None,
        dates_exc: Exception | None = None,
        calendar_val: Any = None,
        calendar_exc: Exception | None = None,
    ):
        self._dates_df = dates_df
        self._dates_exc = dates_exc
        self._calendar_val = calendar_val
        self._calendar_exc = calendar_exc
        self.get_earnings_dates_call_count = 0

    def get_earnings_dates(self, limit: int = 12) -> Any:
        self.get_earnings_dates_call_count += 1
        if self._dates_exc is not None:
            raise self._dates_exc
        return self._dates_df

    @property
    def calendar(self) -> Any:
        if self._calendar_exc is not None:
            raise self._calendar_exc
        return self._calendar_val


def test_get_next_earnings_yahoo_and_cache(tmp_path):
    """1. Valid future date from get_earnings_dates -> known date, cached."""
    settings = _make_earnings_db(tmp_path)
    future = date.today() + timedelta(days=7)  # noqa: DTZ011
    df = pd.DataFrame(
        {"Reported EPS": [1.0]},
        index=pd.to_datetime([future.isoformat()], utc=True),
    )
    fake_ticker = FakeTicker(dates_df=df)

    with patch.object(calendar.yf, "Ticker", return_value=fake_ticker):
        result1 = calendar.get_next_earnings("AAPL", source="yahoo", settings=settings)
        result2 = calendar.get_next_earnings("AAPL", source="yahoo", settings=settings)

    assert result1 == future
    assert result2 == future
    # Cache should prevent a second network call.
    assert fake_ticker.get_earnings_dates_call_count == 1


def test_get_next_earnings_first_fails_calendar_fallback_succeeds(tmp_path):
    """2. First Yahoo method fails, calendar fallback returns valid future date -> known date."""
    settings = _make_earnings_db(tmp_path)
    future = date.today() + timedelta(days=10)  # noqa: DTZ011
    fake_ticker = FakeTicker(
        dates_exc=RuntimeError("Yahoo API connection reset"),
        calendar_val={"Earnings Date": [future]},
    )

    with patch.object(calendar.yf, "Ticker", return_value=fake_ticker):
        result = calendar.get_next_earnings("MSFT", source="yahoo", settings=settings)

    assert result == future


def test_get_next_earnings_first_clean_empty_calendar_fallback_succeeds(tmp_path):
    """Valid future date from calendar fallback when get_earnings_dates is clean empty."""
    settings = _make_earnings_db(tmp_path)
    future = date.today() + timedelta(days=12)  # noqa: DTZ011
    fake_ticker = FakeTicker(
        dates_df=pd.DataFrame(),
        calendar_val={"Earnings Date": [future]},
    )

    with patch.object(calendar.yf, "Ticker", return_value=fake_ticker):
        result = calendar.get_next_earnings("NVDA", source="yahoo", settings=settings)

    assert result == future


def test_get_next_earnings_both_methods_fail_raises_lookup_error(tmp_path):
    """Both lookup methods fail -> typed technical provider failure with chained cause."""
    settings = _make_earnings_db(tmp_path)
    fake_ticker = FakeTicker(
        dates_exc=RuntimeError("Yahoo API connection reset"),
        calendar_exc=RuntimeError("calendar endpoint error"),
    )

    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(EarningsProviderLookupError) as exc_info,
    ):
        calendar.get_next_earnings("BADTICKER", source="yahoo", settings=settings)

    assert "Earnings provider lookup failed for BADTICKER" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    # Verify no row was cached for BADTICKER
    with calendar._conn(settings.paths.earnings_cache_db) as c:
        row = c.execute("SELECT * FROM earnings_cache WHERE ticker = ?", ("BADTICKER",)).fetchone()
    assert row is None


def test_get_next_earnings_first_fails_calendar_clean_empty_raises_lookup_error(tmp_path):
    """Technical failure + clean empty -> technical provider failure, not UNAVAILABLE."""
    settings = _make_earnings_db(tmp_path)
    fake_ticker = FakeTicker(
        dates_exc=RuntimeError("Yahoo API connection reset"),
        calendar_val={},
    )

    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(EarningsProviderLookupError) as exc_info,
    ):
        calendar.get_next_earnings("FAIL1", source="yahoo", settings=settings)

    assert "Earnings provider lookup failed for FAIL1" in str(exc_info.value)
    with calendar._conn(settings.paths.earnings_cache_db) as c:
        row = c.execute("SELECT * FROM earnings_cache WHERE ticker = ?", ("FAIL1",)).fetchone()
    assert row is None


def test_get_next_earnings_first_clean_empty_calendar_fails_raises_lookup_error(tmp_path):
    """Clean empty + technical failure -> technical provider failure, not UNAVAILABLE."""
    settings = _make_earnings_db(tmp_path)
    fake_ticker = FakeTicker(
        dates_df=pd.DataFrame(),
        calendar_exc=RuntimeError("calendar endpoint error"),
    )

    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(EarningsProviderLookupError) as exc_info,
    ):
        calendar.get_next_earnings("FAIL2", source="yahoo", settings=settings)

    assert "Earnings provider lookup failed for FAIL2" in str(exc_info.value)
    with calendar._conn(settings.paths.earnings_cache_db) as c:
        row = c.execute("SELECT * FROM earnings_cache WHERE ticker = ?", ("FAIL2",)).fetchone()
    assert row is None


def test_get_next_earnings_both_methods_return_no_future_date_raises_unavailable(tmp_path):
    """Both methods return no usable future date cleanly -> clean EarningsDataUnavailableError."""
    settings = _make_earnings_db(tmp_path)
    past = date.today() - timedelta(days=30)  # noqa: DTZ011
    past_df = pd.DataFrame(
        {"Reported EPS": [1.0]},
        index=pd.to_datetime([past.isoformat()], utc=True),
    )
    fake_ticker = FakeTicker(
        dates_df=past_df,
        calendar_val={"Earnings Date": [past]},
    )

    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(EarningsDataUnavailableError) as exc_info,
    ):
        calendar.get_next_earnings("SPY", source="yahoo", settings=settings)

    assert "Upcoming earnings date unavailable for SPY" in str(exc_info.value)
    # No unavailable/unknown state is cached as authoritative absence.
    with calendar._conn(settings.paths.earnings_cache_db) as c:
        row = c.execute("SELECT * FROM earnings_cache WHERE ticker = ?", ("SPY",)).fetchone()
    assert row is None


def test_get_next_earnings_malformed_dataframe_raises_response_error(tmp_path):
    """Non-empty DataFrame with all unparseable index values raises EarningsProviderResponseError."""
    settings = _make_earnings_db(tmp_path)
    df = pd.DataFrame({"EPS": [1.0]}, index=["not-a-date"])
    fake_ticker = FakeTicker(
        dates_df=df,
        calendar_val={},
    )

    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(EarningsProviderResponseError) as exc_info,
    ):
        calendar.get_next_earnings("MALFORMED", source="yahoo", settings=settings)

    assert "Earnings provider response malformed for MALFORMED" in str(exc_info.value)


def test_get_next_earnings_unexpected_type_raises_response_error(tmp_path):
    """Unexpected non-empty return type raises EarningsProviderResponseError."""
    settings = _make_earnings_db(tmp_path)
    fake_ticker = FakeTicker(
        dates_df="unexpected string body",
        calendar_val={},
    )

    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(EarningsProviderResponseError) as exc_info,
    ):
        calendar.get_next_earnings("UNEXPECTED", source="yahoo", settings=settings)

    assert "Earnings provider response malformed for UNEXPECTED" in str(exc_info.value)


def test_get_next_earnings_calendar_non_empty_dict_missing_earnings_date_raises_response_error(tmp_path):
    """Non-empty calendar dict without 'Earnings Date' raises EarningsProviderResponseError."""
    settings = _make_earnings_db(tmp_path)
    fake_ticker = FakeTicker(
        dates_df=pd.DataFrame(),
        calendar_val={"Revenue": [1000], "Dividends": [0.5]},
    )

    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(EarningsProviderResponseError) as exc_info,
    ):
        calendar.get_next_earnings("UNEXPECTED_DICT", source="yahoo", settings=settings)

    assert "Earnings provider response malformed for UNEXPECTED_DICT" in str(exc_info.value)


def test_get_next_earnings_calendar_dataframe_missing_earnings_date_with_unrelated_date_raises_response_error(tmp_path):
    """Non-empty calendar DataFrame without 'Earnings Date' raises response error and cannot become KNOWN."""
    settings = _make_earnings_db(tmp_path)
    future_ex_div = date.today() + timedelta(days=20)  # noqa: DTZ011
    # DataFrame where first cell contains an unrelated future date (e.g. Ex-Dividend Date)
    df_unrelated = pd.DataFrame({"Ex-Dividend Date": [future_ex_div]})
    fake_ticker = FakeTicker(
        dates_df=pd.DataFrame(),
        calendar_val=df_unrelated,
    )

    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(EarningsProviderResponseError) as exc_info,
    ):
        calendar.get_next_earnings("UNRELATED_DATE", source="yahoo", settings=settings)

    assert "Earnings provider response malformed for UNRELATED_DATE" in str(exc_info.value)


def test_get_next_earnings_calendar_empty_dict_and_empty_df_remain_clean_absence(tmp_path):
    """Empty calendar dict and empty DataFrame remain clean absence (EarningsDataUnavailableError)."""
    settings = _make_earnings_db(tmp_path)
    fake_ticker_empty_dict = FakeTicker(dates_df=pd.DataFrame(), calendar_val={})
    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker_empty_dict),
        pytest.raises(EarningsDataUnavailableError),
    ):
        calendar.get_next_earnings("EMPTY_DICT", source="yahoo", settings=settings)

    fake_ticker_empty_df = FakeTicker(dates_df=pd.DataFrame(), calendar_val=pd.DataFrame())
    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker_empty_df),
        pytest.raises(EarningsDataUnavailableError),
    ):
        calendar.get_next_earnings("EMPTY_DF", source="yahoo", settings=settings)


def test_get_next_earnings_unsupported_source():
    with pytest.raises(ProviderCapabilityError):
        calendar.get_next_earnings("AAPL", source="schwab")


def test_days_until_earnings():
    future = date.today() + timedelta(days=14)  # noqa: DTZ011
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


def test_days_until_earnings_raises_when_lookup_error():
    with (
        patch.object(
            calendar,
            "get_next_earnings",
            side_effect=EarningsProviderLookupError("Earnings provider lookup failed for AAPL"),
        ),
        pytest.raises(EarningsProviderLookupError),
    ):
        calendar.days_until_earnings("AAPL")


def test_is_within_earnings_window():
    """is_within_earnings_window returns boolean when date is known, raises when unavailable."""
    future_in_window = date.today() + timedelta(days=3)  # noqa: DTZ011
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
    future = date.today() + timedelta(days=10)  # noqa: DTZ011

    def fake_get_next_earnings(ticker, **_):
        if ticker == "AAPL":
            return future
        if ticker == "FAIL":
            raise EarningsDataUnavailableError(f"Upcoming earnings date unavailable for {ticker}")
        if ticker == "TECHFAIL":
            raise EarningsProviderLookupError(f"Earnings provider lookup failed for {ticker}")
        if ticker == "RESPFAIL":
            raise EarningsProviderResponseError(f"Earnings provider response malformed for {ticker}")
        if ticker == "BADSRC":
            raise ProviderCapabilityError("Earnings source 'schwab' is not supported")
        return future

    with patch.object(calendar, "get_next_earnings", side_effect=fake_get_next_earnings):
        df = calendar.annotate(["AAPL", "FAIL", "TECHFAIL", "RESPFAIL", "BADSRC"], source="yahoo")

    assert len(df) == 5
    # AAPL: known
    aapl = df[df["ticker"] == "AAPL"].iloc[0]
    assert aapl["next_earnings"] == future
    assert aapl["days_until"] == 10
    assert aapl["earnings_status"] == "known"
    assert pd.isna(aapl["error_category"]) or aapl["error_category"] is None
    assert pd.isna(aapl["error_message"]) or aapl["error_message"] is None

    # FAIL: unavailable (clean absence)
    fail = df[df["ticker"] == "FAIL"].iloc[0]
    assert pd.isna(fail["next_earnings"]) or fail["next_earnings"] is None
    assert pd.isna(fail["days_until"]) or fail["days_until"] is None
    assert fail["earnings_status"] == "unavailable"
    assert fail["error_category"] == "EarningsDataUnavailableError"
    assert "Upcoming earnings date unavailable for FAIL" in fail["error_message"]

    # TECHFAIL: unavailable (technical provider failure)
    tech = df[df["ticker"] == "TECHFAIL"].iloc[0]
    assert pd.isna(tech["next_earnings"]) or tech["next_earnings"] is None
    assert pd.isna(tech["days_until"]) or tech["days_until"] is None
    assert tech["earnings_status"] == "unavailable"
    assert tech["error_category"] == "EarningsProviderLookupError"
    assert "Earnings provider lookup failed for TECHFAIL" in tech["error_message"]

    # RESPFAIL: unavailable (malformed response error)
    resp = df[df["ticker"] == "RESPFAIL"].iloc[0]
    assert pd.isna(resp["next_earnings"]) or resp["next_earnings"] is None
    assert pd.isna(resp["days_until"]) or resp["days_until"] is None
    assert resp["earnings_status"] == "unavailable"
    assert resp["error_category"] == "EarningsProviderResponseError"
    assert "Earnings provider lookup failed for RESPFAIL" in resp["error_message"]

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

    # Prove technical provider exception message contains no injected secrets
    secret_cause = RuntimeError("HTTP 401 https://api.yahoo.com?token=SECRET_VALUE&password=SUPER_SECRET C:\\Users\\Gary")
    fake_ticker = FakeTicker(dates_exc=secret_cause, calendar_exc=secret_cause)

    with (
        patch.object(calendar.yf, "Ticker", return_value=fake_ticker),
        pytest.raises(EarningsProviderLookupError) as exc_info,
    ):
        calendar._fetch_from_yahoo("LEAK_TEST")

    err_str = str(exc_info.value)
    assert "SECRET_VALUE" not in err_str
    assert "SUPER_SECRET" not in err_str
    assert "C:\\Users\\Gary" not in err_str
    assert "Earnings provider lookup failed for LEAK_TEST" == err_str

    # Also test annotate with secret cause
    def leak_get_next_earnings(ticker, **_):
        raise EarningsProviderLookupError("Earnings provider lookup failed for LEAK_TEST") from secret_cause

    with patch.object(calendar, "get_next_earnings", side_effect=leak_get_next_earnings):
        df = calendar.annotate(["LEAK_TEST"])
        annotated_msg = df.iloc[0]["error_message"]
        assert "SECRET_VALUE" not in annotated_msg
        assert "SUPER_SECRET" not in annotated_msg
        assert "C:\\Users\\Gary" not in annotated_msg
