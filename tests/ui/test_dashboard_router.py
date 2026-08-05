"""Dashboard routing regression: st.tabs labels and extracted tab renderer calls."""
from __future__ import annotations

import importlib
import runpy
import sys
from unittest.mock import MagicMock

import pytest

from tradex.config import TradeXSettings

_EXPECTED_TABS = [
    "Scanner",
    "Coil Detector",
    "Confluence",
    "Pattern Similarity — Experimental Research",
    "Pre-Market",
    "Options Activity",
    "Alerts",
    "Signal Journal",
    "Weights",
    "Help",
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
    st.tabs.return_value = [MagicMock() for _ in range(10)]
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

    # Suppress network/data fetches in tabs that have not yet been extracted.
    monkeypatch.setattr("tradex.screener.engine.run_with_report", MagicMock())
    monkeypatch.setattr("tradex.tracker.store.record_scan", MagicMock())
    monkeypatch.setattr("tradex.tracker.analyzer.detect_coils", MagicMock(return_value=[]))
    monkeypatch.setattr("tradex.tracker.confluence.run_confluence_screen", MagicMock())
    monkeypatch.setattr("tradex.patterns.matcher.run_match_screen", MagicMock())
    monkeypatch.setattr("tradex.premarket.gap_scanner.scan_gaps_with_report", MagicMock())
    monkeypatch.setattr("tradex.options.flow.scan_unusual_flow_with_report", MagicMock())
    monkeypatch.setattr("tradex.options.flow.scan_chain_activity_with_report", MagicMock())

    return st


def test_dashboard_creates_tabs_in_exact_order(fake_dashboard_st, monkeypatch):
    """The dashboard renders the ten canonical tab labels in order."""
    sys.modules.pop("tradex.ui.dashboard", None)
    runpy.run_module("tradex.ui.dashboard", run_name="__main__")

    assert fake_dashboard_st.tabs.call_count == 1
    args, _ = fake_dashboard_st.tabs.call_args
    assert args[0] == _EXPECTED_TABS


def test_dashboard_routes_to_extracted_renderers(fake_dashboard_st, monkeypatch):
    """The dashboard invokes each extracted tab renderer exactly once with explicit settings."""
    alerts_mock = MagicMock()
    coil_mock = MagicMock()
    confluence_mock = MagicMock()
    help_mock = MagicMock()
    journal_mock = MagicMock()
    scanner_mock = MagicMock()
    weights_mock = MagicMock()
    monkeypatch.setattr("tradex.ui.tabs.alerts.render_alerts_tab", alerts_mock)
    monkeypatch.setattr("tradex.ui.tabs.coil_detector.render_coil_detector_tab", coil_mock)
    monkeypatch.setattr("tradex.ui.tabs.confluence.render_confluence_tab", confluence_mock)
    monkeypatch.setattr("tradex.ui.tabs.help.render_help_tab", help_mock)
    monkeypatch.setattr("tradex.ui.tabs.scanner.render_scanner_tab", scanner_mock)
    monkeypatch.setattr("tradex.ui.tabs.signal_journal.render_signal_journal_tab", journal_mock)
    monkeypatch.setattr("tradex.ui.tabs.weights.render_weights_tab", weights_mock)

    sys.modules.pop("tradex.ui.dashboard", None)
    runpy.run_module("tradex.ui.dashboard", run_name="__main__")

    alerts_mock.assert_called_once()
    coil_mock.assert_called_once()
    confluence_mock.assert_called_once()
    help_mock.assert_called_once()
    journal_mock.assert_called_once()
    scanner_mock.assert_called_once()
    weights_mock.assert_called_once()

    _, a_kwargs = alerts_mock.call_args
    assert isinstance(a_kwargs["settings"], TradeXSettings)

    help_mock.assert_called_once_with()

    _, j_kwargs = journal_mock.call_args
    assert isinstance(j_kwargs["settings"], TradeXSettings)
    assert j_kwargs["timeframe"] == "short"
    assert j_kwargs["provider"] == "yahoo"

    _, w_kwargs = weights_mock.call_args
    assert isinstance(w_kwargs["settings"], TradeXSettings)
    assert set(w_kwargs.keys()) == {"settings"}

    _, c_kwargs = coil_mock.call_args
    assert isinstance(c_kwargs["settings"], TradeXSettings)
    assert c_kwargs["timeframe"] == "short"

    _, co_kwargs = confluence_mock.call_args
    assert isinstance(co_kwargs["settings"], TradeXSettings)
    assert isinstance(co_kwargs["watchlist"], list)
    assert len(co_kwargs["watchlist"]) == 20
    assert "AAPL" in co_kwargs["watchlist"]
    assert co_kwargs["watchlist"] == list(dict.fromkeys(co_kwargs["watchlist"]))
    assert co_kwargs["earnings_buffer"] == 0
    assert co_kwargs["provider"] == "yahoo"
    assert co_kwargs["earnings_source"] == "yahoo"

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

    assert a_kwargs["settings"] is j_kwargs["settings"] is w_kwargs["settings"] is c_kwargs["settings"] is co_kwargs["settings"] is s_kwargs["settings"]


def test_dashboard_import_without_main_does_not_call_st_tabs_or_renderers(monkeypatch):
    """A normal ``import tradex.ui.dashboard`` must not render any tab UI."""
    st_mock = MagicMock(name="streamlit")
    alerts_mock = MagicMock(name="render_alerts_tab")
    coil_mock = MagicMock(name="render_coil_detector_tab")
    confluence_mock = MagicMock(name="render_confluence_tab")
    help_mock = MagicMock(name="render_help_tab")
    journal_mock = MagicMock(name="render_signal_journal_tab")
    scanner_mock = MagicMock(name="render_scanner_tab")
    weights_mock = MagicMock(name="render_weights_tab")

    monkeypatch.setitem(sys.modules, "streamlit", st_mock)
    monkeypatch.setattr("tradex.ui.tabs.alerts.render_alerts_tab", alerts_mock)
    monkeypatch.setattr("tradex.ui.tabs.coil_detector.render_coil_detector_tab", coil_mock)
    monkeypatch.setattr("tradex.ui.tabs.confluence.render_confluence_tab", confluence_mock)
    monkeypatch.setattr("tradex.ui.tabs.help.render_help_tab", help_mock)
    monkeypatch.setattr("tradex.ui.tabs.scanner.render_scanner_tab", scanner_mock)
    monkeypatch.setattr("tradex.ui.tabs.signal_journal.render_signal_journal_tab", journal_mock)
    monkeypatch.setattr("tradex.ui.tabs.weights.render_weights_tab", weights_mock)

    sys.modules.pop("tradex.ui.dashboard", None)
    importlib.import_module("tradex.ui.dashboard")

    st_mock.tabs.assert_not_called()
    alerts_mock.assert_not_called()
    coil_mock.assert_not_called()
    confluence_mock.assert_not_called()
    help_mock.assert_not_called()
    journal_mock.assert_not_called()
    scanner_mock.assert_not_called()
    weights_mock.assert_not_called()
