"""Signal Scanner Streamlit tab renderer with Market-Wide Opportunity Discovery (LONG-MVP-003)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tradex.config import TradeXSettings
from tradex.data.fetcher import (
    FetchPolicy,
    fetch,
    resolve_provider,
)
from tradex.discovery import (
    DiscoveryCoordinator,
    Scope,
    resolve_universe,
)
from tradex.discovery.cache import compute_discovery_cache_key
from tradex.discovery.session import get_applicable_completed_session
from tradex.screener.engine import build_long_focus_list, run_with_report
from tradex.signals import long_term
from tradex.signals.indicators import add_indicators
from tradex.tracker import store
from tradex.ui.evidence import render_evidence_notice


def _render_long_table(results_df: pd.DataFrame) -> None:
    """Render a DataFrame of Long MVP results with standard formatting."""
    if results_df.empty:
        return
    display_df = results_df.copy()
    pct_cols = ["atr_pct", "return_5", "return_20", "return_60"]
    for col in pct_cols:
        if col in display_df.columns:
            display_df[col] = pd.to_numeric(display_df[col], errors="coerce") * 100.0

    long_cols = [
        c
        for c in [
            "ticker",
            "state",
            "primary_setup",
            "score",
            "last_close",
            "trigger",
            "invalidation",
            "atr_pct",
            "volume_ratio",
            "return_5",
            "return_20",
            "return_60",
            "days_until_earnings",
            "reasons",
            "provider",
        ]
        if c in display_df.columns
    ]
    st.dataframe(
        display_df[long_cols],
        use_container_width=True,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker"),
            "state": st.column_config.TextColumn("State"),
            "primary_setup": st.column_config.TextColumn("Setup"),
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
            "last_close": st.column_config.NumberColumn("Last Close", format="$%.2f"),
            "trigger": st.column_config.TextColumn("Trigger", width="medium"),
            "invalidation": st.column_config.TextColumn("Invalidation", width="medium"),
            "atr_pct": st.column_config.NumberColumn("ATR %", format="%.2f%%"),
            "volume_ratio": st.column_config.NumberColumn("Vol Ratio", format="%.2f"),
            "return_5": st.column_config.NumberColumn("5d Return", format="%.2f%%"),
            "return_20": st.column_config.NumberColumn("20d Return", format="%.2f%%"),
            "return_60": st.column_config.NumberColumn("60d Return", format="%.2f%%"),
            "days_until_earnings": st.column_config.NumberColumn(
                "Earnings In",
                format="%d d",
                help=(
                    "Calendar days until the next scheduled earnings report. "
                    "Blank/unavailable means TradeX could not establish a reliable upcoming earnings date; "
                    "it does not prove there is no scheduled earnings event."
                ),
            ),
            "reasons": st.column_config.TextColumn("Reasons", width="large"),
            "provider": st.column_config.TextColumn(
                "OHLCV Provider", help="Market-data provider used to score this ticker."
            ),
        },
    )


def _render_legacy_table(results_df: pd.DataFrame) -> None:
    """Render a DataFrame of Intraday/Short results with standard formatting."""
    st.dataframe(
        results_df,
        use_container_width=True,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker"),
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
            "last_close": st.column_config.NumberColumn("Last Close", format="$%.2f"),
            "volume_ratio": st.column_config.NumberColumn(
                "Vol Ratio",
                help="Current volume ÷ 20-bar average. >2 = unusually high volume.",
            ),
            "rsi": st.column_config.NumberColumn(
                "RSI",
                help="Relative Strength Index. 30=oversold, 70=overbought. Sweet spot: 50–70.",
            ),
            "days_until_earnings": st.column_config.NumberColumn(
                "Earnings In",
                format="%d d",
                help=(
                    "Calendar days until the next scheduled earnings report. "
                    "Blank/unavailable means TradeX could not establish a reliable upcoming earnings date; "
                    "it does not prove there is no scheduled earnings event."
                ),
            ),
            "reasons": st.column_config.TextColumn("Reasons", width="large"),
            "provider": st.column_config.TextColumn(
                "OHLCV Provider", help="Market-data provider used to score this ticker."
            ),
        },
    )


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
        "Scores stocks 0–100 using additive technical conditions. "
        "Higher score = more conditions met simultaneously. Each result shows the conditions that fired."
    )

    with st.expander("How scoring works", expanded=False):
        if timeframe == "long":
            st.markdown("""
