"""Tests for dashboard pure source-resolution helpers."""

import importlib

import pytest

from tradex.ui import source_defaults


def test_options_source_index_uses_env_var(monkeypatch):
    """The options source selector default honors OPTIONS_DATA_SOURCE."""
    monkeypatch.setenv("OPTIONS_DATA_SOURCE", "yahoo")
    assert source_defaults.options_source_index() == source_defaults.options_sources().index("yahoo")


def test_options_source_index_falls_back_for_invalid_env_var(monkeypatch):
    """A malformed OPTIONS_DATA_SOURCE falls back to the safe default."""
    monkeypatch.setenv("OPTIONS_DATA_SOURCE", "bloomberg")
    assert source_defaults.options_source_index() == source_defaults.options_sources().index("auto")


def test_earnings_source_index_uses_env_var(monkeypatch):
    monkeypatch.setenv("EARNINGS_DATA_SOURCE", "yahoo")
    assert source_defaults.earnings_source_index() == source_defaults.earnings_sources().index("yahoo")


def test_earnings_source_index_falls_back_for_invalid_env_var(monkeypatch):
    monkeypatch.setenv("EARNINGS_DATA_SOURCE", "schwab")
    assert source_defaults.earnings_source_index() == source_defaults.earnings_sources().index("yahoo")


def test_market_cap_source_index_uses_env_var(monkeypatch):
    monkeypatch.setenv("MARKET_CAP_DATA_SOURCE", "schwab")
    assert source_defaults.market_cap_source_index() == source_defaults.market_cap_sources().index("schwab")


def test_market_cap_source_index_falls_back_for_invalid_env_var(monkeypatch):
    monkeypatch.setenv("MARKET_CAP_DATA_SOURCE", "bloomberg")
    assert source_defaults.market_cap_source_index() == source_defaults.market_cap_sources().index("yahoo")


def test_default_source_index_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("OPTIONS_DATA_SOURCE", "TRADIER")
    assert source_defaults.options_source_index() == source_defaults.options_sources().index("tradier")


