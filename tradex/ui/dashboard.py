"""
Streamlit dashboard — ten tabs:
  1. Scanner                                     : run screener, view ranked results, drill-down chart
  2. Coil Detector                               : stocks building pressure over multiple days (pre-signal)
  3. Confluence                                  : stocks scoring well across multiple timeframes
  4. Pattern Similarity — Experimental Research  : experimental shape comparison against historical run-up/decline fingerprints
  5. Pre-Market                                  : gap scanner — identify gap-up/down candidates before open
  6. Options Activity                            : true options flow and chain-snapshot activity
  7. Alerts                                      : configure Discord/email alert thresholds
  8. Signal Journal                              : historical signal outcomes (did the move happen?)
  9. Weights                                     : tune signal component point values
  10. Help                                       : in-app documentation

Run with: streamlit run tradex/ui/dashboard.py
"""
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import ProviderCapabilityError
from tradex.options.flow import (
    get_put_call_activity,
    resolve_chain_source,
    resolve_flow_source,
    scan_chain_activity_with_report,
    scan_unusual_flow_with_report,
)
from tradex.options.models import OptionsActivityReport, OptionsDataKind, OptionsScanStatus
from tradex.patterns.config import PROFILES
from tradex.patterns.fingerprint import list_fingerprints, load_fingerprint, run_full_build
from tradex.patterns.matcher import match_ticker, run_match_screen
from tradex.premarket.config import GapScanConfig
from tradex.premarket.gap_scanner import scan_gaps_with_report
from tradex.premarket.models import (
    _FAILURE_STATUSES,
    _FILTER_STATUSES,
    _OUTSIDE_WINDOW_STATUSES,
    VALID_TICKER_RE,
    GapScanReport,
)
from tradex.tracker import store
from tradex.ui.source_defaults import (
    earnings_source_index,
    earnings_sources,
    market_cap_source_index,
    market_cap_sources,
    options_source_index,
    options_sources,
)
from tradex.ui.tabs.alerts import (
    _alert_policy_from_env,  # noqa: F401
    _effective_cooldowns,  # noqa: F401
    render_alerts_tab,
)
from tradex.ui.tabs.coil_detector import render_coil_detector_tab
from tradex.ui.tabs.confluence import render_confluence_tab
from tradex.ui.tabs.help import render_help_tab
from tradex.ui.tabs.scanner import render_scanner_tab
from tradex.ui.tabs.signal_journal import render_signal_journal_tab
from tradex.ui.tabs.weights import render_weights_tab
from tradex.watchlists import DEFAULT_NAME as WL_DEFAULT_NAME
from tradex.watchlists import presets as wl_presets
from tradex.watchlists import store as wl_store

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
    "AMD", "PLTR", "MSTR", "SPY", "QQQ", "SOXL", "TQQQ",
    "SMCI", "ARM",  "AVGO", "MU",   "CRWD", "NET",
]

_TICKER_SPLIT_RE = re.compile(r"[\s,;|]+")


def _parse_pasted_tickers(raw: str) -> list[str]:
    """Parse free-form pasted ticker text into a deduped uppercase list.

    Accepts any combination of commas, newlines, tabs, semicolons, pipes, or
    spaces as separators. Strips $ prefixes (e.g. "$AAPL"). Drops anything
    that doesn't look like a plausible ticker symbol.
    """
    seen: list[str] = []
    for tok in _TICKER_SPLIT_RE.split(raw or ""):
        tok = tok.strip().lstrip("$").upper()
        if tok and VALID_TICKER_RE.match(tok) and tok not in seen:
            seen.append(tok)
    return seen


def _all_tickers_are(counts: dict[str, int], statuses: set[str]) -> bool:
    requested = counts.get("requested", 0)
    return requested > 0 and sum(counts.get(s, 0) for s in statuses) == requested


def _all_provider_failures(counts: dict[str, int]) -> bool:
    return _all_tickers_are(counts, {"provider_failure"})


def _all_missing_data(counts: dict[str, int]) -> bool:
    return _all_tickers_are(counts, {"no_previous_close", "no_premarket_data"})


def _options_source_status_message(status) -> str:
    """Human-readable summary of an options source capability status."""
    kind = status.data_kind.value.replace("_", " ") if status.data_kind else "unavailable"
    name = status.actual_source or status.requested_source
    msg = f"{name.title()}: {kind.title()}"
    if status.error:
        msg += f" — {status.error}"
    return msg


def _true_flow_disabled_message(status) -> str:
    """Return the disabled explanation for the true-flow scan button."""
    if status.available and status.data_kind == OptionsDataKind.TRUE_FLOW:
        return ""
    return (
        "No true options-flow source is configured. Tradier and Yahoo provide chain snapshots, "
        "not transaction-level flow. Configure Unusual Whales to enable this scanner."
    )


def _options_status_container(status, label: str) -> None:
    """Render a source status box for the given options capability."""
    if not status.available:
        st.error(f"{label}: {_options_source_status_message(status)}")
    elif status.error:
        st.warning(f"{label}: {_options_source_status_message(status)}")
    else:
        st.info(f"{label}: {_options_source_status_message(status)}")


def _chain_scan_disabled_message(status) -> str:
    """Return the disabled explanation for the chain-activity scan button."""
    if status.available and status.data_kind == OptionsDataKind.CHAIN_SNAPSHOT:
        return ""
    return (
        status.error
        or "No options-chain snapshot source is available for the selected source. "
           "Configure TRADIER_API_KEY or select Yahoo to enable this scanner."
    )


