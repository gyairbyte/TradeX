"""Tests for the extracted Signal Journal tab."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.config import TradeXSettings, load_runtime_settings


def _default_settings() -> TradeXSettings:
    return load_runtime_settings()


@pytest.fixture
def signal_journal_module(fake_st, monkeypatch):
    """Import the Signal Journal tab with a mocked Streamlit and patched store."""
    from tradex.ui import tabs

    mod = importlib.reload(tabs.signal_journal)
    monkeypatch.setattr(mod, "st", fake_st)
    return mod


def test_import_has_no_side_effects(fake_st, monkeypatch):
    """Importing the tab module must not touch Streamlit widgets or backend logic."""
    monkeypatch.setattr("sys.modules", dict(sys.modules, streamlit=fake_st))
    mock_store = MagicMock()
    mock_store.get_signal_journal.return_value = pd.DataFrame()
    monkeypatch.setattr("tradex.ui.tabs.signal_journal.store", mock_store)
    monkeypatch.setattr("tradex.ui.tabs.signal_journal.run_outcome_pass", MagicMock())
    monkeypatch.setattr("tradex.ui.tabs.signal_journal.get_outcome_stats", MagicMock())
    monkeypatch.setattr("tradex.ui.tabs.signal_journal.resolve_provider", MagicMock(return_value="yahoo"))

    mod = importlib.import_module("tradex.ui.tabs.signal_journal")

    assert fake_st.subheader.call_count == 0
    assert mock_store.get_signal_journal.call_count == 0
    assert mod.run_outcome_pass.call_count == 0
    assert mod.get_outcome_stats.call_count == 0


def test_empty_journal_shows_info(signal_journal_module, fake_st, monkeypatch):
    """An empty journal displays the existing empty-state message."""
    settings = _default_settings()
    monkeypatch.setattr(
        signal_journal_module.store,
        "get_signal_journal",
        lambda *, timeframe, settings: pd.DataFrame(columns=["outcome_pct", "signal_provider", "outcome_provider"]),
    )
    monkeypatch.setattr(signal_journal_module, "resolve_provider", lambda provider, **kwargs: provider or "yahoo")

    signal_journal_module.render_signal_journal_tab(settings=settings, timeframe="short", provider="yahoo")

    info_calls = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("No outcomes yet" in c for c in info_calls)
    assert fake_st.dataframe.call_count == 0
    assert fake_st.plotly_chart.call_count == 0


def test_refresh_button_calls_run_outcome_pass(signal_journal_module, fake_st, monkeypatch):
    """Clicking Refresh Outcomes Now calls run_outcome_pass exactly once."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_outcomes"}
    run_mock = MagicMock(return_value={"resolved": 3, "pending": 1, "errors": 0})
    monkeypatch.setattr(signal_journal_module, "run_outcome_pass", run_mock)
    monkeypatch.setattr(signal_journal_module, "resolve_provider", lambda provider, **kwargs: provider or "yahoo")
    monkeypatch.setattr(
        signal_journal_module.store,
        "get_signal_journal",
        lambda *, timeframe, settings: pd.DataFrame(columns=["outcome_pct", "signal_provider", "outcome_provider"]),
    )

    signal_journal_module.render_signal_journal_tab(settings=settings, timeframe="short", provider="yahoo")

    run_mock.assert_called_once()
    _, kwargs = run_mock.call_args
    assert kwargs["provider"] == "yahoo"
    assert kwargs["settings"] is settings
    success_calls = [str(c[0][0]) for c in fake_st.success.call_args_list]
    assert any("Resolved 3" in c and "1 pending" in c for c in success_calls)


def test_no_refresh_button_does_not_call_run_outcome_pass(signal_journal_module, fake_st, monkeypatch):
    """Without a button click, run_outcome_pass is not invoked."""
    settings = _default_settings()
    run_mock = MagicMock(return_value={"resolved": 0, "pending": 0, "errors": 0})
    monkeypatch.setattr(signal_journal_module, "run_outcome_pass", run_mock)
    monkeypatch.setattr(signal_journal_module, "resolve_provider", lambda provider, **kwargs: provider or "yahoo")
    monkeypatch.setattr(
        signal_journal_module.store,
        "get_signal_journal",
        lambda *, timeframe, settings: pd.DataFrame(columns=["outcome_pct", "signal_provider", "outcome_provider"]),
    )

    signal_journal_module.render_signal_journal_tab(settings=settings, timeframe="short", provider="yahoo")

    run_mock.assert_not_called()


