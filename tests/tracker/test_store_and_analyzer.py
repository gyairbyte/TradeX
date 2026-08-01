"""Characterization tests for signal store and coil analyzer."""

import pandas as pd
import pytest

from tradex.tracker import analyzer, store


def _signal_row(ticker: str = "COIL", score: int = 60) -> pd.DataFrame:
    return pd.DataFrame([{
        "ticker": ticker,
        "score": score,
        "last_close": 100.0,
        "volume_ratio": 2.0,
        "rsi": 60.0,
        "reasons": "volume surge",
    }])


@pytest.mark.xfail(strict=True, reason="Coil appearances count scan rows, not distinct sessions (DATA-001/COIL-001)")
def test_coil_counts_distinct_sessions_not_scan_rows(fresh_signal_db):
    """Three scans of the same ticker in one day should not qualify as a coil.

    With min_appearances=2, three executions in a single session should still
    produce an empty coil list. They only count as multiple appearances if the
    detector is incorrectly counting raw scan rows.
    """
    for _ in range(3):
        store.record_signals(_signal_row(), "intraday")

    coils = analyzer.detect_coils("intraday", days=7, min_appearances=2)
    assert coils.empty, "three scans in one session should not satisfy min_appearances=2"


def _signal_row_with_provider(ticker: str = "COIL", score: int = 60, provider: str = "yahoo") -> pd.DataFrame:
    return pd.DataFrame([{
        "ticker": ticker,
        "score": score,
        "last_close": 100.0,
        "volume_ratio": 2.0,
        "rsi": 60.0,
        "reasons": "volume surge",
        "provider": provider,
    }])


def test_init_creates_provenance_columns(fresh_signal_db):
    """The store must include provider and outcome_provider columns."""
    with store._conn() as con:
        sh_cols = {c[1] for c in con.execute("PRAGMA table_info(signal_history)")}
        sr_cols = {c[1] for c in con.execute("PRAGMA table_info(scan_runs)")}
    assert "provider" in sh_cols
    assert "outcome_provider" in sh_cols
    assert "provider" in sr_cols


def test_record_signals_persists_provider(fresh_signal_db):
    """The signal provider and scan-run provider are both persisted."""
    results = _signal_row_with_provider("AAPL", provider="schwab")
    store.record_signals(results, "intraday")

    with store._conn() as con:
        row = con.execute("SELECT provider FROM signal_history LIMIT 1").fetchone()
        run = con.execute("SELECT provider FROM scan_runs LIMIT 1").fetchone()
    assert row["provider"] == "schwab"
    assert run["provider"] == "schwab"


def test_record_signals_uses_unknown_for_legacy_frame(fresh_signal_db):
    """A result frame without a provider column stores 'unknown' rather than guessing."""
    store.record_signals(_signal_row("AAPL"), "intraday")

    with store._conn() as con:
        row = con.execute("SELECT provider FROM signal_history LIMIT 1").fetchone()
    assert row["provider"] == "unknown"


def test_record_signals_explicit_provider_overrides_missing_column(fresh_signal_db):
    """An explicit provider argument is used when the DataFrame has no provider column."""
    store.record_signals(_signal_row("AAPL"), "intraday", provider="alpaca")

    with store._conn() as con:
        row = con.execute("SELECT provider FROM signal_history LIMIT 1").fetchone()
    assert row["provider"] == "alpaca"


def test_record_signals_rejects_mixed_providers(fresh_signal_db):
    """A scan run cannot mix providers in the same result frame."""
    results = pd.concat([
        _signal_row_with_provider("AAPL", provider="yahoo"),
        _signal_row_with_provider("MSFT", provider="schwab"),
    ], ignore_index=True)

    with pytest.raises(ValueError, match="Mixed providers"):
        store.record_signals(results, "intraday")


def test_record_signals_explicit_provider_must_agree_with_frame(fresh_signal_db):
    """An explicit provider that disagrees with the result frame is rejected."""
    results = _signal_row_with_provider("AAPL", provider="schwab")

    with pytest.raises(ValueError, match="mismatch"):
        store.record_signals(results, "intraday", provider="yahoo")