def _render_options_report(report: OptionsActivityReport, label: str, min_vol_oi: float) -> None:
    """Render a scan report, clearly separating results from partial/complete failures."""
    if report is None:
        return

    if report.status == OptionsScanStatus.SOURCE_UNAVAILABLE:
        st.error(
            f"{label}: source unavailable — "
            f"{report.source_status.error or 'check configuration'}"
        )
        return
    if report.status == OptionsScanStatus.NOT_FLOW_CAPABLE:
        st.error(
            f"{label}: not a true-flow source — "
            f"{report.source_status.error or 'selected source does not provide transaction-level flow'}"
        )
        return
    if report.status == OptionsScanStatus.COMPLETE_FAILURE:
        st.error(
            f"{label}: scan failed for all requested tickers. "
            f"Status: {report.status.value}"
        )
        with st.expander("Failures"):
            st.json(report.failures)
        return

    if report.total_matches:
        st.success(
            f"{report.total_matches} {label.lower()} found "
            f"(source: {report.actual_source}; "
            f"data_kind: {report.data_kind.value if report.data_kind else 'unknown'})"
        )
        st.dataframe(report.results, use_container_width=True)
    elif report.failures:
        st.warning(
            f"{label}: no matches; {len(report.failures)} ticker(s) failed. "
            f"Status: {report.status.value}"
        )
        with st.expander("Failures"):
            st.json(report.failures)
    else:
        st.info(
            f"{label}: no matches above {min_vol_oi}x Vol/OI ratio "
            f"(source: {report.actual_source or report.requested_source})."
        )

    if report.failures and report.total_matches:
        st.warning(
            f"Partial failure: {len(report.failures)} ticker(s) failed while other "
            f"tickers produced matches. Status: {report.status.value}"
        )
        with st.expander("Failures"):
            st.json(report.failures)



def _ensure_stores(settings: TradeXSettings) -> None:
    """Lazy one-time SQLite initialization for the dashboard session."""
    key = "_tradex_stores_initialized"
    if not st.session_state.get(key):
        store.init(db_path=str(settings.paths.signals_db), settings=settings)
        wl_store.init(db_path=str(settings.paths.watchlists_db), settings=settings)
        st.session_state[key] = True


