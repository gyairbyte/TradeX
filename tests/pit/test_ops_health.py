"""Tests for get_pit_slot_health: all health states, missing-DB read-only, drift conflict (MVP-ARCH-001-R7-PIT-001C1)."""
from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from tradex.config import settings_from_mapping
from tradex.pit.models import (
    PIT_CAPTURE_WRITE_CONTRACT_VERSION,
    CaptureKind,
    CaptureRunStatus,
    CaptureSlot,
    PITCaptureRun,
    PITReferenceCaptureRun,
)
from tradex.pit.ops import (
    PITSlotHealthStatus,
    PITUniverseManifest,
    get_pit_slot_health,
)
from tradex.pit.store import create_capture_run, create_reference_capture_run

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures and helpers
# ─────────────────────────────────────────────────────────────────────────────

_TRADING_DATE = date(2026, 1, 2)  # Friday, known trading day
_NOW_AFTER_MORNING = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)  # 10:00 ET, after 09:00 slot
_NOW_AFTER_EVENING = datetime(2026, 1, 3, 2, 0, tzinfo=UTC)   # 21:00 ET, after 20:30 slot


def _manifest(symbols=("AAPL", "MSFT")) -> PITUniverseManifest:
    return PITUniverseManifest(
        contract_version=1,
        universe_id="health-test",
        universe_version="v1",
        effective_from=date(2025, 1, 1),
        symbols=symbols,
        description="",
    )


def _settings(tmp_path: Path):
    return settings_from_mapping({"TRADEX_DB_PATH": str(tmp_path / "signals.db")})


def _make_earnings_run(
    run_id: str,
    manifest: PITUniverseManifest,
    *,
    status: CaptureRunStatus = CaptureRunStatus.SUCCEEDED,
    slot: CaptureSlot = CaptureSlot.MORNING,
    capture_date: date = _TRADING_DATE,
    known_n: int | None = None,
    universe_hash: str | None = None,
) -> PITCaptureRun:
    n = len(manifest.symbols)
    uh = universe_hash if universe_hash is not None else manifest.universe_hash
    now = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
    completed = now if status != CaptureRunStatus.STARTED else None
    resolved_n = (known_n if known_n is not None else n) if status != CaptureRunStatus.STARTED else 0
    unavail = 0
    error = 0
    if status != CaptureRunStatus.STARTED:
        # Ensure counts match requested_n
        unavail = n - (resolved_n + error)
    return PITCaptureRun(
        capture_run_id=run_id,
        idempotency_key=f"pit-earnings-2026-01-02-morning-{run_id[:16]}",
        request_fingerprint="f" * 64,
        capture_kind=CaptureKind.EARNINGS,
        capture_slot=slot,
        capture_date=capture_date,
        scheduled_for=datetime(2026, 1, 2, 14, 0, tzinfo=UTC),
        requested_at=now,
        completed_at=completed,
        requested_provider="yahoo",
        universe_hash=uh,
        requested_n=n,
        known_n=resolved_n,
        unavailable_n=unavail,
        error_n=error,
        status=status,
        created_at=now,
        updated_at=now,
        contract_version=PIT_CAPTURE_WRITE_CONTRACT_VERSION,
    )


def _make_reference_run(
    run_id: str,
    manifest: PITUniverseManifest,
    *,
    status: CaptureRunStatus = CaptureRunStatus.SUCCEEDED,
    slot: CaptureSlot = CaptureSlot.MORNING,
    capture_date: date = _TRADING_DATE,
    universe_hash: str | None = None,
) -> PITReferenceCaptureRun:
    n = len(manifest.symbols)
    uh = universe_hash if universe_hash is not None else manifest.universe_hash
    now = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
    completed = now if status != CaptureRunStatus.STARTED else None
    known_n = n if status == CaptureRunStatus.SUCCEEDED else 0
    unavail = 0
    ambig = 0
    err = 0
    if status == CaptureRunStatus.FAILED:
        err = n
    return PITReferenceCaptureRun(
        capture_run_id=run_id,
        idempotency_key=f"pit-reference-2026-01-02-morning-{run_id[:16]}",
        request_fingerprint="g" * 64,
        capture_slot=slot,
        capture_date=capture_date,
        scheduled_for=datetime(2026, 1, 2, 14, 0, tzinfo=UTC),
        requested_at=now,
        completed_at=completed,
        requested_provider="massive",
        universe_hash=uh,
        requested_n=n,
        known_n=known_n,
        unavailable_n=unavail,
        ambiguous_n=ambig,
        error_n=err,
        status=status,
        created_at=now,
        updated_at=now,
        contract_version=PIT_CAPTURE_WRITE_CONTRACT_VERSION,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Read-only: no DB creation
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthReadOnly:
    def test_missing_db_returns_missing_not_error(self, tmp_path):
        """health returns missing status when DB does not exist - no DB creation."""
        manifest = _manifest()
        settings = _settings(tmp_path)
        nonexistent_db = tmp_path / "does_not_exist.db"

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=nonexistent_db,
                settings=settings,
            )

        assert not nonexistent_db.exists(), "Health must not create the database"
        assert health.overall_status == PITSlotHealthStatus.MISSING

    def test_missing_db_zero_attempt_count(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        nonexistent_db = tmp_path / "no.db"

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=nonexistent_db,
                settings=settings,
            )

        assert health.earnings.attempt_count == 0
        assert health.reference.attempt_count == 0
        assert health.earnings.snapshot_count == 0
        assert health.reference.snapshot_count == 0

    def test_naive_now_raises(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        with pytest.raises(ValueError, match="timezone-aware"):
            get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=datetime(2026, 1, 2, 15, 0),  # naive! intentional — testing rejection  # noqa: DTZ001
                db_path=tmp_path / "no.db",
                settings=settings,
            )


