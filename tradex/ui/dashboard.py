"""
Streamlit dashboard — eight tabs:
  1. Scanner       : run screener, view ranked results, drill-down chart
  2. Coil Detector : stocks building pressure over multiple days (pre-signal)
  3. Confluence    : stocks scoring well across multiple timeframes
  4. Pattern Match : compare live stocks against historical run-up/decline fingerprints
  5. Pre-Market    : gap scanner — identify gap-up/down candidates before open
  6. Options Flow  : unusual options activity — vol/OI spikes, put/call sentiment
  7. Alerts        : configure Discord/email alert thresholds
  8. Signal Journal: historical signal outcomes (did the move happen?)

Run with: streamlit run tradex/ui/dashboard.py
"""
import os
import re
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from tradex.screener.engine import run
from tradex.data.fetcher import DEFAULT_PROVIDER, ProviderCapabilityError, fetch, resolve_provider
from tradex.signals.indicators import add_indicators
from tradex.tracker import store, analyzer
from tradex.tracker.confluence import run_confluence_screen
from tradex.tracker.outcome_tracker import run_outcome_pass, get_outcome_stats
from tradex.patterns.fingerprint import run_full_build, list_fingerprints, load_fingerprint
from tradex.patterns.matcher import run_match_screen, match_ticker
from tradex.patterns.config import PROFILES
from tradex.premarket.gap_scanner import scan_gaps
from tradex.options.flow import scan_unusual_flow, get_put_call_sentiment
from tradex.alerts.notifier import (
    send_alert, DISCORD_TOKEN, DISCORD_CHANNEL_ID, EMAIL_TO,
    COIL_ALERT_THRESHOLD, PATTERN_ALERT_THRESHOLD, CONFLUENCE_ALERT_THRESHOLD,
)
from tradex.watchlists import store as wl_store, DEFAULT_NAME as WL_DEFAULT_NAME
from tradex.watchlists import presets as wl_presets
from tradex.signals import weights as signal_weights
from tradex.ui.source_defaults import (
    options_source_index,
    earnings_source_index,
    market_cap_source_index,
    options_sources,
    earnings_sources,
    market_cap_sources,
)

store.init()
wl_store.init()

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
    "AMD", "PLTR", "MSTR", "SPY", "QQQ", "SOXL", "TQQQ",
    "SMCI", "ARM",  "AVGO", "MU",   "CRWD", "NET",
]

_TICKER_SPLIT_RE = re.compile(r"[\s,;|]+")
_TICKER_VALID_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _parse_pasted_tickers(raw: str) -> list[str]:
    """Parse free-form pasted ticker text into a deduped uppercase list.

    Accepts any combination of commas, newlines, tabs, semicolons, pipes, or
    spaces as separators. Strips $ prefixes (e.g. "$AAPL"). Drops anything
    that doesn't look like a plausible ticker symbol.
    """
    seen: list[str] = []
    for tok in _TICKER_SPLIT_RE.split(raw or ""):
        tok = tok.strip().lstrip("$").upper()
        if tok and _TICKER_VALID_RE.match(tok) and tok not in seen:
            seen.append(tok)
    return seen

st.set_page_config(page_title="TradeX", layout="wide")
st.title("TradeX — Market Opportunity Scanner")
st.caption("Scan, track, and get alerted on stock setups across intraday, short-term, and long-term timeframes.")

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
    _default_provider = os.getenv("DATA_PROVIDER", "yahoo").lower()
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
        index=options_source_index(),
        help=(
            "Options-flow data source. ``auto`` follows the priority "
            "Unusual Whales → Tradier → Yahoo based on configured API keys. "
            "A specific paid source will not fall back if credentials are missing."
        ),
    )
    earnings_source = st.selectbox(
        "Earnings source",
        earnings_sources(),
        index=earnings_source_index(),
        help="Earnings-calendar source. Only Yahoo is supported in this release.",
    )
    market_cap_source = st.selectbox(
        "Market-cap source",
        market_cap_sources(),
        index=market_cap_source_index(),
        help="Source for S&P 100 market-cap ranking when refreshing presets. ``schwab`` requires Schwab credentials.",
    )

    # ── Watchlist selector ───────────────────────────────────────────────────
    saved_lists = wl_store.list_all()
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
        base_tickers = wl_store.load(active_name) or DEFAULT_TICKERS

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
                    wl_store.save(create_name, parsed)
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
                wl_store.save(chosen_preset.label, list(chosen_preset.tickers))
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
                            wl_store.save(preset.label, tickers)
                            imported += 1
                    st.success(f"Refreshed {imported} presets. Active watchlists overwritten with latest constituents.")
                    for w in result.warnings:
                        st.warning(w)
                    st.rerun()
                except Exception as e:
                    st.error(f"Refresh failed: {e}")

        st.divider()
        st.markdown("**Snapshot current selection**")
        new_name = st.text_input(
            "Name", key="wl_save_name",
            help="Save the active list + comma-separated additions under this name. Re-using an existing name overwrites it.",
        )
        if st.button("Save current", key="wl_save_btn", use_container_width=True):
            try:
                wl_store.save(new_name, watchlist)
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
                deleted = [n for n in to_delete if wl_store.delete(n)]
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
    "Scanner", "Coil Detector", "Confluence", "Pattern Match",
    "Pre-Market", "Options Flow", "Alerts", "Signal Journal", "Weights", "Help",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SCANNER
