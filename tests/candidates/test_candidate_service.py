"""Tests for candidate service orchestration and persistence (MVP-ARCH-001-R5B)."""
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.candidates.models import (
    CandidateDimension,
    ReasonPolarity,
    SecurityIdentityStatus,
)
from tradex.candidates.service import (
    CandidateService,
    record_session_candidates,
)
from tradex.candidates.store import get_candidate_dossier, list_candidates
from tradex.config import TradeXSettings, settings_from_mapping
from tradex.screener.engine import ScanReport
from tradex.tracker.store import init


@pytest.fixture
def isolated_settings(tmp_path: Path) -> TradeXSettings:
    db_file = tmp_path / "signals.db"
    settings = settings_from_mapping({"TRADEX_DB_PATH": str(db_file)})
    init(db_path=str(db_file), settings=settings)
    return settings


def _build_mock_scan_report(observations: list[dict], requested_provider: str = "schwab", actual_provider: str = "schwab", fallback: bool = False) -> ScanReport:
    obs_df = pd.DataFrame(observations)
    report = MagicMock(spec=ScanReport)
    report.observations = obs_df
    report.requested_provider = requested_provider
    report.actual_provider = actual_provider
    report.fallback_used = fallback
    report.total_requested = len(observations)
    return report


def test_service_creates_dossiers_for_scorable_statuses_only(isolated_settings: TradeXSettings):
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    observations = [
        # Scorable: SIGNAL
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
        # Scorable: BELOW_THRESHOLD
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
        # Non-scorable: FETCH_FAILURE
        {
            "ticker": "FAIL1",
            "status": "fetch_failure",
            "score": None,
            "last_close": None,
            "volume_ratio": None,
            "rsi": None,
            "days_until_earnings": None,
            "reasons": None,
            "provider": None,
        },
        # Non-scorable: INSUFFICIENT_DATA
        {
            "ticker": "FAIL2",
            "status": "insufficient_data",
            "score": None,
            "last_close": None,
            "volume_ratio": None,
            "rsi": None,
            "days_until_earnings": None,
            "reasons": None,
            "provider": None,
        },
        # Non-scorable: EARNINGS_EXCLUDED
        {
            "ticker": "EXCL",
            "status": "earnings_excluded",
            "score": None,
            "last_close": None,
            "volume_ratio": None,
            "rsi": None,
            "days_until_earnings": 1,
            "reasons": None,
            "provider": None,
        },
    ]
    report = _build_mock_scan_report(observations)
    session_id = "session-test-001"

    result = record_session_candidates(
        report=report,
        session_id=session_id,
        timeframe="intraday",
        scan_time=dt,
        settings=isolated_settings,
    )

    assert result.session_id == session_id
    assert result.scorable_count == 2
    assert result.dossiers_persisted == 2
    assert result.dossiers_replayed == 0
    assert result.failures == {}

    # Get by list_candidates
    candidates = list_candidates(settings=isolated_settings)
    assert len(candidates) == 2
    symbols = {c.symbol for c in candidates}
    assert symbols == {"AAPL", "MSFT"}

    for c in candidates:
        dossier = get_candidate_dossier(c.candidate_id, settings=isolated_settings)
        assert dossier is not None
        assert dossier.snapshot.trading_date == "2026-08-21"
        assert dossier.snapshot.security_identity_status == SecurityIdentityStatus.UNKNOWN
        assert len(dossier.evaluations) == 1
        assert dossier.evaluations[0].evaluator_id == "shadow_observation_evaluator"
        assert dossier.evaluations[0].evidence_state == "exploratory"

        # Check dimensions: context and data_confidence only
        dims = dossier.evaluations[0].dimensions
        assert set(dims.keys()) == {CandidateDimension.CONTEXT.value, CandidateDimension.DATA_CONFIDENCE.value}

        # Check reasons
        assert len(dossier.reasons) > 0
        for r in dossier.reasons:
            assert r.polarity == ReasonPolarity.NEUTRAL


