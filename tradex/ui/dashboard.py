"""
Streamlit dashboard — five tabs:
  1. Scanner       : run screener, view ranked results, drill-down chart
  2. Coil Detector : stocks building pressure over multiple days (pre-signal)
  3. Confluence    : stocks scoring well across multiple timeframes
  4. Pattern Match : compare live stocks against historical run-up/decline fingerprints
  5. Signal Journal: historical signal outcomes (did the move happen?)

Run with: streamlit run tradex/ui/dashboard.py
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from tradex.screener.engine import run
from tradex.data.fetcher import fetch
from tradex.signals.indicators import add_indicators
from tradex.tracker import store, analyzer
from tradex.tracker.confluence import run_confluence_screen
from tradex.tracker.outcome_tracker import run_outcome_pass, get_outcome_stats
from tradex.patterns.fingerprint import run_full_build, list_fingerprints, load_fingerprint
from tradex.patterns.matcher import run_match_screen, match_ticker
from tradex.patterns.config import PROFILES

store.init()

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
    "AMD", "PLTR", "MSTR", "SPY", "QQQ", "SOXL", "TQQQ",
    "SMCI", "ARM",  "AVGO", "MU",   "CRWD", "NET",
]

st.set_page_config(page_title="TradeX", layout="wide")
st.title("TradeX — Market Opportunity Scanner")

# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    timeframe = st.selectbox("Timeframe", ["intraday", "short", "long"])
    min_score = st.slider("Min score", 0, 100, 40)
    custom = st.text_input("Add tickers (comma-separated)", "")
    extra = [t.strip().upper() for t in custom.split(",") if t.strip()]
    watchlist = list(dict.fromkeys(DEFAULT_TICKERS + extra))
    st.caption(f"{len(watchlist)} tickers in watchlist")

tab_scanner, tab_coil, tab_confluence, tab_pattern, tab_journal = st.tabs([
    "Scanner", "Coil Detector", "Confluence", "Pattern Match", "Signal Journal"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SCANNER
# ══════════════════════════════════════════════════════════════════════════════
with tab_scanner:
    run_scan = st.button("Run Scan", type="primary", key="btn_scan")

    if run_scan:
        with st.spinner(f"Scanning {len(watchlist)} tickers on {timeframe}…"):
            results = run(watchlist, timeframe=timeframe, min_score=min_score)

        if results.empty:
            st.warning("No opportunities found. Lower the min score or add more tickers.")
        else:
            st.success(f"Found {len(results)} opportunities")
            store.record_signals(results, timeframe)
            st.dataframe(results, use_container_width=True)
            st.session_state["scan_results"] = results
            st.session_state["scan_timeframe"] = timeframe

    if "scan_results" in st.session_state and not st.session_state["scan_results"].empty:
        st.divider()
        st.subheader("Drill-down Chart")
        tickers_with_signals = st.session_state["scan_results"]["ticker"].tolist()
        selected = st.selectbox("Select ticker", tickers_with_signals, key="sel_scanner")
        tf = st.session_state["scan_timeframe"]

        df = fetch(selected, tf)
        df = add_indicators(df)

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="Price"
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
    st.subheader("Coil Detector — Setups Building Pressure")
    st.caption(
        "Stocks that have appeared repeatedly in scans without breaking out yet. "
        "These are pre-signal candidates — the move hasn't happened but the setup is building."
    )

    col1, col2 = st.columns(2)
    coil_days       = col1.slider("Look-back window (days)", 3, 21, 7, key="coil_days")
    min_appearances = col2.slider("Min appearances", 2, 10, 2, key="coil_apps")

    if st.button("Detect Coils", key="btn_coil"):
        coils = analyzer.detect_coils(timeframe, days=coil_days, min_appearances=min_appearances)

        if coils.empty:
            st.info("No coiling setups found. Run the Scanner a few times over multiple days to build history.")
        else:
            st.success(f"{len(coils)} coiling setups detected")

            display = coils[[
                "ticker", "coil_strength", "appearances", "latest_score",
                "score_trend", "trend_direction", "days_building" if "days_building" in coils.columns else "first_seen",
                "last_close"
            ]].copy() if "days_building" not in coils.columns else coils[[
                "ticker", "coil_strength", "appearances", "latest_score",
                "score_trend", "trend_direction", "last_close",
            ]]
            st.dataframe(display, use_container_width=True)

            # Score history sparklines
            st.divider()
            st.subheader("Score History")
            selected_coil = st.selectbox(
                "Select ticker to inspect", coils["ticker"].tolist(), key="sel_coil"
            )
            state = analyzer.get_ticker_state(selected_coil, timeframe, days=coil_days)

            if state["score_history"]:
                score_fig = px.line(
                    y=state["score_history"],
                    labels={"x": "Scan #", "y": "Score"},
                    title=f"{selected_coil} — Score History ({timeframe})",
                    markers=True,
                )
                score_fig.add_hline(y=50, line_dash="dot", line_color="yellow",
                                    annotation_text="Signal threshold")
                score_fig.update_layout(height=300)
                st.plotly_chart(score_fig, use_container_width=True)

            st.info(f"**{state['status'].upper()}** — {state['summary']}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CONFLUENCE
# ══════════════════════════════════════════════════════════════════════════════
with tab_confluence:
    st.subheader("Confluence Scanner — Multi-Timeframe Alignment")
    st.caption(
        "Stocks scoring well across intraday, short-term, AND long-term simultaneously. "
        "Higher conviction setups — all timeframes telling the same story."
    )

    min_confluence = st.slider("Min confluence score", 0, 100, 50, key="min_conf")

    if st.button("Run Confluence Scan", key="btn_conf"):
        with st.spinner(f"Scoring {len(watchlist)} tickers across all timeframes…"):
            conf_results = run_confluence_screen(watchlist, min_confluence=min_confluence)

        if conf_results.empty:
            st.warning("No confluence setups found. Lower the min confluence score.")
        else:
            st.success(f"{len(conf_results)} multi-timeframe setups found")
            st.dataframe(conf_results, use_container_width=True)
            st.session_state["conf_results"] = conf_results

    if "conf_results" in st.session_state and not st.session_state["conf_results"].empty:
        st.divider()
        selected_conf = st.selectbox(
            "Drill down", st.session_state["conf_results"]["ticker"].tolist(), key="sel_conf"
        )

        # Show per-timeframe score breakdown as a bar chart
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

    # ── Step 1: Build / refresh fingerprints ─────────────────────────────────
    with st.expander("Step 1 — Build Fingerprints (run once, takes ~2 min)", expanded=False):
        st.markdown(
            "Mines 3 years of history across 40+ stocks, finds all major run-ups and declines, "
            "and averages the 10-day pre-event windows into fingerprints. "
            "Results are cached — you only need to re-run if you want to refresh."
        )
        fp_col1, fp_col2, fp_col3 = st.columns(3)
        fp_profile   = fp_col1.selectbox("Profile", list(PROFILES.keys()), index=1, key="fp_profile")
        fp_etype     = fp_col2.selectbox("Event type", ["both", "runup", "decline"], key="fp_etype")

        cfg = PROFILES[fp_profile]
        fp_col3.metric("Move threshold", f"+{cfg.runup_pct}% / -{cfg.decline_pct}%")

        if st.button("Build Fingerprints", key="btn_build_fp"):
            with st.spinner("Mining historical events and building fingerprints… (this takes ~2 minutes)"):
                built = run_full_build(profile=fp_profile, event_type=fp_etype, verbose=False)
            if built:
                st.success(f"Built fingerprints: {', '.join(built.keys())}")
            else:
                st.error("Build failed — check that there are enough historical events.")

        existing = list_fingerprints()
        if not existing.empty:
            st.markdown("**Stored fingerprints:**")
            st.dataframe(existing, use_container_width=True)

    st.divider()

    # ── Step 2: Run match screen ──────────────────────────────────────────────
    st.markdown("**Step 2 — Match Live Stocks Against Fingerprints**")

    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    match_profile   = m_col1.selectbox("Profile", list(PROFILES.keys()), index=1, key="match_profile")
    match_etype     = m_col2.selectbox("Pattern type", ["runup", "decline"], key="match_etype")
    match_threshold = m_col3.slider("Min similarity", 0, 100, int(PROFILES[match_profile].alert_threshold), key="match_thresh")

    if st.button("Run Pattern Screen", key="btn_match", type="primary"):
        fp_check = load_fingerprint(match_etype, match_profile)
        if fp_check is None:
            st.error(
                f"No '{match_etype}' fingerprint found for profile '{match_profile}'. "
                "Build it first using Step 1 above."
            )
        else:
            with st.spinner(f"Matching {len(watchlist)} tickers against {match_etype} fingerprint…"):
                match_results = run_match_screen(
                    watchlist,
                    event_type=match_etype,
                    profile=match_profile,
                    min_similarity=match_threshold,
                )
            if match_results.empty:
                st.warning(f"No tickers matched above {match_threshold}% similarity. Lower the threshold or build fingerprints first.")
            else:
                st.success(f"{len(match_results)} pattern matches found")
                st.dataframe(match_results, use_container_width=True)
                st.session_state["match_results"] = match_results
                st.session_state["match_etype"]   = match_etype
                st.session_state["match_profile"]  = match_profile

    # ── Step 3: Drill-down — live vs fingerprint overlay ─────────────────────
    if "match_results" in st.session_state and not st.session_state["match_results"].empty:
        st.divider()
        st.subheader("Pattern Overlay — Live vs Fingerprint")
        st.caption("Solid line = your stock's last 10 days. Shaded band = historical fingerprint mean ± 1 std.")

        selected_match = st.selectbox(
            "Select ticker", st.session_state["match_results"]["ticker"].tolist(), key="sel_match"
        )
        detail = match_ticker(
            selected_match,
            event_type=st.session_state["match_etype"],
            profile=st.session_state["match_profile"],
        )

        if "error" not in detail:
            # Score summary
            s = detail["series_scores"]
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("Overall Similarity", f"{detail['similarity_score']}%")
            sc2.metric("Price shape",  f"{s.get('price_pct', 0):.0f}%")
            sc3.metric("Volume shape", f"{s.get('volume_ratio', 0):.0f}%")
            sc4.metric("RSI shape",    f"{s.get('rsi', 0):.0f}%")
            st.info(f"**{detail['match_tier'].upper()}** — {detail['interpretation']}")

            # Price % chart: live vs fingerprint
            n = len(detail["fp_series"].get("price_pct", []))
            x = list(range(-n + 1, 1))   # day -9 … day 0

            fp_mean  = detail["fp_series"].get("price_pct", [])
            fp_upper = load_fingerprint(
                st.session_state["match_etype"], st.session_state["match_profile"]
            )["series"].get("price_pct", {}).get("upper", fp_mean)
            fp_lower = load_fingerprint(
                st.session_state["match_etype"], st.session_state["match_profile"]
            )["series"].get("price_pct", {}).get("lower", fp_mean)
            live_price = detail["live_series"].get("price_pct", [])[-n:]

            price_fig = go.Figure()
            price_fig.add_trace(go.Scatter(
                x=x, y=fp_upper, mode="lines", line=dict(width=0),
                name="FP upper", showlegend=False,
            ))
            price_fig.add_trace(go.Scatter(
                x=x, y=fp_lower, mode="lines", line=dict(width=0),
                fill="tonexty", fillcolor="rgba(255,165,0,0.15)",
                name="Historical range ±1σ",
            ))
            price_fig.add_trace(go.Scatter(
                x=x, y=fp_mean, mode="lines",
                line=dict(color="orange", dash="dash", width=2),
                name="Historical avg",
            ))
            price_fig.add_trace(go.Scatter(
                x=x, y=live_price, mode="lines+markers",
                line=dict(color="white", width=2),
                name=f"{selected_match} (live)",
            ))
            price_fig.update_layout(
                title="Price % Change — Live vs Historical Fingerprint",
                xaxis_title="Days before move",
                yaxis_title="% return from window start",
                height=400,
            )
            st.plotly_chart(price_fig, use_container_width=True)

            # Volume ratio chart
            fp_vol  = detail["fp_series"].get("volume_ratio", [])
            live_vol = detail["live_series"].get("volume_ratio", [])[-n:]
            if fp_vol and live_vol:
                vol_fig = go.Figure()
                vol_fig.add_trace(go.Scatter(
                    x=x, y=fp_vol, mode="lines",
                    line=dict(color="orange", dash="dash", width=2),
                    name="Historical avg volume ratio",
                ))
                vol_fig.add_trace(go.Bar(
                    x=x, y=live_vol,
                    name=f"{selected_match} volume ratio",
                    marker_color="steelblue", opacity=0.7,
                ))
                vol_fig.update_layout(
                    title="Volume Ratio — Live vs Historical Fingerprint",
                    xaxis_title="Days before move",
                    yaxis_title="Volume / window average",
                    height=300,
                )
                st.plotly_chart(vol_fig, use_container_width=True)
        else:
            st.error(detail["error"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — SIGNAL JOURNAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_journal:
    st.subheader("Signal Journal — Historical Outcomes")
    st.caption(
        "Every signal the app has fired, with automated outcome tracking. "
        "Outcomes are measured at 1d (intraday), 3d (short), and 5d (long) after the signal."
    )

    col_refresh, col_info = st.columns([1, 4])
    with col_refresh:
        if st.button("Refresh Outcomes Now", key="btn_outcomes"):
            with st.spinner("Fetching price outcomes for pending signals…"):
                summary = run_outcome_pass(verbose=False)
            st.success(
                f"Resolved {summary['resolved']} outcomes — "
                f"{summary['pending']} still pending (window not closed yet), "
                f"{summary['errors']} errors."
            )
    with col_info:
        st.caption(
            "Outcomes are also refreshed automatically every day at 4:30pm ET "
            "when the watcher is running (`python -m tradex.tracker.watcher --interval 5`)."
        )

    journal = store.get_signal_journal(timeframe=timeframe if timeframe else None)

    if journal.empty:
        st.info(
            "No outcomes yet. Run the Scanner a few times, wait for the outcome window to close "
            "(1–5 days depending on timeframe), then click Refresh Outcomes."
        )
    else:
        wins   = journal[journal["outcome_pct"] > 0]
        losses = journal[journal["outcome_pct"] <= 0]
        avg_win  = wins["outcome_pct"].mean()   if not wins.empty   else 0
        avg_loss = losses["outcome_pct"].mean() if not losses.empty else 0
        expectancy = (
            (len(wins) / len(journal)) * avg_win +
            (len(losses) / len(journal)) * avg_loss
        )

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Signals",  len(journal))
        m2.metric("Win Rate",       f"{len(wins)/len(journal)*100:.0f}%")
        m3.metric("Avg Win",        f"+{avg_win:.1f}%")
        m4.metric("Avg Loss",       f"{avg_loss:.1f}%")
        m5.metric("Expectancy",     f"{expectancy:+.2f}%",
                  delta_color="normal" if expectancy >= 0 else "inverse")

        st.dataframe(journal, use_container_width=True)

        # Return distribution
        outcome_fig = px.histogram(
            journal, x="outcome_pct", nbins=30,
            title="Distribution of Outcome Returns",
            color_discrete_sequence=["steelblue"],
        )
        outcome_fig.add_vline(x=0, line_color="red", line_dash="dash")
        outcome_fig.update_layout(height=300)
        st.plotly_chart(outcome_fig, use_container_width=True)

        # Per-timeframe and score-bucket breakdown
        st.divider()
        st.subheader("Signal Quality by Score Bucket")
        st.caption("Which score ranges actually produce moves — use this to calibrate your min score threshold.")
        stats = get_outcome_stats()
        if not stats.empty:
            st.dataframe(stats, use_container_width=True)

            quality_fig = px.bar(
                stats,
                x="score_bucket", y="avg_return_pct",
                color="win_rate_pct",
                facet_col="timeframe",
                color_continuous_scale="RdYlGn",
                range_color=[0, 100],
                title="Avg Return % by Score Bucket and Timeframe",
                labels={"avg_return_pct": "Avg Return %", "score_bucket": "Score Range"},
            )
            quality_fig.update_layout(height=350)
            st.plotly_chart(quality_fig, use_container_width=True)
