"""Tests for the extracted Weights tab."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pytest

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.signals import weights as signal_weights


def _default_settings() -> TradeXSettings:
    return load_runtime_settings()


@pytest.fixture
def weights_tab_module(fake_st, monkeypatch):
    """Import the Weights tab fresh with a mocked Streamlit and safe weights backend."""
    mod_name = "tradex.ui.tabs.weights"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    # Ensure no file IO during import or render if the tab module ever calls load early.
    monkeypatch.setattr("tradex.signals.weights.load", MagicMock(return_value=signal_weights.Weights.defaults()))
    monkeypatch.setattr("tradex.signals.weights.save", MagicMock())
    monkeypatch.setattr("tradex.signals.weights.reset_to_defaults", MagicMock(return_value=signal_weights.Weights.defaults()))
    mod = importlib.import_module(mod_name)
    return mod


def test_import_does_not_load_weights(weights_tab_module):
    """Importing the tab module must not load or write weights."""
    assert weights_tab_module.signal_weights.load.call_count == 0
    assert weights_tab_module.signal_weights.save.call_count == 0
    assert weights_tab_module.signal_weights.reset_to_defaults.call_count == 0


def test_render_loads_weights_with_settings(weights_tab_module, fake_st):
    """Rendering loads weights with the explicit settings object."""
    settings = _default_settings()
    load_mock = MagicMock(return_value=signal_weights.Weights.defaults())
    weights_tab_module.signal_weights.load = load_mock

    weights_tab_module.render_weights_tab(settings=settings)

    load_mock.assert_called_once_with(settings=settings)


def test_no_button_click_does_not_write(weights_tab_module, fake_st):
    """If no save/reset button is clicked, no persistence or rerun occurs."""
    settings = _default_settings()
    weights_tab_module.render_weights_tab(settings=settings)

    weights_tab_module.signal_weights.save.assert_not_called()
    weights_tab_module.signal_weights.reset_to_defaults.assert_not_called()
    fake_st.rerun.assert_not_called()


def test_save_button_writes_weights(weights_tab_module, fake_st):
    """Clicking Save weights writes a Weights object built from slider values."""
    settings = _default_settings()
    defaults = signal_weights.Weights.defaults()
    weights_tab_module.signal_weights.load = lambda *, settings: defaults
    fake_st._active_button_keys = {"weights_save"}

    weights_tab_module.render_weights_tab(settings=settings)

    weights_tab_module.signal_weights.save.assert_called_once()
    saved = weights_tab_module.signal_weights.save.call_args[0][0]
    assert isinstance(saved, signal_weights.Weights)
    assert saved.to_dict() == defaults.to_dict()
    assert weights_tab_module.signal_weights.save.call_args.kwargs["settings"] is settings
    fake_st.rerun.assert_not_called()


def test_reset_button_resets_and_reruns(weights_tab_module, fake_st):
    """Clicking Reset to defaults resets weights and triggers a rerun."""
    settings = _default_settings()
    reset_mock = MagicMock(return_value=signal_weights.Weights.defaults())
    weights_tab_module.signal_weights.load = lambda *, settings: signal_weights.Weights.defaults()
    weights_tab_module.signal_weights.reset_to_defaults = reset_mock
    fake_st._active_button_keys = {"weights_reset"}

    weights_tab_module.render_weights_tab(settings=settings)

    reset_mock.assert_called_once_with(settings=settings)
    weights_tab_module.signal_weights.save.assert_not_called()
    fake_st.rerun.assert_called_once()


def test_widget_keys_preserved(weights_tab_module, fake_st):
    """All expected weight slider keys are rendered."""
    settings = _default_settings()
    weights_tab_module.signal_weights.load = lambda *, settings: signal_weights.Weights.defaults()

    weights_tab_module.render_weights_tab(settings=settings)

    slider_keys = {call.kwargs.get("key") for call in fake_st.slider.call_args_list}
    expected = set()
    for timeframe, section in (
        ("intraday", signal_weights.IntradayWeights()),
        ("short", signal_weights.ShortWeights()),
        ("long", signal_weights.LongWeights()),
    ):
        for field in section.__dataclass_fields__:
            expected.add(f"w_{timeframe}_{field}")
    assert expected.issubset(slider_keys)