# ─────────────────────────────────────────────────────────────────────────────
# not_due status
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthNotDue:
    def test_non_trading_day_returns_not_due(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        saturday = date(2026, 1, 3)

        with patch("tradex.pit.ops.is_trading_day", return_value=False):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=saturday,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=tmp_path / "no.db",
                settings=settings,
            )

        assert health.overall_status == PITSlotHealthStatus.NOT_DUE

    def test_before_slot_returns_not_due(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        d = _TRADING_DATE
        before_morning = datetime(2026, 1, 2, 8, 0, tzinfo=UTC)  # 3:00 AM ET, before 09:00 slot

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=d,
                slot=CaptureSlot.MORNING,
                now=before_morning,
                db_path=tmp_path / "no.db",
                settings=settings,
            )

        assert health.overall_status == PITSlotHealthStatus.NOT_DUE


# ─────────────────────────────────────────────────────────────────────────────
# healthy status
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthHealthy:
    def test_both_succeeded_returns_healthy(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"

        from tradex.tracker.store import init as store_init
        store_init(db_path=db_path, settings=settings)

        e_run = _make_earnings_run("e-healthy", manifest)
        r_run = _make_reference_run("r-healthy", manifest)
        create_capture_run(e_run, db_path=db_path, settings=settings)
        create_reference_capture_run(r_run, db_path=db_path, settings=settings)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=db_path,
                settings=settings,
            )

        assert health.overall_status == PITSlotHealthStatus.HEALTHY
        assert health.earnings.attempt_count == 1
        assert health.reference.attempt_count == 1

    def test_healthy_run_ids_present(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"

        from tradex.tracker.store import init as store_init
        store_init(db_path=db_path, settings=settings)

        e_run = _make_earnings_run("e-ids", manifest)
        r_run = _make_reference_run("r-ids", manifest)
        create_capture_run(e_run, db_path=db_path, settings=settings)
        create_reference_capture_run(r_run, db_path=db_path, settings=settings)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=db_path,
                settings=settings,
            )

        assert "e-ids" in health.earnings.run_ids
        assert "r-ids" in health.reference.run_ids


# ─────────────────────────────────────────────────────────────────────────────
# degraded status
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthDegraded:
    def test_earnings_partial_reference_succeeded_is_degraded(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"

        from tradex.tracker.store import init as store_init
        store_init(db_path=db_path, settings=settings)

        e_run = _make_earnings_run("e-partial", manifest, status=CaptureRunStatus.PARTIAL, known_n=1)
        r_run = _make_reference_run("r-succ", manifest, status=CaptureRunStatus.SUCCEEDED)
        create_capture_run(e_run, db_path=db_path, settings=settings)
        create_reference_capture_run(r_run, db_path=db_path, settings=settings)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=db_path,
                settings=settings,
            )

        assert health.overall_status == PITSlotHealthStatus.DEGRADED

    def test_both_failed_is_degraded(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"

        from tradex.tracker.store import init as store_init
        store_init(db_path=db_path, settings=settings)

        e_run = _make_earnings_run("e-fail", manifest, status=CaptureRunStatus.FAILED, known_n=0)
        r_run = _make_reference_run("r-fail", manifest, status=CaptureRunStatus.FAILED)
        create_capture_run(e_run, db_path=db_path, settings=settings)
        create_reference_capture_run(r_run, db_path=db_path, settings=settings)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=db_path,
                settings=settings,
            )

        assert health.overall_status == PITSlotHealthStatus.DEGRADED


