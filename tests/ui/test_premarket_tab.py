"""Tests for the extracted Pre-Market Gap Scanner tab."""
from __future__ import annotations

import importlib
import sys
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.config import TradeXSettings, settings_from_mapping
from tradex.premarket.config import GapScanConfig
from tradex.premarket.models import (
    GAP_STATUS_NO_PREMARKET_DATA,
    GAP_STATUS_NO_PREVIOUS_CLOSE,
    GAP_STATUS_OUTSIDE_WINDOW,
    GAP_STATUS_PRICE_FILTERED,
    GAP_STATUS_PROVIDER_FAILURE,
    GAP_STATUS_QUALIFIED,
    GapScanReport,
)


def _default_settings() -> TradeXSettings:
    return settings_from_mapping({})


def _selectbox(label, *args, **kwargs):
    for arg in args:
        if isinstance(arg, (list, tuple)) and arg:
            return arg[0]
    return kwargs.get("index")


def _collect_calls(fake_st, attr):
    """Collect calls from all Streamlit column objects returned during a render."""
    calls = []
    for cols in getattr(fake_st, "_column_returns", []):
        for col in cols:
            calls.extend(getattr(col, attr, MagicMock()).call_args_list)
    return calls


def _gap_report(
    observations=None,
    results=None,
    provider_errors=None,
    config=None,
    requested_tickers=None,
) -> GapScanReport:
    if results is None:
        results = pd.DataFrame()
    if observations is None:
        observations = pd.DataFrame()
    if provider_errors is None:
        provider_errors = {}
    if config is None:
        config = GapScanConfig()
    if requested_tickers is None:
        requested_tickers = ["AAPL", "MSFT"]
    return GapScanReport(
        session_date=date(2026, 8, 4),
        as_of=datetime(2026, 8, 4, 8, 0, 0, tzinfo=UTC),
        requested_provider="yahoo",
        actual_provider="yahoo",
        config=config,
        requested_tickers=requested_tickers,
        results=results,
        observations=observations,
        provider_errors=provider_errors,
    )


def _qualified_results():
    return pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT"],
            "gap_pct": [3.5, -2.1],
            "direction": ["up", "down"],
            "prev_close": [150.0, 250.0],
            "pre_market": [155.25, 244.75],
            "premarket_volume": [5000, 3000],
            "premarket_dollar_volume": [776250.0, 734250.0],
            "premarket_volume_ratio": [1.5, 0.8],
            "spread_bps": [10.0, pd.NA],
            "catalyst_status": ["none", "none"],
            "data_age_minutes": [5.0, 6.0],
            "requested_provider": ["yahoo", "yahoo"],
            "actual_provider": ["yahoo", "yahoo"],
            "tier": ["large", "moderate"],
            "note": ["", ""],
        }
    )


def _by_key(calls):
    """Index Streamlit widget calls by their ``key`` kwarg."""
    return {c[1].get("key"): c for c in calls if "key" in c[1]}


@pytest.fixture
def premarket_module(fake_st, monkeypatch):
    """Import the Pre-Market tab fresh with mocked Streamlit and backends."""
    mod_name = "tradex.ui.tabs.premarket"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    fake_px = MagicMock(name="plotly.express")
    fake_px.bar.return_value = MagicMock(name="gap_fig")
    monkeypatch.delitem(sys.modules, "plotly", raising=False)
    monkeypatch.delitem(sys.modules, "plotly.express", raising=False)
    monkeypatch.setitem(sys.modules, "plotly.express", fake_px)

    fake_st._number_input_overrides = {}
    fake_st._checked_checkbox_key = None

    original_columns = fake_st.columns.side_effect

    defaults = {
        "min_gap_price": 0.0,
        "min_gap_volume": 0,
        "min_gap_dollar_volume": 0.0,
        "min_gap_volume_ratio": 0.0,
        "max_gap_data_age": 0.0,
        "max_gap_spread": 0.0,
        "gap_liquidity_lookback": 20,
    }

    def _number_input(label, *args, **kwargs):
        key = kwargs.get("key")
        overrides = getattr(fake_st, "_number_input_overrides", {})
        if key in overrides:
            return overrides[key]
        return defaults.get(key, kwargs.get("value", 0.0))

    def _checkbox(label, *args, **kwargs):
        return kwargs.get("key") == fake_st._checked_checkbox_key

    def _columns_with_inputs(spec, *args, **kwargs):
        cols = original_columns(spec, *args, **kwargs)
        for col in cols:
            col.number_input.side_effect = _number_input
            col.checkbox.side_effect = _checkbox
            col.selectbox.side_effect = _selectbox
        return cols

    fake_st.columns.side_effect = _columns_with_inputs

    mod = importlib.import_module(mod_name)
    mod.scan_gaps_with_report = MagicMock()

    yield mod
    sys.modules.pop(mod_name, None)


