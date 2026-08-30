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


def test_orchestration_interruption_persists_completed_observations_and_leaves_run_started(tmp_path) -> None:
    from unittest.mock import MagicMock

    import pytest

    class FatalOrchestrationInterrupt(BaseException):
        """Injected fatal interruption escaping per-symbol Exception handlers."""

    db_path = tmp_path / "crash_test.db"
    clock = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    def fake_lookup(symbol: str, **kwargs) -> date:
        if symbol == "AAPL":
            return date(2026, 9, 15)
        if symbol == "MSFT":
            raise FatalOrchestrationInterrupt("Fatal interruption before MSFT completes")
        raise AssertionError(f"Unexpected symbol: {symbol}")

    with pytest.raises(FatalOrchestrationInterrupt, match="Fatal interruption before MSFT completes"):
        capture_earnings_snapshot(
            symbols=["AAPL", "MSFT"],
            slot=CaptureSlot.MORNING,
            db_path=db_path,
            now_fn=lambda: clock,
            earnings_lookup=fake_lookup,
        )

    # Prove database state after interruption
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        run_row = con.execute("SELECT * FROM pit_capture_runs").fetchone()
        assert run_row is not None
        assert run_row["status"] == "started"
        assert run_row["completed_at"] is None

        snap_rows = con.execute("SELECT * FROM pit_earnings_snapshots").fetchall()
        assert len(snap_rows) == 1
        assert snap_rows[0]["symbol"] == "AAPL"
        assert snap_rows[0]["observation_status"] == "known"
        assert snap_rows[0]["next_earnings_date"] == "2026-09-15"
        assert snap_rows[0]["fact_json"] == '{"next_earnings_date":"2026-09-15"}'

    # Perform exact replay: must return started run, 0 provider calls, 0 mutations
    spy_lookup = MagicMock()
    replay_res = capture_earnings_snapshot(
        symbols=["MSFT", "AAPL"],
        slot=CaptureSlot.MORNING,
        db_path=db_path,
        now_fn=lambda: clock,
        earnings_lookup=spy_lookup,
    )
    spy_lookup.assert_not_called()
    assert replay_res.run.status == CaptureRunStatus.STARTED
    assert len(replay_res.snapshots) == 1
    assert replay_res.snapshots[0].symbol == "AAPL"


def test_clock_backward_and_naive_now_fn_fail_visibly(tmp_path) -> None:
    import pytest

    db_path = tmp_path / "clock_test.db"
    t0 = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
    t_back = datetime(2026, 8, 30, 9, 29, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    # 1. Clock moves backward during lookup
    clock_seq = iter([t0, t0, t_back])

    def lookup_step(sym: str, **kwargs) -> date:
        return date(2026, 9, 15)

    with pytest.raises(ValueError, match="Clock moved backward during lookup for AAPL"):
        capture_earnings_snapshot(
            symbols=["AAPL"],
            slot=CaptureSlot.MORNING,
            db_path=db_path,
            now_fn=lambda: next(clock_seq),
            earnings_lookup=lookup_step,
        )

    # 2. Later naive now_fn during lookup
    db_naive = tmp_path / "clock_naive.db"
    naive_dt = datetime(2026, 8, 30, 9, 30, 0)  # noqa: DTZ001
    clock_seq_naive = iter([t0, naive_dt])
    with pytest.raises(ValueError, match="naive datetime; timezone-aware UTC is required"):
        capture_earnings_snapshot(
            symbols=["AAPL"],
            slot=CaptureSlot.MORNING,
            db_path=db_naive,
            now_fn=lambda: next(clock_seq_naive),
            earnings_lookup=lookup_step,
        )


def test_rejected_validation_paths_do_not_create_database(tmp_path) -> None:
    import pytest

    clock = datetime(2026, 8, 30, 9, 30, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)

    # 1. Blank symbol
    db_blank = tmp_path / "blank.db"
    with pytest.raises(ValueError, match="Blank or whitespace-only"):
        capture_earnings_snapshot(
            symbols=["AAPL", "  "],
            slot=CaptureSlot.MORNING,
            db_path=db_blank,
            now_fn=lambda: clock,
        )
    assert not db_blank.exists()

    # 2. Historical date
    db_hist = tmp_path / "hist.db"
    with pytest.raises(ValueError, match="Historical capture date"):
        capture_earnings_snapshot(
            symbols=["AAPL"],
            slot=CaptureSlot.MORNING,
            capture_date=date(2026, 8, 29),
            db_path=db_hist,
            now_fn=lambda: clock,
        )
    assert not db_hist.exists()

    # 3. Future date
    db_future = tmp_path / "future.db"
    with pytest.raises(ValueError, match="Future capture date"):
        capture_earnings_snapshot(
            symbols=["AAPL"],
            slot=CaptureSlot.MORNING,
            capture_date=date(2026, 8, 31),
            db_path=db_future,
            now_fn=lambda: clock,
        )
    assert not db_future.exists()

    # 4. Before-slot execution
    db_before = tmp_path / "before.db"
    clock_before = datetime(2026, 8, 30, 8, 59, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)
    with pytest.raises(ValueError, match="is before scheduled slot time"):
        capture_earnings_snapshot(
            symbols=["AAPL"],
            slot=CaptureSlot.MORNING,
            capture_date=date(2026, 8, 30),
            db_path=db_before,
            now_fn=lambda: clock_before,
        )
    assert not db_before.exists()
