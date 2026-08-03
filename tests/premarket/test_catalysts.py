"""Tests for pre-market catalyst context."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

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
        None,
        None,
    )
    assert catalysts._earnings_status(None, date(2024, 1, 3), 24.0) == ("none_detected", None, None)


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
    assert ctx.earnings_status == "none_detected"
    assert ctx.headline_status == "unavailable"
    assert ctx.status == "unavailable"
