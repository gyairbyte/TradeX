"""Idempotency, replay, and incomplete run failure tests (MVP-ARCH-001-R7-PIT-001A)."""
from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from tradex.market.hours import MARKET_TIMEZONE
from tradex.pit.earnings import capture_earnings_snapshot
from tradex.pit.models import CaptureKind, CaptureRunStatus, CaptureSlot, PITCaptureRun
from tradex.pit.store import (
    PITIdempotencyConflictError,
    create_capture_run,
    get_capture_run,
)
from tradex.tracker import store


def test_idempotency_exact_replay(tmp_path) -> None:
    db_path = tmp_path / "signals.db"
    store.init(db_path)

    clock = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
    lookup_mock = MagicMock(return_value=date(2026, 9, 15))

    # First execution
    res1 = capture_earnings_snapshot(
        symbols=["AAPL", "MSFT"],
        slot=CaptureSlot.MORNING,
        idempotency_key="custom-key-1",
        db_path=db_path,
        now_fn=lambda: clock,
        earnings_lookup=lookup_mock,
    )
    assert res1.run.status == CaptureRunStatus.SUCCEEDED
    assert lookup_mock.call_count == 2

    # Exact replay: same idempotency key and same symbols/slot/date/provider
    res2 = capture_earnings_snapshot(
        symbols=["AAPL", "MSFT"],
        slot=CaptureSlot.MORNING,
        idempotency_key="custom-key-1",
        db_path=db_path,
        now_fn=lambda: clock,
        earnings_lookup=lookup_mock,
    )

    # Must return identical run and snapshots with ZERO new provider calls
    assert res2.run.capture_run_id == res1.run.capture_run_id
    assert len(res2.snapshots) == 2
    assert lookup_mock.call_count == 2  # Still 2!


def test_idempotency_divergent_replay_conflicts(tmp_path) -> None:
    db_path = tmp_path / "signals.db"
    store.init(db_path)

    clock = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
    lookup_mock = MagicMock(return_value=date(2026, 9, 15))

    # Initial execution
    capture_earnings_snapshot(
        symbols=["AAPL", "MSFT"],
        slot=CaptureSlot.MORNING,
        idempotency_key="key-fixed",
        db_path=db_path,
        now_fn=lambda: clock,
        earnings_lookup=lookup_mock,
    )
    assert lookup_mock.call_count == 2

    # Capture raw DB state before divergent replay attempt
    import sqlite3
    with sqlite3.connect(db_path) as con:
        runs_before = con.execute("SELECT * FROM pit_capture_runs").fetchall()
        snaps_before = con.execute("SELECT * FROM pit_earnings_snapshots").fetchall()

    # Divergent replay: same idempotency key but different symbol list
    with pytest.raises(PITIdempotencyConflictError, match="divergent request fingerprint"):
        capture_earnings_snapshot(
            symbols=["AAPL", "NVDA"],
            slot=CaptureSlot.MORNING,
            idempotency_key="key-fixed",
            db_path=db_path,
            now_fn=lambda: clock,
            earnings_lookup=lookup_mock,
        )

    # Provider call count must NOT have increased
    assert lookup_mock.call_count == 2

    # Database rows must be byte/content identical (zero mutations)
    with sqlite3.connect(db_path) as con:
        runs_after = con.execute("SELECT * FROM pit_capture_runs").fetchall()
        snaps_after = con.execute("SELECT * FROM pit_earnings_snapshots").fetchall()
        assert runs_after == runs_before
        assert snaps_after == snaps_before


def test_incomplete_started_run_not_reported_as_succeeded(tmp_path) -> None:
    db_path = tmp_path / "signals.db"
    store.init(db_path)

    now = datetime(2026, 8, 30, 13, 0, 0, tzinfo=UTC)

    # Manually simulate a started run that crashed mid-execution
    run = PITCaptureRun(
        capture_run_id="crashed-run-1",
        idempotency_key="crash-key",
        request_fingerprint="fp-crash",
        capture_kind=CaptureKind.EARNINGS,
        capture_slot=CaptureSlot.MORNING,
        capture_date=date(2026, 8, 30),
        scheduled_for=now,
        requested_at=now,
        completed_at=None,
        requested_provider="yahoo",
        universe_hash="uhash",
        requested_n=2,
        status=CaptureRunStatus.STARTED,
        created_at=now,
        updated_at=now,
    )
    create_capture_run(run, db_path=db_path)

    persisted = get_capture_run("crashed-run-1", db_path=db_path)
    assert persisted is not None
    assert persisted.status == CaptureRunStatus.STARTED
    assert persisted.status != CaptureRunStatus.SUCCEEDED
    assert persisted.completed_at is None
