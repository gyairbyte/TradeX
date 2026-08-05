"""Confluence Streamlit tab renderer."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from tradex.config import TradeXSettings
from tradex.tracker.confluence import run_confluence_screen


def render_confluence_tab(
    *,
    settings: TradeXSettings,
    watchlist: list[str],
    earnings_buffer: int,
    provider: str,
    earnings_source: str,
) -> None:
    """Render the Confluence Scanner — Multi-Timeframe Alignment tab."""
    st.subheader("Confluence Scanner — Multi-Timeframe Alignment")
    st.caption(
        "Finds stocks scoring well across intraday, short-term, AND long-term simultaneously. "
        "Missing timeframes are penalized; only a true 3/3 result can be labeled 'all timeframes aligned'."
    )

    with st.expander("Why confluence matters", expanded=False):
        st.markdown("""
Most screeners only look at one timeframe. A stock can look great on a 5-minute chart but be
in a downtrend on the daily — that's a low-conviction trade fighting the bigger trend.

**Confluence means all timeframes are telling the same story:**
- The intraday chart (5-min) shows a momentum setup
- The daily chart (short-term) shows an uptrend structure
- The weekly chart (long-term) shows the stock in a healthy secular trend

**Confluence score weights (fixed denominator — missing timeframes contribute zero):**
| Timeframe | Weight | Why |
|---|---|---|
| Intraday (5m) | 30% | Noisiest — good confirmation but not the driver |
| Short-term (1d) | 40% | Most actionable timeframe for swing trades |
| Long-term (1wk) | 30% | Establishes whether the broader trend supports the trade |

**Coverage:**
- `3/3` — All three timeframes fetched and scored successfully.
- `2/3` — Two timeframes contributed. Strong or moderate tiers are possible if the corrected score and active-timeframe count support it.
- `1/3` — Single timeframe only, always treated as weak/single-timeframe.
- `0/3` — No usable data.

**Confluence tiers:**
- 🟢 **90+ and 3/3 active** — `all timeframes aligned`. Rare and high conviction.
- 🟡 **70+ with at least two active timeframes** — `strong confluence`.
- 🟠 **50–69 with at least two active timeframes** — `moderate confluence`.
- 🔴 **<50 or only one/three timeframes active** — Weak confluence or weak/incomplete timeframes.

A stock scoring 80+ on intraday alone is interesting, but it is not multi-timeframe confluence. The same stock also scoring 70+ on short and long is a fundamentally different — and better — trade.
        """)

    min_confluence = st.slider(
        "Min confluence score", 0, 100, 50, key="min_conf",
        help=(
            "Filters results to stocks where the fixed-denominator weighted score across the "
            "three configured timeframes exceeds this value. Missing timeframes contribute zero, "
            "so a single 100-score timeframe cannot pass a 70 threshold.\n\n"
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
                settings=settings,
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
                    "confluence_score":    st.column_config.ProgressColumn("Confluence", min_value=0, max_value=100, help="Fixed-denominator weighted score across intraday (30%), short (40%), and long (30%). Missing timeframes contribute zero."),
                    "tier":                st.column_config.TextColumn("Tier"),
                    "timeframe_coverage":  st.column_config.TextColumn("Coverage", help="Fraction of timeframes that successfully contributed (0/3, 1/3, 2/3, or 3/3)."),
                    "available_timeframes": st.column_config.TextColumn("Available TFs", help="Timeframes that fetched and scored successfully."),
                    "missing_timeframes":  st.column_config.TextColumn("Missing TFs", help="Timeframes that did not contribute due to missing data, insufficient bars, or scorer errors."),
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
