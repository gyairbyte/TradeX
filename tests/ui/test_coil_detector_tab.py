"""Tests for the extracted Coil Detector tab."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.config import TradeXSettings, settings_from_mapping


def _default_settings() -> TradeXSettings:
    return settings_from_mapping({})


def _coil_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "coil_strength": [75],
            "appearances": [3],
            "active_sessions": [3],
            "latest_score": [55],
            "score_trend": [0.8],
            "trend_direction": ["building"],
            "last_close": [150.0],
            "score_history": [[45, 50, 55]],
        }
    )


def _fading_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["TSLA"],
            "fade_strength": [65],
            "appearances": [3],
            "active_sessions": [2],
            "latest_score": [40],
            "peak_score": [58],
            "score_trend": [-0.8],
            "trend_direction": ["fading"],
            "last_close": [220.0],
            "score_history": [[55, 52, 40]],
        }
    )


def _ticker_state() -> dict:
    return {
        "ticker": "AAPL",
        "status": "coiling — building pressure",
        "summary": "AAPL has appeared 3x over 5 days with a score trending up.",
        "score_history": [45, 50, 55],
    }


@pytest.fixture
def coil_detector_module(fake_st, monkeypatch):
    """Import the Coil Detector tab fresh with mocked Streamlit and analyzer."""
    mod_name = "tradex.ui.tabs.coil_detector"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    mod = importlib.import_module(mod_name)

    analyzer_mock = MagicMock(name="analyzer")
    analyzer_mock.detect_coils.return_value = pd.DataFrame()
    analyzer_mock.detect_fading_setups.return_value = pd.DataFrame()
    analyzer_mock.get_ticker_state.return_value = _ticker_state()
    monkeypatch.setattr(mod, "analyzer", analyzer_mock)
    yield mod
    sys.modules.pop(mod_name, None)


def test_import_has_no_side_effects(fake_st, monkeypatch):
    """Importing the tab module must not render widgets or call analyzer backends."""
    mod_name = "tradex.ui.tabs.coil_detector"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    detect_coils = MagicMock()
    detect_fading = MagicMock()
    get_ticker_state = MagicMock()
    monkeypatch.setattr("tradex.tracker.analyzer.detect_coils", detect_coils)
    monkeypatch.setattr("tradex.tracker.analyzer.detect_fading_setups", detect_fading)
    monkeypatch.setattr("tradex.tracker.analyzer.get_ticker_state", get_ticker_state)

    importlib.import_module(mod_name)

    assert fake_st.subheader.call_count == 0
    assert fake_st.caption.call_count == 0
    assert detect_coils.call_count == 0
    assert detect_fading.call_count == 0
    assert get_ticker_state.call_count == 0


def test_initial_render_shows_subheader_caption_and_sliders(coil_detector_module, fake_st):
    """The initial render shows the expected heading, caption, expander, and sliders."""
    settings = _default_settings()

    coil_detector_module.render_coil_detector_tab(settings=settings, timeframe="short")

    assert fake_st.subheader.call_count == 1
    subheader = str(fake_st.subheader.call_args[0][0])
    assert "Coil Detector" in subheader

    caption_texts = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert any("building pressure" in t for t in caption_texts)

    assert fake_st.expander.call_count == 1

    slider_keys = {call.kwargs.get("key") for call in fake_st.slider.call_args_list}
    for col_list in fake_st._column_returns:
        for col in col_list:
            for call in col.slider.call_args_list:
                slider_keys.add(call.kwargs.get("key"))
    assert "coil_days" in slider_keys
    assert "coil_apps" in slider_keys

    coil_detector_module.analyzer.detect_coils.assert_not_called()
    coil_detector_module.analyzer.detect_fading_setups.assert_not_called()
    coil_detector_module.analyzer.get_ticker_state.assert_not_called()


def test_detect_coils_empty_result(coil_detector_module, fake_st):
    """Clicking Detect Coils with empty results shows the existing empty-state message."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_coil"}

    coil_detector_module.render_coil_detector_tab(settings=settings, timeframe="short")

    coil_detector_module.analyzer.detect_coils.assert_called_once()
    args, kwargs = coil_detector_module.analyzer.detect_coils.call_args
    assert args[0] == "short"
    assert kwargs["days"] == 7
    assert kwargs["min_appearances"] == 2
    assert kwargs["settings"] is settings

    info_texts = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("No active coiling setups" in t for t in info_texts)
    coil_detector_module.analyzer.get_ticker_state.assert_not_called()