TradeX **Long Opportunity Strategy v1** models liquid stocks across three distinct swing setup archetypes over a 5–21 session horizon using daily bars.

### The 3 Strategy Archetypes
1. **Momentum Continuation (`momentum_continuation`)**: Strong secular uptrend (`close > EMA20 > EMA50 > EMA200`), persistent intermediate momentum (`return_20 >= +5%`, `return_60 >= +10%`), within 5% of 20-day high, healthy RSI (50–75).
2. **Trend Pullback (`trend_pullback`)**: Primary trend intact (`EMA20 > EMA50 > EMA200`, `return_60 >= +10%`, `close > EMA50`), controlled retracement (`return_5` between -8% and +2%), near EMA20 support (within 4%), reset RSI (40–62).
3. **Breakout / Expansion (`breakout_expansion`)**: Trend intact (`EMA20 > EMA50 > EMA200`), consolidating within 2% of 20-day high or breaking out with volume (`volume_ratio >= 1.30`), RSI 50–78.

### 100-Point Deterministic Score
- **Trend Quality (30 pts)**: Moving average alignment (`close > EMA20`, `EMA20 > EMA50`, `EMA50 > EMA200`) and rising EMA20 slope.
- **Momentum Quality (25 pts)**: Archetype-aware returns (5d, 20d, 60d) and RSI ranges.
- **Setup Quality (20 pts)**: Archetype-specific structural proximity and confirmation.
- **Movement Capacity (15 pts)**: Normalized volatility capacity (`ATR14 / close`, sweet spot 2.0%–6.0%).
- **Participation (10 pts)**: 20-session relative volume turnover conviction.

