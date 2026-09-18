"""Deterministic migration tests for signals.db schema v5 and Journal persistence tables."""
from __future__ import annotations

import sqlite3

import pytest

from tradex.tracker import store


def _build_v4_db(db_path: str) -> None:
    """Build a representative schema v4 database with legacy data and candidate snapshots."""
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        store._create_schema_v1(con)
        store._migrate_v1_to_v2(con)
        store._migrate_v2_to_v3(con)
        store._migrate_v3_to_v4(con)

        # Seed legacy signal and observation data
        con.execute(
            """
            INSERT INTO scan_sessions (
                session_id, scan_time, trading_date, timeframe, requested_provider,
                actual_provider, status, observations_complete, requested_n, observations_n, signals_n
            ) VALUES (
                'session-v4-001', '2026-08-20T14:00:00Z', '2026-08-20', 'intraday', 'schwab',
                'schwab', 'completed', 1, 1, 1, 1
            )
            """
        )
        con.execute(
            """
            INSERT INTO scan_observations (
                session_id, ticker, status, score, last_close, volume_ratio, rsi, provider
            ) VALUES (
                'session-v4-001', 'AAPL', 'signal', 75, 220.5, 1.8, 62.0, 'schwab'
            )
            """
        )
        con.execute(
            """
            INSERT INTO signal_history (
                ticker, timeframe, scan_time, score, last_close, provider, scan_session_id, trading_date
            ) VALUES (
                'AAPL', 'intraday', '2026-08-20T14:00:00Z', 75, 220.5, 'schwab', 'session-v4-001', '2026-08-20'
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
                'cand-v4-001', 1, 'AAPL', '2026-08-20T14:00:00Z', '2026-08-20', 'unknown', '2026-08-20T14:00:00Z'
            )
            """
        )

        con.execute("PRAGMA user_version = 4")
        con.commit()
    finally:
        con.close()


def _build_v3_db(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        store._create_schema_v1(con)
        store._migrate_v1_to_v2(con)
        store._migrate_v2_to_v3(con)
        con.execute("PRAGMA user_version = 3")
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


def test_fresh_db_creates_schema_v5(tmp_path) -> None:
    db_path = str(tmp_path / "fresh_v5.db")
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

        # Verify journal indexes
        indexes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert "idx_journal_trades_state" in indexes
        assert "idx_journal_trades_strategy" in indexes
        assert "idx_journal_trades_candidate" in indexes

        # Verify NO strategy_drawdown column in journal_outcomes
        outcome_cols = {c[1] for c in con.execute("PRAGMA table_info(journal_outcomes)")}
        assert "strategy_drawdown" not in outcome_cols


def test_v4_to_v5_migration_preserves_candidate_and_legacy_data(tmp_path) -> None:
    db_path = str(tmp_path / "v4.db")
    _build_v4_db(db_path)

    # Migrate v4 -> v6
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 8

        # Check legacy rows preserved
        sh = con.execute("SELECT ticker, score, provider FROM signal_history WHERE ticker = 'AAPL'").fetchone()
        assert sh == ("AAPL", 75, "schwab")

        # Check candidate rows preserved
        cand = con.execute("SELECT candidate_id, symbol FROM candidates WHERE candidate_id = 'cand-v4-001'").fetchone()
        assert cand == ("cand-v4-001", "AAPL")

        # Check zero journal rows created
        assert con.execute("SELECT COUNT(*) FROM journal_trades").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM journal_events").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM journal_outcomes").fetchone()[0] == 0


def test_v0_db_migrates_to_v5(tmp_path) -> None:
    db_path = str(tmp_path / "v0.db")
    _build_v0_db(db_path)
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 8
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "journal_trades" in tables
        assert "journal_events" in tables
        assert "journal_outcomes" in tables


def test_v1_db_migrates_to_v5(tmp_path) -> None:
    db_path = str(tmp_path / "v1.db")
    con = sqlite3.connect(db_path)
    try:
        store._create_schema_v1(con)
        con.execute("PRAGMA user_version = 1")
        con.commit()
    finally:
        con.close()

    store.init(db_path)
    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 8


