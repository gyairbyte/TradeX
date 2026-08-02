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
import os
import sqlite3
import uuid
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pandas as pd

from tradex.market.hours import is_trading_day, normalize_market_datetime

DB_PATH = os.getenv("TRADEX_DB_PATH", os.path.expanduser("~/.tradex/signals.db"))

# DB schema version managed by PRAGMA user_version.
_SCHEMA_VERSION = 1


class StoreError(Exception):
    """Raised when the persistence layer cannot complete an operation."""


@contextmanager
def _conn():
    """Yield a managed SQLite connection. Commits on normal exit."""
    _ensure_db_dir()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


@contextmanager
def _transaction():
    """Yield a connection with explicit BEGIN / COMMIT / ROLLBACK."""
    _ensure_db_dir()
    con = sqlite3.connect(DB_PATH)
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


def _ensure_db_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _column_names(con: sqlite3.Connection, table: str) -> set[str]:
    return {c[1] for c in con.execute(f"PRAGMA table_info({table})")}


def _create_schema_v1(con: sqlite3.Connection) -> None:
    """Create the complete DATA-001 schema and indexes."""
    con.executescript("""
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
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time    TEXT NOT NULL,
            timeframe   TEXT NOT NULL,
            tickers_n   INTEGER,
            hits_n      INTEGER,
            provider    TEXT    NOT NULL DEFAULT 'unknown'
        );

        CREATE TABLE IF NOT EXISTS scan_sessions (
            session_id            TEXT PRIMARY KEY,
            scan_time             TEXT NOT NULL,            -- ISO8601 UTC
            trading_date          TEXT,                     -- New York calendar date or NULL
            timeframe             TEXT NOT NULL,
            requested_provider    TEXT NOT NULL,
            actual_provider       TEXT,
            fallback_used         INTEGER NOT NULL DEFAULT 0,
            providers_attempted   TEXT,                     -- comma-separated
            status                TEXT NOT NULL,
            source                TEXT NOT NULL DEFAULT 'live',
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
            session_id        TEXT NOT NULL,
            ticker            TEXT NOT NULL,
            status            TEXT NOT NULL,
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
    """)
    con.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


def _migrate_v0(con: sqlite3.Connection) -> None:
    """Migrate a pre-DATA-001 database to the canonical schema."""
    # Idempotent additions to older signal_history and scan_runs tables.
    sh_cols = _column_names(con, "signal_history")
    if "provider" not in sh_cols:
        con.execute("ALTER TABLE signal_history ADD COLUMN provider TEXT NOT NULL DEFAULT 'unknown'")
    if "outcome_provider" not in sh_cols:
        con.execute("ALTER TABLE signal_history ADD COLUMN outcome_provider TEXT")
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

    # Create the new canonical tables.
    _create_schema_v1(con)

    # Build deterministic synthetic sessions for legacy signal rows.
    legacy_rows = con.execute(
        """
        SELECT id, ticker, timeframe, scan_time, score, last_close, volume_ratio,
               rsi, reasons, provider
        FROM signal_history
        WHERE scan_session_id IS NULL
        ORDER BY scan_time, timeframe, provider, id
        """
    ).fetchall()

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
        reasons = row["reasons"] or ""
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
                row["volume_ratio"],
                row["rsi"],
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

    con.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


def init():
    """Create tables if they don't exist and migrate older schemas."""
    with _conn() as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version < _SCHEMA_VERSION:
            if _table_exists(con, "signal_history"):
                _migrate_v0(con)
            else:
                _create_schema_v1(con)
        else:
            _create_schema_v1(con)


_MISSING_PROVIDERS = {"", "unknown", "nan", "<na>", "none"}


def _is_missing_provider(value) -> bool:
    """Treat null/empty/unknown/na-like strings as missing provenance."""
    if pd.isna(value):
        return True
    return str(value).strip().lower() in _MISSING_PROVIDERS


def _resolve_signal_provider(results: pd.DataFrame, provider: str | None = None) -> str:
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

    explicit = resolve_provider(provider) if provider is not None else None

    df_providers: set[str] = set()
    if "provider" in results.columns:
        for raw in results["provider"]:
            if _is_missing_provider(raw):
                continue
            try:
                resolved = resolve_provider(str(raw))
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
    """Determine scan_sessions.status from the observation DataFrame."""
    if obs.empty:
        return "failed"
    statuses = set(obs["status"].dropna().astype(str).unique())
    has_success = bool(statuses & {"signal", "below_threshold"})
    has_failure = bool(statuses & {"earnings_failure", "fetch_failure", "insufficient_data", "scoring_failure"})
    if has_success and has_failure:
        return "partial"
    if has_success and not has_failure:
        return "completed"
    return "failed"


