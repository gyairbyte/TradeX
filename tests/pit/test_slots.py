"""Tests for canonical observation slots, timezone conversion (EDT/EST), and prospective guards."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from tradex.market.hours import MARKET_TIMEZONE
from tradex.pit.earnings import capture_earnings_snapshot, compute_scheduled_slot_time
from tradex.pit.models import CaptureSlot


def test_summer_edt_slot_times() -> None:
    # Summer date in EDT (UTC-4)
    summer_date = date(2026, 7, 15)

    # Morning slot: 9:00 AM EDT -> 13:00 UTC
    morning_utc = compute_scheduled_slot_time(summer_date, CaptureSlot.MORNING)
    assert morning_utc == datetime(2026, 7, 15, 13, 0, 0, tzinfo=UTC)

    # Evening slot: 8:30 PM EDT -> 00:30 UTC next day
    evening_utc = compute_scheduled_slot_time(summer_date, CaptureSlot.EVENING)
    assert evening_utc == datetime(2026, 7, 16, 0, 30, 0, tzinfo=UTC)


def test_winter_est_slot_times() -> None:
    # Winter date in EST (UTC-5)
    winter_date = date(2026, 1, 15)

    # Morning slot: 9:00 AM EST -> 14:00 UTC
    morning_utc = compute_scheduled_slot_time(winter_date, CaptureSlot.MORNING)
    assert morning_utc == datetime(2026, 1, 15, 14, 0, 0, tzinfo=UTC)

    # Evening slot: 8:30 PM EST -> 01:30 UTC next day
    evening_utc = compute_scheduled_slot_time(winter_date, CaptureSlot.EVENING)
    assert evening_utc == datetime(2026, 1, 16, 1, 30, 0, tzinfo=UTC)


def test_prospective_validation_rejects_before_slot(tmp_path) -> None:
    db_path = tmp_path / "pit.db"
    # Morning slot is 09:00 ET (13:00 UTC in summer). Clock at 08:59 ET.
    clock_before_morning = datetime(2026, 8, 30, 8, 59, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    with pytest.raises(ValueError, match="is before scheduled slot time"):
        capture_earnings_snapshot(
            symbols=["AAPL"],
            slot=CaptureSlot.MORNING,
            db_path=db_path,
            now_fn=lambda: clock_before_morning,
            earnings_lookup=lambda *args, **kwargs: date(2026, 9, 15),
        )

    # Evening slot is 20:30 ET (00:30 UTC next day in summer). Clock at 20:29 ET.
    clock_before_evening = datetime(2026, 8, 30, 20, 29, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    with pytest.raises(ValueError, match="is before scheduled slot time"):
        capture_earnings_snapshot(
            symbols=["AAPL"],
            slot=CaptureSlot.EVENING,
            db_path=db_path,
            now_fn=lambda: clock_before_evening,
            earnings_lookup=lambda *args, **kwargs: date(2026, 9, 15),
        )


def test_prospective_validation_allows_at_or_after_slot(tmp_path) -> None:
    db_path = tmp_path / "pit.db"
    # Exactly at morning slot (09:00 ET)
    clock_at_morning = datetime(2026, 8, 30, 9, 0, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
    res1 = capture_earnings_snapshot(
        symbols=["AAPL"],
        slot=CaptureSlot.MORNING,
        db_path=db_path,
        now_fn=lambda: clock_at_morning,
        earnings_lookup=lambda *args, **kwargs: date(2026, 9, 15),
    )
    assert res1.run.status.value == "succeeded"

    # After morning slot (09:30 ET) with new idempotency key
    clock_after_morning = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
    res2 = capture_earnings_snapshot(
        symbols=["MSFT"],
        slot=CaptureSlot.MORNING,
        idempotency_key="key-after-morning",
        db_path=db_path,
        now_fn=lambda: clock_after_morning,
        earnings_lookup=lambda *args, **kwargs: date(2026, 9, 15),
    )
    assert res2.run.status.value == "succeeded"


def test_prospective_validation_rejects_historical_and_future_dates(tmp_path) -> None:
    db_path = tmp_path / "pit.db"
    # Current clock is 2026-08-30 10:00 ET
    clock = datetime(2026, 8, 30, 10, 0, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    # Historical date
    with pytest.raises(ValueError, match="Historical capture date"):
        capture_earnings_snapshot(
            symbols=["AAPL"],
            slot=CaptureSlot.MORNING,
            capture_date=date(2026, 8, 29),
            db_path=db_path,
            now_fn=lambda: clock,
            earnings_lookup=lambda *args, **kwargs: date(2026, 9, 15),
        )

    # Future date
    with pytest.raises(ValueError, match="Future capture date"):
        capture_earnings_snapshot(
            symbols=["AAPL"],
            slot=CaptureSlot.MORNING,
            capture_date=date(2026, 8, 31),
            db_path=db_path,
            now_fn=lambda: clock,
            earnings_lookup=lambda *args, **kwargs: date(2026, 9, 15),
        )
