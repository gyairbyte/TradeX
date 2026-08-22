"""Tests for the extracted Pattern Similarity tab."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.config import TradeXSettings, settings_from_mapping


def _default_settings() -> TradeXSettings:
    return settings_from_mapping({})


def _match_results_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT"],
            "similarity_score": [82, 76],
            "match_tier": ["high", "high"],
            "fp_events": [25, 30],
            "score_price": [80, 70],
            "score_volume": [85, 75],
            "score_rsi": [78, 80],
            "interpretation": ["Strong shape match", "Good shape match"],
        }
    )


def _detail_dict(*, with_volume: bool = True, error: str | None = None) -> dict:
    if error:
        return {"error": error}
    detail = {
        "similarity_score": 82,
        "match_tier": "high",
        "interpretation": "Strong shape match",
        "series_scores": {
            "price_pct": 80.0,
            "volume_ratio": 85.0,
            "rsi": 78.0,
        },
        "fp_series": {
            "price_pct": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
        },
        "live_series": {
            "price_pct": list(range(10)),
        },
    }
    if with_volume:
        detail["fp_series"]["volume_ratio"] = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9]
        detail["live_series"]["volume_ratio"] = [0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8]
    return detail


def _fingerprint_data() -> dict:
    return {
        "series": {
            "price_pct": {
                "upper": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                "lower": [-1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            }
        }
    }


def _selectbox(label, *args, **kwargs):
    for arg in args:
        if isinstance(arg, (list, tuple)) and arg:
            return arg[0]
    return kwargs.get("index")


@pytest.fixture
def pattern_module(fake_st, monkeypatch):
    """Import the Pattern Similarity tab fresh with mocked Streamlit and backends."""
    mod_name = "tradex.ui.tabs.pattern_similarity"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    # Ensure column selectboxes return the first option deterministically.
    original_columns = fake_st.columns.side_effect
    def _columns_with_selectbox(spec, *args, **kwargs):
        cols = original_columns(spec, *args, **kwargs)
        for col in cols:
            col.selectbox.side_effect = _selectbox
        return cols
    fake_st.columns.side_effect = _columns_with_selectbox

    mod = importlib.import_module(mod_name)

    mod.list_fingerprints = MagicMock(return_value=pd.DataFrame())
    mod.run_full_build = MagicMock(return_value={})
    mod.load_fingerprint = MagicMock(return_value=None)
    mod.run_match_screen = MagicMock(return_value=pd.DataFrame())
    mod.match_ticker = MagicMock(return_value=_detail_dict())

    yield mod
    sys.modules.pop(mod_name, None)


def test_import_has_no_side_effects(fake_st, monkeypatch):
    """Importing the tab module must not render widgets or call backend functions."""
    mod_name = "tradex.ui.tabs.pattern_similarity"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    list_fingerprints = MagicMock()
    run_full_build = MagicMock()
    load_fingerprint = MagicMock()
    run_match_screen = MagicMock()
    match_ticker = MagicMock()
    monkeypatch.setattr("tradex.patterns.fingerprint.list_fingerprints", list_fingerprints)
    monkeypatch.setattr("tradex.patterns.fingerprint.run_full_build", run_full_build)
    monkeypatch.setattr("tradex.patterns.fingerprint.load_fingerprint", load_fingerprint)
    monkeypatch.setattr("tradex.patterns.matcher.run_match_screen", run_match_screen)
    monkeypatch.setattr("tradex.patterns.matcher.match_ticker", match_ticker)

    importlib.import_module(mod_name)

    assert fake_st.subheader.call_count == 0
    assert fake_st.warning.call_count == 0
    assert list_fingerprints.call_count == 0
    assert run_full_build.call_count == 0
    assert load_fingerprint.call_count == 0
    assert run_match_screen.call_count == 0
    assert match_ticker.call_count == 0


def test_initial_render_shows_header_and_controls(pattern_module, fake_st):
    """The initial render displays the expected warnings, expanders, and controls."""
    settings = _default_settings()
    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    subheader_calls = [str(c[0][0]) for c in fake_st.subheader.call_args_list]
    assert any("Pattern Similarity — Experimental Research" in s for s in subheader_calls)

    warning_calls = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert any("experimental" in w for w in warning_calls)
    assert any("Rejected on Holdout" in w for w in warning_calls)

    caption_calls = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert any("Pearson correlation" in c for c in caption_calls)

    expander_labels = [str(c[0][0]) for c in fake_st.expander.call_args_list]
    assert any("How pattern similarity works" in e for e in expander_labels)
    assert any("Step 1 — Build Fingerprints" in e for e in expander_labels)

    button_labels = [str(c[0][0]) for c in fake_st.button.call_args_list]
    assert "Build Fingerprints" in button_labels
    assert "Run Pattern Screen" in button_labels

    assert pattern_module.list_fingerprints.call_count == 1
    assert pattern_module.list_fingerprints.call_args == ((),)
    assert pattern_module.run_full_build.call_count == 0
    assert pattern_module.run_match_screen.call_count == 0
    assert pattern_module.match_ticker.call_count == 0


def _all_selectbox_calls(fake_st):
    """Collect selectbox calls from the top-level streamlit and column widgets."""
    calls = list(fake_st.selectbox.call_args_list)
    for col_list in fake_st._column_returns:
        for col in col_list:
            calls.extend(col.selectbox.call_args_list)
    return calls


def _all_slider_calls(fake_st):
    """Collect slider calls from the top-level streamlit and column widgets."""
    calls = list(fake_st.slider.call_args_list)
    for col_list in fake_st._column_returns:
        for col in col_list:
            calls.extend(col.slider.call_args_list)
    return calls


def _all_metric_calls(fake_st):
    """Collect metric calls from the top-level streamlit and column widgets."""
    calls = list(fake_st.metric.call_args_list)
    for col_list in fake_st._column_returns:
        for col in col_list:
            calls.extend(col.metric.call_args_list)
    return calls


def test_build_control_contract(pattern_module, fake_st):
    """Build controls use the expected options, keys, and metric."""
    settings = _default_settings()
    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    selectbox_calls = _all_selectbox_calls(fake_st)
    fp_profile_call = next(c for c in selectbox_calls if c.kwargs.get("key") == "fp_profile")
    assert fp_profile_call[0][0] == "Profile"
    assert list(fp_profile_call[0][1]) == ["conservative", "standard", "volatile"]
    assert fp_profile_call[1]["index"] == 1
    assert fp_profile_call[1]["key"] == "fp_profile"

    fp_etype_call = next(c for c in selectbox_calls if c.kwargs.get("key") == "fp_etype")
    assert fp_etype_call[0][0] == "Event type"
    assert list(fp_etype_call[0][1]) == ["both", "runup", "decline"]
    assert fp_etype_call[1]["key"] == "fp_etype"

    metric_calls = _all_metric_calls(fake_st)
    metric_call = next(c for c in metric_calls if c[0][0] == "Move threshold")
    assert metric_call is not None

    button_call = next(c for c in fake_st.button.call_args_list if c[0][0] == "Build Fingerprints")
    assert button_call[1]["key"] == "btn_build_fp"


def test_stored_fingerprints_listing_empty_and_populated(pattern_module, fake_st):
    """list_fingerprints is called once and the DataFrame is displayed when populated."""
    settings = _default_settings()
    existing = pd.DataFrame({"profile": ["standard"], "event": ["runup"]})
    pattern_module.list_fingerprints.return_value = existing

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    assert pattern_module.list_fingerprints.call_count == 1
    assert pattern_module.list_fingerprints.call_args == ((),)

    markdown_calls = [str(c[0][0]) for c in fake_st.markdown.call_args_list]
    assert any("Stored fingerprints" in m for m in markdown_calls)

    df_call = fake_st.dataframe.call_args
    assert df_call[0][0] is existing
    assert df_call.kwargs.get("use_container_width") is True


def test_successful_fingerprint_build(pattern_module, fake_st):
    """Clicking Build Fingerprints calls run_full_build with the correct contract."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_build_fp"}
    pattern_module.run_full_build.return_value = {"runup": "standard", "decline": "standard"}

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    assert pattern_module.run_full_build.call_count == 1
    _, kwargs = pattern_module.run_full_build.call_args
    assert kwargs["profile"] == "conservative"  # fake_st.selectbox returns first option
    assert kwargs["event_type"] == "both"       # fake_st.selectbox returns first option
    assert kwargs["verbose"] is False
    assert kwargs["provider"] == "yahoo"
    assert kwargs["settings"] is settings
    assert "watchlist" not in kwargs
    assert "tickers" not in kwargs

    success_calls = [str(c[0][0]) for c in fake_st.success.call_args_list]
    assert any("Built fingerprints" in s for s in success_calls)


