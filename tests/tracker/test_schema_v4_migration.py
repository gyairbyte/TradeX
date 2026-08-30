"""Deterministic migration tests for signals.db schema v4 and candidate domain tables."""
from __future__ import annotations

import sqlite3

import pytest

from tradex.tracker import store


def _build_v3_db(db_path: str) -> None:
    """Build a representative schema v3 database with legacy and DATA-001 data."""
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        # Run base v1 script
        store._create_schema_v1(con)
        # Migrate v1 to v2
        store._migrate_v1_to_v2(con)
        # Migrate v2 to v3
        store._migrate_v2_to_v3(con)

        # Seed data
        con.execute(
            """
            INSERT INTO scan_sessions (
                session_id, scan_time, trading_date, timeframe, requested_provider,
                actual_provider, status, observations_complete, requested_n, observations_n, signals_n
            ) VALUES (
                'session-v3-001', '2026-08-20T14:00:00Z', '2026-08-20', 'intraday', 'schwab',
                'schwab', 'completed', 1, 1, 1, 1
            )
            """
        )
        con.execute(
            """
            INSERT INTO scan_observations (
                session_id, ticker, status, score, last_close, volume_ratio, rsi, provider
            ) VALUES (
                'session-v3-001', 'AAPL', 'signal', 75, 220.5, 1.8, 62.0, 'schwab'
            )
            """
        )
        con.execute(
            """
            INSERT INTO signal_history (
                ticker, timeframe, scan_time, score, last_close, provider, scan_session_id, trading_date
            ) VALUES (
                'AAPL', 'intraday', '2026-08-20T14:00:00Z', 75, 220.5, 'schwab', 'session-v3-001', '2026-08-20'
            )
            """
        )
        con.execute(
            """
            INSERT INTO scan_runs (
                run_time, timeframe, tickers_n, hits_n, provider, session_id, status, counts_complete, source
            ) VALUES (
                '2026-08-20T14:00:00Z', 'intraday', 1, 1, 'schwab', 'session-v3-001', 'completed', 1, 'native'
            )
            """
        )
        con.execute("PRAGMA user_version = 3")
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


def test_fresh_db_creates_schema_v4(tmp_path) -> None:
    db_path = str(tmp_path / "fresh_v4.db")
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        assert version == 7

        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "candidates" in tables
        assert "candidate_evaluations" in tables
        assert "candidate_evidence" in tables
        assert "candidate_reasons" in tables
        assert "candidate_missing_data" in tables
        assert "signal_history" in tables
        assert "scan_runs" in tables
        assert "scan_sessions" in tables
        assert "scan_observations" in tables

    # Idempotent repeat init
    store.init(db_path)
    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 7


def test_v3_to_v4_migration_preserves_legacy_data(tmp_path) -> None:
    db_path = str(tmp_path / "v3.db")
    _build_v3_db(db_path)

    # Migrate v3 -> v6
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        assert version == 7

        # Candidate tables exist
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "candidates" in tables
        assert "candidate_evaluations" in tables
        assert "candidate_evidence" in tables
        assert "candidate_reasons" in tables
        assert "candidate_missing_data" in tables

        # Legacy data is completely preserved
        sh_row = con.execute("SELECT * FROM signal_history WHERE ticker = 'AAPL'").fetchone()
        assert sh_row is not None
        assert sh_row[1] == "AAPL"

        obs_row = con.execute("SELECT * FROM scan_observations WHERE ticker = 'AAPL'").fetchone()
        assert obs_row is not None
        assert obs_row[2] == "AAPL"

        session_row = con.execute("SELECT * FROM scan_sessions WHERE session_id = 'session-v3-001'").fetchone()
        assert session_row is not None
        assert session_row[0] == "session-v3-001"

        run_row = con.execute("SELECT * FROM scan_runs WHERE session_id = 'session-v3-001'").fetchone()
        assert run_row is not None
        assert run_row[6] == "session-v3-001"


def test_v0_db_migrates_to_v4(tmp_path) -> None:
    db_path = str(tmp_path / "v0.db")
    _build_v0_db(db_path)

    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 7
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "candidates" in tables
        sh_row = con.execute("SELECT ticker, score, provider FROM signal_history WHERE ticker = 'MSFT'").fetchone()
        assert sh_row == ("MSFT", 80, "unknown")


def test_v1_db_migrates_to_v4(tmp_path) -> None:
    db_path = str(tmp_path / "v1.db")
    con = sqlite3.connect(db_path)
    try:
        store._create_schema_v1(con)
        con.execute(
            """
            INSERT INTO scan_sessions (
                session_id, scan_time, timeframe, requested_provider, status
            ) VALUES ('sess-v1', '2026-08-19T14:00:00Z', 'intraday', 'yahoo', 'completed')
            """
        )
        con.execute(
            """
            INSERT INTO scan_observations (session_id, ticker, status, score)
            VALUES ('sess-v1', 'NVDA', 'signal', 85)
            """
        )
        con.execute("PRAGMA user_version = 1")
        con.commit()
    finally:
        con.close()

    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 7
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "candidates" in tables
        obs = con.execute("SELECT ticker, score FROM scan_observations WHERE session_id = 'sess-v1'").fetchone()
        assert obs == ("NVDA", 85)


def test_v2_db_migrates_to_v4(tmp_path) -> None:
    db_path = str(tmp_path / "v2.db")
    con = sqlite3.connect(db_path)
    try:
        store._create_schema_v1(con)
        store._migrate_v1_to_v2(con)
        con.execute(
            """
            INSERT INTO scan_sessions (
                session_id, scan_time, timeframe, requested_provider, status
            ) VALUES ('sess-v2', '2026-08-20T14:00:00Z', 'intraday', 'schwab', 'completed')
            """
        )
        con.execute(
            """
            INSERT INTO scan_observations (session_id, ticker, status, score)
            VALUES ('sess-v2', 'AMD', 'signal', 88)
            """
        )
        con.execute("PRAGMA user_version = 2")
        con.commit()
    finally:
        con.close()

    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 7
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "candidates" in tables
        obs = con.execute("SELECT ticker, score FROM scan_observations WHERE session_id = 'sess-v2'").fetchone()
        assert obs == ("AMD", 88)


def test_atomic_failure_in_v3_to_v4_migration(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "v3_fail.db")
    _build_v3_db(db_path)

    def failing_migrate(con):
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id TEXT PRIMARY KEY
            )
            """
        )
        raise sqlite3.OperationalError("injected v3->v4 migration failure")

    monkeypatch.setattr(store, "_migrate_v3_to_v4", failing_migrate)

    with pytest.raises(sqlite3.OperationalError, match="injected v3->v4 migration failure"):
        store.init(db_path)

    with sqlite3.connect(db_path) as con:
        # user_version remains at 3
        version = con.execute("PRAGMA user_version").fetchone()[0]
        assert version == 3

        # Transaction rollback removed any partial candidates table
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "candidates" not in tables
        assert "candidate_evaluations" not in tables


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
        # Version must not have been downgraded
        assert con.execute("PRAGMA user_version").fetchone()[0] == 99
