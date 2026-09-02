"""Deterministic migration tests for signals.db schema v7 and reference PIT capture tables."""
from __future__ import annotations

import sqlite3

import pytest

from tradex.tracker import store


def _build_v6_db(db_path: str) -> None:
    """Build a representative schema v6 database with legacy signals, candidates, journal trades, and earnings PIT rows."""
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        store._create_schema_v1(con)
        store._migrate_v1_to_v2(con)
        store._migrate_v2_to_v3(con)
        store._migrate_v3_to_v4(con)
        store._migrate_v4_to_v5(con)
        store._migrate_v5_to_v6(con)

        # Seed legacy signal and observation data
        con.execute(
            """
            INSERT INTO scan_sessions (
                session_id, scan_time, trading_date, timeframe, requested_provider,
                actual_provider, status, observations_complete, requested_n, observations_n, signals_n
            ) VALUES (
                'session-v6-001', '2026-08-20T14:00:00Z', '2026-08-20', 'intraday', 'schwab',
                'schwab', 'completed', 1, 1, 1, 1
            )
            """
        )
        con.execute(
            """
            INSERT INTO scan_observations (
                session_id, ticker, status, score, last_close, volume_ratio, rsi, provider
            ) VALUES (
                'session-v6-001', 'AAPL', 'signal', 75, 220.5, 1.8, 62.0, 'schwab'
            )
            """
        )
        con.execute(
            """
            INSERT INTO signal_history (
                ticker, timeframe, scan_time, score, last_close, provider, scan_session_id, trading_date
            ) VALUES (
                'AAPL', 'intraday', '2026-08-20T14:00:00Z', 75, 220.5, 'schwab', 'session-v6-001', '2026-08-20'
            )
            """
        )

        # Seed candidate snapshot
        con.execute(
            """
            INSERT INTO candidates (
                candidate_id, contract_version, symbol, decision_timestamp, trading_date,
                security_identity_status, created_at
            ) VALUES (
                'cand-v6-001', 1, 'AAPL', '2026-08-20T14:00:00Z', '2026-08-20', 'unknown', '2026-08-20T14:00:00Z'
            )
            """
        )

        # Seed Journal trade
        con.execute(
            """
            INSERT INTO journal_trades (
                journal_id, contract_version, idempotency_key, candidate_id, strategy_id,
                strategy_version, side, state, decision_timestamp, plan_created_at,
                planned_entry, created_at, updated_at
            ) VALUES (
                'j-v6-001', 1, 'idem-v6-001', 'cand-v6-001', 'strat-1',
                'v1', 'long', 'planned', '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z',
                150.0, '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z'
            )
            """
        )

        # Seed PIT earnings run and snapshot
        con.execute(
            """
            INSERT INTO pit_capture_runs (
                capture_run_id, contract_version, idempotency_key, request_fingerprint,
                capture_kind, capture_slot, capture_date, scheduled_for, requested_at,
                completed_at, requested_provider, universe_hash, requested_n, known_n,
                unavailable_n, error_n, status, created_at, updated_at
            ) VALUES (
                'run-v6-001', 1, 'pit-earnings-2026-08-29-evening-1234', 'fp-v6-001',
                'earnings', 'evening', '2026-08-29', '2026-08-30T00:30:00Z', '2026-08-30T00:30:00Z',
                '2026-08-30T00:30:05Z', 'yahoo', 'uhash-v6', 1, 1, 0, 0, 'succeeded',
                '2026-08-30T00:30:00Z', '2026-08-30T00:30:05Z'
            )
            """
        )
        con.execute(
            """
            INSERT INTO pit_earnings_snapshots (
                snapshot_id, contract_version, capture_run_id, symbol,
                observation_status, next_earnings_date, provider,
                request_started_at, response_received_at, fact_hash, fact_json, created_at
            ) VALUES (
                'snap-v6-001', 1, 'run-v6-001', 'AAPL', 'known', '2026-10-25', 'yahoo',
                '2026-08-30T00:30:00Z', '2026-08-30T00:30:05Z', 'fhash-v6', '{"next_earnings_date":"2026-10-25"}',
                '2026-08-30T00:30:05Z'
            )
            """
        )

        con.execute("PRAGMA user_version = 6")
        con.commit()
    finally:
        con.close()