if __name__ == "__main__":
    st.set_page_config(page_title="TradeX", layout="wide")
    st.title("TradeX — Market Opportunity Scanner")
    st.caption("Scan, track, and get alerted on stock setups across intraday, short-term, and long-term timeframes.")

    settings = load_runtime_settings()
    _ensure_stores(settings)

    # ── sidebar ───────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Global Settings")
        st.caption("These settings apply across all tabs.")
    
        timeframe = st.selectbox(
            "Timeframe",
            ["intraday", "short", "long"],
            help=(
                "Controls which time window the scanner and coil detector operate on.\n\n"
                "• **Intraday** — 5-minute bars over 5 days. For same-day swing setups.\n"
                "• **Short** — Daily bars over 60 days. For moves over days to weeks.\n"
                "• **Long** — Weekly bars over 2 years. For multi-week to multi-month trends."
            ),
        )
    
        min_score = st.slider(
            "Min score",
            0, 100, 40,
            help=(
                "Filters out stocks below this signal score. Each stock is scored 0–100 "
                "based on how many technical conditions are met.\n\n"
                "• **Lower (20–40)** — casts a wider net, more results, more noise.\n"
                "• **Middle (40–65)** — balanced. Good starting point.\n"
                "• **Higher (65–100)** — only the strongest setups. Fewer results but higher conviction.\n\n"
                "Tip: start at 40 and raise it once you have signal history to know what works."
            ),
        )
    
        _PROVIDER_OPTIONS = ["yahoo", "schwab", "alpaca", "ibkr"]
        _default_provider = settings.data.data_provider.lower()
        if _default_provider not in _PROVIDER_OPTIONS:
            _default_provider = "yahoo"
        provider = st.selectbox(
            "OHLCV provider",
            _PROVIDER_OPTIONS,
            index=_PROVIDER_OPTIONS.index(_default_provider),
            help=(
                "Market data provider used by the scanner, confluence, pattern matching, "
                "chart drill-downs, and outcome tracking. The selection is passed to the central "
                "OHLCV fetcher and the daily-history abstraction.\n\n"
                "• Yahoo requires no local setup.\n"
                "• Schwab requires a Schwab developer app (API key + secret) and a local "
                "OAuth token file; selecting Schwab here does not verify it is configured.\n"
                "• Alpaca and IBKR require their respective credentials or a local gateway.\n"
                "• There is no automatic fallback: if the selected provider is not configured, "
                "the fetch will surface a safe error rather than silently switching providers.\n\n"
                "Specialized sources (options, earnings, market-cap ranking, index "
                "constituents) have their own source controls and are not affected by this selector."
            ),
        )
        st.caption(f"OHLCV provider: **{provider}**")
    
        # Options source is independent of OHLCV provider.
        options_source = st.selectbox(
            "Options source",
            options_sources(),
            index=options_source_index(settings),
            help=(
                "Options data source. True options-flow scans require a configured Unusual Whales API key; "
                "chain-activity scans use Tradier when configured, otherwise Yahoo. "
                "A specific paid source will not fall back if credentials are missing."
            ),
        )
        earnings_source = st.selectbox(
            "Earnings source",
            earnings_sources(),
            index=earnings_source_index(settings),
            help="Earnings-calendar source. Only Yahoo is supported in this release.",
        )
        market_cap_source = st.selectbox(
            "Market-cap source",
            market_cap_sources(),
            index=market_cap_source_index(settings),
            help="Source for S&P 100 market-cap ranking when refreshing presets. ``schwab`` requires Schwab credentials.",
        )
    
        # ── Watchlist selector ───────────────────────────────────────────────────
        saved_lists = wl_store.list_all(settings=settings)
        # Build a {name -> ticker_count} lookup for the dropdown formatter
        _wl_counts = {w["name"]: w["ticker_count"] for w in saved_lists}
        # Preset labels (what they get saved under via "Import preset") — used to
        # tag saved watchlists as Preset vs. Custom in the dropdown.
        _preset_labels = {p.label for p in wl_presets.PRESETS}
    
        def _wl_format(name: str) -> str:
            if name == WL_DEFAULT_NAME:
                return f"🏠 {name} ({len(DEFAULT_TICKERS)})"
            count = _wl_counts.get(name, 0)
            icon = "📊" if name in _preset_labels else "⭐"
            kind = "Preset" if name in _preset_labels else "Custom"
            return f"{icon} {kind} · {name} ({count})"
    
        # Sort: Default first, then presets, then customs — alphabetical within each group
        preset_names  = sorted([w["name"] for w in saved_lists if w["name"] in _preset_labels])
        custom_names  = sorted([w["name"] for w in saved_lists if w["name"] not in _preset_labels])
        active_options = [WL_DEFAULT_NAME] + preset_names + custom_names
    
        active_name = st.selectbox(
            "Active watchlist",
            active_options,
            format_func=_wl_format,
            help=(
                "Pick which saved watchlist to scan. Icons indicate the source:\n\n"
                "• 🏠 **Default** — built-in 20-ticker starter universe\n"
                "• 📊 **Preset** — imported from a built-in preset (S&P 500, sectors, etc.)\n"
                "• ⭐ **Custom** — saved by you (paste-and-name, or snapshot)\n\n"
                "Manage saved lists in the expander below."
            ),
        )
        if active_name == WL_DEFAULT_NAME:
            base_tickers = DEFAULT_TICKERS
        else:
            base_tickers = wl_store.load(active_name, settings=settings) or DEFAULT_TICKERS
    
        custom = st.text_input(
            "Add tickers (comma-separated)",
            "",
            help="Append to the active watchlist for this session. Example: COIN, HOOD, RKLB",
        )
        extra = [t.strip().upper() for t in custom.split(",") if t.strip()]
        watchlist = list(dict.fromkeys(base_tickers + extra))
        st.caption(f"{len(watchlist)} tickers in watchlist")
    
        with st.expander("💾 Save / manage watchlists", expanded=False):
            st.caption("Persisted to ~/.tradex/watchlists.db — survives restarts.")
    
            st.markdown("**Create new from paste**")
            create_name = st.text_input(
                "New watchlist name", key="wl_create_name",
                placeholder="e.g. Semis, Crypto plays, Earnings week",
            )
            pasted = st.text_area(
                "Tickers",
                key="wl_create_paste",
                height=120,
                placeholder="Paste tickers here — any format works:\nAAPL, MSFT, NVDA\nor one per line, or tab-separated from Sheets/Excel",
                help="Separators auto-detected: commas, newlines, tabs, semicolons, spaces. Case insensitive. Duplicates removed.",
            )
            if st.button("Create watchlist", key="wl_create_btn", use_container_width=True):
                parsed = _parse_pasted_tickers(pasted)
                if not create_name.strip():
                    st.error("Give the watchlist a name.")
                elif not parsed:
                    st.error("No tickers found in the paste box.")
                else:
                    try:
                        wl_store.save(create_name, parsed, settings=settings)
                        st.success(f"Created '{create_name}' with {len(parsed)} tickers: {', '.join(parsed[:8])}{'…' if len(parsed) > 8 else ''}")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
    
            st.divider()
            st.markdown("**Add a preset**")
            st.caption("One-click watchlists for common universes. Imports a snapshot into your saved lists.")
            preset_options = {f"{p.label} ({len(p.tickers)} tickers)": p for p in wl_presets.PRESETS}
            chosen_label = st.selectbox(
                "Preset", list(preset_options.keys()), key="wl_preset_pick",
                help="Imports the selected preset into your saved watchlists under its label. Re-importing overwrites.",
            )
            chosen_preset = preset_options[chosen_label]
            st.caption(chosen_preset.description)
            col_imp, col_refresh = st.columns(2)
            if col_imp.button("Import preset", key="wl_preset_import_btn", use_container_width=True):
                try:
                    wl_store.save(chosen_preset.label, list(chosen_preset.tickers), settings=settings)
                    st.success(f"Imported '{chosen_preset.label}' ({len(chosen_preset.tickers)} tickers). Select it in 'Active watchlist'.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            if col_refresh.button(
                "Refresh from web",
                key="wl_preset_refresh_btn",
                use_container_width=True,
                help="Re-fetch S&P 500 / Dow / NDX constituents from Wikipedia and re-rank sector lists by live market cap. Overwrites previously imported presets. Takes ~30-60s.",
            ):
                from tradex.watchlists import refresh as wl_refresh
                with st.spinner("Refreshing presets from Wikipedia + yfinance (this may take ~30-60s)…"):
                    try:
                        result = wl_refresh.refresh_all(market_cap_source=market_cap_source)
                        overrides = wl_refresh.result_to_preset_overrides(result)
                        imported = 0
                        for key, tickers in overrides.items():
                            preset = wl_presets.PRESETS_BY_KEY.get(key)
                            if preset and tickers:
                                wl_store.save(preset.label, tickers, settings=settings)
                                imported += 1
                        st.success(f"Refreshed {imported} presets. Active watchlists overwritten with latest constituents.")
                        for w in result.warnings:
                            st.warning(w)
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Refresh failed: {e}")
    
            st.divider()
            st.markdown("**Snapshot current selection**")
            new_name = st.text_input(
                "Name", key="wl_save_name",
                help="Save the active list + comma-separated additions under this name. Re-using an existing name overwrites it.",
            )
            if st.button("Save current", key="wl_save_btn", use_container_width=True):
                try:
                    wl_store.save(new_name, watchlist, settings=settings)
                    st.success(f"Saved '{new_name}' ({len(watchlist)} tickers)")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    
            st.divider()
            st.markdown("**🗑️ Delete saved watchlists**")
            if not saved_lists:
                st.caption("No saved watchlists yet.")
            else:
                del_options = [w["name"] for w in saved_lists]
                to_delete = st.multiselect(
                    "Pick one or more to delete",
                    del_options,
                    format_func=_wl_format,
                    key="wl_del_multi",
                    help="Multi-select. Presets can be re-imported later from the preset dropdown above; custom lists are gone for good.",
                )
                confirm = st.checkbox(
                    f"Yes, delete {len(to_delete)} watchlist{'s' if len(to_delete) != 1 else ''}",
                    key="wl_del_confirm",
                    disabled=not to_delete,
                )
                if st.button(
                    "Delete selected",
                    key="wl_del_btn",
                    disabled=not (to_delete and confirm),
                    use_container_width=True,
                    type="primary",
                ):
                    deleted = [n for n in to_delete if wl_store.delete(n, settings=settings)]
                    if deleted:
                        st.success(f"Deleted: {', '.join(deleted)}")
                        st.rerun()
    
        earnings_buffer = st.slider(
            "Exclude earnings within (days)",
            0, 21, 0,
            help=(
                "Filter out stocks with earnings reports within this many calendar days.\n\n"
                "• **0 (default)** — no earnings filter. Show everything.\n"
                "• **3–5 days** — avoid being long into a print. Technical setups can be "
                "wiped out by an earnings gap regardless of how clean they looked.\n"
                "• **7–14 days** — most conservative. Filters out any setup where the move "
                "could resolve into the earnings window.\n\n"
                "Results still show days-until-earnings as a column even when this is 0, "
                "so you can see the proximity at a glance."
            ),
        )
    
        st.divider()
        st.markdown("[📖 Help & Documentation](#help)", help="Open the Help tab for full feature explanations.")
    
    tab_scanner, tab_coil, tab_confluence, tab_pattern, tab_premarket, tab_options, tab_alerts, tab_journal, tab_weights, tab_help = st.tabs([
        "Scanner", "Coil Detector", "Confluence", "Pattern Similarity — Experimental Research",
        "Pre-Market", "Options Activity", "Alerts", "Signal Journal", "Weights", "Help",
    ])
    
    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 1 — SCANNER
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_scanner:
        render_scanner_tab(
            settings=settings,
            watchlist=watchlist,
            timeframe=timeframe,
            min_score=min_score,
            earnings_buffer=earnings_buffer,
            provider=provider,
            earnings_source=earnings_source,
        )
    
    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 2 — COIL DETECTOR
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_coil:
        render_coil_detector_tab(
            settings=settings,
            timeframe=timeframe,
        )

    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 3 — CONFLUENCE
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_confluence:
        render_confluence_tab(
            settings=settings,
            watchlist=watchlist,
            earnings_buffer=earnings_buffer,
            provider=provider,
            earnings_source=earnings_source,
        )
    
    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 4 — PATTERN MATCH
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_pattern:
        st.subheader("Pattern Similarity — Experimental Research")
        st.warning(
            "Pattern similarity is experimental and has not been shown to predict future returns. "
            "It is not used in production scoring, ranking, eligibility, or automatic alerts."
        )
        st.caption(
            "Compares a stock's current 10-day price/volume/indicator shape against an averaged "
            "shape from historical run-ups or declines. Pearson correlation measures resemblance, "
            "not causality or expected return."
        )
    
        with st.expander("How pattern similarity works", expanded=False):
            st.markdown("""
    **The idea:** historical run-ups and declines sometimes have recurring price/volume/indicator
    shapes in the days before the move. This tool measures how closely a stock's current 10-day
    shape resembles the *average* of those pre-move shapes.
    
    **Step 1 — Mining:** TradeX scans the configured universe and finds past instances where a stock
    moved at least +15% in 5 days (a "run-up") or at least -12% in 5 days (a "decline"). It then
    extracts the 10 trading days *before* each event started.
    
    **Step 2 — Fingerprinting:** All pre-event windows are normalized (so different price levels
    are comparable) and averaged into a "fingerprint" — the mean shape of price, volume, RSI,
    MACD difference, and Bollinger Band width leading up to the mined events.
    
    **Step 3 — Matching:** The stock's current 10-day window is compared against that fingerprint
    using Pearson correlation across the same 5 series. Each series is weighted:
    
    | Series | Weight | Role |
    |---|---|---|
    | Price shape | 35% | Largest weight |
    | Volume shape | 30% | Volume pattern in the 10-day window |
    | RSI | 15% | Momentum shape |
    | MACD | 10% | Trend-momentum shape |
    | BB Width | 10% | Volatility shape |
    
    **Similarity score guide:**
    - 90–100%: Very high shape similarity
    - 75–89%: High shape similarity — this is the existing display cutoff used in the validation study
    - 60–74%: Moderate shape similarity
    - <60%: Low shape similarity / noise
    
    **Important:** Pearson correlation measures *shape resemblance*, not causality or expected
    return. The validation study in `tradex.research.pattern_validation` is the only place this
    idea is evaluated for predictive value. Manual inspection here is experimental and does not
    justify a trade on its own.
    
    **Profiles:**
    - **Conservative** — +20% move threshold. For large stable stocks (AAPL, MSFT).
    - **Standard** — +15% threshold. Default. Works for most mid/large caps.
    - **Volatile** — +30% threshold. For high-beta stocks (SOXL, MSTR, TQQQ).
            """)
    
        with st.expander("Step 1 — Build Fingerprints (run once, ~2 min)", expanded=False):
            fp_col1, fp_col2, fp_col3 = st.columns(3)
            fp_profile = fp_col1.selectbox(
                "Profile", list(PROFILES.keys()), index=1, key="fp_profile",
                help="Conservative=large caps, Standard=default, Volatile=high-beta ETFs/meme stocks.",
            )
            fp_etype = fp_col2.selectbox(
                "Event type", ["both", "runup", "decline"], key="fp_etype",
                help="'Both' builds fingerprints for run-ups AND declines. Use 'runup' if you only trade long.",
            )
            cfg = PROFILES[fp_profile]
            fp_col3.metric(
                "Move threshold",
                f"+{cfg.runup_pct}% / -{cfg.decline_pct}%",
                help="A historical event must move at least this much to count.",
            )
            if st.button("Build Fingerprints", key="btn_build_fp",
                         help="Mine 3 years of history and compute fingerprints. Results are cached — re-run only to refresh."):
                with st.spinner("Mining historical events and building fingerprints… (~2 minutes)"):
                    try:
                        built = run_full_build(
                            profile=fp_profile, event_type=fp_etype, verbose=False,
                            provider=provider, settings=settings,
                        )
                    except ProviderCapabilityError as e:
                        st.error(str(e))
                        built = None
                if built:
                    st.success(f"Built fingerprints: {', '.join(built.keys())}")
                elif built is not None:
                    st.error("Build failed — not enough historical events found.")
            existing = list_fingerprints()
            if not existing.empty:
                st.markdown("**Stored fingerprints:**")
                st.dataframe(existing, use_container_width=True)
    
        st.divider()
        st.markdown("**Step 2 — Match Live Stocks Against Fingerprints**")
    
        m_col1, m_col2, m_col3, _ = st.columns(4)
        match_profile = m_col1.selectbox(
            "Profile", list(PROFILES.keys()), index=1, key="match_profile",
            help="Must match the profile used when building fingerprints.",
        )
        match_etype = m_col2.selectbox(
            "Pattern type", ["runup", "decline"], key="match_etype",
            help="'runup' = compare against the averaged pre-run-up shape. 'decline' = compare against the averaged pre-decline shape. Both are experimental shape comparisons, not directional predictions.",
        )
        match_threshold = m_col3.slider(
            "Min similarity", 0, 100, int(PROFILES[match_profile].alert_threshold), key="match_thresh",
            help=(
                "Only show stocks above this similarity % to the historical fingerprint.\n\n"
                "• **Lower (50–65%)** — more results, more noise.\n"
                "• **75% (default)** — the fixed display cutoff used in the validation study.\n"
                "• **Higher (85–100%)** — very high shape similarity only. Very few results.\n\n"
                "This is a shape-similarity display setting, not a trade recommendation."
            ),
        )
    
        if st.button("Run Pattern Screen", key="btn_match", type="primary"):
            fp_check = load_fingerprint(match_etype, match_profile, source=provider, settings=settings)
            if fp_check is None:
                st.error(f"No '{match_etype}' fingerprint for profile '{match_profile}' with source '{provider}'. Build it first.")
            else:
                with st.spinner(f"Matching {len(watchlist)} tickers against {match_etype} fingerprint…"):
                    match_results = run_match_screen(
                        watchlist, event_type=match_etype,
                        profile=match_profile, min_similarity=match_threshold,
                        provider=provider, settings=settings,
                    )
                if match_results.empty:
                    st.warning(f"No tickers matched above {match_threshold}% shape similarity.")
                else:
                    st.success(f"{len(match_results)} tickers with shape similarity above {match_threshold}% (experimental)")
                    st.dataframe(
                        match_results,
                        use_container_width=True,
                        column_config={
                            "ticker":           st.column_config.TextColumn("Ticker"),
                            "similarity_score": st.column_config.ProgressColumn("Similarity", min_value=0, max_value=100, help="How closely the current 10-day shape resembles the historical fingerprint (0–100)."),
                            "match_tier":       st.column_config.TextColumn("Tier"),
                            "fp_events":        st.column_config.NumberColumn("Based On", help="Number of historical events that make up the fingerprint."),
                            "score_price":      st.column_config.ProgressColumn("Price Match", min_value=0, max_value=100),
                            "score_volume":     st.column_config.ProgressColumn("Vol Match", min_value=0, max_value=100),
                            "score_rsi":        st.column_config.ProgressColumn("RSI Match", min_value=0, max_value=100),
                            "interpretation":   st.column_config.TextColumn("Interpretation", width="large"),
                        },
                    )
                    st.session_state["match_results"]        = match_results
                    st.session_state["match_etype_saved"]    = match_etype
                    st.session_state["match_profile_saved"]  = match_profile
                    st.session_state["match_source_saved"]   = provider
    
        if "match_results" in st.session_state and "match_etype_saved" in st.session_state and not st.session_state["match_results"].empty:
            st.divider()
            st.subheader("Pattern Shape Overlay — Live vs Historical Fingerprint")
            st.caption(
                "White line = your stock's last 10 days (normalized to % change from start). "
                "Orange dashed = historical average pre-event shape. Shaded band = ±1 standard deviation. "
                "This is a shape comparison, not a prediction."
            )
            selected_match = st.selectbox(
                "Select ticker", st.session_state["match_results"]["ticker"].tolist(), key="sel_match",
            )
            match_source = st.session_state.get("match_source_saved", provider)
            detail = match_ticker(
                selected_match,
                event_type=st.session_state["match_etype_saved"],
                profile=st.session_state["match_profile_saved"],
                provider=match_source,
                settings=settings,
            )
            if "error" not in detail:
                s = detail["series_scores"]
                sc1, sc2, sc3, sc4 = st.columns(4)
                sc1.metric("Overall Similarity", f"{detail['similarity_score']}%",
                           help="Weighted average match across all series.")
                sc2.metric("Price shape",  f"{s.get('price_pct', 0):.0f}%",
                           help="How closely the price movement shape matches.")
                sc3.metric("Volume shape", f"{s.get('volume_ratio', 0):.0f}%",
                           help="How closely the volume pattern matches.")
                sc4.metric("RSI shape",    f"{s.get('rsi', 0):.0f}%",
                           help="How closely the RSI trajectory matches.")
                st.info(f"**{detail['match_tier'].upper()}** — {detail['interpretation']}")
    
                n = len(detail["fp_series"].get("price_pct", []))
                x = list(range(-n + 1, 1))
                fp_mean  = detail["fp_series"].get("price_pct", [])
                fp_data  = load_fingerprint(
                    st.session_state["match_etype_saved"],
                    st.session_state["match_profile_saved"],
                    source=match_source,
                    settings=settings,
                )
                fp_upper = fp_data["series"].get("price_pct", {}).get("upper", fp_mean)
                fp_lower = fp_data["series"].get("price_pct", {}).get("lower", fp_mean)
                live_price = detail["live_series"].get("price_pct", [])[-n:]
    
                price_fig = go.Figure()
                price_fig.add_trace(go.Scatter(x=x, y=fp_upper, mode="lines",
                                               line={"width": 0}, showlegend=False))
                price_fig.add_trace(go.Scatter(x=x, y=fp_lower, mode="lines",
                                               line={"width": 0}, fill="tonexty",
                                               fillcolor="rgba(255,165,0,0.15)", name="Historical range ±1σ"))
                price_fig.add_trace(go.Scatter(x=x, y=fp_mean, mode="lines",
                                               line={"color": "orange", "dash": "dash", "width": 2}, name="Historical avg"))
                price_fig.add_trace(go.Scatter(x=x, y=live_price, mode="lines+markers",
                                               line={"color": "white", "width": 2}, name=f"{selected_match} (live)"))
                price_fig.update_layout(title="Price % — Live vs Historical Fingerprint",
                                        xaxis_title="Days before move", yaxis_title="% from window start", height=400)
                st.plotly_chart(price_fig, use_container_width=True)
    
                fp_vol   = detail["fp_series"].get("volume_ratio", [])
                live_vol = detail["live_series"].get("volume_ratio", [])[-n:]
                if fp_vol and live_vol:
                    vol_fig = go.Figure()
                    vol_fig.add_trace(go.Scatter(x=x, y=fp_vol, mode="lines",
                                                 line={"color": "orange", "dash": "dash", "width": 2},
                                                 name="Historical avg volume ratio"))
                    vol_fig.add_trace(go.Bar(x=x, y=live_vol, name=f"{selected_match} volume ratio",
                                             marker_color="steelblue", opacity=0.7))
                    vol_fig.update_layout(title="Volume Ratio — Live vs Historical Fingerprint",
                                          xaxis_title="Days before move",
                                          yaxis_title="Volume / window avg", height=300)
                    st.plotly_chart(vol_fig, use_container_width=True)
            else:
                st.error(detail["error"])
    
    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 5 — PRE-MARKET GAP SCANNER
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_premarket:
        st.subheader("Pre-Market Gap Scanner")
        st.caption(
            "Identifies stocks that have gapped significantly from their previous close "
            "based on pre-market trading activity. Best run 7am–9:25am ET before market open."
        )
    
        with st.expander("What is a gap and how do I use this?", expanded=False):
            st.markdown("""
    A **gap** is the difference between a stock's pre-market price and its previous regular-session close.
    Gaps occur overnight when new information is reflected in prices while the market is closed.
    
    **Gap tiers:**
    | Tier | Size |
    |---|---|
    | 🔴 Massive | ≥ 8% |
    | 🟠 Large | ≥ 4% |
    | 🟡 Moderate | ≥ 2% |
    
    **How to use:**
    - Run this at 7–9am ET before the market opens.
    - Focus on Large and Massive gaps for follow-through or fade setups.
    - Cross-reference with the Scanner tab for technical confirmation.
    - Data is ~15min delayed on Yahoo Finance (free). Schwab pre-market support is not enabled in this release.
    
    **Spread and catalyst notes:**
    - Spread is shown only when real bid/ask quotes are available; it is never inferred from the candle range.
    - Earnings and headline context is explicitly sourced and shown as reference only; it is not proof the context caused the gap.
    - No filter is active by default except the minimum absolute gap.
            """)
    
        g_col1, g_col2 = st.columns(2)
        min_gap = g_col1.slider(
            "Min gap %", 1.0, 15.0, 2.0, step=0.5, key="min_gap",
            help="Only show stocks that have gapped at least this % from the prior close.",
        )
        min_price = g_col2.number_input(
            "Min price", value=0.0, step=1.0, key="min_gap_price",
            help="Minimum pre-market last price. 0 disables the filter.",
        )
    
        g_col3, g_col4 = st.columns(2)
        min_premarket_volume = int(g_col3.number_input(
            "Min pre-market volume", value=0, step=1000, key="min_gap_volume",
            help="Minimum pre-market share volume. 0 disables the filter.",
        ))
        min_premarket_dollar_volume = g_col4.number_input(
            "Min pre-market dollar volume", value=0.0, step=100_000.0, key="min_gap_dollar_volume",
            help="Minimum pre-market dollar volume. 0 disables the filter.",
        )
    
        g_col5, g_col6 = st.columns(2)
        min_volume_ratio = g_col5.number_input(
            "Min volume ratio", value=0.0, step=0.1, key="min_gap_volume_ratio",
            help="Minimum pre-market volume as a multiple of the recent average daily volume. 0 disables.",
        )
        max_data_age = g_col6.number_input(
            "Max data age (minutes)", value=0.0, step=1.0, key="max_gap_data_age",
            help="Maximum staleness of the latest pre-market bar. 0 disables.",
        )
    
        g_col7, g_col8 = st.columns(2)
        max_spread_bps = g_col7.number_input(
            "Max spread (bps)", value=0.0, step=1.0, key="max_gap_spread",
            help="Maximum bid/ask spread in basis points. 0 disables.",
        )
        require_spread = g_col8.checkbox(
            "Require spread data", value=False, key="require_gap_spread",
            help="Filter out tickers when real spread quotes are unavailable.",
        )
    
        g_col9, g_col10 = st.columns(2)
        include_catalysts = g_col9.checkbox(
            "Include catalyst context", value=False, key="include_gap_catalysts",
            help="Fetch earnings and headline context when available. No causal claims are made.",
        )
        require_catalyst = g_col10.checkbox(
            "Require catalyst", value=False, key="require_gap_catalyst",
            help="Filter out tickers with no earnings or recent headline context.",
        )
    
        g_col11, g_col12 = st.columns(2)
        allow_after_open = g_col11.checkbox(
            "Allow after open", value=False, key="allow_gap_after_open",
            help="Allow retrospective scans after the regular session has opened.",
        )
        liquidity_lookback = int(g_col12.number_input(
            "Liquidity lookback sessions", value=20, min_value=5, key="gap_liquidity_lookback",
            help="Completed sessions used to compute average daily volume.",
        ))
    
        gap_report: GapScanReport | None = None
        gap_error = None
        if st.button("Scan Pre-Market Gaps", type="primary", key="btn_gaps"):
            max_data_age_value = max_data_age if max_data_age > 0 else None
            max_spread_bps_value = max_spread_bps if max_spread_bps > 0 else None
            config = GapScanConfig(
                min_abs_gap_pct=min_gap,
                min_price=min_price,
                min_premarket_volume=min_premarket_volume,
                min_premarket_dollar_volume=min_premarket_dollar_volume,
                min_premarket_volume_ratio=min_volume_ratio,
                max_data_age_minutes=max_data_age_value,
                max_spread_bps=max_spread_bps_value,
                require_spread=require_spread,
                require_catalyst=require_catalyst,
                catalyst_lookback_hours=24.0,
                liquidity_lookback_sessions=liquidity_lookback,
                allow_after_open=allow_after_open,
            )
            with st.spinner(f"Scanning {len(watchlist)} tickers for pre-market gaps…"):
                try:
                    gap_report = scan_gaps_with_report(
                        watchlist,
                        config=config,
                        provider=provider,
                        earnings_source=earnings_source if include_catalysts else None,
                        headline_source=earnings_source if include_catalysts else None,
                        include_catalysts=include_catalysts,
                        settings=settings,
                    )
                except ProviderCapabilityError as e:
                    gap_error = str(e)
                    st.error(gap_error)
    
        if gap_error is None and gap_report is not None:
            counts = gap_report.counts()
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("Requested", counts["requested"])
            m2.metric("Qualified", counts["qualified"])
            m3.metric("Filtered", counts["filtered"])
            m4.metric("Failed", counts["failed"])
            m5.metric("Outside window", counts["outside_window"])
            m6.metric("Provider failures", counts.get("provider_failure", 0))
    
            if gap_report.provider_errors:
                st.error("Provider failures: " + ", ".join(gap_report.provider_errors.keys()))
    
            if not gap_report.results.empty:
                st.success(f"{len(gap_report.results)} qualified gaps found")
                display = gap_report.results.copy()
                display["gap_display"] = display["gap_pct"].apply(lambda x: f"{x:+.2f}%")
                display["spread_display"] = display["spread_bps"].apply(
                    lambda x: f"{x:.2f} bps" if pd.notna(x) else "unavailable"
                )
                display["volume_ratio_display"] = display["premarket_volume_ratio"].apply(
                    lambda x: f"{x:.2f}x" if pd.notna(x) else "unavailable"
                )
                display_cols = [
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
                available_cols = [c for c in display_cols if c in display.columns]
                st.dataframe(
                    display[available_cols],
                    use_container_width=True,
                    column_config={
                        "gap_display": st.column_config.TextColumn("Gap %"),
                        "prev_close": st.column_config.NumberColumn("Prev Close", format="$%.2f"),
                        "pre_market": st.column_config.NumberColumn("Pre-Market", format="$%.2f"),
                        "premarket_volume": st.column_config.NumberColumn("Pre-Market Volume"),
                        "premarket_dollar_volume": st.column_config.NumberColumn("Pre-Market $ Volume", format="$%.2f"),
                        "volume_ratio_display": st.column_config.TextColumn("Volume Ratio"),
                        "spread_display": st.column_config.TextColumn("Spread"),
                        "catalyst_status": st.column_config.TextColumn("Catalyst"),
                        "data_age_minutes": st.column_config.NumberColumn("Data Age (min)"),
                        "requested_provider": st.column_config.TextColumn("Requested Provider"),
                        "actual_provider": st.column_config.TextColumn("Actual Provider"),
                        "note": st.column_config.TextColumn("Context", width="large"),
                    },
                )
    
                fig_data = gap_report.results.copy()
                fig_data["color"] = fig_data["direction"].map({"up": "green", "down": "red"})
                gap_fig = px.bar(fig_data, x="ticker", y="gap_pct", color="direction",
                                 color_discrete_map={"up": "green", "down": "red"},
                                 title="Pre-Market Gaps by Ticker", labels={"gap_pct": "Gap %", "ticker": ""})
                gap_fig.add_hline(y=0, line_color="white", line_width=1)
                gap_fig.update_layout(height=350)
                st.plotly_chart(gap_fig, use_container_width=True)
            else:
                if _all_provider_failures(counts):
                    st.error("All tickers failed due to provider or calculation errors. Check provider errors above.")
                elif _all_missing_data(counts):
                    st.error("All tickers lack required market data (previous close or pre-market bars).")
                elif _all_tickers_are(counts, _OUTSIDE_WINDOW_STATUSES):
                    st.info("No pre-market scan performed: current time is outside the pre-market window or the exchange is closed.")
                elif counts["qualified"] == 0:
                    st.info(f"No gaps above {min_gap}% found. {counts['filtered']} filtered, {counts['failed']} failed, {counts['outside_window']} outside window.")
    
            filtered = gap_report.observations[gap_report.observations["status"].isin(_FILTER_STATUSES)]
            failed = gap_report.observations[gap_report.observations["status"].isin(_FAILURE_STATUSES)]
            with st.expander("Filtered tickers", expanded=False):
                if filtered.empty:
                    st.caption("No tickers were filtered.")
                else:
                    st.dataframe(
                        filtered[["ticker", "gap_pct", "filter_reasons"]].reset_index(drop=True),
                        use_container_width=True,
                    )
            with st.expander("Failed tickers", expanded=False):
                if failed.empty:
                    st.caption("No tickers failed.")
                else:
                    st.dataframe(
                        failed[["ticker", "status", "error"]].reset_index(drop=True),
                        use_container_width=True,
                    )
    
    # ══════════════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 6 — OPTIONS ACTIVITY
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_options:
        st.subheader("Options Activity")
        st.caption(
            "Distinguishes true options-flow events from delayed options-chain snapshots. "
            "Chain volume and open interest describe aggregate positioning, not direction or intent."
        )
    
        with st.expander("How to read options activity", expanded=False):
            st.markdown("""
    **Options basics:**
    - A **call option** gives the holder the right to buy a stock at a set price.
    - A **put option** gives the holder the right to sell a stock at a set price.
    - **Volume** = number of contracts traded in a period.
    - **Open Interest (OI)** = total number of contracts currently outstanding.
    
    **True options flow vs. chain snapshots:**
    - **True flow** = transaction-level events (sweeps, block trades, reported premium). Only available
      from a true-flow provider such as Unusual Whales when configured.
    - **Chain snapshots** = a provider's listing of contracts with volume, OI, bid, ask, and last price.
      Tradier and Yahoo provide snapshots, not individual trade events. Sweep, side, and timestamp fields
      are not inferred from a snapshot.
    
    **Why Vol/OI ratio is reported:**
    A high volume-to-open-interest ratio can flag unusual turnover on a contract, but it only measures
    how much trading happened relative to outstanding contracts. It does not identify the trade side,
    whether the activity was opening or closing, or who initiated the trade.
    
    || Vol/OI Ratio | Reading |
    |---|---|---|
    || > 10x | Very high turnover relative to outstanding contracts |
    || 3–10x | Elevated turnover |
    || 1–3x | Typical to slightly elevated |
    
    **Sweeps:** Only a true-flow provider can report whether a trade was a sweep. A sweep indicator
    must come from the provider; it is never inferred from a chain snapshot.
    
    **Call/Put volume balance:**
    Aggregate call and put volume is a non-directional description of activity. It is **not** a
    bullish/bearish signal. A high call/put ratio only tells you more calls traded than puts; those
    calls could be bought or sold, opening or closing.
    
    **Data sources:**
    - **Unusual Whales** — true options-flow events when `UNUSUAL_WHALES_API_KEY` is configured.
    - **Tradier** — options-chain snapshots when `TRADIER_API_KEY` is configured.
    - **Yahoo** — delayed options-chain snapshots, no credentials required.
            """)
    
        st.caption(f"Selected options source: **{options_source}**")
        flow_status = resolve_flow_source(options_source, settings=settings)
        chain_status = resolve_chain_source(options_source, settings=settings)
    
        o_col1, o_col2 = st.columns(2)
        min_vol_oi = o_col1.slider(
            "Min Vol/OI ratio", 1.0, 20.0, 3.0, step=0.5, key="min_vol_oi",
            help=(
                "Only show options contracts where volume exceeds this multiple of open interest.\n\n"
                "• **1–2x** — slightly elevated, lots of noise.\n"
                "• **3x (default)** — meaningful turnover threshold.\n"
                "• **10x+** — very high turnover."
            ),
        )
        o_col2.markdown("""
    **Vol/OI guide:**
    - **>10x** — very high turnover
    - **3–10x** — elevated turnover
    - **1–3x** — typical to slightly elevated
        """)
    
        st.divider()
        st.subheader("True Options Flow")
        st.caption("Transaction-level flow events from Unusual Whales. Requires a configured API key.")
        _options_status_container(flow_status, "True-flow source")
    
        flow_disabled = _true_flow_disabled_message(flow_status)
        if flow_disabled:
            st.warning(flow_disabled)
    
        flow_report = None
        if st.button(
            "Scan True Options Flow",
            type="primary",
            key="btn_options",
            disabled=not flow_status.available,
            help="Scan for transaction-level flow events (sweeps, premium, side) from Unusual Whales.",
        ):
            with st.spinner(f"Scanning true options flow for {len(watchlist)} tickers…"):
                flow_report = scan_unusual_flow_with_report(
                    watchlist, min_vol_oi=min_vol_oi, source=options_source, settings=settings
                )
    
        _render_options_report(flow_report, "True Options Flow", min_vol_oi)
    
        st.divider()
        st.subheader("Options Chain Activity")
        st.caption("Options-chain snapshots from Tradier or Yahoo. Volume, OI, bid/ask/last only.")
        _options_status_container(chain_status, "Chain source")
    
        chain_disabled = not chain_status.available or chain_status.data_kind != OptionsDataKind.CHAIN_SNAPSHOT
        chain_disabled_message = _chain_scan_disabled_message(chain_status)
        if chain_disabled_message:
            st.warning(chain_disabled_message)
    
        chain_report = None
        if st.button(
            "Scan Options Chain Activity",
            key="btn_options_chain",
            disabled=chain_disabled,
            help="Scan Tradier or Yahoo option chains for elevated volume/OI turnover.",
        ):
            with st.spinner(f"Scanning options chains for {len(watchlist)} tickers…"):
                chain_report = scan_chain_activity_with_report(
                    watchlist, min_vol_oi=min_vol_oi, source=options_source, settings=settings
                )
    
        _render_options_report(chain_report, "Options Chain Activity", min_vol_oi)
    
        st.divider()
        st.subheader("Call/Put Volume Balance")
        st.caption("Aggregate call vs. put volume from the selected chain source. This is non-directional.")
        pc_ticker = st.selectbox("Select ticker", watchlist, key="sel_pc")
        if st.button(
            "Get Volume Balance",
            key="btn_pc",
            help="Fetch the options chain and compute a non-directional call/put volume balance.",
        ):
            with st.spinner(f"Fetching options data for {pc_ticker}…"):
                activity = get_put_call_activity(pc_ticker, source=options_source, settings=settings)
            if activity.get("error"):
                st.error(activity["error"])
            else:
                s_col1, s_col2, s_col3, s_col4 = st.columns(4)
                s_col1.metric(
                    "Put/Call Ratio",
                    activity.get("put_call_volume_ratio", "N/A"),
                    help="Put volume ÷ Call volume. Non-directional description of aggregate volume.",
                )
                s_col2.metric("Call Volume", activity.get("call_volume", 0))
                s_col3.metric("Put Volume", activity.get("put_volume", 0))
                s_col4.metric("Volume Balance", activity.get("volume_balance", "unknown").upper())
                if not activity.get("directional_inference"):
                    st.info(
                        "Volume balance is non-directional. It does not imply bullish or bearish intent."
                    )
    
    # TAB 7 — ALERTS
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_alerts:
        render_alerts_tab(settings=settings)
    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 8 — SIGNAL JOURNAL
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_journal:
        render_signal_journal_tab(
            settings=settings,
            timeframe=timeframe,
            provider=provider,
        )

    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 9 — WEIGHTS
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_weights:
        render_weights_tab(settings=settings)
    
    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 10 — HELP
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_help:
        render_help_tab()