def test_empty_fingerprint_build(pattern_module, fake_st):
    """An empty build result shows the existing 'not enough historical events' error."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_build_fp"}
    pattern_module.run_full_build.return_value = {}

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    error_calls = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("not enough historical events" in e for e in error_calls)


def test_provider_capability_failure_during_build(pattern_module, fake_st):
    """ProviderCapabilityError during build is surfaced exactly once."""
    from tradex.data.fetcher import ProviderCapabilityError

    settings = _default_settings()
    fake_st._active_button_keys = {"btn_build_fp"}
    pattern_module.run_full_build.side_effect = ProviderCapabilityError("Provider not configured")

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    error_calls = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("Provider not configured" in e for e in error_calls)
    assert pattern_module.run_full_build.call_count == 1
    assert pattern_module.list_fingerprints.call_count == 1


def test_match_control_contract(pattern_module, fake_st):
    """Match controls use the expected options, keys, and slider defaults."""
    settings = _default_settings()
    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    selectbox_calls = _all_selectbox_calls(fake_st)
    match_profile_call = next(c for c in selectbox_calls if c.kwargs.get("key") == "match_profile")
    assert match_profile_call[0][0] == "Profile"
    assert list(match_profile_call[0][1]) == ["conservative", "standard", "volatile"]
    assert match_profile_call[1]["index"] == 1
    assert match_profile_call[1]["key"] == "match_profile"

    match_etype_call = next(c for c in selectbox_calls if c.kwargs.get("key") == "match_etype")
    assert match_etype_call[0][0] == "Pattern type"
    assert list(match_etype_call[0][1]) == ["runup", "decline"]
    assert match_etype_call[1]["key"] == "match_etype"

    slider_calls = _all_slider_calls(fake_st)
    slider_call = next(c for c in slider_calls if c[0][0] == "Min similarity")
    assert slider_call[0][1] == 0
    assert slider_call[0][2] == 100
    assert slider_call[1]["key"] == "match_thresh"

    button_call = next(c for c in fake_st.button.call_args_list if c[0][0] == "Run Pattern Screen")
    assert button_call[1]["key"] == "btn_match"
    assert button_call[1]["type"] == "primary"


def test_missing_fingerprint_preflight(pattern_module, fake_st):
    """If load_fingerprint returns None, run_match_screen is not called and state is unchanged."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_match"}
    pattern_module.load_fingerprint.return_value = None

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    assert pattern_module.load_fingerprint.call_count == 1
    _, kwargs = pattern_module.load_fingerprint.call_args
    assert kwargs["source"] == "yahoo"
    assert kwargs["settings"] is settings
    assert pattern_module.run_match_screen.call_count == 0
    assert fake_st.session_state.get("match_results") is None

    error_calls = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("Build it first" in e for e in error_calls)


