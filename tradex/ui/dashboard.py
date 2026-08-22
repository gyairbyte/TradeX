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

import streamlit as st

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.premarket.models import VALID_TICKER_RE
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
from tradex.ui.tabs.options_activity import render_options_activity_tab
from tradex.ui.tabs.pattern_similarity import render_pattern_similarity_tab
from tradex.ui.tabs.premarket import render_premarket_tab
from tradex.ui.tabs.scanner import render_scanner_tab
from tradex.ui.tabs.signal_journal import render_signal_journal_tab
from tradex.ui.tabs.weights import render_weights_tab
from tradex.watchlists import DEFAULT_NAME as WL_DEFAULT_NAME
from tradex.watchlists import presets as wl_presets
from tradex.watchlists import store as wl_store

DEFAULT_TICKERS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "AMZN",
    "META",
    "GOOGL",
    "AMD",
    "PLTR",
    "MSTR",
    "SPY",
    "QQQ",
    "SOXL",
    "TQQQ",
    "SMCI",
    "ARM",
    "AVGO",
    "MU",
    "CRWD",
    "NET",
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
    st.caption(
        "Scan, track, and get alerted on technical indicators and market context across intraday, short-term, and long-term timeframes."
    )

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
                "• **Intraday** — 5-minute bars over 5 days. For intraday momentum and swing conditions.\n"
                "• **Short** — Daily bars over 60 days. For short-term technical conditions.\n"
                "• **Long** — Weekly bars over 2 years. For multi-week to multi-month trend context."
            ),
        )

        min_score = st.slider(
            "Min score",
            0,
            100,
            40,
            help=(
                "Filters out stocks below this signal score. Each stock is scored 0–100 "
                "based on how many technical conditions are met.\n\n"
                "• **Lower (20–40)** — casts a wider net across discovery heuristics; more results.\n"
                "• **Middle (40–65)** — balanced filtering across technical conditions.\n"
                "• **Higher (65–100)** — filters to stocks meeting multiple simultaneous conditions; fewer results.\n\n"
                "Note: Technical scores are unvalidated discovery heuristics, not a measure of trade conviction or probability."
            ),
        )

        _PROVIDER_OPTIONS = ["schwab", "alpaca", "yahoo", "ibkr"]
        _PROVIDER_LABELS = {
            "schwab": "Schwab — Primary",
            "alpaca": "Alpaca — Degraded Intraday (IEX)",
            "yahoo": "Yahoo — Research / Fallback",
            "ibkr": "IBKR — Archived / Manual",
        }
        _default_provider = settings.data.data_provider.lower()
        if _default_provider not in _PROVIDER_OPTIONS:
            _default_provider = "schwab"
        provider = st.selectbox(
            "OHLCV provider",
            _PROVIDER_OPTIONS,
            index=_PROVIDER_OPTIONS.index(_default_provider),
            format_func=lambda p: _PROVIDER_LABELS.get(p, p),
            help=(
                "Market data provider used by the scanner, confluence, pattern matching, "
                "chart drill-downs, and outcome tracking. The selection is passed to the central "
                "OHLCV fetcher and the daily-history abstraction.\n\n"
                "• **Schwab (Primary)** — Primary TradeX data foundation. Requires a Schwab developer app (API key + secret) and a local OAuth token file.\n"
                "• **Alpaca (Degraded Intraday)** — Free-tier IEX feed. Lower liquidity coverage than consolidated SIP.\n"
                "• **Yahoo (Research / Fallback)** — Delayed market data for research, daily/weekly analysis, and the specialized pre-market gap scanner.\n"
                "• **IBKR (Archived / Manual)** — Requires local TWS or IB Gateway running.\n\n"
                "• Fallback is explicit, not automatic: if the selected provider is not configured, "
                "the fetch will surface a safe error rather than silently switching providers.\n\n"
                "Specialized sources (options, earnings, market-cap ranking, index "
                "constituents) have their own source controls and are not affected by this selector."
            ),
        )
        st.caption(f"OHLCV provider: **{_PROVIDER_LABELS.get(provider, provider)}**")

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
        preset_names = sorted([w["name"] for w in saved_lists if w["name"] in _preset_labels])
        custom_names = sorted([w["name"] for w in saved_lists if w["name"] not in _preset_labels])
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
                "New watchlist name",
                key="wl_create_name",
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
                        st.success(
                            f"Created '{create_name}' with {len(parsed)} tickers: {', '.join(parsed[:8])}{'…' if len(parsed) > 8 else ''}"
                        )
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

            st.divider()
            st.markdown("**Add a preset**")
            st.caption(
                "One-click watchlists for common universes. Imports a snapshot into your saved lists."
            )
            preset_options = {
                f"{p.label} ({len(p.tickers)} tickers)": p for p in wl_presets.PRESETS
            }
            chosen_label = st.selectbox(
                "Preset",
                list(preset_options.keys()),
                key="wl_preset_pick",
                help="Imports the selected preset into your saved watchlists under its label. Re-importing overwrites.",
            )
            chosen_preset = preset_options[chosen_label]
            st.caption(chosen_preset.description)
            col_imp, col_refresh = st.columns(2)
            if col_imp.button(
                "Import preset", key="wl_preset_import_btn", use_container_width=True
            ):
                try:
                    wl_store.save(
                        chosen_preset.label, list(chosen_preset.tickers), settings=settings
                    )
                    st.success(
                        f"Imported '{chosen_preset.label}' ({len(chosen_preset.tickers)} tickers). Select it in 'Active watchlist'."
                    )
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

                with st.spinner(
                    "Refreshing presets from Wikipedia + yfinance (this may take ~30-60s)…"
                ):
                    try:
                        result = wl_refresh.refresh_all(market_cap_source=market_cap_source)
                        overrides = wl_refresh.result_to_preset_overrides(result)
                        imported = 0
                        for key, tickers in overrides.items():
                            preset = wl_presets.PRESETS_BY_KEY.get(key)
                            if preset and tickers:
                                wl_store.save(preset.label, tickers, settings=settings)
                                imported += 1
                        st.success(
                            f"Refreshed {imported} presets. Active watchlists overwritten with latest constituents."
                        )
                        for w in result.warnings:
                            st.warning(w)
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Refresh failed: {e}")

            st.divider()
            st.markdown("**Snapshot current selection**")
            new_name = st.text_input(
                "Name",
                key="wl_save_name",
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
            0,
            21,
            0,
            help=(
                "Filter out stocks with earnings reports within this many calendar days.\n\n"
                "• **0 (default)** — earnings exclusion filter disabled. Unknown earnings dates are surfaced in tables and observations but do not block candidate discovery.\n"
                "• **>0** — earnings exclusion filter enabled. Because proximity to earnings cannot be verified, stocks with unknown/unavailable earnings dates FAIL CLOSED and are not eligible for scoring or ranking under this filter.\n"
                "• **3–5 days** — avoid being long into a print. Technical setups can be "
                "wiped out by an earnings gap regardless of how clean they looked.\n"
                "• **7–14 days** — most conservative. Filters out any setup where the move "
                "could resolve into the earnings window.\n\n"
                "Results still show days-until-earnings as a column even when this is 0, "
                "so you can see the proximity at a glance."
            ),
        )

        st.divider()
        st.markdown(
            "[📖 Help & Documentation](#help)",
            help="Open the Help tab for full feature explanations.",
        )

    (
        tab_scanner,
        tab_coil,
        tab_confluence,
        tab_pattern,
        tab_premarket,
        tab_options,
        tab_alerts,
        tab_journal,
        tab_weights,
        tab_help,
    ) = st.tabs(
        [
            "Scanner",
            "Coil Detector",
            "Confluence",
            "Pattern Similarity — Experimental Research",
            "Pre-Market",
            "Options Activity",
            "Alerts",
            "Signal Journal",
            "Weights",
            "Help",
        ]
    )

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
        render_pattern_similarity_tab(
            settings=settings,
            watchlist=watchlist,
            provider=provider,
        )

    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 5 — PRE-MARKET GAP SCANNER
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_premarket:
        render_premarket_tab(
            settings=settings,
            watchlist=watchlist,
            provider="yahoo",
            earnings_source=earnings_source,
        )

    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 6 — OPTIONS ACTIVITY
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_options:
        render_options_activity_tab(
            settings=settings,
            watchlist=watchlist,
            options_source=options_source,
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
