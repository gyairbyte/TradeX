"""Tests for pre-market catalyst context."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import ANY, patch

import pytest

from tradex.data.fetcher import ProviderCapabilityError
from tradex.premarket import catalysts
from tradex.premarket.models import GapCatalystContext


def test_resolve_headline_source_yahoo():
    assert catalysts._resolve_headline_source("yahoo") == "yahoo"
    assert catalysts._resolve_headline_source("YAHOO") == "yahoo"


def test_resolve_headline_source_unsupported():
    with pytest.raises(ProviderCapabilityError):
        catalysts._resolve_headline_source("bloomberg")
    with pytest.raises(ProviderCapabilityError):
        catalysts._resolve_headline_source("")


def test_earnings_status_today():
    assert catalysts._earnings_status(date(2024, 1, 3), date(2024, 1, 3), 24.0) == (
        "earnings_today",
        date(2024, 1, 3),
        0,
    )


def test_earnings_status_soon():
    assert catalysts._earnings_status(date(2024, 1, 4), date(2024, 1, 3), 24.0) == (
        "earnings_soon",
        date(2024, 1, 4),
        1,
    )


def test_earnings_status_none():
    assert catalysts._earnings_status(date(2024, 1, 10), date(2024, 1, 3), 24.0) == (
        "none_detected",
        date(2024, 1, 10),
        7,
    )
    assert catalysts._earnings_status(None, date(2024, 1, 3), 24.0) == ("unavailable", None, None)


def test_parse_headline_timestamp():
    assert catalysts._parse_headline_timestamp(datetime(2024, 1, 3, 12, 0, tzinfo=UTC)) == datetime(
        2024, 1, 3, 12, 0, tzinfo=UTC
    )
    assert catalysts._parse_headline_timestamp("2024-01-03T12:00:00+00:00") == datetime(
        2024, 1, 3, 12, 0, tzinfo=UTC
    )
    assert catalysts._parse_headline_timestamp("2024-01-03T12:00:00Z") == datetime(
        2024, 1, 3, 12, 0, tzinfo=UTC
    )
    assert catalysts._parse_headline_timestamp("not a date") is None
    assert catalysts._parse_headline_timestamp(None) is None


def test_sanitize_text():
    assert catalysts._sanitize_text("  Headline  ") == "Headline"
    assert catalysts._sanitize_text(123) == "123"
    assert catalysts._sanitize_text(None) is None
    assert catalysts._sanitize_text("") is None
    assert catalysts._sanitize_text("x" * 600) == "x" * 500


def test_select_recent_headline():
    as_of = datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
    headlines = [
        {"title": "Old news", "published": "2024-01-02T12:00:00+00:00"},
        {"title": "New news", "published": "2024-01-03T12:00:00+00:00"},
        {"title": "Future news", "published": "2024-01-04T12:00:00+00:00"},
    ]
    selected = catalysts._select_recent_headline(headlines, as_of, 24.0)
    assert selected is not None
    assert selected["title"] == "New news"


def test_fetch_catalyst_context_not_requested():
    ctx = catalysts.fetch_catalyst_context(
        "AAPL",
        date(2024, 1, 3),
        datetime(2024, 1, 3, 13, 0, tzinfo=UTC),
        include_catalysts=False,
        require_catalyst=False,
        lookback_hours=24.0,
        earnings_source=None,
        headline_source=None,
    )
    assert isinstance(ctx, GapCatalystContext)
    assert ctx.status == "not_requested"


def test_fetch_catalyst_context_earnings_and_headlines():
    as_of = datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
    fake_headlines = [
        {
            "title": "Breakthrough",
            "published": "2024-01-03T12:00:00+00:00",
        }
    ]
    with (
        patch.object(catalysts, "get_next_earnings", return_value=date(2024, 1, 3)),
        patch.object(catalysts, "_fetch_yahoo_headlines", return_value=(fake_headlines, None)),
        patch.object(catalysts, "_utc_today", return_value=as_of.date()),
    ):
        ctx = catalysts.fetch_catalyst_context(
            "AAPL",
            date(2024, 1, 3),
            as_of,
            include_catalysts=True,
            require_catalyst=False,
            lookback_hours=24.0,
            earnings_source="yahoo",
            headline_source="yahoo",
        )
    assert ctx.earnings_status == "earnings_today"
    assert ctx.headline_status == "recent_headline"
    assert ctx.headline_title == "Breakthrough"
    assert ctx.status == "earnings_and_recent_headline"


def test_fetch_catalyst_context_require_catalyst_filters_no_earnings():
    as_of = datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
    with (
        patch.object(catalysts, "get_next_earnings", return_value=None),
        patch.object(catalysts, "_fetch_yahoo_headlines", return_value=(None, None)),
        patch.object(catalysts, "_utc_today", return_value=as_of.date()),
    ):
        ctx = catalysts.fetch_catalyst_context(
            "AAPL",
            date(2024, 1, 3),
            as_of,
            include_catalysts=True,
            require_catalyst=False,
            lookback_hours=24.0,
            earnings_source="yahoo",
            headline_source=None,
        )
    assert ctx.earnings_status == "unavailable"
    assert ctx.headline_status == "unavailable"
    assert ctx.status == "unavailable"


def test_fetch_catalyst_context_no_earnings_cache_db(tmp_path, monkeypatch):
    """The pre-market scanner must not create the earnings cache database."""
    monkeypatch.setenv("TRADEX_EARNINGS_CACHE_PATH", str(tmp_path / "earnings_cache.db"))

    as_of = datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
    with (
        patch.object(catalysts, "get_next_earnings") as mock_earn,
        patch.object(catalysts, "_fetch_yahoo_headlines", return_value=(None, None)),
        patch.object(catalysts, "_utc_today", return_value=as_of.date()),
    ):
        mock_earn.return_value = date(2024, 1, 3)
        ctx = catalysts.fetch_catalyst_context(
            "AAPL",
            date(2024, 1, 3),
            as_of,
            include_catalysts=True,
            require_catalyst=False,
            lookback_hours=24.0,
            earnings_source="yahoo",
            headline_source=None,
        )
    mock_earn.assert_called_once_with("AAPL", source="yahoo", use_cache=False, settings=ANY)
    assert not (tmp_path / "earnings_cache.db").exists()
    assert ctx.earnings_status == "earnings_today"


def test_fetch_catalyst_context_historical_headline_is_unavailable():
    """For a historical as_of, headline absence is unavailable, not none_detected."""
    as_of = datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
    with (
        patch.object(catalysts, "get_next_earnings") as mock_earn,
        patch.object(catalysts, "_utc_today", return_value=date(2024, 1, 4)),
    ):
        mock_earn.return_value = date(2024, 1, 3)
        ctx = catalysts.fetch_catalyst_context(
            "AAPL",
            date(2024, 1, 3),
            as_of,
            include_catalysts=True,
            require_catalyst=False,
            lookback_hours=24.0,
            earnings_source="yahoo",
            headline_source="yahoo",
        )
    assert ctx.headline_status == "unavailable"
    assert ctx.earnings_status == "unavailable"


def test_utc_today_uses_new_york_market_date():
    """_utc_today returns the America/New_York calendar date, not the UTC date."""
    # 04:30 UTC in January = 23:30 ET the *previous* calendar day.
    winter = datetime(2024, 1, 3, 4, 30, tzinfo=UTC)
    assert catalysts._utc_today(winter) == date(2024, 1, 2)
    # 09:30 UTC in July = 05:30 EDT the *same* calendar day.
    summer = datetime(2024, 7, 3, 9, 30, tzinfo=UTC)
    assert catalysts._utc_today(summer) == date(2024, 7, 3)


def test_fetch_catalyst_context_uses_new_york_session_date_for_history():
    """A historical as_of whose NY date is before today is classified as replay."""
    # 04:30 UTC on 2024-01-02 is NY 2024-01-01 23:30. If current NY date is 2024-01-02,
    # the as_of is historical, and Yahoo headlines must be unavailable.
    as_of = datetime(2024, 1, 2, 4, 30, tzinfo=UTC)
    with (
        patch.object(catalysts, "get_next_earnings") as mock_earn,
        patch.object(catalysts, "_utc_today", return_value=date(2024, 1, 2)),
    ):
        mock_earn.return_value = None
        ctx = catalysts.fetch_catalyst_context(
            "AAPL",
            date(2024, 1, 2),
            as_of,
            include_catalysts=True,
            require_catalyst=False,
            lookback_hours=24.0,
            earnings_source=None,
            headline_source="yahoo",
        )
    assert ctx.headline_status == "unavailable"
