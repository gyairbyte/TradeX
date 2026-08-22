"""Deterministic tests for the Research Lab container tab (MVP-ARCH-001-R3)."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pytest

from tradex.config import settings_from_mapping

_EXPECTED_NESTED_TABS = [
    "Coil Context",
    "Pattern Similarity — Rejected",
    "Options Activity — Exploratory",
]


@pytest.fixture
def fake_rl_st():
    """Return a deterministic Streamlit MagicMock for testing Research Lab."""
    st = MagicMock(name="streamlit")
    st.__version__ = "0.0.0"
    st.session_state = {}
    st.tabs.return_value = [MagicMock(), MagicMock(), MagicMock()]
    return st


@pytest.fixture
def research_lab_module(fake_rl_st, monkeypatch):
    """Import the Research Lab tab fresh with a mocked Streamlit."""
    mod_name = "tradex.ui.tabs.research_lab"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_rl_st)
    return importlib.import_module(mod_name)


def test_import_does_not_render_or_touch_backend(research_lab_module, fake_rl_st):
    """Importing the research_lab tab module must not call Streamlit or backend operations."""
    assert fake_rl_st.subheader.call_count == 0
    assert fake_rl_st.info.call_count == 0
    assert fake_rl_st.tabs.call_count == 0


def test_render_shows_subheader_and_disclosure(research_lab_module, fake_rl_st, monkeypatch):
    """Research Lab renders subheader and visible non-actionable disclosure."""
    monkeypatch.setattr("tradex.ui.tabs.research_lab.render_coil_detector_tab", MagicMock())
    monkeypatch.setattr("tradex.ui.tabs.research_lab.render_pattern_similarity_tab", MagicMock())
    monkeypatch.setattr("tradex.ui.tabs.research_lab.render_options_activity_tab", MagicMock())

    settings = settings_from_mapping({})
    research_lab_module.render_research_lab_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="intraday",
        provider="schwab",
        options_source="auto",
    )

    fake_rl_st.subheader.assert_called_once_with("Research Lab")
    assert fake_rl_st.info.call_count == 1
    info_text = str(fake_rl_st.info.call_args[0][0])
    assert "Research Lab contains exploratory, rejected, contextual, and archived functionality" in info_text
    assert "Nothing in this area is a production-approved actionable strategy" in info_text


def test_render_creates_exact_nested_tabs(research_lab_module, fake_rl_st, monkeypatch):
    """Research Lab creates exactly the three canonical nested tab labels in order."""
    monkeypatch.setattr("tradex.ui.tabs.research_lab.render_coil_detector_tab", MagicMock())
    monkeypatch.setattr("tradex.ui.tabs.research_lab.render_pattern_similarity_tab", MagicMock())
    monkeypatch.setattr("tradex.ui.tabs.research_lab.render_options_activity_tab", MagicMock())

    settings = settings_from_mapping({})
    research_lab_module.render_research_lab_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="short",
        provider="schwab",
        options_source="yahoo",
    )

    fake_rl_st.tabs.assert_called_once_with(_EXPECTED_NESTED_TABS)


def test_render_routes_to_child_renderers_with_preserved_arguments(
    research_lab_module, fake_rl_st, monkeypatch
):
    """Research Lab forwards exact arguments to child renderers without modifications."""
    coil_mock = MagicMock(name="render_coil_detector_tab")
    pattern_mock = MagicMock(name="render_pattern_similarity_tab")
    options_mock = MagicMock(name="render_options_activity_tab")

    monkeypatch.setattr("tradex.ui.tabs.research_lab.render_coil_detector_tab", coil_mock)
    monkeypatch.setattr("tradex.ui.tabs.research_lab.render_pattern_similarity_tab", pattern_mock)
    monkeypatch.setattr("tradex.ui.tabs.research_lab.render_options_activity_tab", options_mock)

    settings = settings_from_mapping({})
    watchlist = ["AAPL", "NVDA", "TSLA"]
    research_lab_module.render_research_lab_tab(
        settings=settings,
        watchlist=watchlist,
        timeframe="long",
        provider="schwab",
        options_source="unusual_whales",
    )

    # 1. Coil Detector receives settings and timeframe
    coil_mock.assert_called_once_with(
        settings=settings,
        timeframe="long",
    )

    # 2. Pattern Similarity receives settings, watchlist, and provider
    pattern_mock.assert_called_once_with(
        settings=settings,
        watchlist=watchlist,
        provider="schwab",
    )

    # 3. Options Activity receives settings, watchlist, and options_source
    options_mock.assert_called_once_with(
        settings=settings,
        watchlist=watchlist,
        options_source="unusual_whales",
    )
