"""ORB Candidate Preview UI tab renderer (DAYTRADE-003E-ORB-PREVIEW-001).

Nested inside Research Lab as an explicitly non-actionable, read-only research tool:
- Displays point-in-time ORB candidate setups as of 09:35 ET.
- Enforces time-gating (blocks ranking if as-of time is before 09:35 ET).
- Reuses existing technical indicator and ranking functions.
- Provides synthetic demo data or in-memory JSON file upload (<=5 MB limit).
- Discloses coverage limitations: ranks solely within provided inputs, NOT full-market Top-20.
- Shows prospective stop-entry trigger and theoretical stop offset (0.10 * ATR14) without
  fabricating executed fills, definitive stop prices, win rates, P&L, or broker actions.
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd
import streamlit as st

from tradex.config import TradeXSettings
from tradex.research.daytrade_orb.demo_fixture import create_demo_snapshot
from tradex.research.daytrade_orb.preview import (
    RESEARCH_PREVIEW_DISCLAIMER,
    ExclusionCategory,
    generate_orb_candidate_preview,
)
from tradex.research.daytrade_orb.snapshot import (
    MARKET_TIMEZONE,
    MAX_SNAPSHOT_BYTES,
    ORBSnapshot,
    SnapshotValidationError,
    parse_snapshot_json,
)


def render_orb_preview_tab(
    *,
    settings: TradeXSettings,
) -> None:
    """Render the ORB Candidate Preview nested tab inside Research Lab."""
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
            2. **Universe Scope:** This preview ranks candidate setups **strictly among the uploaded or demo constituent set**. It must **never** be labeled the source paper's full-market Top-20 (~7,000 U.S. equities) unless full-market PIT data is independently established.
            3. **09:35 ET Time-Gate:** Ranking requires complete 09:30–09:34 ET regular-session bars and strictly prior daily bars (D-1 and older). Ranking is blocked before 09:35:00 ET.
            4. **No Execution Fills or Pre-filled Stops:** Prospective stop-entry triggers represent the opening-range boundary (OR High for LONG, OR Low for SHORT). The protective-stop offset is **theoretical ($0.10 \\times \\text{ATR14}$)** and anchors to the **future executed fill**, which does not exist at 09:35 ET.
            5. **Doji Invariant:** Doji opening ranges produce `NO_ORDER` and are **not** backfilled with rank #21.
            6. **Zero Side-Effects:** No network calls, secrets, live broker orders, persistence writes, or automated alerts are triggered.
            """
        )

    # Ingestion Source Selector
    st.markdown("#### Snapshot Data Input")
    input_source = st.radio(
        "Select Snapshot Input Source",
        options=["Synthetic Demo Snapshot", "Upload Custom Snapshot JSON"],
        index=0,
        horizontal=True,
        help="Choose between the built-in 33-symbol synthetic research fixture or upload an in-memory JSON snapshot.",
    )

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
                # User-uploaded files must never present source_type='synthetic_demo' as trusted provenance;
                # mark all uploads as user_provided_unverified.
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
    preview_result = generate_orb_candidate_preview(snapshot)

    # ══════════════════════════════════════════════════════════════════════════════
    # METADATA & COVERAGE SUMMARY
    # ══════════════════════════════════════════════════════════════════════════════
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

    # Universe coverage and completeness disclosure (unconditionally rendered)
    st.warning(
        f"⚠️ **Universe Coverage Notice ({preview_result.universe_coverage.completeness_status}):** "
        f"{preview_result.universe_coverage.completeness_warning}"
    )

    # ══════════════════════════════════════════════════════════════════════════════
    # TIME-GATING CHECK
    # ══════════════════════════════════════════════════════════════════════════════
    if preview_result.is_time_gated:
        st.error(f"🛑 **Time-Gate Blocked:** {preview_result.time_gate_message}")
        st.stop()

    # ══════════════════════════════════════════════════════════════════════════════
    # TOP-20 CANDIDATES TABLE
    # ══════════════════════════════════════════════════════════════════════════════
    st.markdown(
        f"#### Top {len(preview_result.candidates)} Ranked Candidates (as of 09:35 ET)"
    )
    st.caption(
        "Ranked by Relative Volume (RV14) descending, symbol ascending tie-breaker. "
        "Theoretical Stop Offset ($0.10 \\times \\text{ATR14}$) anchors to the future execution fill, "
        "not a promised or prefilled price."
    )

    if not preview_result.candidates:
        st.info("No candidates met the eligibility filters (Price > $5, ADV14 >= 1M, ATR14 > $0.50, RV14 >= 1.0).")
    else:
        table_rows = []
        for c in preview_result.candidates:
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

    # ══════════════════════════════════════════════════════════════════════════════
    # EXCLUSIONS & AUDIT EXPANDER
    # ══════════════════════════════════════════════════════════════════════════════
    st.markdown("#### Candidate Exclusions & Data Quality Audit")
    num_tech = sum(1 for e in preview_result.exclusions if e.category == ExclusionCategory.TECHNICAL_FILTER)
    num_unav = sum(1 for e in preview_result.exclusions if e.category == ExclusionCategory.DATA_UNAVAILABLE)
    num_block = sum(1 for e in preview_result.exclusions if e.category == ExclusionCategory.INTEGRITY_BLOCKED)

    with st.expander(
        f"Exclusions and Blocked Constituents ({len(preview_result.exclusions)} total: "
        f"{num_tech} filter/cutoff, {num_unav} unavailable, {num_block} integrity blocked)",
        expanded=False,
    ):
        if not preview_result.exclusions:
            st.write("No symbols were excluded.")
        else:
            ex_rows = [
                {
                    "Symbol": e.symbol,
                    "Category": e.category.value,
                    "Reason": e.reason,
                }
                for e in preview_result.exclusions
            ]
            df_exclusions = pd.DataFrame(ex_rows)
            st.dataframe(df_exclusions, use_container_width=True, hide_index=True)
