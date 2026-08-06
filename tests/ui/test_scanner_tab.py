"""Tests for the extracted Scanner tab."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from tradex.config import TradeXSettings, settings_from_mapping
from tradex.data.fetcher import (
    FetchAttempt,
    ProviderDataUnavailableError,
    ProviderResponseError,
    ProviderTransientError,
)
from tradex.screener.engine import ScanReport


def _default_settings() -> TradeXSettings:
    return settings_from_mapping({})


def _drill_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [1.0, 2.0, 3.0],
            "high": [1.1, 2.1, 3.1],
            "low": [0.9, 1.9, 2.9],
            "close": [1.05, 2.05, 3.05],
            "volume": [1000, 2000, 3000],
            "ema_20": [1.0, 2.0, 3.0],
            "ema_50": [1.0, 2.0, 3.0],
            "bb_upper": [1.2, 2.2, 3.2],
            "bb_lower": [0.8, 1.8, 2.8],
            "volume_sma20": [1000.0, 2000.0, 3000.0],
        }
    )


def _scan_results_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT"],
            "score": [75, 62],
            "last_close": [150.0, 420.0],
            "volume_ratio": [2.5, 1.8],
            "rsi": [60.0, 55.0],
            "days_until_earnings": [12, None],
            "reasons": ["Volume surge | RSI momentum", "EMA structure"],
            "provider": ["yahoo", "yahoo"],
        }
    )


def _scan_report(
    *,
    results: pd.DataFrame | None = None,
    requested_provider: str = "yahoo",
    actual_provider: str | None = "yahoo",
    fallback_used: bool = False,
    providers_attempted: tuple[str, ...] = ("yahoo",),
    failures: dict | None = None,
    earnings_failures: dict | None = None,
    fetch_failures: dict | None = None,
    scoring_failures: dict | None = None,
    total_requested: int = 2,
    total_fetch_eligible: int = 2,
    total_fetch_attempted: int = 2,
    total_retries: int = 0,
    total_fetched: int = 2,
    total_scored: int = 2,
    total_signals: int = 0,
    total_below_threshold: int = 0,
    total_insufficient_data: int = 0,
    total_earnings_excluded: int = 0,
    attempt_log: list[FetchAttempt] | None = None,
    min_score: int = 40,
) -> ScanReport:
    results = results if results is not None else pd.DataFrame()
    failures = failures if failures is not None else {}
    earnings_failures = earnings_failures if earnings_failures is not None else {}
    fetch_failures = fetch_failures if fetch_failures is not None else {}
    scoring_failures = scoring_failures if scoring_failures is not None else {}
    attempt_log = attempt_log if attempt_log is not None else []
    return ScanReport(
        results=results,
        requested_provider=requested_provider,
        actual_provider=actual_provider,
        fallback_used=fallback_used,
        providers_attempted=providers_attempted,
        failures=failures,
        total_requested=total_requested,
        total_fetch_eligible=total_fetch_eligible,
        total_fetch_attempted=total_fetch_attempted,
        total_retries=total_retries,
        total_fetched=total_fetched,
        total_scored=total_scored,
        total_signals=total_signals,
        total_below_threshold=total_below_threshold,
        total_insufficient_data=total_insufficient_data,
        total_earnings_excluded=total_earnings_excluded,
        earnings_failures=earnings_failures,
        fetch_failures=fetch_failures,
        scoring_failures=scoring_failures,
        attempt_log=attempt_log,
        min_score=min_score,
    )


@pytest.fixture
def scanner_module(fake_st, monkeypatch):
    """Import the Scanner tab fresh with mocked Streamlit and backend dependencies."""
    mod_name = "tradex.ui.tabs.scanner"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    mod = importlib.import_module(mod_name)

    monkeypatch.setattr(mod, "resolve_provider", MagicMock(return_value="resolved_yahoo"))

    scan_policy = MagicMock(name="scan_policy")
    scan_policy.max_retries = 2
    scan_policy.fallback_order = ("yahoo", "alpaca")
    monkeypatch.setattr(mod.FetchPolicy, "build", MagicMock(return_value=scan_policy))

    monkeypatch.setattr(mod, "run_with_report", MagicMock(return_value=_scan_report()))
    monkeypatch.setattr(mod.store, "record_scan", MagicMock())
    monkeypatch.setattr(mod, "fetch", MagicMock(return_value=_drill_df()))
    monkeypatch.setattr(mod, "add_indicators", MagicMock(return_value=_drill_df()))

    yield mod
    sys.modules.pop(mod_name, None)


def test_import_has_no_side_effects(fake_st, monkeypatch):
    """Importing the tab module must not render widgets or call backend functions."""
    mod_name = "tradex.ui.tabs.scanner"
    sys.modules.pop(mod_name, None)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    resolve = MagicMock()
    run = MagicMock()
    record = MagicMock()
    fetch = MagicMock()
    add_ind = MagicMock()
    monkeypatch.setattr("tradex.data.fetcher.resolve_provider", resolve)
    monkeypatch.setattr("tradex.data.fetcher.FetchPolicy.build", MagicMock())
    monkeypatch.setattr("tradex.screener.engine.run_with_report", run)
    monkeypatch.setattr("tradex.tracker.store.record_scan", record)
    monkeypatch.setattr("tradex.data.fetcher.fetch", fetch)
    monkeypatch.setattr("tradex.signals.indicators.add_indicators", add_ind)

    importlib.import_module(mod_name)

    assert fake_st.subheader.call_count == 0
    assert fake_st.caption.call_count == 0
    assert resolve.call_count == 0
    assert run.call_count == 0
    assert record.call_count == 0
    assert fetch.call_count == 0
    assert add_ind.call_count == 0


def test_initial_render_shows_subheader_caption_and_button(scanner_module, fake_st):
    """The initial render shows the expected heading, caption, expander, and Run Scan button."""
    settings = _default_settings()
    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    assert fake_st.subheader.call_count == 1
    assert "Signal Scanner" in str(fake_st.subheader.call_args[0][0])

    caption_texts = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert any("0–100" in t for t in caption_texts)

    assert fake_st.expander.call_count == 1
    assert fake_st.button.call_count == 1
    args, kwargs = fake_st.button.call_args
    assert args[0] == "Run Scan"
    assert kwargs.get("type") == "primary"
    assert kwargs.get("key") == "btn_scan"
    assert "Fetch live data" in str(kwargs.get("help", ""))

    scanner_module.resolve_provider.assert_not_called()
    scanner_module.run_with_report.assert_not_called()
    scanner_module.store.record_scan.assert_not_called()


def test_run_scan_backend_call_contract(scanner_module, fake_st):
    """Clicking Run Scan invokes the exact provider/policy/screener call chain."""
    settings = _default_settings()
    watchlist = ["AAPL", "MSFT"]
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.run_with_report.return_value = _scan_report(
        results=pd.DataFrame(), total_requested=len(watchlist)
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=watchlist,
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    scanner_module.resolve_provider.assert_called_once_with("yahoo")
    scanner_module.FetchPolicy.build.assert_called_once_with()
    scanner_module.run_with_report.assert_called_once()
    args, kwargs = scanner_module.run_with_report.call_args
    assert args[0] is watchlist
    assert kwargs["timeframe"] == "short"
    assert kwargs["min_score"] == 40
    assert kwargs["exclude_earnings_within"] is None
    assert kwargs["provider"] == "resolved_yahoo"
    assert kwargs["earnings_source"] == "yahoo"
    assert kwargs["policy"] is scanner_module.FetchPolicy.build.return_value
    assert kwargs["settings"] is settings
    assert callable(kwargs["progress"])


def test_run_scan_progress_callback_and_empty(scanner_module, fake_st):
    """The progress callback updates the bar and the bar is emptied after the backend returns."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.run_with_report.return_value = _scan_report(
        results=pd.DataFrame(), total_requested=2
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    progress_bar = fake_st.progress.return_value
    fake_st.progress.assert_called_once_with(0.0, text="Scanning 2 tickers on short…")

    progress = scanner_module.run_with_report.call_args.kwargs["progress"]
    progress(1, 2)
    progress_bar.progress.assert_called_with(0.5, text="Scanning 1/2 tickers on short…")
    progress_bar.empty.assert_called_once()


