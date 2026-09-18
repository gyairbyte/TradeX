"""Deterministic migration tests for signals.db schema v8 and PIT contract v2 tables."""
from __future__ import annotations

import sqlite3

import pytest

from tradex.tracker import store


def _build_v7_db(db_path: str) -> None:
    """Build a representative schema v7 database with legacy signals, candidates, journal trades, earnings PIT, and reference PIT rows."""
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        store._create_schema_v1(con)
        store._migrate_v1_to_v2(con)
        store._migrate_v2_to_v3(con)
        store._migrate_v3_to_v4(con)
        store._migrate_v4_to_v5(con)
        store._migrate_v5_to_v6(con)
        store._migrate_v6_to_v7(con)

        # Seed legacy signal and observation data
        con.execute(
            """
            INSERT INTO scan_sessions (
                session_id, scan_time, trading_date, timeframe, requested_provider,
                actual_provider, status, observations_complete, requested_n, observations_n, signals_n
            ) VALUES (
                'session-v7-001', '2026-08-20T14:00:00Z', '2026-08-20', 'intraday', 'schwab',
                'schwab', 'completed', 1, 1, 1, 1
            )
            """
        )
        con.execute(
            """
            INSERT INTO scan_observations (
                session_id, ticker, status, score, last_close, volume_ratio, rsi, provider
            ) VALUES (
                'session-v7-001', 'AAPL', 'signal', 75, 220.5, 1.8, 62.0, 'schwab'
            )
            """
        )
        con.execute(
            """
            INSERT INTO signal_history (
                ticker, timeframe, scan_time, score, last_close, provider, scan_session_id, trading_date
            ) VALUES (
                'AAPL', 'intraday', '2026-08-20T14:00:00Z', 75, 220.5, 'schwab', 'session-v7-001', '2026-08-20'
            )
            """
        )
        con.execute(
            """
            INSERT INTO scan_runs (
                run_time, timeframe, tickers_n, hits_n, provider, session_id, status, counts_complete, source
            ) VALUES (
                '2026-08-20T14:00:00Z', 'intraday', 1, 1, 'schwab', 'session-v7-001', 'completed', 1, 'native'
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
                'cand-v7-001', 1, 'AAPL', '2026-08-20T14:00:00Z', '2026-08-20', 'unknown', '2026-08-20T14:00:00Z'
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
                'j-v7-001', 1, 'idem-v7-001', 'cand-v7-001', 'strat-1',
                'v1', 'long', 'planned', '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z',
                150.0, '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z'
            )
            """
        )

        # Seed PIT earnings run and snapshots
        con.execute(
            """
            INSERT INTO pit_capture_runs (
                capture_run_id, contract_version, idempotency_key, request_fingerprint,
                capture_kind, capture_slot, capture_date, scheduled_for, requested_at,
                completed_at, requested_provider, universe_hash, requested_n, known_n,
                unavailable_n, error_n, status, created_at, updated_at
            ) VALUES (
                'run-v7-001', 1, 'pit-earnings-2026-08-29-evening-1234', 'fp-v7-001',
                'earnings', 'evening', '2026-08-29', '2026-08-30T00:30:00Z', '2026-08-30T00:30:00Z',
                '2026-08-30T00:30:05Z', 'yahoo', 'uhash-v7', 2, 1, 1, 0, 'succeeded',
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
                'snap-v7-001', 1, 'run-v7-001', 'AAPL', 'known', '2026-10-25', 'yahoo',
                '2026-08-30T00:30:00Z', '2026-08-30T00:30:05Z', 'fhash-v7-1', '{"next_earnings_date":"2026-10-25"}',
                '2026-08-30T00:30:05Z'
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
                'snap-v7-002', 1, 'run-v7-001', 'MSFT', 'unavailable', NULL, 'yahoo',
                '2026-08-30T00:30:00Z', '2026-08-30T00:30:05Z', 'fhash-v7-2', '{"next_earnings_date":null}',
                '2026-08-30T00:30:05Z'
            )
            """
        )

        # Seed PIT reference run and snapshot
        con.execute(
            """
            INSERT INTO pit_reference_capture_runs (
                capture_run_id, contract_version, idempotency_key, request_fingerprint,
                capture_slot, capture_date, scheduled_for, requested_at, completed_at,
                requested_provider, universe_hash, requested_n, known_n, unavailable_n,
                ambiguous_n, error_n, status, created_at, updated_at
            ) VALUES (
                'run-ref-v7-001', 1, 'pit-ref-2026-08-29-evening-1234', 'fp-ref-v7-001',
                'evening', '2026-08-29', '2026-08-30T00:30:00Z', '2026-08-30T00:30:00Z',
                '2026-08-30T00:30:05Z', 'massive', 'uhash-ref-v7', 1, 1, 0, 0, 0, 'succeeded',
                '2026-08-30T00:30:00Z', '2026-08-30T00:30:05Z'
            )
            """
        )
        con.execute(
            """
            INSERT INTO pit_reference_snapshots (
                snapshot_id, contract_version, capture_run_id, symbol, observation_status,
                provider, provider_query_date, provider_active, request_started_at, response_received_at,
                fact_hash, fact_json, created_at
            ) VALUES (
                'snap-ref-v7-001', 1, 'run-ref-v7-001', 'AAPL', 'known',
                'massive', '2026-08-29', 1, '2026-08-30T00:30:00Z', '2026-08-30T00:30:05Z',
                'fhash-ref-v7', '{"active":true}', '2026-08-30T00:30:05Z'
            )
            """
        )

        con.execute("PRAGMA user_version = 7")
        con.commit()
    finally:
        con.close()


