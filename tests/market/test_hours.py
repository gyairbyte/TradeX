"""Tests for the centralized NYSE market-hours module."""
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from tradex.market.hours import (
    MARKET_TIMEZONE,
    get_market_session,
    is_regular_market_open,
    is_trading_day,
    market_status,
    next_trading_session,
    normalize_market_datetime,
    previous_trading_session,
)


def _dt(*args, tz=MARKET_TIMEZONE) -> datetime:
    return datetime(*args, tzinfo=tz)


def test_normalize_market_datetime_returns_new_york_time():
    utc = datetime(2025, 1, 15, 14, 30, tzinfo=UTC)
    ny = normalize_market_datetime(utc)
    assert ny.tzinfo == MARKET_TIMEZONE
    assert ny == datetime(2025, 1, 15, 9, 30, tzinfo=MARKET_TIMEZONE)


def test_normalize_market_datetime_rejects_naive():
    with pytest.raises(ValueError):
        normalize_market_datetime(datetime(2025, 1, 15, 9, 30))  # noqa: DTZ001


def test_is_trading_day_for_normal_wednesday():
    assert is_trading_day(date(2025, 1, 15))


def test_is_trading_day_saturday_is_not_session():
    assert not is_trading_day(date(2025, 1, 18))


def test_is_trading_day_sunday_is_not_session():
    assert not is_trading_day(date(2025, 1, 19))


def test_is_trading_day_full_exchange_holiday():
    # New Year's Day 2025 (Wednesday)
    assert not is_trading_day(date(2025, 1, 1))


def test_is_trading_day_good_friday_is_holiday():
    # Good Friday 2025-04-18
    assert not is_trading_day(date(2025, 4, 18))


def test_get_market_session_returns_open_and_close():
    session = get_market_session(date(2025, 1, 15))
    assert session is not None
    assert session.session_date == date(2025, 1, 15)
    assert session.opens_at == datetime(2025, 1, 15, 9, 30, tzinfo=MARKET_TIMEZONE)
    assert session.closes_at == datetime(2025, 1, 15, 16, 0, tzinfo=MARKET_TIMEZONE)
    assert not session.is_early_close


def test_get_market_session_for_holiday_returns_none():
    assert get_market_session(date(2025, 1, 1)) is None


def test_market_status_regular_open():
    status = market_status(_dt(2025, 1, 15, 10, 0))
    assert status.is_trading_day
    assert status.is_open
    assert status.reason == "Regular session open"
    assert status.next_open is None


def test_market_status_before_open():
    status = market_status(_dt(2025, 1, 15, 9, 29, 59))
    assert status.is_trading_day
    assert not status.is_open
    assert status.reason == "Before regular session"
    assert status.next_open == datetime(2025, 1, 15, 9, 30, tzinfo=MARKET_TIMEZONE)


def test_market_status_exact_open():
    status = market_status(_dt(2025, 1, 15, 9, 30))
    assert status.is_open


def test_market_status_exact_close_is_closed():
    status = market_status(_dt(2025, 1, 15, 16, 0))
    assert not status.is_open


def test_market_status_after_close():
    status = market_status(_dt(2025, 1, 15, 16, 1))
    assert status.is_trading_day
    assert not status.is_open
    assert status.reason == "After regular session"


def test_market_status_weekend():
    status = market_status(_dt(2025, 1, 18, 10, 0))
    assert not status.is_trading_day
    assert not status.is_open


def test_market_status_full_holiday_with_next_open():
    status = market_status(_dt(2025, 1, 1, 10, 0))
    assert not status.is_trading_day
    assert status.next_open is not None


def test_market_status_good_friday_is_holiday():
    status = market_status(_dt(2025, 4, 18, 10, 0))
    assert not status.is_trading_day


def test_early_close_before_close():
    # 2025-11-28 (Black Friday) closes at 13:00 ET
    status = market_status(_dt(2025, 11, 28, 12, 0))
    assert status.is_open
    assert status.session.is_early_close


def test_early_close_exact_close_is_closed():
    status = market_status(_dt(2025, 11, 28, 13, 0))
    assert not status.is_open


def test_early_close_after_close():
    status = market_status(_dt(2025, 11, 28, 13, 1))
    assert not status.is_open
    assert status.reason == "After regular session"


def test_previous_trading_session_from_monday():
    # 2025-01-13 is Monday; previous completed session is Friday 2025-01-10.
    session = previous_trading_session(date(2025, 1, 13))
    assert session.session_date == date(2025, 1, 10)


def test_previous_trading_session_after_holiday():
    # 2025-01-02 Thursday after New Year's; previous is 2025-01-02 itself?
    # Actually 2025-01-02 is a session. previous_session returns prior session.
    session = previous_trading_session(date(2025, 1, 2))
    assert session.session_date == date(2024, 12, 31)


def test_previous_trading_session_from_holiday():
    # New Year's 2025-01-01 not a session; previous should be 2024-12-31.
    session = previous_trading_session(date(2025, 1, 1))
    assert session.session_date == date(2024, 12, 31)


def test_next_trading_session_before_open_same_day():
    at = _dt(2025, 1, 15, 8, 0)
    session = next_trading_session(at)
    assert session.session_date == date(2025, 1, 15)


def test_next_trading_session_during_session():
    at = _dt(2025, 1, 15, 10, 0)
    session = next_trading_session(at)
    assert session.session_date == date(2025, 1, 15)


def test_next_trading_session_after_close_goes_to_next_day():
    at = _dt(2025, 1, 15, 17, 0)
    session = next_trading_session(at)
    assert session.session_date == date(2025, 1, 16)


def test_next_trading_session_from_weekend_goes_to_monday():
    at = _dt(2025, 1, 18, 10, 0)
    session = next_trading_session(at)
    assert session.session_date == date(2025, 1, 21)


def test_next_trading_session_from_holiday_goes_to_next_session():
    at = _dt(2025, 1, 1, 10, 0)
    session = next_trading_session(at)
    assert session.session_date == date(2025, 1, 2)


def test_year_boundary_previous_session():
    session = previous_trading_session(date(2025, 1, 2))
    assert session.session_date == date(2024, 12, 31)


def test_year_boundary_next_session():
    at = _dt(2024, 12, 31, 17, 0)
    session = next_trading_session(at)
    assert session.session_date == date(2025, 1, 2)


def test_dst_winter_open_equivalent():
    # 2025-01-15 09:30 ET = 14:30 UTC
    utc = datetime(2025, 1, 15, 14, 30, tzinfo=UTC)
    assert is_regular_market_open(utc)


def test_dst_summer_open_equivalent():
    # 2025-07-02 09:30 EDT = 13:30 UTC
    utc = datetime(2025, 7, 2, 13, 30, tzinfo=UTC)
    assert is_regular_market_open(utc)


def test_aware_non_new_york_input_is_converted():
    tokyo = ZoneInfo("Asia/Tokyo")
    tokyo_time = datetime(2025, 1, 15, 23, 30, tzinfo=tokyo)  # 09:30 ET
    assert is_regular_market_open(tokyo_time)


def test_naive_datetime_rejected_by_market_status():
    with pytest.raises(ValueError):
        market_status(datetime(2025, 1, 15, 10, 0))  # noqa: DTZ001


def test_is_regular_market_open_returns_false_after_close():
    assert not is_regular_market_open(_dt(2025, 1, 15, 16, 0))
