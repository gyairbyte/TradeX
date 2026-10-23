"""UI tests for Scan Scope selection and discovery scanner workflows (LONG-MVP-003)."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.config import settings_from_mapping
from tradex.discovery.models import DiscoveryResult, ScanStatus, Scope, UniverseProvenance


@pytest.fixture
def scanner_ui(fake_st, monkeypatch):
    """Import the Scanner tab fresh with mocked Streamlit and backend dependencies."""
    mod_name = "tradex.ui.tabs.scanner"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    mod = importlib.import_module(mod_name)

    drill_df = pd.DataFrame(
        {
            "open": [10.0, 11.0],
            "high": [12.0, 13.0],
            "low": [9.0, 10.0],
            "close": [11.0, 12.0],
            "volume": [1000, 2000],
            "ema_20": [10.0, 11.0],
            "ema_50": [9.5, 10.5],
            "bb_upper": [12.5, 13.5],
            "bb_lower": [8.5, 9.5],
            "volume_sma20": [1000.0, 2000.0],
        }
    )
    monkeypatch.setattr(mod, "fetch", MagicMock(return_value=drill_df))
    monkeypatch.setattr(mod, "add_indicators", MagicMock(return_value=drill_df))

    yield mod
    sys.modules.pop(mod_name, None)


def test_scanner_tab_renders_scope_selector_on_long_only(scanner_ui, fake_st):
    """Scan Scope selector appears when timeframe is 'long', but not on 'intraday' or 'short'."""
    settings = settings_from_mapping({})

    # 1. On 'long' timeframe -> selectbox for Scan Scope should be rendered
    scanner_ui.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="long",
        min_score=40,
        earnings_buffer=0,
        provider="schwab",
        earnings_source="yahoo",
    )
    selectbox_labels = [call[0][0] for call in fake_st.selectbox.call_args_list]
    assert "Scan Scope" in selectbox_labels

    fake_st.selectbox.reset_mock()

    # 2. On 'intraday' timeframe -> Scan Scope should NOT be rendered
    scanner_ui.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="intraday",
        min_score=40,
        earnings_buffer=0,
        provider="schwab",
        earnings_source="yahoo",
    )
    selectbox_labels_intraday = [call[0][0] for call in fake_st.selectbox.call_args_list]
    assert "Scan Scope" not in selectbox_labels_intraday


def test_scanner_tab_my_watchlist_preserves_existing_behavior(scanner_ui, fake_st, monkeypatch):
    """When Scan Scope is 'My Watchlist', standard Run Scan button and run_with_report are used."""
    settings = settings_from_mapping({})
    fake_st._active_button_keys.add("btn_scan")

    dummy_report = MagicMock()
    dummy_report.results = pd.DataFrame([{"ticker": "AAPL", "score": 85, "reasons": "Trend"}])
    dummy_report.fetch_failures = {}
    dummy_report.scoring_failures = {}
    dummy_report.earnings_failures = {}
    dummy_report.total_earnings_excluded = 0
    dummy_report.total_fetch_eligible = 1
    dummy_report.total_fetched = 1
    dummy_report.fallback_used = False
    dummy_report.requested_provider = "schwab"
    dummy_report.actual_provider = "schwab"
    dummy_report.failures = {}
    dummy_report.attempt_log = []

    mock_run = MagicMock(return_value=dummy_report)
    mock_record = MagicMock()
    monkeypatch.setattr(scanner_ui, "run_with_report", mock_run)
    monkeypatch.setattr(scanner_ui.store, "record_scan", mock_record)

    scanner_ui.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="long",
        min_score=40,
        earnings_buffer=0,
        provider="schwab",
        earnings_source="yahoo",
    )

    assert mock_run.called
    assert mock_record.called
    assert fake_st.session_state.get("scan_scope") == Scope.MY_WATCHLIST.value


def test_scanner_tab_discovery_scope_triggers_coordinator(scanner_ui, fake_st, monkeypatch):
    """Selecting S&P 500 triggers discovery coordinator and renders status metrics."""
    settings = settings_from_mapping({})

    # Override selectbox to choose S&P 500
    def _selectbox(label, *args, **kwargs):
        if label == "Scan Scope":
            return Scope.SP500.value
        for arg in args:
            if isinstance(arg, (list, tuple)) and arg:
                return arg[0]
        return kwargs.get("index")

    fake_st.selectbox.side_effect = _selectbox
    fake_st._active_button_keys.add("btn_disc_start")

    dummy_res = DiscoveryResult(
        scope=Scope.SP500,
        universe_provenance=UniverseProvenance(
            universe_id="sp500",
            scope=Scope.SP500,
            source_urls=(),
            retrieval_timestamp="2026-10-22T08:00:00Z",
            source_file_generation_timestamp="2026-05",
            snapshot_hash="hash500",
            original_listing_counts={"sp500": 503},
            included_ticker_count=503,
            excluded_counts_by_reason={},
            unsupported_symbol_count=0,
        ),
        session_date=pd.to_datetime("2026-10-21").date(),
        provider="schwab",
        actual_provider="schwab",
        total_tickers=503,
        completed_count=503,
        remaining_count=0,
        scored_count=500,
        qualifying_count=5,
        insufficient_data_count=3,
        failed_count=0,
        cached_count=503,
        status=ScanStatus.COMPLETE,
        focus_list=pd.DataFrame([
            {
                "ticker": "AAPL",
                "score": 90,
                "state": "ENTER NOW",
                "primary_setup": "momentum_continuation",
                "last_close": 150.0,
                "reasons": "Trend",
                "provider": "schwab",
            }
        ]),
        all_qualifying=pd.DataFrame(),
        all_observations=pd.DataFrame(),
        is_partial=False,
    )

    mock_coord_run = MagicMock(return_value=dummy_res)
    monkeypatch.setattr(scanner_ui.DiscoveryCoordinator, "run", mock_coord_run)

    scanner_ui.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="long",
        min_score=40,
        earnings_buffer=0,
        provider="schwab",
        earnings_source="yahoo",
    )

    assert mock_coord_run.called
    assert fake_st.session_state.get("scan_scope") == Scope.SP500.value
    # Verify bounded foreground execution is enforced
    call_kwargs = mock_coord_run.call_args.kwargs
    assert call_kwargs.get("max_batches_per_run") == 5


def test_scanner_tab_cache_key_isolation_clears_stale_results(scanner_ui, fake_st):
    """When switching provider/date/scope, prior scan_results are cleared from session state."""
    settings = settings_from_mapping({})

    # Pre-populate session state with prior scan results from an old cache key
    fake_st.session_state["active_disc_cache_key"] = "old_stale_cache_key_from_prior_session"
    fake_st.session_state["scan_results"] = pd.DataFrame([{"ticker": "OLD", "score": 99}])

    def _selectbox(label, *args, **kwargs):
        if label == "Scan Scope":
            return Scope.SP500.value
        for arg in args:
            if isinstance(arg, (list, tuple)) and arg:
                return arg[0]
        return kwargs.get("index")

    fake_st.selectbox.side_effect = _selectbox

    scanner_ui.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="long",
        min_score=40,
        earnings_buffer=0,
        provider="schwab",
        earnings_source="yahoo",
    )

    # Stale scan_results from previous cache key must have been cleared
    assert "scan_results" not in fake_st.session_state or fake_st.session_state["scan_results"] is None


def test_scanner_tab_mixed_provider_drilldown_uses_row_provider(scanner_ui, fake_st, monkeypatch):
    """Drill-down chart uses row-specific provider when scan_provider is mixed or multi-provider."""
    settings = settings_from_mapping({})

    mixed_results = pd.DataFrame([
        {
            "ticker": "AAPL",
            "score": 85,
            "state": "ENTER NOW",
            "primary_setup": "breakout_expansion",
            "last_close": 150.0,
            "reasons": "Breakout",
            "provider": "alpaca",
        },
        {
            "ticker": "MSFT",
            "score": 80,
            "state": "ARMED",
            "primary_setup": "trend_pullback",
            "last_close": 400.0,
            "reasons": "Pullback",
            "provider": "yahoo",
        },
    ])

    dummy_res = DiscoveryResult(
        scope=Scope.SP500,
        universe_provenance=UniverseProvenance(
            universe_id="sp500",
            scope=Scope.SP500,
            source_urls=(),
            retrieval_timestamp="2026-10-22T08:00:00Z",
            source_file_generation_timestamp="2026-05",
            snapshot_hash="hash500",
            original_listing_counts={"sp500": 503},
            included_ticker_count=503,
            excluded_counts_by_reason={},
            unsupported_symbol_count=0,
        ),
        session_date=pd.to_datetime("2026-10-21").date(),
        provider="alpaca",
        actual_provider="alpaca, yahoo",
        actual_providers=("alpaca", "yahoo"),
        fallback_used=True,
        total_tickers=2,
        completed_count=2,
        remaining_count=0,
        scored_count=2,
        qualifying_count=2,
        insufficient_data_count=0,
        failed_count=0,
        cached_count=2,
        status=ScanStatus.COMPLETE,
        focus_list=mixed_results,
        all_qualifying=mixed_results,
        all_observations=pd.DataFrame(),
        is_partial=False,
    )

    monkeypatch.setattr(scanner_ui.DiscoveryCoordinator, "run", MagicMock(return_value=dummy_res))
    fake_st._active_button_keys.add("btn_disc_start")

    def _selectbox(label, *args, **kwargs):
        if label == "Scan Scope":
            return Scope.SP500.value
        if label == "Select ticker":
            return "MSFT"  # Pick MSFT which used fallback provider yahoo
        for arg in args:
            if isinstance(arg, (list, tuple)) and arg:
                return arg[0]
        return kwargs.get("index")

    fake_st.selectbox.side_effect = _selectbox

    scanner_ui.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="long",
        min_score=40,
        earnings_buffer=0,
        provider="alpaca",
        earnings_source="yahoo",
    )

    # Drilldown fetch must be called for MSFT with provider='yahoo' (its actual row provider)
    scanner_ui.fetch.assert_called_with("MSFT", "long", provider="yahoo", settings=settings)

