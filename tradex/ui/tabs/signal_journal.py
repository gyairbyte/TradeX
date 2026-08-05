"""Signal Journal Streamlit tab renderer."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from tradex.config import TradeXSettings
from tradex.data.fetcher import resolve_provider
from tradex.tracker import store
from tradex.tracker.outcome_tracker import get_outcome_stats, run_outcome_pass


def render_signal_journal_tab(
    *,
    settings: TradeXSettings,
    timeframe: str,
    provider: str,
) -> None:
    """Render the Signal Journal — historical signal outcomes."""
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

    outcome_provider = resolve_provider(provider, settings=settings)
    col_refresh, col_info = st.columns([1, 4])
    with col_refresh:
        if st.button("Refresh Outcomes Now", key="btn_outcomes",
                     help="Manually trigger outcome fetching for all unresolved signals whose window has closed."):
            with st.spinner("Fetching price outcomes for pending signals…"):
                summary = run_outcome_pass(verbose=False, provider=provider, settings=settings)
            st.success(
                f"Resolved {summary['resolved']} — "
                f"{summary['pending']} pending (window not closed yet) — "
                f"{summary['errors']} errors."
            )
    with col_info:
        st.caption(f"Outcome provider: **{outcome_provider}**  ·  Refreshes automatically at 4:30pm ET when the watcher is running.")

    journal = store.get_signal_journal(timeframe=timeframe if timeframe else None, settings=settings)

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
        stats = get_outcome_stats(settings=settings)
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
