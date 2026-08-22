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

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import ProviderCapabilityError, ProviderDataUnavailableError

DEFAULT_CACHE_DB = Path("~/.tradex/earnings_cache.db")
CACHE_TTL_HOURS = 24


class EarningsDataUnavailableError(ProviderDataUnavailableError):
    """Raised when earnings data is unavailable, unparseable, or has no usable upcoming date."""


def _resolve_cache_db(settings: TradeXSettings | None = None) -> Path:
    """Return the earnings cache path from explicit settings or the runtime default."""
    if settings is None:
        settings = load_runtime_settings()
    return settings.paths.earnings_cache_db


def _resolve_earnings_source(source: str | None, *, settings: TradeXSettings | None = None) -> str:
    """Return the validated earnings source. Only Yahoo is supported in this PR."""
    if settings is None:
        settings = load_runtime_settings()
    s = (source or settings.earnings_data_source).lower().strip()
    if s != "yahoo":
        raise ProviderCapabilityError(
            f"Earnings source '{s}' is not supported; only 'yahoo' is available"
        )
    return s


def _conn(cache_db: Path | None = None) -> sqlite3.Connection:
    db = cache_db or DEFAULT_CACHE_DB
    db = Path(str(db)).expanduser()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
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


def _cache_get(
    ticker: str,
    source: str,
    *,
    cache_db: Path | None = None,
    settings: TradeXSettings | None = None,
) -> tuple[date | None, bool]:
    """Return (next_earnings_date_or_None, is_fresh).

    Cached NULL or empty rows are treated as non-authoritative (is_fresh=False)
    so historical or ambiguous cache entries do not masquerade as proof of no earnings.
    """
    with _conn(cache_db or _resolve_cache_db(settings)) as c:
        row = c.execute(
            "SELECT next_earnings, fetched_at FROM earnings_cache WHERE ticker = ? AND source = ?",
            (ticker, source),
        ).fetchone()
    if not row:
        return None, False
    next_str, fetched_str = row
    if not next_str:
        return None, False
    try:
        fetched_at = datetime.fromisoformat(fetched_str)
        is_fresh = datetime.now(UTC).replace(tzinfo=None) - fetched_at < timedelta(
            hours=CACHE_TTL_HOURS
        )
        if not is_fresh:
            return None, False

        return datetime.strptime(next_str, "%Y-%m-%d").date(), True
    except (ValueError, TypeError):
        return None, False


def _cache_put(
    ticker: str,
    source: str,
    next_earnings: date | None,
    *,
    cache_db: Path | None = None,
    settings: TradeXSettings | None = None,
) -> None:
    """Store only authoritative positive earnings dates.

    Do not cache None / unknown states as authoritative absence.
    """
    if next_earnings is None:
        return
    with _conn(cache_db or _resolve_cache_db(settings)) as c:
        c.execute(
            "INSERT OR REPLACE INTO earnings_cache (ticker, source, next_earnings, fetched_at) "
            "VALUES (?, ?, ?, ?)",
            (
                ticker,
                source,
                next_earnings.isoformat(),
                datetime.now(UTC).replace(tzinfo=None).isoformat(),
            ),
        )


def _fetch_from_yahoo(ticker: str) -> date:
    """
    Pull the next upcoming earnings date from yfinance.

    Tries get_earnings_dates() first (returns past + future); falls back to
    the older .calendar attribute. Raises EarningsDataUnavailableError if nothing
    in the future is available or if provider lookups fail.
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
    except Exception:  # noqa: BLE001
        pass

    try:
        cal = t.calendar
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date") or []
            future = [
                d
                for d in dates
                if isinstance(d, (date, datetime))
                and (d.date() if isinstance(d, datetime) else d) >= today
            ]
            if future:
                return future[0].date() if isinstance(future[0], datetime) else future[0]
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            val = cal.iloc[0, 0]
            if isinstance(val, (pd.Timestamp, datetime)) and val.date() >= today:
                return val.date()
    except Exception:  # noqa: BLE001
        pass

    # Neither method yielded a valid upcoming date.
    # Ensure safe error message containing no secrets, tokens, credentials, or paths.
    raise EarningsDataUnavailableError(f"Upcoming earnings date unavailable for {ticker}")


def get_next_earnings(
    ticker: str,
    force_refresh: bool = False,
    source: str | None = None,
    use_cache: bool = True,
    *,
    settings: TradeXSettings | None = None,
) -> date:
    """Return the next earnings date for `ticker`.

    ``source`` is explicit; defaults to ``EARNINGS_DATA_SOURCE`` or ``yahoo``.
    Unsupported sources raise ProviderCapabilityError.
    Unavailable/unparseable/missing future dates raise EarningsDataUnavailableError.

    When ``use_cache`` is False the Yahoo lookup is still used, but no SQLite
    cache file is read or written. This is the path used by the pre-market gap
    scanner, which must not create persistent database files.
    """
    if settings is None:
        settings = load_runtime_settings()
    source = _resolve_earnings_source(source, settings=settings)
    cache_db = settings.paths.earnings_cache_db
    if use_cache and not force_refresh:
        cached, fresh = _cache_get(ticker, source, cache_db=cache_db, settings=settings)
        if fresh and cached is not None:
            return cached
    next_date = _fetch_from_yahoo(ticker)
    if use_cache and next_date is not None:
        _cache_put(ticker, source, next_date, cache_db=cache_db, settings=settings)
    return next_date


def days_until_earnings(
    ticker: str,
    force_refresh: bool = False,
    source: str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> int:
    """Return the number of calendar days until next earnings date.

    Raises `EarningsDataUnavailableError` or `ProviderCapabilityError` if earnings data is unavailable.
    """
    next_date = get_next_earnings(
        ticker, force_refresh=force_refresh, source=source, settings=settings
    )
    return (next_date - date.today()).days


def is_within_earnings_window(
    ticker: str,
    within_days: int,
    source: str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> bool:
    """True if the ticker has earnings within `within_days` calendar days.

    Propagates `EarningsDataUnavailableError` or `ProviderCapabilityError` if
    earnings data cannot be verified.
    """
    days = days_until_earnings(ticker, source=source, settings=settings)
    return 0 <= days <= within_days


def annotate(
    tickers: list[str], source: str | None = None, *, settings: TradeXSettings | None = None
) -> pd.DataFrame:
    """
    Return a DataFrame with one row per ticker:
      ticker | next_earnings (date or NaT) | days_until (int or NaN) |
      earnings_status ("known" | "unavailable") | error_category | error_message
    Useful for the dashboard's earnings tab.
    """
    rows = []
    for t in tickers:
        nxt: date | None = None
        days: int | None = None
        status = "known"
        error_category: str | None = None
        error_message: str | None = None
        try:
            nxt = get_next_earnings(t, source=source, settings=settings)
            days = (nxt - date.today()).days
        except (ProviderDataUnavailableError, ProviderCapabilityError) as exc:
            nxt = None
            days = None
            status = "unavailable"
            error_category = type(exc).__name__
            error_message = str(exc)
        except Exception as exc:  # noqa: BLE001
            nxt = None
            days = None
            status = "unavailable"
            error_category = "EarningsDataUnavailableError"
            error_message = f"Earnings lookup failed for {t}"

        rows.append(
            {
                "ticker": t,
                "next_earnings": nxt,
                "days_until": days,
                "earnings_status": status,
                "error_category": error_category,
                "error_message": error_message,
            }
        )
    return pd.DataFrame(rows)
