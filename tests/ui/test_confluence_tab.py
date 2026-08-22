"""Tests for the extracted Confluence tab."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.config import TradeXSettings, settings_from_mapping
from tradex.data.fetcher import ProviderDataUnavailableError
from tradex.tracker.confluence import ConfluenceReport


def _default_settings() -> TradeXSettings:
    return settings_from_mapping({})


def _confluence_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "confluence_score": [85],
            "tier": ["strong confluence"],
            "timeframe_coverage": ["2/3"],
            "available_timeframes": ["short, long"],
            "missing_timeframes": ["intraday"],
            "active_timeframes": ["short, long"],
            "score_intraday": ["-"],
            "score_short": [70],
            "score_long": [65],
            "days_until_earnings": [12],
            "last_close": [150.0],
        }
    )


@pytest.fixture
def confluence_module(fake_st, monkeypatch):
    """Import the Confluence tab fresh with mocked Streamlit and backend."""
    mod_name = "tradex.ui.tabs.confluence"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    mod = importlib.import_module(mod_name)

    empty_report = ConfluenceReport(
        results=pd.DataFrame(),
        total_requested=0,
        total_scored=0,
        total_earnings_excluded=0,
    )
    run_mock = MagicMock(return_value=empty_report)
    monkeypatch.setattr(mod, "run_confluence_screen_with_report", run_mock)
    yield mod
    sys.modules.pop(mod_name, None)


def test_import_has_no_side_effects(fake_st, monkeypatch):
    """Importing the tab module must not render widgets or call the confluence backend."""
    mod_name = "tradex.ui.tabs.confluence"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    run_mock = MagicMock()
    monkeypatch.setattr("tradex.tracker.confluence.run_confluence_screen_with_report", run_mock)

    importlib.import_module(mod_name)

    assert fake_st.subheader.call_count == 0
    assert fake_st.caption.call_count == 0
    assert run_mock.call_count == 0


def test_initial_render_shows_subheader_caption_and_slider(confluence_module, fake_st):
    """The initial render shows the expected heading, caption, expander, evidence notice, and slider."""
    settings = _default_settings()

    confluence_module.render_confluence_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    assert fake_st.subheader.call_count == 1
    subheader = str(fake_st.subheader.call_args[0][0])
    assert "Confluence Scanner" in subheader

    info_texts = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("Exploratory Context — Multi-Timeframe Alignment" in t for t in info_texts)

    caption_texts = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert any("timeframe" in t.lower() for t in caption_texts)

    assert fake_st.expander.call_count == 1
    assert fake_st.slider.call_count == 1
    assert fake_st.slider.call_args.args == ("Min confluence score", 0, 100, 50)
    assert fake_st.slider.call_args.kwargs.get("key") == "min_conf"

    confluence_module.run_confluence_screen_with_report.assert_not_called()


def test_zero_earnings_buffer_passes_none(confluence_module, fake_st):
    """Clicking Run Confluence Scan with buffer 0 passes exclude_earnings_within=None."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_conf"}
    watchlist = ["AAPL", "MSFT"]

    confluence_module.render_confluence_tab(
        settings=settings,
        watchlist=watchlist,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    confluence_module.run_confluence_screen_with_report.assert_called_once()
    args, kwargs = confluence_module.run_confluence_screen_with_report.call_args
    assert args[0] is watchlist
    assert kwargs["settings"] is settings
    assert kwargs["min_confluence"] == 50
    assert kwargs["exclude_earnings_within"] is None
    assert kwargs["provider"] == "yahoo"
    assert kwargs["earnings_source"] == "yahoo"


def test_positive_earnings_buffer_passes_integer(confluence_module, fake_st):
    """Clicking Run Confluence Scan with a positive buffer passes the integer unchanged."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_conf"}

    confluence_module.render_confluence_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        earnings_buffer=5,
        provider="yahoo",
        earnings_source="yahoo",
    )

    _args, kwargs = confluence_module.run_confluence_screen_with_report.call_args
    assert kwargs["exclude_earnings_within"] == 5


def test_watchlist_not_mutated(confluence_module, fake_st):
    """The renderer must not mutate the supplied watchlist."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_conf"}
    watchlist = ["AAPL", "MSFT", "NVDA"]
    original = watchlist.copy()

    confluence_module.render_confluence_tab(
        settings=settings,
        watchlist=watchlist,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    args, _ = confluence_module.run_confluence_screen_with_report.call_args
    assert args[0] is watchlist
    assert watchlist == original


def test_empty_result_shows_warning(confluence_module, fake_st):
    """Empty confluence results show the existing warning and do not store results."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_conf"}

    confluence_module.render_confluence_tab(
        settings=settings,
        watchlist=["AAPL"],
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    warning_texts = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert any("No confluence setups" in t for t in warning_texts)

    assert fake_st.dataframe.call_count == 0
    assert "conf_results" not in fake_st.session_state


def test_populated_result_stores_exact_dataframe(confluence_module, fake_st):
    """Populated confluence results store the exact returned DataFrame in session state."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_conf"}
    results = _confluence_df()
    confluence_module.run_confluence_screen_with_report.return_value = ConfluenceReport(
        results=results,
        total_requested=1,
        total_scored=1,
        total_earnings_excluded=0,
    )

    confluence_module.render_confluence_tab(
        settings=settings,
        watchlist=["AAPL"],
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    success_texts = [str(c[0][0]) for c in fake_st.success.call_args_list]
    assert any("multi-timeframe setups found" in t for t in success_texts)
    assert all("earnings" not in t.lower() for t in success_texts)

    assert fake_st.dataframe.call_count == 1
    _, df_kwargs = fake_st.dataframe.call_args
    expected_config_keys = {
        "ticker",
        "confluence_score",
        "tier",
        "timeframe_coverage",
        "available_timeframes",
        "missing_timeframes",
        "active_timeframes",
        "score_intraday",
        "score_short",
        "score_long",
        "days_until_earnings",
        "last_close",
    }
    assert set(df_kwargs.get("column_config", {}).keys()) == expected_config_keys
    assert fake_st.session_state["conf_results"] is results


def test_positive_buffer_success_wording(confluence_module, fake_st):
    """Populated results with a positive buffer include the existing earnings-exclusion wording."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_conf"}
    confluence_module.run_confluence_screen_with_report.return_value = ConfluenceReport(
        results=_confluence_df(),
        total_requested=1,
        total_scored=1,
        total_earnings_excluded=0,
    )

    confluence_module.render_confluence_tab(
        settings=settings,
        watchlist=["AAPL"],
        earnings_buffer=3,
        provider="yahoo",
        earnings_source="yahoo",
    )

    success_texts = [str(c[0][0]) for c in fake_st.success.call_args_list]
    assert any("excluded tickers with earnings within 3d" in t for t in success_texts)


def test_earnings_failure_warning_when_buffer_active(confluence_module, fake_st):
    """Earnings failures with active buffer render an explicit warning indicating excluded tickers."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_conf"}
    confluence_module.run_confluence_screen_with_report.return_value = ConfluenceReport(
        results=_confluence_df(),
        earnings_failures={"BADTICKER": ProviderDataUnavailableError("lookup failed")},
        total_requested=2,
        total_scored=1,
        total_earnings_excluded=0,
    )

    confluence_module.render_confluence_tab(
        settings=settings,
        watchlist=["AAPL", "BADTICKER"],
        earnings_buffer=5,
        provider="yahoo",
        earnings_source="yahoo",
    )

    warning_texts = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert any("Earnings date unavailable for 1 symbol(s)" in t and "BADTICKER" in t for t in warning_texts)


