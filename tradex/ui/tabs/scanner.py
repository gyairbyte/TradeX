"""Signal Scanner Streamlit tab renderer."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from tradex.config import TradeXSettings
from tradex.data.fetcher import (
    FetchPolicy,
    fetch,
    resolve_provider,
)
from tradex.screener.engine import run_with_report
from tradex.signals.indicators import add_indicators
from tradex.tracker import store
from tradex.ui.evidence import render_evidence_notice


def render_scanner_tab(
    *,
    settings: TradeXSettings,
    watchlist: list[str],
    timeframe: str,
    min_score: int,
    earnings_buffer: int,
    provider: str,
    earnings_source: str,
) -> None:
    """Render the Signal Scanner tab."""
    st.subheader("Signal Scanner")
    render_evidence_notice("scanner", st_module=st)
    st.caption(
        "Scores every stock in your watchlist 0–100 using additive technical indicators. "
        "Higher score = more conditions met simultaneously. Each result shows the conditions that fired."
    )

    with st.expander("How scoring works", expanded=False):
        st.markdown("""
Each timeframe runs its own set of signal checks. Points are awarded for each condition met and capped at 100.

| Signal | What it checks | Points |
|---|---|---|
| **Volume surge** | Current volume vs. 20-bar average. >2x = strong volume turnover | Up to 30 |
| **RSI momentum** | Relative Strength Index in the 55–75 zone = trending without being overbought | Up to 20 |
| **MACD crossover** | MACD line crossing above signal line = trend shift | Up to 30 |
| **EMA structure** | Price above EMA20 which is above EMA50 = uptrend structure | Up to 25 |
| **Bollinger Band expansion** | Bands tightening then widening = volatility expansion | Up to 20 |
| **Pullback to EMA** | Price dipping back to EMA20 in an uptrend = moving average test | Up to 15 |

