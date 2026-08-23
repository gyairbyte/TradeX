"""Tests for watcher candidate recording integration and failure isolation (MVP-ARCH-001-R5B)."""
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.candidates.store import list_candidates
from tradex.config import TradeXSettings, settings_from_mapping
from tradex.screener.engine import ScanReport
from tradex.tracker import store
from tradex.tracker.watcher import run_once


@pytest.fixture
def isolated_settings(tmp_path: Path) -> TradeXSettings:
    db_file = tmp_path / "signals.db"
    settings = settings_from_mapping({"TRADEX_DB_PATH": str(db_file)})
    store.init(db_path=str(db_file), settings=settings)
    return settings


def test_watcher_creates_candidates_after_scan(isolated_settings: TradeXSettings, monkeypatch):
    """Confirm watcher.run_once creates CandidateDossiers for scorable observations."""
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)

    obs_data = [
        {
            "ticker": "AAPL",
            "status": "signal",
            "score": 75,
            "last_close": 150.0,
            "volume_ratio": 1.5,
            "rsi": 60.0,
            "days_until_earnings": 10,
            "reasons": "Bullish",
            "provider": "schwab",
        },
        {
            "ticker": "MSFT",
            "status": "below_threshold",
            "score": 25,
            "last_close": 300.0,
            "volume_ratio": 0.8,
            "rsi": 40.0,
            "days_until_earnings": 30,
            "reasons": "Weak volume",
            "provider": "schwab",
        },
    ]
    obs_df = pd.DataFrame(obs_data)
    results_df = obs_df[obs_df["status"] == "signal"].copy()

    mock_report = MagicMock(spec=ScanReport)
    mock_report.observations = obs_df
    mock_report.results = results_df
    mock_report.requested_provider = "schwab"
    mock_report.actual_provider = "schwab"
    mock_report.fallback_used = False
    mock_report.providers_attempted = ("schwab",)
    mock_report.failures = {}
    mock_report.earnings_failures = {}
    mock_report.fetch_failures = {}
    mock_report.scoring_failures = {}
    mock_report.total_requested = 2
    mock_report.total_fetch_eligible = 2
    mock_report.total_fetch_attempted = 2
    mock_report.total_fetched = 2
    mock_report.total_scored = 2
    mock_report.total_signals = 1
    mock_report.total_below_threshold = 1
    mock_report.total_insufficient_data = 0
    mock_report.total_earnings_excluded = 0
    mock_report.total_retries = 0
    mock_report.attempt_log = []

    monkeypatch.setattr("tradex.tracker.watcher.screener_run_with_report", lambda *a, **kw: mock_report)
    monkeypatch.setattr("tradex.tracker.watcher._check_alerts", lambda *a, **kw: [])

    # Run watcher run_once
    run_once(
        tickers=["AAPL", "MSFT"],
        timeframe="intraday",
        now=dt,
        settings=isolated_settings,
    )

    # Check that scan audit is recorded
    sessions = store.get_recent_scan_sessions(settings=isolated_settings)
    assert len(sessions) == 1
    session_id = sessions.iloc[0]["session_id"]

    observations = store.get_scan_observations(session_id, settings=isolated_settings)
    assert len(observations) == 2

    # Check that CandidateDossiers are persisted for both AAPL and MSFT
    candidates = list_candidates(settings=isolated_settings)
    assert len(candidates) == 2
    symbols = {c.symbol for c in candidates}
    assert symbols == {"AAPL", "MSFT"}


def test_watcher_candidate_failure_isolation(isolated_settings: TradeXSettings, monkeypatch, capsys):
    """Test that candidate service failure does NOT crash watcher or prevent scan audit."""
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)

    obs_df = pd.DataFrame([
        {
            "ticker": "AAPL",
            "status": "signal",
            "score": 75,
            "last_close": 150.0,
            "volume_ratio": 1.5,
            "rsi": 60.0,
            "days_until_earnings": 10,
            "reasons": "Bullish",
            "provider": "schwab",
        }
    ])
    results_df = obs_df.copy()

    mock_report = MagicMock(spec=ScanReport)
    mock_report.observations = obs_df
    mock_report.results = results_df
    mock_report.requested_provider = "schwab"
    mock_report.actual_provider = "schwab"
    mock_report.fallback_used = False
    mock_report.providers_attempted = ("schwab",)
    mock_report.failures = {}
    mock_report.earnings_failures = {}
    mock_report.fetch_failures = {}
    mock_report.scoring_failures = {}
    mock_report.total_requested = 1
    mock_report.total_fetch_eligible = 1
    mock_report.total_fetch_attempted = 1
    mock_report.total_fetched = 1
    mock_report.total_scored = 1
    mock_report.total_signals = 1
    mock_report.total_below_threshold = 0
    mock_report.total_insufficient_data = 0
    mock_report.total_earnings_excluded = 0
    mock_report.total_retries = 0
    mock_report.attempt_log = []

    monkeypatch.setattr("tradex.tracker.watcher.screener_run_with_report", lambda *a, **kw: mock_report)
    monkeypatch.setattr("tradex.tracker.watcher._check_alerts", lambda *a, **kw: [])

    # Force candidate service to raise an unhandled error
    def faulty_record_session_candidates(*args, **kwargs):
        raise RuntimeError("Synthetic failure in candidate recording service")

    monkeypatch.setattr("tradex.candidates.service.record_session_candidates", faulty_record_session_candidates)

    # run_once must NOT raise
    run_once(
        tickers=["AAPL"],
        timeframe="intraday",
        now=dt,
        settings=isolated_settings,
    )

    captured = capsys.readouterr()
    assert "Candidate shadow aggregation failed" in captured.out

    # Scan audit was still persisted
    sessions = store.get_recent_scan_sessions(settings=isolated_settings)
    assert len(sessions) == 1
