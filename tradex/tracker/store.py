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
    """Create tables if they don't exist. Safe to call on every startup."""
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
                -- outcome tracking (filled in later via mark_outcome)
                outcome_close REAL,
                outcome_pct   REAL,
                outcome_at    TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sh_ticker    ON signal_history(ticker);
            CREATE INDEX IF NOT EXISTS idx_sh_timeframe ON signal_history(timeframe);
            CREATE INDEX IF NOT EXISTS idx_sh_scan_time ON signal_history(scan_time);

            CREATE TABLE IF NOT EXISTS scan_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time    TEXT NOT NULL,
                timeframe   TEXT NOT NULL,
                tickers_n   INTEGER,
                hits_n      INTEGER
            );
        """)


def record_signals(results: pd.DataFrame, timeframe: str):
    """Persist a screener result DataFrame. Call after every scan."""
    if results.empty:
        return
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        for _, row in results.iterrows():
            con.execute("""
                INSERT INTO signal_history
                  (ticker, timeframe, scan_time, score, last_close, volume_ratio, rsi, reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["ticker"], timeframe, now,
                int(row["score"]), float(row["last_close"]),
                float(row["volume_ratio"]), float(row["rsi"]),
                row.get("reasons", ""),
            ))
        con.execute("""
            INSERT INTO scan_runs (run_time, timeframe, tickers_n, hits_n)
            VALUES (?, ?, ?, ?)
        """, (now, timeframe, len(results), len(results)))


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


def mark_outcome(ticker: str, timeframe: str, scan_time: str, outcome_close: float):
    """
    Record what the price did after a signal fired.
    outcome_pct is computed automatically from last_close at signal time.
    """
    with _conn() as con:
        row = con.execute("""
            SELECT id, last_close FROM signal_history
            WHERE ticker = ? AND timeframe = ? AND scan_time = ?
            LIMIT 1
        """, (ticker, timeframe, scan_time)).fetchone()
        if not row:
            return
        pct = ((outcome_close - row["last_close"]) / row["last_close"]) * 100
        con.execute("""
            UPDATE signal_history
            SET outcome_close = ?, outcome_pct = ?, outcome_at = datetime('now')
            WHERE id = ?
        """, (outcome_close, round(pct, 2), row["id"]))


def get_signal_journal(timeframe: str | None = None, min_score: int = 0) -> pd.DataFrame:
    """Return all signals that have outcomes recorded — the signal journal."""
    tf_filter = "AND timeframe = ?" if timeframe else ""
    params = ([timeframe] if timeframe else []) + [min_score]
    with _conn() as con:
        rows = con.execute(f"""
            SELECT ticker, timeframe, scan_time, score, last_close,
                   outcome_close, outcome_pct, outcome_at, reasons
            FROM signal_history
            WHERE outcome_close IS NOT NULL
              {tf_filter}
              AND score >= ?
            ORDER BY scan_time DESC
        """, params).fetchall()
    return pd.DataFrame([dict(r) for r in rows])
