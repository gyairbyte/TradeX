"""Tests for the extracted Options Activity tab."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.config import TradeXSettings, settings_from_mapping


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


def _chain_status(
    actual_source: str,
    available: bool,
    data_kind,
    error: str | None = None,
    requested_source: str = "auto",
):
    from tradex.options.models import OptionsSourceStatus

    return OptionsSourceStatus(
        requested_source=requested_source,
        actual_source=actual_source,
        configured=available,
        available=available,
        data_kind=data_kind,
        freshness="delayed" if actual_source == "yahoo" else "provider_defined",
        delayed=actual_source == "yahoo",
        supports_event_timestamps=False,
        supports_trade_side=False,
        supports_premium=False,
        supports_sweeps=False,
        supports_chain_volume=(data_kind.value == "chain_snapshot" if data_kind else False),
        supports_open_interest=True,
        limitations=("snapshot source",) if data_kind else ("not configured",),
        error=error,
    )


def _true_flow_status(available: bool, configured: bool, error: str | None = None):
    from tradex.options.models import OptionsDataKind, OptionsSourceStatus

    return OptionsSourceStatus(
        requested_source="auto",
        actual_source="unusual_whales" if available else None,
        configured=configured,
        available=available,
        data_kind=OptionsDataKind.TRUE_FLOW if available else None,
        freshness="provider_defined",
        delayed=None,
        supports_event_timestamps=True,
        supports_trade_side=True,
        supports_premium=True,
        supports_sweeps=True,
        supports_chain_volume=False,
        supports_open_interest=False,
        limitations=("flow source",),
        error=error,
    )


def _make_chain_report(status, total_fetched=1, total_matches=0, failures=None, source_error=None):
    from tradex.options.models import (
        OptionsActivityReport,
        OptionsDataKind,
        OptionsScanStatus,
        OptionsSourceStatus,
    )

    if status in (OptionsScanStatus.SOURCE_UNAVAILABLE, OptionsScanStatus.NOT_FLOW_CAPABLE):
        source_status = OptionsSourceStatus(
            requested_source="auto",
            actual_source=None,
            configured=False,
            available=False,
            data_kind=None,
            freshness="unknown",
            delayed=None,
            supports_event_timestamps=False,
            supports_trade_side=False,
            supports_premium=False,
            supports_sweeps=False,
            supports_chain_volume=False,
            supports_open_interest=False,
            limitations=("source unavailable",),
            error=source_error or "No chain source available",
        )
    else:
        source_status = OptionsSourceStatus(
            requested_source="auto",
            actual_source="yahoo",
            configured=True,
            available=True,
            data_kind=OptionsDataKind.CHAIN_SNAPSHOT,
            freshness="delayed",
            delayed=True,
            supports_event_timestamps=False,
            supports_trade_side=False,
            supports_premium=False,
            supports_sweeps=False,
            supports_chain_volume=True,
            supports_open_interest=True,
            limitations=("delayed",),
            error=None,
        )

    if total_matches:
        results = pd.DataFrame({"ticker": ["AAPL"]})
    else:
        results = pd.DataFrame()

    return OptionsActivityReport(
        requested_source="auto",
        actual_source=source_status.actual_source,
        data_kind=source_status.data_kind,
        status=status,
        results=results,
        source_status=source_status,
        total_requested=2,
        total_fetched=total_fetched,
        total_matches=total_matches,
        failures=failures or {},
        limitations=("delayed",),
    )


@pytest.fixture
def options_module(fake_st, monkeypatch):
    """Import the Options Activity tab fresh with mocked Streamlit and backends."""
    mod_name = "tradex.ui.tabs.options_activity"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    original_columns = fake_st.columns.side_effect

    def _columns_with_selectbox(spec, *args, **kwargs):
        cols = original_columns(spec, *args, **kwargs)
        for col in cols:
            col.selectbox.side_effect = _selectbox
            col.number_input.return_value = 0.0
            col.checkbox.return_value = False
        return cols

    fake_st.columns.side_effect = _columns_with_selectbox

    mod = importlib.import_module(mod_name)

    mod.resolve_flow_source = MagicMock()
    mod.resolve_chain_source = MagicMock()
    mod.scan_unusual_flow_with_report = MagicMock()
    mod.scan_chain_activity_with_report = MagicMock()
    mod.get_put_call_activity = MagicMock()

    yield mod
    sys.modules.pop(mod_name, None)


def test_import_has_no_side_effects(fake_st, monkeypatch):
    """Importing the tab module must not render or resolve sources."""
    mod_name = "tradex.ui.tabs.options_activity"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    resolve_flow = MagicMock()
    resolve_chain = MagicMock()
    scan_flow = MagicMock()
    scan_chain = MagicMock()
    get_pc = MagicMock()
    monkeypatch.setattr("tradex.options.flow.resolve_flow_source", resolve_flow)
    monkeypatch.setattr("tradex.options.flow.resolve_chain_source", resolve_chain)
    monkeypatch.setattr("tradex.options.flow.scan_unusual_flow_with_report", scan_flow)
    monkeypatch.setattr("tradex.options.flow.scan_chain_activity_with_report", scan_chain)
    monkeypatch.setattr("tradex.options.flow.get_put_call_activity", get_pc)

    importlib.import_module(mod_name)

    assert fake_st.subheader.call_count == 0
    assert resolve_flow.call_count == 0
    assert resolve_chain.call_count == 0
    assert scan_flow.call_count == 0
    assert scan_chain.call_count == 0
    assert get_pc.call_count == 0


def test_initial_render_resolves_sources(options_module, fake_st):
    """The renderer calls source resolvers exactly once with the right settings."""
    settings = _default_settings()
    from tradex.options.models import OptionsDataKind

    options_module.resolve_flow_source.return_value = _true_flow_status(False, False)
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)

    options_module.render_options_activity_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        options_source="auto",
    )

    options_module.resolve_flow_source.assert_called_once_with("auto", settings=settings)
    options_module.resolve_chain_source.assert_called_once_with("auto", settings=settings)

    subheaders = [c[0][0] for c in fake_st.subheader.call_args_list]
    assert "Options Activity" in subheaders
    assert "True Options Flow" in subheaders
    assert "Options Chain Activity" in subheaders
    assert "Call/Put Volume Balance" in subheaders


def test_vol_oi_control_contract(options_module, fake_st):
    """The Vol/OI slider has the expected range, default, step, key, and help."""
    from tradex.options.models import OptionsDataKind

    options_module.resolve_flow_source.return_value = _true_flow_status(False, False)
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)

    options_module.render_options_activity_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        options_source="auto",
    )

    slider_calls = _collect_calls(fake_st, "slider")
    slider_call = next(c for c in slider_calls if c[1].get("key") == "min_vol_oi")
    assert slider_call[0][0] == "Min Vol/OI ratio"
    assert slider_call[0][1] == 1.0
    assert slider_call[0][2] == 20.0
    assert slider_call[0][3] == 3.0
    assert slider_call[1]["step"] == 0.5

    # The guide markdown is rendered inside the second column.
    md_calls = _collect_calls(fake_st, "markdown")
    md_texts = [str(c[0][0]) for c in md_calls]
    assert any(">10x" in m and "3–10x" in m and "1–3x" in m for m in md_texts
    )


def test_source_status_message_describes_available_source(options_module):
    """_options_source_status_message describes an available chain source."""
    from tradex.options.models import OptionsDataKind

    status = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)
    msg = options_module._options_source_status_message(status)
    assert "yahoo" in msg.lower()
    assert "chain snapshot" in msg.lower()
    assert "error" not in msg.lower()


def test_source_status_message_includes_error(options_module):
    """_options_source_status_message includes an error when present."""
    from tradex.options.models import OptionsDataKind

    status = _chain_status("tradier", False, OptionsDataKind.CHAIN_SNAPSHOT, error="TRADIER_API_KEY is not configured")
    msg = options_module._options_source_status_message(status)
    assert "tradier" in msg.lower()
    assert "TRADIER_API_KEY is not configured" in msg


def test_true_flow_disabled_message_empty_when_available(options_module):
    """_true_flow_disabled_message returns an empty string for a true-flow source."""
    status = _true_flow_status(True, True)
    assert options_module._true_flow_disabled_message(status) == ""


def test_true_flow_disabled_message_when_unconfigured(options_module):
    """_true_flow_disabled_message explains why true flow is disabled."""
    status = _true_flow_status(False, False, error="UNUSUAL_WHALES_API_KEY is not configured")
    msg = options_module._true_flow_disabled_message(status)
    assert "No true options-flow source is configured" in msg
    assert "Tradier and Yahoo provide chain snapshots" in msg
    assert "Configure Unusual Whales" in msg


def test_options_status_container_unavailable_source(options_module, fake_st):
    """_options_status_container renders an error for an unavailable source."""
    from tradex.options.models import OptionsSourceStatus

    status = OptionsSourceStatus(
        requested_source="auto",
        actual_source=None,
        configured=False,
        available=False,
        data_kind=None,
        freshness="unknown",
        delayed=None,
        supports_event_timestamps=False,
        supports_trade_side=False,
        supports_premium=False,
        supports_sweeps=False,
        supports_chain_volume=False,
        supports_open_interest=False,
        limitations=("not configured",),
        error="No true-flow source is configured",
    )
    fake_st.reset_mock()
    options_module._options_status_container(status, "True-flow source")
    assert fake_st.error.called


def test_options_status_container_available_source(options_module, fake_st):
    """_options_status_container renders an info box for an available source."""
    from tradex.options.models import OptionsDataKind

    status = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)
    fake_st.reset_mock()
    options_module._options_status_container(status, "Chain source")
    assert fake_st.info.called


def test_chain_scan_disabled_message_empty_when_available(options_module):
    """_chain_scan_disabled_message is empty when a chain snapshot is available."""
    from tradex.options.models import OptionsDataKind

    status = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)
    assert options_module._chain_scan_disabled_message(status) == ""


def test_chain_scan_disabled_message_when_unconfigured(options_module):
    """_chain_scan_disabled_message reports missing chain-source credentials."""
    from tradex.options.models import OptionsDataKind

    status = _chain_status("tradier", False, OptionsDataKind.CHAIN_SNAPSHOT, error="TRADIER_API_KEY is not configured")
    msg = options_module._chain_scan_disabled_message(status)
    assert "TRADIER_API_KEY is not configured" in msg


def test_chain_scan_disabled_message_rejects_unusual_whales(options_module):
    """_chain_scan_disabled_message rejects Unusual Whales as a chain source."""
    from tradex.options.models import OptionsSourceStatus

    status = OptionsSourceStatus(
        requested_source="unusual_whales",
        actual_source=None,
        configured=True,
        available=False,
        data_kind=None,
        freshness="provider_defined",
        delayed=None,
        supports_event_timestamps=True,
        supports_trade_side=True,
        supports_premium=True,
        supports_sweeps=True,
        supports_chain_volume=False,
        supports_open_interest=True,
        limitations=("true-flow source",),
        error="Unusual Whales is a true-flow source, not a chain snapshot.",
    )
    msg = options_module._chain_scan_disabled_message(status)
    assert "Unusual Whales is a true-flow source" in msg


def test_no_scans_without_button_click(options_module, fake_st):
    """No backend scan is triggered when no options button is active."""
    from tradex.options.models import OptionsDataKind

    options_module.resolve_flow_source.return_value = _true_flow_status(False, False)
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)

    options_module.render_options_activity_tab(
        settings=_default_settings(),
        watchlist=["AAPL", "MSFT"],
        options_source="auto",
    )

    assert options_module.scan_unusual_flow_with_report.call_count == 0
    assert options_module.scan_chain_activity_with_report.call_count == 0
    assert options_module.get_put_call_activity.call_count == 0


def test_true_flow_button_contract(options_module, fake_st):
    """The true-flow button label/key/type and disabled state match source availability."""
    from tradex.options.models import OptionsDataKind

    options_module.resolve_flow_source.return_value = _true_flow_status(True, True)
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)

    options_module.render_options_activity_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        options_source="auto",
    )

    button_call = next(c for c in fake_st.button.call_args_list if c[1].get("key") == "btn_options")
    assert button_call[0][0] == "Scan True Options Flow"
    assert button_call[1]["type"] == "primary"
    assert button_call[1]["disabled"] is False
    assert "key" in button_call[1]


def test_true_flow_button_disabled_for_chain_only(options_module, fake_st):
    """The true-flow button is disabled when the source is a chain snapshot."""
    from tradex.options.models import OptionsDataKind

    options_module.resolve_flow_source.return_value = _chain_status("yahoo", False, None, error="Yahoo provides snapshots, not flow")
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)

    options_module.render_options_activity_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        options_source="auto",
    )

    button_call = next(c for c in fake_st.button.call_args_list if c[1].get("key") == "btn_options")
    assert button_call[1]["disabled"] is True


def test_true_flow_scan_call_contract(options_module):
    """Clicking the true-flow scan passes the correct arguments."""
    from tradex.options.models import OptionsDataKind

    fake_st = options_module.st
    fake_st._active_button_keys = {"btn_options"}

    watchlist = ["AAPL", "MSFT"]
    settings = _default_settings()
    options_module.resolve_flow_source.return_value = _true_flow_status(True, True)
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)

    options_module.render_options_activity_tab(
        settings=settings,
        watchlist=watchlist,
        options_source="auto",
    )

    assert options_module.scan_unusual_flow_with_report.call_count == 1
    args, kwargs = options_module.scan_unusual_flow_with_report.call_args
    assert args[0] is watchlist
    assert kwargs["min_vol_oi"] == 3.0
    assert kwargs["source"] == "auto"
    assert kwargs["settings"] is settings


def test_chain_button_contract(options_module, fake_st):
    """The chain button is enabled when a chain snapshot source is available."""
    from tradex.options.models import OptionsDataKind

    options_module.resolve_flow_source.return_value = _true_flow_status(False, False)
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)

    options_module.render_options_activity_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        options_source="auto",
    )

    button_call = next(c for c in fake_st.button.call_args_list if c[1].get("key") == "btn_options_chain")
    assert button_call[0][0] == "Scan Options Chain Activity"
    assert button_call[1]["disabled"] is False


def test_chain_button_disabled_for_true_flow(options_module, fake_st):
    """The chain button is disabled when the selected source is a true-flow source."""

    options_module.resolve_flow_source.return_value = _true_flow_status(True, True)
    options_module.resolve_chain_source.return_value = _chain_status("unusual_whales", False, None, error="Unusual Whales is a true-flow source, not a chain snapshot.")

    options_module.render_options_activity_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        options_source="unusual_whales",
    )

    button_call = next(c for c in fake_st.button.call_args_list if c[1].get("key") == "btn_options_chain")
    assert button_call[1]["disabled"] is True


def test_chain_scan_call_contract(options_module):
    """Clicking the chain scan passes the correct arguments."""
    from tradex.options.models import OptionsDataKind

    options_module.st._active_button_keys = {"btn_options_chain"}
    watchlist = ["AAPL", "MSFT"]
    settings = _default_settings()
    options_module.resolve_flow_source.return_value = _true_flow_status(False, False)
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)

    options_module.render_options_activity_tab(
        settings=settings,
        watchlist=watchlist,
        options_source="auto",
    )

    assert options_module.scan_chain_activity_with_report.call_count == 1
    args, kwargs = options_module.scan_chain_activity_with_report.call_args
    assert args[0] is watchlist
    assert kwargs["min_vol_oi"] == 3.0
    assert kwargs["source"] == "auto"
    assert kwargs["settings"] is settings


@pytest.mark.parametrize("status", ["SOURCE_UNAVAILABLE", "NOT_FLOW_CAPABLE", "COMPLETE_FAILURE"])
def test_render_options_report_returns_early_on_terminal_states(options_module, fake_st, status):
    """The report helper returns early for terminal non-match statuses."""
    from tradex.options.models import OptionsScanStatus

    status_enum = getattr(OptionsScanStatus, status)
    report = _make_chain_report(status_enum, source_error="No source")
    fake_st.reset_mock()
    options_module._render_options_report(report, "Chain Activity", 3.0)

    if status == "COMPLETE_FAILURE":
        assert fake_st.error.called
        assert fake_st.json.called
    else:
        assert fake_st.error.called
        assert fake_st.json.call_count == 0


def test_render_options_report_valid_zero_matches(options_module, fake_st):
    """A report with no matches and no failures renders an informational message."""
    from tradex.options.models import OptionsScanStatus

    report = _make_chain_report(OptionsScanStatus.NO_MATCHES, total_fetched=1, total_matches=0)
    fake_st.reset_mock()
    options_module._render_options_report(report, "Chain Activity", 3.0)
    assert fake_st.info.called


def test_render_options_report_partial_failure_with_matches(options_module, fake_st):
    """A partial-failure report renders both matches and a warning with failures."""
    from tradex.options.models import OptionsScanStatus

    report = _make_chain_report(
        OptionsScanStatus.PARTIAL_FAILURE,
        total_fetched=2,
        total_matches=1,
        failures={"MSFT": "network timeout"},
    )
    fake_st.reset_mock()
    options_module._render_options_report(report, "Chain Activity", 3.0)
    assert fake_st.success.called
    assert fake_st.warning.called
    assert fake_st.dataframe.called
    assert fake_st.json.called


def test_render_options_report_matches_without_failures(options_module, fake_st):
    """A successful report with matches renders results only."""
    from tradex.options.models import OptionsScanStatus

    report = _make_chain_report(OptionsScanStatus.COMPLETED, total_fetched=2, total_matches=2)
    fake_st.reset_mock()
    options_module._render_options_report(report, "Chain Activity", 3.0)
    assert fake_st.success.called
    assert fake_st.dataframe.called
    assert fake_st.warning.call_count == 0


def test_render_options_report_no_matches_with_failures(options_module, fake_st):
    """A report with failures but no matches renders a warning with a failures expander."""
    from tradex.options.models import OptionsScanStatus

    report = _make_chain_report(
        OptionsScanStatus.COMPLETE_FAILURE,
        total_fetched=2,
        total_matches=0,
        failures={"AAPL": "HTTP 500", "MSFT": "HTTP 500"},
    )
    fake_st.reset_mock()
    options_module._render_options_report(report, "Chain Activity", 3.0)
    assert fake_st.error.called
    assert fake_st.json.called


def test_put_call_selector_and_call_contract(options_module, fake_st):
    """The ticker selectbox and Get Volume Balance call use the correct arguments."""
    from tradex.options.models import OptionsDataKind

    fake_st._active_button_keys = {"btn_pc"}
    watchlist = ["AAPL", "MSFT", "NVDA"]
    settings = _default_settings()
    options_module.resolve_flow_source.return_value = _true_flow_status(False, False)
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)
    options_module.get_put_call_activity.return_value = {
        "put_call_volume_ratio": 1.5,
        "call_volume": 1000,
        "put_volume": 1500,
        "volume_balance": "neutral",
    }

    options_module.render_options_activity_tab(
        settings=settings,
        watchlist=watchlist,
        options_source="yahoo",
    )

    selectbox_call = next(c for c in fake_st.selectbox.call_args_list if c[1].get("key") == "sel_pc")
    assert selectbox_call[0][0] == "Select ticker"
    assert selectbox_call[0][1] is watchlist

    args, kwargs = options_module.get_put_call_activity.call_args
    assert args[0] == "AAPL"
    assert kwargs["source"] == "yahoo"
    assert kwargs["settings"] is settings


def test_put_call_error_renders_no_metrics(options_module, fake_st):
    """An error in put/call activity displays the error and no metrics."""
    from tradex.options.models import OptionsDataKind

    fake_st._active_button_keys = {"btn_pc"}
    options_module.resolve_flow_source.return_value = _true_flow_status(False, False)
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)
    options_module.get_put_call_activity.return_value = {"error": "No options data available"}

    options_module.render_options_activity_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        options_source="auto",
    )

    error_calls = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("No options data available" in e for e in error_calls)
    metric_calls = _collect_calls(fake_st, "metric")
    assert len(metric_calls) == 0


def test_put_call_metrics_and_non_directional_message(options_module, fake_st):
    """Successful put/call activity renders four metrics and the non-directional message."""
    from tradex.options.models import OptionsDataKind

    fake_st._active_button_keys = {"btn_pc"}
    options_module.resolve_flow_source.return_value = _true_flow_status(False, False)
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)
    options_module.get_put_call_activity.return_value = {
        "put_call_volume_ratio": 1.5,
        "call_volume": 1000,
        "put_volume": 1500,
        "volume_balance": "neutral",
    }

    options_module.render_options_activity_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        options_source="auto",
    )

    metric_calls = _collect_calls(fake_st, "metric")
    metric_labels = [c[0][0] for c in metric_calls]
    assert "Put/Call Ratio" in metric_labels
    assert "Call Volume" in metric_labels
    assert "Put Volume" in metric_labels
    assert "Volume Balance" in metric_labels

    info_calls = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("non-directional" in i and "bullish or bearish" in i for i in info_calls)


def test_put_call_no_non_directional_message_when_inference_present(options_module, fake_st):
    """Truthy directional_inference suppresses the non-directional info message."""
    from tradex.options.models import OptionsDataKind

    fake_st._active_button_keys = {"btn_pc"}
    options_module.resolve_flow_source.return_value = _true_flow_status(False, False)
    options_module.resolve_chain_source.return_value = _chain_status("yahoo", True, OptionsDataKind.CHAIN_SNAPSHOT)
    options_module.get_put_call_activity.return_value = {
        "put_call_volume_ratio": 2.0,
        "call_volume": 1000,
        "put_volume": 500,
        "volume_balance": "call_heavy",
        "directional_inference": True,
    }

    options_module.render_options_activity_tab(
        settings=_default_settings(),
        watchlist=["AAPL"],
        options_source="auto",
    )

    info_calls = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert not any("non-directional" in i for i in info_calls)
