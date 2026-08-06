"""Pattern Similarity — Experimental Research tab renderer."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from tradex.config import TradeXSettings
from tradex.data.fetcher import ProviderCapabilityError
from tradex.patterns.config import PROFILES
from tradex.patterns.fingerprint import list_fingerprints, load_fingerprint, run_full_build
from tradex.patterns.matcher import match_ticker, run_match_screen


def render_pattern_similarity_tab(
    *,
    settings: TradeXSettings,
    watchlist: list[str],
    provider: str,
) -> None:
    """Render the experimental Pattern Similarity tab."""
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