def test_dashboard_scan_passes_normalized_watchlist_to_record_scan(fresh_signal_db, tmp_path, monkeypatch):
    """A user-initiated scan passes the normalized, deduplicated watchlist to record_scan."""
    import sys
    from unittest.mock import MagicMock

    from tradex.watchlists import store as wl_store

    # Isolate the watchlist database from the real ~/.tradex path.
    monkeypatch.setattr(wl_store, "DB_PATH", tmp_path / "watchlists.db")

    # Replace the real Streamlit UI with deterministic mocks before importing dashboard.
    st = MagicMock(name="streamlit")
    st.__version__ = "0.0.0"
    st.session_state = {}

    def _button(label, *args, **kwargs):
        return label == "Run Scan"

    def _selectbox(label, *args, **kwargs):
        if label == "Timeframe":
            return "intraday"
        if label == "OHLCV provider":
            return "yahoo"
        if label == "Options source":
            return "auto"
        if label == "Earnings source":
            return "yahoo"
        if label == "Market-cap source":
            return "yahoo"
        if label == "Active watchlist":
            return "Default"
        if label == "Preset":
            return args[0][0]
        if args and isinstance(args[0], (list, tuple)) and args[0]:
            return args[0][0]
        return None

    def _columns(spec, *args, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        cols = []
        for _ in range(n):
            col = MagicMock()
            col.selectbox.side_effect = _selectbox
            col.button.side_effect = _button
            col.checkbox.return_value = False
            col.text_input.return_value = ""
            col.text_area.return_value = ""
            col.slider.return_value = 40
            cols.append(col)
        return cols

    st.button.side_effect = _button
    st.selectbox.side_effect = _selectbox
    st.columns.side_effect = _columns
    st.slider.return_value = 40
    st.text_input.return_value = ""
    st.text_area.return_value = ""
    st.checkbox.return_value = False
    st.multiselect.return_value = []
    st.tabs.return_value = [MagicMock() for _ in range(10)]
    st.progress.return_value = MagicMock()

    monkeypatch.setitem(sys.modules, "streamlit", st)

    # Build a realistic ScanReport and patch production calls.
    report = MagicMock(name="ScanReport")
    report.results.empty = True
    report.total_earnings_excluded = 0
    report.total_fetched = 0
    report.total_fetch_eligible = 0
    report.fetch_failures = {}
    report.earnings_failures = {}
    report.scoring_failures = {}
    report.failures = {}
    report.fallback_used = False
    report.requested_provider = "yahoo"
    report.actual_provider = "yahoo"

    run_mock = MagicMock(return_value=report)
    record_mock = MagicMock(return_value="session-123")
    monkeypatch.setattr("tradex.screener.engine.run_with_report", run_mock)
    monkeypatch.setattr("tradex.tracker.store.record_scan", record_mock)

    # Importing the module executes the Streamlit UI and triggers the scan.
    import tradex.ui.dashboard  # noqa: F401

    assert run_mock.call_count == 1
    assert record_mock.call_count == 1

    _, kwargs = record_mock.call_args
    assert kwargs["timeframe"] == "intraday"
    assert kwargs["min_score"] == 40
    tickers_scanned = kwargs["tickers_scanned"]
    assert isinstance(tickers_scanned, list)
    assert len(tickers_scanned) == 20
    assert "AAPL" in tickers_scanned
    assert tickers_scanned == list(dict.fromkeys(tickers_scanned))


def test_effective_cooldowns_helper():
    """_effective_cooldowns exposes per-alert-type cooldown durations."""
    from tradex.alerts.models import AlertCooldownConfig
    from tradex.ui.dashboard import _effective_cooldowns

    cfg = AlertCooldownConfig(enabled=True, default_minutes=60, coil_minutes=30)
    result = _effective_cooldowns(cfg)
    assert result["coil"] == 30
    assert result["confluence"] == 60
    assert result["pattern"] == 60
    assert result["gap"] == 60

    disabled_cfg = AlertCooldownConfig(enabled=False)
    assert _effective_cooldowns(disabled_cfg) == {"status": "disabled"}


def test_alert_policy_from_env_builds_policy(monkeypatch, tmp_path):
    """The dashboard can construct a policy from environment variables."""
    from pathlib import Path

    from tradex.ui.dashboard import _alert_policy_from_env

    state_path = tmp_path / "dash_alerts.db"
    monkeypatch.setenv("ALERT_STATE_PATH", str(state_path))
    monkeypatch.setenv("ALERT_COOLDOWN_MINUTES", "45")
    monkeypatch.setenv("ALERT_COIL_COOLDOWN_MINUTES", "15")

    policy = _alert_policy_from_env()
    assert policy.config.default_minutes == 45
    assert policy.config.coil_minutes == 15
    assert Path(policy.config.resolved_state_path) == state_path
    assert not state_path.exists()


@pytest.fixture
def dashboard_module(fresh_signal_db, tmp_path, monkeypatch):
    """Load the dashboard module with a mocked Streamlit and isolated DB paths."""
    import sys
    from unittest.mock import MagicMock

    from tradex.watchlists import store as wl_store

    monkeypatch.setattr(wl_store, "DB_PATH", tmp_path / "watchlists.db")

    st = MagicMock(name="streamlit")
    st.__version__ = "0.0.0"
    st.session_state = {}
    st.button.return_value = False
    st.slider.return_value = 3.0
    st.text_input.return_value = ""
    st.text_area.return_value = ""
    st.checkbox.return_value = False
    st.multiselect.return_value = []
    st.tabs.return_value = [MagicMock() for _ in range(10)]
    st.progress.return_value = MagicMock()

    def _selectbox(label, options, *args, **kwargs):
        if options and isinstance(options, (list, tuple)):
            return options[0]
        return None

    st.selectbox.side_effect = _selectbox

    def _columns(spec, *args, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        cols = []
        for _ in range(n):
            col = MagicMock()
            col.selectbox.side_effect = _selectbox
            col.button.return_value = False
            col.checkbox.return_value = False
            col.slider.return_value = 3.0
            col.text_input.return_value = ""
            col.text_area.return_value = ""
            cols.append(col)
        return cols

    st.columns.side_effect = _columns

    monkeypatch.setitem(sys.modules, "streamlit", st)

    from tradex.ui import dashboard

    importlib.reload(dashboard)
    return dashboard


def _chain_status(actual_source: str, available: bool, error: str | None = None):
    from tradex.options.models import OptionsDataKind, OptionsSourceStatus

    return OptionsSourceStatus(
        requested_source="auto",
        actual_source=actual_source,
        configured=available,
        available=available,
        data_kind=OptionsDataKind.CHAIN_SNAPSHOT,
        freshness="delayed" if actual_source == "yahoo" else "provider_defined",
        delayed=actual_source == "yahoo",
        supports_event_timestamps=False,
        supports_trade_side=False,
        supports_premium=False,
        supports_sweeps=False,
        supports_chain_volume=True,
        supports_open_interest=True,
        limitations=("snapshot source",),
        error=error,
    )


def test_options_source_status_message_describes_available_source(dashboard_module):
    status = _chain_status("yahoo", available=True)
    msg = dashboard_module._options_source_status_message(status)
    assert "yahoo" in msg.lower()
    assert "chain snapshot" in msg.lower()
    assert "error" not in msg.lower()


def test_options_source_status_message_includes_error(dashboard_module):
    status = _chain_status("tradier", available=False, error="TRADIER_API_KEY is not configured")
    msg = dashboard_module._options_source_status_message(status)
    assert "tradier" in msg.lower()
    assert "TRADIER_API_KEY is not configured" in msg


def test_true_flow_disabled_message_empty_when_available(dashboard_module):
    from tradex.options.models import OptionsDataKind, OptionsSourceStatus

    status = OptionsSourceStatus(
        requested_source="auto",
        actual_source="unusual_whales",
        configured=True,
        available=True,
        data_kind=OptionsDataKind.TRUE_FLOW,
        freshness="provider_defined",
        delayed=None,
        supports_event_timestamps=True,
        supports_trade_side=True,
        supports_premium=True,
        supports_sweeps=True,
        supports_chain_volume=False,
        supports_open_interest=False,
        limitations=("flow source",),
        error=None,
    )
    assert dashboard_module._true_flow_disabled_message(status) == ""


def test_true_flow_disabled_message_when_unconfigured(dashboard_module):
    from tradex.options.models import OptionsDataKind, OptionsSourceStatus

    status = OptionsSourceStatus(
        requested_source="auto",
        actual_source=None,
        configured=False,
        available=False,
        data_kind=OptionsDataKind.TRUE_FLOW,
        freshness="unknown",
        delayed=None,
        supports_event_timestamps=False,
        supports_trade_side=False,
        supports_premium=False,
        supports_sweeps=False,
        supports_chain_volume=False,
        supports_open_interest=False,
        limitations=("not configured",),
        error="UNUSUAL_WHALES_API_KEY is not configured",
    )
    msg = dashboard_module._true_flow_disabled_message(status)
    assert "No true options-flow source is configured" in msg
    assert "Tradier and Yahoo provide chain snapshots" in msg
    assert "Configure Unusual Whales" in msg
