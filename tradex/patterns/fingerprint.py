"""
Pattern fingerprinter.

Takes raw mined events (from miner.py) and averages them into a
"fingerprint" — the typical shape of price/volume/indicators in
the days leading up to a major run-up or decline.

The fingerprint is stored to ~/.tradex/fingerprints.db so it doesn't
need to be recomputed every session. Re-run mine + build to refresh.

Fingerprint schema per event_type:
  - mean and std of each series at each time step (day -N to day -1)
  - confidence band (mean ± 1 std)
  - metadata: how many events, date range, config used
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from tradex.data.fetcher import DEFAULT_PROVIDER
from tradex.data.history import _resolve_history_provider
from tradex.patterns.config import PatternConfig, PROFILES

DB_PATH = os.getenv("TRADEX_FP_DB", os.path.expanduser("~/.tradex/fingerprints.db"))
SERIES_KEYS = ["price_pct", "volume_ratio", "rsi", "macd_diff", "bb_width", "atr"]


@contextmanager
def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _init_db():
    with _conn() as con:
        # Create the table if it does not exist. Do NOT create the new
        # source-dependent index here -- on an old schema the `source` column
        # may be missing and the index creation would fail before migration runs.
        con.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,   -- "runup" | "decline"
                profile     TEXT NOT NULL,   -- "standard" | "conservative" | "volatile"
                source      TEXT NOT NULL DEFAULT 'yahoo',
                created_at  TEXT NOT NULL,
                n_events    INTEGER NOT NULL,
                lookback_days INTEGER NOT NULL,
                config_json TEXT NOT NULL,   -- full PatternConfig as JSON
                data_json   TEXT NOT NULL    -- the actual fingerprint series
            )
        """)

        # Migration: older tables did not have a `source` column. Add it first,
        # then drop the old unique index and create the new source-aware one so
        # fingerprints from different providers do not silently overwrite each
        # other.
        existing_cols = [row[1] for row in con.execute("PRAGMA table_info(fingerprints)")]
        if "source" not in existing_cols:
            con.execute(
                "ALTER TABLE fingerprints "
                "ADD COLUMN source TEXT NOT NULL DEFAULT 'yahoo'"
            )

        con.execute("DROP INDEX IF EXISTS idx_fp_type_profile")
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_fp_type_profile_source "
            "ON fingerprints(event_type, profile, source)"
        )