def test_earnings_failure_info_when_buffer_zero(confluence_module, fake_st):
    """Earnings failures with zero buffer render an informational message that ticker scored normally."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_conf"}
    confluence_module.run_confluence_screen_with_report.return_value = ConfluenceReport(
        results=_confluence_df(),
        earnings_failures={"BADTICKER": ProviderDataUnavailableError("lookup failed")},
        total_requested=2,
        total_scored=2,
        total_earnings_excluded=0,
    )

    confluence_module.render_confluence_tab(
        settings=settings,
        watchlist=["AAPL", "BADTICKER"],
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    info_texts = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("Earnings date unavailable for 1 symbol(s)" in t and "scored normally" in t for t in info_texts)


def test_existing_session_state_drill_down(confluence_module, fake_st, monkeypatch):
    """Pre-populated conf_results render the drill-down bar chart with the expected title."""
    settings = _default_settings()
    results = _confluence_df()
    fake_st.session_state["conf_results"] = results

    bar_mock = MagicMock()
    monkeypatch.setattr(confluence_module.px, "bar", MagicMock(return_value=bar_mock))

    confluence_module.render_confluence_tab(
        settings=settings,
        watchlist=["AAPL"],
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    selectbox_keys = {call.kwargs.get("key") for call in fake_st.selectbox.call_args_list}
    assert "sel_conf" in selectbox_keys

    confluence_module.px.bar.assert_called_once()
    _, kwargs = confluence_module.px.bar.call_args
    assert kwargs["x"] == ["Intraday", "Short", "Long"]
    assert list(kwargs["y"]) == ["-", 70, 65]
    assert "AAPL" in kwargs["title"]
    assert "85" in kwargs["title"]
    assert "strong confluence" in kwargs["title"]
    assert kwargs["color_continuous_scale"] == "RdYlGn"
    assert kwargs["range_color"] == [0, 100]

    assert fake_st.plotly_chart.call_count == 1
    _, plot_kwargs = fake_st.plotly_chart.call_args
    assert plot_kwargs.get("use_container_width") is True
    bar_mock.update_layout.assert_called_once_with(height=350, showlegend=False)
    assert fake_st.plotly_chart.call_args[0][0] is bar_mock


def test_widget_keys_preserved(confluence_module, fake_st):
    """All expected Confluence widget keys, labels, ranges, and defaults are rendered."""
    settings = _default_settings()

    confluence_module.render_confluence_tab(
        settings=settings,
        watchlist=["AAPL"],
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    assert fake_st.slider.call_count == 1
    assert fake_st.slider.call_args.args == ("Min confluence score", 0, 100, 50)
    assert fake_st.slider.call_args.kwargs.get("key") == "min_conf"

    button_keys = {call.kwargs.get("key") for call in fake_st.button.call_args_list}
    assert button_keys == {"btn_conf"}
