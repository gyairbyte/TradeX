"""Coil Detector Streamlit tab renderer."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from tradex.config import TradeXSettings
from tradex.tracker import analyzer


def render_coil_detector_tab(
    *,
    settings: TradeXSettings,
    timeframe: str,
) -> None:
    """Render the Coil Detector — Pre-Breakout Setups tab."""
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
        coils = analyzer.detect_coils(timeframe, days=coil_days, min_appearances=min_appearances, settings=settings)
        if coils.empty:
            st.info("No active coiling setups found. Run the Scanner a few times over multiple days to build history.")
        else:
            st.success(f"{len(coils)} coiling setups detected")
            display_cols = ["ticker", "coil_strength", "appearances", "active_sessions",
                            "latest_score", "score_trend", "trend_direction", "last_close"]
            st.dataframe(
                coils[display_cols],
                use_container_width=True,
                column_config={
                    "ticker":          st.column_config.TextColumn("Ticker"),
                    "coil_strength":   st.column_config.ProgressColumn("Coil Strength", min_value=0, max_value=100, help="Combined score of duration, signal level, and trend acceleration."),
                    "appearances":     st.column_config.NumberColumn("Distinct Sessions", help="How many distinct trading sessions this stock has shown up in."),
                    "active_sessions": st.column_config.NumberColumn("Active Sessions", help="Sessions where the score was at or above the coil threshold."),
                    "latest_score":    st.column_config.ProgressColumn("Latest Score", min_value=0, max_value=100),
                    "score_trend":     st.column_config.NumberColumn("Trend Slope", help="Positive = score rising each session. Negative = fading."),
                    "trend_direction": st.column_config.TextColumn("Direction"),
                    "last_close":      st.column_config.NumberColumn("Last Close", format="$%.2f"),
                },
            )

            st.divider()
            st.subheader("Score History")
            st.caption("Shows how this stock's signal score has evolved across distinct sessions.")
            selected_coil = st.selectbox("Select ticker to inspect", coils["ticker"].tolist(), key="sel_coil")
            state = analyzer.get_ticker_state(selected_coil, timeframe, days=coil_days)

            if state["score_history"]:
                score_fig = px.line(
                    y=state["score_history"],
                    labels={"x": "Session #", "y": "Score"},
                    title=f"{selected_coil} — Score History ({timeframe})",
                    markers=True,
                )
                score_fig.add_hline(y=50, line_dash="dot", line_color="yellow",
                                    annotation_text="Signal threshold (50)")
                score_fig.update_layout(height=300)
                st.plotly_chart(score_fig, use_container_width=True)

            st.info(f"**{state['status'].upper()}** — {state['summary']}")

    if st.button("Detect Fading Setups", key="btn_fade", type="secondary",
                 help="Search signal history for stocks that were coiling but are now fading."):
        fading = analyzer.detect_fading_setups(timeframe, days=coil_days, min_appearances=min_appearances, settings=settings)
        if fading.empty:
            st.info("No fading setups found.")
        else:
            st.warning(f"{len(fading)} fading setups detected")
            display_cols = ["ticker", "fade_strength", "appearances", "active_sessions",
                            "latest_score", "peak_score", "score_trend", "trend_direction", "last_close"]
            st.dataframe(
                fading[display_cols],
                use_container_width=True,
                column_config={
                    "ticker":          st.column_config.TextColumn("Ticker"),
                    "fade_strength":   st.column_config.ProgressColumn("Fade Strength", min_value=0, max_value=100, help="How strongly the setup is fading from its prior peak."),
                    "appearances":     st.column_config.NumberColumn("Distinct Sessions", help="How many distinct trading sessions this stock has shown up in."),
                    "active_sessions": st.column_config.NumberColumn("Active Sessions", help="Sessions where the score was at or above the coil threshold."),
                    "latest_score":    st.column_config.ProgressColumn("Latest Score", min_value=0, max_value=100),
                    "peak_score":      st.column_config.ProgressColumn("Peak Score", min_value=0, max_value=100),
                    "score_trend":     st.column_config.NumberColumn("Trend Slope", help="Negative = score declining."),
                    "trend_direction": st.column_config.TextColumn("Direction"),
                    "last_close":      st.column_config.NumberColumn("Last Close", format="$%.2f"),
                },
            )
