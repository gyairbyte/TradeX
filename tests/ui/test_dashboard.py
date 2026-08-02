"""Tests for dashboard pure source-resolution helpers."""


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