def test_detect_coils_populated_result(coil_detector_module, fake_st):
    """Clicking Detect Coils renders the results table and drill-down."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_coil"}
    coil_detector_module.analyzer.detect_coils.return_value = _coil_df()

    coil_detector_module.render_coil_detector_tab(settings=settings, timeframe="short")

    coil_detector_module.analyzer.detect_coils.assert_called_once()
    args, kwargs = coil_detector_module.analyzer.detect_coils.call_args
    assert kwargs["settings"] is settings
    assert args[0] == "short"

    success_texts = [str(c[0][0]) for c in fake_st.success.call_args_list]
    assert any("coiling setups detected" in t for t in success_texts)

    assert fake_st.dataframe.call_count == 1
    passed_df = fake_st.dataframe.call_args[0][0]
    expected_cols = [
        "ticker",
        "coil_strength",
        "appearances",
        "active_sessions",
        "latest_score",
        "score_trend",
        "trend_direction",
        "last_close",
    ]
    assert list(passed_df.columns) == expected_cols

    selectbox_keys = {call.kwargs.get("key") for call in fake_st.selectbox.call_args_list}
    assert "sel_coil" in selectbox_keys

    coil_detector_module.analyzer.get_ticker_state.assert_called_once()
    args, kwargs = coil_detector_module.analyzer.get_ticker_state.call_args
    assert args[0] == "AAPL"
    assert args[1] == "short"
    assert kwargs["days"] == 7

    assert fake_st.plotly_chart.call_count == 1

    info_texts = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("building pressure" in t.lower() for t in info_texts)


def test_detect_fading_empty_result(coil_detector_module, fake_st):
    """Clicking Detect Fading Setups with empty results shows the existing message."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_fade"}

    coil_detector_module.render_coil_detector_tab(settings=settings, timeframe="short")

    coil_detector_module.analyzer.detect_fading_setups.assert_called_once()
    args, kwargs = coil_detector_module.analyzer.detect_fading_setups.call_args
    assert kwargs["settings"] is settings
    assert args[0] == "short"
    assert kwargs["days"] == 7
    assert kwargs["min_appearances"] == 2

    info_texts = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("No fading setups" in t for t in info_texts)


def test_detect_fading_populated_result(coil_detector_module, fake_st):
    """Clicking Detect Fading Setups renders the existing warning and table."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_fade"}
    coil_detector_module.analyzer.detect_fading_setups.return_value = _fading_df()

    coil_detector_module.render_coil_detector_tab(settings=settings, timeframe="short")

    coil_detector_module.analyzer.detect_fading_setups.assert_called_once()
    args, kwargs = coil_detector_module.analyzer.detect_fading_setups.call_args
    assert kwargs["settings"] is settings
    assert args[0] == "short"

    warning_texts = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert any("fading setups detected" in t for t in warning_texts)

    assert fake_st.dataframe.call_count == 1
    passed_df = fake_st.dataframe.call_args[0][0]
    expected_cols = [
        "ticker",
        "fade_strength",
        "appearances",
        "active_sessions",
        "latest_score",
        "peak_score",
        "score_trend",
        "trend_direction",
        "last_close",
    ]
    assert list(passed_df.columns) == expected_cols

    coil_detector_module.analyzer.get_ticker_state.assert_not_called()


def test_widget_keys_preserved(coil_detector_module, fake_st):
    """All expected Coil Detector widget keys are rendered."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_coil"}
    coil_detector_module.analyzer.detect_coils.return_value = _coil_df()

    coil_detector_module.render_coil_detector_tab(settings=settings, timeframe="short")

    button_keys = {call.kwargs.get("key") for call in fake_st.button.call_args_list}
    assert button_keys == {"btn_coil", "btn_fade"}

    slider_keys = set()
    for col_list in fake_st._column_returns:
        for col in col_list:
            for call in col.slider.call_args_list:
                slider_keys.add(call.kwargs.get("key"))
    assert slider_keys == {"coil_days", "coil_apps"}

    selectbox_keys = {call.kwargs.get("key") for call in fake_st.selectbox.call_args_list}
    assert selectbox_keys == {"sel_coil"}


def test_backend_ordering_unchanged(coil_detector_module, fake_st):
    """The UI preserves backend result ordering and does not re-rank."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_coil"}
    coil_detector_module.analyzer.detect_coils.return_value = _coil_df()

    coil_detector_module.render_coil_detector_tab(settings=settings, timeframe="short")

    passed_df = fake_st.dataframe.call_args[0][0]
    assert passed_df["ticker"].tolist() == ["AAPL"]
    assert passed_df.iloc[0]["coil_strength"] == 75
