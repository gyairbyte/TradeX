"""
Named watchlist persistence.

Stores named lists of tickers so you can switch between (e.g.) "mega-cap tech",
"semis", "crypto-adjacent", or any custom universe without retyping. Persists
across dashboard restarts.

Storage: SQLite at ~/.tradex/watchlists.db, one row per named list.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.path.expanduser("~/.tradex/watchlists.db"))
DEFAULT_NAME = "Default"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS watchlists (
                name       TEXT PRIMARY KEY,
                tickers    TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


def _normalize(tickers: list[str]) -> list[str]:
    seen = []
    for t in tickers:
        t = t.strip().upper()
        if t and t not in seen:
            seen.append(t)
    return seen


def save(name: str, tickers: list[str]) -> None:
    """Create or overwrite a named watchlist. Names are case-sensitive."""
    name = name.strip()
    if not name:
        raise ValueError("watchlist name cannot be empty")
    tickers = _normalize(tickers)
    if not tickers:
        raise ValueError("watchlist must contain at least one ticker")
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        row = c.execute("SELECT created_at FROM watchlists WHERE name = ?", (name,)).fetchone()
        created = row[0] if row else now
        c.execute(
            "INSERT OR REPLACE INTO watchlists (name, tickers, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (name, ",".join(tickers), created, now),
        )


def load(name: str) -> list[str] | None:
    """Return the tickers in a named watchlist, or None if it doesn't exist."""
    with _conn() as c:
        row = c.execute("SELECT tickers FROM watchlists WHERE name = ?", (name,)).fetchone()
    if not row:
        return None
    return [t for t in row[0].split(",") if t]


def delete(name: str) -> bool:
    """Delete a named watchlist. Returns True if a row was removed."""
    with _conn() as c:
        cur = c.execute("DELETE FROM watchlists WHERE name = ?", (name,))
        return cur.rowcount > 0


def list_all() -> list[dict]:
    """Return [{name, ticker_count, updated_at}] sorted by most recently updated."""
    with _conn() as c:
        rows = c.execute(
            "SELECT name, tickers, updated_at FROM watchlists ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {"name": name, "ticker_count": len([t for t in tickers.split(",") if t]), "updated_at": updated_at}
        for name, tickers, updated_at in rows
    ]
