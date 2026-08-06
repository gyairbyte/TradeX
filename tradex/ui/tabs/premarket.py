"""Pre-Market Gap Scanner tab renderer (extracted from dashboard.py)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from tradex.config import TradeXSettings
from tradex.data.fetcher import ProviderCapabilityError
from tradex.premarket.config import GapScanConfig
from tradex.premarket.gap_scanner import scan_gaps_with_report
from tradex.premarket.models import (
    _FAILURE_STATUSES,
    _FILTER_STATUSES,
    _OUTSIDE_WINDOW_STATUSES,
    GapScanReport,
)


def _all_tickers_are(counts: dict[str, int], statuses: set[str]) -> bool:
    requested = counts.get("requested", 0)
    return requested > 0 and sum(counts.get(s, 0) for s in statuses) == requested


def _all_provider_failures(counts: dict[str, int]) -> bool:
    return _all_tickers_are(counts, {"provider_failure"})


def _all_missing_data(counts: dict[str, int]) -> bool:
    return _all_tickers_are(counts, {"no_previous_close", "no_premarket_data"})


def render_premarket_tab(
    *,
    settings: TradeXSettings,
    watchlist: list[str],
    provider: str,
    earnings_source: str,
) -> None:
    """Render the Pre-Market Gap Scanner tab."""
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