def test_import_has_no_side_effects(fake_st, monkeypatch):
    """Importing the Pre-Market tab module must not render or call backends."""
    mod_name = "tradex.ui.tabs.premarket"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    monkeypatch.setattr("tradex.premarket.gap_scanner.scan_gaps_with_report", MagicMock())

    importlib.import_module(mod_name)

    assert fake_st.subheader.call_count == 0
    assert fake_st.slider.call_count == 0


def test_initial_render_and_complete_control_contract(premarket_module, fake_st):
    """All Pre-Market controls render with the expected labels, defaults, keys, and help."""
    premarket_module.scan_gaps_with_report.return_value = _gap_report()

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    subheaders = [c[0][0] for c in fake_st.subheader.call_args_list]
    assert subheaders == ["Pre-Market Gap Scanner"]

    info_texts = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("Exploratory Event Context" in t for t in info_texts)

    captions = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert captions == [(
        "Identifies stocks that have gapped significantly from their previous close "
        "based on pre-market trading activity. Best run 7am–9:25am ET before market open."
    )]

    expander_labels = [c[0][0] for c in fake_st.expander.call_args_list]
    assert expander_labels == ["What is a gap and how do I read this?"]

    slider_calls = _by_key(_collect_calls(fake_st, "slider"))
    assert len(slider_calls) == 1
    sc = slider_calls["min_gap"]
    assert sc[0][0] == "Min gap %"
    assert sc[0][1] == 1.0
    assert sc[0][2] == 15.0
    assert sc[0][3] == 2.0
    assert sc[1] == {
        "step": 0.5,
        "key": "min_gap",
        "help": "Only show stocks that have gapped at least this % from the prior close.",
    }

    ni_calls = _by_key(_collect_calls(fake_st, "number_input"))
    expected_number_inputs = {
        "min_gap_price": ("Min price", 0.0, 1.0, "Minimum pre-market last price. 0 disables the filter."),
        "min_gap_volume": ("Min pre-market volume", 0, 1000, "Minimum pre-market share volume. 0 disables the filter."),
        "min_gap_dollar_volume": (
            "Min pre-market dollar volume",
            0.0,
            100_000.0,
            "Minimum pre-market dollar volume. 0 disables the filter.",
        ),
        "min_gap_volume_ratio": (
            "Min volume ratio",
            0.0,
            0.1,
            "Minimum pre-market volume as a multiple of the recent average daily volume. 0 disables.",
        ),
        "max_gap_data_age": (
            "Max data age (minutes)",
            0.0,
            1.0,
            "Maximum staleness of the latest pre-market bar. 0 disables.",
        ),
        "max_gap_spread": (
            "Max spread (bps)",
            0.0,
            1.0,
            "Maximum bid/ask spread in basis points. 0 disables.",
        ),
        "gap_liquidity_lookback": (
            "Liquidity lookback sessions",
            20,
            None,
            "Completed sessions used to compute average daily volume.",
        ),
    }
    for key, (label, value, step, help_text) in expected_number_inputs.items():
        assert key in ni_calls, key
        call_obj = ni_calls[key]
        assert call_obj[0][0] == label
        assert call_obj[1]["value"] == value
        assert call_obj[1]["key"] == key
        assert call_obj[1]["help"] == help_text
        if step is not None:
            assert call_obj[1]["step"] == step
    assert ni_calls["gap_liquidity_lookback"][1]["min_value"] == 5

    cb_calls = _by_key(_collect_calls(fake_st, "checkbox"))
    expected_checkboxes = {
        "require_gap_spread": ("Require spread data", False, "Filter out tickers when real spread quotes are unavailable."),
        "include_gap_catalysts": (
            "Include catalyst context",
            False,
            "Fetch earnings and headline context when available. No causal claims are made.",
        ),
        "require_gap_catalyst": (
            "Require catalyst",
            False,
            "Filter out tickers with no earnings or recent headline context.",
        ),
        "allow_gap_after_open": (
            "Allow after open",
            False,
            "Allow retrospective scans after the regular session has opened.",
        ),
    }
    for key, (label, value, help_text) in expected_checkboxes.items():
        assert key in cb_calls, key
        call_obj = cb_calls[key]
        assert call_obj[0][0] == label
        assert call_obj[1]["value"] == value
        assert call_obj[1]["key"] == key
        assert call_obj[1]["help"] == help_text

    button_call = next(c for c in fake_st.button.call_args_list if c[1].get("key") == "btn_gaps")
    assert button_call[0][0] == "Scan Pre-Market Gaps"
    assert button_call[1] == {"type": "primary", "key": "btn_gaps"}

    assert premarket_module.scan_gaps_with_report.call_count == 0