def test_mark_outcome_persists_outcome_provider(fresh_signal_db):
    """The outcome provider is stored separately from the signal provider."""
    store.record_signals(_signal_row_with_provider("AAPL", provider="yahoo"), "intraday")
    store.mark_outcome("AAPL", "intraday", _scan_time_from_ticker("AAPL"), 110.0, outcome_provider="schwab")

    journal = store.get_signal_journal()
    assert journal.iloc[0]["signal_provider"] == "yahoo"
    assert journal.iloc[0]["outcome_provider"] == "schwab"


def _scan_time_from_ticker(ticker: str) -> str:
    with store._conn() as con:
        row = con.execute("SELECT scan_time FROM signal_history WHERE ticker = ?", (ticker,)).fetchone()
    return row["scan_time"]


def test_get_signal_journal_exposes_signal_and_outcome_provider(fresh_signal_db):
    """The journal DataFrame exposes clear signal and outcome provider columns."""
    store.record_signals(_signal_row_with_provider("AAPL", provider="yahoo"), "intraday")
    store.mark_outcome("AAPL", "intraday", _scan_time_from_ticker("AAPL"), 110.0, outcome_provider="schwab")

    journal = store.get_signal_journal()
    assert "signal_provider" in journal.columns
    assert "outcome_provider" in journal.columns
    assert journal["signal_provider"].iloc[0] == "yahoo"
    assert journal["outcome_provider"].iloc[0] == "schwab"


