"""Focused data-integrity tests for COR-012 scan auditing."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest

from tradex.screener.engine import ObservationStatus, ScanReport
from tradex.tracker import store


def _ny(*args) -> datetime:
    from zoneinfo import ZoneInfo
    return datetime(*args, tzinfo=ZoneInfo("America/New_York"))


def _obs(ticker, status, *, score=None, provider=None, error=None, days_until_earnings=None, reasons=None):
    status = status.value if isinstance(status, ObservationStatus) else status
    is_scored = status in (ObservationStatus.SIGNAL.value, ObservationStatus.BELOW_THRESHOLD.value)
    if is_scored and reasons is None:
        reasons = "test"
    if status == ObservationStatus.SCORING_FAILURE.value and provider is None:
        provider = "yahoo"
    return {
        "ticker": ticker,
        "status": status,
        "score": score,
        "last_close": 100.0 if is_scored else None,
        "volume_ratio": 2.0 if is_scored else None,
        "rsi": 60.0 if is_scored else None,
        "days_until_earnings": days_until_earnings,
        "reasons": reasons,
        "provider": provider,
        "error_category": type(error).__name__ if error else None,
        "error_message": str(error) if error else None,
    }


def _scan_report(observations: list[dict], *, requested_provider="yahoo", actual_provider=None, fallback_used=False) -> ScanReport:
    obs_df = pd.DataFrame(observations)
    if obs_df.empty:
        obs_df = pd.DataFrame(columns=[
            "ticker", "status", "score", "last_close", "volume_ratio", "rsi",
            "days_until_earnings", "reasons", "provider", "error_category", "error_message",
        ])

    signal_mask = obs_df["status"] == ObservationStatus.SIGNAL.value
    below_mask = obs_df["status"] == ObservationStatus.BELOW_THRESHOLD.value
    results = obs_df[signal_mask][[
        "ticker", "score", "last_close", "volume_ratio", "rsi",
        "days_until_earnings", "reasons", "provider",
    ]]
    if results.empty:
        results = pd.DataFrame(columns=[
            "ticker", "score", "last_close", "volume_ratio", "rsi",
            "days_until_earnings", "reasons", "provider",
        ])

    if actual_provider is None:
        successful = obs_df[obs_df["status"].isin({ObservationStatus.SIGNAL.value, ObservationStatus.BELOW_THRESHOLD.value})]
        providers = set(successful["provider"].dropna().unique())
        actual_provider = next(iter(providers)) if providers else None

    signals_n = int(signal_mask.sum())
    below_n = int(below_mask.sum())
    return ScanReport(
        results=results,
        requested_provider=requested_provider,
        actual_provider=actual_provider,
        fallback_used=fallback_used,
        providers_attempted=(requested_provider,),
        failures={},
        total_requested=len(obs_df),
        total_fetch_attempted=len(obs_df),
        total_fetched=len(obs_df) if signals_n or below_n else 0,
        total_scored=signals_n + below_n,
        total_signals=signals_n,
        total_below_threshold=below_n,
        total_insufficient_data=int((obs_df["status"] == ObservationStatus.INSUFFICIENT_DATA.value).sum()),
        total_earnings_excluded=int((obs_df["status"] == ObservationStatus.EARNINGS_EXCLUDED.value).sum()),
        earnings_failures={},
        fetch_failures={},
        scoring_failures={},
        total_fetch_eligible=len(obs_df),
        total_retries=0,
        attempt_log=[],
        observations=obs_df,
    )


# ── Fresh schema ─────────────────────────────────────────────────────────────


def test_schema_version_is_three(fresh_signal_db):
    with store._conn() as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
    assert version == 3


def test_scan_runs_has_audit_columns(fresh_signal_db):
    with store._conn() as con:
        cols = {c[1] for c in con.execute("PRAGMA table_info(scan_runs)")}
    assert cols >= {
        "session_id", "status", "requested_provider", "actual_provider",
        "counts_complete", "source",
    }


def test_scan_runs_has_required_indexes(fresh_signal_db):
    with store._conn() as con:
        indexes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='scan_runs'")}
    assert "idx_sr_run_time" in indexes
    assert "idx_sr_timeframe_run_time" in indexes
    assert "idx_sr_session_id" in indexes
    assert "idx_sr_status" in indexes


def test_unique_session_index_allows_null_links(fresh_signal_db):
    """SQLite unique indexes allow multiple NULL session_id values."""
    with store._conn() as con:
        con.execute("INSERT INTO scan_runs (run_time, timeframe) VALUES (?, ?)", ("2025-01-15T10:00:00+00:00", "intraday"))
        con.execute("INSERT INTO scan_runs (run_time, timeframe) VALUES (?, ?)", ("2025-01-15T10:00:00+00:00", "short"))
        rows = con.execute("SELECT COUNT(*) FROM scan_runs WHERE session_id IS NULL").fetchone()[0]
    assert rows == 2


def test_repeated_init_succeeds(fresh_signal_db):
    store.init()
    store.init()
    with store._conn() as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
    assert version == 3


# ── Native persistence ─────────────────────────────────────────────────────────


def test_native_scan_five_requested_two_signals(fresh_signal_db):
    obs = [
        _obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo"),
        _obs("MSFT", ObservationStatus.SIGNAL, score=65, provider="yahoo"),
        _obs("TSLA", ObservationStatus.BELOW_THRESHOLD, score=30, provider="yahoo"),
        _obs("NVDA", ObservationStatus.BELOW_THRESHOLD, score=35, provider="yahoo"),
        _obs("AMD", ObservationStatus.BELOW_THRESHOLD, score=20, provider="yahoo"),
    ]
    report = _scan_report(obs, requested_provider="yahoo")
    session_id = store.record_scan(report, "intraday", 40, ["AAPL", "MSFT", "TSLA", "NVDA", "AMD"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        run = con.execute("SELECT * FROM scan_runs WHERE session_id = ?", (session_id,)).fetchone()
    assert run["tickers_n"] == 5
    assert run["hits_n"] == 2
    assert run["status"] == "completed"
    assert run["counts_complete"] == 1
    assert run["source"] == "native"
    assert run["requested_provider"] == "yahoo"
    assert run["actual_provider"] == "yahoo"
    assert run["session_id"] == session_id


def test_native_zero_signal_below_threshold(fresh_signal_db):
    obs = [
        _obs("AAPL", ObservationStatus.BELOW_THRESHOLD, score=30, provider="yahoo"),
        _obs("MSFT", ObservationStatus.BELOW_THRESHOLD, score=35, provider="yahoo"),
    ]
    report = _scan_report(obs, requested_provider="yahoo")
    store.record_scan(report, "intraday", 40, ["AAPL", "MSFT"], scan_time=_ny(2025, 1, 15, 10, 0))

    runs = store.get_recent_scan_runs()
    assert len(runs) == 1
    assert runs.iloc[0]["tickers_n"] == 2
    assert runs.iloc[0]["hits_n"] == 0
    assert runs.iloc[0]["status"] == "completed"


def test_native_all_earnings_excluded(fresh_signal_db):
    obs = [
        _obs("AAPL", ObservationStatus.EARNINGS_EXCLUDED, days_until_earnings=2),
        _obs("MSFT", ObservationStatus.EARNINGS_EXCLUDED, days_until_earnings=1),
    ]
    report = _scan_report(obs, requested_provider="yahoo", actual_provider="yahoo")
    store.record_scan(report, "intraday", 40, ["AAPL", "MSFT"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        run = con.execute("SELECT * FROM scan_runs").fetchone()
    assert run["tickers_n"] == 2
    assert run["hits_n"] == 0
    assert run["status"] == "completed"
    assert run["actual_provider"] == "yahoo"


def test_native_partial_scan(fresh_signal_db):
    obs = [
        _obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo"),
        _obs("MSFT", ObservationStatus.FETCH_FAILURE, error=Exception("network")),
    ]
    report = _scan_report(obs, requested_provider="yahoo")
    store.record_scan(report, "intraday", 40, ["AAPL", "MSFT"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        run = con.execute("SELECT * FROM scan_runs").fetchone()
    assert run["tickers_n"] == 2
    assert run["hits_n"] == 1
    assert run["status"] == "partial"


def test_native_complete_provider_failure(fresh_signal_db):
    obs = [
        _obs("AAPL", ObservationStatus.FETCH_FAILURE, error=Exception("network")),
        _obs("MSFT", ObservationStatus.FETCH_FAILURE, error=Exception("network")),
    ]
    report = _scan_report(obs, requested_provider="yahoo", actual_provider=None)
    store.record_scan(report, "intraday", 40, ["AAPL", "MSFT"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        run = con.execute("SELECT * FROM scan_runs").fetchone()
    assert run["tickers_n"] == 2
    assert run["hits_n"] == 0
    assert run["status"] == "failed"
    assert run["actual_provider"] is None


def test_native_scoring_failure(fresh_signal_db):
    obs = [
        _obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo"),
        _obs("MSFT", ObservationStatus.SCORING_FAILURE, error=Exception("bad data"), provider="yahoo"),
    ]
    report = _scan_report(obs, requested_provider="yahoo")
    store.record_scan(report, "intraday", 40, ["AAPL", "MSFT"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        run = con.execute("SELECT * FROM scan_runs").fetchone()
    assert run["tickers_n"] == 2
    assert run["hits_n"] == 1
    assert run["status"] == "partial"


def test_duplicate_requested_tickers_normalize_to_one(fresh_signal_db):
    obs = [_obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo")]
    report = _scan_report(obs, requested_provider="yahoo")
    store.record_scan(report, "intraday", 40, ["AAPL", "aapl", "AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        session = con.execute("SELECT requested_n FROM scan_sessions").fetchone()
        run = con.execute("SELECT * FROM scan_runs").fetchone()
    assert session["requested_n"] == 1
    assert run["tickers_n"] == 1
    assert run["hits_n"] == 1


def test_one_audit_row_per_session(fresh_signal_db):
    obs = [_obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo")]
    report = _scan_report(obs, requested_provider="yahoo")
    store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        count = con.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
    assert count == 1


def test_duplicate_session_id_is_rejected(fresh_signal_db):
    obs = [_obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo")]
    report = _scan_report(obs, requested_provider="yahoo")
    _ = store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0), session_id="abc123")

    with pytest.raises(store.StoreError, match="already exists"):
        store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 5), session_id="abc123")


def test_hits_never_exceed_tickers(fresh_signal_db):
    """Validation in record_scan enforces hits <= tickers."""
    obs = [
        _obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo"),
    ]
    report = _scan_report(obs, requested_provider="yahoo")
    # Intentionally mismatch the report so validation fails.
    report.total_requested = 0
    with pytest.raises((store.StoreError, ValueError)):
        store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))


def test_failed_scan_actual_provider_null(fresh_signal_db):
    obs = [_obs("AAPL", ObservationStatus.FETCH_FAILURE, error=Exception("network"))]
    report = _scan_report(obs, requested_provider="yahoo", actual_provider=None)
    store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        session = con.execute("SELECT actual_provider FROM scan_sessions").fetchone()
        run = con.execute("SELECT actual_provider FROM scan_runs").fetchone()
    assert session["actual_provider"] is None
    assert run["actual_provider"] is None


def test_audit_row_and_session_counts_agree(fresh_signal_db):
    obs = [
        _obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo"),
        _obs("MSFT", ObservationStatus.BELOW_THRESHOLD, score=30, provider="yahoo"),
        _obs("NVDA", ObservationStatus.FETCH_FAILURE, error=Exception("network")),
    ]
    report = _scan_report(obs, requested_provider="yahoo")
    session_id = store.record_scan(report, "intraday", 40, ["AAPL", "MSFT", "NVDA"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        session = con.execute("SELECT * FROM scan_sessions WHERE session_id = ?", (session_id,)).fetchone()
        run = con.execute("SELECT * FROM scan_runs WHERE session_id = ?", (session_id,)).fetchone()
    assert run["tickers_n"] == session["requested_n"]
    assert run["hits_n"] == session["signals_n"]
    assert run["status"] == session["status"]


def test_provider_field_is_backward_compatible(fresh_signal_db):
    obs = [_obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="schwab")]
    report = _scan_report(obs, requested_provider="schwab")
    store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    run = store.get_recent_scan_runs().iloc[0]
    assert run["provider"] == "schwab"
    assert run["actual_provider"] == "schwab"
    assert run["requested_provider"] == "schwab"


# ── Transactionality ─────────────────────────────────────────────────────────


def test_audit_insert_failure_rolls_back_entire_transaction(fresh_signal_db, monkeypatch):
    """A failure during the final scan_runs insert rolls back the session, observations, and signals."""
    obs = [_obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo")]
    report = _scan_report(obs, requested_provider="yahoo")

    original = store._persist_scan
    def _wrapped(*args, **kwargs):
        con = args[0]
        con.execute(
            "CREATE TEMP TRIGGER IF NOT EXISTS trg_audit_fail "
            "BEFORE INSERT ON scan_runs "
            "BEGIN SELECT RAISE(ABORT, 'injected audit failure'); END;"
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "_persist_scan", _wrapped)
    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="injected audit failure"):
        store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM scan_sessions").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM scan_observations").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM signal_history").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0] == 0


def test_observation_insert_failure_leaves_no_audit_row(fresh_signal_db):
    obs = [
        _obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo"),
        _obs("MSFT", ObservationStatus.BELOW_THRESHOLD, score=30, provider="yahoo"),
    ]
    report = _scan_report(obs, requested_provider="yahoo")

    call_count = 0
    original = store._observation_to_params
    def _failing_params(obs, session_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return original(obs, session_id)
        raise RuntimeError("injected observation failure")

    with patch.object(store, "_observation_to_params", side_effect=_failing_params), pytest.raises(RuntimeError, match="injected observation failure"):
        store.record_scan(report, "intraday", 40, ["AAPL", "MSFT"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM scan_sessions").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM scan_observations").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM signal_history").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0] == 0


# ── Compatibility wrapper ──────────────────────────────────────────────────────


def _signal_result(ticker, provider="yahoo"):
    return {
        "ticker": ticker,
        "score": 70,
        "last_close": 100.0,
        "volume_ratio": 2.0,
        "rsi": 60.0,
        "reasons": "test",
        "provider": provider,
    }


def test_record_signals_old_three_arg_call_still_works(fresh_signal_db):
    results = pd.DataFrame([_signal_result("AAPL", provider="schwab")])
    store.record_signals(results, "intraday", provider="schwab")

    run = store.get_recent_scan_runs().iloc[0]
    assert run["hits_n"] == 1
    assert run["provider"] == "schwab"


def test_record_signals_omitted_tickers_scanned_is_incomplete(fresh_signal_db):
    results = pd.DataFrame([_signal_result("AAPL")])
    store.record_signals(results, "intraday")

    with store._conn() as con:
        run = con.execute("SELECT * FROM scan_runs").fetchone()
        session = con.execute("SELECT * FROM scan_sessions").fetchone()
    assert run["tickers_n"] is None
    assert run["counts_complete"] == 0
    assert run["source"] == "compatibility"
    assert run["status"] == "unknown"
    assert session["observations_complete"] == 0
    assert session["source"] == "compatibility"


def test_record_signals_explicit_integer_count(fresh_signal_db):
    results = pd.DataFrame([_signal_result("AAPL"), _signal_result("MSFT")])
    store.record_signals(results, "intraday", tickers_scanned=10)

    run = store.get_recent_scan_runs().iloc[0]
    assert run["tickers_n"] == 10
    assert run["hits_n"] == 2
    assert run["counts_complete"] == 1
    assert run["source"] == "compatibility"


def test_record_signals_explicit_ticker_sequence(fresh_signal_db):
    results = pd.DataFrame([_signal_result("AAPL"), _signal_result("MSFT")])
    store.record_signals(results, "intraday", tickers_scanned=["AAPL", "MSFT", "TSLA"])

    run = store.get_recent_scan_runs().iloc[0]
    session = store.get_scan_session(run["session_id"])
    assert run["tickers_n"] == 3
    assert run["hits_n"] == 2
    assert run["counts_complete"] == 1
    assert session["observations_complete"] == 0
    assert session["signals_n"] == 2


def test_record_signals_sequence_exact_match_is_complete(fresh_signal_db):
    results = pd.DataFrame([_signal_result("AAPL"), _signal_result("MSFT")])
    store.record_signals(results, "intraday", tickers_scanned=["AAPL", "MSFT"])

    run = store.get_recent_scan_runs().iloc[0]
    session = store.get_scan_session(run["session_id"])
    assert session["observations_complete"] == 1
    assert run["status"] == "completed"


def test_record_signals_duplicate_tickers_are_deduplicated(fresh_signal_db):
    results = pd.DataFrame([_signal_result("AAPL")])
    store.record_signals(results, "intraday", tickers_scanned=["AAPL", "aapl", "AAPL"])

    run = store.get_recent_scan_runs().iloc[0]
    assert run["tickers_n"] == 1
    assert run["hits_n"] == 1


def test_record_signals_rejects_sequence_missing_result_ticker(fresh_signal_db):
    results = pd.DataFrame([_signal_result("AAPL")])
    with pytest.raises(ValueError, match="tickers_scanned must include"):
        store.record_signals(results, "intraday", tickers_scanned=["MSFT"])


def test_record_signals_rejects_integer_smaller_than_result_count(fresh_signal_db):
    results = pd.DataFrame([_signal_result("AAPL"), _signal_result("MSFT")])
    with pytest.raises(ValueError, match="tickers_scanned cannot be smaller"):
        store.record_signals(results, "intraday", tickers_scanned=1)


def test_record_signals_rejects_negative_integer(fresh_signal_db):
    results = pd.DataFrame([_signal_result("AAPL")])
    with pytest.raises(ValueError, match="non-negative"):
        store.record_signals(results, "intraday", tickers_scanned=-1)


def test_record_signals_preserves_provider_validation(fresh_signal_db):
    results = pd.DataFrame([_signal_result("AAPL", provider="bloomberg")])
    with pytest.raises(ValueError, match="invalid provider"):
        store.record_signals(results, "intraday")


def test_record_signals_no_fake_non_signal_observations(fresh_signal_db):
    """The compatibility wrapper must not fabricate below-threshold observations for missing tickers."""
    results = pd.DataFrame([_signal_result("AAPL"), _signal_result("MSFT")])
    store.record_signals(results, "intraday", tickers_scanned=["AAPL", "MSFT", "TSLA"])

    with store._conn() as con:
        observations = con.execute("SELECT COUNT(*) FROM scan_observations").fetchone()[0]
    assert observations == 2


# ── Migration ────────────────────────────────────────────────────────────────


def _build_v2_db(db_path: str) -> None:
    """Create a version-2 database with mixed native and legacy sessions."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.executescript("""
        PRAGMA user_version = 2;

        CREATE TABLE signal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            scan_time TEXT NOT NULL,
            score INTEGER,
            last_close REAL,
            volume_ratio REAL,
            rsi REAL,
            reasons TEXT,
            provider TEXT,
            outcome_close REAL,
            outcome_pct REAL,
            outcome_at TEXT,
            outcome_provider TEXT,
            scan_session_id TEXT,
            trading_date TEXT
        );

        CREATE TABLE scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            tickers_n INTEGER,
            hits_n INTEGER,
            provider TEXT NOT NULL DEFAULT 'unknown'
        );

        CREATE TABLE scan_sessions (
            session_id TEXT PRIMARY KEY,
            scan_time TEXT NOT NULL,
            trading_date TEXT,
            timeframe TEXT NOT NULL,
            requested_provider TEXT NOT NULL,
            actual_provider TEXT,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            providers_attempted TEXT,
            status TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'live',
            observations_complete INTEGER NOT NULL DEFAULT 0,
            requested_n INTEGER NOT NULL DEFAULT 0,
            observations_n INTEGER NOT NULL DEFAULT 0,
            signals_n INTEGER NOT NULL DEFAULT 0,
            below_threshold_n INTEGER NOT NULL DEFAULT 0,
            earnings_excluded_n INTEGER NOT NULL DEFAULT 0,
            earnings_failure_n INTEGER NOT NULL DEFAULT 0,
            fetch_failure_n INTEGER NOT NULL DEFAULT 0,
            insufficient_data_n INTEGER NOT NULL DEFAULT 0,
            scoring_failure_n INTEGER NOT NULL DEFAULT 0,
            min_score INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE scan_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            status TEXT NOT NULL,
            score INTEGER,
            last_close REAL,
            volume_ratio REAL,
            rsi REAL,
            days_until_earnings INTEGER,
            reasons TEXT,
            provider TEXT,
            error_category TEXT,
            error_message TEXT
        );
    """)

    # Native complete signal session with an old signal-only audit row.
    con.execute(
        "INSERT INTO scan_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("sig-session", "2025-01-15T15:00:00+00:00", "2025-01-15", "intraday",
         "yahoo", "yahoo", 0, "yahoo", "completed", "live", 1, 5, 5, 2, 3, 0, 0, 0, 0, 0, 40)
    )
    for t in ["A", "B", "C", "D", "E"]:
        con.execute(
            "INSERT INTO scan_observations (session_id, ticker, status, provider) VALUES (?, ?, ?, ?)",
            ("sig-session", t, "signal" if t in ("A", "B") else "below_threshold", "yahoo")
        )
    # Old legacy audit row: tickers_n = hits_n = signals_n (2), no session link.
    con.execute(
        "INSERT INTO scan_runs (run_time, timeframe, tickers_n, hits_n, provider) VALUES (?, ?, ?, ?, ?)",
        ("2025-01-15T15:00:00+00:00", "intraday", 2, 2, "yahoo")
    )

    # Native zero-signal session without an old audit row.
    con.execute(
        "INSERT INTO scan_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("zero-session", "2025-01-15T15:05:00+00:00", "2025-01-15", "intraday",
         "yahoo", "yahoo", 0, "yahoo", "completed", "live", 1, 4, 4, 0, 4, 0, 0, 0, 0, 0, 40)
    )
    for t in ["F", "G", "H", "I"]:
        con.execute(
            "INSERT INTO scan_observations (session_id, ticker, status, provider) VALUES (?, ?, ?, ?)",
            ("zero-session", t, "below_threshold", "yahoo")
        )

    # Native failed session without an old audit row.
    con.execute(
        "INSERT INTO scan_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("fail-session", "2025-01-15T15:10:00+00:00", "2025-01-15", "intraday",
         "yahoo", None, 0, "yahoo", "failed", "live", 1, 3, 3, 0, 0, 0, 3, 0, 0, 0, 40)
    )
    for t in ["J", "K", "L"]:
        con.execute(
            "INSERT INTO scan_observations (session_id, ticker, status) VALUES (?, ?, ?)",
            ("fail-session", t, "fetch_failure")
        )

    # Legacy incomplete session: observations_complete = 0, source = legacy.
    con.execute(
        "INSERT INTO scan_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("legacy-session", "2025-01-15T15:15:00+00:00", "2025-01-15", "intraday",
         "yahoo", "yahoo", 0, "yahoo", "completed", "legacy", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 40)
    )

    # Unmatched historical scan_runs row and an ambiguous duplicate.
    con.execute(
        "INSERT INTO scan_runs (run_time, timeframe, tickers_n, hits_n, provider) VALUES (?, ?, ?, ?, ?)",
        ("2024-01-01T10:00:00+00:00", "short", 10, 1, "yahoo")
    )
    con.execute(
        "INSERT INTO scan_runs (run_time, timeframe, tickers_n, hits_n, provider) VALUES (?, ?, ?, ?, ?)",
        ("2024-01-01T10:00:00+00:00", "short", 10, 1, "yahoo")
    )

    con.commit()
    con.close()


def test_migration_backfills_and_preserves_legacy_rows(tmp_path, monkeypatch):
    db_path = str(tmp_path / "v2.db")
    _build_v2_db(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    store.init()

    with store._conn() as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        assert version == 3

        # Signal session linked and corrected: tickers_n becomes 5, hits_n stays 2.
        sig = con.execute("SELECT * FROM scan_runs WHERE session_id = 'sig-session'").fetchone()
        assert sig is not None
        assert sig["tickers_n"] == 5
        assert sig["hits_n"] == 2
        assert sig["counts_complete"] == 1
        assert sig["source"] == "native"
        assert sig["status"] == "completed"

        # Zero-signal and failed sessions got canonical audit rows.
        assert con.execute("SELECT COUNT(*) FROM scan_runs WHERE session_id = 'zero-session'").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM scan_runs WHERE session_id = 'fail-session'").fetchone()[0] == 1

        zero = con.execute("SELECT * FROM scan_runs WHERE session_id = 'zero-session'").fetchone()
        assert zero["tickers_n"] == 4
        assert zero["hits_n"] == 0
        assert zero["status"] == "completed"

        fail = con.execute("SELECT * FROM scan_runs WHERE session_id = 'fail-session'").fetchone()
        assert fail["tickers_n"] == 3
        assert fail["hits_n"] == 0
        assert fail["status"] == "failed"
        assert fail["actual_provider"] is None

        # Legacy incomplete session should not get an audit row with complete counts.
        legacy = con.execute("SELECT * FROM scan_runs WHERE session_id = 'legacy-session'").fetchone()
        assert legacy is None

        # Unmatched historical rows preserved and marked legacy/incomplete.
        unmatched = con.execute("SELECT * FROM scan_runs WHERE source = 'legacy'").fetchall()
        assert len(unmatched) == 2
        for row in unmatched:
            assert row["counts_complete"] == 0
            assert row["status"] == "unknown"
            assert row["session_id"] is None


def test_migration_idempotent_and_no_duplicate_backfill(tmp_path, monkeypatch):
    db_path = str(tmp_path / "v2.db")
    _build_v2_db(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    store.init()
    store.init()

    with store._conn() as con:
        # The signal session still maps to exactly one row; the old row was reused.
        sig_rows = con.execute("SELECT id FROM scan_runs WHERE session_id = 'sig-session'").fetchall()
        assert len(sig_rows) == 1
        # Total rows: 1 native signal + 1 native zero + 1 native fail + 2 legacy = 5.
        total = con.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
        assert total == 5


def test_migration_rollback_leaves_no_new_columns_indexes_or_backfill(tmp_path, monkeypatch):
    """If the v2->v3 migration fails mid-backfill, no columns, indexes, or backfilled rows persist."""
    db_path = str(tmp_path / "v2.db")
    _build_v2_db(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    original = store._migrate_v2_to_v3
    def _wrapped(con):
        con.execute(
            "CREATE TEMP TRIGGER IF NOT EXISTS trg_migration_fail "
            "BEFORE UPDATE OF session_id ON scan_runs "
            "WHEN NEW.session_id IS NOT NULL "
            "BEGIN SELECT RAISE(ABORT, 'injected migration failure'); END;"
        )
        original(con)

    monkeypatch.setattr(store, "_migrate_v2_to_v3", _wrapped)
    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="injected migration failure"):
        store.init()

    con = sqlite3.connect(db_path)
    try:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        assert version == 2

        # New columns and indexes added by the migration must be rolled back.
        cols = {c[1] for c in con.execute("PRAGMA table_info(scan_runs)")}
        assert "session_id" not in cols
        assert "source" not in cols

        indexes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'scan_runs'")}
        assert "idx_sr_session_id_unique" not in indexes

        # No native audit rows were backfilled.
        if "source" in cols:
            native_count = con.execute("SELECT COUNT(*) FROM scan_runs WHERE source IN ('native', 'compatibility')").fetchone()[0]
            assert native_count == 0

        # Legacy rows remain as they were.
        assert con.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0] == 3
    finally:
        con.close()


# ── Query API ─────────────────────────────────────────────────────────────────


def test_get_recent_scan_runs_columns_and_empty_schema(fresh_signal_db):
    df = store.get_recent_scan_runs()
    assert list(df.columns) == [
        "run_time", "timeframe", "tickers_n", "hits_n", "provider",
        "session_id", "status", "requested_provider", "actual_provider",
        "counts_complete", "source", "hit_rate_pct",
    ]
    assert df.empty


def test_get_recent_scan_runs_ordering_and_timeframe_filter(fresh_signal_db):
    t0 = _ny(2025, 1, 15, 10, 0)
    for i, ticker in enumerate(["A", "B", "C"]):
        report = _scan_report([_obs(ticker, ObservationStatus.SIGNAL, score=70, provider="yahoo")], requested_provider="yahoo")
        store.record_scan(report, "intraday", 40, [ticker], scan_time=t0.replace(minute=i))

    # Add one short timeframe scan.
    report = _scan_report([_obs("D", ObservationStatus.SIGNAL, score=70, provider="yahoo")], requested_provider="yahoo")
    store.record_scan(report, "short", 40, ["D"], scan_time=t0.replace(minute=10))

    all_runs = store.get_recent_scan_runs(limit=10)
    assert len(all_runs) == 4
    # Descending by run_time, then id DESC: last recorded first.
    assert all_runs.iloc[0]["timeframe"] == "short"

    intraday = store.get_recent_scan_runs(timeframe="intraday", limit=10)
    assert all(intraday["timeframe"] == "intraday")
    assert len(intraday) == 3


def test_get_recent_scan_runs_complete_only(fresh_signal_db):
    report = _scan_report([_obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo")], requested_provider="yahoo")
    store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        con.execute("INSERT INTO scan_runs (run_time, timeframe, counts_complete, source) VALUES (?, ?, ?, ?)",
                    ("2020-01-01T00:00:00+00:00", "intraday", 0, "legacy"))

    complete = store.get_recent_scan_runs(complete_only=True)
    assert len(complete) == 1
    assert complete.iloc[0]["counts_complete"] == 1


def test_hit_rate_pct_calculation(fresh_signal_db):
    obs = [
        _obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo"),
        _obs("MSFT", ObservationStatus.SIGNAL, score=65, provider="yahoo"),
        _obs("TSLA", ObservationStatus.BELOW_THRESHOLD, score=30, provider="yahoo"),
        _obs("NVDA", ObservationStatus.BELOW_THRESHOLD, score=35, provider="yahoo"),
        _obs("AMD", ObservationStatus.BELOW_THRESHOLD, score=20, provider="yahoo"),
    ]
    report = _scan_report(obs, requested_provider="yahoo")
    store.record_scan(report, "intraday", 40, ["AAPL", "MSFT", "TSLA", "NVDA", "AMD"], scan_time=_ny(2025, 1, 15, 10, 0))

    run = store.get_recent_scan_runs().iloc[0]
    assert run["hit_rate_pct"] == 40.0


def test_hit_rate_null_for_unknown_or_zero_tickers(fresh_signal_db):
    # Legacy row with unknown count.
    with store._conn() as con:
        con.execute(
            "INSERT INTO scan_runs (run_time, timeframe, tickers_n, hits_n, counts_complete, source) VALUES (?, ?, ?, ?, ?, ?)",
            ("2020-01-01T00:00:00+00:00", "intraday", None, 0, 0, "legacy"),
        )
    df = store.get_recent_scan_runs()
    assert pd.isna(df.iloc[0]["hit_rate_pct"])


def test_get_recent_scan_runs_failed_scan_visible(fresh_signal_db):
    obs = [_obs("AAPL", ObservationStatus.FETCH_FAILURE, error=Exception("network"))]
    report = _scan_report(obs, requested_provider="yahoo", actual_provider=None)
    store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    df = store.get_recent_scan_runs()
    assert len(df) == 1
    assert df.iloc[0]["status"] == "failed"
    assert df.iloc[0]["hits_n"] == 0


# ── Additional COR-012 regressions ─────────────────────────────────────────────


def test_scan_runs_partial_unique_index_rejects_duplicate_non_null_session_id(fresh_signal_db):
    with store._conn() as con:
        con.execute(
            "INSERT INTO scan_runs (run_time, timeframe, provider, session_id) VALUES (?, ?, ?, ?)",
            ("2025-01-15T15:00:00+00:00", "intraday", "yahoo", "s1"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO scan_runs (run_time, timeframe, provider, session_id) VALUES (?, ?, ?, ?)",
                ("2025-01-15T15:00:00+00:00", "intraday", "yahoo", "s1"),
            )
        # Multiple NULL session_id rows are allowed.
        con.execute(
            "INSERT INTO scan_runs (run_time, timeframe, provider) VALUES (?, ?, ?)",
            ("2025-01-15T15:00:00+00:00", "intraday", "yahoo"),
        )
        con.execute(
            "INSERT INTO scan_runs (run_time, timeframe, provider) VALUES (?, ?, ?)",
            ("2025-01-15T15:00:00+00:00", "intraday", "yahoo"),
        )


def test_native_scan_session_source_is_live_and_audit_source_is_native(fresh_signal_db):
    obs = [_obs("AAPL", ObservationStatus.SIGNAL, score=70, provider="yahoo")]
    report = _scan_report(obs, requested_provider="yahoo")
    store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    with store._conn() as con:
        session = con.execute("SELECT source FROM scan_sessions").fetchone()
        run = con.execute("SELECT source FROM scan_runs").fetchone()
    assert session["source"] == "live"
    assert run["source"] == "native"


def test_record_signals_compatibility_session_and_audit_source(fresh_signal_db):
    results = pd.DataFrame([_signal_result("AAPL")])
    store.record_signals(results, "intraday", tickers_scanned=["AAPL"])

    with store._conn() as con:
        session = con.execute("SELECT source FROM scan_sessions").fetchone()
        run = con.execute("SELECT source FROM scan_runs").fetchone()
    assert session["source"] == "compatibility"
    assert run["source"] == "compatibility"


def _empty_results_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "ticker", "score", "last_close", "volume_ratio", "rsi",
        "days_until_earnings", "reasons", "provider",
    ])


def test_record_signals_non_empty_sequence_empty_results_is_incomplete(fresh_signal_db):
    empty = _empty_results_df()
    store.record_signals(empty, "intraday", provider="schwab", tickers_scanned=["AAPL"])

    with store._conn() as con:
        run = con.execute("SELECT * FROM scan_runs").fetchone()
        session = con.execute("SELECT * FROM scan_sessions").fetchone()
    assert run["tickers_n"] == 1
    assert run["hits_n"] == 0
    assert run["counts_complete"] == 1
    assert run["status"] == "unknown"
    assert run["actual_provider"] is None
    assert run["requested_provider"] == "schwab"
    assert run["source"] == "compatibility"
    assert session["observations_complete"] == 0
    assert session["status"] == "unknown"
    assert session["requested_provider"] == "schwab"
    assert session["actual_provider"] is None


def test_record_signals_positive_integer_empty_results_is_incomplete(fresh_signal_db):
    empty = _empty_results_df()
    store.record_signals(empty, "intraday", provider="schwab", tickers_scanned=5)

    with store._conn() as con:
        run = con.execute("SELECT * FROM scan_runs").fetchone()
        session = con.execute("SELECT * FROM scan_sessions").fetchone()
    assert run["tickers_n"] == 5
    assert run["hits_n"] == 0
    assert run["counts_complete"] == 1
    assert run["status"] == "unknown"
    assert run["actual_provider"] is None
    assert run["requested_provider"] == "schwab"
    assert run["source"] == "compatibility"
    assert session["observations_complete"] == 0
    assert session["status"] == "unknown"
    assert session["actual_provider"] is None


def test_record_signals_empty_sequence_empty_results_is_complete(fresh_signal_db):
    empty = _empty_results_df()
    store.record_signals(empty, "intraday", provider="schwab", tickers_scanned=[])

    with store._conn() as con:
        run = con.execute("SELECT * FROM scan_runs").fetchone()
        session = con.execute("SELECT * FROM scan_sessions").fetchone()
    assert run["tickers_n"] == 0
    assert run["hits_n"] == 0
    assert run["counts_complete"] == 1
    assert run["status"] == "completed"
    assert run["actual_provider"] is None
    assert run["requested_provider"] == "schwab"
    assert run["source"] == "compatibility"
    assert session["observations_complete"] == 1
    assert session["status"] == "completed"
    assert session["actual_provider"] is None


def test_record_signals_zero_integer_empty_results_is_incomplete(fresh_signal_db):
    empty = _empty_results_df()
    store.record_signals(empty, "intraday", provider="schwab", tickers_scanned=0)

    with store._conn() as con:
        run = con.execute("SELECT * FROM scan_runs").fetchone()
        session = con.execute("SELECT * FROM scan_sessions").fetchone()
    assert run["tickers_n"] == 0
    assert run["hits_n"] == 0
    assert run["counts_complete"] == 1
    assert run["status"] == "unknown"
    assert run["actual_provider"] is None
    assert run["source"] == "compatibility"
    assert session["observations_complete"] == 0
    assert session["status"] == "unknown"
    assert session["actual_provider"] is None


def test_migration_reuses_legacy_row_only_for_unambiguous_one_to_one_match(tmp_path, monkeypatch):
    db_path = str(tmp_path / "v2.db")
    _build_v2_db(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    store.init()

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        sig = con.execute("SELECT * FROM scan_runs WHERE session_id = 'sig-session'").fetchone()
        assert sig is not None
        assert sig["id"] == 1
        assert sig["source"] == "native"


def _build_v2_one_row_two_sessions(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.executescript("""
        PRAGMA user_version = 2;

        CREATE TABLE signal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            scan_time TEXT NOT NULL,
            score INTEGER,
            last_close REAL,
            volume_ratio REAL,
            rsi REAL,
            reasons TEXT,
            provider TEXT,
            outcome_close REAL,
            outcome_pct REAL,
            outcome_at TEXT,
            outcome_provider TEXT,
            scan_session_id TEXT,
            trading_date TEXT
        );

        CREATE TABLE scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            tickers_n INTEGER,
            hits_n INTEGER,
            provider TEXT NOT NULL DEFAULT 'unknown'
        );

        CREATE TABLE scan_sessions (
            session_id TEXT PRIMARY KEY,
            scan_time TEXT NOT NULL,
            trading_date TEXT,
            timeframe TEXT NOT NULL,
            requested_provider TEXT NOT NULL,
            actual_provider TEXT,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            providers_attempted TEXT,
            status TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'live',
            observations_complete INTEGER NOT NULL DEFAULT 0,
            requested_n INTEGER NOT NULL DEFAULT 0,
            observations_n INTEGER NOT NULL DEFAULT 0,
            signals_n INTEGER NOT NULL DEFAULT 0,
            below_threshold_n INTEGER NOT NULL DEFAULT 0,
            earnings_excluded_n INTEGER NOT NULL DEFAULT 0,
            earnings_failure_n INTEGER NOT NULL DEFAULT 0,
            fetch_failure_n INTEGER NOT NULL DEFAULT 0,
            insufficient_data_n INTEGER NOT NULL DEFAULT 0,
            scoring_failure_n INTEGER NOT NULL DEFAULT 0,
            min_score INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE scan_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            status TEXT NOT NULL,
            score INTEGER,
            last_close REAL,
            volume_ratio REAL,
            rsi REAL,
            days_until_earnings INTEGER,
            reasons TEXT,
            provider TEXT,
            error_category TEXT,
            error_message TEXT
        );
    """)

    base = ("2025-01-15T15:00:00+00:00", "intraday")
    for sid in ("session-a", "session-b"):
        con.execute(
            "INSERT INTO scan_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, base[0], "2025-01-15", base[1], "yahoo", "yahoo", 0, "yahoo", "completed", "live", 1, 3, 3, 1, 2, 0, 0, 0, 0, 0, 40)
        )
        for t in ("A", "B", "C"):
            con.execute(
                "INSERT INTO scan_observations (session_id, ticker, status, provider) VALUES (?, ?, ?, ?)",
                (sid, t, "signal" if t == "A" else "below_threshold", "yahoo")
            )

    con.execute(
        "INSERT INTO scan_runs (run_time, timeframe, tickers_n, hits_n, provider) VALUES (?, ?, ?, ?, ?)",
        (base[0], base[1], 2, 1, "yahoo")
    )
    con.commit()
    con.close()


def test_migration_does_not_reuse_legacy_row_for_one_row_multiple_sessions(tmp_path, monkeypatch):
    db_path = str(tmp_path / "v2.db")
    _build_v2_one_row_two_sessions(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    store.init()

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM scan_runs").fetchall()
        assert len(rows) == 3
        legacy = [r for r in rows if r["source"] == "legacy"]
        native = [r for r in rows if r["source"] == "native"]
        assert len(legacy) == 1
        assert len(native) == 2
        assert legacy[0]["session_id"] is None
        for r in native:
            assert r["session_id"] in ("session-a", "session-b")
            assert r["counts_complete"] == 1


def _build_v2_two_rows_one_session(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.executescript("""
        PRAGMA user_version = 2;

        CREATE TABLE signal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            scan_time TEXT NOT NULL,
            score INTEGER,
            last_close REAL,
            volume_ratio REAL,
            rsi REAL,
            reasons TEXT,
            provider TEXT,
            outcome_close REAL,
            outcome_pct REAL,
            outcome_at TEXT,
            outcome_provider TEXT,
            scan_session_id TEXT,
            trading_date TEXT
        );

        CREATE TABLE scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            tickers_n INTEGER,
            hits_n INTEGER,
            provider TEXT NOT NULL DEFAULT 'unknown'
        );

        CREATE TABLE scan_sessions (
            session_id TEXT PRIMARY KEY,
            scan_time TEXT NOT NULL,
            trading_date TEXT,
            timeframe TEXT NOT NULL,
            requested_provider TEXT NOT NULL,
            actual_provider TEXT,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            providers_attempted TEXT,
            status TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'live',
            observations_complete INTEGER NOT NULL DEFAULT 0,
            requested_n INTEGER NOT NULL DEFAULT 0,
            observations_n INTEGER NOT NULL DEFAULT 0,
            signals_n INTEGER NOT NULL DEFAULT 0,
            below_threshold_n INTEGER NOT NULL DEFAULT 0,
            earnings_excluded_n INTEGER NOT NULL DEFAULT 0,
            earnings_failure_n INTEGER NOT NULL DEFAULT 0,
            fetch_failure_n INTEGER NOT NULL DEFAULT 0,
            insufficient_data_n INTEGER NOT NULL DEFAULT 0,
            scoring_failure_n INTEGER NOT NULL DEFAULT 0,
            min_score INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE scan_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            status TEXT NOT NULL,
            score INTEGER,
            last_close REAL,
            volume_ratio REAL,
            rsi REAL,
            days_until_earnings INTEGER,
            reasons TEXT,
            provider TEXT,
            error_category TEXT,
            error_message TEXT
        );
    """)

    base = ("2025-01-15T15:00:00+00:00", "intraday")
    con.execute(
        "INSERT INTO scan_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("session-only", base[0], "2025-01-15", base[1], "yahoo", "yahoo", 0, "yahoo", "completed", "live", 1, 3, 3, 1, 2, 0, 0, 0, 0, 0, 40)
    )
    for t in ("A", "B", "C"):
        con.execute(
            "INSERT INTO scan_observations (session_id, ticker, status, provider) VALUES (?, ?, ?, ?)",
            ("session-only", t, "signal" if t == "A" else "below_threshold", "yahoo")
        )

    for _ in range(2):
        con.execute(
            "INSERT INTO scan_runs (run_time, timeframe, tickers_n, hits_n, provider) VALUES (?, ?, ?, ?, ?)",
            (base[0], base[1], 2, 1, "yahoo")
        )
    con.commit()
    con.close()


def test_migration_does_not_reuse_legacy_rows_for_multiple_rows_one_session(tmp_path, monkeypatch):
    db_path = str(tmp_path / "v2.db")
    _build_v2_two_rows_one_session(db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)

    store.init()

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM scan_runs").fetchall()
        assert len(rows) == 3
        legacy = [r for r in rows if r["source"] == "legacy"]
        native = [r for r in rows if r["source"] == "native"]
        assert len(legacy) == 2
        assert len(native) == 1
        for r in legacy:
            assert r["session_id"] is None
        assert native[0]["session_id"] == "session-only"
        assert native[0]["counts_complete"] == 1
