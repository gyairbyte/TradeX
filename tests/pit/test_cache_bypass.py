"""Regression tests proving PIT capture bypasses the 24-hour earnings cache."""
from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from unittest.mock import patch

from tradex.config import settings_from_mapping
from tradex.market.hours import MARKET_TIMEZONE
from tradex.pit.earnings import _default_earnings_lookup, capture_earnings_snapshot
from tradex.pit.models import CaptureSlot


def test_default_earnings_lookup_calls_get_next_earnings_with_cache_bypassed() -> None:
    with patch("tradex.pit.earnings.get_next_earnings") as mock_get:
        mock_get.return_value = date(2026, 9, 15)

        settings = settings_from_mapping({"DATA_PROVIDER": "schwab", "EARNINGS_DATA_SOURCE": "yahoo"})
        res = _default_earnings_lookup("AAPL", source="yahoo", settings=settings)

        assert res == date(2026, 9, 15)
        mock_get.assert_called_once_with(
            "AAPL",
            force_refresh=True,
            source="yahoo",
            use_cache=False,
            settings=settings,
        )


def test_pit_capture_does_not_use_or_mutate_earnings_cache_db(tmp_path) -> None:
    cache_db_path = tmp_path / "earnings_cache.db"
    signals_db_path = tmp_path / "signals.db"

    # Pre-populate earnings_cache.db with a stale date for AAPL
    with sqlite3.connect(cache_db_path) as con:
        con.execute(
            """
            CREATE TABLE earnings_cache (
                ticker TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT 'yahoo',
                next_earnings TEXT,
                fetched_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            INSERT INTO earnings_cache (ticker, source, next_earnings, fetched_at)
            VALUES ('AAPL', 'yahoo', '2026-08-01', ?)
            """,
            (datetime.now(UTC).isoformat(),),
        )

    settings = settings_from_mapping(
        {
            "TRADEX_EARNINGS_CACHE_PATH": str(cache_db_path),
            "TRADEX_DB_PATH": str(signals_db_path),
        }
    )

    clock = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    # Patch yfinance retrieval behind _fetch_from_yahoo
    with patch("tradex.earnings.calendar._fetch_from_yahoo") as mock_fetch:
        mock_fetch.return_value = date(2026, 9, 25)

        result = capture_earnings_snapshot(
            symbols=["AAPL"],
            slot=CaptureSlot.MORNING,
            settings=settings,
            db_path=signals_db_path,
            now_fn=lambda: clock,
        )

        assert result.run.status.value == "succeeded"
        # Must return the fresh 2026-09-25 date, NOT the cached 2026-08-01 date
        assert result.snapshots[0].next_earnings_date == date(2026, 9, 25)
        mock_fetch.assert_called_once_with("AAPL")

    # Verify that earnings_cache.db was NOT mutated
    with sqlite3.connect(cache_db_path) as con:
        row = con.execute("SELECT next_earnings FROM earnings_cache WHERE ticker = 'AAPL'").fetchone()
        assert row is not None
        assert row[0] == "2026-08-01"  # Still unchanged!