def test_service_idempotent_replay(isolated_settings: TradeXSettings):
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    observations = [
        {
            "ticker": "NVDA",
            "status": "signal",
            "score": 80,
            "last_close": 110.0,
            "volume_ratio": 2.1,
            "rsi": 65.0,
            "days_until_earnings": 45,
            "reasons": "Breakout",
            "provider": "schwab",
        }
    ]
    report = _build_mock_scan_report(observations)
    session_id = "session-replay-001"

    # First run: 1 persisted
    res1 = record_session_candidates(
        report=report,
        session_id=session_id,
        timeframe="intraday",
        scan_time=dt,
        settings=isolated_settings,
    )
    assert res1.dossiers_persisted == 1
    assert res1.dossiers_replayed == 0

    # Second run with exact same report: 1 replayed
    res2 = record_session_candidates(
        report=report,
        session_id=session_id,
        timeframe="intraday",
        scan_time=dt,
        settings=isolated_settings,
    )
    assert res2.dossiers_persisted == 0
    assert res2.dossiers_replayed == 1
    assert res2.failures == {}

    # Store still has exactly 1 candidate
    candidates = list_candidates(settings=isolated_settings)
    assert len(candidates) == 1


def test_service_zero_provider_calls(isolated_settings: TradeXSettings, monkeypatch):
    """Prove that CandidateService makes zero new provider/network calls."""
    # Monkeypatch fetcher functions to raise if called
    def fail_if_called(*args, **kwargs):
        pytest.fail("Provider fetch function was unexpectedly called during candidate aggregation")

    monkeypatch.setattr("tradex.data.fetcher.fetch", fail_if_called)
    monkeypatch.setattr("tradex.data.fetcher.fetch_multi", fail_if_called)
    monkeypatch.setattr("tradex.data.fetcher.fetch_multi_report", fail_if_called)

    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    observations = [
        {
            "ticker": "TSLA",
            "status": "signal",
            "score": 60,
            "last_close": 200.0,
            "volume_ratio": 1.2,
            "rsi": 50.0,
            "days_until_earnings": 14,
            "reasons": "Momentum",
            "provider": "schwab",
        }
    ]
    report = _build_mock_scan_report(observations)
    session_id = "session-zero-call"

    result = record_session_candidates(
        report=report,
        session_id=session_id,
        timeframe="intraday",
        scan_time=dt,
        settings=isolated_settings,
    )
    assert result.dossiers_persisted == 1


def test_service_per_candidate_failure_isolation(isolated_settings: TradeXSettings, monkeypatch):
    """Test that a failure in one candidate does not block other candidates in the same session."""
    service = CandidateService()
    dt = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)

    original_process = service.process_scorable_observation

    def faulty_process(observation, session_id, timeframe, scan_time, **kwargs):
        obs_dict = observation.to_dict() if isinstance(observation, pd.Series) else dict(observation)
        if obs_dict.get("ticker") == "BROKEN":
            raise RuntimeError("Synthetic failure for BROKEN ticker")
        return original_process(observation, session_id, timeframe, scan_time, **kwargs)

    monkeypatch.setattr(service, "process_scorable_observation", faulty_process)

    observations = [
        {
            "ticker": "GOOD1",
            "status": "signal",
            "score": 70,
            "last_close": 100.0,
            "volume_ratio": 1.1,
            "rsi": 55.0,
            "days_until_earnings": None,
            "reasons": None,
            "provider": "schwab",
        },
        {
            "ticker": "BROKEN",
            "status": "signal",
            "score": 50,
            "last_close": 50.0,
            "volume_ratio": 1.0,
            "rsi": 50.0,
            "days_until_earnings": None,
            "reasons": None,
            "provider": "schwab",
        },
        {
            "ticker": "GOOD2",
            "status": "below_threshold",
            "score": 30,
            "last_close": 20.0,
            "volume_ratio": 0.5,
            "rsi": 40.0,
            "days_until_earnings": None,
            "reasons": None,
            "provider": "schwab",
        },
    ]
    report = _build_mock_scan_report(observations)
    session_id = "session-isolation-001"

    result = service.record_session_candidates(
        report=report,
        session_id=session_id,
        timeframe="intraday",
        scan_time=dt,
        settings=isolated_settings,
    )

    assert result.scorable_count == 3
    assert result.dossiers_persisted == 2
    assert result.failed_symbols == ("BROKEN",)
    assert "Synthetic failure" in result.failures["BROKEN"]

    # Verify both GOOD1 and GOOD2 exist in store
    candidates = list_candidates(settings=isolated_settings)
    assert len(candidates) == 2
    symbols = {c.symbol for c in candidates}
    assert symbols == {"GOOD1", "GOOD2"}