# ══════════════════════════════════════════════════════════════════════════════
with tab_scanner:
    st.subheader("Signal Scanner")
    st.caption(
        "Scores every stock in your watchlist 0–100 using technical indicators. "
        "Higher score = more conditions aligned. Each result shows exactly why it was flagged."
    )

    with st.expander("How scoring works", expanded=False):
        st.markdown("""
Each timeframe runs its own set of signal checks. Points are awarded for each condition met and capped at 100.

| Signal | What it checks | Points |
|---|---|---|
| **Volume surge** | Current volume vs. 20-bar average. >2x = strong institutional interest | Up to 30 |
| **RSI momentum** | Relative Strength Index in the 55–75 zone = trending without being overbought | Up to 20 |
| **MACD crossover** | MACD line crossing above signal line = trend shift | Up to 30 |
| **EMA structure** | Price above EMA20 which is above EMA50 = healthy uptrend structure | Up to 25 |
| **Bollinger Band expansion** | Bands tightening then widening = volatility breakout | Up to 20 |
| **Pullback to EMA** | Price dipping back to EMA20 in an uptrend = entry opportunity | Up to 15 |

**Score guide:**
- 0–39: Weak / no clear setup
- 40–59: Worth watching
- 60–79: Strong signal
- 80–100: Multiple conditions aligned — highest conviction
        """)

    run_scan = st.button("Run Scan", type="primary", key="btn_scan",
                         help="Fetch live data for all watchlist tickers and score each one.")

    if run_scan:
        progress_bar = st.progress(0.0, text=f"Scanning {len(watchlist)} tickers on {timeframe}…")

        def _update_progress(done: int, total: int) -> None:
            progress_bar.progress(done / total, text=f"Scanning {done}/{total} tickers on {timeframe}…")

        results = run(
            watchlist,
            timeframe=timeframe,
            min_score=min_score,
            exclude_earnings_within=earnings_buffer if earnings_buffer > 0 else None,
            progress=_update_progress,
            provider=provider,
            earnings_source=earnings_source,
        )
        progress_bar.empty()
        if results.empty:
            st.warning("No opportunities found. Lower the min score or add more tickers.")
        else:
            if earnings_buffer > 0:
                st.success(f"Found {len(results)} opportunities (excluded tickers with earnings within {earnings_buffer}d)")
            else:
                st.success(f"Found {len(results)} opportunities")
            store.record_signals(results, timeframe, provider=provider)
            st.dataframe(
                results,
                use_container_width=True,
                column_config={
                    "ticker":              st.column_config.TextColumn("Ticker"),
                    "score":               st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
                    "last_close":          st.column_config.NumberColumn("Last Close", format="$%.2f"),
                    "volume_ratio":        st.column_config.NumberColumn("Vol Ratio", help="Current volume ÷ 20-bar average. >2 = unusually high volume."),
                    "rsi":                 st.column_config.NumberColumn("RSI", help="Relative Strength Index. 30=oversold, 70=overbought. Sweet spot: 50–70."),
                    "days_until_earnings": st.column_config.NumberColumn(
                        "Earnings In",
                        format="%d d",
                        help="Calendar days until the next scheduled earnings report. Blank = none scheduled or unknown (e.g. ETFs).",
                    ),
                    "reasons":             st.column_config.TextColumn("Reasons", width="large"),
                    "provider":            st.column_config.TextColumn("OHLCV Provider", help="Market-data provider used to score this ticker."),
                },
            )
            st.session_state["scan_results"] = results
            st.session_state["scan_timeframe"] = timeframe
            st.session_state["scan_provider"] = provider

    if "scan_results" in st.session_state and not st.session_state["scan_results"].empty:
        st.divider()
        st.subheader("Drill-down Chart")
        st.caption("Candlestick chart with EMA20 (orange), EMA50 (blue), and Bollinger Bands (gray shaded). Volume bars below. Uses the provider from the saved scan.")
        tickers_with_signals = st.session_state["scan_results"]["ticker"].tolist()
        selected = st.selectbox("Select ticker", tickers_with_signals, key="sel_scanner",
                                help="Pick any stock from the scan results to view its chart.")
        tf = st.session_state["scan_timeframe"]
        scan_provider = st.session_state.get("scan_provider", provider)

        df = fetch(selected, tf, provider=scan_provider)
        df = add_indicators(df)

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="Price",
        ))
        fig.add_trace(go.Scatter(x=df.index, y=df["ema_20"], name="EMA20",
                                 line=dict(color="orange", width=1)))
        fig.add_trace(go.Scatter(x=df.index, y=df["ema_50"], name="EMA50",
                                 line=dict(color="blue", width=1)))
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"], name="BB Upper",
                                 line=dict(color="gray", dash="dot", width=1)))
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"], name="BB Lower",
                                 line=dict(color="gray", dash="dot", width=1),
                                 fill="tonexty", fillcolor="rgba(200,200,200,0.1)"))
        fig.update_layout(xaxis_rangeslider_visible=False, height=500)
        st.plotly_chart(fig, use_container_width=True)

        vol_fig = go.Figure()
        colors = ["green" if c >= o else "red" for c, o in zip(df["close"], df["open"])]
        vol_fig.add_trace(go.Bar(x=df.index, y=df["volume"], marker_color=colors, name="Volume"))
        vol_fig.add_trace(go.Scatter(x=df.index, y=df["volume_sma20"], name="Vol SMA20",
                                     line=dict(color="white", width=1.5)))
        vol_fig.update_layout(height=200)
        st.plotly_chart(vol_fig, use_container_width=True)

        row = st.session_state["scan_results"][
            st.session_state["scan_results"]["ticker"] == selected
        ].iloc[0]
        st.info(f"**Score: {row['score']}** — {row['reasons']}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — COIL DETECTOR
# ══════════════════════════════════════════════════════════════════════════════
with tab_coil:
    st.subheader("Coil Detector — Pre-Breakout Setups")
    st.caption(
        "Finds stocks that have appeared in multiple scans over several days without breaking out yet. "
        "These are the setups building pressure before a move — caught *before* the crowd sees them."
    )

    with st.expander("What is a coil and how does it work?", expanded=False):
        st.markdown("""
A **coil** is a stock that is quietly building technical pressure without yet making a large price move.
Think of it like a spring being compressed — the longer it builds, the bigger the potential release.

**TradeX defines a coil as a stock that:**
1. Has appeared in scans at least N times within the look-back window
2. Still has a score above the signal threshold (45+)
3. Has NOT already made a large price move (≥3% would mean it already broke out)
4. Has a score that is stable or rising (not fading)

**Why this matters:** Standard screeners show you what happened. The coil detector shows you what's *building*.
By the time a stock appears on Finviz or TradingView's trending list, thousands of traders already see it.
Coils let you get positioned before the obvious move.

**Coil Strength score** combines:
- How many times the stock appeared (more = stronger conviction)
- The latest signal score (higher = more conditions met)
- The slope of the score trend (accelerating = higher strength)

**Score trend directions:**
- 🟢 **Building** — score is rising each scan. Best setups.
- 🟡 **Stable** — holding steady. Still valid, not accelerating.
- 🔴 **Fading** — score declining. Setup may be breaking down.
        """)

    col1, col2 = st.columns(2)
    coil_days = col1.slider(
        "Look-back window (days)", 3, 21, 7, key="coil_days",
        help=(
            "How many calendar days of scan history to search through.\n\n"
            "• **Shorter (3–5 days)** — only recent setups. Misses slower-building coils.\n"
            "• **7 days (default)** — one trading week. Good balance.\n"
            "• **Longer (10–21 days)** — catches slower accumulation patterns. "
            "More history required (watcher must have been running for that many days)."
        ),
    )
    min_appearances = col2.slider(
        "Min appearances", 2, 10, 2, key="coil_apps",
        help=(
            "Minimum number of scan sessions where a stock must have scored above threshold "
            "to be considered a coil.\n\n"
            "• **2 (default)** — appeared at least twice. Low bar, catches early setups.\n"
            "• **3–5** — repeated pattern. More reliable signal.\n"
            "• **6–10** — long-duration coil. Very persistent setup — could resolve soon.\n\n"
            "Note: this requires the watcher to have run enough sessions to accumulate that history."
        ),
    )

    if st.button("Detect Coils", key="btn_coil", type="primary",
                 help="Search signal history for stocks matching the coil definition."):
        coils = analyzer.detect_coils(timeframe, days=coil_days, min_appearances=min_appearances)
        if coils.empty:
            st.info("No coiling setups found. Run the Scanner a few times over multiple days to build history.")
        else:
            st.success(f"{len(coils)} coiling setups detected")
            display_cols = ["ticker", "coil_strength", "appearances", "latest_score",
                            "score_trend", "trend_direction", "last_close"]
            st.dataframe(
                coils[display_cols],
                use_container_width=True,
                column_config={
                    "ticker":          st.column_config.TextColumn("Ticker"),
                    "coil_strength":   st.column_config.ProgressColumn("Coil Strength", min_value=0, max_value=100, help="Combined score of duration, signal level, and trend acceleration."),
                    "appearances":     st.column_config.NumberColumn("Appearances", help="How many scan sessions this stock has shown up in."),
                    "latest_score":    st.column_config.ProgressColumn("Latest Score", min_value=0, max_value=100),
                    "score_trend":     st.column_config.NumberColumn("Trend Slope", help="Positive = score rising each scan. Negative = fading."),
                    "trend_direction": st.column_config.TextColumn("Direction"),
                    "last_close":      st.column_config.NumberColumn("Last Close", format="$%.2f"),
                },
            )

            st.divider()
            st.subheader("Score History")
            st.caption("Shows how this stock's signal score has evolved across scan sessions.")
            selected_coil = st.selectbox("Select ticker to inspect", coils["ticker"].tolist(), key="sel_coil")
            state = analyzer.get_ticker_state(selected_coil, timeframe, days=coil_days)

            if state["score_history"]:
                score_fig = px.line(
                    y=state["score_history"],
                    labels={"x": "Scan #", "y": "Score"},
                    title=f"{selected_coil} — Score History ({timeframe})",
                    markers=True,
                )
                score_fig.add_hline(y=50, line_dash="dot", line_color="yellow",
                                    annotation_text="Signal threshold (50)")
                score_fig.update_layout(height=300)
                st.plotly_chart(score_fig, use_container_width=True)

            st.info(f"**{state['status'].upper()}** — {state['summary']}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CONFLUENCE
# ══════════════════════════════════════════════════════════════════════════════
with tab_confluence:
    st.subheader("Confluence Scanner — Multi-Timeframe Alignment")
    st.caption(
        "Finds stocks scoring well across intraday, short-term, AND long-term simultaneously. "
        "When all timeframes agree, the setup has more conviction."
    )

    with st.expander("Why confluence matters", expanded=False):
        st.markdown("""
Most screeners only look at one timeframe. A stock can look great on a 5-minute chart but be
in a downtrend on the daily — that's a low-conviction trade fighting the bigger trend.

**Confluence means all timeframes are telling the same story:**
- The intraday chart (5-min) shows a momentum setup
- The daily chart (short-term) shows an uptrend structure
- The weekly chart (long-term) shows the stock in a healthy secular trend

**Confluence score weights:**
| Timeframe | Weight | Why |
|---|---|---|
| Intraday (5m) | 30% | Noisiest — good confirmation but not the driver |
| Short-term (1d) | 40% | Most actionable timeframe for swing trades |
| Long-term (1wk) | 30% | Establishes whether the broader trend supports the trade |

**Confluence tiers:**
- 🟢 **90+** — All three timeframes strongly aligned. Rare and high conviction.
- 🟡 **70–89** — Two or more timeframes well aligned. Strong setup.
- 🟠 **50–69** — Partial alignment. Use additional confirmation.
- 🔴 **<50** — Single timeframe only. Low conviction — treat carefully.

A stock scoring 80+ on intraday alone is interesting. The same stock also scoring 70+ on short and long is a fundamentally different — and better — trade.
        """)

    min_confluence = st.slider(
        "Min confluence score", 0, 100, 50, key="min_conf",
        help=(
            "Filters results to stocks where the weighted average score across all three "
            "timeframes exceeds this value.\n\n"
            "• **Lower (30–50)** — more results, includes partial alignments.\n"
            "• **50–70** — meaningful alignment across at least two timeframes.\n"
            "• **Higher (70–100)** — only the strongest multi-timeframe setups. Fewer but higher quality."
        ),
    )

    if st.button("Run Confluence Scan", key="btn_conf", type="primary",
                 help="Score each watchlist ticker across all three timeframes simultaneously. Takes ~3x longer than a single-timeframe scan."):
        with st.spinner(f"Scoring {len(watchlist)} tickers across all timeframes…"):
            conf_results = run_confluence_screen(
                watchlist,
                min_confluence=min_confluence,
                exclude_earnings_within=earnings_buffer if earnings_buffer > 0 else None,
                provider=provider,
                earnings_source=earnings_source,
            )
        if conf_results.empty:
            st.warning("No confluence setups found. Lower the min confluence score.")
        else:
            if earnings_buffer > 0:
                st.success(f"{len(conf_results)} multi-timeframe setups found (excluded tickers with earnings within {earnings_buffer}d)")
            else:
                st.success(f"{len(conf_results)} multi-timeframe setups found")
            st.dataframe(
                conf_results,
                use_container_width=True,
                column_config={
                    "ticker":              st.column_config.TextColumn("Ticker"),
                    "confluence_score":    st.column_config.ProgressColumn("Confluence", min_value=0, max_value=100, help="Weighted average score across all three timeframes."),
                    "tier":                st.column_config.TextColumn("Tier"),
                    "active_timeframes":   st.column_config.TextColumn("Active TFs", help="Timeframes where score ≥ 50."),
                    "score_intraday":      st.column_config.ProgressColumn("Intraday", min_value=0, max_value=100),
                    "score_short":         st.column_config.ProgressColumn("Short", min_value=0, max_value=100),
                    "score_long":          st.column_config.ProgressColumn("Long", min_value=0, max_value=100),
                    "days_until_earnings": st.column_config.NumberColumn(
                        "Earnings In",
                        format="%d d",
                        help="Calendar days until the next scheduled earnings report. Blank = none scheduled or unknown.",
                    ),
                    "last_close":          st.column_config.NumberColumn("Last Close", format="$%.2f"),
                },
            )
            st.session_state["conf_results"] = conf_results

    if "conf_results" in st.session_state and not st.session_state["conf_results"].empty:
        st.divider()
        selected_conf = st.selectbox("Drill down", st.session_state["conf_results"]["ticker"].tolist(), key="sel_conf")
        row = st.session_state["conf_results"][
            st.session_state["conf_results"]["ticker"] == selected_conf
        ].iloc[0]
        scores = {
            "Intraday": row.get("score_intraday", 0),
            "Short":    row.get("score_short", 0),
            "Long":     row.get("score_long", 0),
        }
        bar_fig = px.bar(
            x=list(scores.keys()), y=list(scores.values()),
            labels={"x": "Timeframe", "y": "Score"},
            title=f"{selected_conf} — Confluence Score: {row['confluence_score']} ({row['tier']})",
            color=list(scores.values()),
            color_continuous_scale="RdYlGn",
            range_color=[0, 100],
        )
        bar_fig.update_layout(height=350, showlegend=False)
        st.plotly_chart(bar_fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — PATTERN MATCH
# ══════════════════════════════════════════════════════════════════════════════
with tab_pattern:
    st.subheader("Pattern Match — Historical Run-Up & Decline Fingerprints")
    st.caption(
        "Compares each stock's current 10-day pattern against the averaged shape of "
        "hundreds of historical run-ups or declines. High similarity = the setup looks "
        "like it did before major moves in the past."
    )

    with st.expander("How pattern matching works", expanded=False):
        st.markdown("""
**The idea:** if hundreds of major run-ups all had a similar price/volume shape in the days before,
and your stock's current shape matches that pattern — it's worth paying attention.

**Step 1 — Mining:** TradeX scans 3 years of history across 40+ stocks and finds every event where
a stock moved +15% or more in 5 days (a "run-up") or -12% (a "decline"). It then extracts the
10 trading days *before* each event started.

**Step 2 — Fingerprinting:** All those pre-event windows are normalized (so NVDA at $800 and
AMD at $100 are comparable) and averaged into a "fingerprint" — the typical shape of price,
volume, RSI, MACD, and Bollinger Band width in the days leading up to a major move.

**Step 3 — Matching:** Your stock's current 10-day window is compared against that fingerprint
using Pearson correlation across 5 series. Each series is weighted:

| Series | Weight | Why |
|---|---|---|
| Price shape | 35% | Most direct signal |
| Volume shape | 30% | Institutional footprint |
| RSI | 15% | Momentum confirmation |
| MACD | 10% | Trend direction |
| BB Width | 10% | Volatility context |

**Similarity score guide:**
- 90–100%: Near-perfect match
- 75–89%: Strong match — alert threshold
- 60–74%: Moderate — watch but don't act alone
- <60%: Low similarity / noise

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
                    built = run_full_build(profile=fp_profile, event_type=fp_etype, verbose=False, provider=provider)
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
        help="'runup' = looking for stocks about to go up. 'decline' = looking for potential shorts or stocks to avoid.",
    )
    match_threshold = m_col3.slider(
        "Min similarity", 0, 100, int(PROFILES[match_profile].alert_threshold), key="match_thresh",
        help=(
            "Only show stocks above this similarity % to the historical fingerprint.\n\n"
            "• **Lower (50–65%)** — more results, some false positives.\n"
            "• **75% (default)** — strong match threshold.\n"
            "• **Higher (85–100%)** — near-perfect matches only. Very few results."
        ),
    )

    if st.button("Run Pattern Screen", key="btn_match", type="primary"):
        fp_check = load_fingerprint(match_etype, match_profile, source=provider)
        if fp_check is None:
            st.error(f"No '{match_etype}' fingerprint for profile '{match_profile}' with source '{provider}'. Build it first.")
        else:
            with st.spinner(f"Matching {len(watchlist)} tickers against {match_etype} fingerprint…"):
                match_results = run_match_screen(
                    watchlist, event_type=match_etype,
                    profile=match_profile, min_similarity=match_threshold,
                    provider=provider,
                )
            if match_results.empty:
                st.warning(f"No tickers matched above {match_threshold}% similarity.")
            else:
                st.success(f"{len(match_results)} pattern matches found")
                st.dataframe(
                    match_results,
                    use_container_width=True,
                    column_config={
                        "ticker":           st.column_config.TextColumn("Ticker"),
                        "similarity_score": st.column_config.ProgressColumn("Similarity", min_value=0, max_value=100, help="How closely the current pattern matches historical pre-move fingerprint."),
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
        st.subheader("Pattern Overlay — Live vs Fingerprint")
        st.caption(
            "White line = your stock's last 10 days (normalized to % change from start). "
            "Orange dashed = historical average pre-move shape. Shaded band = ±1 standard deviation."
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
            )
            fp_upper = fp_data["series"].get("price_pct", {}).get("upper", fp_mean)
            fp_lower = fp_data["series"].get("price_pct", {}).get("lower", fp_mean)
            live_price = detail["live_series"].get("price_pct", [])[-n:]

            price_fig = go.Figure()
            price_fig.add_trace(go.Scatter(x=x, y=fp_upper, mode="lines",
                                           line=dict(width=0), showlegend=False))
            price_fig.add_trace(go.Scatter(x=x, y=fp_lower, mode="lines",
                                           line=dict(width=0), fill="tonexty",
                                           fillcolor="rgba(255,165,0,0.15)", name="Historical range ±1σ"))
            price_fig.add_trace(go.Scatter(x=x, y=fp_mean, mode="lines",
                                           line=dict(color="orange", dash="dash", width=2), name="Historical avg"))
            price_fig.add_trace(go.Scatter(x=x, y=live_price, mode="lines+markers",
                                           line=dict(color="white", width=2), name=f"{selected_match} (live)"))
            price_fig.update_layout(title="Price % — Live vs Historical Fingerprint",
                                    xaxis_title="Days before move", yaxis_title="% from window start", height=400)
            st.plotly_chart(price_fig, use_container_width=True)

            fp_vol   = detail["fp_series"].get("volume_ratio", [])
            live_vol = detail["live_series"].get("volume_ratio", [])[-n:]
            if fp_vol and live_vol:
                vol_fig = go.Figure()
                vol_fig.add_trace(go.Scatter(x=x, y=fp_vol, mode="lines",
                                             line=dict(color="orange", dash="dash", width=2),
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
A **gap** occurs when a stock's pre-market price is significantly different from yesterday's closing price.
Gaps happen overnight because news, earnings, or macro events move the price when the market is closed.

**Why gaps matter:**
- Large gaps often signal a significant catalyst (earnings beat, analyst upgrade, news event)
- Gap-up stocks frequently continue moving in the direction of the gap on high volume (continuation)
- Sometimes gaps get "filled" — the stock trades back down to the prior close before resuming (reversal)
- Knowing about a gap before the open lets you plan your entry instead of reacting at 9:31am

**Gap tiers:**
| Tier | Size | Typical cause |
|---|---|---|
| 🔴 Massive | ≥ 8% | Earnings surprise, M&A announcement, FDA approval/rejection |
| 🟠 Large | 4–8% | Analyst upgrade/downgrade, sector rotation, macro event |
| 🟡 Moderate | 2–4% | General pre-market sentiment, minor news |

**How to use:**
- Run this at 7–9am ET before the market opens
- Focus on Large and Massive gaps — they have the most follow-through
- Cross-reference with the Scanner tab to see if technical signals support the move
- Data is ~15min delayed on Yahoo Finance (free). Use Alpaca or Polygon for real-time.
        """)

    g_col1, g_col2 = st.columns(2)
    min_gap = g_col1.slider(
        "Min gap %", 1.0, 15.0, 2.0, step=0.5, key="min_gap",
        help=(
            "Only show stocks that have gapped at least this % from the prior close.\n\n"
            "• **1–2%** — catches all notable pre-market movement. Lots of results.\n"
            "• **4% (default for alerts)** — meaningful gaps with real catalysts.\n"
            "• **8%+** — only major events. Earnings, M&A, major news."
        ),
    )
    g_col2.markdown("""
**Gap tiers:**
- 🔴 **Massive** ≥ 8% — earnings / M&A / major news
- 🟠 **Large** ≥ 4% — analyst action / sector move
- 🟡 **Moderate** ≥ 2% — notable pre-market activity
    """)

    gaps = pd.DataFrame()
    gap_error = None
    if st.button("Scan Pre-Market Gaps", type="primary", key="btn_gaps"):
        with st.spinner(f"Scanning {len(watchlist)} tickers for pre-market gaps…"):
            try:
                gaps = scan_gaps(watchlist, min_gap_pct=min_gap, provider=provider)
            except ProviderCapabilityError as e:
                gap_error = str(e)
                st.error(gap_error)
    if gap_error is None:
        if gaps.empty:
            st.info(f"No gaps above {min_gap}% found. Market may not be in pre-market session, or no significant gaps today.")
        else:
            tier_colors = {"massive": "🔴", "large": "🟠", "moderate": "🟡", "small": "⚪"}
            gaps["tier_icon"] = gaps["tier"].map(tier_colors)
            gaps["gap_display"] = gaps["gap_pct"].apply(lambda x: f"{x:+.2f}%")
            st.success(f"{len(gaps)} gaps found")
            gap_ups   = gaps[gaps["direction"] == "up"]
            gap_downs = gaps[gaps["direction"] == "down"]
            m1, m2, m3 = st.columns(3)
            m1.metric("Total gaps", len(gaps))
            m2.metric("Gap ups",   len(gap_ups),
                      delta=f"avg {gap_ups['gap_pct'].mean():+.1f}%" if not gap_ups.empty else None)
            m3.metric("Gap downs", len(gap_downs),
                      delta=f"avg {gap_downs['gap_pct'].mean():+.1f}%" if not gap_downs.empty else None,
                      delta_color="inverse")
            st.dataframe(
                gaps[["tier_icon", "ticker", "gap_display", "prev_close", "pre_market", "tier", "note"]].rename(columns={"tier_icon": ""}),
                use_container_width=True,
                column_config={
                    "gap_display":  st.column_config.TextColumn("Gap %"),
                    "prev_close":   st.column_config.NumberColumn("Prev Close", format="$%.2f"),
                    "pre_market":   st.column_config.NumberColumn("Pre-Market", format="$%.2f"),
                    "note":         st.column_config.TextColumn("Context", width="large"),
                },
            )
            gap_fig = px.bar(gaps, x="ticker", y="gap_pct", color="direction",
                             color_discrete_map={"up": "green", "down": "red"},
                             title="Pre-Market Gaps by Ticker", labels={"gap_pct": "Gap %", "ticker": ""})
            gap_fig.add_hline(y=0, line_color="white", line_width=1)
            gap_fig.update_layout(height=350)
            st.plotly_chart(gap_fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — OPTIONS FLOW
# ══════════════════════════════════════════════════════════════════════════════
with tab_options:
    st.subheader("Options Flow — Unusual Activity Scanner")
    st.caption(
        "Detects unusual options volume relative to open interest. "
        "Institutional players frequently telegraph moves through options 1–3 days before price follows."
    )

    with st.expander("How to read options flow", expanded=False):
        st.markdown("""
**Options basics:**
- A **call option** gives the buyer the right to buy a stock at a set price. Buying calls = bullish bet.
- A **put option** gives the buyer the right to sell a stock at a set price. Buying puts = bearish bet.
- **Volume** = number of contracts traded today.
- **Open Interest (OI)** = total number of contracts currently outstanding.

**Why Vol/OI ratio matters:**
If a stock normally has 500 open interest on a call strike and today 3,000 contracts trade (6x),
that's unusual. Someone is making a large, directional bet. Institutions don't accidentally buy
3,000 contracts — they're positioning for a move.

| Vol/OI Ratio | Interpretation |
|---|---|
| > 10x | Extremely unusual — likely a sweep across multiple exchanges |
| 3–10x | Notable — worth investigating |
| 1–3x | Slightly elevated — may be noise |

**Sweeps** (available with Unusual Whales API): a single large market order that "sweeps" multiple
exchanges filling at the ask. This is aggressive — someone wants in immediately at any price.
That urgency is a strong signal.

**Put/Call Ratio:**
- < 0.7 — Heavy call buying relative to puts. Bullish sentiment.
- 0.7–1.2 — Balanced. Neutral.
- > 1.2 — Heavy put buying. Bearish sentiment or hedging.

**Data sources (in priority order):**
1. **Unusual Whales** ($50/mo) — real-time sweep detection, best signal quality
2. **Tradier** (free with account) — real-time chains, no sweep detection
3. **yfinance** (free, default) — delayed chains, volume/OI only. Good enough to spot anomalies.
        """)

    st.caption(f"Selected options source: **{options_source}**")
    if options_source == "auto":
        st.info("auto follows the documented priority: Unusual Whales → Tradier → Yahoo based on configured API keys.")
    elif options_source == "unusual_whales":
        st.info("Using Unusual Whales API — requires UNUSUAL_WHALES_API_KEY.")
    elif options_source == "tradier":
        st.info("Using Tradier API — requires TRADIER_API_KEY.")
    else:
        st.info("Using yfinance (free, delayed) — volume/OI analysis only.")

    o_col1, o_col2 = st.columns(2)
    min_vol_oi = o_col1.slider(
        "Min Vol/OI ratio", 1.0, 20.0, 3.0, step=0.5, key="min_vol_oi",
        help=(
            "Only show options contracts where today's volume exceeds this multiple of open interest.\n\n"
            "• **1–2x** — slightly elevated. Lots of noise.\n"
            "• **3x (default)** — meaningful threshold. Catches most unusual activity.\n"
            "• **10x+** — extremely unusual. Very likely institutional or sweep."
        ),
    )
    o_col2.markdown("""
**Vol/OI guide:**
- **>10x** — extremely unusual, likely a sweep
- **3–10x** — notable, worth watching
- **1–3x** — slightly elevated, may be noise
    """)

    unusual = pd.DataFrame()
    options_error = None
    if st.button("Scan Options Flow", type="primary", key="btn_options"):
        with st.spinner(f"Scanning options chains for {len(watchlist)} tickers…"):
            try:
                unusual = scan_unusual_flow(watchlist, min_vol_oi=min_vol_oi, source=options_source)
            except ProviderCapabilityError as e:
                options_error = str(e)
                st.error(options_error)
    if options_error is None:
        if unusual.empty:
            st.info(f"No unusual options activity found above {min_vol_oi}x Vol/OI ratio (source: {options_source}).")
        else:
            st.success(f"{len(unusual)} unusual contracts found (source: {options_source})")
            st.dataframe(unusual, use_container_width=True)

    st.divider()
    st.subheader("Put/Call Sentiment")
    st.caption("Aggregate call vs. put volume for a single ticker to gauge overall options sentiment.")
    pc_ticker = st.selectbox("Select ticker", watchlist, key="sel_pc")
    if st.button("Get Sentiment", key="btn_pc", help="Fetch the options chain and compute the put/call ratio."):
        with st.spinner(f"Fetching options data for {pc_ticker}…"):
            sentiment = get_put_call_sentiment(pc_ticker, source=options_source)
        if sentiment.get("error"):
            st.error(sentiment["error"])
        else:
            s_col1, s_col2, s_col3, s_col4 = st.columns(4)
            s_col1.metric("Put/Call Ratio", sentiment.get("put_call_ratio", "N/A"),
                          help="Put volume ÷ Call volume. <0.7=bullish, >1.2=bearish.")
            s_col2.metric("Call Volume",    sentiment.get("call_volume", 0))
            s_col3.metric("Put Volume",     sentiment.get("put_volume", 0))
            s_col4.metric("Sentiment",      sentiment.get("sentiment", "unknown").upper())
            ratio  = sentiment.get("put_call_ratio")
            source = sentiment.get("data_source", "unknown")
            if ratio is not None:
                if ratio < 0.7:
                    st.success(f"Bullish — heavy call buying relative to puts (source: {source})")
                elif ratio > 1.2:
                    st.error(f"Bearish — heavy put buying relative to calls (source: {source})")
                else:
                    st.info(f"Neutral — balanced call/put activity (source: {source})")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — ALERTS
# ══════════════════════════════════════════════════════════════════════════════
with tab_alerts:
    st.subheader("Alert Configuration")
    st.caption(
        "Alerts fire automatically when the watcher is running and thresholds are crossed. "
        "Configure channels and thresholds in your .env file."
    )

    st.markdown("### Channel Status")
    ch1, ch2 = st.columns(2)
    with ch1:
        if DISCORD_TOKEN and DISCORD_CHANNEL_ID:
            st.success("Discord: **Connected**")
        else:
            st.error("Discord: **Not configured**")
            st.code("ALERT_DISCORD_TOKEN=your-bot-token\nALERT_DISCORD_CHANNEL_ID=your-channel-id")
            st.caption("Setup: discord.com/developers/applications → New App → Bot → copy Token")
    with ch2:
        if EMAIL_TO:
            st.success(f"Email: **Connected** → {EMAIL_TO}")
        else:
            st.error("Email: **Not configured**")
            st.code("ALERT_EMAIL_TO=you@example.com\nALERT_EMAIL_HOST=smtp.gmail.com\nALERT_EMAIL_USER=...\nALERT_EMAIL_PASS=...")

    st.divider()
    st.markdown("### Current Thresholds")
    st.caption("Edit in your .env file — changes take effect on next watcher restart.")
    t1, t2, t3 = st.columns(3)
    t1.metric("Coil threshold",      str(COIL_ALERT_THRESHOLD),
              help="Minimum coil strength score (0–100) to fire an alert. Lower = more alerts.")
    t2.metric("Pattern threshold",   f"{PATTERN_ALERT_THRESHOLD}%",
              help="Minimum pattern similarity % to fire an alert. Lower = more alerts, more noise.")
    t3.metric("Confluence threshold", str(CONFLUENCE_ALERT_THRESHOLD),
              help="Minimum confluence score (0–100) to fire an alert.")
    st.code("ALERT_COIL_THRESHOLD=60\nALERT_PATTERN_THRESHOLD=75\nALERT_CONFLUENCE_THRESHOLD=70")

    st.divider()
    st.markdown("### Send Test Alert")
    st.caption("Verify your channels are working before relying on them.")
    if st.button("Send Test Alert", key="btn_test_alert"):
        results = send_alert(
            subject="TradeX Test Alert",
            body="This is a test alert from your TradeX dashboard. If you received this, alerts are configured correctly.",
        )
        sent   = [k for k, v in results.items() if v]
        failed = [k for k, v in results.items() if not v]
        if sent:
            st.success(f"Test alert sent via: {', '.join(sent)}")
        if failed:
            st.warning(f"Not sent (not configured): {', '.join(failed)}")

    st.divider()
    st.markdown("### What Triggers Alerts")
    st.markdown("""
| Alert type | When it fires | Color in Discord |
|---|---|---|
| **Coil detected** | Coil strength ≥ threshold after a scan | 🟡 Amber |
| **Pattern match** | Similarity ≥ threshold vs fingerprint | 🔵 Blurple |
| **Confluence** | Cross-timeframe score ≥ threshold | 🟢 Green |
| **Gap up** | Pre-market gap ≥ 4% upward (8am ET) | 🟢 Green |
| **Gap down** | Pre-market gap ≥ 4% downward (8am ET) | 🔴 Red |

Run the watcher to activate automatic alerts:
```bash
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5
```
""")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 8 — SIGNAL JOURNAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_journal:
    st.subheader("Signal Journal — Historical Outcomes")
    st.caption(
        "Every signal the app has fired, with automated outcome tracking. "
        "Outcomes are measured at 1d (intraday), 3d (short), and 5d (long) after the signal fires."
    )

    with st.expander("How to use the Signal Journal", expanded=False):
        st.markdown("""
The Signal Journal is your feedback loop. It answers the only question that actually matters:
**do the signals work?**

Every time you run a scan and a stock scores above your min score threshold, that signal is recorded.
After the outcome window closes (1, 3, or 5 days later depending on timeframe), TradeX automatically
fetches the price and records what happened.

**Key metrics:**
- **Win Rate** — % of signals where the stock moved in the expected direction. Above 50% is positive edge.
- **Avg Win / Avg Loss** — how big the wins and losses are on average.
- **Expectancy** — the most important number. Calculated as: `(win rate × avg win) + (loss rate × avg loss)`. Positive expectancy means the strategy has mathematical edge over time.

**Signal Quality by Score Bucket:**
This chart is how you calibrate. If 80+ signals have a 68% win rate but 40–59 signals have a 43% win rate,
you should raise your min score to 80. Use the data to tune your thresholds — don't guess.

**Outcome windows:**
| Timeframe | Outcome measured at |
|---|---|
| Intraday | 1 trading day after signal |
| Short | 3 trading days after signal |
| Long | 5 trading days after signal |

Outcomes are refreshed automatically at 4:30pm ET when the watcher is running.
        """)

    outcome_provider = resolve_provider(provider)
    col_refresh, col_info = st.columns([1, 4])
    with col_refresh:
        if st.button("Refresh Outcomes Now", key="btn_outcomes",
                     help="Manually trigger outcome fetching for all unresolved signals whose window has closed."):
            with st.spinner("Fetching price outcomes for pending signals…"):
                summary = run_outcome_pass(verbose=False, provider=provider)
            st.success(
                f"Resolved {summary['resolved']} — "
                f"{summary['pending']} pending (window not closed yet) — "
                f"{summary['errors']} errors."
            )
    with col_info:
        st.caption(f"Outcome provider: **{outcome_provider}**  ·  Refreshes automatically at 4:30pm ET when the watcher is running.")

    journal = store.get_signal_journal(timeframe=timeframe if timeframe else None)

    if journal.empty:
        st.info("No outcomes yet. Run the Scanner, wait 1–5 days, then click Refresh Outcomes.")
    else:
        wins   = journal[journal["outcome_pct"] > 0]
        losses = journal[journal["outcome_pct"] <= 0]
        avg_win  = wins["outcome_pct"].mean()   if not wins.empty   else 0
        avg_loss = losses["outcome_pct"].mean() if not losses.empty else 0
        expectancy = (len(wins) / len(journal)) * avg_win + (len(losses) / len(journal)) * avg_loss

        known = journal[
            (journal["signal_provider"].notna()) &
            (journal["outcome_provider"].notna()) &
            (journal["signal_provider"] != "unknown") &
            (journal["outcome_provider"] != "unknown")
        ]
        mismatched = known[known["signal_provider"] != known["outcome_provider"]]
        if not mismatched.empty:
            st.caption(
                f"{len(mismatched)} signals were resolved with a different OHLCV provider than they were scanned with."
            )

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Signals", len(journal))
        m2.metric("Win Rate",      f"{len(wins)/len(journal)*100:.0f}%",
                  help="% of signals where the stock moved up after the signal fired.")
        m3.metric("Avg Win",       f"+{avg_win:.1f}%",
                  help="Average % gain on winning signals.")
        m4.metric("Avg Loss",      f"{avg_loss:.1f}%",
                  help="Average % loss on losing signals.")
        m5.metric("Expectancy",    f"{expectancy:+.2f}%",
                  delta_color="normal" if expectancy >= 0 else "inverse",
                  help="(Win rate × Avg win) + (Loss rate × Avg loss). Positive = mathematical edge.")

        st.dataframe(
            journal,
            use_container_width=True,
            column_config={
                "signal_provider":  st.column_config.TextColumn("Signal Provider"),
                "outcome_provider": st.column_config.TextColumn("Outcome Provider"),
            },
        )

        outcome_fig = px.histogram(journal, x="outcome_pct", nbins=30,
                                   title="Distribution of Outcome Returns",
                                   color_discrete_sequence=["steelblue"])
        outcome_fig.add_vline(x=0, line_color="red", line_dash="dash")
        outcome_fig.update_layout(height=300)
        st.plotly_chart(outcome_fig, use_container_width=True)

        st.divider()
        st.subheader("Signal Quality by Score Bucket")
        st.caption("Use this to calibrate your min score threshold — find the score range that actually produces moves.")
        stats = get_outcome_stats()
        if not stats.empty:
            st.dataframe(stats, use_container_width=True)
            quality_fig = px.bar(
                stats, x="score_bucket", y="avg_return_pct",
                color="win_rate_pct", facet_col="timeframe",
                color_continuous_scale="RdYlGn", range_color=[0, 100],
                title="Avg Return % by Score Bucket and Timeframe",
                labels={"avg_return_pct": "Avg Return %", "score_bucket": "Score Range"},
            )
            quality_fig.update_layout(height=350)
            st.plotly_chart(quality_fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 9 — WEIGHTS
# ══════════════════════════════════════════════════════════════════════════════
with tab_weights:
    st.subheader("Scoring Weights — Tune Signal Contributions")
    st.caption(
        "Adjust how many points each signal component awards when it fires. "
        "Changes apply to every Scanner and Confluence run after Save. Persisted to ~/.tradex/weights.json."
    )

    with st.expander("How weighting works", expanded=False):
        st.markdown("""
Each timeframe scorer is composed of several **components** (volume surge, RSI momentum, MACD crossover, etc.).
When a component condition is met, it contributes its configured points to the total score. The final score
is capped at 100, so the sum of weights *can* exceed 100 — that just makes individual components count for more.

**Tiered signals** (intraday volume + RSI) award full credit for the strong tier and a reduced share for the
weaker tier (50% for elevated volume, 75% for oversold-bounce RSI). The ratios scale with your configured weight.

**Tips:**
- If you trust volume more than indicators, raise volume weights and lower MACD / RSI.
- If you want every clean setup to clear 50, keep the sum of your top 2–3 components ≥ 50.
- Use **Reset to defaults** to get back the original 30/20/30/20-style scoring at any time.
        """)

    current = signal_weights.load()
    section_meta = [
        ("Intraday (5-min bars)", "intraday", current.intraday),
        ("Short-term (daily bars)", "short", current.short),
        ("Long-term (weekly bars)", "long", current.long),
    ]

    new_values: dict[str, dict[str, int]] = {"intraday": {}, "short": {}, "long": {}}

    for title, key, section in section_meta:
        st.markdown(f"### {title}")
        st.caption(f"Max possible score (uncapped sum): **{signal_weights.max_possible(section)}**")
        for field_name in section.__dataclass_fields__:
            meta = signal_weights.COMPONENT_LABELS.get((key, field_name), {"label": field_name, "help": ""})
            new_values[key][field_name] = st.slider(
                meta["label"],
                0, 50, getattr(section, field_name),
                key=f"w_{key}_{field_name}",
                help=meta["help"],
            )
        st.divider()

    col_save, col_reset = st.columns([1, 1])
    if col_save.button("Save weights", type="primary", key="weights_save",
                       help="Persist these weights to ~/.tradex/weights.json. All future scans will use them."):
        updated = signal_weights.Weights(
            intraday=signal_weights.IntradayWeights(**new_values["intraday"]),
            short=signal_weights.ShortWeights(**new_values["short"]),
            long=signal_weights.LongWeights(**new_values["long"]),
        )
        signal_weights.save(updated)
        st.success("Weights saved. Re-run any Scanner or Confluence scan to see the effect.")

    if col_reset.button("Reset to defaults", key="weights_reset",
                        help="Restore original built-in weights (matches the scoring shown in CLAUDE.md and the README)."):
        signal_weights.reset_to_defaults()
        st.success("Weights reset to defaults.")
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 10 — HELP
# ══════════════════════════════════════════════════════════════════════════════
with tab_help:
    st.subheader("TradeX — Help & Documentation")
    st.caption("Everything you need to understand what each feature does, how to tune it, and how to get started.")

    st.markdown("---")

    # ── Quick start ───────────────────────────────────────────────────────────
    st.markdown("## Getting Started")
    st.markdown("""
**Recommended first session:**

1. **Scanner tab** → Run Scan. See which stocks are signaling right now.
2. **Confluence tab** → Run Confluence Scan. Find stocks where multiple timeframes agree.
3. **Pattern Match tab** → Build Fingerprints (standard profile, ~2 min) → Run Pattern Screen.
4. **Start the watcher** in a terminal so signal history starts building:
   ```bash
   cd /Users/gary.yang/tradex
   .venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5
   ```
5. After a few days → **Coil Detector** becomes useful as history accumulates.
6. After signals resolve → **Signal Journal** shows your win rate and lets you calibrate.
    """)

    st.markdown("---")

    # ── Global settings ───────────────────────────────────────────────────────
    st.markdown("## Global Settings (Sidebar)")

    with st.expander("Timeframe", expanded=False):
        st.markdown("""
Controls which time window the Scanner and Coil Detector use.

| Option | Bars | Window | Best for |
|---|---|---|---|
| **Intraday** | 5-minute | Last 5 trading days | Same-day swings, momentum plays |
| **Short** | Daily | Last 60 trading days | Multi-day to multi-week swing trades |
| **Long** | Weekly | Last 2 years | Position trades, trend following |

**Tuning:** Start with `intraday` for active trading. Switch to `short` for swing trades
you plan to hold 3–10 days. Use `long` to filter out stocks that are in long-term downtrends.
        """)

    with st.expander("Min Score (0–100)", expanded=False):
        st.markdown("""
Filters out stocks below this signal strength. Each stock is scored by how many technical
conditions are simultaneously met — more conditions = higher score.

| Range | Meaning | Use when |
|---|---|---|
| 0–39 | No clear setup | Research / exploration only |
| 40–59 | Weak to moderate signal | Casting a wide net |
| 60–79 | Strong signal | Good default for active scanning |
| 80–100 | Multiple conditions aligned | Highest conviction — fewer but better setups |

**Tuning:** Start at 40. After you've built Signal Journal history, look at the
"Signal Quality by Score Bucket" chart to see what threshold actually produces moves for you.
Lower = more noise. Higher = fewer opportunities but higher win rate.
        """)

    with st.expander("Watchlist", expanded=False):
        st.markdown("""
The default watchlist covers 20 actively traded stocks and ETFs across mega-cap tech,
high-growth names, and leveraged ETFs.

**Default tickers:** AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL, AMD, PLTR, MSTR,
SPY, QQQ, SOXL, TQQQ, SMCI, ARM, AVGO, MU, CRWD, NET

**Adding tickers:** Type comma-separated symbols in the "Add tickers" box (e.g. `COIN, HOOD, RKLB`).
They'll be appended to the watchlist for this session.

**Tip:** Fewer tickers = faster scans. If you're running the intraday scanner every 5 minutes,
keep the watchlist under 30 to avoid rate limiting from Yahoo Finance.
        """)

    st.markdown("---")

    # ── Scanner ───────────────────────────────────────────────────────────────
    st.markdown("## Scanner")

    with st.expander("What the Scanner does", expanded=False):
        st.markdown("""
The Scanner fetches live price data for every ticker in your watchlist and scores each one
0–100 based on how many technical conditions are met simultaneously.

**Signals checked per timeframe:**

| Signal | What it detects | Weight |
|---|---|---|
| **Volume surge** | Current volume > 2x the 20-bar average. Indicates unusual interest — often institutional. | Up to 30 pts |
| **RSI momentum** | RSI between 55–75 (bullish momentum without being overbought). | Up to 20 pts |
| **MACD crossover** | MACD line crossing above signal line. Trend direction shifting bullish. | Up to 30 pts |
| **EMA structure** | Price above EMA20, which is above EMA50. Classic uptrend structure. | Up to 25 pts |
| **BB expansion** | Bollinger Bands tightening then expanding. Volatility building for a breakout. | Up to 20 pts |
| **EMA pullback** | Price dipping back to EMA20 in an uptrend. Potential buy-the-dip entry. | Up to 15 pts |

**Results columns:**
- **Score** — 0–100 signal strength
- **Vol Ratio** — how unusual today's volume is vs. the 20-bar average (2.0 = twice normal)
- **RSI** — momentum indicator. 30=oversold, 50=neutral, 70=overbought
- **Reasons** — plain-English explanation of exactly why this stock scored what it did

**Chart indicators:**
- 🟠 **EMA20** — 20-period exponential moving average. Short-term trend.
- 🔵 **EMA50** — 50-period EMA. Medium-term trend.
- **Shaded band** — Bollinger Bands (±2 std dev). Wide = high volatility, narrow = compression.
- **Volume bars** — green when close > open, red when close < open. White line = 20-bar average.
        """)

    st.markdown("---")

    # ── Coil Detector ─────────────────────────────────────────────────────────
    st.markdown("## Coil Detector")

    with st.expander("What a coil is and how to use it", expanded=False):
        st.markdown("""
A **coil** is a stock that has been quietly building technical pressure across multiple scan
sessions without yet making a large price move. The idea is to identify stocks *before* the
obvious move — not after.

**How it's detected:**
1. Every scan result is saved to a local database
2. The Coil Detector looks back over N days and finds stocks that appeared in multiple sessions
3. It checks: is the score still high? Has the price not already broken out (>3% move)?
4. If yes — it's a coil candidate. The longer and stronger the coil, the higher the Coil Strength.

**Controls:**

| Control | What it does |
|---|---|
| **Look-back window** | How many days of history to search. 7 days = one trading week. |
| **Min appearances** | How many scan sessions the stock must have appeared in. More = longer coil. |

**Tuning look-back:**
- **3–5 days** — only catches recent, fast-building setups
- **7 days (default)** — one week, best balance
- **14–21 days** — longer accumulation patterns, more reliable but slower to develop

**Tuning min appearances:**
- **2 (default)** — appeared at least twice. Catches early coils.
- **3–5** — appeared repeatedly. More reliable.
- **6–10** — very persistent. Usually means the stock is about to resolve soon.

**Score History chart:** shows how the signal score evolved across scan sessions.
A rising score line = the setup is getting stronger. A flat line = holding steady.
A falling line = watch out, the setup may be fading.

**Status labels:**
- 🟢 **Coiling — building pressure** — score rising, no breakout yet. Best setups.
- 🟡 **Coiling — stable** — holding at signal level, not accelerating yet.
- 🔴 **Fading** — score declining. Setup may be breaking down.
- ⚪ **Watching** — appeared but hasn't met full coil criteria yet.
        """)

    st.markdown("---")

    # ── Confluence ────────────────────────────────────────────────────────────
    st.markdown("## Confluence Scanner")

    with st.expander("Multi-timeframe alignment explained", expanded=False):
        st.markdown("""
The Confluence Scanner scores each stock across all three timeframes simultaneously and
combines them into a single weighted score.

**Why it matters:** A stock can look great on a 5-minute chart but be in a daily downtrend.
Trading against the larger trend is fighting an uphill battle. When intraday, short-term, and
long-term all point the same direction — that's a genuinely high-conviction setup.

**Weighting:**
| Timeframe | Weight | Reasoning |
|---|---|---|
| Intraday (5m) | 30% | Noisiest signal — good confirmation, not the driver |
| Short (1d) | 40% | Most actionable for swing trades |
| Long (1wk) | 30% | Establishes macro trend direction |

**Confluence score tiers:**
| Score | Tier | Meaning |
|---|---|---|
| 90–100 | All timeframes aligned | Rare. Very high conviction. |
| 70–89 | Strong confluence | Two or more timeframes strongly aligned. |
| 50–69 | Moderate confluence | Partial alignment. Use additional confirmation. |
| < 50 | Weak | Single timeframe only. Lower conviction. |

**Min confluence slider:** raise it to see only the strongest setups. Lower it if nothing
appears (may be a weak market environment where setups are rarer).

**Bar chart (drill-down):** shows the individual score per timeframe so you can see exactly
which timeframes are contributing to the confluence score.
        """)

    st.markdown("---")

    # ── Pattern Match ─────────────────────────────────────────────────────────
    st.markdown("## Pattern Match")

    with st.expander("Fingerprinting and similarity scoring explained", expanded=False):
        st.markdown("""
Pattern Match mines 3 years of historical data to find what stocks looked like in the days
*before* a major move — then compares your current watchlist against that historical shape.

**Step 1 — Build Fingerprints (one-time setup, ~2 min):**
- Scans 40+ stocks over 3 years
- Finds every event where a stock moved ≥15% in 5 days (run-up) or ≥12% down (decline)
- Extracts the 10 trading days *before* each event
- Normalizes everything (so NVDA at $800 and AMD at $100 are comparable — uses % changes and ratios)
- Averages all pre-event windows into a "fingerprint" with a mean and ±1 std deviation band
- Saves to a local database — doesn't recompute unless you click Build again

**Step 2 — Run Pattern Screen:**
- Extracts the last 10 trading days for each stock in your watchlist
- Compares it to the fingerprint using Pearson correlation across 5 series
- Returns a similarity score 0–100

**Series weights:**
| Series | Weight |
|---|---|
| Price % change shape | 35% |
| Volume ratio shape | 30% |
| RSI trajectory | 15% |
| MACD diff trajectory | 10% |
| Bollinger Band width | 10% |

**Profiles:**
| Profile | Run-up threshold | Best for |
|---|---|---|
| Conservative | +20% / -16% | AAPL, MSFT, GOOGL, SPY |
| Standard | +15% / -12% | Most mid/large cap stocks |
| Volatile | +30% / -25% | SOXL, TQQQ, MSTR, NVDA, TSLA |

**Similarity score guide:**
| Score | Meaning |
|---|---|
| 90–100% | Near-perfect match — very strong setup |
| 75–89% | Strong match — alert threshold |
| 60–74% | Moderate — watch but don't act alone |
| < 60% | Low similarity / noise |

**Overlay chart:** white line = your stock now. Orange dashed = historical average.
Shaded band = the range most historical events fell within (±1 std dev).
The closer your stock tracks the orange line, the higher the similarity.
        """)

    st.markdown("---")

    # ── Pre-Market ────────────────────────────────────────────────────────────
    st.markdown("## Pre-Market Gap Scanner")

    with st.expander("Gaps explained", expanded=False):
        st.markdown("""
A gap occurs when a stock's pre-market price is significantly different from the previous
regular-session closing price. Gaps happen because news, earnings, or macro events move
the price while the market is closed.

**Best time to use:** 7:00am – 9:25am ET, before market open.

**Min gap % slider:**
- **1–2%** — catches all notable pre-market moves. Many results, some noise.
- **4%** — meaningful gaps with real catalysts. Used for automatic alerts.
- **8%+** — major events only (earnings, M&A).

**Gap tiers:**
| Tier | Size | Typical cause |
|---|---|---|
| 🔴 Massive | ≥ 8% | Earnings surprise, M&A, FDA event |
| 🟠 Large | 4–8% | Analyst action, sector news |
| 🟡 Moderate | 2–4% | General pre-market sentiment |

**How to trade gaps:**
- **Continuation** — stock gaps up on volume and keeps going. Common after strong earnings.
- **Gap fill** — stock gaps up then reverses back to the prior close before resuming. Watch for this.
- **Cross-check with Scanner** — a gap-up stock that also has high technical signal score is stronger.

**Data source:** Yahoo Finance (free, ~15min delayed). Add Alpaca or Polygon for real-time.
        """)

    st.markdown("---")

    # ── Options Flow ──────────────────────────────────────────────────────────
    st.markdown("## Options Flow")

    with st.expander("Options basics and how to read flow", expanded=False):
        st.markdown("""
Options give traders the right (but not obligation) to buy or sell a stock at a set price
by a set date. They're often used by institutions to make large directional bets.

**Key terms:**
- **Call** — right to buy. Buying calls = bullish bet.
- **Put** — right to sell. Buying puts = bearish bet or hedge.
- **Strike** — the price at which the option can be exercised.
- **Expiry** — the date the option expires.
- **Volume** — contracts traded today.
- **Open Interest (OI)** — total contracts currently outstanding.
- **Vol/OI ratio** — today's volume ÷ existing open interest. High ratio = unusual activity.

**Min Vol/OI ratio slider:**
- **1–2x** — slightly elevated, lots of noise
- **3x (default)** — meaningful. Catches most unusual activity.
- **10x+** — extremely unusual. Very likely institutional or a sweep.

**Put/Call Ratio:**
- **< 0.7** — heavy call buying relative to puts → bullish
- **0.7–1.2** — balanced → neutral
- **> 1.2** — heavy put buying → bearish or hedging

**Data sources:**
- **Unusual Whales** ($50/mo) — real-time, sweep detection, best signal quality. Set `UNUSUAL_WHALES_API_KEY` in .env.
- **Tradier** (free with brokerage account) — real-time chains. Set `TRADIER_API_KEY` in .env.
- **yfinance** (default, free) — delayed chains, volume/OI ratio analysis only.
        """)

    st.markdown("---")

    # ── Alerts ────────────────────────────────────────────────────────────────
    st.markdown("## Alerts")

    with st.expander("Setting up Discord and email alerts", expanded=False):
        st.markdown("""
Alerts fire automatically when the background watcher detects a threshold crossing.

**Discord bot setup (one-time):**
1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → give it a name (e.g. "TradeX")
3. Go to **Bot** tab → **Add Bot** → copy the **Token**
4. Go to **OAuth2** → **URL Generator** → check `bot` scope → check `Send Messages` + `Embed Links` permissions
5. Open the generated URL → invite the bot to your Discord server
6. Right-click the channel you want alerts in → **Copy Channel ID** (requires Developer Mode: Settings → Advanced → Developer Mode)
7. Add to `.env`:
   ```
   ALERT_DISCORD_TOKEN=your-token-here
   ALERT_DISCORD_CHANNEL_ID=your-channel-id-here
   ```

**Email setup:**
For Gmail, use an [App Password](https://myaccount.google.com/apppasswords) — not your regular password.
```
ALERT_EMAIL_TO=you@example.com
ALERT_EMAIL_FROM=your-gmail@gmail.com
ALERT_EMAIL_HOST=smtp.gmail.com
ALERT_EMAIL_PORT=587
ALERT_EMAIL_USER=your-gmail@gmail.com
ALERT_EMAIL_PASS=your-app-password
```

**Threshold tuning:**
| Setting | Default | Effect of lowering | Effect of raising |
|---|---|---|---|
| `ALERT_COIL_THRESHOLD` | 60 | More coil alerts, more noise | Fewer but stronger coil alerts |
| `ALERT_PATTERN_THRESHOLD` | 75% | More pattern alerts | Only near-perfect pattern matches |
| `ALERT_CONFLUENCE_THRESHOLD` | 70 | More confluence alerts | Only strong multi-timeframe setups |
        """)

    st.markdown("---")

    # ── Signal Journal ────────────────────────────────────────────────────────
    st.markdown("## Signal Journal")

    with st.expander("Understanding your signal history and outcomes", expanded=False):
        st.markdown("""
The Signal Journal automatically tracks what happened after every signal fired.

**How outcomes are measured:**
| Timeframe | Outcome window |
|---|---|
| Intraday | Price 1 trading day after signal |
| Short | Price 3 trading days after signal |
| Long | Price 5 trading days after signal |

**Key metrics:**
- **Win Rate** — % of signals where the stock moved up. >50% = positive directional bias.
- **Avg Win** — average % gain on winning signals.
- **Avg Loss** — average % loss on losing signals.
- **Expectancy** — `(win rate × avg win) + (loss rate × avg loss)`. The single most important number.
  Positive expectancy means the strategy has mathematical edge over time, even if individual trades lose.

**Signal Quality by Score Bucket:**
Shows win rate and avg return broken down by score range (40–59, 60–79, 80–100).
Use this to find your optimal min score threshold:
- If 80+ signals have 65% win rate but 40–59 signals have 44%, raise your min score to 80.
- Don't guess at thresholds — let the data tell you.

**Refresh Outcomes:** manually triggers the outcome fetcher. Also runs automatically
at 4:30pm ET when the watcher is running.
        """)

    st.markdown("---")

    # ── Indicators glossary ───────────────────────────────────────────────────
    st.markdown("## Indicator Glossary")

    with st.expander("RSI — Relative Strength Index", expanded=False):
        st.markdown("""
Measures momentum by comparing the magnitude of recent gains vs. recent losses over 14 periods.

| Value | Interpretation |
|---|---|
| < 30 | Oversold — potential bounce setup |
| 30–50 | Weak / recovering |
| 50–70 | Momentum zone — trending stock |
| > 70 | Overbought — potential reversal risk |

TradeX uses RSI 55–75 as the bullish momentum zone. Above 75 = overextended, below 55 = not enough momentum.
        """)

    with st.expander("MACD — Moving Average Convergence Divergence", expanded=False):
        st.markdown("""
Compares two exponential moving averages (12-period and 26-period) to detect trend direction and shifts.

**Key signals:**
- **MACD line crosses above signal line** → bullish crossover. TradeX awards points for this.
- **MACD positive and expanding** → established uptrend with momentum.
- **MACD negative and falling** → downtrend in progress.

**MACD diff** (histogram) = MACD minus signal line. Positive and growing = accelerating uptrend.
        """)

    with st.expander("EMA — Exponential Moving Average", expanded=False):
        st.markdown("""
A moving average that gives more weight to recent prices, making it more responsive than a simple average.

TradeX uses two EMAs:
- **EMA20** (orange) — short-term trend. If price is above this, the short-term trend is up.
- **EMA50** (blue) — medium-term trend. The "bigger" trend.

**Key patterns:**
- **Price > EMA20 > EMA50** → classic uptrend structure. TradeX awards points for this.
- **Pullback to EMA20 in uptrend** → price dips back to the 20 but holds. Entry opportunity.
- **EMA20 crosses below EMA50** → "death cross" — bearish trend change.
        """)

    with st.expander("Bollinger Bands", expanded=False):
        st.markdown("""
Bands placed ±2 standard deviations around a 20-period moving average. They expand and contract
with volatility.

**Key patterns:**
- **Narrow bands (squeeze)** — volatility is low. The stock is coiling. A big move is often coming.
- **Band expansion after squeeze** — volatility returning. Breakout underway. TradeX detects this.
- **Price at upper band** — either strong momentum or overextended.
- **Price at lower band** — either bearish or oversold bounce setup.

TradeX uses **BB Width** (band width as % of the middle band) to detect squeezes and expansions.
        """)

    with st.expander("Volume Ratio", expanded=False):
        st.markdown("""
Volume ratio = today's volume ÷ the 20-period average volume.

| Ratio | Interpretation |
|---|---|
| < 0.5 | Very light volume — low conviction in price movement |
| 0.5–1.0 | Below average — quiet day |
| 1.0–1.5 | Normal |
| 1.5–2.0 | Elevated — increased interest |
| 2.0–3.0 | High volume — likely institutional activity |
| > 3.0 | Unusually high — major event, earnings, or news |

High volume on an up day = institutional buying. High volume on a down day = institutional selling.
Volume confirms price moves — a breakout on low volume is suspect. On high volume, it's real.
        """)

    with st.expander("ATR — Average True Range", expanded=False):
        st.markdown("""
Measures average daily volatility in price terms over 14 periods. Unlike % moves, ATR is in dollars.

**How TradeX uses it:**
- Used internally in the pattern fingerprinter to normalize volatility across different stocks.
- Not displayed directly in the scanner results.

**Practical use:** A stock with ATR of $5 moves $5/day on average. If you're setting a stop loss,
placing it 1–2 ATR below your entry gives the stock room to breathe without triggering prematurely.
        """)

    st.markdown("---")
    st.markdown("## Running the Background Watcher")
    st.code("""# Run in a terminal during market hours (9:30am–4pm ET)
cd /Users/gary.yang/tradex
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5

# Options:
# --timeframe   intraday | short | long
# --interval    poll interval in minutes (0 = run once and exit)
# --min-score   minimum score to record (default: 35)
# --provider    yahoo | alpaca | ibkr | schwab (default: yahoo)""", language="bash")

    st.markdown("""
The watcher:
- Runs the Scanner every N minutes
- Saves results to `~/.tradex/signals.db` (builds Coil Detector history)
- Checks alert thresholds and fires Discord/email alerts on every scan cycle
- Runs a gap scan automatically at 8am ET
- Runs the outcome pass automatically at 4:30pm ET
    """)
