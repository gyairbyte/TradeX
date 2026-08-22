"""Coil Detector Streamlit tab renderer."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from tradex.config import TradeXSettings
from tradex.tracker import analyzer
from tradex.ui.evidence import render_evidence_notice


def render_coil_detector_tab(
    *,
    settings: TradeXSettings,
    timeframe: str,
) -> None:
    """Render the Coil Detector — Multi-Session Persistence tab."""
    st.subheader("Coil Detector — Multi-Session Persistence")
    render_evidence_notice("coil_detector", st_module=st)
    st.caption(
        "Summarizes stocks that have appeared in multiple scans across distinct sessions without large price moves. "
        "Exploratory context describing persistence and score stability."
    )

    with st.expander("What is a coil and how does it work?", expanded=False):
        st.markdown("""
A **coil** is a descriptive observation of repeated appearances and score stability across scan sessions without a large price breakout (≥3%).

**TradeX defines a coil observation as a stock that:**
1. Has appeared in scans at least N times within the look-back window
2. Maintained a score at or above the threshold (45+)
3. Has NOT already moved ≥3% (which would indicate a prior move has occurred)
4. Has a score trend that is stable or rising

**Exploratory context:** Coil metrics summarize scan persistence. They do not predict upcoming breakouts, guarantee a future move, or establish an executable trading edge.

**Coil Strength score** combines:
- Number of distinct scan sessions where the stock appeared
- Latest signal score level
- Slope of the score trend across sessions

**Score trend directions:**
- 🟢 **Building** — score is rising across recorded scans.
- 🟡 **Stable** — holding steady at or above threshold.
- 🔴 **Fading** — score declining relative to prior scans.
        """)

    col1, col2 = st.columns(2)
    coil_days = col1.slider(
        "Look-back window (days)", 3, 21, 7, key="coil_days",
        help=(
            "How many calendar days of scan history to search through.\n\n"
            "• **Shorter (3–5 days)** — only recent sessions.\n"
            "• **7 days (default)** — one trading week.\n"
            "• **Longer (10–21 days)** — searches longer scan history (requires watcher to have run for that duration)."
        ),
    )
    min_appearances = col2.slider(
        "Min appearances", 2, 10, 2, key="coil_apps",
        help=(
            "Minimum number of scan sessions where a stock must have scored above threshold.\n\n"
            "• **2 (default)** — appeared at least twice.\n"
            "• **3–5** — repeated scan appearance.\n"
            "• **6–10** — persistent appearance across many recorded sessions.\n\n"
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