def test_nonempty_journal_renders_metrics(signal_journal_module, fake_st, monkeypatch):
    """A non-empty journal renders total signals, win rate, avg win/loss, and expectancy."""
    settings = _default_settings()
    monkeypatch.setattr(signal_journal_module, "resolve_provider", lambda provider, **kwargs: provider or "yahoo")
    monkeypatch.setattr(signal_journal_module, "get_outcome_stats", lambda *, settings: pd.DataFrame())
    journal = pd.DataFrame({
        "outcome_pct": [5.0, -2.0, 3.0, -1.5],
        "signal_provider": ["yahoo", "yahoo", "yahoo", "yahoo"],
        "outcome_provider": ["yahoo", "yahoo", "yahoo", "yahoo"],
    })
    monkeypatch.setattr(
        signal_journal_module.store,
        "get_signal_journal",
        lambda *, timeframe, settings: journal,
    )

    signal_journal_module.render_signal_journal_tab(settings=settings, timeframe="short", provider="yahoo")

    metric_labels = []
    for cols in fake_st._column_returns:
        for col in cols:
            for call in col.metric.call_args_list:
                metric_labels.append(call[0][0])
    assert "Total Signals" in metric_labels
    assert "Win Rate" in metric_labels
    assert "Avg Win" in metric_labels
    assert "Avg Loss" in metric_labels
    assert "Expectancy" in metric_labels
    assert fake_st.dataframe.call_count >= 1
    assert fake_st.plotly_chart.call_count >= 1


def test_provider_mismatch_caption(signal_journal_module, fake_st, monkeypatch):
    """A provider mismatch produces the existing mismatch caption."""
    settings = _default_settings()
    monkeypatch.setattr(signal_journal_module, "resolve_provider", lambda provider, **kwargs: provider or "yahoo")
    monkeypatch.setattr(signal_journal_module, "get_outcome_stats", lambda *, settings: pd.DataFrame())
    journal = pd.DataFrame({
        "outcome_pct": [1.0],
        "signal_provider": ["yahoo"],
        "outcome_provider": ["alpaca"],
    })
    monkeypatch.setattr(
        signal_journal_module.store,
        "get_signal_journal",
        lambda *, timeframe, settings: journal,
    )

    signal_journal_module.render_signal_journal_tab(settings=settings, timeframe="short", provider="yahoo")

    caption_calls = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert any("different OHLCV provider" in c for c in caption_calls)


def test_score_bucket_stats_render(signal_journal_module, fake_st, monkeypatch):
    """Score-bucket statistics table and chart render when data exists."""
    settings = _default_settings()
    monkeypatch.setattr(signal_journal_module, "resolve_provider", lambda provider, **kwargs: provider or "yahoo")
    stats = pd.DataFrame({
        "timeframe": ["short"],
        "score_bucket": ["60-79"],
        "avg_return_pct": [2.5],
        "win_rate_pct": [60.0],
        "best": [5.0],
        "worst": [-1.0],
        "total": [10],
    })
    monkeypatch.setattr(signal_journal_module, "get_outcome_stats", lambda *, settings: stats)
    journal = pd.DataFrame({
        "outcome_pct": [1.0],
        "signal_provider": ["yahoo"],
        "outcome_provider": ["yahoo"],
    })
    monkeypatch.setattr(
        signal_journal_module.store,
        "get_signal_journal",
        lambda *, timeframe, settings: journal,
    )

    signal_journal_module.render_signal_journal_tab(settings=settings, timeframe="short", provider="yahoo")

    assert fake_st.dataframe.call_count >= 2
    assert fake_st.plotly_chart.call_count >= 2