def build_fingerprint(
    events: pd.DataFrame,
    event_type: str,
    profile: str = "standard",
    cfg: PatternConfig | None = None,
    min_events: int | None = None,
    source: str | None = None,
) -> dict | None:
    """
    Average all events of a given type into a fingerprint dict.

    ``source`` records which market-data provider was used to mine the events
    so that Yahoo-built and Schwab-built fingerprints do not overwrite each
    other silently. Defaults to ``DATA_PROVIDER`` or ``yahoo``.

    Returns None if there aren't enough events to trust the result.
    Saves to DB automatically.
    """
    _init_db()
    if cfg is None:
        cfg = PROFILES[profile]
    if min_events is None:
        min_events = cfg.min_events

    subset = events[events["event_type"] == event_type]
    if len(subset) < min_events:
        print(f"  [fingerprint] Only {len(subset)} {event_type} events — need {min_events}. Skipping.")
        return None

    print(f"  Building {event_type} fingerprint from {len(subset)} events…")

    # Each row stores a list for each series key.
    # Pad/truncate to exactly lookback_days so we can stack into a matrix.
    n = cfg.lookback_days
    fingerprint: dict[str, dict] = {}

    for key in SERIES_KEYS:
        if key not in subset.columns:
            continue
        # Parse stored lists
        arrays = []
        for val in subset[key]:
            series = val if isinstance(val, list) else json.loads(val)
            if len(series) >= n:
                arrays.append(series[-n:])   # take the last N days (closest to event)
            elif len(series) > 0:
                # Pad left with the first value
                pad = [series[0]] * (n - len(series))
                arrays.append(pad + series)

        if not arrays:
            continue

        matrix = np.array(arrays, dtype=float)  # shape: (n_events, lookback_days)
        fingerprint[key] = {
            "mean": np.nanmean(matrix, axis=0).round(4).tolist(),
            "std":  np.nanstd(matrix,  axis=0).round(4).tolist(),
            "upper": (np.nanmean(matrix, axis=0) + np.nanstd(matrix, axis=0)).round(4).tolist(),
            "lower": (np.nanmean(matrix, axis=0) - np.nanstd(matrix, axis=0)).round(4).tolist(),
        }

    if not fingerprint:
        return None

    source = (source or DEFAULT_PROVIDER).lower()

    fp = {
        "event_type":    event_type,
        "profile":       profile,
        "source":        source,
        "n_events":      len(subset),
        "lookback_days": n,
        "date_range": {
            "earliest": subset["event_date"].min(),
            "latest":   subset["event_date"].max(),
        },
        "series": fingerprint,
    }

    # Persist
    with _conn() as con:
        con.execute("""
            INSERT INTO fingerprints
              (event_type, profile, source, created_at, n_events, lookback_days, config_json, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_type, profile, source) DO UPDATE SET
              created_at    = excluded.created_at,
              n_events      = excluded.n_events,
              lookback_days = excluded.lookback_days,
              config_json   = excluded.config_json,
              data_json     = excluded.data_json
        """, (
            event_type, profile, source,
            datetime.now(timezone.utc).isoformat(),
            len(subset), n,
            json.dumps(cfg.__dict__),
            json.dumps(fp),
        ))

    print(f"  Saved {event_type} fingerprint from {source} ({len(subset)} events, lookback={n}d)")
    return fp


def load_fingerprint(
    event_type: str, profile: str = "standard", source: str | None = None
) -> dict | None:
    """Load a previously built fingerprint from DB. Returns None if not found.

    ``source`` defaults to ``DATA_PROVIDER`` or ``yahoo`` so the fingerprint
    used for matching comes from the same provider as the live data.
    """
    source = (source or DEFAULT_PROVIDER).lower()
    _init_db()
    with _conn() as con:
        row = con.execute("""
            SELECT data_json, created_at, n_events FROM fingerprints
            WHERE event_type = ? AND profile = ? AND source = ?
        """, (event_type, profile, source)).fetchone()
    if not row:
        return None
    fp = json.loads(row["data_json"])
    fp["_loaded_at"] = row["created_at"]
    fp["_n_events"]  = row["n_events"]
    return fp


def list_fingerprints() -> pd.DataFrame:
    """Return a summary of all stored fingerprints."""
    _init_db()
    with _conn() as con:
        rows = con.execute("""
            SELECT event_type, profile, source, created_at, n_events, lookback_days
            FROM fingerprints ORDER BY created_at DESC
        """).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def run_full_build(
    tickers: list[str] | None = None,
    profile: str = "standard",
    event_type: str = "both",
    verbose: bool = True,
    provider: str | None = None,
) -> dict[str, dict]:
    """
    Convenience function: mine events + build fingerprints in one call.
    Returns dict of {event_type: fingerprint}.

    ``provider`` is passed to the daily-history abstraction. The resolved
    provider is stored with the fingerprint so Schwab and Yahoo caches do
    not mix.
    """
    from tradex.patterns.miner import mine_events
    cfg = PROFILES[profile]

    # Resolve the provider early so the fingerprint source key is explicit.
    source = _resolve_history_provider(provider)

    if verbose:
        print(f"Mining events (profile={profile}, source={source}, {cfg.history_years}yr history)…")

    events = mine_events(
        tickers=tickers, cfg=cfg, event_type=event_type, verbose=verbose, provider=provider
    )

    results = {}
    types = ["runup", "decline"] if event_type == "both" else [event_type]
    for etype in types:
        fp = build_fingerprint(events, etype, profile=profile, cfg=cfg, source=source)
        if fp:
            results[etype] = fp

    return results
