"""Tests for the extracted Help tab."""
from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture
def help_tab_module(fake_st, monkeypatch):
    """Import the Help tab fresh with a mocked Streamlit."""
    mod_name = "tradex.ui.tabs.help"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    return importlib.import_module(mod_name)


def test_import_does_not_render_or_touch_backend(help_tab_module, fake_st):
    """Importing the Help tab module must not call Streamlit or any backend."""
    assert fake_st.subheader.call_count == 0
    assert fake_st.markdown.call_count == 0
    assert fake_st.expander.call_count == 0
    assert fake_st.code.call_count == 0


def test_render_shows_subheader_and_caption(help_tab_module, fake_st):
    """The Help tab renders its subheader and caption."""
    help_tab_module.render_help_tab()

    fake_st.subheader.assert_called_once_with("TradeX — Help & Documentation")
    caption_texts = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert "Everything you need to understand what each feature does" in " ".join(caption_texts)


def test_render_headings_in_order(help_tab_module, fake_st):
    """The Help tab renders the expected top-level headings in their existing order."""
    expected_headings = [
        "## Getting Started",
        "## Global Settings (Sidebar)",
        "## Scanner",
        "## Coil Detector",
        "## Confluence Scanner",
        "## Pattern Match",
        "## Pre-Market Gap Scanner",
        "## Options Flow",
        "## Alerts",
        "## Signal Journal",
        "## Indicator Glossary",
        "## Running the Background Watcher",
    ]
    help_tab_module.render_help_tab()

    rendered_headings = []
    for call in fake_st.markdown.call_args_list:
        text = call.args[0] if call.args else ""
        if isinstance(text, str) and text.startswith("## "):
            rendered_headings.append(text.strip())

    assert rendered_headings == expected_headings


def test_render_expanders_present(help_tab_module, fake_st):
    """The Help tab preserves the existing expander labels."""
    expected_labels = {
        "Timeframe",
        "Min Score (0–100)",
        "Watchlist",
        "What the Scanner does",
        "What a coil is and how to use it",
        "Multi-timeframe alignment explained",
        "Fingerprinting and similarity scoring explained",
        "Gaps explained",
        "Options basics and how to read flow",
        "Setting up Discord and email alerts",
        "Understanding your signal history and outcomes",
        "RSI — Relative Strength Index",
        "MACD — Moving Average Convergence Divergence",
        "EMA — Exponential Moving Average",
        "Bollinger Bands",
        "Volume Ratio",
        "ATR — Average True Range",
    }
    help_tab_module.render_help_tab()

    expander_labels = {str(c[0][0]) for c in fake_st.expander.call_args_list}
    assert expected_labels.issubset(expander_labels)


def test_render_watcher_code_block_present(help_tab_module, fake_st):
    """The background-watcher code block is still rendered."""
    help_tab_module.render_help_tab()

    code_blocks = [str(c[0][0]) for c in fake_st.code.call_args_list]
    assert any(".venv/bin/python -m tradex.tracker.watcher" in block for block in code_blocks)
    assert any(call.kwargs.get("language") == "bash" for call in fake_st.code.call_args_list)


def test_render_no_interactive_inputs(help_tab_module, fake_st):
    """The Help tab does not use interactive inputs, selectors, or persistence."""
    help_tab_module.render_help_tab()

    assert fake_st.button.call_count == 0
    assert fake_st.text_input.call_count == 0
    assert fake_st.text_area.call_count == 0
    assert fake_st.selectbox.call_count == 0
    assert fake_st.slider.call_count == 0
    assert fake_st.multiselect.call_count == 0
    assert fake_st.checkbox.call_count == 0


def test_render_help_tab_accepts_no_arguments(help_tab_module):
    """render_help_tab is parameter-free and relies on no hidden globals."""
    help_tab_module.render_help_tab()
