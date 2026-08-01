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

from tradex.data.fetcher import ProviderCapabilityError, resolve_provider
from tradex.data.history import fetch_daily_history
from tradex.tracker.store import DB_PATH, _conn, _ensure_db_dir, mark_outcome

# Days after signal to measure outcome, keyed by timeframe
OUTCOME_WINDOWS = {
    "intraday": 1,
    "short":    3,
    "long":     5,
}


def _utc_now() -> datetime:
    """Return the current UTC time. Patching this helper keeps tests deterministic."""
    return datetime.now(timezone.utc)


def _fetch_close_after(
    ticker: str, after_date: datetime, days_forward: int, provider: str | None = None
) -> float | None:
    """
    Fetch the closing price `days_forward` trading sessions after `after_date`.

    `days_forward` is a count of trading sessions, not calendar days. A bounded
    +7 calendar-day buffer is used to cover weekends and holidays, but it is
    never treated as an eligibility gate. Outcomes resolve as soon as the Nth
    trading-session close is available in the daily data.

    ``provider`` is passed to the daily-history abstraction. When None, the value
    of the ``DATA_PROVIDER`` environment variable is used.

    Returns None if the required trading session has not occurred yet or its
    close cannot be resolved.
    """
    if after_date.tzinfo is None:
        after_date = after_date.replace(tzinfo=timezone.utc)
    after = after_date.astimezone(timezone.utc).date()

    # The first eligible session is the calendar day after the signal.
    start_date = after + timedelta(days=1)

    # Bounded buffer for weekends/holidays: 7 extra calendar days beyond the
    # requested holding period. The actual fetch window is limited to data that
    # has already had a chance to be available (inclusive end date).
    buffer_end_date = after + timedelta(days=days_forward + 7)
    available_end_date = _utc_now().date()

    end_date = min(buffer_end_date, available_end_date)

    # Nothing to fetch yet.
    if end_date < start_date:
        return None

    df = fetch_daily_history(ticker, start_date, end_date, provider=provider)

    if df.empty:
        return None
    if "close" not in df.columns:
        return None

    # fetch_daily_history returns sorted, de-duplicated, canonical columns.
    # Count trading-session rows first; do not drop NaN closes before the length
    # check, because a missing close in an earlier session is still a session.
    if len(df) < days_forward:
        return None

    # Return the close at the Nth trading session. If that session's close is
    # missing, use the next available close within the fetched window.
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


def _write_outcome(signal: dict, outcome_close: float, outcome_provider: str):
    """Persist a resolved outcome and its provider without overwriting signal provider."""
    mark_outcome(
        signal["ticker"],
        signal["timeframe"],
        signal["scan_time"],
        outcome_close,
        outcome_provider=outcome_provider,
    )


def run_outcome_pass(verbose: bool = True, provider: str | None = None) -> dict:
    """
    Check all unresolved signals and mark outcomes for those whose window has closed.
    Returns a summary dict of how many were resolved vs still pending.

    ``provider`` is passed to the daily-history abstraction for the close lookup.
    The resolved provider is recorded as ``outcome_provider`` on successful outcomes.
    """
    _ensure_db_dir()
    outcome_provider = resolve_provider(provider)
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
            outcome_close = _fetch_close_after(
                signal["ticker"], scan_dt, days_forward, provider=provider
            )
            if outcome_close is None:
                still_pending += 1
                continue

            _write_outcome(signal, outcome_close, outcome_provider)
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
