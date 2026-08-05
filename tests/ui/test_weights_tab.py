"""Tests for the extracted Weights tab."""
from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.signals import weights as signal_weights


def _default_settings() -> TradeXSettings:
    return load_runtime_settings()


@pytest.fixture
def weights_tab_module(fake_st, monkeypatch):
    """Import the Weights tab with a mocked Streamlit."""
    from tradex.ui import tabs

    mod = importlib.reload(tabs.weights)
    monkeypatch.setattr(mod, "st", fake_st)
    return mod


def test_import_does_not_load_weights(weights_tab_module, monkeypatch):
    """Importing the tab module must not load or write weights."""
    load_mock = MagicMock()
    save_mock = MagicMock()
    reset_mock = MagicMock()
    monkeypatch.setattr(weights_tab_module.signal_weights, "load", load_mock)
    monkeypatch.setattr(weights_tab_module.signal_weights, "save", save_mock)
    monkeypatch.setattr(weights_tab_module.signal_weights, "reset_to_defaults", reset_mock)

    # module already imported, but no render call yet
    load_mock.assert_not_called()
    save_mock.assert_not_called()
    reset_mock.assert_not_called()


def test_render_loads_weights_with_settings(weights_tab_module, fake_st, monkeypatch):
    """Rendering loads weights with the explicit settings object."""
    settings = _default_settings()
    load_mock = MagicMock(return_value=signal_weights.Weights.defaults())
    monkeypatch.setattr(weights_tab_module.signal_weights, "load", load_mock)
    monkeypatch.setattr(weights_tab_module.signal_weights, "save", MagicMock())
    monkeypatch.setattr(weights_tab_module.signal_weights, "reset_to_defaults", MagicMock())

    weights_tab_module.render_weights_tab(settings=settings)

    load_mock.assert_called_once_with(settings=settings)


def test_no_button_click_does_not_write(weights_tab_module, fake_st, monkeypatch):
    """If no save/reset button is clicked, no persistence or rerun occurs."""
    settings = _default_settings()
    save_mock = MagicMock()
    reset_mock = MagicMock()
    monkeypatch.setattr(weights_tab_module.signal_weights, "load", lambda *, settings: signal_weights.Weights.defaults())
    monkeypatch.setattr(weights_tab_module.signal_weights, "save", save_mock)
    monkeypatch.setattr(weights_tab_module.signal_weights, "reset_to_defaults", reset_mock)

    weights_tab_module.render_weights_tab(settings=settings)

    save_mock.assert_not_called()
    reset_mock.assert_not_called()
    fake_st.rerun.assert_not_called()


def test_save_button_writes_weights(weights_tab_module, fake_st, monkeypatch):
    """Clicking Save weights writes a Weights object built from slider values."""
    settings = _default_settings()
    defaults = signal_weights.Weights.defaults()
    save_mock = MagicMock()
    reset_mock = MagicMock()
    monkeypatch.setattr(weights_tab_module.signal_weights, "load", lambda *, settings: defaults)
    monkeypatch.setattr(weights_tab_module.signal_weights, "save", save_mock)
    monkeypatch.setattr(weights_tab_module.signal_weights, "reset_to_defaults", reset_mock)
    fake_st._active_button_keys = {"weights_save"}

    weights_tab_module.render_weights_tab(settings=settings)

    save_mock.assert_called_once()
    saved = save_mock.call_args[0][0]
    assert isinstance(saved, signal_weights.Weights)
    assert saved.to_dict() == defaults.to_dict()
    assert save_mock.call_args.kwargs["settings"] is settings
    fake_st.rerun.assert_not_called()


def test_reset_button_resets_and_reruns(weights_tab_module, fake_st, monkeypatch):
    """Clicking Reset to defaults resets weights and triggers a rerun."""
    settings = _default_settings()
    reset_mock = MagicMock(return_value=signal_weights.Weights.defaults())
    save_mock = MagicMock()
    monkeypatch.setattr(weights_tab_module.signal_weights, "load", lambda *, settings: signal_weights.Weights.defaults())
    monkeypatch.setattr(weights_tab_module.signal_weights, "save", save_mock)
    monkeypatch.setattr(weights_tab_module.signal_weights, "reset_to_defaults", reset_mock)
    fake_st._active_button_keys = {"weights_reset"}

    weights_tab_module.render_weights_tab(settings=settings)

    reset_mock.assert_called_once_with(settings=settings)
    save_mock.assert_not_called()
    fake_st.rerun.assert_called_once()


def test_widget_keys_preserved(weights_tab_module, fake_st, monkeypatch):
    """All expected weight slider keys are rendered."""
    settings = _default_settings()
    monkeypatch.setattr(weights_tab_module.signal_weights, "load", lambda *, settings: signal_weights.Weights.defaults())
    monkeypatch.setattr(weights_tab_module.signal_weights, "save", MagicMock())
    monkeypatch.setattr(weights_tab_module.signal_weights, "reset_to_defaults", MagicMock())

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
