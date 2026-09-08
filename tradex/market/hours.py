"""NYSE/XNYS market-hours utilities built on exchange-calendars.

TradeX targets US-listed equities, so the canonical schedule is the NYSE regular
session in ``America/New_York``. All public functions accept timezone-aware
``datetime`` values and convert them safely; naive datetimes raise ``ValueError``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as ec

MARKET_TIMEZONE = ZoneInfo("America/New_York")
EXCHANGE_CALENDAR_KEY = "XNYS"


@dataclass(frozen=True)
class MarketSession:
    """A single regular trading session with New-York-local timestamps."""

    session_date: date
    opens_at: datetime
    closes_at: datetime
    is_early_close: bool


@dataclass(frozen=True)
class MarketStatus:
    """Time-stamped market status derived from the exchange calendar."""

    is_trading_day: bool
    is_open: bool
    session: MarketSession | None
    reason: str
    next_open: datetime | None


@lru_cache(maxsize=1)
def _calendar() -> ec.ExchangeCalendar:
    return ec.get_calendar(EXCHANGE_CALENDAR_KEY)


def _as_market_timezone(value: datetime) -> datetime:
    """Return ``value`` converted to ``America/New_York`` or raise on naive input."""
    if value.tzinfo is None:
        raise ValueError("Naive datetime is not accepted; provide a timezone-aware datetime.")
    return value.astimezone(MARKET_TIMEZONE)


def normalize_market_datetime(value: datetime) -> datetime:
    """Convert any timezone-aware datetime to ``America/New_York``."""
    return _as_market_timezone(value)


def _to_date(value: date | datetime) -> date:
    return value if isinstance(value, date) and not isinstance(value, datetime) else value.date()


def _ny_timestamp_to_local(ts) -> datetime:
    """Convert a pandas/UTC timestamp to a Python ``datetime`` in New York time."""
    return ts.to_pydatetime().astimezone(MARKET_TIMEZONE)


def _is_early_close(close: datetime) -> bool:
    """A session is early when it closes before the regular 4:00 PM ET close."""
    return close.time() < time(16, 0)


def get_market_session(day: date) -> MarketSession | None:
    """Return the ``MarketSession`` for ``day`` if it is an NYSE session, else ``None``."""
    cal = _calendar()
    if not cal.is_session(day):
        return None
    opens = _ny_timestamp_to_local(cal.session_open(day))
    closes = _ny_timestamp_to_local(cal.session_close(day))
    return MarketSession(
        session_date=day,
        opens_at=opens,
        closes_at=closes,
        is_early_close=_is_early_close(closes),
    )


def is_trading_day(day: date) -> bool:
    """Return ``True`` when ``day`` is an NYSE regular session."""
    return bool(_calendar().is_session(day))


def previous_trading_session(day: date) -> MarketSession:
    """Return the completed NYSE session immediately before ``day``."""
    cal = _calendar()
    if cal.is_session(day):
        prev = cal.previous_session(day)
    else:
        prev = cal.date_to_session(day, direction="previous")
    session = get_market_session(prev.date())
    if session is None:
        raise ValueError(f"No previous trading session before {day}")
    return session


def next_trading_session(at: datetime) -> MarketSession:
    """Return the next NYSE session on or after ``at``.

    If ``at`` is before the open of today's session, today's session is returned.
    If ``at`` is during today's session, today's session is returned.
    If ``at`` is at or after today's close, the next future session is returned.
    """
    dt = _as_market_timezone(at)
    day = dt.date()
    cal = _calendar()

    if cal.is_session(day):
        session = get_market_session(day)
        if session is not None and dt < session.closes_at:
            return session
        try:
            next_day = cal.next_session(day)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"No next trading session after {at}") from exc
    else:
        next_day = cal.date_to_session(day, direction="next")

    session = get_market_session(next_day.date())
    if session is None:
        raise ValueError(f"No next trading session after {at}")
    return session


def market_status(at: datetime) -> MarketStatus:
    """Return a ``MarketStatus`` describing the market at ``at``.

    ``at`` may be in any timezone and is converted to ``America/New_York``.
    """
    dt = _as_market_timezone(at)
    day = dt.date()
    session = get_market_session(day)

    if session is None:
        try:
            nxt = next_trading_session(at)
        except ValueError:
            return MarketStatus(
                is_trading_day=False,
                is_open=False,
                session=None,
                reason="Weekend or exchange holiday",
                next_open=None,
            )
        return MarketStatus(
            is_trading_day=False,
            is_open=False,
            session=None,
            reason="Weekend or exchange holiday",
            next_open=nxt.opens_at,
        )

    if dt < session.opens_at:
        return MarketStatus(
            is_trading_day=True,
            is_open=False,
            session=session,
            reason="Before regular session",
            next_open=session.opens_at,
        )
    if dt < session.closes_at:
        return MarketStatus(
            is_trading_day=True,
            is_open=True,
            session=session,
            reason="Regular session open",
            next_open=None,
        )

    try:
        nxt = next_trading_session(at)
    except ValueError:
        nxt = None
    return MarketStatus(
        is_trading_day=True,
        is_open=False,
        session=session,
        reason="After regular session",
        next_open=nxt.opens_at if nxt else None,
    )


def is_regular_market_open(at: datetime) -> bool:
    """Return ``True`` when ``at`` falls within the NYSE regular session."""
    return market_status(at).is_open