**Score guide:**
- 0–39: Few conditions met
- 40–59: Moderate condition alignment
- 60–79: Multiple conditions aligned
- 80–100: Most conditions aligned simultaneously (legacy heuristic discovery only)
        """)

    run_scan = st.button("Run Scan", type="primary", key="btn_scan",
                         help="Fetch live data for all watchlist tickers and score each one.")

    if run_scan:
        progress_bar = st.progress(0.0, text=f"Scanning {len(watchlist)} tickers on {timeframe}…")
        scan_provider = resolve_provider(provider)
        scan_policy = FetchPolicy.build()

        retry_label = f"{scan_policy.max_retries} retry" + ("" if scan_policy.max_retries == 1 else "ies")
        if scan_policy.fallback_order:
            fb_label = "Fallback: " + " → ".join(scan_policy.fallback_order)
        else:
            fb_label = "Fallback disabled"
        st.caption(f"Retries: {retry_label} | {fb_label}")

        def _update_progress(done: int, total: int) -> None:
            progress_bar.progress(done / total, text=f"Scanning {done}/{total} tickers on {timeframe}…")

        report = run_with_report(
            watchlist,
            timeframe=timeframe,
            min_score=min_score,
            exclude_earnings_within=earnings_buffer if earnings_buffer > 0 else None,
            progress=_update_progress,
            provider=scan_provider,
            earnings_source=earnings_source,
            policy=scan_policy,
            settings=settings,
        )
        results = report.results
        actual_provider = report.actual_provider or report.requested_provider
        progress_bar.empty()

        has_fetch_failures = bool(report.fetch_failures)
        has_scoring_failures = bool(report.scoring_failures)
        has_earnings_failures = bool(report.earnings_failures)
        all_earnings_excluded = report.total_earnings_excluded == len(watchlist)
        all_fetch_eligible_failed = (
            report.total_fetch_eligible > 0
            and report.total_fetched == 0
            and has_fetch_failures
        )

        if report.fallback_used:
            st.info(
                f"Fallback used: requested provider '{report.requested_provider}', "
                f"actual provider '{actual_provider}'"
            )

        if all_fetch_eligible_failed:
            categories = {type(e).__name__ for e in report.fetch_failures.values()}
            st.error(
                f"Provider '{report.requested_provider}' failed for all "
                f"{report.total_fetch_eligible} symbol(s) that reached OHLCV fetching. "
                f"Failure categories: {', '.join(sorted(categories)) or 'unknown'}."
            )
        elif (
            report.total_fetched == 0
            and has_earnings_failures
            and not has_fetch_failures
            and not has_scoring_failures
            and not all_earnings_excluded
        ):
            categories = {type(e).__name__ for e in report.earnings_failures.values()}
            st.error(
                f"Earnings source failed for {len(report.earnings_failures)} symbol(s). "
                f"Failure categories: {', '.join(sorted(categories)) or 'unknown'}."
            )
        elif results.empty:
            if all_earnings_excluded:
                st.warning(
                    f"No matching results found. All {report.total_earnings_excluded} tickers "
                    f"were excluded due to upcoming earnings."
                )
            else:
                st.warning("No matching results found. Lower the min score or add more tickers.")
        else:
            failed_count = len(report.failures)
            if failed_count:
                st.warning(
                    f"Found {len(results)} matching results; {failed_count} symbol(s) had stage failures."
                )
            else:
                if earnings_buffer > 0:
                    st.success(f"Found {len(results)} matching results (excluded tickers with earnings within {earnings_buffer}d)")
                else:
                    st.success(f"Found {len(results)} matching results")
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
            st.session_state["scan_provider"] = actual_provider

        # Persist every scan exactly once, regardless of whether it produced signals.
        store.record_scan(
            report,
            timeframe=timeframe,
            min_score=min_score,
            tickers_scanned=list(dict.fromkeys(str(t).upper() for t in watchlist)),
            settings=settings,
        )

        # Surface each non-empty stage failure map independently.
        if has_earnings_failures:
            st.warning(f"{len(report.earnings_failures)} earnings lookup(s) failed.")
            with st.expander("Earnings failure summary"):
                for ticker, err in report.earnings_failures.items():
                    st.caption(f"**{ticker}**: {type(err).__name__}")
                    st.text(str(err))

        if has_fetch_failures and not all_fetch_eligible_failed:
            st.warning(f"{len(report.fetch_failures)} OHLCV fetch/insufficient-data failure(s).")
            with st.expander("OHLCV failure summary"):
                for ticker, err in report.fetch_failures.items():
                    st.caption(f"**{ticker}**: {type(err).__name__}")
                    st.text(str(err))

        if has_scoring_failures:
            st.warning(f"{len(report.scoring_failures)} scoring failure(s).")
            with st.expander("Scoring failure summary"):
                for ticker, err in report.scoring_failures.items():
                    st.caption(f"**{ticker}**: {type(err).__name__}")
                    st.text(str(err))

        if report.attempt_log:
            with st.expander("Fetch attempt summary"):
                st.caption(
                    f"Providers attempted: {report.providers_attempted} | "
                    f"total attempts: {report.total_fetch_attempted} | "
                    f"retries: {report.total_retries}"
                )
                for prov in report.providers_attempted:
                    entries = [a for a in report.attempt_log if a.provider == prov]
                    attempted = len(entries)
                    succeeded = sum(1 for e in entries if e.success)
                    failed = attempted - succeeded
                    retries = sum(e.retries for e in entries)
                    st.text(
                        f"{prov}: {attempted} attempted, {succeeded} succeeded, "
                        f"{failed} failed, {retries} retries"
                    )

    if "scan_results" in st.session_state and not st.session_state["scan_results"].empty:
        st.divider()
        st.subheader("Drill-down Chart")
        st.caption("Candlestick chart with EMA20 (orange), EMA50 (blue), and Bollinger Bands (gray shaded). Volume bars below. Uses the provider from the saved scan.")
        tickers_with_signals = st.session_state["scan_results"]["ticker"].tolist()
        selected = st.selectbox("Select ticker", tickers_with_signals, key="sel_scanner",
                                help="Pick any stock from the scan results to view its chart.")
        tf = st.session_state["scan_timeframe"]
        scan_provider = st.session_state.get("scan_provider", provider)

        df = fetch(selected, tf, provider=scan_provider, settings=settings)
        df = add_indicators(df)

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="Price",
        ))
        fig.add_trace(go.Scatter(x=df.index, y=df["ema_20"], name="EMA20",
                                 line={"color": "orange", "width": 1}))
        fig.add_trace(go.Scatter(x=df.index, y=df["ema_50"], name="EMA50",
                                 line={"color": "blue", "width": 1}))
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"], name="BB Upper",
                                 line={"color": "gray", "dash": "dot", "width": 1}))
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"], name="BB Lower",
                                 line={"color": "gray", "dash": "dot", "width": 1},
                                 fill="tonexty", fillcolor="rgba(200,200,200,0.1)"))
        fig.update_layout(xaxis_rangeslider_visible=False, height=500)
        st.plotly_chart(fig, use_container_width=True)

        vol_fig = go.Figure()
        colors = ["green" if c >= o else "red" for c, o in zip(df["close"], df["open"])]
        vol_fig.add_trace(go.Bar(x=df.index, y=df["volume"], marker_color=colors, name="Volume"))
        vol_fig.add_trace(go.Scatter(x=df.index, y=df["volume_sma20"], name="Vol SMA20",
                                     line={"color": "white", "width": 1.5}))
        vol_fig.update_layout(height=200)
        st.plotly_chart(vol_fig, use_container_width=True)

        row = st.session_state["scan_results"][
            st.session_state["scan_results"]["ticker"] == selected
        ].iloc[0]
        st.info(f"**Score: {row['score']}** — {row['reasons']}")