# ─────────────────────────────────────────────────────────────────────────────
# missing status (only one family has runs)
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthMissing:
    def test_only_earnings_run_is_missing(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"

        from tradex.tracker.store import init as store_init
        store_init(db_path=db_path, settings=settings)

        e_run = _make_earnings_run("e-only", manifest)
        create_capture_run(e_run, db_path=db_path, settings=settings)
        # No reference run

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=db_path,
                settings=settings,
            )

        assert health.overall_status == PITSlotHealthStatus.MISSING
        assert health.earnings.attempt_count == 1
        assert health.reference.attempt_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# universe_conflict status
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthUniverseConflict:
    def test_mismatched_hash_returns_universe_conflict(self, tmp_path):
        new_manifest = _manifest(symbols=("AAPL", "MSFT"))
        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"

        from tradex.tracker.store import init as store_init
        store_init(db_path=db_path, settings=settings)

        old_manifest = _manifest(symbols=("AAPL",))
        assert old_manifest.universe_hash != new_manifest.universe_hash

        # Existing run with different hash
        e_run = _make_earnings_run("e-conflict", old_manifest, universe_hash=old_manifest.universe_hash)
        r_run = _make_reference_run("r-conflict", old_manifest, universe_hash=old_manifest.universe_hash)
        create_capture_run(e_run, db_path=db_path, settings=settings)
        create_reference_capture_run(r_run, db_path=db_path, settings=settings)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=new_manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=db_path,
                settings=settings,
            )

        assert health.overall_status == PITSlotHealthStatus.UNIVERSE_CONFLICT


# ─────────────────────────────────────────────────────────────────────────────
# incomplete status (run in started state)
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthIncomplete:
    def test_started_run_is_incomplete(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"

        from tradex.tracker.store import init as store_init
        store_init(db_path=db_path, settings=settings)

        # Earnings still in STARTED state (no completed_at, all zeros)
        now = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
        e_started = PITCaptureRun(
            capture_run_id="e-started",
            idempotency_key="pit-earnings-2026-01-02-morning-estrtd",
            request_fingerprint="h" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=_TRADING_DATE,
            scheduled_for=now,
            requested_at=now,
            completed_at=None,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=0,
            unavailable_n=0,
            error_n=0,
            status=CaptureRunStatus.STARTED,
            created_at=now,
            updated_at=now,
            contract_version=PIT_CAPTURE_WRITE_CONTRACT_VERSION,
        )
        r_run = _make_reference_run("r-done", manifest)
        create_capture_run(e_started, db_path=db_path, settings=settings)
        create_reference_capture_run(r_run, db_path=db_path, settings=settings)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=db_path,
                settings=settings,
            )

        assert health.overall_status == PITSlotHealthStatus.INCOMPLETE


