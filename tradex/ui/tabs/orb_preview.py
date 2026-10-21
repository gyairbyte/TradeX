"""ORB Market-Wide Opportunity Scanner & Candidate Preview UI tab renderer.

Implements DAYTRADE-003F inside Research Lab as an explicitly non-actionable, research-only tool:
- Discovers U.S. equities on NYSE and Nasdaq without requiring the user to provide a watchlist or ticker symbols.
- Features prominent "Scan Market" action triggering lean two-stage discovery and ranking.
- Displays scan progress across stages: Discovery -> Daily Screening -> Opening Range & RV14 -> Ranking.
- Ranks Top-20 opportunities with explainable setup context and theoretical protective stop offsets (0.10 * ATR14).
- Prominently audits and discloses universe coverage, feed type (SIP consolidated vs IEX degraded), and data freshness.
- Enforces strict 09:35 ET time-gating (blocks ranking if as-of time is before 09:35 ET).
- Preserves existing Synthetic Demo Snapshot and Custom JSON Upload modes for testing and offline analysis.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd
import streamlit as st

from tradex.config import TradeXSettings
from tradex.market.hours import MARKET_TIMEZONE
from tradex.research.daytrade_orb.demo_fixture import create_demo_snapshot
from tradex.research.daytrade_orb.preview import (
    RESEARCH_PREVIEW_DISCLAIMER,
    CandidatePreviewRow,
    ExclusionCategory,
    ORBCandidatePreviewResult,
    generate_orb_candidate_preview,
)
from tradex.research.daytrade_orb.provider import (
    AlpacaORBProvider,
    MockORBProvider,
    ORBMarketDataProvider,
    ORBProviderConfigurationError,
    ORBProviderError,
)
from tradex.research.daytrade_orb.scanner import (
    ScanProgress,
    run_market_scan,
)
from tradex.research.daytrade_orb.snapshot import (
    MAX_SNAPSHOT_BYTES,
    ORBSnapshot,
    SnapshotValidationError,
    parse_snapshot_json,
)


def _render_candidates_table(candidates: list[CandidatePreviewRow]) -> None:
    """Render the user-facing Top-20 candidates table with explainable metrics."""
    if not candidates:
        st.info("No candidates met the eligibility filters (Price > $5, ADV14 >= 1M, ATR14 > $0.50, RV14 >= 1.0).")
        return

    table_rows = []
    for c in candidates:
        trigger_str = (
            f"${c.stop_entry_trigger:.2f}"
            if c.stop_entry_trigger is not None
            else "None (Doji)"
        )
        table_rows.append(
            {
                "Rank": c.rank,
                "Symbol": c.symbol,
                "Direction": c.direction.value,
                "OR Open": f"${c.or_open:.2f}",
                "OR High": f"${c.or_high:.2f}",
                "OR Low": f"${c.or_low:.2f}",
                "OR Close": f"${c.or_close:.2f}",
                "OR Volume": f"{c.or_volume:,.0f}",
                "ADV14": f"{c.adv14:,.0f}",
                "ATR14": f"${c.atr14:.2f}",
                "RV14": f"{c.rv14:.2f}x",
                "Stop-Entry Trigger": trigger_str,
                "Theoretical Stop Offset": f"±${c.theoretical_stop_offset:.2f}",
                "Order Intent": c.order_intent_status.value,
                "Setup Explanation": c.explanation,
            }
        )

    df_candidates = pd.DataFrame(table_rows)
    st.dataframe(df_candidates, use_container_width=True, hide_index=True)


def _render_exclusions_audit(exclusions: list[Any]) -> None:
    """Render the candidate exclusions and data-quality audit view."""
    num_tech = sum(1 for e in exclusions if getattr(e, "category", None) == ExclusionCategory.TECHNICAL_FILTER)
    num_unav = sum(1 for e in exclusions if getattr(e, "category", None) == ExclusionCategory.DATA_UNAVAILABLE)
    num_block = sum(1 for e in exclusions if getattr(e, "category", None) == ExclusionCategory.INTEGRITY_BLOCKED)

    with st.expander(
        f"Exclusions and Blocked Constituents ({len(exclusions)} total: "
        f"{num_tech} filter/cutoff, {num_unav} unavailable, {num_block} integrity blocked)",
        expanded=False,
    ):
        if not exclusions:
            st.write("No symbols were excluded.")
        else:
            ex_rows = [
                {
                    "Symbol": e.symbol,
                    "Category": e.category.value if hasattr(e.category, "value") else str(e.category),
                    "Reason": e.reason,
                }
                for e in exclusions
            ]
            df_exclusions = pd.DataFrame(ex_rows)
            st.dataframe(df_exclusions, use_container_width=True, hide_index=True)


def render_orb_preview_tab(
    *,
    settings: TradeXSettings,
) -> None:
    """Render the ORB Opportunity Scanner and Candidate Preview tab inside Research Lab."""
    st.subheader("Stocks-in-Play 5-Minute ORB Candidate Preview — Research Only")

    # Visible governance and research disclaimers
    st.warning(RESEARCH_PREVIEW_DISCLAIMER)

    with st.expander("Methodology, Limitations & Governance Disclosures", expanded=False):
        st.markdown(
            """
            **Primary Literature Foundation:**
            - Strategy rules: Zarattini, Barbon, Aziz (2024), *A Profitable Day Trading Strategy For The U.S. Equity Market* (Swiss Finance Institute RP 24-98).
            - Position sizing / stop-loss: Zarattini & Aziz (2023), SSRN 4416622.

            **Critical Research-Only Limitations:**
            1. **Unvalidated Research Status:** TradeX has **not** confirmed or replicated published historical returns. No production strategy is authorized (`APPROVED_PRODUCTION_STRATEGIES == ()`).
            2. **Market-Wide Discovery:** When running a live market scan, TradeX discovers eligible U.S. equities on NYSE and Nasdaq automatically without requiring a user watchlist.
            3. **09:35 ET Time-Gate:** Ranking requires complete 09:30–09:34 ET regular-session bars and strictly prior daily bars (D-1 and older). Ranking is blocked before 09:35:00 ET.
            4. **No Execution Fills or Pre-filled Stops:** Prospective stop-entry triggers represent the opening-range boundary (OR High for LONG, OR Low for SHORT). The protective-stop offset is **theoretical ($0.10 \\times \\text{ATR14}$)** and anchors to the **future executed fill**, which does not exist at 09:35 ET.
            5. **Doji Invariant:** Doji opening ranges produce `NO_ORDER` and are **not** backfilled with rank #21.
            6. **Feed Limitations:** TradeX explicitly identifies whether market data is consolidated SIP (100% tape volume) or degraded IEX (~2% volume).
            7. **Zero Side-Effects:** No live broker orders, persistence writes, or automated alerts are triggered.
            """
        )

    # Ingestion Source Selector
    st.markdown("#### Mode & Data Input")
    input_source = st.radio(
        "Select Scanner Mode / Data Input",
        options=[
            "Market-Wide Live Discovery",
            "Synthetic Demo Snapshot",
            "Upload Custom Snapshot JSON",
        ],
        index=1,  # Default to Synthetic Demo to ensure compatibility with existing mock fixtures
        horizontal=True,
        help="Choose Market-Wide Live Discovery to scan eligible U.S. stocks, or select offline snapshot modes.",
    )

    # ══════════════════════════════════════════════════════════════════════════════
    # MODE 1: MARKET-WIDE LIVE DISCOVERY
    # ══════════════════════════════════════════════════════════════════════════════
    if input_source == "Market-Wide Live Discovery":
        st.markdown("#### Market-Wide Opening Range Breakout Scanner")
        st.caption(
            "Scans U.S. equities on NYSE and Nasdaq at or after 09:35 ET without requiring ticker entry. "
            "Applies published Zarattini et al. (2024) eligibility (Price > $5, ADV14 >= 1M, ATR14 > $0.50, RV14 >= 1.0) "
            "and ranks the Top 20 Stocks in Play."
        )

        has_alpaca_creds = bool(settings.data.alpaca_api_key and settings.data.alpaca_secret_key)
        provider_mode = st.radio(
            "Select Scanner Provider",
            options=["Alpaca Live Provider", "Deterministic Mock Provider (Credential-Free)"],
            index=0 if has_alpaca_creds else 1,
            horizontal=True,
            help="Alpaca queries live market data. Deterministic Mock Provider runs offline simulated discovery.",
        )

        provider_obj: ORBMarketDataProvider | None = None
        if provider_mode == "Alpaca Live Provider":
            if not has_alpaca_creds:
                st.warning(
                    "⚠️ **Alpaca credentials not found:** `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` are not configured in your `.env` file. "
                    "You can switch to the **Deterministic Mock Provider** to inspect the scanner workflow, "
                    "or add credentials to `.env` to query live market data."
                )
            else:
                provider_obj = AlpacaORBProvider(
                    api_key=settings.data.alpaca_api_key or "",
                    secret_key=settings.data.alpaca_secret_key or "",
                    feed="sip",
                )
                feed_label = "SIP (Consolidated Tape)" if provider_obj.is_feed_consolidated else "IEX (Free Tier — Degraded)"
                st.info(f"Using **Alpaca Provider** with configured feed: **{feed_label}**.")
        else:
            st.info(
                "Using **Deterministic Mock Provider** (offline simulated market universe with qualifying candidates, "
                "ties, technical filters, and Doji handling for testing)."
            )
            provider_obj = MockORBProvider()

        # Notice on Schwab limitation if Schwab is active in main app settings
        if settings.data.data_provider == "schwab":
            with st.expander("ℹ️ Note on Schwab Provider for Broad-Market Scanning", expanded=False):
                st.markdown(
                    "Schwab is currently configured as your primary TradeX OHLCV provider. "
                    "However, the Charles Schwab API does not offer a universe discovery endpoint and restricts "
                    "price history to single-symbol requests with a 120 calls/minute rate limit. "
                    "A broad-market scan of ~8,000 securities would take >66 minutes. "
                    "Alpaca is TradeX's supported multi-symbol discovery provider."
                )

        # Trigger Scan Button
        scan_clicked = st.button("🔍 Scan Market", type="primary", use_container_width=True)

        # Session state persistence for scan result
        if "orb_market_scan_result" not in st.session_state:
            st.session_state["orb_market_scan_result"] = None

        if scan_clicked:
            if provider_obj is None:
                st.error("Cannot start scan: provider is not configured.")
                return

            status_container = st.empty()
            with st.spinner("Executing market-wide ORB scan..."):
                def _ui_progress(p: ScanProgress) -> None:
                    status_container.info(f"⏳ **{p.stage.value}**: {p.message}")

                try:
                    scan_result = run_market_scan(
                        provider=provider_obj,
                        progress_callback=_ui_progress,
                        top_n=20,
                    )
                    st.session_state["orb_market_scan_result"] = scan_result
                    status_container.success("✅ Market scan completed successfully.")
                except ORBProviderConfigurationError as err:
                    st.session_state["orb_market_scan_result"] = None
                    status_container.error(f"Configuration error: {err}")
                    return
                except (ORBProviderError, RuntimeError, OSError) as err:
                    st.session_state["orb_market_scan_result"] = None
                    status_container.error(f"Scan failed: {err}")
                    return

        scan_result = st.session_state["orb_market_scan_result"]
        if scan_result is None:
            st.info("Click **Scan Market** above to initiate automatic opportunity discovery across U.S. equities.")
            return

        # Provenance and Coverage Metrics
        st.markdown("#### Market Scan Provenance & Coverage")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Session Date", scan_result.session_date.isoformat())
        with col2:
            st.metric("As-Of Time (ET)", scan_result.as_of_time_et.strftime("%H:%M:%S %Z"))
        with col3:
            st.metric("Discovered", f"{scan_result.universe_size_discovered:,}")
        with col4:
            st.metric("Evaluated", f"{scan_result.securities_evaluated:,}")
        with col5:
            st.metric("Eligible", f"{scan_result.eligible_candidates_count:,}")

        # Feed & Coverage Disclosure Notice
        if not scan_result.is_feed_consolidated:
            st.warning(f"⚠️ **{scan_result.coverage_warning}**")
        else:
            st.info(f"ℹ️ **Universe Coverage Notice ({scan_result.coverage_status}):** {scan_result.coverage_warning}")

        # Time-Gating Check
        if scan_result.is_time_gated:
            st.error(f"🛑 **Time-Gate Blocked:** {scan_result.time_gate_message}")
            st.stop()

        # Candidates Table
        st.markdown(f"#### Top {len(scan_result.candidates)} Ranked Opportunities (as of 09:35 ET)")
        st.caption(
            "Ranked by Relative Volume (RV14) descending, symbol ascending tie-breaker. "
            "Theoretical Stop Offset ($0.10 \\times \\text{ATR14}$) anchors to the future execution fill, "
            "not a promised or prefilled price."
        )
        _render_candidates_table(scan_result.candidates)

        # Exclusions View
        _render_exclusions_audit(scan_result.exclusions)
        return

    # ══════════════════════════════════════════════════════════════════════════════
    # MODE 2: SYNTHETIC DEMO SNAPSHOT
    # ══════════════════════════════════════════════════════════════════════════════
    snapshot: ORBSnapshot | None = None

    if input_source == "Synthetic Demo Snapshot":
        st.info(
            "Using built-in **Synthetic Demo Snapshot** (33 synthetic securities, session 2024-01-02 09:35 ET). "
            "Includes qualifying Long, Short, and Doji candidates, ties, technical filter rejections, "
            "missing data, and corrupt entries for deterministic testing."
        )
        try:
            snapshot = create_demo_snapshot()
        except (ValueError, TypeError, KeyError, RuntimeError, OSError) as err:
            st.error(f"Failed to load synthetic demo snapshot: {err}")
            return
    else:
        st.caption(
            "Upload an explicit in-memory JSON snapshot file (maximum 5 MB). "
            "No data is saved to disk, logged, or sent over the network."
        )
        uploaded_file = st.file_uploader(
            "Upload Snapshot JSON",
            type=["json"],
            help="Select a valid JSON snapshot containing session_date, as_of_time, source metadata, and symbol payloads.",
        )

        if uploaded_file is not None:
            file_bytes = uploaded_file.getvalue()
            if len(file_bytes) > MAX_SNAPSHOT_BYTES:
                st.error(
                    f"Uploaded file size ({len(file_bytes):,} bytes) exceeds the 5 MB limit ({MAX_SNAPSHOT_BYTES:,} bytes)."
                )
                return
            try:
                parsed_snap = parse_snapshot_json(file_bytes)
                if parsed_snap.source_type != "user_provided_unverified":
                    parsed_snap = replace(
                        parsed_snap,
                        source_type="user_provided_unverified",
                        source_label=(
                            f"{parsed_snap.source_label} (unverified upload)"
                            if parsed_snap.source_label
                            else "User upload (unverified)"
                        ),
                    )
                snapshot = parsed_snap
                as_of_ny = snapshot.as_of_time.astimezone(MARKET_TIMEZONE)
                st.success(
                    f"Successfully parsed snapshot: {len(snapshot.symbols)} symbols as of "
                    f"{snapshot.session_date.isoformat()} {as_of_ny.strftime('%H:%M:%S %Z')}."
                )
            except SnapshotValidationError as err:
                st.error(f"Snapshot Validation Error: {err}")
                return
            except (ValueError, TypeError, KeyError, RuntimeError, OSError) as err:
                st.error(f"Failed to parse uploaded snapshot JSON: {err}")
                return
        else:
            st.info("Please upload a snapshot JSON file to preview candidates.")
            return

    if snapshot is None:
        return

    # Generate Candidate Preview
    preview_result: ORBCandidatePreviewResult = generate_orb_candidate_preview(snapshot)

    # Metadata & Coverage Summary
    st.markdown("#### Snapshot Provenance & Coverage")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Session Date", preview_result.session_date.isoformat())
    with col2:
        st.metric("As-Of Time (ET)", preview_result.as_of_time_et.strftime("%H:%M:%S %Z"))
    with col3:
        st.metric("Source Type", preview_result.source_type)
    with col4:
        st.metric("Constituents Provided", preview_result.universe_coverage.provided_count)

    # Universe coverage notice
    st.warning(
        f"⚠️ **Universe Coverage Notice ({preview_result.universe_coverage.completeness_status}):** "
        f"{preview_result.universe_coverage.completeness_warning}"
    )

    # Time-Gating Check
    if preview_result.is_time_gated:
        st.error(f"🛑 **Time-Gate Blocked:** {preview_result.time_gate_message}")
        st.stop()

    # Candidates Table
    st.markdown(
        f"#### Top {len(preview_result.candidates)} Ranked Candidates (as of 09:35 ET)"
    )
    st.caption(
        "Ranked by Relative Volume (RV14) descending, symbol ascending tie-breaker. "
        "Theoretical Stop Offset ($0.10 \\times \\text{ATR14}$) anchors to the future execution fill, "
        "not a promised or prefilled price."
    )
    _render_candidates_table(preview_result.candidates)

    # Exclusions Audit
    _render_exclusions_audit(preview_result.exclusions)