def test_init_migrates_old_database(tmp_path, monkeypatch):
    """An existing database without provenance columns is migrated safely."""
    db_path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(store, "DB_PATH", db_path)

    # Create a pre-PROVIDER-004 schema manually
    import sqlite3
    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE signal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            scan_time TEXT NOT NULL,
            score INTEGER NOT NULL,
            last_close REAL,
            volume_ratio REAL,
            rsi REAL,
            reasons TEXT,
            outcome_close REAL,
            outcome_pct REAL,
            outcome_at TEXT
        )
    """)
    con.execute("""
        CREATE TABLE scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            tickers_n INTEGER,
            hits_n INTEGER
        )
    """)
    con.execute("INSERT INTO signal_history (ticker, timeframe, scan_time, score, last_close, outcome_close, outcome_pct) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("AAPL", "intraday", "2024-01-01T00:00:00+00:00", 60, 100.0, 110.0, 10.0))
    con.execute("INSERT INTO scan_runs (run_time, timeframe, tickers_n, hits_n) VALUES (?, ?, ?, ?)",
                ("2024-01-01T00:00:00+00:00", "intraday", 10, 1))
    con.commit()
    con.close()

    store.init()

    with store._conn() as con:
        sh_cols = {c[1] for c in con.execute("PRAGMA table_info(signal_history)")}
        sr_cols = {c[1] for c in con.execute("PRAGMA table_info(scan_runs)")}
        row = con.execute("SELECT provider, outcome_provider FROM signal_history WHERE ticker = ?", ("AAPL",)).fetchone()
        run_row = con.execute("SELECT provider FROM scan_runs").fetchone()

    assert "provider" in sh_cols
    assert "outcome_provider" in sh_cols
    assert "provider" in sr_cols
    assert row["provider"] == "unknown"
    assert row["outcome_provider"] == "unknown"
    assert run_row["provider"] == "unknown"


def test_init_is_idempotent(fresh_signal_db):
    """Calling init repeatedly on the same database must not fail."""
    store.init()
    store.init()

    with store._conn() as con:
        sh_cols = {c[1] for c in con.execute("PRAGMA table_info(signal_history)")}
    assert "provider" in sh_cols


def test_get_recent_scan_runs_includes_provider(fresh_signal_db):
    """scan_runs rows expose the provider used for the scan."""
    store.record_signals(_signal_row_with_provider("AAPL", provider="schwab"), "intraday")

    runs = store.get_recent_scan_runs()
    assert "provider" in runs.columns
    assert runs.iloc[0]["provider"] == "schwab"


def test_record_signals_unknown_frame_plus_explicit_schwab(fresh_signal_db):
    """An all-unknown provider frame combined with an explicit Schwab provider stores Schwab for every row."""
    results = pd.DataFrame([
        {"ticker": "AAPL", "score": 60, "last_close": 100.0, "volume_ratio": 2.0, "rsi": 60.0, "reasons": "test", "provider": "unknown"},
        {"ticker": "MSFT", "score": 60, "last_close": 100.0, "volume_ratio": 2.0, "rsi": 60.0, "reasons": "test", "provider": "unknown"},
    ])
    store.record_signals(results, "intraday", provider="schwab")

    with store._conn() as con:
        providers = {r["provider"] for r in con.execute("SELECT provider FROM signal_history")}
    assert providers == {"schwab"}


def test_record_signals_null_nan_provider_cells(fresh_signal_db):
    """Blank, None, NaN, and <NA> provider cells are treated as missing and not written raw."""
    results = pd.DataFrame([
        {"ticker": "AAPL", "score": 60, "last_close": 100.0, "volume_ratio": 2.0, "rsi": 60.0, "reasons": "test", "provider": ""},
        {"ticker": "MSFT", "score": 60, "last_close": 100.0, "volume_ratio": 2.0, "rsi": 60.0, "reasons": "test", "provider": None},
        {"ticker": "NVDA", "score": 60, "last_close": 100.0, "volume_ratio": 2.0, "rsi": 60.0, "reasons": "test", "provider": float("nan")},
        {"ticker": "TSLA", "score": 60, "last_close": 100.0, "volume_ratio": 2.0, "rsi": 60.0, "reasons": "test", "provider": "<NA>"},
    ])
    store.record_signals(results, "intraday")

    with store._conn() as con:
        providers = {r["provider"] for r in con.execute("SELECT provider FROM signal_history")}
    assert providers == {"unknown"}
    assert all(p not in ("", "nan", "<na>", "none") for p in providers)


def test_record_signals_mixed_unknown_and_one_valid_provider(fresh_signal_db):
    """Unknown/NaN rows plus one valid provider resolve to the single valid provider."""
    results = pd.DataFrame([
        {"ticker": "AAPL", "score": 60, "last_close": 100.0, "volume_ratio": 2.0, "rsi": 60.0, "reasons": "test", "provider": "unknown"},
        {"ticker": "MSFT", "score": 60, "last_close": 100.0, "volume_ratio": 2.0, "rsi": 60.0, "reasons": "test", "provider": "YAHOO"},
        {"ticker": "NVDA", "score": 60, "last_close": 100.0, "volume_ratio": 2.0, "rsi": 60.0, "reasons": "test", "provider": None},
    ])
    store.record_signals(results, "intraday")

    with store._conn() as con:
        providers = {r["provider"] for r in con.execute("SELECT provider FROM signal_history")}
    assert providers == {"yahoo"}


def test_record_signals_invalid_dataframe_provider(fresh_signal_db):
    """A DataFrame containing an unsupported provider name raises a clear error."""
    results = _signal_row_with_provider("AAPL", provider="bloomberg")

    with pytest.raises(ValueError, match="invalid provider"):
        store.record_signals(results, "intraday")


def test_mark_outcome_defaults_to_unknown(fresh_signal_db):
    """A manual outcome with no provider stores 'unknown' rather than NULL."""
    store.record_signals(_signal_row_with_provider("AAPL", provider="yahoo"), "intraday")
    scan_time = _scan_time_from_ticker("AAPL")
    store.mark_outcome("AAPL", "intraday", scan_time, 110.0)

    with store._conn() as con:
        row = con.execute("SELECT outcome_provider FROM signal_history WHERE ticker = ?", ("AAPL",)).fetchone()
    assert row["outcome_provider"] == "unknown"


def test_mark_outcome_rejects_invalid_provider(fresh_signal_db):
    """An invalid outcome provider is rejected."""
    store.record_signals(_signal_row_with_provider("AAPL", provider="yahoo"), "intraday")
    scan_time = _scan_time_from_ticker("AAPL")

    with pytest.raises(ValueError):
        store.mark_outcome("AAPL", "intraday", scan_time, 110.0, outcome_provider="bloomberg")


def test_get_signal_journal_coalesces_null_outcome_provider(fresh_signal_db):
    """Journal rows with NULL outcome_provider display as 'unknown'."""
    store.record_signals(_signal_row_with_provider("AAPL", provider="yahoo"), "intraday")
    with store._conn() as con:
        con.execute(
            "UPDATE signal_history SET outcome_close = ?, outcome_pct = ? WHERE ticker = ?",
            (110.0, 10.0, "AAPL"),
        )

    journal = store.get_signal_journal()
    assert journal["outcome_provider"].iloc[0] == "unknown"
