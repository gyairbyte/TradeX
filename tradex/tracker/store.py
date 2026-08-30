"""
SQLite-backed signal history store.

Every time the scanner runs, each observation gets a row written here.
This is the foundation for:
  - detecting how long a stock has been building (coil duration)
  - confluence analysis across timeframes
  - signal journal / outcome tracking
  - "seen N times this week" awareness
"""
from __future__ import annotations

import hashlib
import sqlite3
import uuid
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.market.hours import is_trading_day, normalize_market_datetime

DB_PATH: Path = Path("~/.tradex/signals.db")
_DEFAULT_DB_PATH = DB_PATH  # sentinel for legacy DB_PATH monkeypatch detection

# DB schema version managed by PRAGMA user_version.
_SCHEMA_VERSION = 7


class StoreError(Exception):
    """Raised when the persistence layer cannot complete an operation."""


def _db_path(db_path: Path | None = None) -> str:
    return str(Path(str(db_path or DB_PATH)).expanduser())


@contextmanager
def _conn(db_path: Path | None = None):
    """Yield a managed SQLite connection. Commits on normal exit."""
    path = Path(_db_path(db_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


@contextmanager
def _transaction(db_path: Path | None = None):
    """Yield a connection with explicit BEGIN / COMMIT / ROLLBACK."""
    path = Path(_db_path(db_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("BEGIN")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _ensure_db_dir(db_path: Path | None = None):
    Path(str(db_path or DB_PATH)).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _resolve_db_path(settings: TradeXSettings | None = None) -> Path:
    """Return the signal database path from explicit settings or runtime env.

    Legacy tests may monkeypatch ``DB_PATH``; if the module constant has been
    replaced with a different path, that path takes precedence. Otherwise the
    call-time runtime settings are loaded so ``TRADEX_DB_PATH`` is honored.
    """
    if settings is not None:
        return settings.paths.signals_db
    # Preserve legacy test monkeypatch compatibility.
    if DB_PATH is not _DEFAULT_DB_PATH and str(DB_PATH) != str(_DEFAULT_DB_PATH):
        return DB_PATH
    return load_runtime_settings().paths.signals_db


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _column_names(con: sqlite3.Connection, table: str) -> set[str]:
    return {c[1] for c in con.execute(f"PRAGMA table_info({table})")}


def _set_schema_version(con: sqlite3.Connection) -> None:
    con.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


def _execute_schema_statements(con: sqlite3.Connection, script: str) -> None:
    """Run a semicolon-separated schema script inside an explicit transaction."""
    for raw in script.split(";"):
        stmt = "\n".join(
            line for line in raw.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ).strip()
        if stmt:
            con.execute(stmt)


_SCHEMA_SCRIPT = """
    CREATE TABLE IF NOT EXISTS signal_history (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker            TEXT    NOT NULL,
        timeframe         TEXT    NOT NULL,
        scan_time         TEXT    NOT NULL,   -- ISO8601 UTC
        score             INTEGER NOT NULL,
        last_close        REAL,
        volume_ratio      REAL,
        rsi               REAL,
        reasons           TEXT,              -- pipe-separated
        -- provenance: OHLCV provider that produced this signal
        provider          TEXT    NOT NULL DEFAULT 'unknown',
        -- outcome tracking (filled in later via mark_outcome)
        outcome_close     REAL,
        outcome_pct       REAL,
        outcome_at        TEXT,
        outcome_provider  TEXT,
        -- DATA-001 session linkage
        scan_session_id   TEXT,
        trading_date      TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_sh_ticker          ON signal_history(ticker);
    CREATE INDEX IF NOT EXISTS idx_sh_timeframe       ON signal_history(timeframe);
    CREATE INDEX IF NOT EXISTS idx_sh_scan_time        ON signal_history(scan_time);
    CREATE INDEX IF NOT EXISTS idx_sh_scan_session_id  ON signal_history(scan_session_id);
    CREATE INDEX IF NOT EXISTS idx_sh_trading_date     ON signal_history(trading_date);

    CREATE TABLE IF NOT EXISTS scan_runs (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        run_time            TEXT NOT NULL,
        timeframe           TEXT NOT NULL,
        tickers_n           INTEGER,
        hits_n              INTEGER,
        provider            TEXT    NOT NULL DEFAULT 'unknown',
        session_id          TEXT,
        status              TEXT,
        requested_provider  TEXT,
        actual_provider     TEXT,
        counts_complete     INTEGER NOT NULL DEFAULT 0,
        source              TEXT    NOT NULL DEFAULT 'legacy'
    );

    CREATE INDEX IF NOT EXISTS idx_sr_run_time             ON scan_runs(run_time);
    CREATE INDEX IF NOT EXISTS idx_sr_timeframe_run_time   ON scan_runs(timeframe, run_time);
    CREATE INDEX IF NOT EXISTS idx_sr_session_id           ON scan_runs(session_id);
    CREATE INDEX IF NOT EXISTS idx_sr_status               ON scan_runs(status);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_sr_session_id_unique
        ON scan_runs(session_id) WHERE session_id IS NOT NULL;

    CREATE TABLE IF NOT EXISTS scan_sessions (
        session_id            TEXT PRIMARY KEY,
        scan_time             TEXT NOT NULL,            -- ISO8601 UTC
        trading_date          TEXT,                     -- New York calendar date or NULL
        timeframe             TEXT    NOT NULL,
        requested_provider    TEXT    NOT NULL,
        actual_provider       TEXT,
        fallback_used         INTEGER NOT NULL DEFAULT 0,
        providers_attempted   TEXT,                     -- comma-separated
        status                TEXT    NOT NULL,
        source                TEXT    NOT NULL DEFAULT 'live',
        observations_complete INTEGER NOT NULL DEFAULT 0,
        requested_n           INTEGER NOT NULL DEFAULT 0,
        observations_n        INTEGER NOT NULL DEFAULT 0,
        signals_n             INTEGER NOT NULL DEFAULT 0,
        below_threshold_n     INTEGER NOT NULL DEFAULT 0,
        earnings_excluded_n   INTEGER NOT NULL DEFAULT 0,
        earnings_failure_n    INTEGER NOT NULL DEFAULT 0,
        fetch_failure_n       INTEGER NOT NULL DEFAULT 0,
        insufficient_data_n   INTEGER NOT NULL DEFAULT 0,
        scoring_failure_n     INTEGER NOT NULL DEFAULT 0,
        min_score             INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_ss_timeframe       ON scan_sessions(timeframe);
    CREATE INDEX IF NOT EXISTS idx_ss_scan_time       ON scan_sessions(scan_time);
    CREATE INDEX IF NOT EXISTS idx_ss_trading_date    ON scan_sessions(trading_date);

    CREATE TABLE IF NOT EXISTS scan_observations (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id        TEXT    NOT NULL,
        ticker            TEXT    NOT NULL,
        status            TEXT    NOT NULL,
        score             INTEGER,
        last_close        REAL,
        volume_ratio      REAL,
        rsi               REAL,
        days_until_earnings INTEGER,
        reasons           TEXT,
        provider          TEXT,
        error_category    TEXT,
        error_message     TEXT,
        FOREIGN KEY (session_id) REFERENCES scan_sessions(session_id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_so_session_id    ON scan_observations(session_id);
    CREATE INDEX IF NOT EXISTS idx_so_ticker        ON scan_observations(ticker);
    CREATE INDEX IF NOT EXISTS idx_so_status        ON scan_observations(status);
    CREATE INDEX IF NOT EXISTS idx_so_ticker_time   ON scan_observations(ticker, session_id);

    CREATE UNIQUE INDEX IF NOT EXISTS idx_so_unique_session_ticker
        ON scan_observations(session_id, ticker);
"""


def _create_schema_v1(con: sqlite3.Connection) -> None:
    """Create the complete DATA-001 schema, indexes, and observation uniqueness."""
    _execute_schema_statements(con, _SCHEMA_SCRIPT)


def _migrate_v0(con: sqlite3.Connection) -> None:
    """Migrate a pre-DATA-001 database to the canonical schema."""
    # Idempotent additions to older signal_history and scan_runs tables.
    sh_cols = _column_names(con, "signal_history")
    if "provider" not in sh_cols:
        con.execute("ALTER TABLE signal_history ADD COLUMN provider TEXT NOT NULL DEFAULT 'unknown'")
    if "outcome_provider" not in sh_cols:
        con.execute("ALTER TABLE signal_history ADD COLUMN outcome_provider TEXT")
        if "outcome_close" in sh_cols:
            con.execute("""
                UPDATE signal_history
                SET outcome_provider = 'unknown'
                WHERE outcome_provider IS NULL AND outcome_close IS NOT NULL
            """)
    if "scan_session_id" not in sh_cols:
        con.execute("ALTER TABLE signal_history ADD COLUMN scan_session_id TEXT")
    if "trading_date" not in sh_cols:
        con.execute("ALTER TABLE signal_history ADD COLUMN trading_date TEXT")

    sr_cols = _column_names(con, "scan_runs")
    if "provider" not in sr_cols:
        con.execute("ALTER TABLE scan_runs ADD COLUMN provider TEXT NOT NULL DEFAULT 'unknown'")
    if "session_id" not in sr_cols:
        con.execute("ALTER TABLE scan_runs ADD COLUMN session_id TEXT")
    if "status" not in sr_cols:
        con.execute("ALTER TABLE scan_runs ADD COLUMN status TEXT")
    if "requested_provider" not in sr_cols:
        con.execute("ALTER TABLE scan_runs ADD COLUMN requested_provider TEXT")
    if "actual_provider" not in sr_cols:
        con.execute("ALTER TABLE scan_runs ADD COLUMN actual_provider TEXT")
    if "counts_complete" not in sr_cols:
        con.execute("ALTER TABLE scan_runs ADD COLUMN counts_complete INTEGER NOT NULL DEFAULT 0")
    if "source" not in sr_cols:
        con.execute("ALTER TABLE scan_runs ADD COLUMN source TEXT NOT NULL DEFAULT 'legacy'")

    # Create the new canonical tables and indexes.
    _create_schema_v1(con)

    # Build deterministic synthetic sessions for legacy signal rows.
    # Older signal_history tables may be missing optional columns; only select what exists.
    available_sh_cols = _column_names(con, "signal_history")
    optional_cols = [c for c in ("volume_ratio", "rsi", "reasons") if c in available_sh_cols]
    select_cols = ["id", "ticker", "timeframe", "scan_time", "score", "last_close", "provider"] + optional_cols
    legacy_rows = con.execute(
        f"""
        SELECT {', '.join(select_cols)}
        FROM signal_history
        WHERE scan_session_id IS NULL
        ORDER BY scan_time, timeframe, provider, id
        """
    ).fetchall()

    def _legacy_value(row, col: str):
        return row[col] if col in available_sh_cols else None

    session_map: dict[tuple[str, str, str], str] = {}
    for row in legacy_rows:
        key = (row["scan_time"], row["timeframe"], row["provider"] or "unknown")
        session_id = session_map.get(key)
        if session_id is None:
            digest = hashlib.sha256("|".join(key).encode()).hexdigest()[:32]
            session_id = f"legacy-{digest}"
            session_map[key] = session_id

            ny_dt = _parse_iso_or_none(row["scan_time"])
            trading_date = None
            if ny_dt is not None:
                trading_date = _derive_trading_date(ny_dt)

            con.execute(
                """
                INSERT OR IGNORE INTO scan_sessions
                  (session_id, scan_time, trading_date, timeframe, requested_provider,
                   actual_provider, fallback_used, providers_attempted, status, source,
                   observations_complete, requested_n, observations_n, signals_n,
                   below_threshold_n, earnings_excluded_n, earnings_failure_n,
                   fetch_failure_n, insufficient_data_n, scoring_failure_n, min_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    row["scan_time"],
                    trading_date,
                    row["timeframe"],
                    row["provider"] or "unknown",
                    row["provider"] or "unknown",
                    0,
                    row["provider"] or "unknown",
                    "completed",
                    "legacy",
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                ),
            )

        # Update the signal row with its synthetic session linkage.
        ny_dt = _parse_iso_or_none(row["scan_time"])
        trading_date = _derive_trading_date(ny_dt) if ny_dt is not None else None
        con.execute(
            """
            UPDATE signal_history
            SET scan_session_id = ?, trading_date = ?
            WHERE id = ?
            """,
            (session_id, trading_date, row["id"]),
        )

        # Create one observation for each legacy signal (all legacy rows are qualifying signals).
        reasons = _legacy_value(row, "reasons") or ""
        con.execute(
            """
            INSERT INTO scan_observations
              (session_id, ticker, status, score, last_close, volume_ratio, rsi,
               days_until_earnings, reasons, provider, error_category, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                row["ticker"],
                "signal",
                row["score"],
                row["last_close"],
                _legacy_value(row, "volume_ratio"),
                _legacy_value(row, "rsi"),
                None,
                reasons,
                row["provider"] or "unknown",
                None,
                None,
            ),
        )

    # Finalize synthetic session counts from the observations we just inserted.
    for key, session_id in session_map.items():
        con.execute(
            """
            UPDATE scan_sessions
            SET requested_n = (
                SELECT COUNT(*) FROM scan_observations WHERE session_id = ?
            ),
                observations_n = (
                    SELECT COUNT(*) FROM scan_observations WHERE session_id = ?
                ),
                signals_n = (
                    SELECT COUNT(*) FROM scan_observations WHERE session_id = ? AND status = 'signal'
                )
            WHERE session_id = ?
            """,
            (session_id, session_id, session_id, session_id),
        )


def _migrate_v1_to_v2(con: sqlite3.Connection) -> None:
    """Add the observation uniqueness constraint introduced after DATA-001."""
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_so_unique_session_ticker
            ON scan_observations(session_id, ticker)
    """)


def _migrate_v2_to_v3(con: sqlite3.Connection) -> None:
    """Upgrade the scan_runs audit surface with session linkage and count completeness."""
    sr_cols = _column_names(con, "scan_runs")
    new_columns = [
        ("session_id", "TEXT"),
        ("status", "TEXT"),
        ("requested_provider", "TEXT"),
        ("actual_provider", "TEXT"),
        ("counts_complete", "INTEGER NOT NULL DEFAULT 0"),
        ("source", "TEXT NOT NULL DEFAULT 'legacy'"),
    ]
    for col, dtype in new_columns:
        if col not in sr_cols:
            con.execute(f"ALTER TABLE scan_runs ADD COLUMN {col} {dtype}")

    _execute_schema_statements(
        con,
        """
        CREATE INDEX IF NOT EXISTS idx_sr_run_time           ON scan_runs(run_time);
        CREATE INDEX IF NOT EXISTS idx_sr_timeframe_run_time ON scan_runs(timeframe, run_time);
        CREATE INDEX IF NOT EXISTS idx_sr_session_id         ON scan_runs(session_id);
        CREATE INDEX IF NOT EXISTS idx_sr_status             ON scan_runs(status);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sr_session_id_unique
            ON scan_runs(session_id) WHERE session_id IS NOT NULL;
        """,
    )

    # Existing rows without a source are legacy audit rows whose true requested
    # universe cannot be reconstructed.
    con.execute(
        """
        UPDATE scan_runs
        SET source = 'legacy',
            counts_complete = 0,
            status = COALESCE(status, 'unknown')
        WHERE source IS NULL OR source = 'legacy'
        """
    )

    # Backfill canonical audit rows for complete native scan sessions. Reuse a
    # legacy scan_runs row only when exactly one complete session and exactly one
    # legacy row share the match key (run_time, timeframe, provider). Otherwise,
    # leave legacy rows unlinked and insert a new canonical row per session.
    sessions = con.execute(
        """
        SELECT *
        FROM scan_sessions
        WHERE observations_complete = 1
        ORDER BY scan_time, timeframe, session_id
        """
    ).fetchall()

    def _match_key(session):
        requested_provider = session["requested_provider"]
        actual_provider = session["actual_provider"]
        provider = actual_provider or requested_provider or "unknown"
        return (session["scan_time"], session["timeframe"], provider)

    # Count how many complete sessions fall under each match key.
    session_counts: dict[tuple[str, str, str], int] = {}
    for session in sessions:
        session_counts[_match_key(session)] = session_counts.get(_match_key(session), 0) + 1

    # Count legacy (unlinked) scan_runs rows for each match key.
    legacy_counts: dict[tuple[str, str, str], int] = {}
    legacy_rows = con.execute(
        """
        SELECT run_time, timeframe, provider, id
        FROM scan_runs
        WHERE session_id IS NULL AND source = 'legacy'
        ORDER BY run_time, timeframe, provider, id
        """
    ).fetchall()
    for row in legacy_rows:
        key = (row["run_time"], row["timeframe"], row["provider"])
        legacy_counts[key] = legacy_counts.get(key, 0) + 1

    reusable_keys = {
        key for key in session_counts
        if session_counts[key] == 1 and legacy_counts.get(key, 0) == 1
    }
    used_legacy_ids: set[int] = set()

    for session in sessions:
        session_id = session["session_id"]
        run_time = session["scan_time"]
        timeframe = session["timeframe"]
        requested_n = session["requested_n"]
        signals_n = session["signals_n"]
        status = session["status"]
        requested_provider = session["requested_provider"]
        actual_provider = session["actual_provider"]
        provider = actual_provider or requested_provider or "unknown"
        key = _match_key(session)

        if key in reusable_keys:
            legacy_id = next(
                (row["id"] for row in legacy_rows
                 if row["run_time"] == run_time
                 and row["timeframe"] == timeframe
                 and row["provider"] == provider
                 and row["id"] not in used_legacy_ids),
                None,
            )
            if legacy_id is not None:
                used_legacy_ids.add(legacy_id)
                con.execute(
                    """
                    UPDATE scan_runs
                    SET tickers_n = ?,
                        hits_n = ?,
                        provider = ?,
                        session_id = ?,
                        status = ?,
                        requested_provider = ?,
                        actual_provider = ?,
                        counts_complete = 1,
                        source = 'native'
                    WHERE id = ?
                    """,
                    (
                        requested_n,
                        signals_n,
                        provider,
                        session_id,
                        status,
                        requested_provider,
                        actual_provider,
                        legacy_id,
                    ),
                )
                continue

        con.execute(
            """
            INSERT INTO scan_runs
              (run_time, timeframe, tickers_n, hits_n, provider,
               session_id, status, requested_provider, actual_provider,
               counts_complete, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_time,
                timeframe,
                requested_n,
                signals_n,
                provider,
                session_id,
                status,
                requested_provider,
                actual_provider,
                1,
                "native",
            ),
        )


def _migrate_v3_to_v4(con: sqlite3.Connection) -> None:
    """Add candidate snapshot domain tables and indexes for schema v4."""
    _execute_schema_statements(con, _CANDIDATE_SCHEMA_SCRIPT)


_CANDIDATE_SCHEMA_SCRIPT = """
    CREATE TABLE IF NOT EXISTS candidates (
        candidate_id               TEXT PRIMARY KEY,
        contract_version           INTEGER NOT NULL DEFAULT 1,
        symbol                     TEXT    NOT NULL,
        decision_timestamp         TEXT    NOT NULL,   -- ISO8601 UTC
        trading_date               TEXT,               -- YYYY-MM-DD New York market date or NULL
        security_identity_version  TEXT,
        security_identity_status   TEXT    NOT NULL DEFAULT 'unknown',
        created_at                 TEXT    NOT NULL    -- ISO8601 UTC
    );

    CREATE INDEX IF NOT EXISTS idx_candidates_symbol       ON candidates(symbol);
    CREATE INDEX IF NOT EXISTS idx_candidates_decision_ts  ON candidates(decision_timestamp);
    CREATE INDEX IF NOT EXISTS idx_candidates_trading_date ON candidates(trading_date);

    CREATE TABLE IF NOT EXISTS candidate_evaluations (
        evaluation_id      TEXT PRIMARY KEY,
        candidate_id       TEXT NOT NULL,
        evaluator_id       TEXT NOT NULL,
        evaluator_version  TEXT NOT NULL,
        evidence_state     TEXT NOT NULL,
        dimensions_json    TEXT NOT NULL DEFAULT '{}',
        created_at         TEXT NOT NULL,
        FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_ceval_candidate_id ON candidate_evaluations(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_ceval_evaluator    ON candidate_evaluations(evaluator_id, evaluator_version);

    CREATE TABLE IF NOT EXISTS candidate_evidence (
        evidence_id        TEXT PRIMARY KEY,
        candidate_id       TEXT NOT NULL,
        evidence_type      TEXT NOT NULL,
        source_ref_type    TEXT,
        source_ref_id      TEXT,
        provider           TEXT,
        observed_at        TEXT,
        metadata_json      TEXT NOT NULL DEFAULT '{}',
        created_at         TEXT NOT NULL,
        FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_cevid_candidate_id ON candidate_evidence(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_cevid_data_family  ON candidate_evidence(evidence_type);

    CREATE TABLE IF NOT EXISTS candidate_reasons (
        reason_id          TEXT PRIMARY KEY,
        candidate_id       TEXT NOT NULL,
        evaluation_id      TEXT NOT NULL,
        dimension          TEXT NOT NULL,
        reason_code        TEXT NOT NULL,
        polarity           TEXT NOT NULL DEFAULT 'neutral',
        severity           TEXT NOT NULL DEFAULT 'info',
        human_text         TEXT NOT NULL,
        source_evidence_id TEXT,
        created_at         TEXT NOT NULL,
        FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        FOREIGN KEY (evaluation_id) REFERENCES candidate_evaluations(evaluation_id) ON DELETE CASCADE,
        FOREIGN KEY (source_evidence_id) REFERENCES candidate_evidence(evidence_id) ON DELETE SET NULL
    );

    CREATE INDEX IF NOT EXISTS idx_creasons_candidate_id ON candidate_reasons(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_creasons_eval_id      ON candidate_reasons(evaluation_id);
    CREATE INDEX IF NOT EXISTS idx_creasons_source_evid  ON candidate_reasons(source_evidence_id);

    CREATE TABLE IF NOT EXISTS candidate_missing_data (
        record_id          TEXT PRIMARY KEY,
        candidate_id       TEXT NOT NULL,
        evaluation_id      TEXT,
        input_name         TEXT NOT NULL,
        data_family        TEXT NOT NULL,
        status             TEXT NOT NULL,
        detail             TEXT,
        provider           TEXT,
        observed_at        TEXT,
        created_at         TEXT NOT NULL,
        FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE,
        FOREIGN KEY (evaluation_id) REFERENCES candidate_evaluations(evaluation_id) ON DELETE SET NULL
    );

    CREATE INDEX IF NOT EXISTS idx_cmissing_candidate_id ON candidate_missing_data(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_cmissing_eval_id      ON candidate_missing_data(evaluation_id);
"""


def _migrate_v4_to_v5(con: sqlite3.Connection) -> None:
    """Add executable journal domain tables and indexes for schema v5."""
    _execute_schema_statements(con, _JOURNAL_SCHEMA_SCRIPT)


_JOURNAL_SCHEMA_SCRIPT = """
    CREATE TABLE IF NOT EXISTS journal_trades (
        journal_id          TEXT PRIMARY KEY,
        contract_version    INTEGER NOT NULL DEFAULT 1,
        idempotency_key     TEXT    NOT NULL UNIQUE,
        candidate_id        TEXT    NOT NULL REFERENCES candidates(candidate_id),
        strategy_id         TEXT    NOT NULL,
        strategy_version    TEXT    NOT NULL,
        side                TEXT    NOT NULL CHECK (side IN ('long')),
        state               TEXT    NOT NULL CHECK (state IN
                              ('planned','open','closed','cancelled','expired','invalidated')),
        decision_timestamp  TEXT    NOT NULL,
        plan_created_at     TEXT    NOT NULL,
        planned_entry       REAL    NOT NULL CHECK (planned_entry > 0),
        stop_price          REAL    CHECK (stop_price IS NULL OR stop_price > 0),
        target_price        REAL    CHECK (target_price IS NULL OR target_price > 0),
        expiration          TEXT,
        invalidation_rule   TEXT,
        quantity            REAL    CHECK (quantity IS NULL OR quantity > 0),
        fill_price          REAL    CHECK (fill_price IS NULL OR fill_price > 0),
        fill_timestamp      TEXT,
        fill_provenance     TEXT,
        exit_price          REAL    CHECK (exit_price IS NULL OR exit_price > 0),
        exit_timestamp      TEXT,
        exit_reason         TEXT    CHECK (exit_reason IS NULL OR exit_reason IN
                              ('stop','target','expiration','invalidation','discretionary')),
        exit_provenance     TEXT,
        terminal_reason     TEXT,
        created_at          TEXT    NOT NULL,
        updated_at          TEXT    NOT NULL,
        UNIQUE (candidate_id, strategy_id, strategy_version),
        CHECK (state != 'open'   OR (fill_price IS NOT NULL AND fill_timestamp IS NOT NULL
                                     AND quantity IS NOT NULL)),
        CHECK (state != 'closed' OR (fill_price IS NOT NULL AND quantity IS NOT NULL
                                     AND exit_price IS NOT NULL
                                     AND exit_timestamp IS NOT NULL AND exit_reason IS NOT NULL)),
        CHECK (state NOT IN ('planned','cancelled','expired','invalidated')
               OR (fill_price IS NULL AND exit_price IS NULL))
    );

    CREATE INDEX IF NOT EXISTS idx_journal_trades_state
        ON journal_trades(state);
    CREATE INDEX IF NOT EXISTS idx_journal_trades_strategy
        ON journal_trades(strategy_id, strategy_version);
    CREATE INDEX IF NOT EXISTS idx_journal_trades_candidate
        ON journal_trades(candidate_id);

    CREATE TABLE IF NOT EXISTS journal_events (
        event_id        TEXT    PRIMARY KEY,
        journal_id      TEXT    NOT NULL REFERENCES journal_trades(journal_id),
        seq             INTEGER NOT NULL,
        event_type      TEXT    NOT NULL CHECK (event_type IN
                          ('created','filled','cancelled',
                           'expired','invalidated','exited')),
        event_timestamp TEXT    NOT NULL,
        recorded_at     TEXT    NOT NULL,
        payload_json    TEXT    NOT NULL DEFAULT '{}',
        UNIQUE (journal_id, seq)
    );

    CREATE TABLE IF NOT EXISTS journal_outcomes (
        outcome_id          TEXT    PRIMARY KEY,
        journal_id          TEXT    NOT NULL REFERENCES journal_trades(journal_id),
        computation_version TEXT    NOT NULL,
        computed_at         TEXT    NOT NULL,
        source_event_seq    INTEGER NOT NULL,
        inputs_hash         TEXT    NOT NULL,
        entry_slippage      REAL,
        costs               REAL    CHECK (costs IS NULL OR costs >= 0),
        gross_return_pct    REAL,
        net_return_pct      REAL,
        outcome_confidence  TEXT    NOT NULL CHECK (outcome_confidence IN
                               ('confirmed','provisional','unknown')),
        inputs_json         TEXT    NOT NULL DEFAULT '{}',
        UNIQUE (journal_id, computation_version, computed_at)
    );
"""


def _migrate_v5_to_v6(con: sqlite3.Connection) -> None:
    """Add point-in-time capture runs and earnings snapshots tables for schema v6."""
    _execute_schema_statements(con, _PIT_SCHEMA_SCRIPT)


_PIT_SCHEMA_SCRIPT = """
    CREATE TABLE IF NOT EXISTS pit_capture_runs (
        capture_run_id      TEXT PRIMARY KEY,
        contract_version    INTEGER NOT NULL DEFAULT 1 CHECK (contract_version = 1),
        idempotency_key     TEXT NOT NULL UNIQUE,
        request_fingerprint TEXT NOT NULL,
        capture_kind        TEXT NOT NULL CHECK (capture_kind IN ('earnings')),
        capture_slot        TEXT NOT NULL CHECK (capture_slot IN ('evening', 'morning')),
        capture_date        TEXT NOT NULL,
        scheduled_for       TEXT NOT NULL,
        requested_at        TEXT NOT NULL,
        completed_at        TEXT,
        requested_provider  TEXT NOT NULL,
        universe_hash       TEXT NOT NULL,
        requested_n         INTEGER NOT NULL CHECK (requested_n >= 1),
        known_n             INTEGER NOT NULL DEFAULT 0 CHECK (known_n >= 0),
        unavailable_n       INTEGER NOT NULL DEFAULT 0 CHECK (unavailable_n >= 0),
        error_n             INTEGER NOT NULL DEFAULT 0 CHECK (error_n >= 0),
        status              TEXT NOT NULL CHECK (status IN ('started', 'succeeded', 'partial', 'failed')),
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL,
        CHECK (status = 'started' OR completed_at IS NOT NULL),
        CHECK (status = 'started' OR requested_n = (known_n + unavailable_n + error_n))
    );

    CREATE INDEX IF NOT EXISTS idx_pit_runs_date_slot ON pit_capture_runs(capture_date, capture_slot);
    CREATE INDEX IF NOT EXISTS idx_pit_runs_status    ON pit_capture_runs(status);
    CREATE INDEX IF NOT EXISTS idx_pit_runs_requested ON pit_capture_runs(requested_at);

    CREATE TABLE IF NOT EXISTS pit_earnings_snapshots (
        snapshot_id          TEXT PRIMARY KEY,
        contract_version     INTEGER NOT NULL DEFAULT 1 CHECK (contract_version = 1),
        capture_run_id       TEXT NOT NULL REFERENCES pit_capture_runs(capture_run_id) ON DELETE CASCADE,
        symbol               TEXT NOT NULL,
        observation_status   TEXT NOT NULL CHECK (observation_status IN ('known', 'unavailable', 'error')),
        next_earnings_date   TEXT,
        provider             TEXT NOT NULL,
        provider_observed_at TEXT,
        request_started_at   TEXT NOT NULL,
        response_received_at TEXT NOT NULL,
        fact_hash            TEXT NOT NULL,
        fact_json            TEXT NOT NULL,
        error_category       TEXT,
        error_message        TEXT,
        created_at           TEXT NOT NULL,
        UNIQUE (capture_run_id, symbol),
        CHECK ((observation_status = 'known' AND next_earnings_date IS NOT NULL) OR (observation_status != 'known' AND next_earnings_date IS NULL)),
        CHECK (request_started_at <= response_received_at)
    );

    CREATE INDEX IF NOT EXISTS idx_pit_snaps_run_id    ON pit_earnings_snapshots(capture_run_id);
    CREATE INDEX IF NOT EXISTS idx_pit_snaps_symbol    ON pit_earnings_snapshots(symbol);
    CREATE INDEX IF NOT EXISTS idx_pit_snaps_next_date ON pit_earnings_snapshots(next_earnings_date);
    CREATE INDEX IF NOT EXISTS idx_pit_snaps_status    ON pit_earnings_snapshots(observation_status);
"""


def _migrate_v6_to_v7(con: sqlite3.Connection) -> None:
    """Add point-in-time reference capture runs and reference snapshots tables for schema v7."""
    _execute_schema_statements(con, _PIT_REFERENCE_SCHEMA_SCRIPT)


_PIT_REFERENCE_SCHEMA_SCRIPT = """
    CREATE TABLE IF NOT EXISTS pit_reference_capture_runs (
        capture_run_id      TEXT PRIMARY KEY,
        contract_version    INTEGER NOT NULL DEFAULT 1 CHECK (contract_version = 1),
        idempotency_key     TEXT NOT NULL UNIQUE,
        request_fingerprint TEXT NOT NULL,
        capture_slot        TEXT NOT NULL CHECK (capture_slot IN ('evening', 'morning')),
        capture_date        TEXT NOT NULL,
        scheduled_for       TEXT NOT NULL,
        requested_at        TEXT NOT NULL,
        completed_at        TEXT,
        requested_provider  TEXT NOT NULL,
        universe_hash       TEXT NOT NULL,
        requested_n         INTEGER NOT NULL CHECK (requested_n >= 1),
        known_n             INTEGER NOT NULL DEFAULT 0 CHECK (known_n >= 0),
        unavailable_n       INTEGER NOT NULL DEFAULT 0 CHECK (unavailable_n >= 0),
        ambiguous_n         INTEGER NOT NULL DEFAULT 0 CHECK (ambiguous_n >= 0),
        error_n             INTEGER NOT NULL DEFAULT 0 CHECK (error_n >= 0),
        status              TEXT NOT NULL CHECK (status IN ('started', 'succeeded', 'partial', 'failed')),
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL,
        CHECK (status = 'started' OR completed_at IS NOT NULL),
        CHECK (status = 'started' OR requested_n = (known_n + unavailable_n + ambiguous_n + error_n))
    );

    CREATE INDEX IF NOT EXISTS idx_pit_ref_runs_date_slot ON pit_reference_capture_runs(capture_date, capture_slot);
    CREATE INDEX IF NOT EXISTS idx_pit_ref_runs_status    ON pit_reference_capture_runs(status);
    CREATE INDEX IF NOT EXISTS idx_pit_ref_runs_requested ON pit_reference_capture_runs(requested_at);

    CREATE TABLE IF NOT EXISTS pit_reference_snapshots (
        snapshot_id                TEXT PRIMARY KEY,
        contract_version           INTEGER NOT NULL DEFAULT 1 CHECK (contract_version = 1),
        capture_run_id             TEXT NOT NULL REFERENCES pit_reference_capture_runs(capture_run_id) ON DELETE CASCADE,
        symbol                     TEXT NOT NULL,
        observation_status         TEXT NOT NULL CHECK (observation_status IN ('known', 'unavailable', 'ambiguous', 'error')),
        provider                   TEXT NOT NULL,
        provider_query_date        TEXT NOT NULL,
        provider_request_ids_json  TEXT NOT NULL DEFAULT '[]',
        provider_ticker            TEXT,
        provider_name              TEXT,
        provider_market            TEXT,
        provider_locale            TEXT,
        provider_active            INTEGER,
        provider_type_code         TEXT,
        provider_primary_exchange  TEXT,
        provider_cik               TEXT,
        provider_composite_figi    TEXT,
        provider_share_class_figi  TEXT,
        provider_last_updated_at   TEXT,
        provider_delisted_at       TEXT,
        missing_fields_json        TEXT NOT NULL DEFAULT '[]',
        request_started_at         TEXT NOT NULL,
        response_received_at       TEXT NOT NULL,
        fact_hash                  TEXT NOT NULL,
        fact_json                  TEXT NOT NULL,
        error_category             TEXT,
        error_message              TEXT,
        created_at                 TEXT NOT NULL,
        UNIQUE (capture_run_id, symbol),
        CHECK (request_started_at <= response_received_at)
    );

    CREATE INDEX IF NOT EXISTS idx_pit_ref_snaps_run_id ON pit_reference_snapshots(capture_run_id);
    CREATE INDEX IF NOT EXISTS idx_pit_ref_snaps_symbol ON pit_reference_snapshots(symbol);
    CREATE INDEX IF NOT EXISTS idx_pit_ref_snaps_status ON pit_reference_snapshots(observation_status);
"""


def init(db_path: str | Path | None = None, *, settings: TradeXSettings | None = None):
    """Create tables if they don't exist and migrate older schemas atomically."""
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _transaction(db_path=path) as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version > _SCHEMA_VERSION:
            raise StoreError(
                f"Database schema version {version} is newer than supported schema version {_SCHEMA_VERSION}. "
                "Downgrades and unknown future versions are rejected."
            )
        if version < _SCHEMA_VERSION:
            if version == 0 and _table_exists(con, "signal_history"):
                _migrate_v0(con)
                _migrate_v1_to_v2(con)
                _migrate_v2_to_v3(con)
                _migrate_v3_to_v4(con)
                _migrate_v4_to_v5(con)
                _migrate_v5_to_v6(con)
                _migrate_v6_to_v7(con)
            elif version == 1 and _table_exists(con, "signal_history"):
                _migrate_v1_to_v2(con)
                _migrate_v2_to_v3(con)
                _migrate_v3_to_v4(con)
                _migrate_v4_to_v5(con)
                _migrate_v5_to_v6(con)
                _migrate_v6_to_v7(con)
            elif version == 2 and _table_exists(con, "signal_history"):
                _migrate_v2_to_v3(con)
                _migrate_v3_to_v4(con)
                _migrate_v4_to_v5(con)
                _migrate_v5_to_v6(con)
                _migrate_v6_to_v7(con)
            elif version == 3 and _table_exists(con, "signal_history"):
                _migrate_v3_to_v4(con)
                _migrate_v4_to_v5(con)
                _migrate_v5_to_v6(con)
                _migrate_v6_to_v7(con)
            elif version == 4 and _table_exists(con, "signal_history"):
                _migrate_v4_to_v5(con)
                _migrate_v5_to_v6(con)
                _migrate_v6_to_v7(con)
            elif version == 5 and (_table_exists(con, "signal_history") or _table_exists(con, "journal_trades")):
                _migrate_v5_to_v6(con)
                _migrate_v6_to_v7(con)
            elif version == 6 and (
                _table_exists(con, "signal_history")
                or _table_exists(con, "journal_trades")
                or _table_exists(con, "pit_capture_runs")
            ):
                _migrate_v6_to_v7(con)
            else:
                _create_schema_v1(con)
                _migrate_v3_to_v4(con)
                _migrate_v4_to_v5(con)
                _migrate_v5_to_v6(con)
                _migrate_v6_to_v7(con)
        else:
            _create_schema_v1(con)
            _migrate_v3_to_v4(con)
            _migrate_v4_to_v5(con)
            _migrate_v5_to_v6(con)
            _migrate_v6_to_v7(con)
        _set_schema_version(con)


_MISSING_PROVIDERS = {"", "unknown", "nan", "<na>", "none"}


def _is_missing_provider(value) -> bool:
    """Treat null/empty/unknown/na-like strings as missing provenance."""
    if pd.isna(value):
        return True
    return str(value).strip().lower() in _MISSING_PROVIDERS


def _resolve_signal_provider(
    results: pd.DataFrame,
    provider: str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> str:
    """Return the single canonical OHLCV provider to persist for a scan run.

    Precedence:
      1. Explicit ``provider`` argument (resolved/normalized).
      2. ``results`` DataFrame ``provider`` column (if it contains exactly one
         valid, resolvable provider; blank/unknown/NaN values are ignored).
      3. ``unknown`` for legacy frames with no provenance.

    Raises ``ValueError`` if the DataFrame contains multiple valid providers or
    a value that cannot be resolved to a canonical provider.
    """
    from tradex.data.fetcher import resolve_provider

    explicit = resolve_provider(provider, settings=settings) if provider is not None else None

    df_providers: set[str] = set()
    if "provider" in results.columns:
        for raw in results["provider"]:
            if _is_missing_provider(raw):
                continue
            try:
                resolved = resolve_provider(str(raw), settings=settings)
            except ValueError as e:
                raise ValueError(f"DataFrame contains invalid provider {raw!r}: {e}") from e
            df_providers.add(resolved)

    if len(df_providers) > 1:
        raise ValueError(f"Mixed providers in results: {sorted(df_providers)}")

    df_provider = next(iter(df_providers)) if df_providers else None

    if explicit is not None and df_provider is not None and explicit != df_provider:
        raise ValueError(
            f"Provider mismatch: DataFrame has '{df_provider}', explicit is '{explicit}'"
        )

    return explicit or df_provider or "unknown"


def _parse_iso_or_none(value: str | None) -> datetime | None:
    """Parse an ISO timestamp or return None without raising."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return None


def _derive_trading_date(scan_time: datetime) -> str | None:
    """Return the XNYS trading date for ``scan_time`` or None on weekends/holidays."""
    try:
        ny_dt = normalize_market_datetime(scan_time)
        day = ny_dt.date()
        if is_trading_day(day):
            return day.isoformat()
    except Exception:  # noqa: BLE001
        return None
    return None


def _observation_to_params(obs: pd.Series, session_id: str) -> tuple:
    """Convert a pandas observation row into DB parameters."""
    return (
        session_id,
        str(obs["ticker"]).strip().upper(),
        str(obs["status"]),
        int(obs["score"]) if pd.notna(obs.get("score")) else None,
        float(obs["last_close"]) if pd.notna(obs.get("last_close")) else None,
        float(obs["volume_ratio"]) if pd.notna(obs.get("volume_ratio")) else None,
        float(obs["rsi"]) if pd.notna(obs.get("rsi")) else None,
        int(obs["days_until_earnings"]) if pd.notna(obs.get("days_until_earnings")) else None,
        _safe_str_or_none(obs.get("reasons")),
        _safe_str_or_none(obs.get("provider")),
        _safe_str_or_none(obs.get("error_category")),
        _safe_str_or_none(obs.get("error_message")),
    )


def _safe_str_or_none(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _status_for_observations(obs: pd.DataFrame) -> str:
    """Determine scan_sessions.status from the observation DataFrame.

    Earnings-excluded observations are valid, successfully-processed outcomes and
    therefore keep a session in ``completed`` status unless a failure also exists.
    """
    if obs.empty:
        return "failed"
    statuses = set(obs["status"].dropna().astype(str).unique())
    has_success = bool(statuses & {"signal", "below_threshold", "earnings_excluded"})
    has_failure = bool(statuses & {"earnings_failure", "fetch_failure", "insufficient_data", "scoring_failure"})
    if has_success and has_failure:
        return "partial"
    if has_success and not has_failure:
        return "completed"
    return "failed"


def _observation_counts(obs: pd.DataFrame) -> dict[str, int]:
    """Return status-derived counts from an observation DataFrame."""
    from tradex.screener.engine import ObservationStatus

    empty = obs.empty
    return {
        "observations_n": 0 if empty else len(obs),
        "signals_n": int((obs["status"] == ObservationStatus.SIGNAL.value).sum()) if not empty else 0,
        "below_threshold_n": int((obs["status"] == ObservationStatus.BELOW_THRESHOLD.value).sum()) if not empty else 0,
        "earnings_excluded_n": int((obs["status"] == ObservationStatus.EARNINGS_EXCLUDED.value).sum()) if not empty else 0,
        "earnings_failure_n": int((obs["status"] == ObservationStatus.EARNINGS_FAILURE.value).sum()) if not empty else 0,
        "fetch_failure_n": int((obs["status"] == ObservationStatus.FETCH_FAILURE.value).sum()) if not empty else 0,
        "insufficient_data_n": int((obs["status"] == ObservationStatus.INSUFFICIENT_DATA.value).sum()) if not empty else 0,
        "scoring_failure_n": int((obs["status"] == ObservationStatus.SCORING_FAILURE.value).sum()) if not empty else 0,
    }


def _persist_scan(
    con: sqlite3.Connection,
    session_id: str,
    report_time: str,
    trading_date: str | None,
    timeframe: str,
    report,
    requested_n: int,
    audit_tickers_n: int | None,
    observations_complete: int,
    counts_complete: int,
    session_source: str,
    audit_source: str,
    status: str,
    min_score: int,
) -> None:
    """Persist the canonical session, observations, signals, and audit row.

    This is the internal atomic write path shared by ``record_scan`` and the
    ``record_signals`` compatibility wrapper. It does not validate the report;
    callers are responsible for ensuring counts and structure are correct.

    ``requested_n`` is stored on the canonical ``scan_sessions`` row and may be a
    lower-bound for compatibility calls. ``audit_tickers_n`` is stored on the
    ``scan_runs`` audit surface and should be ``None`` when the true requested
    universe is unknown.

    ``session_source`` is written to ``scan_sessions.source``; ``audit_source`` is
    written to ``scan_runs.source``. Native scans keep canonical sessions as
    ``live`` and audit rows as ``native``; compatibility callers use
    ``compatibility`` for both.
    """
    from tradex.screener.engine import ObservationStatus

    requested_provider = report.requested_provider
    actual_provider = report.actual_provider
    fallback_used = 1 if report.fallback_used else 0
    providers_attempted = ",".join(report.providers_attempted) if report.providers_attempted else None

    obs = report.observations
    counts = _observation_counts(obs)

    existing = con.execute(
        "SELECT 1 FROM scan_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if existing is not None:
        raise StoreError(f"scan session id already exists: {session_id}")

    con.execute(
        """
        INSERT INTO scan_sessions
          (session_id, scan_time, trading_date, timeframe, requested_provider,
           actual_provider, fallback_used, providers_attempted, status, source,
           observations_complete, requested_n, observations_n, signals_n,
           below_threshold_n, earnings_excluded_n, earnings_failure_n,
           fetch_failure_n, insufficient_data_n, scoring_failure_n, min_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            report_time,
            trading_date,
            timeframe,
            requested_provider,
            actual_provider,
            fallback_used,
            providers_attempted,
            status,
            session_source,
            observations_complete,
            requested_n,
            counts["observations_n"],
            counts["signals_n"],
            counts["below_threshold_n"],
            counts["earnings_excluded_n"],
            counts["earnings_failure_n"],
            counts["fetch_failure_n"],
            counts["insufficient_data_n"],
            counts["scoring_failure_n"],
            min_score,
        ),
    )

    for _, row in obs.iterrows():
        params = _observation_to_params(row, session_id)
        con.execute(
            """
            INSERT INTO scan_observations
              (session_id, ticker, status, score, last_close, volume_ratio, rsi,
               days_until_earnings, reasons, provider, error_category, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )

    if obs.empty or "status" not in obs.columns:
        signal_rows = pd.DataFrame()
    else:
        signal_rows = obs[obs["status"] == ObservationStatus.SIGNAL.value]
    for _, row in signal_rows.iterrows():
        con.execute(
            """
            INSERT INTO signal_history
              (ticker, timeframe, scan_time, score, last_close, volume_ratio, rsi,
               reasons, provider, scan_session_id, trading_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(row["ticker"]).strip().upper(),
                timeframe,
                report_time,
                int(row["score"]),
                float(row["last_close"]) if pd.notna(row["last_close"]) else None,
                float(row["volume_ratio"]) if pd.notna(row["volume_ratio"]) else None,
                float(row["rsi"]) if pd.notna(row["rsi"]) else None,
                _safe_str_or_none(row.get("reasons")),
                _safe_str_or_none(row.get("provider")),
                session_id,
                trading_date,
            ),
        )

    con.execute(
        """
        INSERT INTO scan_runs
          (run_time, timeframe, tickers_n, hits_n, provider,
           session_id, status, requested_provider, actual_provider,
           counts_complete, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report_time,
            timeframe,
            audit_tickers_n,
            counts["signals_n"],
            actual_provider or requested_provider or "unknown",
            session_id,
            status,
            requested_provider,
            actual_provider,
            counts_complete,
            audit_source,
        ),
    )


def record_scan(
    report,
    timeframe: str,
    min_score: int,
    tickers_scanned: Sequence[str],
    *,
    scan_time: datetime | None = None,
    session_id: str | None = None,
    settings: TradeXSettings | None = None,
) -> str:
    """Persist a complete scan report, observations, and qualifying signals.

    The operation is atomic: either the session, observations, signal rows, and
    audit row are all written, or nothing is written.
    """
    if scan_time is None:
        scan_time = datetime.now(UTC)
    if scan_time.tzinfo is None:
        raise ValueError("scan_time must be timezone-aware; naive datetimes are not accepted")

    report.validate(expected_tickers=list(tickers_scanned))

    if session_id is None:
        session_id = uuid.uuid4().hex

    report_time = scan_time.astimezone(UTC).isoformat()
    trading_date = _derive_trading_date(scan_time)

    obs = report.observations
    counts = _observation_counts(obs)
    requested_n = report.total_requested
    signals_n = counts["signals_n"]
    observations_n = counts["observations_n"]

    # Audit-count invariants for a native complete scan.
    if requested_n < 0 or signals_n < 0 or signals_n > requested_n:
        raise StoreError(f"inconsistent audit counts: requested={requested_n}, signals={signals_n}")
    if requested_n != observations_n:
        raise StoreError(f"requested count {requested_n} does not match observation count {observations_n}")
    if requested_n != report.total_requested:
        raise StoreError(f"requested count {requested_n} does not match report.total_requested {report.total_requested}")
    if signals_n != counts["signals_n"]:
        raise StoreError(f"signal count mismatch: {signals_n} vs {counts['signals_n']}")

    status = _status_for_observations(obs)
    observations_complete = 1 if observations_n == requested_n and observations_n > 0 else 0

    with _transaction(db_path=_resolve_db_path(settings)) as con:
        _persist_scan(
            con,
            session_id=session_id,
            report_time=report_time,
            trading_date=trading_date,
            timeframe=timeframe,
            report=report,
            requested_n=requested_n,
            audit_tickers_n=requested_n,
            observations_complete=observations_complete,
            counts_complete=1,
            session_source="live",
            audit_source="native",
            status=status,
            min_score=min_score,
        )

    return session_id


def record_signals(
    results: pd.DataFrame,
    timeframe: str,
    provider: str | None = None,
    *,
    tickers_scanned: Sequence[str] | int | None = None,
    scan_time: datetime | None = None,
    session_id: str | None = None,
    settings: TradeXSettings | None = None,
) -> None:
    """Persist a screener result DataFrame as a compatibility scan session.

    ``record_scan`` is the canonical production API; this wrapper remains for
    callers that only have qualifying results. When the original requested
    universe is known, pass ``tickers_scanned`` so the audit row can be marked
    complete. Otherwise the audit row is marked incomplete and the requested
    count is recorded as a lower-bound only.
    """
    from tradex.screener.engine import ObservationStatus, ScanReport, _normalize_ticker

    if results.empty and tickers_scanned is None:
        # Preserve legacy no-op for empty calls without a known universe.
        return

    scan_provider = _resolve_signal_provider(results, provider=provider, settings=settings)
    if scan_time is None:
        scan_time = datetime.now(UTC)
    if scan_time.tzinfo is None:
        raise ValueError("scan_time must be timezone-aware; naive datetimes are not accepted")
    if session_id is None:
        session_id = uuid.uuid4().hex

    report_time = scan_time.astimezone(UTC).isoformat()
    trading_date = _derive_trading_date(scan_time)

    # Normalize legacy result frames to the stable signal column contract.
    if not results.empty:
        results = results.copy()
        if "days_until_earnings" not in results.columns:
            results["days_until_earnings"] = None
        results["provider"] = scan_provider

    requested_n: int | None = None
    audit_tickers_n: int | None = None
    observations_complete = 0
    counts_complete = 0
    status = "unknown"
    session_source = "compatibility"
    audit_source = "compatibility"

    requested_provider = scan_provider
    actual_provider = scan_provider if not results.empty else None

    if isinstance(tickers_scanned, int):
        if tickers_scanned < 0:
            raise ValueError("tickers_scanned must be non-negative")
        if not results.empty and tickers_scanned < results["ticker"].nunique():
            raise ValueError("tickers_scanned cannot be smaller than the number of result tickers")
        requested_n = tickers_scanned
        audit_tickers_n = tickers_scanned
        counts_complete = 1
        # An integer count does not prove per-ticker outcomes. A positive
        # count with zero results means the remaining tickers are unobserved.
        observations_complete = 0
        status = "unknown"
    elif isinstance(tickers_scanned, Sequence) and not isinstance(tickers_scanned, (str, bytes)):
        normalized_requested = list(dict.fromkeys(_normalize_ticker(t) for t in tickers_scanned))
        if not results.empty:
            result_tickers = set(results["ticker"].apply(_normalize_ticker))
            if not result_tickers.issubset(set(normalized_requested)):
                raise ValueError("tickers_scanned must include every ticker present in results")
            if result_tickers == set(normalized_requested):
                observations_complete = 1
                status = "completed"
        elif not normalized_requested:
            # Explicitly empty requested universe with zero results.
            observations_complete = 1
            status = "completed"
        requested_n = len(normalized_requested)
        audit_tickers_n = requested_n
        counts_complete = 1
    else:
        # tickers_scanned omitted: requested universe is unknowable.
        if results.empty:
            return
        # Use the known result count as a lower-bound for the session; the audit
        # row records an unknown requested count as NULL.
        requested_n = len(results)
        audit_tickers_n = None
        observations_complete = 0
        counts_complete = 0
        status = "unknown"

    observations = []
    for _, row in results.iterrows():
        observations.append({
            "ticker": str(row["ticker"]).strip().upper(),
            "status": ObservationStatus.SIGNAL.value,
            "score": int(row["score"]),
            "last_close": float(row["last_close"]) if pd.notna(row.get("last_close")) else None,
            "volume_ratio": float(row["volume_ratio"]) if pd.notna(row.get("volume_ratio")) else None,
            "rsi": float(row["rsi"]) if pd.notna(row.get("rsi")) else None,
            "days_until_earnings": int(row["days_until_earnings"]) if pd.notna(row.get("days_until_earnings")) else None,
            "reasons": _safe_str_or_none(row.get("reasons")),
            "provider": actual_provider,
            "error_category": None,
            "error_message": None,
        })
    observations_df = pd.DataFrame(observations) if observations else pd.DataFrame()

    total_requested = requested_n if requested_n is not None else len(results)
    report = ScanReport(
        results=results,
        requested_provider=requested_provider,
        actual_provider=actual_provider,
        fallback_used=False,
        providers_attempted=(requested_provider,),
        failures={},
        total_requested=total_requested,
        total_fetch_attempted=total_requested,
        total_fetched=len(results) if not results.empty else 0,
        total_scored=len(results) if not results.empty else 0,
        total_signals=len(results),
        total_below_threshold=0,
        total_insufficient_data=0,
        total_earnings_excluded=0,
        earnings_failures={},
        fetch_failures={},
        scoring_failures={},
        total_fetch_eligible=total_requested,
        total_retries=0,
        attempt_log=[],
        observations=observations_df,
        min_score=0,
    )

    with _transaction(db_path=_resolve_db_path(settings)) as con:
        _persist_scan(
            con,
            session_id=session_id,
            report_time=report_time,
            trading_date=trading_date,
            timeframe=timeframe,
            report=report,
            requested_n=requested_n if requested_n is not None else len(results),
            audit_tickers_n=audit_tickers_n,
            observations_complete=observations_complete,
            counts_complete=counts_complete,
            session_source=session_source,
            audit_source=audit_source,
            status=status,
            min_score=0,
        )


def get_history(ticker: str, timeframe: str, days: int = 14, *, settings: TradeXSettings | None = None) -> pd.DataFrame:
    """Return signal history for a ticker over the last N days."""
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _conn(db_path=_resolve_db_path(settings)) as con:
        rows = con.execute(
            """
            SELECT * FROM signal_history
            WHERE ticker = ? AND timeframe = ?
              AND scan_time >= ?
            ORDER BY scan_time ASC
            """,
            (ticker, timeframe, since),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def get_recent_appearances(timeframe: str, days: int = 7, *, settings: TradeXSettings | None = None) -> pd.DataFrame:
    """
    Return all tickers that appeared in signals within the last N days,
    with their appearance count and latest score.
    Useful for 'seen N times this week' awareness.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _conn(db_path=_resolve_db_path(settings)) as con:
        rows = con.execute(
            """
            SELECT
                ticker,
                COUNT(*)        AS appearances,
                MAX(score)      AS peak_score,
                AVG(score)      AS avg_score,
                MAX(scan_time)  AS last_seen,
                MIN(scan_time)  AS first_seen
            FROM signal_history
            WHERE timeframe = ?
              AND scan_time >= ?
            GROUP BY ticker
            ORDER BY appearances DESC, peak_score DESC
            """,
            (timeframe, since),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def _normalize_outcome_provider(outcome_provider: str | None) -> str:
    """Return a canonical provider name or 'unknown' for a resolved outcome.

    Raises ``ValueError`` if the supplied value is not a valid OHLCV provider.
    """
    if outcome_provider is None or str(outcome_provider).strip().lower() == "unknown":
        return "unknown"
    from tradex.data.fetcher import resolve_provider
    return resolve_provider(outcome_provider)


def mark_outcome_by_id(signal_id: int, outcome_close: float, outcome_provider: str | None = None, *, settings: TradeXSettings | None = None):
    """Record an outcome for the exact signal_history row by id."""
    with _conn(db_path=_resolve_db_path(settings)) as con:
        row = con.execute(
            "SELECT last_close FROM signal_history WHERE id = ?", (signal_id,)
        ).fetchone()
        if not row:
            return
        pct = ((outcome_close - row["last_close"]) / row["last_close"]) * 100
        norm_provider = _normalize_outcome_provider(outcome_provider)
        con.execute(
            """
            UPDATE signal_history
            SET outcome_close = ?, outcome_pct = ?, outcome_at = ?, outcome_provider = ?
            WHERE id = ?
            """,
            (round(outcome_close, 4), round(pct, 2), datetime.now(UTC).isoformat(), norm_provider, signal_id),
        )


def mark_outcome(
    ticker: str,
    timeframe: str,
    scan_time: str,
    outcome_close: float,
    outcome_provider: str | None = None,
    *,
    settings: TradeXSettings | None = None,
):
    """
    Record what the price did after a signal fired.
    outcome_pct is computed automatically from last_close at signal time.
    outcome_provider is normalized to a canonical provider or 'unknown'.
    """
    with _conn(db_path=_resolve_db_path(settings)) as con:
        row = con.execute(
            """
            SELECT id, last_close FROM signal_history
            WHERE ticker = ? AND timeframe = ? AND scan_time = ?
            LIMIT 1
            """,
            (ticker, timeframe, scan_time),
        ).fetchone()
        if not row:
            return
    mark_outcome_by_id(row["id"], outcome_close, outcome_provider=outcome_provider, settings=settings)


def get_signal_journal(timeframe: str | None = None, min_score: int = 0, *, settings: TradeXSettings | None = None) -> pd.DataFrame:
    """Return all signals that have outcomes recorded — the signal journal."""
    tf_filter = "AND timeframe = ?" if timeframe else ""
    params = ([timeframe] if timeframe else []) + [min_score]
    with _conn(db_path=_resolve_db_path(settings)) as con:
        rows = con.execute(
            f"""
            SELECT
                ticker,
                timeframe,
                scan_time,
                score,
                last_close,
                outcome_close,
                outcome_pct,
                outcome_at,
                reasons,
                COALESCE(provider, 'unknown')         AS signal_provider,
                COALESCE(outcome_provider, 'unknown') AS outcome_provider,
                scan_session_id,
                trading_date
            FROM signal_history
            WHERE outcome_close IS NOT NULL
              {tf_filter}
              AND score >= ?
            ORDER BY scan_time DESC
            """,
            params,
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def get_recent_scan_runs(
    timeframe: str | None = None,
    limit: int = 20,
    *,
    complete_only: bool = False,
    settings: TradeXSettings | None = None,
) -> pd.DataFrame:
    """Return recent scan-run rows with provenance and completeness metadata."""
    tf_filter = "AND timeframe = ?" if timeframe else ""
    complete_filter = "AND counts_complete = 1" if complete_only else ""
    params = ([timeframe] if timeframe else []) + [limit]
    with _conn(db_path=_resolve_db_path(settings)) as con:
        rows = con.execute(
            f"""
            SELECT
                run_time,
                timeframe,
                tickers_n,
                hits_n,
                provider,
                session_id,
                status,
                requested_provider,
                actual_provider,
                counts_complete,
                source,
                CASE
                    WHEN counts_complete = 1 AND COALESCE(tickers_n, 0) > 0
                        THEN CAST(100.0 * hits_n / tickers_n AS REAL)
                    ELSE NULL
                END AS hit_rate_pct
            FROM scan_runs
            WHERE 1=1 {tf_filter} {complete_filter}
            ORDER BY run_time DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        df = pd.DataFrame(columns=[
            "run_time", "timeframe", "tickers_n", "hits_n", "provider",
            "session_id", "status", "requested_provider", "actual_provider",
            "counts_complete", "source", "hit_rate_pct",
        ])
    return df


# ── DATA-001 scan session / observation queries ──────────────────────────────

def get_scan_session(session_id: str, *, settings: TradeXSettings | None = None) -> dict | None:
    """Return a scan session as a dict, or None if not found."""
    with _conn(db_path=_resolve_db_path(settings)) as con:
        row = con.execute(
            "SELECT * FROM scan_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def get_scan_observations(session_id: str, *, settings: TradeXSettings | None = None) -> pd.DataFrame:
    """Return all observations for a scan session."""
    with _conn(db_path=_resolve_db_path(settings)) as con:
        rows = con.execute(
            "SELECT * FROM scan_observations WHERE session_id = ? ORDER BY ticker",
            (session_id,),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def get_recent_scan_sessions(timeframe: str | None = None, limit: int = 20, *, settings: TradeXSettings | None = None) -> pd.DataFrame:
    """Return recent scan sessions ordered by scan time."""
    tf_filter = "AND timeframe = ?" if timeframe else ""
    params = ([timeframe] if timeframe else []) + [limit]
    with _conn(db_path=_resolve_db_path(settings)) as con:
        rows = con.execute(
            f"""
            SELECT * FROM scan_sessions
            WHERE 1=1 {tf_filter}
            ORDER BY scan_time DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def get_observation_history(ticker: str, timeframe: str, days: int = 14, *, settings: TradeXSettings | None = None) -> pd.DataFrame:
    """Return the complete observation history for a ticker over the last N days."""
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _conn(db_path=_resolve_db_path(settings)) as con:
        rows = con.execute(
            """
            SELECT so.*, ss.scan_time, ss.timeframe, ss.trading_date
            FROM scan_observations so
            JOIN scan_sessions ss ON so.session_id = ss.session_id
            WHERE so.ticker = ? AND ss.timeframe = ?
              AND ss.scan_time >= ?
            ORDER BY ss.scan_time ASC
            """,
            (ticker, timeframe, since),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def get_daily_score_history(ticker: str, timeframe: str, days: int = 14, *, settings: TradeXSettings | None = None) -> pd.DataFrame:
    """Return one row per distinct XNYS trading session with a score for the ticker.

    When a ticker was observed multiple times in one trading session, the latest
    successfully-scored observation is used so the detector is scan-frequency
    invariant. Ties are broken by the observation ``id`` (most recent first).
    """
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _conn(db_path=_resolve_db_path(settings)) as con:
        rows = con.execute(
            """
            WITH ranked AS (
                SELECT
                    so.ticker,
                    ss.trading_date,
                    ss.scan_time,
                    so.score,
                    so.last_close,
                    so.status,
                    so.provider,
                    so.reasons,
                    ROW_NUMBER() OVER (
                        PARTITION BY ss.trading_date
                        ORDER BY ss.scan_time DESC, so.id DESC
                    ) AS rn
                FROM scan_observations so
                JOIN scan_sessions ss ON so.session_id = ss.session_id
                WHERE so.ticker = ?
                  AND ss.timeframe = ?
                  AND ss.scan_time >= ?
                  AND so.status IN ('signal', 'below_threshold')
                  AND ss.trading_date IS NOT NULL
            )
            SELECT ticker, trading_date, scan_time, score, last_close, status, provider, reasons
            FROM ranked
            WHERE rn = 1
            ORDER BY trading_date ASC
            """,
            (ticker, timeframe, since),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def get_all_daily_scores(timeframe: str, days: int = 14, *, settings: TradeXSettings | None = None) -> pd.DataFrame:
    """Return the latest score observation per ticker per trading date.

    Ties are broken by observation ``id`` (most recent first).
    """
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _conn(db_path=_resolve_db_path(settings)) as con:
        rows = con.execute(
            """
            WITH ranked AS (
                SELECT
                    so.ticker,
                    ss.trading_date,
                    ss.scan_time,
                    so.score,
                    so.last_close,
                    so.status,
                    so.provider,
                    so.reasons,
                    ROW_NUMBER() OVER (
                        PARTITION BY so.ticker, ss.trading_date
                        ORDER BY ss.scan_time DESC, so.id DESC
                    ) AS rn
                FROM scan_observations so
                JOIN scan_sessions ss ON so.session_id = ss.session_id
                WHERE ss.timeframe = ?
                  AND ss.scan_time >= ?
                  AND so.status IN ('signal', 'below_threshold')
                  AND ss.trading_date IS NOT NULL
            )
            SELECT ticker, trading_date, scan_time, score, last_close, status, provider, reasons
            FROM ranked
            WHERE rn = 1
            ORDER BY ticker, trading_date ASC
            """,
            (timeframe, since),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


# ── Candidate persistence primitives (MVP-ARCH-001-R5A) ──────────────────────
def record_candidate_dossier(*args, **kwargs):
    """Record a complete CandidateDossier atomically."""
    from tradex.candidates.store import record_candidate_dossier as _fn
    return _fn(*args, **kwargs)


def get_candidate(*args, **kwargs):
    """Retrieve the immutable candidate snapshot header for candidate_id."""
    from tradex.candidates.store import get_candidate as _fn
    return _fn(*args, **kwargs)


def get_candidate_dossier(*args, **kwargs):
    """Retrieve the complete CandidateDossier for candidate_id."""
    from tradex.candidates.store import get_candidate_dossier as _fn
    return _fn(*args, **kwargs)


def list_candidates(*args, **kwargs):
    """Neutral query API returning candidate snapshot headers."""
    from tradex.candidates.store import list_candidates as _fn
    return _fn(*args, **kwargs)