def test_run_scan_earnings_buffer_zero_forwards_none(scanner_module, fake_st):
    """A zero earnings buffer is converted to None for the backend."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )
    assert scanner_module.run_with_report.call_args.kwargs["exclude_earnings_within"] is None


def test_run_scan_positive_earnings_buffer_forwards_integer(scanner_module, fake_st):
    """A positive earnings buffer is forwarded unchanged."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="short",
        min_score=40,
        earnings_buffer=5,
        provider="yahoo",
        earnings_source="yahoo",
    )
    assert scanner_module.run_with_report.call_args.kwargs["exclude_earnings_within"] == 5


def test_run_scan_watchlist_identity_and_normalization(scanner_module, fake_st):
    """The original watchlist is passed to the backend and normalized for persistence."""
    settings = _default_settings()
    watchlist = ["aapl", "AAPL", "msft"]
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.run_with_report.return_value = _scan_report(
        results=pd.DataFrame(), total_requested=2
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=watchlist,
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    assert scanner_module.run_with_report.call_args[0][0] is watchlist
    assert watchlist == ["aapl", "AAPL", "msft"]

    _, kwargs = scanner_module.store.record_scan.call_args
    assert kwargs["tickers_scanned"] == ["AAPL", "MSFT"]


def test_run_scan_persistence_runs_for_empty_result(scanner_module, fake_st):
    """An empty scan still calls record_scan exactly once with the right contract."""
    settings = _default_settings()
    watchlist = ["AAPL", "MSFT"]
    fake_st._active_button_keys = {"btn_scan"}
    report = _scan_report(results=pd.DataFrame(), total_requested=len(watchlist))
    scanner_module.run_with_report.return_value = report

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=watchlist,
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    scanner_module.store.record_scan.assert_called_once()
    args, kwargs = scanner_module.store.record_scan.call_args
    assert args[0] is report
    assert kwargs["timeframe"] == "short"
    assert kwargs["min_score"] == 40
    assert kwargs["settings"] is settings
    assert kwargs["tickers_scanned"] == ["AAPL", "MSFT"]


def test_run_scan_valid_empty_no_session_state(scanner_module, fake_st):
    """A valid empty scan shows the generic warning and does not write session state."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.run_with_report.return_value = _scan_report(
        results=pd.DataFrame(), total_requested=2
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    warning_texts = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert any("No opportunities found" in t and "add more tickers" in t for t in warning_texts)
    assert "scan_results" not in fake_st.session_state


def test_run_scan_all_earnings_excluded(scanner_module, fake_st):
    """When every ticker is earnings-excluded, the dedicated warning is shown."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.run_with_report.return_value = _scan_report(
        results=pd.DataFrame(),
        total_requested=2,
        total_earnings_excluded=2,
        total_fetch_eligible=0,
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=5,
        provider="yahoo",
        earnings_source="yahoo",
    )

    warning_texts = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert any("All 2 tickers" in t and "upcoming earnings" in t for t in warning_texts)
    scanner_module.store.record_scan.assert_called_once()