def test_configuration_conversion_zeros_become_none(premarket_module):
    """When age/spread are zero, the renderer passes None to GapScanConfig."""
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report()

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    _, kwargs = premarket_module.scan_gaps_with_report.call_args
    config = kwargs["config"]
    assert config.max_data_age_minutes is None
    assert config.max_spread_bps is None
    assert config.catalyst_lookback_hours == 24.0
    assert config.min_abs_gap_pct == 2.0
    assert config.min_price == 0.0
    assert config.min_premarket_volume == 0
    assert config.min_premarket_dollar_volume == 0.0
    assert config.min_premarket_volume_ratio == 0.0
    assert config.require_spread is False
    assert config.require_catalyst is False
    assert config.allow_after_open is False
    assert config.liquidity_lookback_sessions == 20


def test_configuration_conversion_positive_values_forwarded(premarket_module):
    """Positive age/spread values are forwarded unchanged (not converted to None)."""
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.st._number_input_overrides = {
        "max_gap_data_age": 12.5,
        "max_gap_spread": 7.0,
    }
    premarket_module.scan_gaps_with_report.return_value = _gap_report()

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    _, kwargs = premarket_module.scan_gaps_with_report.call_args
    config = kwargs["config"]
    assert config.max_data_age_minutes == 12.5
    assert config.max_spread_bps == 7.0


def test_number_inputs_are_int_converted(premarket_module):
    """The two wrapped number inputs are cast through ``int(...)`` before use."""
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.st._number_input_overrides = {
        "min_gap_volume": 15.7,
        "gap_liquidity_lookback": 30.2,
    }
    premarket_module.scan_gaps_with_report.return_value = _gap_report()

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    _, kwargs = premarket_module.scan_gaps_with_report.call_args
    config = kwargs["config"]
    assert config.min_premarket_volume == 15
    assert isinstance(config.min_premarket_volume, int)
    assert config.liquidity_lookback_sessions == 30
    assert isinstance(config.liquidity_lookback_sessions, int)


def test_gap_scan_call_contract_catalysts_disabled(premarket_module):
    """The gap scan receives the exact watchlist, provider, and None catalyst sources."""
    premarket_module.st._active_button_keys = {"btn_gaps"}
    watchlist = ["AAPL", "MSFT"]
    settings = _default_settings()
    premarket_module.scan_gaps_with_report.return_value = _gap_report()

    premarket_module.render_premarket_tab(
        settings=settings,
        watchlist=watchlist,
        provider="yahoo",
        earnings_source="yahoo",
    )

    args, kwargs = premarket_module.scan_gaps_with_report.call_args
    assert args[0] is watchlist
    assert kwargs["provider"] == "yahoo"
    assert kwargs["earnings_source"] is None
    assert kwargs["headline_source"] is None
    assert kwargs["include_catalysts"] is False
    assert kwargs["settings"] is settings
    assert isinstance(kwargs["config"], GapScanConfig)


