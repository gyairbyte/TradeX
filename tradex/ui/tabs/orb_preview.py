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

import logging
from dataclasses import replace
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from tradex.config import TradeXSettings
from tradex.market.hours import (
    MARKET_TIMEZONE,
    is_trading_day,
    previous_trading_session,
)
from tradex.research.daytrade_orb.demo_fixture import (
    DEMO_AS_OF_TIME,
    DEMO_SESSION_DATE,
    create_demo_snapshot,
)
from tradex.research.daytrade_orb.preparation import (
    CacheValidationResult,
    PreparationProgress,
    PreparationStatus,
    inspect_cache_status,
    prepare_market,
)
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

logger = logging.getLogger(__name__)


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
                feed_choice = st.radio(
                    "Market Data Feed Selection",
                    options=[
                        "Consolidated Tape (SIP) — Published Strategy Requirement",
                        "IEX Free-Tier Feed (Provisional Heuristic Only)",
                    ],
                    index=0,
                    horizontal=True,
                    help="SIP delivers 100% tape volume. IEX covers ~2% tape and yields provisional heuristic rankings.",
                )
                selected_feed = "sip" if "SIP" in feed_choice else "iex"
                provider_obj = AlpacaORBProvider(
                    api_key=settings.data.alpaca_api_key or "",
                    secret_key=settings.data.alpaca_secret_key or "",
                    feed=selected_feed,
                )
                feed_label = "SIP (Consolidated Tape)" if provider_obj.is_feed_consolidated else "IEX (Free Tier — Provisional)"
                st.info(f"Using **Alpaca Provider** with explicitly selected feed: **{feed_label}**.")
        else:
            st.info(
                "Using **Deterministic Mock Provider** (seeded with the 33-symbol simulated market universe "
                "with qualifying Long, Short, and Doji candidates, ties, and technical filter exclusions)."
            )
            provider_obj = MockORBProvider.create_populated()

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

        is_mock_provider = isinstance(provider_obj, MockORBProvider)
        is_market_session = True
        if is_mock_provider:
            target_date = DEMO_SESSION_DATE
        else:
            now_ny = datetime.now(MARKET_TIMEZONE)
            today_date = now_ny.date()
            is_market_session = is_trading_day(today_date)
            if is_market_session:
                target_date = today_date
            else:
                prev_sess = previous_trading_session(today_date)
                target_date = prev_sess.session_date

        cache_dir = settings.paths.orb_cache_dir.expanduser()
        cache_status_info = None
        if provider_obj is not None:
            try:
                cache_status_info = inspect_cache_status(
                    target_session=target_date,
                    provider=provider_obj.provider_name,
                    feed=provider_obj.feed_name,
                    cache_dir=cache_dir,
                )
            except Exception as err:
                logger.exception("Failed to inspect cache status for session %s", target_date)
                cache_status_info = CacheValidationResult(
                    is_valid=False,
                    status=PreparationStatus.FAILED,
                    reason=f"Cached snapshot file could not be read or is corrupted: {err}",
                    snapshot=None,
                )

        if not is_mock_provider and not is_market_session:
            st.info(
                f"ℹ️ **Market Closed Today ({today_date.isoformat()})**: Market preparation is only permitted on regular "
                f"XNYS trading sessions before market open. Currently viewing last regular session ({target_date.isoformat()}) "
                f"for scanning and historical analysis."
            )

        # Market Preparation Status & Metadata Card
        st.markdown("##### Market Preparation & Cache Status")
        prep_col1, prep_col2, prep_col3, prep_col4 = st.columns(4)
        with prep_col1:
            st.metric("Target Session Date", target_date.isoformat())
        with prep_col2:
            prep_status_label = cache_status_info.status.value if cache_status_info else "NOT_PREPARED"
            st.metric("Prep Status", prep_status_label)
        with prep_col3:
            if cache_status_info and cache_status_info.snapshot and cache_status_info.snapshot.completed_at_et:
                try:
                    prep_ts = datetime.fromisoformat(cache_status_info.snapshot.completed_at_et).strftime("%H:%M:%S %Z")
                except ValueError:
                    prep_ts = "Recorded"
            else:
                prep_ts = "None"
            st.metric("Prepared At", prep_ts)
        with prep_col4:
            if cache_status_info and cache_status_info.snapshot:
                qual_count = len(cache_status_info.snapshot.daily_eligible_symbols)
                total_disc = cache_status_info.snapshot.universe_size_discovered
                elig_str = f"{qual_count:,} / {total_disc:,}"
            else:
                elig_str = "0"
            st.metric("Eligible / Discovered", elig_str)

        if cache_status_info:
            if cache_status_info.is_valid:
                if cache_status_info.status == PreparationStatus.READY:
                    st.success(f"🟢 **Ready (Full Market Preparation)**: {cache_status_info.reason}")
                else:
                    st.warning(f"🟠 **Partial (Provisional Preparation)**: {cache_status_info.reason}")
            elif cache_status_info.status == PreparationStatus.STALE:
                st.warning(f"⚠️ **Stale Preparation**: {cache_status_info.reason} Click **Prepare Market** below to update.")
            elif cache_status_info.status == PreparationStatus.FAILED:
                st.error(f"🔴 **Preparation Failed / Corrupt**: {cache_status_info.reason}")
            else:
                st.info("⚪ **Not Prepared**: Click **Prepare Market** before market open (e.g. 8:00 AM ET) to pre-calculate historical indicators.")

        # Action Buttons: Prepare Market and Scan Market
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            prep_btn_help = (
                "Prepare market universe, daily metrics, and opening-range volume baselines before market open."
                if (is_mock_provider or is_market_session)
                else f"Market preparation is disabled on non-trading days ({today_date.isoformat()})."
            )
            prepare_clicked = st.button(
                "🛠️ Prepare Market",
                disabled=not (is_mock_provider or is_market_session),
                help=prep_btn_help,
                use_container_width=True,
            )
        with btn_col2:
            scan_clicked = st.button("🔍 Scan Market", type="primary", use_container_width=True)

        # Session state persistence
        if "orb_market_prep_result" not in st.session_state:
            st.session_state["orb_market_prep_result"] = None
        if "orb_market_scan_result" not in st.session_state:
            st.session_state["orb_market_scan_result"] = None

        if prepare_clicked and not scan_clicked:
            if provider_obj is None:
                st.error("Cannot prepare market: provider is not configured.")
                return

            prep_status_container = st.empty()
            if not is_mock_provider and not is_market_session:
                prep_status_container.error(
                    f"Market preparation cannot be executed on non-trading days ({today_date.isoformat()}). "
                    "Preparation is only valid on regular XNYS trading days before market open."
                )
                return

            with st.spinner("Executing market preparation (historical data & indicators)..."):
                def _ui_prep_progress(p: PreparationProgress) -> None:
                    prep_status_container.info(f"⏳ **{p.stage.value}**: {p.message}")

                try:
                    prep_session_date = DEMO_SESSION_DATE if is_mock_provider else today_date
                    prep_as_of_time = DEMO_AS_OF_TIME if is_mock_provider else None

                    prep_result = prepare_market(
                        provider=provider_obj,
                        session_date=prep_session_date,
                        as_of_time=prep_as_of_time,
                        progress_callback=_ui_prep_progress,
                        cache_dir=cache_dir,
                        settings=settings,
                    )
                    st.session_state["orb_market_prep_result"] = prep_result
                    if prep_result.status == PreparationStatus.READY:
                        prep_status_container.success(
                            f"✅ Market preparation completed successfully! Pre-screened {prep_result.daily_eligible_count:,} "
                            f"eligible candidates out of {prep_result.universe_size_discovered:,} discovered equities. "
                            f"Snapshot saved to `{prep_result.artifact_path.name if prep_result.artifact_path else 'cache'}`."
                        )
                    elif prep_result.status == PreparationStatus.PARTIAL:
                        prep_status_container.warning(
                            f"⚠️ Market preparation completed with provisional coverage: {prep_result.coverage_warning}"
                        )
                    else:
                        prep_status_container.error(
                            f"❌ Market preparation failed: {prep_result.error_message or prep_result.coverage_warning}"
                        )
                except ORBProviderConfigurationError as err:
                    st.session_state["orb_market_prep_result"] = None
                    prep_status_container.error(f"Configuration error: {err}")
                    return
                except (ORBProviderError, RuntimeError, OSError) as err:
                    st.session_state["orb_market_prep_result"] = None
                    prep_status_container.error(f"Preparation failed: {err}")
                    return

        elif scan_clicked:
            if provider_obj is None:
                st.error("Cannot start scan: provider is not configured.")
                return

            status_container = st.empty()
            with st.spinner("Executing market-wide ORB scan..."):
                def _ui_progress(p: ScanProgress) -> None:
                    status_container.info(f"⏳ **{p.stage.value}**: {p.message}")

                try:
                    scan_session_date = DEMO_SESSION_DATE if is_mock_provider else target_date
                    scan_as_of_time = DEMO_AS_OF_TIME if is_mock_provider else None

                    scan_result = run_market_scan(
                        provider=provider_obj,
                        session_date=scan_session_date,
                        as_of_time=scan_as_of_time,
                        progress_callback=_ui_progress,
                        top_n=20,
                        use_cache=True,
                        cache_dir=cache_dir,
                    )
                    st.session_state["orb_market_scan_result"] = scan_result
                    if scan_result.coverage_status == "synthetic_demo":
                        status_container.info("🧪 Historical synthetic demo scan evaluated successfully using 2024-01-02 fixture.")
                    elif scan_result.coverage_status == "full_market_sip":
                        status_container.success("✅ Market scan completed successfully with full-market consolidated SIP coverage.")
                    elif scan_result.coverage_status == "provisional_iex":
                        status_container.warning("⚠️ Market scan completed with provisional IEX coverage (~2% volume).")
                    elif scan_result.coverage_status == "provisional_incomplete":
                        status_container.warning("⚠️ Market scan completed with provisional coverage due to material data gaps.")
                    elif scan_result.coverage_status == "failed":
                        status_container.error(f"❌ Market scan failed: {scan_result.coverage_warning}")
                    elif scan_result.coverage_status == "time_gated":
                        status_container.error(f"🛑 Time-Gate Blocked: {scan_result.time_gate_message}")
                    else:
                        status_container.info(f"Scan completed: {scan_result.coverage_warning}")
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
            st.info("Click **Prepare Market** before open, or **Scan Market** to discover ORB opportunities.")
            return

        # Warmed vs Cold Scan Banner
        if scan_result.was_warmed:
            prep_str = scan_result.prep_completed_at_et.strftime('%H:%M:%S %Z') if scan_result.prep_completed_at_et else "cache"
            st.success(
                f"⚡ **Warmed Scan (Zero Historical Provider Calls)**: Loaded valid preparation snapshot from {prep_str}. "
                f"Retrieved session D opening range ({scan_result.securities_evaluated:,} securities evaluated)."
            )
        else:
            st.info(
                f"🐢 **Cold Scan (Live Historical Acquisition)**: {scan_result.cache_message or 'No prepared snapshot used'}. "
                "Retrieved full historical daily bars and prior 14-session opening-range volume baselines."
            )

        # Provenance and Coverage Metrics
        st.markdown("#### Market Scan Provenance & Coverage")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Session Date", scan_result.session_date.isoformat())
        with col2:
            st.metric("As-Of Cutoff", scan_result.as_of_time_et.strftime("%H:%M:%S %Z"))
        with col3:
            st.metric("Discovered", f"{scan_result.universe_size_discovered:,}")
        with col4:
            st.metric("Evaluated Data", f"{scan_result.securities_evaluated:,} ({scan_result.coverage_completeness_pct:.1f}%)")
        with col5:
            st.metric("Eligible Candidates", f"{scan_result.eligible_candidates_count:,}")

        # Scan Execution Timestamps & Window Cutoff
        t_col1, t_col2, t_col3, t_col4 = st.columns(4)
        with t_col1:
            req_str = scan_result.scan_requested_at_et.strftime("%H:%M:%S %Z") if scan_result.scan_requested_at_et else "N/A"
            st.caption(f"**Scan Requested:** {req_str}")
        with t_col2:
            if scan_result.scan_requested_at and scan_result.scan_completed_at:
                elapsed = (scan_result.scan_completed_at - scan_result.scan_requested_at).total_seconds()
                comp_str = f"{scan_result.scan_completed_at_et.strftime('%H:%M:%S %Z')} ({elapsed:.1f}s)"
            elif scan_result.scan_completed_at_et:
                comp_str = scan_result.scan_completed_at_et.strftime("%H:%M:%S %Z")
            else:
                comp_str = "N/A"
            st.caption(f"**Scan Completed:** {comp_str}")
        with t_col3:
            mode_label = "⚡ Warmed (Cache)" if scan_result.was_warmed else "🐢 Cold (Live)"
            st.caption(f"**Scan Path:** {mode_label}")
        with t_col4:
            win_str = scan_result.or_window_end_time_et.strftime("%H:%M:%S %Z") if scan_result.or_window_end_time_et else "09:34:59 ET"
            st.caption(f"**Opening-Range Window End:** {win_str}")

        # Feed & Coverage Disclosure Notice
        if scan_result.coverage_status == "synthetic_demo":
            st.info(f"🧪 **{scan_result.coverage_warning}**")
        elif scan_result.coverage_status in ("provisional_iex", "provisional_incomplete"):
            st.warning(f"⚠️ **{scan_result.coverage_warning}**")
        elif scan_result.coverage_status == "full_market_sip":
            st.info(f"ℹ️ **Universe Coverage Notice ({scan_result.coverage_status}):** {scan_result.coverage_warning}")
        else:
            st.info(f"ℹ️ **Notice ({scan_result.coverage_status}):** {scan_result.coverage_warning}")

        # Time-Gating Check
        if scan_result.is_time_gated:
            st.error(f"🛑 **Time-Gate Blocked:** {scan_result.time_gate_message}")
            st.stop()

        # Candidates Table
        if scan_result.coverage_status == "synthetic_demo":
            status_suffix = " — Historical Synthetic Demo (Simulated Universe)"
        elif scan_result.coverage_status == "full_market_sip":
            status_suffix = " — Authoritative Full-Market SIP"
        elif scan_result.coverage_status == "provisional_iex":
            status_suffix = " — Provisional Rankings (IEX Free Tier)"
        else:
            status_suffix = " — Top 20 of Evaluated Provider Universe (Provisional Rankings)"
        st.markdown(f"#### Top {len(scan_result.candidates)} Ranked Opportunities{status_suffix}")
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