def test_run_scan_complete_provider_failure(scanner_module, fake_st):
    """A complete provider failure produces the dedicated error and no duplicate summary."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    err = ProviderTransientError("timeout")
    scanner_module.run_with_report.return_value = _scan_report(
        results=pd.DataFrame(),
        total_requested=2,
        total_fetch_eligible=2,
        total_fetched=0,
        fetch_failures={"AAPL": err, "MSFT": err},
        failures={"AAPL": err, "MSFT": err},
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    error_texts = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("'yahoo' failed for all 2 symbol" in t for t in error_texts)
    assert any("ProviderTransientError" in t for t in error_texts)
    warning_texts = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert not any("OHLCV fetch" in t for t in warning_texts)
    scanner_module.store.record_scan.assert_called_once()


def test_run_scan_earnings_source_failure(scanner_module, fake_st):
    """A dedicated earnings-source failure is shown and the scan is persisted."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    err = ProviderDataUnavailableError("earnings lookup failed")
    scanner_module.run_with_report.return_value = _scan_report(
        results=pd.DataFrame(),
        total_requested=2,
        total_fetched=0,
        earnings_failures={"AAPL": err, "MSFT": err},
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    error_texts = [str(c[0][0]) for c in fake_st.error.call_args_list]
    assert any("Earnings source failed for 2 symbol" in t for t in error_texts)
    assert any("ProviderDataUnavailableError" in t for t in error_texts)
    warning_texts = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert not any("No opportunities found" in t for t in warning_texts)
    scanner_module.store.record_scan.assert_called_once()


def test_run_scan_populated_result_session_state_and_dataframe(scanner_module, fake_st):
    """A populated result stores the exact DataFrame, displays it, and writes session state."""
    settings = _default_settings()
    results = _scan_results_df()
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.run_with_report.return_value = _scan_report(
        results=results,
        total_requested=2,
        total_signals=2,
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    success_texts = [str(c[0][0]) for c in fake_st.success.call_args_list]
    assert any("Found 2 opportunities" in t for t in success_texts)
    assert not any("excluded tickers" in t.lower() for t in success_texts)

    assert fake_st.dataframe.call_count == 1
    assert fake_st.dataframe.call_args[0][0] is results
    _, df_kwargs = fake_st.dataframe.call_args
    assert df_kwargs.get("use_container_width") is True
    column_config = df_kwargs.get("column_config", {})
    expected_keys = {
        "ticker",
        "score",
        "last_close",
        "volume_ratio",
        "rsi",
        "days_until_earnings",
        "reasons",
        "provider",
    }
    assert set(column_config.keys()) == expected_keys
    fake_st.column_config.TextColumn.assert_any_call("Ticker")
    fake_st.column_config.ProgressColumn.assert_any_call("Score", min_value=0, max_value=100)
    fake_st.column_config.NumberColumn.assert_any_call("Last Close", format="$%.2f")

    assert fake_st.session_state["scan_results"] is results
    assert fake_st.session_state["scan_timeframe"] == "short"
    assert fake_st.session_state["scan_provider"] == "yahoo"


def test_run_scan_positive_buffer_success_wording(scanner_module, fake_st):
    """A populated result with a positive buffer includes the earnings-exclusion wording."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.run_with_report.return_value = _scan_report(
        results=_scan_results_df(), total_requested=2, total_signals=2
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=3,
        provider="yahoo",
        earnings_source="yahoo",
    )

    success_texts = [str(c[0][0]) for c in fake_st.success.call_args_list]
    assert any("excluded tickers with earnings within 3d" in t for t in success_texts)


def test_run_scan_partial_failure_warning(scanner_module, fake_st):
    """A populated result with stage failures shows the partial-failure warning."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    err = ProviderResponseError("scoring error")
    results = _scan_results_df()
    scanner_module.run_with_report.return_value = _scan_report(
        results=results,
        total_requested=3,
        total_signals=2,
        scoring_failures={"TSLA": err},
        failures={"TSLA": err},
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT", "TSLA"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    warning_texts = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert any("2 opportunities; 1 symbol(s) had stage failures" in t for t in warning_texts)


def test_run_scan_failure_summaries(scanner_module, fake_st):
    """Stage failure maps are surfaced independently with counts and expanders."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    fetch_err = ProviderDataUnavailableError("no data")
    earn_err = ProviderDataUnavailableError("earnings failed")
    score_err = ProviderResponseError("scoring failed")
    scanner_module.run_with_report.return_value = _scan_report(
        results=pd.DataFrame(),
        total_requested=3,
        total_fetch_eligible=3,
        total_fetched=1,
        fetch_failures={"AAPL": fetch_err},
        earnings_failures={"MSFT": earn_err},
        scoring_failures={"TSLA": score_err},
        failures={"AAPL": fetch_err, "TSLA": score_err},
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT", "TSLA"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    warning_texts = [str(c[0][0]) for c in fake_st.warning.call_args_list]
    assert any("1 earnings lookup(s) failed" in t for t in warning_texts)
    assert any("1 OHLCV fetch/insufficient-data failure(s)" in t for t in warning_texts)
    assert any("1 scoring failure(s)" in t for t in warning_texts)

    expander_labels = [str(c[0][0]) for c in fake_st.expander.call_args_list]
    assert "Earnings failure summary" in expander_labels
    assert "OHLCV failure summary" in expander_labels
    assert "Scoring failure summary" in expander_labels

    caption_texts = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert any("**AAPL**: ProviderDataUnavailableError" in t for t in caption_texts)
    assert any("**MSFT**: ProviderDataUnavailableError" in t for t in caption_texts)
    assert any("**TSLA**: ProviderResponseError" in t for t in caption_texts)


def test_run_scan_attempt_log_summary(scanner_module, fake_st):
    """The attempt log is rendered per provider with counts."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    attempts = [
        FetchAttempt(provider="yahoo", ticker="AAPL", attempts=1, retries=0, success=False),
        FetchAttempt(provider="alpaca", ticker="AAPL", attempts=2, retries=1, success=True),
    ]
    scanner_module.run_with_report.return_value = _scan_report(
        results=pd.DataFrame(),
        total_requested=1,
        total_fetch_attempted=3,
        total_retries=1,
        providers_attempted=("yahoo", "alpaca"),
        attempt_log=attempts,
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    expander_labels = [str(c[0][0]) for c in fake_st.expander.call_args_list]
    assert "Fetch attempt summary" in expander_labels

    caption_texts = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert any("Providers attempted: ('yahoo', 'alpaca')" in t for t in caption_texts)
    assert any("total attempts: 3" in t for t in caption_texts)
    assert any("retries: 1" in t for t in caption_texts)

    text_texts = [str(c[0][0]) for c in fake_st.text.call_args_list]
    assert any("yahoo: 1 attempted, 0 succeeded, 1 failed, 0 retries" in t for t in text_texts)
    assert any("alpaca: 1 attempted, 1 succeeded, 0 failed, 1 retries" in t for t in text_texts)


def test_run_scan_fallback_used_info(scanner_module, fake_st):
    """When the report indicates fallback, an info message shows requested/actual provider."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.run_with_report.return_value = _scan_report(
        results=_scan_results_df(),
        total_requested=2,
        requested_provider="yahoo",
        actual_provider="alpaca",
        fallback_used=True,
    )

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    info_texts = [str(c[0][0]) for c in fake_st.info.call_args_list]
    assert any("Fallback used" in t and "'yahoo'" in t and "'alpaca'" in t for t in info_texts)


def test_drill_down_without_new_scan(scanner_module, fake_st):
    """Pre-populated scan state renders the drill-down without re-running the backend."""
    settings = _default_settings()
    results = _scan_results_df()
    fake_st.session_state["scan_results"] = results
    fake_st.session_state["scan_timeframe"] = "long"
    fake_st.session_state["scan_provider"] = "alpaca"

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    scanner_module.run_with_report.assert_not_called()
    scanner_module.store.record_scan.assert_not_called()

    selectbox_keys = {call.kwargs.get("key") for call in fake_st.selectbox.call_args_list}
    assert "sel_scanner" in selectbox_keys

    scanner_module.fetch.assert_called_once_with("AAPL", "long", provider="alpaca", settings=settings)
    scanner_module.add_indicators.assert_called_once_with(scanner_module.fetch.return_value)

    assert fake_st.plotly_chart.call_count == 2
    assert fake_st.info.call_count == 1
    assert "Score: 75" in str(fake_st.info.call_args[0][0])


def test_drill_down_uses_current_provider_when_not_saved(scanner_module, fake_st):
    """The drill-down falls back to the current provider if no saved scan provider exists."""
    settings = _default_settings()
    fake_st.session_state["scan_results"] = _scan_results_df()
    fake_st.session_state["scan_timeframe"] = "short"

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    assert scanner_module.fetch.call_args.kwargs["provider"] == "yahoo"


def test_price_and_volume_chart_contracts(scanner_module, fake_st):
    """The drill-down price and volume charts are constructed with the expected traces."""
    settings = _default_settings()
    fake_st.session_state["scan_results"] = _scan_results_df()
    fake_st.session_state["scan_timeframe"] = "short"

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    assert fake_st.plotly_chart.call_count == 2
    price_fig = fake_st.plotly_chart.call_args_list[0][0][0]
    volume_fig = fake_st.plotly_chart.call_args_list[1][0][0]

    assert fake_st.plotly_chart.call_args_list[0].kwargs.get("use_container_width") is True
    assert fake_st.plotly_chart.call_args_list[1].kwargs.get("use_container_width") is True

    trace_types = [t.type for t in price_fig.data]
    trace_names = [t.name for t in price_fig.data]
    assert trace_types == ["candlestick", "scatter", "scatter", "scatter", "scatter"]
    assert trace_names == ["Price", "EMA20", "EMA50", "BB Upper", "BB Lower"]
    assert price_fig.layout.xaxis.rangeslider.visible is False
    assert price_fig.layout.height == 500

    assert price_fig.data[1].line.color == "orange"
    assert price_fig.data[1].line.width == 1
    assert price_fig.data[2].line.color == "blue"
    assert price_fig.data[2].line.width == 1
    assert price_fig.data[3].line.color == "gray"
    assert price_fig.data[3].line.dash == "dot"
    assert price_fig.data[3].line.width == 1
    assert price_fig.data[4].line.color == "gray"
    assert price_fig.data[4].line.dash == "dot"
    assert price_fig.data[4].line.width == 1
    assert price_fig.data[4].fill == "tonexty"
    assert price_fig.data[4].fillcolor == "rgba(200,200,200,0.1)"

    vol_types = [t.type for t in volume_fig.data]
    vol_names = [t.name for t in volume_fig.data]
    assert vol_types == ["bar", "scatter"]
    assert vol_names == ["Volume", "Vol SMA20"]
    assert volume_fig.layout.height == 200
    marker_colors = volume_fig.data[0].marker.color
    assert list(marker_colors) == ["green", "green", "green"]
    assert volume_fig.data[1].line.color == "white"
    assert volume_fig.data[1].line.width == 1.5


def test_retry_and_fallback_caption(scanner_module, fake_st):
    """The retry/fallback caption reflects the built policy."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    caption_texts = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert any("Retries: 2 retryies" in t for t in caption_texts)
    assert any("Fallback: yahoo → alpaca" in t for t in caption_texts)


def test_fallback_disabled_caption(scanner_module, fake_st):
    """An empty fallback order renders the 'Fallback disabled' caption."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.FetchPolicy.build.return_value.fallback_order = ()
    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    caption_texts = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert any("Fallback disabled" in t for t in caption_texts)


def test_volume_bar_colors_include_red_when_close_below_open(scanner_module, fake_st):
    """Volume bars are red when the close is below the open."""
    settings = _default_settings()
    fake_st.session_state["scan_results"] = _scan_results_df()
    fake_st.session_state["scan_timeframe"] = "short"

    red_df = pd.DataFrame(
        {
            "open": [1.0, 2.0, 3.0],
            "high": [1.1, 2.1, 3.1],
            "low": [0.9, 1.9, 2.9],
            "close": [0.95, 2.05, 2.5],
            "volume": [1000, 2000, 3000],
            "ema_20": [1.0, 2.0, 3.0],
            "ema_50": [1.0, 2.0, 3.0],
            "bb_upper": [1.2, 2.2, 3.2],
            "bb_lower": [0.8, 1.8, 2.8],
            "volume_sma20": [1000.0, 2000.0, 3000.0],
        }
    )
    scanner_module.fetch.return_value = red_df
    scanner_module.add_indicators.return_value = red_df

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL", "MSFT"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    volume_fig = fake_st.plotly_chart.call_args_list[1][0][0]
    marker_colors = volume_fig.data[0].marker.color
    assert "red" in marker_colors
    assert "green" in marker_colors


def test_retry_caption_uses_singular_when_max_retries_is_one(scanner_module, fake_st):
    """The retry caption reads '1 retry' when max_retries is exactly one."""
    settings = _default_settings()
    fake_st._active_button_keys = {"btn_scan"}
    scanner_module.FetchPolicy.build.return_value.max_retries = 1
    scanner_module.FetchPolicy.build.return_value.fallback_order = ()

    scanner_module.render_scanner_tab(
        settings=settings,
        watchlist=["AAPL"],
        timeframe="short",
        min_score=40,
        earnings_buffer=0,
        provider="yahoo",
        earnings_source="yahoo",
    )

    caption_texts = [str(c[0][0]) for c in fake_st.caption.call_args_list]
    assert any("Retries: 1 retry" in t for t in caption_texts)
