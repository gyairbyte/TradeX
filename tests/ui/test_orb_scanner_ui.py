"""Deterministic tests for the ORB Market-Wide Scanner UI (DAYTRADE-003F).

Tests:
- No provider calls or scan execution before explicit user action (button click)
- Scan Market button triggers market scan execution
- Provenance and coverage metrics rendering (Discovered, Evaluated, Eligible, As-Of Time)
- Top 20 Candidates table rendering with directions, breakout levels, theoretical stop offsets
- Setup explanations showing why stocks qualified and hold their ranks
- Exclusions and data quality audit view with categories and reasons
- IEX versus SIP feed disclosures
- Time-gated scan error display
- Mode selector preserving Synthetic Demo and Upload JSON modes
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pytest

from tradex.config import settings_from_mapping
from tradex.research.daytrade_orb.models import Direction, OrderStatus
from tradex.research.daytrade_orb.scanner import (
    CandidatePreviewRow,
    MarketScanResult,
)


@pytest.fixture
def fake_scanner_st():
    """Return a deterministic Streamlit MagicMock for testing scanner UI."""
    st = MagicMock(name="streamlit")
    st.__version__ = "0.0.0"
    st.session_state = {}
    st.columns.side_effect = lambda n: [MagicMock() for _ in range(n)]
    st.expander.return_value.__enter__ = MagicMock()
    st.expander.return_value.__exit__ = MagicMock()
    st.empty.return_value = MagicMock()
    st.spinner.return_value.__enter__ = MagicMock()
    st.spinner.return_value.__exit__ = MagicMock()
    st.radio.return_value = "Market-Wide Live Discovery"
    st.button.return_value = False
    return st


@pytest.fixture
def scanner_ui_module(fake_scanner_st, monkeypatch):
    """Import orb_preview tab fresh with mocked Streamlit."""
    mod_name = "tradex.ui.tabs.orb_preview"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_scanner_st)
    return importlib.import_module(mod_name)


def test_no_provider_calls_before_explicit_user_action(scanner_ui_module, fake_scanner_st, monkeypatch):
    """Rendering the tab does NOT trigger provider calls or market scan before button is clicked."""
    settings = settings_from_mapping({"DATA_PROVIDER": "schwab"})
    fake_scanner_st.button.return_value = False

    mock_run_scan = MagicMock()
    monkeypatch.setattr("tradex.ui.tabs.orb_preview.run_market_scan", mock_run_scan)

    scanner_ui_module.render_orb_preview_tab(settings=settings)

    # Scan Market button rendered
    assert fake_scanner_st.button.call_count >= 1
    # run_market_scan must NOT have been called
    assert mock_run_scan.call_count == 0


def test_scan_button_triggers_market_scan_execution(scanner_ui_module, fake_scanner_st, monkeypatch):
    """Clicking 'Scan Market' triggers run_market_scan and renders results."""
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    settings = settings_from_mapping({"DATA_PROVIDER": "schwab"})
    fake_scanner_st.button.return_value = True

    mock_res = MarketScanResult(
        session_date=date(2024, 1, 2),
        as_of_time=datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("America/New_York")),
        provider="mock",
        feed="sip",
        is_feed_consolidated=True,
        feed_disclosure="Simulated consolidated SIP tape",
        universe_size_discovered=500,
        securities_evaluated=500,
        daily_eligible_count=45,
        eligible_candidates_count=10,
        top_n_selected=2,
        candidates=[
            CandidatePreviewRow(
                rank=1,
                symbol="AAPL",
                direction=Direction.LONG,
                or_open=180.0,
                or_high=182.5,
                or_low=179.5,
                or_close=182.0,
                or_volume=500000.0,
                adv14=3000000.0,
                atr14=2.50,
                rv14=3.50,
                stop_entry_trigger=182.5,
                theoretical_stop_offset=0.25,
                order_intent_status=OrderStatus.ORDER_NOT_TRIGGERED,
                explanation="Rank 1: Bullish OR LONG setup above $182.50; RV14 3.50x.",
            ),
            CandidatePreviewRow(
                rank=2,
                symbol="MSFT",
                direction=Direction.SHORT,
                or_open=375.0,
                or_high=376.0,
                or_low=372.0,
                or_close=372.5,
                or_volume=400000.0,
                adv14=2000000.0,
                atr14=3.00,
                rv14=2.80,
                stop_entry_trigger=372.0,
                theoretical_stop_offset=0.30,
                order_intent_status=OrderStatus.ORDER_NOT_TRIGGERED,
                explanation="Rank 2: Bearish OR SHORT setup below $372.00; RV14 2.80x.",
            ),
        ],
        unranked_eligible_candidates=[],
        exclusions=[],
        is_time_gated=False,
        time_gate_message=None,
        coverage_completeness_pct=100.0,
        coverage_status="full_market_sip",
        coverage_warning="Full-market candidate discovery evaluated 500 securities.",
        warnings=[],
    )

    mock_run_scan = MagicMock(return_value=mock_res)
    monkeypatch.setattr("tradex.ui.tabs.orb_preview.run_market_scan", mock_run_scan)

    scanner_ui_module.render_orb_preview_tab(settings=settings)

    assert mock_run_scan.call_count == 1
    # Candidate table rendered via dataframe
    assert fake_scanner_st.dataframe.call_count >= 1
    df_called = fake_scanner_st.dataframe.call_args_list[0][0][0]
    assert len(df_called) == 2
    assert "AAPL" in df_called["Symbol"].values
    assert "MSFT" in df_called["Symbol"].values


def test_ui_feed_disclosure_warning_on_iex(scanner_ui_module, fake_scanner_st, monkeypatch):
    """When scan runs on IEX feed, renders a prominent warning about provisional status."""
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    settings = settings_from_mapping({})
    fake_scanner_st.button.return_value = False

    # Simulate existing scan result on IEX in session_state
    mock_res_iex = MarketScanResult(
        session_date=date(2024, 1, 2),
        as_of_time=datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("America/New_York")),
        provider="alpaca",
        feed="iex",
        is_feed_consolidated=False,
        feed_disclosure="Alpaca Free Tier (IEX Feed Only)",
        universe_size_discovered=1000,
        securities_evaluated=1000,
        daily_eligible_count=100,
        eligible_candidates_count=20,
        top_n_selected=20,
        candidates=[],
        unranked_eligible_candidates=[],
        exclusions=[],
        is_time_gated=False,
        time_gate_message=None,
        coverage_completeness_pct=100.0,
        coverage_status="provisional_iex",
        coverage_warning="PROVISIONAL RANKINGS (IEX FEED ONLY): TradeX evaluated 1,000 securities using IEX feed (~2% volume).",
        warnings=[],
    )
    fake_scanner_st.session_state["orb_market_scan_result"] = mock_res_iex

    scanner_ui_module.render_orb_preview_tab(settings=settings)

    # Check warning was called with IEX notice
    warning_calls = [str(c[0][0]) for c in fake_scanner_st.warning.call_args_list]
    assert any("PROVISIONAL RANKINGS (IEX FEED ONLY)" in w for w in warning_calls)


def test_ui_time_gate_blocked_error_display(scanner_ui_module, fake_scanner_st):
    """When scan is time-gated before 09:35 ET, renders time-gate error and stops."""
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    settings = settings_from_mapping({})
    mock_res_gated = MarketScanResult(
        session_date=date(2024, 1, 2),
        as_of_time=datetime(2024, 1, 2, 9, 30, tzinfo=ZoneInfo("America/New_York")),
        provider="mock",
        feed="sip",
        is_feed_consolidated=True,
        feed_disclosure="Simulated consolidated SIP tape",
        universe_size_discovered=0,
        securities_evaluated=0,
        daily_eligible_count=0,
        eligible_candidates_count=0,
        top_n_selected=0,
        candidates=[],
        unranked_eligible_candidates=[],
        exclusions=[],
        is_time_gated=True,
        time_gate_message="Candidate ranking is blocked: as-of time is prior to 09:35 ET.",
        coverage_completeness_pct=0.0,
        coverage_status="time_gated",
        coverage_warning="Time-gated before 09:35 ET.",
        warnings=[],
    )
    fake_scanner_st.session_state["orb_market_scan_result"] = mock_res_gated

    scanner_ui_module.render_orb_preview_tab(settings=settings)

    fake_scanner_st.error.assert_called_once()
    assert "Time-Gate Blocked" in str(fake_scanner_st.error.call_args[0][0])
    fake_scanner_st.stop.assert_called_once()


def test_ui_provisional_incomplete_warning(scanner_ui_module, fake_scanner_st):
    """When scan has material data gaps (provisional_incomplete), renders warning and provisional table header."""
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    settings = settings_from_mapping({})
    mock_res_incomplete = MarketScanResult(
        session_date=date(2024, 1, 2),
        as_of_time=datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("America/New_York")),
        scan_requested_at=datetime(2024, 1, 2, 9, 35, 10, tzinfo=ZoneInfo("America/New_York")),
        scan_completed_at=datetime(2024, 1, 2, 9, 36, 15, tzinfo=ZoneInfo("America/New_York")),
        data_freshness_time=datetime(2024, 1, 2, 9, 34, 59, tzinfo=ZoneInfo("America/New_York")),
        provider="mock",
        feed="sip",
        is_feed_consolidated=True,
        feed_disclosure="Simulated consolidated SIP tape",
        universe_size_discovered=100,
        securities_evaluated=10,
        daily_eligible_count=2,
        eligible_candidates_count=1,
        top_n_selected=1,
        candidates=[],
        unranked_eligible_candidates=[],
        exclusions=[],
        is_time_gated=False,
        time_gate_message=None,
        coverage_completeness_pct=10.0,
        coverage_status="provisional_incomplete",
        coverage_warning="PROVISIONAL RANKINGS (MATERIAL DATA GAPS): Evaluated 10 of 100 discovered securities (10.0% coverage).",
        warnings=[],
    )
    fake_scanner_st.session_state["orb_market_scan_result"] = mock_res_incomplete

    scanner_ui_module.render_orb_preview_tab(settings=settings)

    warning_calls = [str(c[0][0]) for c in fake_scanner_st.warning.call_args_list]
    assert any("PROVISIONAL RANKINGS (MATERIAL DATA GAPS)" in w for w in warning_calls)

    markdown_calls = [str(c[0][0]) for c in fake_scanner_st.markdown.call_args_list]
    assert any("Provisional Rankings" in m for m in markdown_calls)

    # Captions must display timestamps
    caption_calls = [str(c[0][0]) for c in fake_scanner_st.caption.call_args_list]
    assert any("Scan Requested" in c for c in caption_calls)
    assert any("Scan Completed" in c for c in caption_calls)
    assert any("Opening-Range Window End" in c for c in caption_calls)


def test_ui_failed_scan_displays_error_not_success(scanner_ui_module, fake_scanner_st, monkeypatch):
    """When a scan fails, status container renders an error message, never success."""
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    settings = settings_from_mapping({})
    fake_scanner_st.button.return_value = True

    mock_res_failed = MarketScanResult(
        session_date=date(2024, 1, 2),
        as_of_time=datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("America/New_York")),
        provider="mock",
        feed="sip",
        is_feed_consolidated=True,
        feed_disclosure="Simulated consolidated SIP tape",
        universe_size_discovered=10,
        securities_evaluated=0,
        daily_eligible_count=0,
        eligible_candidates_count=0,
        top_n_selected=0,
        candidates=[],
        unranked_eligible_candidates=[],
        exclusions=[],
        is_time_gated=False,
        time_gate_message=None,
        coverage_completeness_pct=0.0,
        coverage_status="failed",
        coverage_warning="Daily data acquisition failed.",
        warnings=["Failed"],
        stage_failures={"DAILY_ELIGIBILITY": "Simulated error"},
    )

    mock_run_scan = MagicMock(return_value=mock_res_failed)
    monkeypatch.setattr("tradex.ui.tabs.orb_preview.run_market_scan", mock_run_scan)

    # Setup status container mock
    status_mock = MagicMock()
    fake_scanner_st.empty.return_value = status_mock

    scanner_ui_module.render_orb_preview_tab(settings=settings)

    # Status container must show error, NOT success
    status_mock.error.assert_called_once()
    assert "Market scan failed" in str(status_mock.error.call_args[0][0])


def test_ui_mock_market_scan_end_to_end_renders_populated_candidates(scanner_ui_module, fake_scanner_st):
    """End-to-end smoke test of UI-to-scanner workflow using populated mock provider.

    Verifies clicking 'Scan Market' evaluates the 2024-01-02 fixture without real network calls,
    identifies the results as a historical synthetic demo, and renders all 20 qualifying candidates.
    """
    settings = settings_from_mapping({"DATA_PROVIDER": "schwab"})
    fake_scanner_st.button.return_value = True

    status_mock = MagicMock()
    fake_scanner_st.empty.return_value = status_mock

    scanner_ui_module.render_orb_preview_tab(settings=settings)

    # Status container must show historical synthetic demo info
    info_calls = [str(c[0][0]) for c in status_mock.info.call_args_list]
    assert any("Historical synthetic demo" in i for i in info_calls)

    # Result in session state must be synthetic demo with 20 candidates
    scan_result = fake_scanner_st.session_state.get("orb_market_scan_result")
    assert scan_result is not None
    assert scan_result.coverage_status == "synthetic_demo"
    assert len(scan_result.candidates) == 20
    assert scan_result.top_n_selected == 20
    assert scan_result.session_date.isoformat() == "2024-01-02"

    # Dataframe must have received 20 candidates
    df_calls = fake_scanner_st.dataframe.call_args_list
    assert len(df_calls) >= 1
    df = df_calls[0][0][0]
    assert len(df) == 20
    status_mock.success.assert_not_called()


def test_ui_prepare_market_button_triggers_preparation(scanner_ui_module, fake_scanner_st, monkeypatch):
    """Clicking 'Prepare Market' triggers preparation service and displays success container."""
    from datetime import date
    from pathlib import Path

    from tradex.research.daytrade_orb.preparation import PreparationResult, PreparationStatus

    settings = settings_from_mapping({"DATA_PROVIDER": "schwab"})

    # Discrimination: Prepare Market returns True, Scan Market returns False
    fake_scanner_st.button.side_effect = lambda label, **kw: "Prepare Market" in label

    mock_prep_res = PreparationResult(
        session_date=date(2024, 1, 2),
        provider="mock",
        feed="synthetic",
        status=PreparationStatus.READY,
        universe_size_discovered=33,
        daily_eligible_count=25,
        artifact_path=Path("/tmp/prep_mock.json"),
        coverage_status="complete",
        coverage_warning="",
        timings={},
        warnings=[],
    )
    mock_prepare = MagicMock(return_value=mock_prep_res)
    monkeypatch.setattr("tradex.ui.tabs.orb_preview.prepare_market", mock_prepare)

    status_mock = MagicMock()
    fake_scanner_st.empty.return_value = status_mock

    scanner_ui_module.render_orb_preview_tab(settings=settings)

    mock_prepare.assert_called_once()
    assert fake_scanner_st.session_state.get("orb_market_prep_result") == mock_prep_res
    status_mock.success.assert_called_once()
    assert "Market preparation completed successfully" in str(status_mock.success.call_args[0][0])


def test_ui_cache_status_renders_ready_and_stale_badges(scanner_ui_module, fake_scanner_st, monkeypatch):
    """Cache card renders appropriate status alerts for READY and STALE cache states."""
    from tradex.research.daytrade_orb.preparation import CacheValidationResult, PreparationStatus

    settings = settings_from_mapping({"DATA_PROVIDER": "schwab"})
    fake_scanner_st.button.return_value = False

    # 1. Test READY status
    ready_result = CacheValidationResult(
        is_valid=True,
        status=PreparationStatus.READY,
        reason="Preparation artifact is fully valid.",
    )
    monkeypatch.setattr("tradex.ui.tabs.orb_preview.inspect_cache_status", lambda **kw: ready_result)

    scanner_ui_module.render_orb_preview_tab(settings=settings)
    assert any("Ready (Full Market Preparation)" in str(c[0][0]) for c in fake_scanner_st.success.call_args_list)

    # 2. Test STALE status
    fake_scanner_st.success.reset_mock()
    fake_scanner_st.warning.reset_mock()
    stale_result = CacheValidationResult(
        is_valid=False,
        status=PreparationStatus.STALE,
        reason="Artifact target date does not match current session.",
    )
    monkeypatch.setattr("tradex.ui.tabs.orb_preview.inspect_cache_status", lambda **kw: stale_result)

    scanner_ui_module.render_orb_preview_tab(settings=settings)
    assert any("Stale Preparation" in str(c[0][0]) for c in fake_scanner_st.warning.call_args_list)


def test_ui_warmed_scan_renders_warmed_badge(scanner_ui_module, fake_scanner_st, monkeypatch):
    """A scan marked as was_warmed=True renders the Warmed Scan badge in the UI."""
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    settings = settings_from_mapping({"DATA_PROVIDER": "schwab"})
    fake_scanner_st.button.side_effect = lambda label, **kw: "Scan Market" in label

    mock_res_warmed = MarketScanResult(
        session_date=date(2024, 1, 2),
        as_of_time=datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("America/New_York")),
        provider="alpaca",
        feed="sip",
        is_feed_consolidated=True,
        feed_disclosure="Consolidated SIP",
        universe_size_discovered=8000,
        securities_evaluated=1200,
        daily_eligible_count=1200,
        eligible_candidates_count=20,
        top_n_selected=20,
        candidates=[],
        unranked_eligible_candidates=[],
        exclusions=[],
        is_time_gated=False,
        time_gate_message=None,
        coverage_completeness_pct=100.0,
        coverage_status="complete",
        coverage_warning=None,
        warnings=[],
        was_warmed=True,
        cache_status="READY",
        cache_message="Validated snapshot loaded.",
    )
    monkeypatch.setattr("tradex.ui.tabs.orb_preview.run_market_scan", lambda **kw: mock_res_warmed)

    scanner_ui_module.render_orb_preview_tab(settings=settings)
    assert any("Warmed Scan (Zero Historical Provider Calls)" in str(c[0][0]) for c in fake_scanner_st.success.call_args_list)

