"""
Automated outcome tracker.

After a signal fires, this module fetches the price at 1, 3, and 5 trading
days later and writes results back to signal_history. Run it daily (e.g.
after market close) alongside the watcher.

Outcome windows:
  1d  — did it move the next day? (intraday setups)
  3d  — short follow-through (short-term setups)
  5d  — weekly resolution (long-term setups)

The best outcome window per timeframe:
  intraday → 1d
  short    → 3d
  long     → 5d
"""
import os
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
import sqlite3

import pandas as pd
import yfinance as yf

from tradex.data.fetcher import normalize_yahoo_columns
from tradex.tracker.store import DB_PATH, _conn, _ensure_db_dir

# Days after signal to measure outcome, keyed by timeframe
OUTCOME_WINDOWS = {
    "intraday": 1,
    "short":    3,
    "long":     5,
}


def _fetch_close_after(ticker: str, after_date: datetime, days_forward: int) -> float | None:
    """
    Fetch the closing price approximately `days_forward` trading days after `after_date`.
    Returns None if data isn't available yet (future date or market holiday gap).
    """
    start = after_date + timedelta(days=1)
    # Fetch extra buffer to account for weekends and holidays
    end = after_date + timedelta(days=days_forward + 7)

    if end > datetime.now(timezone.utc):
        return None  # outcome window hasn't closed yet

    df = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1d",
        progress=False,
        auto_adjust=True,
    )
    if df.empty:
        return None

    df = normalize_yahoo_columns(df)
    if "close" not in df.columns or len(df) < days_forward:
        return None

    # Return the close at the Nth trading day. If that day's close is missing,
    # use the next available close within the fetched window.
    close = df["close"].iloc[days_forward - 1 :].dropna().head(1)
    if close.empty:
        return None
    return float(close.iloc[0])


def _get_pending_outcomes() -> list[dict]:
    """Return signals that fired long enough ago to have an outcome but haven't been marked yet."""
    with _conn() as con:
        rows = con.execute("""
            SELECT id, ticker, timeframe, scan_time, last_close
            FROM signal_history
            WHERE outcome_close IS NULL
              AND last_close IS NOT NULL
        """).fetchall()
    return [dict(r) for r in rows]


def _write_outcome(signal_id: int, outcome_close: float, entry_close: float):
    pct = ((outcome_close - entry_close) / entry_close) * 100
    with _conn() as con:
        con.execute("""
            UPDATE signal_history
            SET outcome_close = ?, outcome_pct = ?, outcome_at = datetime('now')
            WHERE id = ?
        """, (round(outcome_close, 4), round(pct, 2), signal_id))


def run_outcome_pass(verbose: bool = True) -> dict:
    """
    Check all unresolved signals and mark outcomes for those whose window has closed.
    Returns a summary dict of how many were resolved vs still pending.
    """
    _ensure_db_dir()
    pending = _get_pending_outcomes()
    resolved = 0
    still_pending = 0
    errors = 0

    for signal in pending:
        tf = signal["timeframe"]
        days_forward = OUTCOME_WINDOWS.get(tf, 3)
        scan_dt = datetime.fromisoformat(signal["scan_time"])
        if scan_dt.tzinfo is None:
            scan_dt = scan_dt.replace(tzinfo=timezone.utc)

        try:
            outcome_close = _fetch_close_after(signal["ticker"], scan_dt, days_forward)
            if outcome_close is None:
                still_pending += 1
                continue

            _write_outcome(signal["id"], outcome_close, signal["last_close"])
            pct = ((outcome_close - signal["last_close"]) / signal["last_close"]) * 100
            if verbose:
                direction = "▲" if pct > 0 else "▼"
                print(
                    f"[outcome] {signal['ticker']:6s} {tf:8s} "
                    f"signal={signal['scan_time'][:10]}  "
                    f"entry={signal['last_close']:.2f}  "
                    f"exit={outcome_close:.2f}  {direction}{abs(pct):.1f}%"
                )
            resolved += 1

        except Exception as e:
            if verbose:
                print(f"[error]   {signal['ticker']}: {e}")
            errors += 1

    summary = {"resolved": resolved, "pending": still_pending, "errors": errors}
    if verbose:
        print(f"\nOutcome pass complete: {resolved} resolved, {still_pending} pending, {errors} errors")
    return summary


def get_outcome_stats() -> pd.DataFrame:
    """
    Aggregate win rate and avg return per timeframe and score bucket.
    Useful for understanding which signals actually work.
    """
    with _conn() as con:
        rows = con.execute("""
            SELECT
                timeframe,
                CASE
                    WHEN score >= 80 THEN '80-100'
                    WHEN score >= 60 THEN '60-79'
                    WHEN score >= 40 THEN '40-59'
                    ELSE '<40'
                END AS score_bucket,
                COUNT(*)                                         AS total,
                ROUND(AVG(outcome_pct), 2)                       AS avg_return_pct,
                ROUND(100.0 * SUM(CASE WHEN outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                 AS win_rate_pct,
                ROUND(MAX(outcome_pct), 2)                       AS best,
                ROUND(MIN(outcome_pct), 2)                       AS worst
            FROM signal_history
            WHERE outcome_close IS NOT NULL
            GROUP BY timeframe, score_bucket
            ORDER BY timeframe, score_bucket DESC
        """).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


if __name__ == "__main__":
    run_outcome_pass(verbose=True)
