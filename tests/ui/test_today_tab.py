"""Unit and regression tests for Today & Candidate Detail UI tab (MVP-ARCH-001-R5C).

Tests verify:
- Truthful Today overview presentation ("Market Observations").
- Required columns present (Symbol, Legacy Observation, Observed, Observed Close, Provider, Data Completeness, Snapshots).
- Prohibited columns absent (Legacy Scanner Score, RSI, Volume Ratio, Days Until Earnings, Ranking).
- Status labels ("Signal (Legacy Heuristic)", "Below Threshold (Legacy)").
- In-place Candidate Detail drill-down and Back navigation.
- Persisted PIT facts, legacy score with disclaimer, raw reasons, context dimension, data confidence, missing data records, and snapshot history in detail.
- Zero network/provider calls and zero database writes.
- Truthful empty states and distinct DB read error states.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.candidates import (
    CandidateDimension,
    CandidateDossier,
    CandidateEvaluation,
    CandidateEvidence,
    CandidateMissingData,
    CandidateReason,
    CandidateSnapshot,
    MissingDataStatus,
    ReasonPolarity,
    ReasonSeverity,
    SecurityIdentityStatus,
    record_candidate_dossier,
)
from tradex.config import TradeXSettings, settings_from_mapping
from tradex.tracker import store
from tradex.ui.tabs.today import (
    _render_candidate_detail,
    _render_today_overview,
    render_today_tab,
)


@pytest.fixture
def isolated_today_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, TradeXSettings]:
    db_path = str(tmp_path / "today_ui_test.db")
    monkeypatch.setattr(store, "DB_PATH", db_path)
    store.init(db_path)

    settings = settings_from_mapping(
        {
            "TRADEX_DB_PATH": db_path,
            "TRADEX_WATCHLISTS_DB_PATH": str(tmp_path / "watchlists.db"),
            "TRADEX_WEIGHTS_PATH": str(tmp_path / "weights.json"),
            "TRADEX_FP_DB": str(tmp_path / "fingerprints.db"),
            "TRADEX_EARNINGS_CACHE_PATH": str(tmp_path / "earnings_cache.db"),
            "ALERT_STATE_PATH": str(tmp_path / "alerts.db"),
        }
    )
    return db_path, settings


def _seed_sample_candidates(db_path: str) -> None:
    dt1 = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    dt2 = datetime(2026, 8, 21, 15, 45, tzinfo=UTC)

    # AAPL - Signal
    snap_aapl = CandidateSnapshot(
        candidate_id="cand-aapl-01",
        symbol="AAPL",
        decision_timestamp=dt1,
        contract_version=1,
        trading_date="2026-08-21",
        security_identity_version="sec-v1",
        security_identity_status=SecurityIdentityStatus.KNOWN,
    )
    evid_aapl = CandidateEvidence(
        evidence_id="evid-aapl-01",
        candidate_id="cand-aapl-01",
        evidence_type="screener_observation",
        source_ref_type="scan_session",
        source_ref_id="session-scan-01",
        provider="schwab",
        observed_at=dt1,
        metadata={
            "observation_status": "signal",
            "legacy_heuristic_score": 85,
            "last_close": 150.25,
            "volume_ratio": 2.45,
            "rsi": 62.3,
            "days_until_earnings": 12,
            "reasons": "Volume surge > 2x | RSI momentum in sweet spot",
            "timeframe": "intraday",
        },
    )
    eval_aapl = CandidateEvaluation(
        evaluation_id="eval-aapl-01",
        candidate_id="cand-aapl-01",
        evaluator_id="shadow_observation_evaluator",
        evaluator_version="1.0.0",
        evidence_state="exploratory",
        dimensions={
            CandidateDimension.CONTEXT.value: {
                "evidence_types": ["screener_observation"],
                "observation_status": "signal",
                "timeframe": "intraday",
                "days_until_earnings": 12,
            },
            CandidateDimension.DATA_CONFIDENCE.value: {
                "actual_provider": "schwab",
                "requested_provider": "schwab",
                "fallback_used": False,
                "missing_inputs_count": 0,
                "missing_inputs": [],
            },
        },
    )
    reas_aapl = CandidateReason(
        reason_id="reas-aapl-01",
        candidate_id="cand-aapl-01",
        evaluation_id="eval-aapl-01",
        dimension=CandidateDimension.CONTEXT,
        reason_code="PRIMARY_OBSERVATION_CAPTURED",
        human_text="Primary screener observation recorded on intraday timeframe.",
        polarity=ReasonPolarity.NEUTRAL,
        severity=ReasonSeverity.INFO,
        source_evidence_id="evid-aapl-01",
    )
    dossier_aapl = CandidateDossier(
        snapshot=snap_aapl,
        evaluations=(eval_aapl,),
        evidence=(evid_aapl,),
        reasons=(reas_aapl,),
        missing_data=(),
    )
    record_candidate_dossier(dossier_aapl, db_path)

    # MSFT - Below Threshold with missing RSI and fallback provider
    snap_msft = CandidateSnapshot(
        candidate_id="cand-msft-01",
        symbol="MSFT",
        decision_timestamp=dt2,
        contract_version=1,
        trading_date="2026-08-21",
        security_identity_version="sec-v1",
        security_identity_status=SecurityIdentityStatus.KNOWN,
    )
    evid_msft = CandidateEvidence(
        evidence_id="evid-msft-01",
        candidate_id="cand-msft-01",
        evidence_type="screener_observation",
        source_ref_type="scan_session",
        source_ref_id="session-scan-02",
        provider="yahoo",
        observed_at=dt2,
        metadata={
            "observation_status": "below_threshold",
            "legacy_heuristic_score": 35,
            "last_close": 310.50,
            "volume_ratio": 0.85,
            "rsi": None,
            "days_until_earnings": None,
            "reasons": "Below minimum score threshold",
            "timeframe": "intraday",
        },
    )
    eval_msft = CandidateEvaluation(
        evaluation_id="eval-msft-01",
        candidate_id="cand-msft-01",
        evaluator_id="shadow_observation_evaluator",
        evaluator_version="1.0.0",
        evidence_state="exploratory",
        dimensions={
            CandidateDimension.CONTEXT.value: {
                "evidence_types": ["screener_observation"],
                "observation_status": "below_threshold",
                "timeframe": "intraday",
                "days_until_earnings": None,
            },
            CandidateDimension.DATA_CONFIDENCE.value: {
                "actual_provider": "yahoo",
                "requested_provider": "schwab",
                "fallback_used": True,
                "missing_inputs_count": 1,
                "missing_inputs": ["rsi"],
            },
        },
    )
    miss_msft = CandidateMissingData(
        record_id="miss-msft-rsi",
        candidate_id="cand-msft-01",
        evaluation_id="eval-msft-01",
        input_name="rsi",
        data_family="indicator",
        status=MissingDataStatus.UNKNOWN,
        detail="RSI missing from observation",
        provider="yahoo",
        observed_at=dt2,
    )
    dossier_msft = CandidateDossier(
        snapshot=snap_msft,
        evaluations=(eval_msft,),
        evidence=(evid_msft,),
        reasons=(),
        missing_data=(miss_msft,),
    )
    record_candidate_dossier(dossier_msft, db_path)


# ── Test 1: Empty state when no candidates exist ─────────────────────────────
def test_today_overview_empty_state(isolated_today_db, monkeypatch):
    _, settings = isolated_today_db

    mock_st = MagicMock()
    mock_st.session_state = {}

    monkeypatch.setattr("tradex.ui.tabs.today.st", mock_st)

    _render_today_overview(settings=settings)

    mock_st.subheader.assert_called_with("Today — Market Observations")
    info_texts = [c.args[0] for c in mock_st.info.call_args_list if c.args]
    assert any("No market-observation snapshots have been captured yet" in text for text in info_texts)


# ── Test 2: Overview rendering with populated candidates ──────────────────────
def test_today_overview_populated(isolated_today_db, monkeypatch):
    db_path, settings = isolated_today_db
    _seed_sample_candidates(db_path)

    mock_st = MagicMock()
    mock_st.session_state = {}

    def _selectbox(label, options, **kwargs):
        if options:
            return options[0]
        return None

    def _columns(spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        return [MagicMock() for _ in range(n)]

    mock_st.selectbox.side_effect = _selectbox
    mock_st.columns.side_effect = _columns
    mock_st.text_input.return_value = ""

    monkeypatch.setattr("tradex.ui.tabs.today.st", mock_st)

    _render_today_overview(settings=settings)

    mock_st.subheader.assert_called_with("Today — Market Observations")

    # Verify dataframe display call
    mock_st.dataframe.assert_called_once()
    df_arg = mock_st.dataframe.call_args[0][0]
    assert isinstance(df_arg, pd.DataFrame)
    assert len(df_arg) == 2

    columns = list(df_arg.columns)
    # Required columns present
    assert "Symbol" in columns
    assert "Legacy Observation" in columns
    assert "Observed" in columns
    assert "Observed Close" in columns
    assert "Provider" in columns
    assert "Data Completeness" in columns
    assert "Snapshots" in columns

    # Prohibited columns strictly absent from Today table
    assert "Legacy Scanner Score" not in columns
    assert "Score" not in columns
    assert "score" not in columns
    assert "RSI" not in columns
    assert "rsi" not in columns
    assert "Volume Ratio" not in columns
    assert "Vol Ratio" not in columns
    assert "Days Until Earnings" not in columns
    assert "Earnings In" not in columns
    assert "reasons" not in columns
    assert "Rank" not in columns
    assert "candidate_id" not in columns

    # Verify status labels
    obs_labels = list(df_arg["Legacy Observation"])
    assert "Signal (Legacy Heuristic)" in obs_labels
    assert "Below Threshold (Legacy)" in obs_labels

    # Verify provider fallback formatting
    prov_labels = list(df_arg["Provider"])
    assert "schwab" in prov_labels
    assert "yahoo · Fallback" in prov_labels

    # Verify completeness
    comp_labels = list(df_arg["Data Completeness"])
    assert "Complete" in comp_labels
    assert "1 missing" in comp_labels


# ── Test 3: Prohibited trading CTAs absent from Today overview & detail ───────
def test_no_trading_ctas_in_rendered_ui(isolated_today_db, monkeypatch):
    db_path, settings = isolated_today_db
    _seed_sample_candidates(db_path)

    mock_st = MagicMock()
    mock_st.session_state = {}

    def _columns(spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        return [MagicMock() for _ in range(n)]

    mock_st.columns.side_effect = _columns
    mock_st.selectbox.side_effect = lambda label, options, **kwargs: options[0] if options else None
    mock_st.text_input.return_value = ""

    monkeypatch.setattr("tradex.ui.tabs.today.st", mock_st)

    # Render overview
    _render_today_overview(settings=settings)

    # Render detail
    _render_candidate_detail("cand-aapl-01", settings=settings)

    # Collect all text strings passed to streamlit methods
    all_texts: list[str] = []
    for call in mock_st.mock_calls:
        for arg in call.args:
            if isinstance(arg, str):
                all_texts.append(arg)
        for val in call.kwargs.values():
            if isinstance(val, str):
                all_texts.append(val)

    combined_text = " ".join(all_texts).lower()

    # Check all button labels invoked
    button_labels = [c.args[0] for c in mock_st.button.call_args_list if c.args]
    for label in button_labels:
        assert label in {"View Detail", "← Back to Today"}, f"Unexpected button label: {label!r}"

    # Prohibited actionability CTAs and recommendation buttons
    prohibited_actions = [
        "buy now",
        "sell now",
        "trade now",
        "enter now",
        "armed",
        "waitlist",
        "set stop",
        "set target",
        "alert me",
        "add to trade",
        "watch closely",
    ]
    for b in prohibited_actions:
        assert b not in combined_text, f"Found prohibited trading CTA: {b!r}"


# ── Test 4: Candidate Detail in-place rendering ──────────────────────────────
def test_candidate_detail_rendering(isolated_today_db, monkeypatch):
    db_path, settings = isolated_today_db
    _seed_sample_candidates(db_path)

    mock_st = MagicMock()
    mock_st.session_state = {"today_selected_candidate_id": "cand-aapl-01"}

    def _columns(spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        return [MagicMock() for _ in range(n)]

    mock_st.columns.side_effect = _columns
    mock_st.button.return_value = False

    monkeypatch.setattr("tradex.ui.tabs.today.st", mock_st)

    render_today_tab(settings=settings)

    # Header check
    mock_st.subheader.assert_called_with("Candidate Detail — AAPL")

    # Mandatory disclaimer notice check
    info_calls = [c.args[0] for c in mock_st.info.call_args_list if c.args]
    assert any("Point-in-time research observation" in text for text in info_calls)

    # Score disclaimer text check
    markdown_calls = [c.args[0] for c in mock_st.markdown.call_args_list if c.args]
    assert any("Legacy Scanner Score" in text for text in markdown_calls)
    assert any("Unvalidated heuristic discovery score" in text for text in markdown_calls)

    # Reasons rendered
    assert any("Volume surge > 2x" in text for text in markdown_calls)


# ── Test 5: Candidate Detail back navigation ─────────────────────────────────
def test_candidate_detail_back_navigation(isolated_today_db, monkeypatch):
    db_path, settings = isolated_today_db
    _seed_sample_candidates(db_path)

    session_state = {"today_selected_candidate_id": "cand-aapl-01"}
    mock_st = MagicMock()
    mock_st.session_state = session_state

    def _button(label, **kwargs):
        return "Back to Today" in label

    mock_st.button.side_effect = _button

    monkeypatch.setattr("tradex.ui.tabs.today.st", mock_st)

    _render_candidate_detail("cand-aapl-01", settings=settings)

    # Back button clicked -> clears selected candidate and calls rerun
    assert session_state["today_selected_candidate_id"] is None
    mock_st.rerun.assert_called_once()


# ── Test 6: Zero provider calls during UI rendering ──────────────────────────
def test_ui_rendering_makes_zero_provider_calls(isolated_today_db, monkeypatch):
    db_path, settings = isolated_today_db
    _seed_sample_candidates(db_path)

    faulty_fetch = MagicMock(side_effect=RuntimeError("Live fetch forbidden in read UI!"))
    monkeypatch.setattr("tradex.data.fetcher.fetch", faulty_fetch)
    monkeypatch.setattr("tradex.screener.engine.run_with_report", faulty_fetch)

    mock_st = MagicMock()
    mock_st.session_state = {}

    def _columns(spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        return [MagicMock() for _ in range(n)]

    mock_st.columns.side_effect = _columns
    mock_st.selectbox.side_effect = lambda label, options, **kwargs: options[0] if options else None
    mock_st.text_input.return_value = ""

    monkeypatch.setattr("tradex.ui.tabs.today.st", mock_st)

    # Render overview & detail
    _render_today_overview(settings=settings)
    _render_candidate_detail("cand-aapl-01", settings=settings)

    faulty_fetch.assert_not_called()


# ── Test 7: Zero database writes during UI rendering ─────────────────────────
def test_ui_rendering_performs_zero_writes(isolated_today_db, monkeypatch):
    db_path, settings = isolated_today_db
    _seed_sample_candidates(db_path)

    with store._conn(db_path=Path(db_path)) as con:
        candidates_before = con.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]

    mock_st = MagicMock()
    mock_st.session_state = {}

    def _columns(spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        return [MagicMock() for _ in range(n)]

    mock_st.columns.side_effect = _columns
    mock_st.selectbox.side_effect = lambda label, options, **kwargs: options[0] if options else None
    mock_st.text_input.return_value = ""

    monkeypatch.setattr("tradex.ui.tabs.today.st", mock_st)

    _render_today_overview(settings=settings)
    _render_candidate_detail("cand-aapl-01", settings=settings)

    with store._conn(db_path=Path(db_path)) as con:
        candidates_after = con.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]

    assert candidates_before == candidates_after == 2


# ── Test 8: Database error handled gracefully in UI ──────────────────────────
def test_ui_handles_db_read_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bad_db = str(tmp_path / "nonexistent" / "bad.db")
    settings = settings_from_mapping({"TRADEX_DB_PATH": bad_db})

    mock_st = MagicMock()
    mock_st.session_state = {}

    monkeypatch.setattr("tradex.ui.tabs.today.st", mock_st)

    _render_today_overview(settings=settings)

    # Should render st.error and not crash
    mock_st.error.assert_called_once()
    err_text = mock_st.error.call_args[0][0]
    assert "Failed to read market observation history" in err_text