# ─────────────────────────────────────────────────────────────────────────────
# Metadata fields
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthMetadata:
    def test_health_contains_manifest_metadata(self, tmp_path):
        manifest = _manifest(symbols=("AAPL",))
        settings = _settings(tmp_path)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.EVENING,
                now=_NOW_AFTER_EVENING,
                db_path=tmp_path / "no.db",
                settings=settings,
            )

        assert health.universe_id == manifest.universe_id
        assert health.universe_version == manifest.universe_version
        assert health.manifest_hash == manifest.manifest_hash
        assert health.universe_hash == manifest.universe_hash
        assert health.capture_date == _TRADING_DATE
        assert health.slot == CaptureSlot.EVENING

    def test_health_checked_at_is_utc_aware(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        now_aware = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=now_aware,
                db_path=tmp_path / "no.db",
                settings=settings,
            )

        assert health.health_checked_at.tzinfo is not None

    def test_historical_date_inspectable(self, tmp_path):
        """get_pit_slot_health can inspect historical dates read-only."""
        manifest = _manifest()
        settings = _settings(tmp_path)
        historical_date = date(2025, 6, 2)  # a historical Monday
        past_now = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)  # current time, after the historical date

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=historical_date,
                slot=CaptureSlot.MORNING,
                now=past_now,
                db_path=tmp_path / "no.db",
                settings=settings,
            )

        # slot_due = True because now >= scheduled_for of historical date
        assert health.overall_status in (PITSlotHealthStatus.MISSING, PITSlotHealthStatus.NOT_DUE, PITSlotHealthStatus.HEALTHY)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-attempt lag and SQL trace read-only tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthLags:
    def test_multi_attempt_health_lag(self, tmp_path):
        """Attempt 1 = STARTED (+10s), Attempt 2 = SUCCEEDED (+30s, completed +60s).
        Assert first_request_lag_seconds == 10.0, completion_lag_seconds == 60.0.
        """
        manifest = _manifest()
        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"

        from tradex.tracker.store import init as store_init
        store_init(db_path=db_path, settings=settings)

        scheduled_for = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)

        # Attempt 1: STARTED at scheduled_for + 10s (completed_at=None)
        e_run_1 = PITCaptureRun(
            capture_run_id="e-attempt-1",
            idempotency_key="pit-earnings-2026-01-02-morning-att1",
            request_fingerprint="1" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=_TRADING_DATE,
            scheduled_for=scheduled_for,
            requested_at=scheduled_for + timedelta(seconds=10),
            completed_at=None,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=0,
            unavailable_n=0,
            error_n=0,
            status=CaptureRunStatus.STARTED,
            created_at=scheduled_for + timedelta(seconds=10),
            updated_at=scheduled_for + timedelta(seconds=10),
            contract_version=PIT_CAPTURE_WRITE_CONTRACT_VERSION,
        )
        # Attempt 2: SUCCEEDED at scheduled_for + 30s, completed at scheduled_for + 60s
        e_run_2 = PITCaptureRun(
            capture_run_id="e-attempt-2",
            idempotency_key="pit-earnings-2026-01-02-morning-att2",
            request_fingerprint="2" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=_TRADING_DATE,
            scheduled_for=scheduled_for,
            requested_at=scheduled_for + timedelta(seconds=30),
            completed_at=scheduled_for + timedelta(seconds=60),
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=scheduled_for + timedelta(seconds=30),
            updated_at=scheduled_for + timedelta(seconds=60),
            contract_version=PIT_CAPTURE_WRITE_CONTRACT_VERSION,
        )

        create_capture_run(e_run_1, db_path=db_path, settings=settings)
        create_capture_run(e_run_2, db_path=db_path, settings=settings)

        # Also reference run so slot is not missing
        r_run = _make_reference_run("r-attempt-1", manifest)
        create_reference_capture_run(r_run, db_path=db_path, settings=settings)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=db_path,
                settings=settings,
            )

        assert health.earnings.attempt_count == 2
        assert health.earnings.first_request_lag_seconds == 10.0
        assert health.earnings.completion_lag_seconds == 60.0


class TestHealthSqlTraceReadOnly:
    def test_health_existing_db_read_only_sql_trace(self, tmp_path):
        """get_pit_slot_health on existing database must perform zero write statements."""
        manifest = _manifest()
        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"

        from tradex.tracker.store import init as store_init
        store_init(db_path=db_path, settings=settings)

        e_run = _make_earnings_run("e-trace", manifest)
        r_run = _make_reference_run("r-trace", manifest)
        create_capture_run(e_run, db_path=db_path, settings=settings)
        create_reference_capture_run(r_run, db_path=db_path, settings=settings)

        # Record pre-inspection database snapshot
        with sqlite3.connect(str(db_path)) as con:
            pre_e_count = con.execute("SELECT COUNT(*) FROM pit_capture_runs").fetchone()[0]
            pre_r_count = con.execute("SELECT COUNT(*) FROM pit_reference_capture_runs").fetchone()[0]
            pre_schema = con.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()

        executed_statements: list[str] = []
        orig_connect = sqlite3.connect

        def tracing_connect(*args, **kwargs):
            conn = orig_connect(*args, **kwargs)
            conn.set_trace_callback(executed_statements.append)
            return conn

        with (
            patch("sqlite3.connect", side_effect=tracing_connect),
            patch("tradex.pit.ops.is_trading_day", return_value=True),
        ):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=_TRADING_DATE,
                slot=CaptureSlot.MORNING,
                now=_NOW_AFTER_MORNING,
                db_path=db_path,
                settings=settings,
            )

        assert health.overall_status == PITSlotHealthStatus.HEALTHY
        assert len(executed_statements) > 0, "Trace should capture executed SQL statements"

        mutating_keywords = (
            "insert ",
            "update ",
            "delete ",
            "replace ",
            "create ",
            "alter ",
            "drop ",
            "pragma user_version =",
        )
        for stmt in executed_statements:
            normalized = stmt.strip().lower()
            for kw in mutating_keywords:
                assert not normalized.startswith(kw) and kw not in normalized, (
                    f"Forbidden mutating SQL executed during read-only health check: {stmt}"
                )

        # Verify post-inspection database is completely unchanged
        with sqlite3.connect(str(db_path)) as con:
            post_e_count = con.execute("SELECT COUNT(*) FROM pit_capture_runs").fetchone()[0]
            post_r_count = con.execute("SELECT COUNT(*) FROM pit_reference_capture_runs").fetchone()[0]
            post_schema = con.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()

        assert post_e_count == pre_e_count
        assert post_r_count == pre_r_count
        assert post_schema == pre_schema
