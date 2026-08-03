"""Explicitly sourced, non-causal catalyst context for pre-market gap candidates.

Earnings and headline lookups are intentionally separate from OHLCV provider
selection. No sentiment analysis or causal claims are made.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from tradex.data.fetcher import ProviderCapabilityError
from tradex.earnings.calendar import get_next_earnings
from tradex.premarket.models import GapCatalystContext

_EARNINGS_STATUSES = (
    "earnings_today",
    "earnings_soon",
    "none_detected",
    "unavailable",
    "not_requested",
)

_HEADLINE_STATUSES = (
    "recent_headline",
    "none_detected",
    "unavailable",
    "not_requested",
)


def _resolve_earnings_source(source: str | None) -> str:
    from tradex.earnings.calendar import _resolve_earnings_source as _core_resolve

    return _core_resolve(source)


def _resolve_headline_source(source: str | None) -> str:
    s = (source or "").lower().strip()
    if not s:
        raise ProviderCapabilityError("Headline source is required; only 'yahoo' is available")
    if s == "yahoo":
        return s
    raise ProviderCapabilityError(f"Headline source '{s}' is not supported; only 'yahoo' is available")


def _earnings_status(
    next_earnings: date | None,
    session_date: date | None,
    lookback_hours: float,
) -> tuple[str, date | None]:
    """Return stable earnings status relative to the pre-market session date."""
    if next_earnings is None or session_date is None:
        return "none_detected", None
    if next_earnings == session_date:
        return "earnings_today", next_earnings
    window_days = max(1, int(lookback_hours / 24.0 + 0.999999))
    if session_date < next_earnings <= (session_date + timedelta(days=window_days)):
        return "earnings_soon", next_earnings
    return "none_detected", None


def _parse_headline_timestamp(value: Any) -> datetime | None:
    """Parse a headline timestamp into a UTC datetime, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except Exception:  # noqa: BLE001
            return None
    if isinstance(value, str):
        s = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(s)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except Exception:  # noqa: BLE001
            try:
                parsed = pd.to_datetime(value, utc=True)
                return parsed.to_pydatetime()
            except Exception:  # noqa: BLE001
                return None
    return None


def _sanitize_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    if not text:
        return None
    return text[:500]


def _fetch_yahoo_headlines(
    ticker: str,
    as_of: datetime,
    lookback_hours: float,
) -> tuple[list[dict[str, Any]] | None, Exception | None]:
    """Fetch recent headlines for ``ticker`` from Yahoo Finance."""
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        news = t.news
        if news is None:
            return None, None
        if not isinstance(news, list):
            return None, None
        return news, None
    except Exception as exc:  # noqa: BLE001
        return None, exc


def _select_recent_headline(
    headlines: list[dict[str, Any]],
    as_of: datetime,
    lookback_hours: float,
) -> dict[str, Any] | None:
    """Select the newest headline at or before as_of and within lookback_hours."""
    cutoff = as_of - timedelta(hours=lookback_hours)
    candidates: list[dict[str, Any]] = []
    for raw in headlines:
        if not isinstance(raw, dict):
            continue
        published = _parse_headline_timestamp(raw.get("published") or raw.get("published_at") or raw.get("date"))
        if published is None:
            continue
        if published > as_of or published < cutoff:
            continue
        title = _sanitize_text(raw.get("title"))
        if not title:
            continue
        url = _sanitize_text(raw.get("link") or raw.get("url"))
        candidates.append({
            "published_at": published,
            "title": title,
            "url": url,
            "publisher": _sanitize_text(raw.get("publisher")),
        })
    if not candidates:
        return None
    # Stable tie-break: newest first, then title, then url.
    candidates.sort(key=lambda h: (-h["published_at"].timestamp(), h["title"], h["url"] or ""))
    return candidates[0]


def fetch_catalyst_context(
    ticker: str,
    session_date: date | None,
    as_of: datetime,
    include_catalysts: bool,
    require_catalyst: bool,
    lookback_hours: float,
    earnings_source: str | None,
    headline_source: str | None,
) -> GapCatalystContext:
    """Return explicitly sourced catalyst context with no causal inference."""
    requested_earnings_source = earnings_source
    requested_headline_source = headline_source

    if not include_catalysts and not require_catalyst:
        return GapCatalystContext(
            ticker=ticker,
            session_date=session_date,
            requested_earnings_source=requested_earnings_source,
            actual_earnings_source=None,
            requested_headline_source=requested_headline_source,
            actual_headline_source=None,
        )

    earnings_status: str | None = "not_requested"
    earnings_date: date | None = None
    actual_earnings_source: str | None = None
    headline_status: str | None = "not_requested"
    headline_title: str | None = None
    headline_published_at: datetime | None = None
    headline_url: str | None = None
    actual_headline_source: str | None = None
    error: Exception | None = None

    # Earnings
    if requested_earnings_source:
        try:
            actual_earnings_source = _resolve_earnings_source(requested_earnings_source)
            next_earnings = get_next_earnings(ticker, source=actual_earnings_source)
            earnings_status, earnings_date = _earnings_status(
                next_earnings, session_date or as_of.date(), lookback_hours
            )
        except ProviderCapabilityError as exc:
            actual_earnings_source = requested_earnings_source
            earnings_status = "unavailable"
            error = exc
        except Exception as exc:  # noqa: BLE001
            actual_earnings_source = requested_earnings_source
            earnings_status = "unavailable"
            error = error or exc

    # Headlines
    if requested_headline_source:
        try:
            actual_headline_source = _resolve_headline_source(requested_headline_source)
            if actual_headline_source == "yahoo":
                headlines, exc = _fetch_yahoo_headlines(ticker, as_of, lookback_hours)
                if exc:
                    headline_status = "unavailable"
                    error = error or exc
                elif headlines is None:
                    headline_status = "unavailable"
                else:
                    selected = _select_recent_headline(headlines, as_of, lookback_hours)
                    if selected:
                        headline_status = "recent_headline"
                        headline_title = selected["title"]
                        headline_published_at = selected["published_at"]
                        headline_url = selected["url"]
                    else:
                        headline_status = "none_detected"
        except ProviderCapabilityError as exc:
            actual_headline_source = requested_headline_source
            headline_status = "unavailable"
            error = error or exc
        except Exception as exc:  # noqa: BLE001
            actual_headline_source = requested_headline_source
            headline_status = "unavailable"
            error = error or exc

    return GapCatalystContext(
        ticker=ticker,
        session_date=session_date,
        requested_earnings_source=requested_earnings_source,
        actual_earnings_source=actual_earnings_source,
        earnings_status=earnings_status,
        earnings_date=earnings_date,
        requested_headline_source=requested_headline_source,
        actual_headline_source=actual_headline_source,
        headline_status=headline_status,
        headline_title=headline_title,
        headline_published_at=headline_published_at,
        headline_url=headline_url,
        error=error,
    )
