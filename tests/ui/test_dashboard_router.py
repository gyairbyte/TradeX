"""Dashboard routing regression: st.tabs labels and extracted tab renderer calls."""
from __future__ import annotations

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
        if args and isinstance(args[0], (list, tuple)) and args[0]:
            return args[0][0]
        return None

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
            col.slider.return_value = 40
            cols.append(col)
        return cols

    st.button.side_effect = _button
    st.selectbox.side_effect = _selectbox
    st.columns.side_effect = _columns
    st.slider.return_value = 40
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
    from tradex.tracker import store
    from tradex.watchlists import store as wl_store

    monkeypatch.setattr(store, "init", lambda *args, **kwargs: None)
    monkeypatch.setattr(wl_store, "init", lambda *args, **kwargs: None)

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
    journal_mock = MagicMock()
    weights_mock = MagicMock()
    monkeypatch.setattr("tradex.ui.tabs.signal_journal.render_signal_journal_tab", journal_mock)
    monkeypatch.setattr("tradex.ui.tabs.weights.render_weights_tab", weights_mock)

    sys.modules.pop("tradex.ui.dashboard", None)
    runpy.run_module("tradex.ui.dashboard", run_name="__main__")

    journal_mock.assert_called_once()
    weights_mock.assert_called_once()

    _, j_kwargs = journal_mock.call_args
    assert isinstance(j_kwargs["settings"], TradeXSettings)
    assert j_kwargs["timeframe"] == "short"
    assert j_kwargs["provider"] == "yahoo"

    _, w_kwargs = weights_mock.call_args
    assert isinstance(w_kwargs["settings"], TradeXSettings)
    assert set(w_kwargs.keys()) == {"settings"}