def test_match_screen_call_contract(pattern_module, fake_st):
    """Clicking Run Pattern Screen calls run_match_screen with the exact contract."""
    settings = _default_settings()
    watchlist = ["AAPL", "MSFT"]
    fake_st._active_button_keys = {"btn_match"}
    pattern_module.load_fingerprint.return_value = _fingerprint_data()
    pattern_module.run_match_screen.return_value = _match_results_df()

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=watchlist,
        provider="yahoo",
    )

    assert pattern_module.run_match_screen.call_count == 1
    args, kwargs = pattern_module.run_match_screen.call_args
    assert args[0] is watchlist
    assert args[0] == ["AAPL", "MSFT"]
    assert kwargs["event_type"] == "runup"  # fake selectbox returns first option
    assert kwargs["profile"] == "conservative"
    assert kwargs["min_similarity"] == 78    # conservative alert_threshold int
    assert kwargs["provider"] == "yahoo"
    assert kwargs["settings"] is settings


def test_empty_match_result(pattern_module, fake_st):
    """Empty match results show the threshold-specific warning and do not write session state."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_match"}
    pattern_module.load_fingerprint.return_value = _fingerprint_data()
    pattern_module.run_match_screen.return_value = pd.DataFrame()

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    warning_calls = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert any("No tickers matched above" in w for w in warning_calls)
    assert fake_st.session_state.get("match_results") is None


def test_populated_match_result_writes_session_state(pattern_module, fake_st):
    """Populated match results are displayed and saved to session state unchanged."""
    settings = _default_settings()
    watchlist = ["AAPL", "MSFT"]
    fake_st._active_button_keys = {"btn_match"}
    pattern_module.load_fingerprint.return_value = _fingerprint_data()
    results = _match_results_df()
    pattern_module.run_match_screen.return_value = results

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=watchlist,
        provider="yahoo",
    )

    df_call = fake_st.dataframe.call_args
    assert df_call[0][0] is results
    assert df_call.kwargs.get("use_container_width") is True

    config = df_call.kwargs.get("column_config", {})
    expected_keys = {
        "ticker", "similarity_score", "match_tier", "fp_events",
        "score_price", "score_volume", "score_rsi", "interpretation",
    }
    assert set(config.keys()) == expected_keys

    assert fake_st.session_state["match_results"] is results
    assert fake_st.session_state["match_etype_saved"] == "runup"
    assert fake_st.session_state["match_profile_saved"] == "conservative"
    assert fake_st.session_state["match_source_saved"] == "yahoo"


def test_drill_down_renders_without_new_screen(pattern_module, fake_st):
    """Pre-populated match state renders drill-down without calling run_match_screen."""
    settings = _default_settings()
    results = _match_results_df()
    fake_st.session_state["match_results"] = results
    fake_st.session_state["match_etype_saved"] = "runup"
    fake_st.session_state["match_profile_saved"] = "standard"
    fake_st.session_state["match_source_saved"] = "yahoo"
    pattern_module.load_fingerprint.return_value = _fingerprint_data()

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    assert pattern_module.run_match_screen.call_count == 0
    assert pattern_module.match_ticker.call_count == 1
    args, kwargs = pattern_module.match_ticker.call_args
    assert args[0] == "AAPL"  # first ticker in saved results
    assert kwargs["event_type"] == "runup"
    assert kwargs["profile"] == "standard"
    assert kwargs["provider"] == "yahoo"
    assert kwargs["settings"] is settings


def test_drill_down_uses_current_provider_when_saved_source_missing(pattern_module, fake_st):
    """When match_source_saved is absent, match_ticker falls back to the current provider."""
    settings = _default_settings()
    results = _match_results_df()
    fake_st.session_state["match_results"] = results
    fake_st.session_state["match_etype_saved"] = "runup"
    fake_st.session_state["match_profile_saved"] = "standard"
    # match_source_saved intentionally omitted
    pattern_module.load_fingerprint.return_value = _fingerprint_data()

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="alpaca",
    )

    _, kwargs = pattern_module.match_ticker.call_args
    assert kwargs["provider"] == "alpaca"


def test_detail_error_renders_no_metrics_or_charts(pattern_module, fake_st):
    """A detail error is displayed and no metrics/charts are rendered."""
    settings = _default_settings()
    results = _match_results_df()
    fake_st.session_state["match_results"] = results
    fake_st.session_state["match_etype_saved"] = "runup"
    fake_st.session_state["match_profile_saved"] = "standard"
    pattern_module.match_ticker.return_value = _detail_dict(error="Fingerprint missing")

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    error_calls = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("Fingerprint missing" in e for e in error_calls)
    assert fake_st.metric.call_count == 0
    assert fake_st.plotly_chart.call_count == 0


def test_detail_metrics_and_interpretation(pattern_module, fake_st):
    """Successful detail renders the four metrics and interpretation info."""
    settings = _default_settings()
    results = _match_results_df()
    fake_st.session_state["match_results"] = results
    fake_st.session_state["match_etype_saved"] = "runup"
    fake_st.session_state["match_profile_saved"] = "standard"
    pattern_module.load_fingerprint.return_value = _fingerprint_data()

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    metric_labels = [c[0][0] for c in _all_metric_calls(fake_st)]
    assert "Overall Similarity" in metric_labels
    assert "Price shape" in metric_labels
    assert "Volume shape" in metric_labels
    assert "RSI shape" in metric_labels

    info_calls = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("HIGH" in i and "Strong shape match" in i for i in info_calls)


def test_overlay_fingerprint_reloads_with_saved_context(pattern_module, fake_st):
    """The overlay reloads the fingerprint using saved event type/profile/source."""
    settings = _default_settings()
    results = _match_results_df()
    fake_st.session_state["match_results"] = results
    fake_st.session_state["match_etype_saved"] = "decline"
    fake_st.session_state["match_profile_saved"] = "volatile"
    fake_st.session_state["match_source_saved"] = "alpaca"
    pattern_module.load_fingerprint.return_value = _fingerprint_data()

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    # With btn_match not clicked, only the overlay reload is invoked.
    assert pattern_module.load_fingerprint.call_count == 1
    _, kwargs = pattern_module.load_fingerprint.call_args
    assert kwargs["source"] == "alpaca"
    assert kwargs["settings"] is settings


def test_price_overlay_chart_contract(pattern_module, fake_st):
    """The price overlay chart contains the four expected traces and layout."""
    settings = _default_settings()
    results = _match_results_df()
    fake_st.session_state["match_results"] = results
    fake_st.session_state["match_etype_saved"] = "runup"
    fake_st.session_state["match_profile_saved"] = "standard"
    pattern_module.load_fingerprint.return_value = _fingerprint_data()

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    assert fake_st.plotly_chart.call_count == 2
    price_call = fake_st.plotly_chart.call_args_list[0]
    price_fig = price_call[0][0]
    assert price_call.kwargs.get("use_container_width") is True

    assert len(price_fig.data) == 4
    trace_types = [t.type for t in price_fig.data]
    assert trace_types == ["scatter", "scatter", "scatter", "scatter"]
    trace_names = [t.name for t in price_fig.data]
    assert trace_names == [None, "Historical range ±1σ", "Historical avg", "AAPL (live)"]

    upper, lower, avg, live = price_fig.data
    assert upper.mode == "lines"
    assert upper.line.width == 0
    assert lower.line.width == 0
    assert lower.fill == "tonexty"
    assert lower.fillcolor == "rgba(255,165,0,0.15)"
    assert avg.line.color == "orange"
    assert avg.line.dash == "dash"
    assert avg.line.width == 2
    assert live.mode == "lines+markers"
    assert live.line.color == "white"
    assert live.line.width == 2

    assert price_fig.layout.title.text == "Price % — Live vs Historical Fingerprint"
    assert price_fig.layout.xaxis.title.text == "Days before move"
    assert price_fig.layout.yaxis.title.text == "% from window start"
    assert price_fig.layout.height == 400

    # X values should be -n+1 .. 0
    n = len(price_fig.data[2].y)
    assert list(price_fig.data[2].x) == list(range(-n + 1, 1))


def test_volume_overlay_chart_contract(pattern_module, fake_st):
    """The volume overlay chart contains the two expected traces and layout."""
    settings = _default_settings()
    results = _match_results_df()
    fake_st.session_state["match_results"] = results
    fake_st.session_state["match_etype_saved"] = "runup"
    fake_st.session_state["match_profile_saved"] = "standard"
    pattern_module.load_fingerprint.return_value = _fingerprint_data()

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    vol_call = fake_st.plotly_chart.call_args_list[1]
    vol_fig = vol_call[0][0]
    assert vol_call.kwargs.get("use_container_width") is True

    assert len(vol_fig.data) == 2
    assert vol_fig.data[0].type == "scatter"
    assert vol_fig.data[0].name == "Historical avg volume ratio"
    assert vol_fig.data[0].line.color == "orange"
    assert vol_fig.data[0].line.dash == "dash"
    assert vol_fig.data[0].line.width == 2

    assert vol_fig.data[1].type == "bar"
    assert vol_fig.data[1].name == "AAPL volume ratio"
    assert vol_fig.data[1].marker.color == "steelblue"
    assert vol_fig.data[1].opacity == 0.7

    assert vol_fig.layout.title.text == "Volume Ratio — Live vs Historical Fingerprint"
    assert vol_fig.layout.xaxis.title.text == "Days before move"
    assert vol_fig.layout.yaxis.title.text == "Volume / window avg"
    assert vol_fig.layout.height == 300


def test_volume_overlay_skipped_when_series_empty(pattern_module, fake_st):
    """No volume chart is rendered when the volume series is empty."""
    settings = _default_settings()
    results = _match_results_df()
    fake_st.session_state["match_results"] = results
    fake_st.session_state["match_etype_saved"] = "runup"
    fake_st.session_state["match_profile_saved"] = "standard"
    pattern_module.load_fingerprint.return_value = _fingerprint_data()
    pattern_module.match_ticker.return_value = _detail_dict(with_volume=False)

    pattern_module.render_pattern_similarity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
    )

    assert fake_st.plotly_chart.call_count == 1  # only price overlay