def _build_v0_db(db_path: str) -> None:
    """Build a pre-DATA-001 legacy v0 database."""
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
            INSERT INTO scan_runs (run_time, timeframe, tickers_n, hits_n)
            VALUES ('2026-08-18T14:00:00Z', 'intraday', 10, 1);
            PRAGMA user_version = 0;
            """
        )
        con.commit()
    finally:
        con.close()


def test_fresh_db_creates_schema_v8(tmp_path) -> None:
    db_path = str(tmp_path / "fresh_v8.db")
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        assert version == 8

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
        # PIT v8 tables
        assert "pit_capture_runs" in tables
        assert "pit_earnings_snapshots" in tables
        assert "pit_reference_capture_runs" in tables
        assert "pit_reference_snapshots" in tables

        # Verify PIT v8 columns
        pit_runs_cols = {r[1] for r in con.execute("PRAGMA table_info(pit_capture_runs)")}
        assert "manifest_hash" in pit_runs_cols
        assert "not_applicable_n" in pit_runs_cols

        pit_snaps_cols = {r[1] for r in con.execute("PRAGMA table_info(pit_earnings_snapshots)")}
        assert "observation_origin" in pit_snaps_cols
        assert "applicability_source" in pit_snaps_cols
        assert "provider_call_attempted" in pit_snaps_cols

        pit_ref_runs_cols = {r[1] for r in con.execute("PRAGMA table_info(pit_reference_capture_runs)")}
        assert "manifest_hash" in pit_ref_runs_cols

        # Verify PIT indexes
        indexes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert "idx_pit_runs_date_slot" in indexes
        assert "idx_pit_runs_status" in indexes
        assert "idx_pit_runs_requested" in indexes
        assert "idx_pit_snaps_run_id" in indexes
        assert "idx_pit_snaps_symbol" in indexes
        assert "idx_pit_snaps_next_date" in indexes
        assert "idx_pit_snaps_status" in indexes
        assert "idx_pit_ref_runs_date_slot" in indexes
        assert "idx_pit_ref_runs_status" in indexes
        assert "idx_pit_ref_runs_requested" in indexes
        assert "idx_pit_ref_snaps_run_id" in indexes
        assert "idx_pit_ref_snaps_symbol" in indexes
        assert "idx_pit_ref_snaps_status" in indexes


def test_v7_to_v8_migration_preserves_all_data_and_backfills_v8_columns(tmp_path) -> None:
    db_path = str(tmp_path / "v7.db")
    _build_v7_db(db_path)

    # Perform migration
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 8

        # Exact row counts
        assert con.execute("SELECT COUNT(*) FROM scan_sessions").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM scan_observations").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM signal_history").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM journal_trades").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM pit_capture_runs").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM pit_earnings_snapshots").fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM pit_reference_capture_runs").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM pit_reference_snapshots").fetchone()[0] == 1

        # Check v7 row migration in pit_capture_runs
        run = con.execute(
            """
            SELECT capture_run_id, contract_version, manifest_hash, not_applicable_n, requested_n, known_n, unavailable_n, error_n
            FROM pit_capture_runs WHERE capture_run_id = 'run-v7-001'
            """
        ).fetchone()
        assert run == ("run-v7-001", 1, None, 0, 2, 1, 1, 0)

        # Check v7 row migration in pit_earnings_snapshots
        snap_known = con.execute(
            """
            SELECT snapshot_id, contract_version, observation_origin,
                   applicability_source, provider_call_attempted, observation_status, next_earnings_date
            FROM pit_earnings_snapshots WHERE snapshot_id = 'snap-v7-001'
            """
        ).fetchone()
        assert snap_known == ("snap-v7-001", 1, "provider", None, 1, "known", "2026-10-25")

        snap_unavail = con.execute(
            """
            SELECT snapshot_id, contract_version, observation_origin,
                   applicability_source, provider_call_attempted, observation_status, next_earnings_date
            FROM pit_earnings_snapshots WHERE snapshot_id = 'snap-v7-002'
            """
        ).fetchone()
        assert snap_unavail == ("snap-v7-002", 1, "provider", None, 1, "unavailable", None)

        # Check v7 row migration in pit_reference_capture_runs
        ref_run = con.execute(
            """
            SELECT capture_run_id, contract_version, manifest_hash, status
            FROM pit_reference_capture_runs WHERE capture_run_id = 'run-ref-v7-001'
            """
        ).fetchone()
        assert ref_run == ("run-ref-v7-001", 1, None, "succeeded")

        # Check v7 row migration in pit_reference_snapshots
        ref_snap = con.execute(
            """
            SELECT snapshot_id, contract_version, provider_active
            FROM pit_reference_snapshots WHERE snapshot_id = 'snap-ref-v7-001'
            """
        ).fetchone()
        assert ref_snap == ("snap-ref-v7-001", 1, 1)

        # Foreign keys are consistent
        fk_check = con.execute("PRAGMA foreign_key_check").fetchall()
        assert fk_check == []


def test_v8_repeat_init_is_idempotent(tmp_path) -> None:
    db_path = str(tmp_path / "v8_idempotent.db")
    store.init(db_path)
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 8


def test_v8_future_schema_version_rejected(tmp_path) -> None:
    db_path = str(tmp_path / "v99.db")
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA user_version = 99")
        con.commit()
    finally:
        con.close()

    with pytest.raises(store.StoreError, match="newer than supported schema version 8"):
        store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 99


def test_atomic_rollback_on_v7_to_v8_failure(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "v7_fail.db")
    _build_v7_db(db_path)

    original_execute_schema = store._execute_schema_statements

    def failing_execute_schema(con, script):
        if "pit_capture_runs_v8" in script:
            raise sqlite3.OperationalError("injected v7->v8 rebuild failure")
        return original_execute_schema(con, script)

    monkeypatch.setattr(store, "_execute_schema_statements", failing_execute_schema)

    with pytest.raises(sqlite3.OperationalError, match="injected v7->v8 rebuild failure"):
        store.init(db_path)

    with sqlite3.connect(db_path) as con:
        # Version must stay 7
        assert con.execute("PRAGMA user_version").fetchone()[0] == 7
        # Original rows remain completely intact
        assert con.execute("SELECT COUNT(*) FROM pit_capture_runs").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM pit_earnings_snapshots").fetchone()[0] == 2
        # No v8 temporary/staging tables leaked
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "pit_capture_runs_v8" not in tables


def test_atomic_rollback_on_row_count_mismatch(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "v7_count_fail.db")
    _build_v7_db(db_path)

    real_connect = sqlite3.connect

    class ConnectionProxy:
        def __init__(self, con):
            self._con = con

        def __getattr__(self, name):
            return getattr(self._con, name)

        def __enter__(self):
            self._con.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self._con.__exit__(exc_type, exc_val, exc_tb)

        def execute(self, sql, *args, **kwargs):
            if "INSERT INTO pit_capture_runs_v8" in sql:
                return self._con.execute("INSERT INTO pit_capture_runs_v8 SELECT * FROM pit_capture_runs_v8 WHERE 1=0")
            return self._con.execute(sql, *args, **kwargs)

    def fake_connect(*args, **kwargs):
        con = real_connect(*args, **kwargs)
        return ConnectionProxy(con)

    monkeypatch.setattr(sqlite3, "connect", fake_connect)

    with pytest.raises(store.StoreError, match="Row count mismatch during Schema v8 rebuild"):
        store.init(db_path)

    with real_connect(db_path) as con:
        # Version must stay 7
        assert con.execute("PRAGMA user_version").fetchone()[0] == 7
        assert con.execute("SELECT COUNT(*) FROM pit_capture_runs").fetchone()[0] == 1


def test_v0_db_migrates_to_v8(tmp_path) -> None:
    db_path = str(tmp_path / "v0.db")
    _build_v0_db(db_path)
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 8
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "signal_history" in tables
        assert "scan_runs" in tables
        assert "candidates" in tables
        assert "journal_trades" in tables
        assert "pit_capture_runs" in tables
        assert "pit_earnings_snapshots" in tables
        assert "pit_reference_capture_runs" in tables
        assert "pit_reference_snapshots" in tables


def test_pit_capture_runs_v8_check_constraints(tmp_path) -> None:
    db_path = str(tmp_path / "check_runs_v8.db")
    store.init(db_path)

    with store._conn(db_path=tmp_path / "check_runs_v8.db") as con:
        # 1. contract_version = 1 with manifest_hash -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_capture_runs (
                    capture_run_id, idempotency_key, request_fingerprint, capture_kind,
                    capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                    universe_hash, requested_n, status, created_at, updated_at,
                    contract_version, manifest_hash
                ) VALUES (
                    'run-bad-1', 'idem-bad-1', 'fp-bad-1', 'earnings',
                    'morning', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                    'yahoo', 'uhash', 1, 'started', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                    1, 'unexpected_manifest_hash'
                )
                """
            )

        # 2. contract_version = 2 without manifest_hash -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_capture_runs (
                    capture_run_id, idempotency_key, request_fingerprint, capture_kind,
                    capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                    universe_hash, requested_n, status, created_at, updated_at,
                    contract_version, manifest_hash
                ) VALUES (
                    'run-bad-2', 'idem-bad-2', 'fp-bad-2', 'earnings',
                    'morning', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                    'yahoo', 'uhash', 1, 'started', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                    2, NULL
                )
                """
            )

        # 3. negative not_applicable_n -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_capture_runs (
                    capture_run_id, idempotency_key, request_fingerprint, capture_kind,
                    capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                    universe_hash, requested_n, not_applicable_n, status, created_at, updated_at,
                    contract_version, manifest_hash
                ) VALUES (
                    'run-bad-3', 'idem-bad-3', 'fp-bad-3', 'earnings',
                    'morning', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                    'yahoo', 'uhash', 1, -1, 'started', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                    2, 'mhash'
                )
                """
            )

        # 4. Valid v2 run succeeds
        con.execute(
            """
            INSERT INTO pit_capture_runs (
                capture_run_id, idempotency_key, request_fingerprint, capture_kind,
                capture_slot, capture_date, scheduled_for, requested_at, completed_at,
                requested_provider, universe_hash, requested_n, known_n, unavailable_n,
                not_applicable_n, error_n, status, created_at, updated_at,
                contract_version, manifest_hash
            ) VALUES (
                'run-valid-v2', 'idem-v2', 'fp-v2', 'earnings',
                'morning', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                '2026-08-30T13:05:00Z', 'yahoo', 'uhash', 3, 1, 1, 1, 0,
                'succeeded', '2026-08-30T13:00:00Z', '2026-08-30T13:05:00Z',
                2, 'mhash'
            )
            """
        )


