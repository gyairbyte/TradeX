"""Tests for fingerprint DB schema migration and source-aware storage."""
import json
import sqlite3
from datetime import UTC, datetime

import pandas as pd

from tradex.patterns import fingerprint


def _build_fake_fp_row():
    return {
        "event_type": "runup",
        "profile": "standard",
        "created_at": datetime.now(UTC).isoformat(),
        "n_events": 5,
        "lookback_days": 10,
        "config_json": json.dumps({"lookback_days": 10}),
        "data_json": json.dumps({"series": {}}),
    }


def test_init_db_migrates_old_schema(tmp_path, monkeypatch):
    """An old fingerprints table without a `source` column is upgraded safely
    and existing Yahoo fingerprints remain readable."""
    db_path = tmp_path / "fingerprints.db"
    monkeypatch.setattr(fingerprint, "DB_PATH", str(db_path))

    # Create an old-style schema exactly as it existed before the source column.
    con = sqlite3.connect(str(db_path))
    con.execute("""
        CREATE TABLE fingerprints (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT NOT NULL,
            profile     TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            n_events    INTEGER NOT NULL,
            lookback_days INTEGER NOT NULL,
            config_json TEXT NOT NULL,
            data_json   TEXT NOT NULL
        )
    """)
    con.execute(
        "CREATE UNIQUE INDEX idx_fp_type_profile ON fingerprints(event_type, profile)"
    )
    old_row = _build_fake_fp_row()
    con.execute(
        "INSERT INTO fingerprints (event_type, profile, created_at, n_events, lookback_days, config_json, data_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        tuple(old_row.values()),
    )
    con.commit()
    con.close()

    # Running _init_db() should add the source column, drop the old index, and
    # create the new source-aware index without destroying existing rows.
    fingerprint._init_db()

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    cols = [r[1] for r in con.execute("PRAGMA table_info(fingerprints)")]
    assert "source" in cols

    indexes = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")]
    assert "idx_fp_type_profile_source" in indexes
    assert "idx_fp_type_profile" not in indexes

    row = con.execute(
        "SELECT event_type, profile, source, n_events FROM fingerprints WHERE event_type='runup' AND profile='standard'"
    ).fetchone()
    con.close()
    assert row is not None
    assert row["source"] == "yahoo"
    assert row["n_events"] == 5

    # load_fingerprint should return the migrated row for the default source.
    loaded = fingerprint.load_fingerprint("runup", "standard", source="yahoo")
    assert loaded is not None
    assert loaded["_n_events"] == 5


def test_build_and_load_fingerprint_carries_source(tmp_path, monkeypatch):
    """A fingerprint built with an explicit source is loaded by that source."""
    db_path = tmp_path / "fingerprints.db"
    monkeypatch.setattr(fingerprint, "DB_PATH", str(db_path))

    events = pd.DataFrame({
        "ticker": ["AAPL"],
        "event_type": ["runup"],
        "event_date": ["2024-01-01"],
        "move_pct": [20.0],
        "price_pct": [[1.0, 2.0]],
        "volume_ratio": [[1.0, 1.0]],
        "rsi": [[50.0, 50.0]],
        "macd_diff": [[0.0, 0.0]],
        "bb_width": [[0.1, 0.1]],
        "atr": [[0.5, 0.5]],
    })

    fp = fingerprint.build_fingerprint(
        events, event_type="runup", profile="standard", source="schwab", min_events=1
    )
    assert fp is not None
    assert fp["source"] == "schwab"

    loaded = fingerprint.load_fingerprint("runup", "standard", source="schwab")
    assert loaded is not None
    assert loaded["_n_events"] == 1

    assert fingerprint.load_fingerprint("runup", "standard", source="yahoo") is None