def test_gap_scan_call_contract_catalysts_enabled(premarket_module):
    """When Include catalyst context is checked, both source arguments are set."""
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.st._checked_checkbox_key = "include_gap_catalysts"
    settings = _default_settings()
    premarket_module.scan_gaps_with_report.return_value = _gap_report()

    premarket_module.render_premarket_tab(
        settings=settings,
        watchlist=["AAPL"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    _, kwargs = premarket_module.scan_gaps_with_report.call_args
    assert kwargs["earnings_source"] == "yahoo"
    assert kwargs["headline_source"] == "yahoo"
    assert kwargs["include_catalysts"] is True


def test_provider_capability_error_renders_no_results(premarket_module, fake_st):
    """A ProviderCapabilityError displays an error and skips metrics, table, chart, and expanders."""
    from tradex.data.fetcher import ProviderCapabilityError

    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.side_effect = ProviderCapabilityError("Yahoo unavailable")

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    error_calls = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert error_calls == ["Yahoo unavailable"]

    assert len(_collect_calls(fake_st, "metric")) == 0
    assert fake_st.dataframe.call_count == 0
    assert fake_st.plotly_chart.call_count == 0
    assert fake_st.success.call_count == 0
    expander_labels = [c[0][0] for c in fake_st.expander.call_args_list]
    assert "Filtered tickers" not in expander_labels
    assert "Failed tickers" not in expander_labels


def test_count_metrics_order_and_values(premarket_module, fake_st):
    """The six count metrics are rendered in the expected order with correct values."""
    observations = pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT", "NVDA"],
            "status": [GAP_STATUS_QUALIFIED, GAP_STATUS_PRICE_FILTERED, GAP_STATUS_OUTSIDE_WINDOW],
            "error": [None, None, None],
            "filter_reasons": [[], [], []],
        }
    )
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report(
        observations=observations, requested_tickers=["AAPL", "MSFT", "NVDA"]
    )

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL", "MSFT", "NVDA"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    metric_calls = _collect_calls(fake_st, "metric")
    metric_labels = [c[0][0] for c in metric_calls]
    expected = ["Requested", "Qualified", "Filtered", "Failed", "Outside window", "Provider failures"]
    assert metric_labels == expected

    assert metric_calls[0][0][1] == 3
    assert metric_calls[1][0][1] == 1
    assert metric_calls[2][0][1] == 1
    assert metric_calls[3][0][1] == 0
    assert metric_calls[4][0][1] == 1
    assert metric_calls[5][0][1] == 0


def test_provider_errors_message_and_key_order(premarket_module, fake_st):
    """Provider errors are joined in dictionary-key order."""
    observations = pd.DataFrame(
        {"ticker": ["AAPL"], "status": [GAP_STATUS_PROVIDER_FAILURE], "error": ["fail"], "filter_reasons": [[]]}
    )
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report(
        observations=observations,
        provider_errors={"AAPL": "timeout", "MSFT": "network"},
        requested_tickers=["AAPL"],
    )

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    error_calls = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert "Provider failures: AAPL, MSFT" in error_calls