def _build_v5_db(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        store._create_schema_v1(con)
        store._migrate_v1_to_v2(con)
        store._migrate_v2_to_v3(con)
        store._migrate_v3_to_v4(con)
        store._migrate_v4_to_v5(con)
        con.execute("PRAGMA user_version = 5")
        con.commit()
    finally:
        con.close()


def _build_v0_db(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            """
            CREATE TABLE signal_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker       TEXT    NOT NULL,
                timeframe    TEXT    NOT NULL,
                scan_time    TEXT    NOT NULL,
                score        INTEGER NOT NULL,
                last_close   REAL,
                outcome_close REAL,
                outcome_pct   REAL,
                outcome_at    TEXT
            );
            CREATE TABLE scan_runs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time  TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                tickers_n INTEGER,
                hits_n    INTEGER
            );
            INSERT INTO signal_history (ticker, timeframe, scan_time, score, last_close)
            VALUES ('MSFT', 'intraday', '2026-08-18T14:00:00Z', 80, 420.0);
            PRAGMA user_version = 0;
            """
        )
        con.commit()
    finally:
        con.close()


def test_fresh_db_creates_schema_v7(tmp_path) -> None:
    db_path = str(tmp_path / "fresh_v7.db")
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        assert version == 7

        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        # Legacy tables
        assert "signal_history" in tables
        assert "scan_runs" in tables
        assert "scan_sessions" in tables
        assert "scan_observations" in tables
        # Candidate v4 tables
        assert "candidates" in tables
        assert "candidate_evaluations" in tables
        assert "candidate_evidence" in tables
        assert "candidate_reasons" in tables
        assert "candidate_missing_data" in tables
        # Journal v5 tables
        assert "journal_trades" in tables
        assert "journal_events" in tables
        assert "journal_outcomes" in tables
        # Earnings PIT v6 tables
        assert "pit_capture_runs" in tables
        assert "pit_earnings_snapshots" in tables
        # Reference PIT v7 tables
        assert "pit_reference_capture_runs" in tables
        assert "pit_reference_snapshots" in tables

        # Verify PIT reference indexes
        indexes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert "idx_pit_ref_runs_date_slot" in indexes
        assert "idx_pit_ref_runs_status" in indexes
        assert "idx_pit_ref_runs_requested" in indexes
        assert "idx_pit_ref_snaps_run_id" in indexes
        assert "idx_pit_ref_snaps_symbol" in indexes
        assert "idx_pit_ref_snaps_status" in indexes


def test_v6_to_v7_migration_preserves_earnings_pit_journal_candidate_and_legacy_data(tmp_path) -> None:
    db_path = str(tmp_path / "v6.db")
    _build_v6_db(db_path)

    # Migrate v6 -> v7
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 7

        # Check legacy rows preserved
        sh = con.execute("SELECT ticker, score, provider FROM signal_history WHERE ticker = 'AAPL'").fetchone()
        assert sh == ("AAPL", 75, "schwab")

        # Check candidate rows preserved
        cand = con.execute("SELECT candidate_id, symbol FROM candidates WHERE candidate_id = 'cand-v6-001'").fetchone()
        assert cand == ("cand-v6-001", "AAPL")

        # Check journal rows preserved
        j = con.execute("SELECT journal_id, candidate_id, planned_entry FROM journal_trades WHERE journal_id = 'j-v6-001'").fetchone()
        assert j == ("j-v6-001", "cand-v6-001", 150.0)

        # Check earnings PIT rows preserved
        run = con.execute("SELECT capture_run_id, capture_kind, requested_provider FROM pit_capture_runs WHERE capture_run_id = 'run-v6-001'").fetchone()
        assert run == ("run-v6-001", "earnings", "yahoo")

        snap = con.execute("SELECT snapshot_id, symbol, next_earnings_date FROM pit_earnings_snapshots WHERE snapshot_id = 'snap-v6-001'").fetchone()
        assert snap == ("snap-v6-001", "AAPL", "2026-10-25")

        # Check zero reference PIT rows created (no backfill)
        assert con.execute("SELECT COUNT(*) FROM pit_reference_capture_runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM pit_reference_snapshots").fetchone()[0] == 0


def test_v5_to_v7_migration(tmp_path) -> None:
    db_path = str(tmp_path / "v5.db")
    _build_v5_db(db_path)
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 7
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "pit_capture_runs" in tables
        assert "pit_earnings_snapshots" in tables
        assert "pit_reference_capture_runs" in tables
        assert "pit_reference_snapshots" in tables


def test_v0_db_migrates_to_v7(tmp_path) -> None:
    db_path = str(tmp_path / "v0.db")
    _build_v0_db(db_path)
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 7
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "pit_reference_capture_runs" in tables
        assert "pit_reference_snapshots" in tables


def test_v7_repeat_init_is_idempotent(tmp_path) -> None:
    db_path = str(tmp_path / "v7_idempotent.db")
    store.init(db_path)
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 7


def test_future_schema_version_rejected(tmp_path) -> None:
    db_path = str(tmp_path / "v99.db")
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA user_version = 99")
        con.commit()
    finally:
        con.close()

    with pytest.raises(store.StoreError, match="newer than supported schema version 7"):
        store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 99


def test_atomic_rollback_on_v6_to_v7_failure(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "v6_fail.db")
    _build_v6_db(db_path)

    def failing_migrate(con):
        con.execute("CREATE TABLE IF NOT EXISTS pit_reference_capture_runs (capture_run_id TEXT PRIMARY KEY)")
        raise sqlite3.OperationalError("injected v6->v7 failure")

    monkeypatch.setattr(store, "_migrate_v6_to_v7", failing_migrate)

    with pytest.raises(sqlite3.OperationalError, match="injected v6->v7 failure"):
        store.init(db_path)

    with sqlite3.connect(db_path) as con:
        # Version must stay 6
        assert con.execute("PRAGMA user_version").fetchone()[0] == 6
        # Partial table was rolled back
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "pit_reference_capture_runs" not in tables


def test_pit_reference_capture_runs_check_constraints(tmp_path) -> None:
    db_path = str(tmp_path / "check_ref_runs.db")
    store.init(db_path)

    with store._conn(db_path=tmp_path / "check_ref_runs.db") as con:
        # Invalid capture_slot
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_reference_capture_runs (
                    capture_run_id, idempotency_key, request_fingerprint,
                    capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                    universe_hash, requested_n, status, created_at, updated_at
                ) VALUES (
                    'run-1', 'idem-1', 'fp-1', 'midnight', '2026-08-30',
                    '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z', 'massive', 'uhash',
                    1, 'started', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z'
                )
                """
            )

        # Terminal status without completed_at fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_reference_capture_runs (
                    capture_run_id, idempotency_key, request_fingerprint,
                    capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                    universe_hash, requested_n, known_n, unavailable_n, ambiguous_n, error_n,
                    status, created_at, updated_at
                ) VALUES (
                    'run-1', 'idem-1', 'fp-1', 'morning', '2026-08-30',
                    '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z', 'massive', 'uhash',
                    1, 1, 0, 0, 0, 'succeeded', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z'
                )
                """
            )

        # Terminal status with count mismatch fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_reference_capture_runs (
                    capture_run_id, idempotency_key, request_fingerprint,
                    capture_slot, capture_date, scheduled_for, requested_at, completed_at,
                    requested_provider, universe_hash, requested_n, known_n, unavailable_n, ambiguous_n, error_n,
                    status, created_at, updated_at
                ) VALUES (
                    'run-1', 'idem-1', 'fp-1', 'morning', '2026-08-30',
                    '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z', '2026-08-30T13:05:00Z',
                    'massive', 'uhash', 3, 1, 0, 0, 0, 'succeeded', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z'
                )
                """
            )


def test_pit_reference_snapshots_check_constraints(tmp_path) -> None:
    db_path = str(tmp_path / "check_ref_snaps.db")
    store.init(db_path)

    with store._conn(db_path=tmp_path / "check_ref_snaps.db") as con:
        # Seed a valid run
        con.execute(
            """
            INSERT INTO pit_reference_capture_runs (
                capture_run_id, idempotency_key, request_fingerprint,
                capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                universe_hash, requested_n, status, created_at, updated_at
            ) VALUES (
                'run-ref-1', 'idem-ref-1', 'fp-ref-1', 'morning', '2026-08-30',
                '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z', 'massive', 'uhash',
                1, 'started', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z'
            )
            """
        )

        # Foreign key violation
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_reference_snapshots (
                    snapshot_id, capture_run_id, symbol, observation_status,
                    provider, provider_query_date, request_started_at, response_received_at,
                    fact_hash, fact_json, created_at
                ) VALUES (
                    'snap-1', 'nonexistent-run', 'AAPL', 'known',
                    'massive', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:01Z',
                    'hash', '{}', '2026-08-30T13:00:01Z'
                )
                """
            )

        # Invalid observation_status
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_reference_snapshots (
                    snapshot_id, capture_run_id, symbol, observation_status,
                    provider, provider_query_date, request_started_at, response_received_at,
                    fact_hash, fact_json, created_at
                ) VALUES (
                    'snap-1', 'run-ref-1', 'AAPL', 'invalid_status',
                    'massive', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:01Z',
                    'hash', '{}', '2026-08-30T13:00:01Z'
                )
                """
            )

        # provider_active valid values: NULL, 0, 1
        for idx, val in enumerate((None, 0, 1)):
            con.execute(
                """
                INSERT INTO pit_reference_snapshots (
                    snapshot_id, capture_run_id, symbol, observation_status,
                    provider, provider_query_date, provider_active, request_started_at, response_received_at,
                    fact_hash, fact_json, created_at
                ) VALUES (
                    ?, 'run-ref-1', ?, 'known',
                    'massive', '2026-08-30', ?, '2026-08-30T13:00:00Z', '2026-08-30T13:00:01Z',
                    'hash', '{}', '2026-08-30T13:00:01Z'
                )
                """,
                (f"snap-act-{idx}", f"SYM{idx}", val),
            )

        # provider_active invalid values: 2, -1
        for idx, bad_val in enumerate((2, -1, 99)):
            with pytest.raises(sqlite3.IntegrityError):
                con.execute(
                    """
                    INSERT INTO pit_reference_snapshots (
                        snapshot_id, capture_run_id, symbol, observation_status,
                        provider, provider_query_date, provider_active, request_started_at, response_received_at,
                        fact_hash, fact_json, created_at
                    ) VALUES (
                        ?, 'run-ref-1', ?, 'known',
                        'massive', '2026-08-30', ?, '2026-08-30T13:00:00Z', '2026-08-30T13:00:01Z',
                        'hash', '{}', '2026-08-30T13:00:01Z'
                    )
                    """,
                    (f"snap-bad-{idx}", f"BADSYM{idx}", bad_val),
                )


def test_pit_reference_metadata_canonical_json_persistence(tmp_path) -> None:
    from datetime import UTC, date, datetime

    from tradex.pit import store as pit_store
    from tradex.pit.models import (
        PITReferenceSnapshot,
        ReferenceObservationStatus,
        compute_fact_hash,
        serialize_canonical_fact_json,
    )

    db_path = tmp_path / "metadata_json.db"
    store.init(db_path)

    # Seed run
    with store._conn(db_path=db_path) as con:
        con.execute(
            """
            INSERT INTO pit_reference_capture_runs (
                capture_run_id, idempotency_key, request_fingerprint,
                capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                universe_hash, requested_n, status, created_at, updated_at
            ) VALUES (
                'run-m1', 'idem-m1', 'fp-m1', 'evening', '2026-08-30',
                '2026-08-31T00:30:00Z', '2026-08-31T00:30:00Z', 'massive', 'uhash',
                1, 'started', '2026-08-31T00:30:00Z', '2026-08-31T00:30:00Z'
            )
            """
        )

    fact_json = serialize_canonical_fact_json({"active": True, "ticker": "AAPL"})
    snap = PITReferenceSnapshot(
        snapshot_id="snap-m1",
        capture_run_id="run-m1",
        symbol="AAPL",
        observation_status=ReferenceObservationStatus.KNOWN,
        provider="massive",
        provider_query_date=date(2026, 8, 30),
        provider_request_ids=("req-b", "req-a"),
        provider_ticker="AAPL",
        provider_name="Apple",
        provider_market="stocks",
        provider_locale="us",
        provider_active=True,
        provider_type_code="CS",
        provider_primary_exchange="XNAS",
        provider_cik="0000320193",
        provider_composite_figi="FIGI1",
        provider_share_class_figi="FIGI2",
        provider_last_updated_at=datetime(2026, 8, 30, 14, 0, tzinfo=UTC),
        provider_delisted_at=None,
        missing_fields=("delisted_utc", "last_updated_utc"),
        request_started_at=datetime(2026, 8, 30, 14, 0, tzinfo=UTC),
        response_received_at=datetime(2026, 8, 30, 14, 0, 1, tzinfo=UTC),
        fact_hash=compute_fact_hash(fact_json),
        fact_json=fact_json,
        error_category=None,
        error_message=None,
        created_at=datetime(2026, 8, 30, 14, 0, 1, tzinfo=UTC),
    )

    pit_store.insert_reference_snapshots([snap], db_path=db_path)

    # Query raw SQLite rows to verify deterministic no-whitespace JSON
    with store._conn(db_path=db_path) as con:
        row = con.execute("SELECT provider_request_ids_json, missing_fields_json FROM pit_reference_snapshots WHERE snapshot_id = 'snap-m1'").fetchone()
        assert row[0] == '["req-b","req-a"]'
        assert row[1] == '["delisted_utc","last_updated_utc"]'
