"""
Earnings calendar — fetches the next earnings date for a ticker and lets the
screener / UI filter or flag stocks based on proximity to that date.

Why this matters:
  A technically-clean setup that resolves *into* an earnings print is no
  longer a technical trade — it's a binary event bet. This module lets you
  exclude or visually flag those tickers so you don't enter a coil setup
  two days before earnings.

Source:
  yfinance Ticker.calendar / Ticker.get_earnings_dates. Free, no API key.
  Results are cached on disk for 24h to avoid re-hitting Yahoo on every scan.

Cache:
  ~/.tradex/earnings_cache.db (SQLite, single table).
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf


CACHE_DIR = Path(os.path.expanduser("~/.tradex"))
CACHE_DB = CACHE_DIR / "earnings_cache.db"
CACHE_TTL_HOURS = 24


def _conn() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_cache (
            ticker        TEXT PRIMARY KEY,
            next_earnings TEXT,
            fetched_at    TEXT NOT NULL
        )
    """)
    return conn


def _cache_get(ticker: str) -> tuple[date | None, bool]:
    """Return (next_earnings_date_or_None, is_fresh)."""
    with _conn() as c:
        row = c.execute(
            "SELECT next_earnings, fetched_at FROM earnings_cache WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    if not row:
        return None, False
    next_str, fetched_str = row
    fetched_at = datetime.fromisoformat(fetched_str)
    is_fresh = datetime.utcnow() - fetched_at < timedelta(hours=CACHE_TTL_HOURS)
    next_date = date.fromisoformat(next_str) if next_str else None
    return next_date, is_fresh


def _cache_put(ticker: str, next_earnings: date | None) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO earnings_cache (ticker, next_earnings, fetched_at) "
            "VALUES (?, ?, ?)",
            (
                ticker,
                next_earnings.isoformat() if next_earnings else None,
                datetime.utcnow().isoformat(),
            ),
        )


def _fetch_from_yahoo(ticker: str) -> date | None:
    """
    Pull the next upcoming earnings date from yfinance.

    Tries get_earnings_dates() first (returns past + future); falls back to
    the older .calendar attribute. Returns None if nothing in the future is
    available (e.g., ETFs, recently-delisted, or Yahoo just doesn't have it).
    """
    t = yf.Ticker(ticker)
    today = date.today()

    try:
        df = t.get_earnings_dates(limit=12)
        if isinstance(df, pd.DataFrame) and not df.empty:
            idx = pd.to_datetime(df.index, errors="coerce", utc=True).tz_convert(None)
            future = [d.date() for d in idx if pd.notna(d) and d.date() >= today]
            if future:
                return min(future)
    except Exception:
        pass

    try:
        cal = t.calendar
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date") or []
            future = [d for d in dates if isinstance(d, (date, datetime)) and (d.date() if isinstance(d, datetime) else d) >= today]
            if future:
                return future[0].date() if isinstance(future[0], datetime) else future[0]
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            val = cal.iloc[0, 0]
            if isinstance(val, (pd.Timestamp, datetime)) and val.date() >= today:
                return val.date()
    except Exception:
        pass

    return None


def get_next_earnings(ticker: str, force_refresh: bool = False) -> date | None:
    """Return the next earnings date for `ticker`, or None if unavailable."""
    if not force_refresh:
        cached, fresh = _cache_get(ticker)
        if fresh:
            return cached
    next_date = _fetch_from_yahoo(ticker)
    _cache_put(ticker, next_date)
    return next_date


def days_until_earnings(ticker: str, force_refresh: bool = False) -> int | None:
    next_date = get_next_earnings(ticker, force_refresh=force_refresh)
    if next_date is None:
        return None
    return (next_date - date.today()).days


def is_within_earnings_window(ticker: str, within_days: int) -> bool:
    """True if the ticker has earnings within `within_days` calendar days."""
    days = days_until_earnings(ticker)
    return days is not None and 0 <= days <= within_days


def annotate(tickers: list[str]) -> pd.DataFrame:
    """
    Return a DataFrame with one row per ticker:
      ticker | next_earnings (date or NaT) | days_until (int or NaN)
    Useful for the dashboard's earnings tab.
    """
    rows = []
    for t in tickers:
        nxt = get_next_earnings(t)
        rows.append({
            "ticker": t,
            "next_earnings": nxt,
            "days_until": (nxt - date.today()).days if nxt else None,
        })
    return pd.DataFrame(rows)