def test_populated_result_transformation_and_display(premarket_module, fake_st):
    """Qualified results are formatted and displayed with the expected columns and config."""
    results = _qualified_results()
    observations = pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT"],
            "status": [GAP_STATUS_QUALIFIED, GAP_STATUS_QUALIFIED],
            "error": [None, None],
            "filter_reasons": [[], []],
        }
    )
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report(
        results=results, observations=observations
    )

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    assert fake_st.success.call_args[0][0] == "2 qualified gaps found"

    df_call = fake_st.dataframe.call_args_list[0]
    display = df_call[0][0]
    assert list(display["ticker"]) == ["AAPL", "MSFT"]
    assert list(display["gap_display"]) == ["+3.50%", "-2.10%"]
    assert list(display["spread_display"]) == ["10.00 bps", "unavailable"]
    assert list(display["volume_ratio_display"]) == ["1.50x", "0.80x"]

    expected_cols = [
        "ticker",
        "gap_display",
        "prev_close",
        "pre_market",
        "premarket_volume",
        "premarket_dollar_volume",
        "volume_ratio_display",
        "spread_display",
        "catalyst_status",
        "data_age_minutes",
        "requested_provider",
        "actual_provider",
        "tier",
        "note",
    ]
    assert list(display.columns) == expected_cols
    assert df_call.kwargs.get("use_container_width") is True

    config = df_call.kwargs.get("column_config", {})
    assert set(config.keys()) == set(expected_cols) - {"ticker", "tier"}

    text_calls = {c[0][0]: c[1] for c in fake_st.column_config.TextColumn.call_args_list}
    assert text_calls["Gap %"] == {}
    assert text_calls["Volume Ratio"] == {}
    assert text_calls["Spread"] == {}
    assert text_calls["Catalyst"] == {}
    assert text_calls["Requested Provider"] == {}
    assert text_calls["Actual Provider"] == {}
    assert text_calls["Context"] == {"width": "large"}

    number_calls = {c[0][0]: c[1] for c in fake_st.column_config.NumberColumn.call_args_list}
    assert number_calls["Prev Close"] == {"format": "$%.2f"}
    assert number_calls["Pre-Market"] == {"format": "$%.2f"}
    assert number_calls["Pre-Market Volume"] == {}
    assert number_calls["Pre-Market $ Volume"] == {"format": "$%.2f"}
    assert number_calls["Data Age (min)"] == {}


def test_gap_chart_contract(premarket_module, fake_st):
    """The gap chart is built with the exact px.bar arguments, colors, hline, and layout."""
    results = _qualified_results()
    observations = pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT"],
            "status": [GAP_STATUS_QUALIFIED, GAP_STATUS_QUALIFIED],
            "error": [None, None],
            "filter_reasons": [[], []],
        }
    )
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report(
        results=results, observations=observations
    )

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    px = premarket_module.px
    assert px.bar.call_count == 1
    _, kwargs = px.bar.call_args
    assert kwargs["x"] == "ticker"
    assert kwargs["y"] == "gap_pct"
    assert kwargs["color"] == "direction"
    assert kwargs["color_discrete_map"] == {"up": "green", "down": "red"}
    assert kwargs["title"] == "Pre-Market Gaps by Ticker"
    assert kwargs["labels"] == {"gap_pct": "Gap %", "ticker": ""}
    df = px.bar.call_args[0][0]
    assert list(df["ticker"]) == ["AAPL", "MSFT"]
    assert list(df["direction"]) == ["up", "down"]

    fig = px.bar.return_value
    assert fig.add_hline.call_args.kwargs == {"y": 0, "line_color": "white", "line_width": 1}
    assert fig.update_layout.call_args.kwargs == {"height": 350}

    assert fake_st.plotly_chart.call_count == 1
    assert fake_st.plotly_chart.call_args[0][0] is fig
    assert fake_st.plotly_chart.call_args.kwargs.get("use_container_width") is True


def test_empty_result_all_provider_failures(premarket_module, fake_st):
    """All provider failures produce the correct error message."""
    observations = pd.DataFrame(
        {"ticker": ["AAPL"], "status": [GAP_STATUS_PROVIDER_FAILURE], "error": ["fail"], "filter_reasons": [[]]}
    )
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report(
        observations=observations, requested_tickers=["AAPL"]
    )

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    error_calls = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("All tickers failed due to provider or calculation errors" in e for e in error_calls)


def test_empty_result_all_missing_data(premarket_module, fake_st):
    """All missing required data produces the correct error message."""
    observations = pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT"],
            "status": [GAP_STATUS_NO_PREVIOUS_CLOSE, GAP_STATUS_NO_PREMARKET_DATA],
            "error": [None, None],
            "filter_reasons": [[], []],
        }
    )
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report(
        observations=observations, requested_tickers=["AAPL", "MSFT"]
    )

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    error_calls = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("All tickers lack required market data" in e for e in error_calls)