def record_scan(
    report,
    timeframe: str,
    min_score: int,
    tickers_scanned: Sequence[str],
    *,
    scan_time: datetime | None = None,
    session_id: str | None = None,
) -> str:
    """Persist a complete scan report, observations, and qualifying signals.

    The operation is atomic: either the session, observations, and signal rows
    are all written, or nothing is written.
    """
    from tradex.screener.engine import ObservationStatus

    if scan_time is None:
        scan_time = datetime.now(UTC)
    if scan_time.tzinfo is None:
        raise ValueError("scan_time must be timezone-aware; naive datetimes are not accepted")

    report.validate(expected_tickers=list(tickers_scanned))

    if session_id is None:
        session_id = uuid.uuid4().hex

    report_time = scan_time.astimezone(UTC).isoformat()
    trading_date = _derive_trading_date(scan_time)

    requested_provider = report.requested_provider
    actual_provider = report.actual_provider or requested_provider
    fallback_used = 1 if report.fallback_used else 0
    providers_attempted = ",".join(report.providers_attempted) if report.providers_attempted else actual_provider
    status = _status_for_observations(report.observations)

    obs = report.observations
    counts = {
        "observations_n": len(obs),
        "signals_n": int((obs["status"] == ObservationStatus.SIGNAL.value).sum()) if not obs.empty else 0,
        "below_threshold_n": int((obs["status"] == ObservationStatus.BELOW_THRESHOLD.value).sum()) if not obs.empty else 0,
        "earnings_excluded_n": int((obs["status"] == ObservationStatus.EARNINGS_EXCLUDED.value).sum()) if not obs.empty else 0,
        "earnings_failure_n": int((obs["status"] == ObservationStatus.EARNINGS_FAILURE.value).sum()) if not obs.empty else 0,
        "fetch_failure_n": int((obs["status"] == ObservationStatus.FETCH_FAILURE.value).sum()) if not obs.empty else 0,
        "insufficient_data_n": int((obs["status"] == ObservationStatus.INSUFFICIENT_DATA.value).sum()) if not obs.empty else 0,
        "scoring_failure_n": int((obs["status"] == ObservationStatus.SCORING_FAILURE.value).sum()) if not obs.empty else 0,
    }

    source = "live"
    observations_complete = 1 if len(obs) == report.total_requested and not obs.empty else 0

    with _transaction() as con:
        # Verify uniqueness of the generated session id.
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
                source,
                observations_complete,
                report.total_requested,
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

        signal_mask = obs["status"] == ObservationStatus.SIGNAL.value
        for _, row in obs[signal_mask].iterrows():
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

    return session_id


def record_signals(results: pd.DataFrame, timeframe: str, provider: str | None = None):
    """Persist a screener result DataFrame. Call after every scan.

    This is a backward-compatibility wrapper that creates a minimal complete
    ScanReport and records it as a scan session.
    """
    from tradex.screener.engine import ObservationStatus, ScanReport

    if results.empty:
        return

    scan_provider = _resolve_signal_provider(results, provider=provider)
    scan_time = datetime.now(UTC)
    session_id = uuid.uuid4().hex

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
            "provider": scan_provider,
            "error_category": None,
            "error_message": None,
        })
    observations_df = pd.DataFrame(observations)

    report = ScanReport(
        results=results,
        requested_provider=scan_provider,
        actual_provider=scan_provider,
        fallback_used=False,
        providers_attempted=(scan_provider,),
        failures={},
        total_requested=len(results),
        total_fetch_attempted=len(results),
        total_fetched=len(results),
        total_scored=len(results),
        total_signals=len(results),
        total_below_threshold=0,
        total_insufficient_data=0,
        total_earnings_excluded=0,
        earnings_failures={},
        fetch_failures={},
        scoring_failures={},
        total_fetch_eligible=len(results),
        total_retries=0,
        attempt_log=[],
        observations=observations_df,
        min_score=0,
    )

    record_scan(report, timeframe, min_score=0, tickers_scanned=results["ticker"].tolist(),
                scan_time=scan_time, session_id=session_id)

    # Preserve legacy scan_runs audit row for compatibility.
    report_time = scan_time.isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO scan_runs (run_time, timeframe, tickers_n, hits_n, provider) VALUES (?, ?, ?, ?, ?)",
            (report_time, timeframe, len(results), len(results), scan_provider),
        )