### Execution States
- **ENTER NOW**: Score >= 75 and actionable confirmation trigger met.
- **ARMED**: Score >= 70 and nearing trigger level.
- **QUALIFIED WAITLIST**: Score >= 60 and technically credible setup.
- Candidates below 60 or failing eligibility floor (220 bars, price >= $5, median dollar volume >= $20M) are omitted.
            """)
        else:
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

    # ── Scan Scope selector (Long scans only; My Watchlist is default) ────────────
    if timeframe == "long":
        scope_options = [
            Scope.MY_WATCHLIST.value,
            Scope.SP500.value,
            Scope.NASDAQ100.value,
            Scope.ALL_US_STOCKS.value,
        ]
        scan_scope_str = st.selectbox(
            "Scan Scope",
            scope_options,
            index=0,
            key="scanner_scan_scope",
            help=(
                "Choose the market universe to evaluate:\n\n"
                "• **My Watchlist** — Evaluates your active watchlist (default, preserves existing behavior).\n"
                "• **S&P 500** — Evaluates constituents from the S&P 500 preset snapshot.\n"
                "• **Nasdaq 100** — Evaluates constituents from the Nasdaq 100 preset snapshot.\n"
                "• **All U.S. Listed Stocks** — Discovers and evaluates the broader U.S.-listed common stock universe from the official Nasdaq Trader Symbol Directory."
            ),
        )
        scan_scope = Scope(scan_scope_str)
    else:
        scan_scope = Scope.MY_WATCHLIST

    # ─────────────────────────────────────────────────────────────────────────────
    # WORKFLOW A: My Watchlist (Default / All timeframes)
    # ─────────────────────────────────────────────────────────────────────────────
    if scan_scope == Scope.MY_WATCHLIST:
        run_scan = st.button(
            "Run Scan",
            type="primary",
            key="btn_scan",
            help="Fetch live data for all watchlist tickers and score each one.",
        )

        if run_scan:
            scan_provider = resolve_provider(provider, settings=settings)
            progress_bar = st.progress(0.0, text=f"Scanning {len(watchlist)} tickers on {timeframe}…")
            scan_policy = FetchPolicy.build(settings=settings)

            retry_label = f"{scan_policy.max_retries} retry" + (
                "" if scan_policy.max_retries == 1 else "ies"
            )
            if scan_policy.fallback_order:
                fb_label = "Fallback: " + " → ".join(scan_policy.fallback_order)
            else:
                fb_label = "Fallback disabled"
            st.caption(f"Retries: {retry_label} | {fb_label}")

            def _update_progress(done: int, total: int) -> None:
                progress_bar.progress(
                    done / total, text=f"Scanning {done}/{total} tickers on {timeframe}…"
                )

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
                report.total_fetch_eligible > 0 and report.total_fetched == 0 and has_fetch_failures
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
                        st.success(
                            f"Found {len(results)} matching results (excluded tickers with earnings within {earnings_buffer}d)"
                        )
                    else:
                        st.success(f"Found {len(results)} matching results")

                if timeframe == "long":
                    display_df = build_long_focus_list(results)
                    _render_long_table(display_df)
                else:
                    _render_legacy_table(results)

                st.session_state["scan_results"] = results
                st.session_state["scan_timeframe"] = timeframe
                st.session_state["scan_scope"] = scan_scope.value
                st.session_state["scan_provider"] = actual_provider

            # Persist every scan exactly once, regardless of whether it produced signals.
            store.record_scan(
                report,
                timeframe=timeframe,
                min_score=min_score,
                tickers_scanned=list(dict.fromkeys(str(t).upper() for t in watchlist)),
                settings=settings,
            )

            # Surface stage failure maps independently
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

    # ─────────────────────────────────────────────────────────────────────────────
    # WORKFLOW B: Index Discovery & All U.S. Listed Stocks
    # ─────────────────────────────────────────────────────────────────────────────
    else:
        scan_provider = resolve_provider(provider, settings=settings)
        coordinator = DiscoveryCoordinator(settings=settings)
        market_session = get_applicable_completed_session()
        session_date = market_session.session_date

        try:
            tickers, prov = resolve_universe(scan_scope, settings=settings)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to resolve universe for {scan_scope.value}: {exc}")
            return

        cache_key = compute_discovery_cache_key(
            strategy_id=long_term.STRATEGY_ID,
            strategy_version=long_term.STRATEGY_VERSION,
            universe_id=prov.universe_id,
            universe_hash=prov.snapshot_hash,
            session_date=session_date,
            requested_provider=scan_provider,
            earnings_source=(earnings_source or settings.earnings_data_source).lower().strip(),
            earnings_buffer=earnings_buffer,
            min_score=min_score,
        )
        checkpoint = coordinator.cache.load(cache_key)

        # Provenance and scope metadata banner
        source_note = (
            f"Source: {prov.universe_id} ({prov.source_file_generation_timestamp or prov.retrieval_timestamp[:10]})"
        )
        st.caption(
            f"**Selected Scope:** {scan_scope.value} | **Constituents:** {len(tickers)} tickers | "
            f"**Session:** {session_date} | {source_note}"
        )
        if prov.is_stale:
            st.warning(f"Preserved universe snapshot: {prov.stale_reason}")

        # Action button controls based on checkpoint state
        btn_start = False
        btn_continue = False
        btn_retry = False
        btn_reset = False

        if checkpoint is None or not checkpoint.attempted_tickers:
            btn_start = st.button(
                "Scan for Opportunities",
                type="primary",
                key="btn_disc_start",
                help=f"Scan {len(tickers)} tickers in {scan_scope.value} using bounded batches.",
            )
        elif len(checkpoint.attempted_tickers) < len(tickers):
            c1, c2, c3 = st.columns([2, 2, 1])
            btn_continue = c1.button(
                "Continue Scan",
                type="primary",
                key="btn_disc_continue",
                help=f"Resume scan from ticker {len(checkpoint.attempted_tickers)}/{len(tickers)}.",
            )
            btn_start = c2.button(
                "Restart Scan",
                key="btn_disc_restart",
                help="Discard checkpoint and restart scan from the beginning.",
            )
            btn_reset = c3.button("Reset Scan", key="btn_disc_reset")
        else:
            c1, c2, c3 = st.columns([2, 2, 1])
            btn_start = c1.button(
                "Rescan Opportunities",
                type="primary",
                key="btn_disc_rescan",
                help="Re-evaluate all tickers for this session.",
            )
            if checkpoint.failed_tickers:
                btn_retry = c2.button(
                    f"Retry {len(checkpoint.failed_tickers)} Failed",
                    key="btn_disc_retry",
                    help="Retry only tickers that encountered stage or provider failures.",
                )
            btn_reset = c3.button("Reset Scan", key="btn_disc_reset")

        if btn_reset:
            coordinator.cache.clear(cache_key)
            st.session_state.pop(f"disc_result_{scan_scope.value}", None)
            st.session_state.pop("scan_results", None)
            st.success("Scan checkpoint reset.")
            st.rerun()

        if btn_start or btn_continue or btn_retry:
            prog_bar = st.progress(0.0, text=f"Evaluating {scan_scope.value} on {session_date}…")

            def _update_discovery_progress(done: int, total: int, status_txt: str) -> None:
                prog_bar.progress(done / total if total > 0 else 0.0, text=status_txt)

            result = coordinator.run(
                scan_scope,
                provider=scan_provider,
                earnings_source=earnings_source,
                earnings_buffer=earnings_buffer,
                min_score=min_score,
                batch_size=100,
                max_workers=4,
                pacing_delay_seconds=0.1,
                retry_failed=bool(btn_retry),
                force_reset=bool(btn_start and checkpoint is not None),
                progress_callback=_update_discovery_progress,
            )
            prog_bar.empty()

            st.session_state[f"disc_result_{scan_scope.value}"] = result
            st.session_state["scan_results"] = result.focus_list
            st.session_state["scan_timeframe"] = "long"
            st.session_state["scan_scope"] = scan_scope.value
            st.session_state["scan_provider"] = result.actual_provider

        # Render current results if present
        result = st.session_state.get(f"disc_result_{scan_scope.value}")
        if result is None and checkpoint is not None and checkpoint.attempted_tickers:
            # Reconstitute result view from valid checkpoint without re-fetching
            result = coordinator.run(
                scan_scope,
                provider=scan_provider,
                earnings_source=earnings_source,
                earnings_buffer=earnings_buffer,
                min_score=min_score,
                max_batches_per_run=0,  # 0 batches -> view checkpoint without running new fetches
            )
            st.session_state[f"disc_result_{scan_scope.value}"] = result
            st.session_state["scan_results"] = result.focus_list
            st.session_state["scan_timeframe"] = "long"
            st.session_state["scan_scope"] = scan_scope.value
            st.session_state["scan_provider"] = result.actual_provider

        if result is not None:
            # Completeness and Coverage Status
            st.markdown(
                f"**Scan Status:** `{result.status.value}` | **Market Session:** `{result.session_date}` | "
                f"**Coverage:** {result.completed_count}/{result.total_tickers} tickers evaluated"
            )
            col_a, col_b, col_c, col_d, col_e = st.columns(5)
            col_a.metric("Total Universe", result.total_tickers)
            col_b.metric("Evaluated", result.completed_count)
            col_c.metric("Scored", result.scored_count)
            col_d.metric("Qualifying Setups", result.qualifying_count)
            col_e.metric("Failures / Missing", result.failed_count)

            if result.is_partial:
                st.warning(
                    f"**Partial results — not the final ranking across the full selected universe.** "
                    f"({result.completed_count}/{result.total_tickers} tickers evaluated)"
                )

            if result.focus_list.empty:
                st.info(
                    f"No qualifying Long MVP opportunities found matching score >= {min_score} "
                    f"across {result.completed_count} evaluated tickers."
                )
            else:
                st.write("**Top Focus Opportunities (Display Capped: 7 ENTER NOW / 12 ARMED / 12 QUALIFIED WAITLIST)**")
                _render_long_table(result.focus_list)

            if not result.all_qualifying.empty and len(result.all_qualifying) > len(result.focus_list):
                with st.expander(f"All Qualifying Opportunities ({len(result.all_qualifying)} tickers)", expanded=False):
                    _render_long_table(result.all_qualifying)

            if result.failures:
                with st.expander(f"Stage and Provider Failures ({len(result.failures)} symbol(s))", expanded=False):
                    for sym, msg in sorted(result.failures.items()):
                        st.caption(f"**{sym}**: {msg}")

    # ─────────────────────────────────────────────────────────────────────────────
    # DRILL-DOWN CHART (Shared across workflows)
    # ─────────────────────────────────────────────────────────────────────────────
    if "scan_results" in st.session_state and not st.session_state["scan_results"].empty:
        saved_scope = st.session_state.get("scan_scope", Scope.MY_WATCHLIST.value)
        if saved_scope == scan_scope.value:
            st.divider()
            st.subheader("Drill-down Chart")
            tf = st.session_state.get("scan_timeframe", timeframe)
            chart_provider = st.session_state.get("scan_provider", provider)
            if tf == "long":
                st.caption(
                    "Candlestick chart with EMA20 (orange), EMA50 (blue), EMA200 (purple), "
                    "and Bollinger Bands (gray shaded). Volume bars below. Uses provider from the scan."
                )
            else:
                st.caption(
                    "Candlestick chart with EMA20 (orange), EMA50 (blue), and Bollinger Bands (gray shaded). "
                    "Volume bars below. Uses provider from the scan."
                )
            tickers_with_signals = st.session_state["scan_results"]["ticker"].tolist()
            selected = st.selectbox(
                "Select ticker",
                tickers_with_signals,
                key="sel_scanner",
                help="Pick any stock from the scan results to view its chart.",
            )

            df = fetch(selected, tf, provider=chart_provider, settings=settings)
            df = add_indicators(df)

            fig = go.Figure()
            fig.add_trace(
                go.Candlestick(
                    x=df.index,
                    open=df["open"],
                    high=df["high"],
                    low=df["low"],
                    close=df["close"],
                    name="Price",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=df["ema_20"], name="EMA20", line={"color": "orange", "width": 1}
                )
            )
            fig.add_trace(
                go.Scatter(x=df.index, y=df["ema_50"], name="EMA50", line={"color": "blue", "width": 1})
            )
            if tf == "long" and "ema_200" in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df["ema_200"],
                        name="EMA200",
                        line={"color": "purple", "width": 1},
                    )
                )
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["bb_upper"],
                    name="BB Upper",
                    line={"color": "gray", "dash": "dot", "width": 1},
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["bb_lower"],
                    name="BB Lower",
                    line={"color": "gray", "dash": "dot", "width": 1},
                    fill="tonexty",
                    fillcolor="rgba(200,200,200,0.1)",
                )
            )
            fig.update_layout(xaxis_rangeslider_visible=False, height=500)
            st.plotly_chart(fig, use_container_width=True)

            vol_fig = go.Figure()
            colors = ["green" if c >= o else "red" for c, o in zip(df["close"], df["open"])]
            vol_fig.add_trace(go.Bar(x=df.index, y=df["volume"], marker_color=colors, name="Volume"))
            vol_fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["volume_sma20"],
                    name="Vol SMA20",
                    line={"color": "white", "width": 1.5},
                )
            )
            vol_fig.update_layout(height=200)
            st.plotly_chart(vol_fig, use_container_width=True)

            matching_rows = st.session_state["scan_results"][
                st.session_state["scan_results"]["ticker"] == selected
            ]
            if not matching_rows.empty:
                row = matching_rows.iloc[0]
                st.info(f"**Score: {row['score']}** — {row['reasons']}")