def test_v2_db_migrates_to_v5(tmp_path) -> None:
    db_path = str(tmp_path / "v2.db")
    con = sqlite3.connect(db_path)
    try:
        store._create_schema_v1(con)
        store._migrate_v1_to_v2(con)
        con.execute("PRAGMA user_version = 2")
        con.commit()
    finally:
        con.close()

    store.init(db_path)
    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 8


def test_v3_db_migrates_to_v5(tmp_path) -> None:
    db_path = str(tmp_path / "v3.db")
    _build_v3_db(db_path)
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 8


def test_v5_repeat_init_is_idempotent(tmp_path) -> None:
    db_path = str(tmp_path / "v5_idempotent.db")
    store.init(db_path)
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 8


def test_future_schema_version_rejected(tmp_path) -> None:
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


def test_atomic_rollback_on_v4_to_v5_failure(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "v4_fail.db")
    _build_v4_db(db_path)

    def failing_migrate(con):
        con.execute("CREATE TABLE IF NOT EXISTS journal_trades (journal_id TEXT PRIMARY KEY)")
        raise sqlite3.OperationalError("injected v4->v5 failure")

    monkeypatch.setattr(store, "_migrate_v4_to_v5", failing_migrate)

    with pytest.raises(sqlite3.OperationalError, match="injected v4->v5 failure"):
        store.init(db_path)

    with sqlite3.connect(db_path) as con:
        # Version must stay 4
        assert con.execute("PRAGMA user_version").fetchone()[0] == 4
        # Partial table was rolled back
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "journal_trades" not in tables


def test_foreign_key_prevents_dangling_candidate_reference(tmp_path) -> None:
    db_path = str(tmp_path / "fk_test.db")
    store.init(db_path)

    with store._conn(db_path=tmp_path / "fk_test.db") as con, pytest.raises(sqlite3.IntegrityError):
        con.execute(
            """
            INSERT INTO journal_trades (
                journal_id, idempotency_key, candidate_id, strategy_id, strategy_version,
                side, state, decision_timestamp, plan_created_at, planned_entry,
                created_at, updated_at
            ) VALUES (
                'j-1', 'idem-1', 'nonexistent-candidate', 'strat-1', 'v1',
                'long', 'planned', '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z', 100.0,
                '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z'
            )
            """
        )


def test_journal_trades_table_check_constraints(tmp_path) -> None:
    db_path = str(tmp_path / "check_test.db")
    store.init(db_path)

    with store._conn(db_path=tmp_path / "check_test.db") as con:
        # Seed candidate
        con.execute(
            """
            INSERT INTO candidates (candidate_id, symbol, decision_timestamp, created_at)
            VALUES ('cand-1', 'AAPL', '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z')
            """
        )

        # Invalid state
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO journal_trades (
                    journal_id, idempotency_key, candidate_id, strategy_id, strategy_version,
                    side, state, decision_timestamp, plan_created_at, planned_entry,
                    created_at, updated_at
                ) VALUES (
                    'j-1', 'idem-1', 'cand-1', 'strat-1', 'v1',
                    'long', 'armed', '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z', 100.0,
                    '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z'
                )
                """
            )

        # Invalid side
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO journal_trades (
                    journal_id, idempotency_key, candidate_id, strategy_id, strategy_version,
                    side, state, decision_timestamp, plan_created_at, planned_entry,
                    created_at, updated_at
                ) VALUES (
                    'j-1', 'idem-1', 'cand-1', 'strat-1', 'v1',
                    'short', 'planned', '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z', 100.0,
                    '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z'
                )
                """
            )

        # Planned state cannot have fill_price
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO journal_trades (
                    journal_id, idempotency_key, candidate_id, strategy_id, strategy_version,
                    side, state, decision_timestamp, plan_created_at, planned_entry,
                    fill_price, created_at, updated_at
                ) VALUES (
                    'j-1', 'idem-1', 'cand-1', 'strat-1', 'v1',
                    'long', 'planned', '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z', 100.0,
                    101.0, '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z'
                )
                """
            )

        # Open state requires fill_price, fill_timestamp, quantity
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO journal_trades (
                    journal_id, idempotency_key, candidate_id, strategy_id, strategy_version,
                    side, state, decision_timestamp, plan_created_at, planned_entry,
                    created_at, updated_at
                ) VALUES (
                    'j-1', 'idem-1', 'cand-1', 'strat-1', 'v1',
                    'long', 'open', '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z', 100.0,
                    '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z'
                )
                """
            )
