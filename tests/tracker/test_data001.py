"""Regression tests for DATA-001 / COIL-001 / COIL-002 signal-history redesign."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from tradex.screener.engine import ObservationStatus, ScanReport
from tradex.tracker import analyzer, store


def _signal_obs_row(ticker, score=60):
    return {
        "ticker": ticker,
        "status": ObservationStatus.SIGNAL.value,
        "score": score,
        "last_close": 100.0,
        "volume_ratio": 2.0,
        "rsi": 60.0,
        "days_until_earnings": None,
        "reasons": "volume surge",
        "provider": "yahoo",
        "error_category": None,
        "error_message": None,
    }


def _failure_obs_row(ticker, error, *, status=None):
    status = status or ObservationStatus.FETCH_FAILURE.value
    return {
        "ticker": ticker,
        "status": status,
        "score": None,
        "last_close": None,
        "volume_ratio": None,
        "rsi": None,
        "days_until_earnings": None,
        "reasons": None,
        "provider": None,
        "error_category": type(error).__name__,
        "error_message": str(error),
    }


def _below_threshold_obs_row(ticker, score=30, provider="yahoo"):
    return {
        "ticker": ticker,
        "status": ObservationStatus.BELOW_THRESHOLD.value,
        "score": score,
        "last_close": 100.0,
        "volume_ratio": 2.0,
        "rsi": 60.0,
        "days_until_earnings": None,
        "reasons": "below min score",
        "provider": provider,
        "error_category": None,
        "error_message": None,
    }


def _earnings_excluded_obs_row(ticker, days=3):
    return {
        "ticker": ticker,
        "status": ObservationStatus.EARNINGS_EXCLUDED.value,
        "score": None,
        "last_close": None,
        "volume_ratio": None,
        "rsi": None,
        "days_until_earnings": days,
        "reasons": None,
        "provider": None,
        "error_category": None,
        "error_message": None,
    }


def _make_report(observations: list[dict], *, requested_provider="yahoo", actual_provider=None) -> ScanReport:
    if actual_provider is None:
        actual_provider = requested_provider
    obs = pd.DataFrame(observations)
    signal_mask = obs["status"] == ObservationStatus.SIGNAL.value
    results = obs[signal_mask][[
        "ticker", "score", "last_close", "volume_ratio", "rsi",
        "days_until_earnings", "reasons", "provider",
    ]]
    if results.empty:
        results = pd.DataFrame(columns=[
            "ticker", "score", "last_close", "volume_ratio", "rsi",
            "days_until_earnings", "reasons", "provider",
        ])
    providers_attempted = (requested_provider,)
    status_values = set(obs["status"].dropna().astype(str).unique())
    scored_statuses = {ObservationStatus.SIGNAL.value, ObservationStatus.BELOW_THRESHOLD.value}
    has_scored = bool(status_values & scored_statuses)
    has_earnings_excluded = ObservationStatus.EARNINGS_EXCLUDED.value in status_values
    if has_scored:
        resolved_actual = actual_provider
    elif has_earnings_excluded:
        resolved_actual = None
    else:
        resolved_actual = None
    return ScanReport(
        results=results,
        requested_provider=requested_provider,
        actual_provider=resolved_actual,
        fallback_used=False,
        providers_attempted=providers_attempted,
        failures={},
        total_requested=len(obs),
        total_fetch_attempted=len(obs),
        total_fetch_eligible=len(obs),
        total_retries=0,
        total_fetched=len(obs) if has_scored else 0,
        total_scored=int(signal_mask.sum()),
        total_signals=len(results),
        total_below_threshold=int((obs["status"] == ObservationStatus.BELOW_THRESHOLD.value).sum()),
        total_insufficient_data=int((obs["status"] == ObservationStatus.INSUFFICIENT_DATA.value).sum()),
        total_earnings_excluded=int((obs["status"] == ObservationStatus.EARNINGS_EXCLUDED.value).sum()),
        earnings_failures={},
        fetch_failures={},
        scoring_failures={},
        attempt_log=[],
        observations=obs,
    )


def test_record_scan_persists_session_and_signal(fresh_signal_db):
    """record_scan writes session, observations, and signal rows atomically."""
    report = _make_report([_signal_obs_row("AAPL", 70)])
    scan_time = datetime(2025, 1, 15, 15, 0, tzinfo=UTC)

    session_id = store.record_scan(
        report, "intraday", 40, ["AAPL"], scan_time=scan_time
    )

    session = store.get_scan_session(session_id)
    assert session is not None
    assert session["status"] == "completed"
    assert session["signals_n"] == 1

    obs = store.get_scan_observations(session_id)
    assert len(obs) == 1
    assert obs.iloc[0]["status"] == "signal"

    with store._conn() as con:
        row = con.execute(
            "SELECT * FROM signal_history WHERE scan_session_id = ?", (session_id,)
        ).fetchone()
    assert row is not None
    assert row["ticker"] == "AAPL"
    assert row["trading_date"] == "2025-01-15"


def test_record_scan_records_failed_session(fresh_signal_db):
    """A session with all fetch failures stores a failed status and no signal rows."""
    err = ValueError("network")
    report = _make_report([_failure_obs_row("AAPL", err)])
    scan_time = datetime(2025, 1, 15, 15, 0, tzinfo=UTC)

    session_id = store.record_scan(
        report, "intraday", 40, ["AAPL"], scan_time=scan_time
    )

    session = store.get_scan_session(session_id)
    assert session["status"] == "failed"
    assert session["actual_provider"] is None
    assert session["requested_provider"] == "yahoo"
    assert session["providers_attempted"] == "yahoo"

    with store._conn() as con:
        count = con.execute(
            "SELECT COUNT(*) FROM signal_history WHERE scan_session_id = ?", (session_id,)
        ).fetchone()[0]
    assert count == 0


def test_record_scan_rejects_naive_scan_time(fresh_signal_db):
    """Naive scan_time values raise ValueError before writing."""
    report = _make_report([_signal_obs_row("AAPL")])
    naive = datetime(2025, 1, 15, 15, 0)  # noqa: DTZ001

    with pytest.raises(ValueError, match="timezone-aware"):
        store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=naive)


def test_record_scan_partial_session_status(fresh_signal_db):
    """A mixed result/failure observation set records a partial session."""
    report = _make_report([
        _signal_obs_row("AAPL", 70),
        _failure_obs_row("MSFT", ValueError("network")),
    ])
    scan_time = datetime(2025, 1, 15, 15, 0, tzinfo=UTC)

    session_id = store.record_scan(report, "intraday", 40, ["AAPL", "MSFT"], scan_time=scan_time)
    session = store.get_scan_session(session_id)
    assert session["status"] == "partial"
    assert session["signals_n"] == 1
    assert session["fetch_failure_n"] == 1


def test_record_signals_wrapper_writes_signal_and_scan_run(fresh_signal_db):
    """The legacy record_signals wrapper still populates signal_history and scan_runs."""
    results = pd.DataFrame([{
        "ticker": "AAPL",
        "score": 70,
        "last_close": 100.0,
        "volume_ratio": 2.0,
        "rsi": 60.0,
        "days_until_earnings": 5,
        "reasons": "volume surge",
        "provider": "schwab",
    }])
    store.record_signals(results, "intraday")

    with store._conn() as con:
        signal = con.execute("SELECT provider FROM signal_history").fetchone()
        run = con.execute("SELECT provider FROM scan_runs").fetchone()
    assert signal["provider"] == "schwab"
    assert run["provider"] == "schwab"


def test_init_migrates_legacy_rows_to_synthetic_sessions(tmp_path, monkeypatch):
    """An existing pre-DATA-001 database is migrated into deterministic scan sessions."""
    db_path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(store, "DB_PATH", db_path)

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
    con.execute(
        "INSERT INTO signal_history (ticker, timeframe, scan_time, score, last_close) VALUES (?, ?, ?, ?, ?)",
        ("AAPL", "intraday", "2024-01-02T14:30:00+00:00", 60, 100.0),
    )
    con.commit()
    con.close()

    store.init()

    with store._conn() as con:
        sh_cols = {c[1] for c in con.execute("PRAGMA table_info(signal_history)")}
        assert "scan_session_id" in sh_cols
        assert "trading_date" in sh_cols
        assert con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scan_sessions'").fetchone()
        assert con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scan_observations'").fetchone()

        row = con.execute("SELECT scan_session_id, trading_date, provider FROM signal_history").fetchone()
        assert row["scan_session_id"].startswith("legacy-")
        assert row["trading_date"] == "2024-01-02"

        obs = con.execute("SELECT status, provider FROM scan_observations").fetchone()
        assert obs["status"] == "signal"
        assert obs["provider"] == "unknown"


def _ny(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_coil_counts_distinct_sessions_not_scan_rows_via_record_scan(fresh_signal_db):
    """Three scans on the same trading day count as one session, not three."""
    base = _ny(2025, 1, 15, 10, 0)
    for i in range(3):
        report = _make_report([_signal_obs_row("COIL", 60)])
        store.record_scan(report, "intraday", 40, ["COIL"], scan_time=base + timedelta(minutes=i))

    coils = analyzer.detect_coils("intraday", days=600, min_appearances=2)
    assert coils.empty


def test_coil_detected_across_distinct_sessions(fresh_signal_db):
    """Two distinct trading sessions above threshold produce a coil."""
    for dt in (_ny(2025, 1, 13, 10, 0), _ny(2025, 1, 14, 10, 0)):
        report = _make_report([_signal_obs_row("COIL", 60)])
        store.record_scan(report, "intraday", 40, ["COIL"], scan_time=dt)

    coils = analyzer.detect_coils("intraday", days=600, min_appearances=2)
    assert not coils.empty
    assert coils.iloc[0]["ticker"] == "COIL"
    assert coils.iloc[0]["appearances"] == 2


def test_weekend_observations_do_not_count_as_sessions(fresh_signal_db):
    """Observations recorded on a weekend are not treated as trading sessions."""
    saturday = _ny(2025, 1, 11, 10, 0)
    sunday = _ny(2025, 1, 12, 10, 0)
    for dt in (saturday, sunday):
        report = _make_report([_signal_obs_row("COIL", 60)])
        store.record_scan(report, "intraday", 40, ["COIL"], scan_time=dt)

    daily = store.get_daily_score_history("COIL", "intraday", days=600)
    assert daily.empty
    coils = analyzer.detect_coils("intraday", days=600, min_appearances=2)
    assert coils.empty


def test_daily_score_history_returns_latest_per_session(fresh_signal_db):
    """Two scans on one trading day collapse to the latest scored observation."""
    base = _ny(2025, 1, 15, 9, 0)
    for score, offset in ((55, 0), (70, 2)):
        report = _make_report([_signal_obs_row("COIL", score)])
        store.record_scan(report, "intraday", 40, ["COIL"], scan_time=base + timedelta(hours=offset))

    daily = store.get_daily_score_history("COIL", "intraday", days=600)
    assert len(daily) == 1
    assert daily.iloc[0]["score"] == 70


def test_fading_setup_detected(fresh_signal_db):
    """A score that peaks above threshold then declines below it is flagged as fading."""
    for dt, score in (
        (_ny(2025, 1, 13, 10, 0), 70),
        (_ny(2025, 1, 14, 10, 0), 40),
    ):
        report = _make_report([_signal_obs_row("FADE", score)])
        store.record_scan(report, "intraday", 40, ["FADE"], scan_time=dt)

    fading = analyzer.detect_fading_setups("intraday", days=600, min_appearances=2)
    assert not fading.empty
    assert fading.iloc[0]["ticker"] == "FADE"


def test_observation_history_returns_all_statuses(fresh_signal_db):
    """get_observation_history returns signal and below-threshold rows."""
    report = _make_report([
        _signal_obs_row("AAPL", 70),
        {**_signal_obs_row("MSFT", 30), "status": ObservationStatus.BELOW_THRESHOLD.value},
    ])
    store.record_scan(report, "intraday", 40, ["AAPL", "MSFT"], scan_time=_ny(2025, 1, 15, 10, 0))

    history = store.get_observation_history("MSFT", "intraday", days=600)
    assert len(history) == 1
    assert history.iloc[0]["status"] == ObservationStatus.BELOW_THRESHOLD.value


def test_scan_frequency_invariance_for_coil_strength(fresh_signal_db):
    """Two scans in one session vs one scan should not inflate coil strength."""
    # Distinct day with one scan
    report = _make_report([_signal_obs_row("COIL", 60)])
    store.record_scan(report, "intraday", 40, ["COIL"], scan_time=_ny(2025, 1, 14, 10, 0))

    # Latest day with two scans
    base = _ny(2025, 1, 15, 9, 0)
    for i in range(2):
        report = _make_report([_signal_obs_row("COIL", 60)])
        store.record_scan(report, "intraday", 40, ["COIL"], scan_time=base + timedelta(minutes=i))

    coils = analyzer.detect_coils("intraday", days=600, min_appearances=2)
    assert not coils.empty
    assert coils.iloc[0]["appearances"] == 2


def test_scan_frequency_invariance_identical_trend_and_strength(fresh_signal_db, tmp_path, monkeypatch):
    """Equivalent market histories at different scan frequencies produce the same coil metrics."""
    # History A: one scan on day 1, one scan on day 2
    report = _make_report([_signal_obs_row("COIL", 60)])
    store.record_scan(report, "intraday", 40, ["COIL"], scan_time=_ny(2025, 1, 14, 10, 0))
    report = _make_report([_signal_obs_row("COIL", 65)])
    store.record_scan(report, "intraday", 40, ["COIL"], scan_time=_ny(2025, 1, 15, 11, 0))

    coils_a = analyzer.detect_coils("intraday", days=600, min_appearances=2)
    assert not coils_a.empty
    row_a = coils_a.iloc[0]

    # History B: one scan on day 1, two scans on day 2 (same latest score)
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "history_b.db"))
    store.init()
    report = _make_report([_signal_obs_row("COIL", 60)])
    store.record_scan(report, "intraday", 40, ["COIL"], scan_time=_ny(2025, 1, 14, 10, 0))
    report = _make_report([_signal_obs_row("COIL", 55)])
    store.record_scan(report, "intraday", 40, ["COIL"], scan_time=_ny(2025, 1, 15, 10, 0))
    report = _make_report([_signal_obs_row("COIL", 65)])
    store.record_scan(report, "intraday", 40, ["COIL"], scan_time=_ny(2025, 1, 15, 11, 0))

    coils_b = analyzer.detect_coils("intraday", days=600, min_appearances=2)
    assert not coils_b.empty
    row_b = coils_b.iloc[0]

    assert row_a["appearances"] == row_b["appearances"] == 2
    assert row_a["trend_direction"] == row_b["trend_direction"] == "building"
    assert row_a["coil_strength"] == row_b["coil_strength"]


def test_record_scan_persists_zero_signal_below_threshold(fresh_signal_db):
    """A scan with all below-threshold observations is persisted as a completed session."""
    report = _make_report([_below_threshold_obs_row("AAPL")])
    session_id = store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    session = store.get_scan_session(session_id)
    assert session["status"] == "completed"
    assert session["signals_n"] == 0
    assert session["below_threshold_n"] == 1
    assert session["actual_provider"] == "yahoo"


def test_record_scan_persists_all_earnings_excluded(fresh_signal_db):
    """A scan where every ticker is earnings-excluded is a completed session with NULL provider."""
    report = _make_report([_earnings_excluded_obs_row("AAPL", days=2)])
    session_id = store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    session = store.get_scan_session(session_id)
    assert session["status"] == "completed"
    assert session["earnings_excluded_n"] == 1
    assert session["actual_provider"] is None
    assert session["requested_provider"] == "yahoo"


def test_record_scan_persists_complete_provider_failure(fresh_signal_db):
    """When no provider succeeds actual_provider is NULL while requested/attempted are preserved."""
    err = ValueError("network")
    report = _make_report([_failure_obs_row("AAPL", err)])
    session_id = store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    session = store.get_scan_session(session_id)
    assert session["status"] == "failed"
    assert session["actual_provider"] is None
    assert session["requested_provider"] == "yahoo"
    assert session["providers_attempted"] == "yahoo"
    assert session["fetch_failure_n"] == 1


def test_record_scan_persists_partial_failure(fresh_signal_db):
    """A mixed signal and failure observation set is partial and keeps the actual provider."""
    report = _make_report([
        _signal_obs_row("AAPL", 70),
        _failure_obs_row("MSFT", ValueError("network")),
    ])
    session_id = store.record_scan(report, "intraday", 40, ["AAPL", "MSFT"], scan_time=_ny(2025, 1, 15, 10, 0))

    session = store.get_scan_session(session_id)
    assert session["status"] == "partial"
    assert session["actual_provider"] == "yahoo"
    assert session["signals_n"] == 1
    assert session["fetch_failure_n"] == 1


def test_record_scan_persists_earnings_source_failure(fresh_signal_db):
    """An earnings-only failure still records a failed session with no provider."""
    from tradex.screener.engine import ObservationStatus
    report = _make_report([_failure_obs_row("AAPL", ValueError("earnings down"), status=ObservationStatus.EARNINGS_FAILURE.value)])
    session_id = store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    session = store.get_scan_session(session_id)
    assert session["status"] == "failed"
    assert session["actual_provider"] is None
    assert session["earnings_failure_n"] == 1


def test_record_scan_persists_scoring_only_failure(fresh_signal_db):
    """A scoring failure after successful fetch records a partial session with the actual provider."""
    from tradex.screener.engine import ObservationStatus
    err = ValueError("scoring failed")
    obs = _failure_obs_row("AAPL", err, status=ObservationStatus.SCORING_FAILURE.value)
    obs["provider"] = "yahoo"
    report = _make_report([obs])
    session_id = store.record_scan(report, "intraday", 40, ["AAPL"], scan_time=_ny(2025, 1, 15, 10, 0))

    session = store.get_scan_session(session_id)
    assert session["status"] == "failed"
    assert session["actual_provider"] is None
    assert session["scoring_failure_n"] == 1


def test_latest_score_not_erased_by_later_same_day_failure(fresh_signal_db):
    """A later same-day failed scan does not overwrite the earlier successful score."""
    report = _make_report([_signal_obs_row("COIL", 70)])
    store.record_scan(report, "intraday", 40, ["COIL"], scan_time=_ny(2025, 1, 15, 9, 0))

    err = ValueError("network")
    report = _make_report([_failure_obs_row("COIL", err)])
    store.record_scan(report, "intraday", 40, ["COIL"], scan_time=_ny(2025, 1, 15, 10, 0))

    daily = store.get_daily_score_history("COIL", "intraday", days=600)
    assert len(daily) == 1
    assert daily.iloc[0]["score"] == 70


def test_init_migration_is_atomic_and_idempotent(tmp_path, monkeypatch):
    """A mid-migration failure rolls back; repeated init does not duplicate legacy rows."""
    db_path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(store, "DB_PATH", db_path)

    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE signal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            scan_time TEXT NOT NULL,
            score INTEGER NOT NULL,
            last_close REAL
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
    con.execute(
        "INSERT INTO signal_history (ticker, timeframe, scan_time, score, last_close) VALUES (?, ?, ?, ?, ?)",
        ("AAPL", "intraday", "2024-01-02T14:30:00+00:00", 60, 100.0),
    )
    con.commit()
    con.close()

    original_migrate = store._migrate_v0
    def failing_migrate(con):
        original_migrate(con)
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(store, "_migrate_v0", failing_migrate)
    with pytest.raises(RuntimeError, match="injected migration failure"):
        store.init()

    with sqlite3.connect(db_path) as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        assert version == 0
        assert con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scan_sessions'").fetchone() is None

    monkeypatch.setattr(store, "_migrate_v0", original_migrate)
    store.init()
    store.init()

    with store._conn() as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        assert version == 2
        sessions = con.execute("SELECT COUNT(*) FROM scan_sessions").fetchone()[0]
        observations = con.execute("SELECT COUNT(*) FROM scan_observations").fetchone()[0]
        assert sessions == 1
        assert observations == 1
