"""
Named watchlist persistence.

Stores named lists of tickers so you can switch between (e.g.) "mega-cap tech",
"semis", "crypto-adjacent", or any custom universe without retyping. Persists
across dashboard restarts.

Storage: SQLite at ~/.tradex/watchlists.db, one row per named list.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from tradex.config import TradeXSettings, load_runtime_settings

DB_PATH: Path = Path("~/.tradex/watchlists.db")
_DEFAULT_DB_PATH = DB_PATH  # sentinel for legacy DB_PATH monkeypatch detection
DEFAULT_NAME = "Default"


def _db_path(db_path: Path | None = None) -> str:
    return str(Path(str(db_path or DB_PATH)).expanduser().resolve())


def _conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(_db_path(db_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(_db_path(db_path))


def _resolve_db_path(settings: TradeXSettings | None = None) -> Path:
    """Return the watchlist database path from explicit settings or runtime env.

    Legacy tests may monkeypatch ``DB_PATH``; if the module constant has been
    replaced with a different path, that path takes precedence. Otherwise the
    call-time runtime settings are loaded so ``TRADEX_WATCHLISTS_DB_PATH`` is honored.
    """
    if settings is not None:
        return settings.paths.watchlists_db
    if DB_PATH is not _DEFAULT_DB_PATH and str(DB_PATH) != str(_DEFAULT_DB_PATH):
        return DB_PATH
    return load_runtime_settings().paths.watchlists_db


def init(db_path: str | Path | None = None, *, settings: TradeXSettings | None = None) -> None:
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _conn(db_path=path) as c:
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


def save(name: str, tickers: list[str], *, settings: TradeXSettings | None = None) -> None:
    """Create or overwrite a named watchlist. Names are case-sensitive."""
    name = name.strip()
    if not name:
        raise ValueError("watchlist name cannot be empty")
    tickers = _normalize(tickers)
    if not tickers:
        raise ValueError("watchlist must contain at least one ticker")
    now = datetime.utcnow().isoformat()
    with _conn(db_path=_resolve_db_path(settings)) as c:
        row = c.execute("SELECT created_at FROM watchlists WHERE name = ?", (name,)).fetchone()
        created = row[0] if row else now
        c.execute(
            "INSERT OR REPLACE INTO watchlists (name, tickers, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (name, ",".join(tickers), created, now),
        )


def load(name: str, *, settings: TradeXSettings | None = None) -> list[str] | None:
    """Return the tickers in a named watchlist, or None if it doesn't exist."""
    with _conn(db_path=_resolve_db_path(settings)) as c:
        row = c.execute("SELECT tickers FROM watchlists WHERE name = ?", (name,)).fetchone()
    if not row:
        return None
    return [t for t in row[0].split(",") if t]


def delete(name: str, *, settings: TradeXSettings | None = None) -> bool:
    """Delete a named watchlist. Returns True if a row was removed."""
    with _conn(db_path=_resolve_db_path(settings)) as c:
        cur = c.execute("DELETE FROM watchlists WHERE name = ?", (name,))
        return cur.rowcount > 0


def list_all(*, settings: TradeXSettings | None = None) -> list[dict]:
    """Return [{name, ticker_count, updated_at}] sorted by most recently updated."""
    with _conn(db_path=_resolve_db_path(settings)) as c:
        rows = c.execute(
            "SELECT name, tickers, updated_at FROM watchlists ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {"name": name, "ticker_count": len([t for t in tickers.split(",") if t]), "updated_at": updated_at}
        for name, tickers, updated_at in rows
    ]