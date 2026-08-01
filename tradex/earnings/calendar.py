"""Earnings calendar — fetches the next earnings date for a ticker.

The screener / UI filters or flags stocks based on proximity to the next
earnings print.

Data source policy:
  Earnings dates are specialized reference data, not OHLCV. The current source
  is explicitly Yahoo Finance. ``DATA_PROVIDER`` does not affect earnings data.
  The optional ``source`` argument (or ``EARNINGS_DATA_SOURCE`` env var) controls
  the source; unsupported sources raise ProviderCapabilityError rather than
  silently falling back to Yahoo.

Cache:
  ~/.tradex/earnings_cache.db (SQLite, single table). Cached for 24h.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from tradex.data.fetcher import ProviderCapabilityError

CACHE_DIR = Path(os.path.expanduser("~/.tradex"))
CACHE_DB = CACHE_DIR / "earnings_cache.db"
CACHE_TTL_HOURS = 24


def _resolve_earnings_source(source: str | None) -> str:
    """Return the validated earnings source. Only Yahoo is supported in this PR."""
    s = (source or os.getenv("EARNINGS_DATA_SOURCE", "yahoo")).lower().strip()
    if s != "yahoo":
        raise ProviderCapabilityError(
            f"Earnings source '{s}' is not supported; only 'yahoo' is available"
        )
    return s


def _conn() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_cache (
            ticker        TEXT PRIMARY KEY,
            source        TEXT NOT NULL DEFAULT 'yahoo',
            next_earnings TEXT,
            fetched_at    TEXT NOT NULL
        )
    """)
    # Older cache tables did not have a `source` column.
    existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(earnings_cache)")]
    if "source" not in existing_cols:
        conn.execute("ALTER TABLE earnings_cache ADD COLUMN source TEXT NOT NULL DEFAULT 'yahoo'")
    return conn


def _cache_get(ticker: str, source: str) -> tuple[date | None, bool]:
    """Return (next_earnings_date_or_None, is_fresh)."""
    with _conn() as c:
        row = c.execute(
            "SELECT next_earnings, fetched_at FROM earnings_cache WHERE ticker = ? AND source = ?",
            (ticker, source),
        ).fetchone()
    if not row:
        return None, False
    next_str, fetched_str = row
    fetched_at = datetime.fromisoformat(fetched_str)
    is_fresh = datetime.now(timezone.utc).replace(tzinfo=None) - fetched_at < timedelta(hours=CACHE_TTL_HOURS)
    next_date = date.fromisoformat(next_str) if next_str else None
    return next_date, is_fresh


def _cache_put(ticker: str, source: str, next_earnings: date | None) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO earnings_cache (ticker, source, next_earnings, fetched_at) "
            "VALUES (?, ?, ?, ?)",
            (
                ticker,
                source,
                next_earnings.isoformat() if next_earnings else None,
                datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
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


def get_next_earnings(
    ticker: str, force_refresh: bool = False, source: str | None = None
) -> date | None:
    """Return the next earnings date for `ticker`, or None if unavailable.

    ``source`` is explicit; defaults to ``EARNINGS_DATA_SOURCE`` or ``yahoo``.
    Unsupported sources raise ProviderCapabilityError.
    """
    source = _resolve_earnings_source(source)
    if not force_refresh:
        cached, fresh = _cache_get(ticker, source)
        if fresh:
            return cached
    next_date = _fetch_from_yahoo(ticker)
    _cache_put(ticker, source, next_date)
    return next_date


def days_until_earnings(ticker: str, force_refresh: bool = False, source: str | None = None) -> int | None:
    next_date = get_next_earnings(ticker, force_refresh=force_refresh, source=source)
    if next_date is None:
        return None
    return (next_date - date.today()).days


def is_within_earnings_window(ticker: str, within_days: int, source: str | None = None) -> bool:
    """True if the ticker has earnings within `within_days` calendar days."""
    days = days_until_earnings(ticker, source=source)
    return days is not None and 0 <= days <= within_days


def annotate(tickers: list[str], source: str | None = None) -> pd.DataFrame:
    """
    Return a DataFrame with one row per ticker:
      ticker | next_earnings (date or NaT) | days_until (int or NaN)
    Useful for the dashboard's earnings tab.
    """
    rows = []
    for t in tickers:
        try:
            nxt = get_next_earnings(t, source=source)
        except ProviderCapabilityError:
            nxt = None
        rows.append({
            "ticker": t,
            "next_earnings": nxt,
            "days_until": (nxt - date.today()).days if nxt else None,
        })
    return pd.DataFrame(rows)
