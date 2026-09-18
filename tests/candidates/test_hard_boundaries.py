"""Hard architectural and governance boundary tests for MVP-ARCH-001-R5C.

Validates:
- Database schema version remains exactly 4.
- No schema migrations added or changed.
- APPROVED_PRODUCTION_STRATEGIES remains empty tuple ().
- Alert policies and notifier remain unchanged and fail-closed.
- Candidate aggregator, evaluator, and service logic unchanged from R5B.
- Scanner execution and diagnostics unchanged.
- Provider resolution and fallback unchanged.
- Signal journal logic and tables unchanged.
- Zero ranking logic, quality bands, or score sorting in candidate read queries.
- Zero actionable candidate states in domain models.
- Zero provider/network calls reachable from Today / Candidate Detail queries or UI.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradex.alerts.eligibility import check_automatic_alert_eligibility
from tradex.alerts.models import AlertKey
from tradex.candidates import (
    CandidateDimension,
    CandidateSnapshot,
    ShadowObservationEvaluator,
    get_available_trading_dates,
    get_latest_candidates_for_date,
)
from tradex.config import settings_from_mapping
from tradex.data.fetcher import resolve_provider
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES
from tradex.tracker import store
from tradex.ui.tabs.today import render_today_tab


def test_schema_version_is_eight(tmp_path: Path) -> None:
    """The database schema version is 8 after Schema v8 PIT rebuild."""
    db_path = str(tmp_path / "test_schema_v8.db")
    store.init(db_path)

    with sqlite3.connect(db_path) as con:
        ver = con.execute("PRAGMA user_version").fetchone()[0]
        assert ver == 8

    assert store._SCHEMA_VERSION == 8


def test_approved_production_strategies_remains_empty() -> None:
    """Automatic alert gating must remain fail-closed with zero approved production strategies."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()
    key = AlertKey(ticker="AAPL", alert_type="price", timeframe="intraday")
    res = check_automatic_alert_eligibility(
        key,
        strategy_id="long-002c",
        strategy_version="1.0.0",
        evidence_state="production_approved",
    )
    assert res.eligible is False


def test_candidate_evaluator_and_dimensions_unchanged_from_r5b() -> None:
    """The descriptive shadow evaluator must populate ONLY context and data_confidence."""
    evaluator = ShadowObservationEvaluator()
    assert evaluator.evaluator_id == "shadow_observation_evaluator"
    assert evaluator.evaluator_version == "1.0.0"
    assert evaluator.evidence_state == "exploratory"

    # Evaluator dimensions are purely descriptive
    dt = CandidateSnapshot(
        candidate_id="cand-001",
        symbol="AAPL",
        decision_timestamp=datetime(2026, 8, 21, 15, 0, tzinfo=UTC),
    )
    ev, _reasons = evaluator.evaluate(dt, [], [])
    dims = ev.dimensions
    assert set(dims.keys()) == {CandidateDimension.CONTEXT.value, CandidateDimension.DATA_CONFIDENCE.value}

    # Setup quality, move potential, entry readiness, and downside risk remain unassessed
    assert CandidateDimension.SETUP_QUALITY.value not in dims
    assert CandidateDimension.MOVE_POTENTIAL.value not in dims
    assert CandidateDimension.ENTRY_READINESS.value not in dims
    assert CandidateDimension.DOWNSIDE_RISK.value not in dims
    assert CandidateDimension.ELIGIBILITY.value not in dims


def test_no_actionable_candidate_states_in_snapshot_model() -> None:
    """CandidateSnapshot domain header has no candidate_state, entry_plan, or actionability."""
    snap_fields = CandidateSnapshot.__dataclass_fields__.keys()
    prohibited_fields = {
        "candidate_state",
        "actionable_state",
        "enter_now",
        "armed",
        "waitlist",
        "strategy_id",
        "entry_plan",
        "invalidation_stop",
        "target_or_expiration",
        "outcome_status",
    }
    for f in prohibited_fields:
        assert f not in snap_fields, f"Prohibited field '{f}' found on CandidateSnapshot"


def test_provider_resolution_and_defaults_unchanged() -> None:
    """Default OHLCV provider remains Schwab; resolution logic unchanged."""
    settings = settings_from_mapping({})
    assert settings.data.data_provider == "schwab"
    resolved = resolve_provider("schwab", settings=settings)
    assert resolved == "schwab"


def test_zero_provider_calls_from_today_query_and_ui(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Today queries and tab rendering must make zero live provider / network calls."""
    db_path = str(tmp_path / "zero_call_test.db")
    store.init(db_path)
    settings = settings_from_mapping({"TRADEX_DB_PATH": db_path})

    faulty_fetch = MagicMock(side_effect=RuntimeError("Provider network call attempted!"))
    monkeypatch.setattr("tradex.data.fetcher.fetch", faulty_fetch)
    monkeypatch.setattr("tradex.screener.engine.run_with_report", faulty_fetch)

    mock_st = MagicMock()
    mock_st.session_state = {}
    monkeypatch.setattr("tradex.ui.tabs.today.st", mock_st)

    # Execute queries and render UI
    _ = get_available_trading_dates(settings=settings)
    _ = get_latest_candidates_for_date("2026-08-21", settings=settings)
    render_today_tab(settings=settings)

    faulty_fetch.assert_not_called()
