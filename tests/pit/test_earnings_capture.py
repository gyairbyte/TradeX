"""Comprehensive unit and integration tests for prospective earnings point-in-time capture."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, date, datetime

from tradex.data.fetcher import ProviderDataUnavailableError
from tradex.earnings.calendar import EarningsDataUnavailableError
from tradex.market.hours import MARKET_TIMEZONE
from tradex.pit.earnings import capture_earnings_snapshot
from tradex.pit.models import CaptureRunStatus, CaptureSlot, ObservationStatus
from tradex.tracker import store


def test_earnings_capture_all_known_succeeded(tmp_path) -> None:
    db_path = tmp_path / "signals.db"
    store.init(db_path)

    clock = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    def fake_lookup(symbol: str, **kwargs) -> date:
        if symbol == "AAPL":
            return date(2026, 9, 15)
        if symbol == "MSFT":
            return date(2026, 9, 20)
        raise AssertionError(f"Unexpected symbol: {symbol}")

    result = capture_earnings_snapshot(
        symbols=["MSFT", "AAPL"],
        slot=CaptureSlot.MORNING,
        db_path=db_path,
        now_fn=lambda: clock,
        earnings_lookup=fake_lookup,
    )

    run = result.run
    assert run.status == CaptureRunStatus.SUCCEEDED
    assert run.requested_n == 2
    assert run.known_n == 2
    assert run.unavailable_n == 0
    assert run.error_n == 0
    assert run.requested_provider == "yahoo"

    assert len(result.snapshots) == 2
    snap_aapl = result.snapshots[0]
    assert snap_aapl.symbol == "AAPL"
    assert snap_aapl.observation_status == ObservationStatus.KNOWN
    assert snap_aapl.next_earnings_date == date(2026, 9, 15)
    assert snap_aapl.provider == "yahoo"
    assert snap_aapl.provider_observed_at is None
    assert snap_aapl.request_started_at <= snap_aapl.response_received_at

    # Raw database verification for exact JSON and SHA-256 hash match
    with sqlite3.connect(db_path) as con:
        row = con.execute(
            "SELECT fact_json, fact_hash FROM pit_earnings_snapshots WHERE symbol = 'AAPL'"
        ).fetchone()
        assert row is not None
        fact_json, fact_hash = row
        assert fact_json == '{"next_earnings_date":"2026-09-15"}'
        assert fact_hash == hashlib.sha256(fact_json.encode("utf-8")).hexdigest()


def test_earnings_capture_mixed_partial(tmp_path) -> None:
    db_path = tmp_path / "signals.db"
    store.init(db_path)

    clock = datetime(2026, 8, 30, 21, 0, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    def fake_lookup(symbol: str, **kwargs) -> date:
        if symbol == "AAPL":
            return date(2026, 9, 15)
        if symbol == "XYZ":
            raise EarningsDataUnavailableError("Upcoming earnings date unavailable for XYZ")
        if symbol == "FAIL":
            raise RuntimeError("Unexpected network drop")
        raise AssertionError(f"Unexpected symbol: {symbol}")

    result = capture_earnings_snapshot(
        symbols=["AAPL", "XYZ", "FAIL"],
        slot=CaptureSlot.EVENING,
        db_path=db_path,
        now_fn=lambda: clock,
        earnings_lookup=fake_lookup,
    )

    run = result.run
    assert run.status == CaptureRunStatus.PARTIAL
    assert run.requested_n == 3
    assert run.known_n == 1
    assert run.unavailable_n == 1
    assert run.error_n == 1

    snaps_by_sym = {s.symbol: s for s in result.snapshots}
    assert snaps_by_sym["AAPL"].observation_status == ObservationStatus.KNOWN
    assert snaps_by_sym["AAPL"].next_earnings_date == date(2026, 9, 15)

    assert snaps_by_sym["XYZ"].observation_status == ObservationStatus.UNAVAILABLE
    assert snaps_by_sym["XYZ"].next_earnings_date is None
    assert snaps_by_sym["XYZ"].error_category == "EarningsDataUnavailableError"
    assert "Upcoming earnings date unavailable for XYZ" in (snaps_by_sym["XYZ"].error_message or "")

    assert snaps_by_sym["FAIL"].observation_status == ObservationStatus.ERROR
    assert snaps_by_sym["FAIL"].next_earnings_date is None
    assert snaps_by_sym["FAIL"].error_category == "RuntimeError"
    assert snaps_by_sym["FAIL"].error_message == "Earnings lookup failed for FAIL"


def test_earnings_capture_zero_known_failed(tmp_path) -> None:
    db_path = tmp_path / "signals.db"
    store.init(db_path)

    clock = datetime(2026, 8, 30, 9, 15, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    def fake_lookup(symbol: str, **kwargs) -> date:
        raise ProviderDataUnavailableError(f"No data for {symbol}")

    result = capture_earnings_snapshot(
        symbols=["NVDA"],
        slot=CaptureSlot.MORNING,
        db_path=db_path,
        now_fn=lambda: clock,
        earnings_lookup=fake_lookup,
    )

    assert result.run.status == CaptureRunStatus.FAILED
    assert result.run.requested_n == 1
    assert result.run.known_n == 0
    assert result.run.unavailable_n == 1
    assert result.run.error_n == 0


def test_database_write_boundary_audit(tmp_path) -> None:
    db_path = tmp_path / "signals.db"
    store.init(db_path)

    clock = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    # Perform capture
    capture_earnings_snapshot(
        symbols=["AAPL", "MSFT"],
        slot=CaptureSlot.MORNING,
        db_path=db_path,
        now_fn=lambda: clock,
        earnings_lookup=lambda *args, **kwargs: date(2026, 9, 15),
    )

    # Verify that ONLY pit_* tables received rows; all other tables have 0 rows
    with sqlite3.connect(db_path) as con:
        # PIT tables have rows
        assert con.execute("SELECT COUNT(*) FROM pit_capture_runs").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM pit_earnings_snapshots").fetchone()[0] == 2

        # Non-PIT tables MUST have zero rows
        non_pit_tables = [
            "signal_history",
            "scan_sessions",
            "scan_observations",
            "scan_runs",
            "candidates",
            "candidate_evaluations",
            "candidate_evidence",
            "candidate_reasons",
            "candidate_missing_data",
            "journal_trades",
            "journal_events",
            "journal_outcomes",
        ]
        for tbl in non_pit_tables:
            count = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            assert count == 0, f"Table {tbl} was written to during PIT capture: count={count}"