def get_history(ticker: str, timeframe: str, days: int = 14) -> pd.DataFrame:
    """Return signal history for a ticker over the last N days."""
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _conn() as con:
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


def get_recent_appearances(timeframe: str, days: int = 7) -> pd.DataFrame:
    """
    Return all tickers that appeared in signals within the last N days,
    with their appearance count and latest score.
    Useful for 'seen N times this week' awareness.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _conn() as con:
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


def mark_outcome_by_id(signal_id: int, outcome_close: float, outcome_provider: str | None = None):
    """Record an outcome for the exact signal_history row by id."""
    with _conn() as con:
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
):
    """
    Record what the price did after a signal fired.
    outcome_pct is computed automatically from last_close at signal time.
    outcome_provider is normalized to a canonical provider or 'unknown'.
    """
    with _conn() as con:
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
    mark_outcome_by_id(row["id"], outcome_close, outcome_provider=outcome_provider)


def get_signal_journal(timeframe: str | None = None, min_score: int = 0) -> pd.DataFrame:
    """Return all signals that have outcomes recorded — the signal journal."""
    tf_filter = "AND timeframe = ?" if timeframe else ""
    params = ([timeframe] if timeframe else []) + [min_score]
    with _conn() as con:
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


def get_recent_scan_runs(timeframe: str | None = None, limit: int = 20) -> pd.DataFrame:
    """Return recent scan-run rows with provenance."""
    tf_filter = "AND timeframe = ?" if timeframe else ""
    params = ([timeframe] if timeframe else []) + [limit]
    with _conn() as con:
        rows = con.execute(
            f"""
            SELECT run_time, timeframe, tickers_n, hits_n, provider
            FROM scan_runs
            WHERE 1=1 {tf_filter}
            ORDER BY run_time DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


# ── DATA-001 scan session / observation queries ──────────────────────────────

def get_scan_session(session_id: str) -> dict | None:
    """Return a scan session as a dict, or None if not found."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM scan_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def get_scan_observations(session_id: str) -> pd.DataFrame:
    """Return all observations for a scan session."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM scan_observations WHERE session_id = ? ORDER BY ticker",
            (session_id,),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def get_recent_scan_sessions(timeframe: str | None = None, limit: int = 20) -> pd.DataFrame:
    """Return recent scan sessions ordered by scan time."""
    tf_filter = "AND timeframe = ?" if timeframe else ""
    params = ([timeframe] if timeframe else []) + [limit]
    with _conn() as con:
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


def get_observation_history(ticker: str, timeframe: str, days: int = 14) -> pd.DataFrame:
    """Return the complete observation history for a ticker over the last N days."""
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _conn() as con:
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


def get_daily_score_history(ticker: str, timeframe: str, days: int = 14) -> pd.DataFrame:
    """Return one row per distinct XNYS trading session with a score for the ticker.

    When a ticker was observed multiple times in one trading session, the latest
    successfully-scored observation is used so the detector is scan-frequency
    invariant.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT
                so.ticker,
                ss.trading_date,
                MAX(ss.scan_time) AS scan_time,
                so.score,
                so.last_close,
                so.status,
                so.provider,
                so.reasons
            FROM scan_observations so
            JOIN scan_sessions ss ON so.session_id = ss.session_id
            WHERE so.ticker = ?
              AND ss.timeframe = ?
              AND ss.scan_time >= ?
              AND so.status IN ('signal', 'below_threshold')
              AND ss.trading_date IS NOT NULL
            GROUP BY ss.trading_date
            ORDER BY ss.trading_date ASC
            """,
            (ticker, timeframe, since),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def get_all_daily_scores(timeframe: str, days: int = 14) -> pd.DataFrame:
    """Return the latest score observation per ticker per trading date."""
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT
                so.ticker,
                ss.trading_date,
                MAX(ss.scan_time) AS scan_time,
                so.score,
                so.last_close,
                so.status,
                so.provider,
                so.reasons
            FROM scan_observations so
            JOIN scan_sessions ss ON so.session_id = ss.session_id
            WHERE ss.timeframe = ?
              AND ss.scan_time >= ?
              AND so.status IN ('signal', 'below_threshold')
              AND ss.trading_date IS NOT NULL
            GROUP BY so.ticker, ss.trading_date
            ORDER BY so.ticker, ss.trading_date ASC
            """,
            (timeframe, since),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])
