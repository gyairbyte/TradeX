"""
SQLite-backed signal history store.

Every time the scanner runs, each scored ticker gets a row written here.
This is the foundation for:
  - detecting how long a stock has been building (coil duration)
  - confluence analysis across timeframes
  - signal journal / outcome tracking
  - "seen N times this week" awareness

Schema:
  signal_history  — one row per (ticker, timeframe, scan_time)
  scan_runs       — one row per scan run for auditing
"""
import sqlite3
import os
from datetime import datetime, timezone
from contextlib import contextmanager
import pandas as pd

DB_PATH = os.getenv("TRADEX_DB_PATH", os.path.expanduser("~/.tradex/signals.db"))


def _ensure_db_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def _conn():
    _ensure_db_dir()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init():
    """Create tables if they don't exist and migrate older schemas."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS signal_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker        TEXT    NOT NULL,
                timeframe     TEXT    NOT NULL,
                scan_time     TEXT    NOT NULL,   -- ISO8601 UTC
                score         INTEGER NOT NULL,
                last_close    REAL,
                volume_ratio  REAL,
                rsi           REAL,
                reasons       TEXT,              -- pipe-separated
                -- provenance: OHLCV provider that produced this signal
                provider      TEXT    NOT NULL DEFAULT 'unknown',
                -- outcome tracking (filled in later via mark_outcome)
                outcome_close REAL,
                outcome_pct   REAL,
                outcome_at    TEXT,
                outcome_provider TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sh_ticker    ON signal_history(ticker);
            CREATE INDEX IF NOT EXISTS idx_sh_timeframe ON signal_history(timeframe);
            CREATE INDEX IF NOT EXISTS idx_sh_scan_time ON signal_history(scan_time);

            CREATE TABLE IF NOT EXISTS scan_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time    TEXT NOT NULL,
                timeframe   TEXT NOT NULL,
                tickers_n   INTEGER,
                hits_n      INTEGER,
                provider    TEXT    NOT NULL DEFAULT 'unknown'
            );
        """)

        # Idempotent migrations for pre-PROVIDER-004 databases
        sh_cols = {c[1] for c in con.execute("PRAGMA table_info(signal_history)")}
        if "provider" not in sh_cols:
            con.execute("ALTER TABLE signal_history ADD COLUMN provider TEXT NOT NULL DEFAULT 'unknown'")
        if "outcome_provider" not in sh_cols:
            con.execute("ALTER TABLE signal_history ADD COLUMN outcome_provider TEXT")
            # Pre-existing resolved outcomes did not record provenance; show them as unknown.
            con.execute("""
                UPDATE signal_history
                SET outcome_provider = 'unknown'
                WHERE outcome_provider IS NULL AND outcome_close IS NOT NULL
            """)

        sr_cols = {c[1] for c in con.execute("PRAGMA table_info(scan_runs)")}
        if "provider" not in sr_cols:
            con.execute("ALTER TABLE scan_runs ADD COLUMN provider TEXT NOT NULL DEFAULT 'unknown'")


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


def record_signals(results: pd.DataFrame, timeframe: str, provider: str | None = None):
    """Persist a screener result DataFrame. Call after every scan."""
    if results.empty:
        return
    scan_provider = _resolve_signal_provider(results, provider=provider)
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        for _, row in results.iterrows():
            con.execute("""
                INSERT INTO signal_history
                  (ticker, timeframe, scan_time, score, last_close,
                   volume_ratio, rsi, reasons, provider)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["ticker"], timeframe, now,
                int(row["score"]), float(row["last_close"]),
                float(row["volume_ratio"]), float(row["rsi"]),
                row.get("reasons", ""),
                scan_provider,
            ))
        con.execute("""
            INSERT INTO scan_runs (run_time, timeframe, tickers_n, hits_n, provider)
            VALUES (?, ?, ?, ?, ?)
        """, (now, timeframe, len(results), len(results), scan_provider))


def get_history(ticker: str, timeframe: str, days: int = 14) -> pd.DataFrame:
    """Return signal history for a ticker over the last N days."""
    with _conn() as con:
        rows = con.execute("""
            SELECT * FROM signal_history
            WHERE ticker = ? AND timeframe = ?
              AND scan_time >= datetime('now', ?)
            ORDER BY scan_time ASC
        """, (ticker, timeframe, f"-{days} days")).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def get_recent_appearances(timeframe: str, days: int = 7) -> pd.DataFrame:
    """
    Return all tickers that appeared in signals within the last N days,
    with their appearance count and latest score.
    Useful for 'seen N times this week' awareness.
    """
    with _conn() as con:
        rows = con.execute("""
            SELECT
                ticker,
                COUNT(*)        AS appearances,
                MAX(score)      AS peak_score,
                AVG(score)      AS avg_score,
                MAX(scan_time)  AS last_seen,
                MIN(scan_time)  AS first_seen
            FROM signal_history
            WHERE timeframe = ?
              AND scan_time >= datetime('now', ?)
            GROUP BY ticker
            ORDER BY appearances DESC, peak_score DESC
        """, (timeframe, f"-{days} days")).fetchall()
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
        row = con.execute("""
            SELECT last_close FROM signal_history WHERE id = ?
        """, (signal_id,)).fetchone()
        if not row:
            return
        pct = ((outcome_close - row["last_close"]) / row["last_close"]) * 100
        norm_provider = _normalize_outcome_provider(outcome_provider)
        con.execute("""
            UPDATE signal_history
            SET outcome_close = ?, outcome_pct = ?, outcome_at = datetime('now'), outcome_provider = ?
            WHERE id = ?
        """, (round(outcome_close, 4), round(pct, 2), norm_provider, signal_id))


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
        row = con.execute("""
            SELECT id, last_close FROM signal_history
            WHERE ticker = ? AND timeframe = ? AND scan_time = ?
            LIMIT 1
        """, (ticker, timeframe, scan_time)).fetchone()
        if not row:
            return
    mark_outcome_by_id(row["id"], outcome_close, outcome_provider=outcome_provider)


def get_signal_journal(timeframe: str | None = None, min_score: int = 0) -> pd.DataFrame:
    """Return all signals that have outcomes recorded — the signal journal."""
    tf_filter = "AND timeframe = ?" if timeframe else ""
    params = ([timeframe] if timeframe else []) + [min_score]
    with _conn() as con:
        rows = con.execute(f"""
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
                COALESCE(outcome_provider, 'unknown') AS outcome_provider
            FROM signal_history
            WHERE outcome_close IS NOT NULL
              {tf_filter}
              AND score >= ?
            ORDER BY scan_time DESC
        """, params).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def get_recent_scan_runs(timeframe: str | None = None, limit: int = 20) -> pd.DataFrame:
    """Return recent scan-run rows with provenance."""
    tf_filter = "AND timeframe = ?" if timeframe else ""
    params = ([timeframe] if timeframe else []) + [limit]
    with _conn() as con:
        rows = con.execute(f"""
            SELECT run_time, timeframe, tickers_n, hits_n, provider
            FROM scan_runs
            WHERE 1=1 {tf_filter}
            ORDER BY run_time DESC
            LIMIT ?
        """, params).fetchall()
    return pd.DataFrame([dict(r) for r in rows])
