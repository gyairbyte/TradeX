"""Dashboard routing regression: st.tabs labels and extracted tab renderer calls (MVP-ARCH-001-R3)."""
from __future__ import annotations

import importlib
import runpy
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.config import TradeXSettings

_EXPECTED_TABS = [
    "Scanner",
    "Confluence",
    "Pre-Market",
    "Signal Journal",
    "Research Lab",
    "Settings",
    "Help",
]

_REMOVED_TOP_LEVEL_TABS = [
    "Coil Detector",
    "Pattern Similarity — Experimental Research",
    "Options Activity",
    "Alerts",
    "Weights",
]


def _make_fake_st():
    """Return a deterministic Streamlit MagicMock for a full dashboard run."""
    st = MagicMock(name="streamlit")
    st.__version__ = "0.0.0"
    st.session_state = {}

    def _button(label, *args, **kwargs):
        # Keep the dashboard run network-free; do not trigger scans or saves.
        return False

    def _selectbox(label, *args, **kwargs):
        if label == "Timeframe":
            return "short"
        if label == "OHLCV provider":
            return "yahoo"
        if label == "Options source":
            return "auto"
        if label == "Earnings source":
            return "yahoo"
        if label == "Market-cap source":
            return "yahoo"
        if label == "Active watchlist":
            return "Default"
        if label == "Preset":
            return args[0][0]
        for arg in args:
            if isinstance(arg, (list, tuple)) and arg:
                return arg[0]
        return None

    def _slider(*args, **kwargs):
        # Streamlit slider signature: st.slider(label, min, max, value, ...)
        if len(args) >= 4:
            return args[3]
        return kwargs.get("value", 0)

    def _columns(spec, *args, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        cols = []
        for _ in range(n):
            col = MagicMock()
            col.selectbox.side_effect = _selectbox
            col.button.side_effect = _button
            col.checkbox.return_value = False
            col.text_input.return_value = ""
            col.text_area.return_value = ""
            col.slider.side_effect = _slider
            cols.append(col)
        return cols

    st.button.side_effect = _button
    st.selectbox.side_effect = _selectbox
    st.columns.side_effect = _columns
    st.slider.side_effect = _slider
    st.text_input.return_value = ""
    st.text_area.return_value = ""
    st.checkbox.return_value = False
    st.multiselect.return_value = []
    st.tabs.side_effect = lambda tabs: [MagicMock() for _ in tabs]
    st.progress.return_value = MagicMock()
    return st


@pytest.fixture
def fake_dashboard_st(monkeypatch, tmp_path):
    """Install a deterministic Streamlit mock and suppress dashboard side effects."""
    st = _make_fake_st()
    monkeypatch.setitem(sys.modules, "streamlit", st)

    # Avoid touching ~/.tradex during the dashboard run.
    from tradex.watchlists import store as wl_store

    monkeypatch.setenv("TRADEX_DB_PATH", str(tmp_path / "signals.db"))
    monkeypatch.setenv("TRADEX_WATCHLISTS_DB_PATH", str(tmp_path / "watchlists.db"))
    monkeypatch.setenv("TRADEX_WEIGHTS_PATH", str(tmp_path / "weights.json"))
    monkeypatch.setenv("TRADEX_FP_DB", str(tmp_path / "fingerprints.db"))
    monkeypatch.setenv("TRADEX_EARNINGS_CACHE_PATH", str(tmp_path / "earnings_cache.db"))
    monkeypatch.setenv("ALERT_STATE_PATH", str(tmp_path / "alerts.db"))
    # list_all is called at module load; skip the real DB.
    monkeypatch.setattr(wl_store, "list_all", lambda *, settings: [])
    monkeypatch.setattr(wl_store, "load", lambda *args, **kwargs: None)

    # Suppress network/data fetches in tabs.
    monkeypatch.setattr("tradex.screener.engine.run_with_report", MagicMock())
    monkeypatch.setattr("tradex.tracker.store.record_scan", MagicMock())
    monkeypatch.setattr("tradex.tracker.analyzer.detect_coils", MagicMock(return_value=[]))
    monkeypatch.setattr("tradex.tracker.confluence.run_confluence_screen", MagicMock())
    monkeypatch.setattr("tradex.patterns.fingerprint.list_fingerprints", MagicMock(return_value=pd.DataFrame()))
    monkeypatch.setattr("tradex.patterns.matcher.run_match_screen", MagicMock())
    monkeypatch.setattr("tradex.premarket.gap_scanner.scan_gaps_with_report", MagicMock())
    monkeypatch.setattr("tradex.options.flow.scan_unusual_flow_with_report", MagicMock())
    monkeypatch.setattr("tradex.options.flow.scan_chain_activity_with_report", MagicMock())
    monkeypatch.setattr("tradex.options.flow.resolve_flow_source", MagicMock())
    monkeypatch.setattr("tradex.options.flow.resolve_chain_source", MagicMock())

    return st


def test_dashboard_creates_tabs_in_exact_order(fake_dashboard_st, monkeypatch):
    """The dashboard renders exactly the seven transitional tab labels in canonical order."""
    sys.modules.pop("tradex.ui.dashboard", None)
    runpy.run_module("tradex.ui.dashboard", run_name="__main__")

    assert fake_dashboard_st.tabs.call_count == 1
    args, _ = fake_dashboard_st.tabs.call_args
    assert len(args[0]) == 7
    assert args[0] == _EXPECTED_TABS

    # Assert old individual tabs are no longer top-level
    for removed in _REMOVED_TOP_LEVEL_TABS:
        assert removed not in args[0]


def test_dashboard_routes_to_extracted_renderers(fake_dashboard_st, monkeypatch):
    """The dashboard invokes each transitional top-level tab renderer exactly once with explicit settings."""
    scanner_mock = MagicMock(name="render_scanner_tab")
    confluence_mock = MagicMock(name="render_confluence_tab")
    premarket_mock = MagicMock(name="render_premarket_tab")
    journal_mock = MagicMock(name="render_signal_journal_tab")
    research_lab_mock = MagicMock(name="render_research_lab_tab")
    settings_mock = MagicMock(name="render_settings_tab")
    help_mock = MagicMock(name="render_help_tab")

    monkeypatch.setattr("tradex.ui.tabs.scanner.render_scanner_tab", scanner_mock)
    monkeypatch.setattr("tradex.ui.tabs.confluence.render_confluence_tab", confluence_mock)
    monkeypatch.setattr("tradex.ui.tabs.premarket.render_premarket_tab", premarket_mock)
    monkeypatch.setattr("tradex.ui.tabs.signal_journal.render_signal_journal_tab", journal_mock)
    monkeypatch.setattr("tradex.ui.tabs.research_lab.render_research_lab_tab", research_lab_mock)
    monkeypatch.setattr("tradex.ui.tabs.settings.render_settings_tab", settings_mock)
    monkeypatch.setattr("tradex.ui.tabs.help.render_help_tab", help_mock)

    sys.modules.pop("tradex.ui.dashboard", None)
    runpy.run_module("tradex.ui.dashboard", run_name="__main__")

    scanner_mock.assert_called_once()
    confluence_mock.assert_called_once()
    premarket_mock.assert_called_once()
    journal_mock.assert_called_once()
    research_lab_mock.assert_called_once()
    settings_mock.assert_called_once()
    help_mock.assert_called_once()

    help_mock.assert_called_once_with()

    # Scanner kwargs
    _, s_kwargs = scanner_mock.call_args
    assert isinstance(s_kwargs["settings"], TradeXSettings)
    assert isinstance(s_kwargs["watchlist"], list)
    assert len(s_kwargs["watchlist"]) == 20
    assert "AAPL" in s_kwargs["watchlist"]
    assert s_kwargs["watchlist"] == list(dict.fromkeys(s_kwargs["watchlist"]))
    assert s_kwargs["timeframe"] == "short"
    assert s_kwargs["min_score"] == 40
    assert s_kwargs["earnings_buffer"] == 0
    assert s_kwargs["provider"] == "yahoo"
    assert s_kwargs["earnings_source"] == "yahoo"

    # Confluence kwargs
    _, co_kwargs = confluence_mock.call_args
    assert isinstance(co_kwargs["settings"], TradeXSettings)
    assert isinstance(co_kwargs["watchlist"], list)
    assert len(co_kwargs["watchlist"]) == 20
    assert "AAPL" in co_kwargs["watchlist"]
    assert co_kwargs["watchlist"] == list(dict.fromkeys(co_kwargs["watchlist"]))
    assert co_kwargs["earnings_buffer"] == 0
    assert co_kwargs["provider"] == "yahoo"
    assert co_kwargs["earnings_source"] == "yahoo"

    # Pre-market kwargs (specialized Yahoo provider preserved)
    _, pm_kwargs = premarket_mock.call_args
    assert isinstance(pm_kwargs["settings"], TradeXSettings)
    assert isinstance(pm_kwargs["watchlist"], list)
    assert len(pm_kwargs["watchlist"]) == 20
    assert pm_kwargs["provider"] == "yahoo"
    assert pm_kwargs["earnings_source"] == "yahoo"

    # Signal Journal kwargs
    _, j_kwargs = journal_mock.call_args
    assert isinstance(j_kwargs["settings"], TradeXSettings)
    assert j_kwargs["timeframe"] == "short"
    assert j_kwargs["provider"] == "yahoo"

    # Research Lab kwargs
    _, rl_kwargs = research_lab_mock.call_args
    assert isinstance(rl_kwargs["settings"], TradeXSettings)
    assert isinstance(rl_kwargs["watchlist"], list)
    assert len(rl_kwargs["watchlist"]) == 20
    assert rl_kwargs["timeframe"] == "short"
    assert rl_kwargs["provider"] == "yahoo"
    assert rl_kwargs["options_source"] == "auto"

    # Settings kwargs
    _, set_kwargs = settings_mock.call_args
    assert isinstance(set_kwargs["settings"], TradeXSettings)
    assert set(set_kwargs.keys()) == {"settings"}

    assert (
        s_kwargs["settings"]
        is co_kwargs["settings"]
        is pm_kwargs["settings"]
        is j_kwargs["settings"]
        is rl_kwargs["settings"]
        is set_kwargs["settings"]
    )


def test_dashboard_import_without_main_does_not_call_st_tabs_or_renderers(monkeypatch):
    """A normal ``import tradex.ui.dashboard`` must not render any tab UI."""
    st_mock = MagicMock(name="streamlit")
    scanner_mock = MagicMock(name="render_scanner_tab")
    confluence_mock = MagicMock(name="render_confluence_tab")
    premarket_mock = MagicMock(name="render_premarket_tab")
    journal_mock = MagicMock(name="render_signal_journal_tab")
    research_lab_mock = MagicMock(name="render_research_lab_tab")
    settings_mock = MagicMock(name="render_settings_tab")
    help_mock = MagicMock(name="render_help_tab")

    monkeypatch.setitem(sys.modules, "streamlit", st_mock)
    monkeypatch.setattr("tradex.ui.tabs.scanner.render_scanner_tab", scanner_mock)
    monkeypatch.setattr("tradex.ui.tabs.confluence.render_confluence_tab", confluence_mock)
    monkeypatch.setattr("tradex.ui.tabs.premarket.render_premarket_tab", premarket_mock)
    monkeypatch.setattr("tradex.ui.tabs.signal_journal.render_signal_journal_tab", journal_mock)
    monkeypatch.setattr("tradex.ui.tabs.research_lab.render_research_lab_tab", research_lab_mock)
    monkeypatch.setattr("tradex.ui.tabs.settings.render_settings_tab", settings_mock)
    monkeypatch.setattr("tradex.ui.tabs.help.render_help_tab", help_mock)

    sys.modules.pop("tradex.ui.dashboard", None)
    importlib.import_module("tradex.ui.dashboard")

    st_mock.tabs.assert_not_called()
    scanner_mock.assert_not_called()
    confluence_mock.assert_not_called()
    premarket_mock.assert_not_called()
    journal_mock.assert_not_called()
    research_lab_mock.assert_not_called()
    settings_mock.assert_not_called()
    help_mock.assert_not_called()