def test_pit_earnings_snapshots_v8_check_constraints(tmp_path) -> None:
    db_path = str(tmp_path / "check_snaps_v8.db")
    store.init(db_path)

    with store._conn(db_path=tmp_path / "check_snaps_v8.db") as con:
        # Seed parent runs: v1 and v2
        con.execute(
            """
            INSERT INTO pit_capture_runs (
                capture_run_id, idempotency_key, request_fingerprint, capture_kind,
                capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                universe_hash, requested_n, status, created_at, updated_at,
                contract_version, manifest_hash
            ) VALUES (
                'run-v1', 'idem-v1', 'fp-v1', 'earnings',
                'morning', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                'yahoo', 'uhash', 1, 'started', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                1, NULL
            )
            """
        )
        con.execute(
            """
            INSERT INTO pit_capture_runs (
                capture_run_id, idempotency_key, request_fingerprint, capture_kind,
                capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                universe_hash, requested_n, status, created_at, updated_at,
                contract_version, manifest_hash
            ) VALUES (
                'run-v2', 'idem-v2', 'fp-v2', 'earnings',
                'morning', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                'yahoo', 'uhash', 1, 'started', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                2, 'mhash'
            )
            """
        )

        # 1. Valid not_applicable snapshot on v2 run
        con.execute(
            """
            INSERT INTO pit_earnings_snapshots (
                snapshot_id, capture_run_id, symbol, observation_status, next_earnings_date,
                provider, request_started_at, response_received_at, fact_hash, fact_json,
                created_at, contract_version, observation_origin,
                applicability_source, provider_call_attempted
            ) VALUES (
                'snap-na-1', 'run-v2', 'SPY', 'not_applicable', NULL,
                NULL, NULL, NULL, 'hash-na', '{}',
                '2026-08-30T13:00:00Z', 2, 'manifest', 'manifest', 0
            )
            """
        )

        # 2. not_applicable with observation_origin = 'provider' -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_earnings_snapshots (
                    snapshot_id, capture_run_id, symbol, observation_status, next_earnings_date,
                    provider, request_started_at, response_received_at, fact_hash, fact_json,
                    created_at, contract_version, observation_origin,
                    applicability_source, provider_call_attempted
                ) VALUES (
                    'snap-bad-na-1', 'run-v2', 'SPY', 'not_applicable', NULL,
                    'yahoo', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z', 'hash', '{}',
                    '2026-08-30T13:00:00Z', 2, 'provider', 'manifest', 0
                )
                """
            )

        # 3. not_applicable with applicability_source NULL -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_earnings_snapshots (
                    snapshot_id, capture_run_id, symbol, observation_status, next_earnings_date,
                    provider, request_started_at, response_received_at, fact_hash, fact_json,
                    created_at, contract_version, observation_origin,
                    applicability_source, provider_call_attempted
                ) VALUES (
                    'snap-bad-na-2', 'run-v2', 'SPY', 'not_applicable', NULL,
                    NULL, NULL, NULL, 'hash', '{}',
                    '2026-08-30T13:00:00Z', 2, 'manifest', NULL, 0
                )
                """
            )

        # 4. not_applicable with provider_call_attempted = 1 -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_earnings_snapshots (
                    snapshot_id, capture_run_id, symbol, observation_status, next_earnings_date,
                    provider, request_started_at, response_received_at, fact_hash, fact_json,
                    created_at, contract_version, observation_origin,
                    applicability_source, provider_call_attempted
                ) VALUES (
                    'snap-bad-na-3', 'run-v2', 'SPY', 'not_applicable', NULL,
                    NULL, NULL, NULL, 'hash', '{}',
                    '2026-08-30T13:00:00Z', 2, 'manifest', 'manifest', 1
                )
                """
            )

        # 5. not_applicable with non-null next_earnings_date -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_earnings_snapshots (
                    snapshot_id, capture_run_id, symbol, observation_status, next_earnings_date,
                    provider, request_started_at, response_received_at, fact_hash, fact_json,
                    created_at, contract_version, observation_origin,
                    applicability_source, provider_call_attempted
                ) VALUES (
                    'snap-bad-na-4', 'run-v2', 'SPY', 'not_applicable', '2026-10-01',
                    NULL, NULL, NULL, 'hash', '{}',
                    '2026-08-30T13:00:00Z', 2, 'manifest', 'manifest', 0
                )
                """
            )

        # 6. known status with observation_origin = 'manifest' -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_earnings_snapshots (
                    snapshot_id, capture_run_id, symbol, observation_status, next_earnings_date,
                    provider, request_started_at, response_received_at, fact_hash, fact_json,
                    created_at, contract_version, observation_origin,
                    applicability_source, provider_call_attempted
                ) VALUES (
                    'snap-bad-kn-1', 'run-v2', 'AAPL', 'known', '2026-10-25',
                    'yahoo', '2026-08-30T13:00:00Z', '2026-08-30T13:00:01Z', 'hash', '{}',
                    '2026-08-30T13:00:01Z', 2, 'manifest', NULL, 1
                )
                """
            )

        # 7. known status with applicability_source NOT NULL -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_earnings_snapshots (
                    snapshot_id, capture_run_id, symbol, observation_status, next_earnings_date,
                    provider, request_started_at, response_received_at, fact_hash, fact_json,
                    created_at, contract_version, observation_origin,
                    applicability_source, provider_call_attempted
                ) VALUES (
                    'snap-bad-kn-2', 'run-v2', 'AAPL', 'known', '2026-10-25',
                    'yahoo', '2026-08-30T13:00:00Z', '2026-08-30T13:00:01Z', 'hash', '{}',
                    '2026-08-30T13:00:01Z', 2, 'provider', 'manifest', 1
                )
                """
            )

        # 8. known status with provider_call_attempted = 0 -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_earnings_snapshots (
                    snapshot_id, capture_run_id, symbol, observation_status, next_earnings_date,
                    provider, request_started_at, response_received_at, fact_hash, fact_json,
                    created_at, contract_version, observation_origin,
                    applicability_source, provider_call_attempted
                ) VALUES (
                    'snap-bad-kn-3', 'run-v2', 'AAPL', 'known', '2026-10-25',
                    'yahoo', '2026-08-30T13:00:00Z', '2026-08-30T13:00:01Z', 'hash', '{}',
                    '2026-08-30T13:00:01Z', 2, 'provider', NULL, 0
                )
                """
            )


def test_pit_reference_v8_check_constraints(tmp_path) -> None:
    db_path = str(tmp_path / "check_ref_v8.db")
    store.init(db_path)

    with store._conn(db_path=tmp_path / "check_ref_v8.db") as con:
        # Reference run: contract_version = 1 with manifest_hash -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_reference_capture_runs (
                    capture_run_id, idempotency_key, request_fingerprint,
                    capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                    universe_hash, requested_n, status, created_at, updated_at,
                    contract_version, manifest_hash
                ) VALUES (
                    'ref-bad-1', 'idem-ref-bad-1', 'fp-ref-bad-1',
                    'morning', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                    'massive', 'uhash', 1, 'started', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                    1, 'unexpected_manifest_hash'
                )
                """
            )

        # Reference run: contract_version = 2 without manifest_hash -> fails
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO pit_reference_capture_runs (
                    capture_run_id, idempotency_key, request_fingerprint,
                    capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                    universe_hash, requested_n, status, created_at, updated_at,
                    contract_version, manifest_hash
                ) VALUES (
                    'ref-bad-2', 'idem-ref-bad-2', 'fp-ref-bad-2',
                    'morning', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                    'massive', 'uhash', 1, 'started', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                    2, NULL
                )
                """
            )

        # Valid v2 reference run succeeds
        con.execute(
            """
            INSERT INTO pit_reference_capture_runs (
                capture_run_id, idempotency_key, request_fingerprint,
                capture_slot, capture_date, scheduled_for, requested_at, requested_provider,
                universe_hash, requested_n, status, created_at, updated_at,
                contract_version, manifest_hash
            ) VALUES (
                'ref-v2-ok', 'idem-ref-v2-ok', 'fp-ref-v2-ok',
                'morning', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                'massive', 'uhash', 1, 'started', '2026-08-30T13:00:00Z', '2026-08-30T13:00:00Z',
                2, 'mhash'
            )
            """
        )

        # Reference snapshot: valid v2 snapshot succeeds
        con.execute(
            """
            INSERT INTO pit_reference_snapshots (
                snapshot_id, capture_run_id, symbol, observation_status,
                provider, provider_query_date, request_started_at, response_received_at,
                fact_hash, fact_json, created_at, contract_version
            ) VALUES (
                'ref-snap-v2-ok', 'ref-v2-ok', 'AAPL', 'known',
                'massive', '2026-08-30', '2026-08-30T13:00:00Z', '2026-08-30T13:00:01Z',
                'hash', '{}', '2026-08-30T13:00:01Z', 2
            )
            """
        )
