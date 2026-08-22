"""Deterministic tests for the Settings container tab (MVP-ARCH-001-R3)."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pytest

from tradex.config import settings_from_mapping

_EXPECTED_NESTED_TABS = [
    "Alert Delivery",
    "Legacy Weights",
]


@pytest.fixture
def fake_settings_st():
    """Return a deterministic Streamlit MagicMock for testing Settings."""
    st = MagicMock(name="streamlit")
    st.__version__ = "0.0.0"
    st.session_state = {}
    st.tabs.return_value = [MagicMock(), MagicMock()]
    return st


@pytest.fixture
def settings_module(fake_settings_st, monkeypatch):
    """Import the Settings tab fresh with a mocked Streamlit."""
    mod_name = "tradex.ui.tabs.settings"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_settings_st)
    return importlib.import_module(mod_name)


def test_import_does_not_render_or_touch_backend(settings_module, fake_settings_st):
    """Importing the settings tab module must not call Streamlit or backend operations."""
    assert fake_settings_st.subheader.call_count == 0
    assert fake_settings_st.info.call_count == 0
    assert fake_settings_st.tabs.call_count == 0


def test_render_shows_subheader_and_transitional_guidance(settings_module, fake_settings_st, monkeypatch):
    """Settings renders subheader and transitional guidance disclosure."""
    monkeypatch.setattr("tradex.ui.tabs.settings.render_alerts_tab", MagicMock())
    monkeypatch.setattr("tradex.ui.tabs.settings.render_weights_tab", MagicMock())

    settings = settings_from_mapping({})
    settings_module.render_settings_tab(settings=settings)

    fake_settings_st.subheader.assert_called_once_with("Settings")
    assert fake_settings_st.info.call_count == 1
    info_text = str(fake_settings_st.info.call_args[0][0])
    assert "groups existing operational controls" in info_text
    assert "Global provider and watchlist controls remain in the sidebar" in info_text
    assert "alert gating has not been implemented" in info_text.lower()
    assert "legacy weight controls remain unvalidated" in info_text


def test_render_creates_exact_nested_tabs(settings_module, fake_settings_st, monkeypatch):
    """Settings creates exactly the two canonical nested tab labels in order."""
    monkeypatch.setattr("tradex.ui.tabs.settings.render_alerts_tab", MagicMock())
    monkeypatch.setattr("tradex.ui.tabs.settings.render_weights_tab", MagicMock())

    settings = settings_from_mapping({})
    settings_module.render_settings_tab(settings=settings)

    fake_settings_st.tabs.assert_called_once_with(_EXPECTED_NESTED_TABS)


def test_render_routes_to_child_renderers_with_preserved_arguments(
    settings_module, fake_settings_st, monkeypatch
):
    """Settings forwards exact settings argument to child renderers without modifications."""
    alerts_mock = MagicMock(name="render_alerts_tab")
    weights_mock = MagicMock(name="render_weights_tab")

    monkeypatch.setattr("tradex.ui.tabs.settings.render_alerts_tab", alerts_mock)
    monkeypatch.setattr("tradex.ui.tabs.settings.render_weights_tab", weights_mock)

    settings = settings_from_mapping({})
    settings_module.render_settings_tab(settings=settings)

    alerts_mock.assert_called_once_with(settings=settings)
    weights_mock.assert_called_once_with(settings=settings)