def test_empty_result_all_outside_window(premarket_module, fake_st):
    """All outside-window outcomes produce the correct info message."""
    observations = pd.DataFrame(
        {"ticker": ["AAPL"], "status": [GAP_STATUS_OUTSIDE_WINDOW], "error": [None], "filter_reasons": [[]]}
    )
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report(
        observations=observations, requested_tickers=["AAPL"]
    )

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    info_calls = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("outside the pre-market window" in i for i in info_calls)


def test_empty_result_valid_zero_qualified(premarket_module, fake_st):
    """A valid zero-qualified result reports the gap threshold and counts."""
    observations = pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT"],
            "status": [GAP_STATUS_PRICE_FILTERED, GAP_STATUS_PRICE_FILTERED],
            "error": [None, None],
            "filter_reasons": [["price"], ["price"]],
        }
    )
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report(
        observations=observations, requested_tickers=["AAPL", "MSFT"]
    )

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL", "MSFT"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    info_calls = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("No gaps above 2.0% found" in i for i in info_calls)


def test_filtered_observations_expand(premarket_module, fake_st):
    """Filtered observations are displayed with the expected columns and reset index."""
    observations = pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "status": [GAP_STATUS_PRICE_FILTERED],
            "gap_pct": [0.5],
            "filter_reasons": [["price"]],
            "error": [None],
        }
    )
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report(
        observations=observations, requested_tickers=["AAPL"]
    )

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    expander_labels = [c[0][0] for c in fake_st.expander.call_args_list]
    assert "Filtered tickers" in expander_labels
    assert "Failed tickers" in expander_labels

    df_call = fake_st.dataframe.call_args_list[-1]
    assert list(df_call[0][0].columns) == ["ticker", "gap_pct", "filter_reasons"]
    assert df_call.kwargs.get("use_container_width") is True


def test_failed_observations_expand(premarket_module, fake_st):
    """Failed observations are displayed with the expected columns and reset index."""
    observations = pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "status": [GAP_STATUS_NO_PREVIOUS_CLOSE],
            "error": ["no close"],
            "filter_reasons": [[]],
        }
    )
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report(
        observations=observations, requested_tickers=["AAPL"]
    )

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    df_call = fake_st.dataframe.call_args_list[-1]
    assert list(df_call[0][0].columns) == ["ticker", "status", "error"]
    assert df_call.kwargs.get("use_container_width") is True


def test_empty_filtered_and_failed_captions(premarket_module, fake_st):
    """Empty filtered/failed observations render caption placeholders."""
    observations = pd.DataFrame(
        {"ticker": ["AAPL"], "status": [GAP_STATUS_QUALIFIED], "error": [None], "filter_reasons": [[]]}
    )
    results = _qualified_results().iloc[:1]
    premarket_module.st._active_button_keys = {"btn_gaps"}
    premarket_module.scan_gaps_with_report.return_value = _gap_report(
        results=results, observations=observations, requested_tickers=["AAPL"]
    )

    premarket_module.render_premarket_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        provider="yahoo",
        earnings_source="yahoo",
    )

    caption_texts = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert any("No tickers were filtered" in c for c in caption_texts)
    assert any("No tickers failed" in c for c in caption_texts)


def test_helper_all_tickers_are_logic(premarket_module):
    """_all_tickers_are checks that all requested tickers share a set of statuses."""
    assert premarket_module._all_tickers_are({"requested": 2, "provider_failure": 2}, {"provider_failure"}) is True
    assert premarket_module._all_tickers_are({"requested": 2, "provider_failure": 1}, {"provider_failure"}) is False
    assert premarket_module._all_tickers_are({"requested": 0}, {"provider_failure"}) is False


def test_helper_all_provider_failures(premarket_module):
    """_all_provider_failures delegates to _all_tickers_are."""
    assert premarket_module._all_provider_failures({"requested": 1, "provider_failure": 1}) is True
    assert premarket_module._all_provider_failures({"requested": 2, "provider_failure": 1}) is False


def test_helper_all_missing_data(premarket_module):
    """_all_missing_data detects only no_previous_close / no_premarket_data statuses."""
    assert premarket_module._all_missing_data({"requested": 2, "no_previous_close": 1, "no_premarket_data": 1}) is True
    assert premarket_module._all_missing_data({"requested": 2, "provider_failure": 2}) is False
