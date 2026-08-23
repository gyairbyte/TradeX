"""Today — Market Observations Streamlit tab renderer (MVP-ARCH-001-R5C).

Provides a truthful, read-only landing surface for point-in-time candidate snapshots
and an in-place Candidate Detail drill-down. Makes zero provider/network calls and
performs zero candidate writes.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st

from tradex.candidates.queries import (
    TodayCandidateRow,
    _format_market_time,
    get_available_trading_dates,
    get_candidate_history_for_symbol,
    get_latest_candidates_for_date,
    get_today_summary_facts,
)
from tradex.candidates.store import get_candidate_dossier
from tradex.tracker.store import StoreError
from tradex.ui.evidence import render_evidence_notice

if TYPE_CHECKING:
    from tradex.candidates.models import CandidateDossier
    from tradex.config import TradeXSettings


def _format_date_label(date_str: str | None) -> str:
    """Format YYYY-MM-DD trading date string to human-readable date."""
    if not date_str:
        return "Unknown"
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        return dt.strftime("%A, %b %d, %Y")
    except (ValueError, TypeError):
        return date_str


def render_today_tab(*, settings: TradeXSettings) -> None:
    """Render the Today — Market Observations top-level surface with in-place detail drill-down."""
    selected_candidate_id = st.session_state.get("today_selected_candidate_id")

    if selected_candidate_id:
        _render_candidate_detail(selected_candidate_id, settings=settings)
    else:
        _render_today_overview(settings=settings)


def _render_today_overview(*, settings: TradeXSettings) -> None:
    """Render the default Today overview table and filters."""
    st.subheader("Today — Market Observations")
    render_evidence_notice("today", st_module=st)
    st.caption(
        "Read-only point-in-time observations captured by TradeX. "
        "Legacy scanner classifications are heuristic research inputs, not validated trade recommendations."
    )

    try:
        available_dates = get_available_trading_dates(settings=settings)
    except StoreError as err:
        st.error(f"Failed to read market observation history from database: {err}")
        return

    if not available_dates:
        st.info(
            "No market-observation snapshots have been captured yet. "
            "Today will populate after scorable scan observations are prospectively recorded."
        )
        return

    # Date selector — default is most recent persisted trading date (index 0)
    col_date, col_facts = st.columns([1, 2])
    with col_date:
        selected_date = st.selectbox(
            "Captured Trading Date",
            options=available_dates,
            index=0,
            key="today_date_select",
            help="Select which persisted market-observation trading date to view.",
        )

    # Summary facts for selected date
    summary = get_today_summary_facts(selected_date, settings=settings)
    with col_facts:
        date_formatted = _format_date_label(selected_date)
        last_snap_time = summary.formatted_last_snapshot_time
        st.markdown(
            f"**Latest captured trading date:** {date_formatted}  \n"
            f"**Last captured snapshot:** {last_snap_time}"
        )

    try:
        candidates = get_latest_candidates_for_date(selected_date, settings=settings)
    except StoreError as err:
        st.error(f"Failed to load candidate observations for date '{selected_date}': {err}")
        return

    if not candidates:
        st.info(f"No market-observation snapshots were captured for trading date {selected_date}.")
        return

    # ── Minimal MVP Filters ───────────────────────────────────────────────────
    with st.expander("🔍 Filter Observations", expanded=True):
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)

        with col_f1:
            search_query = st.text_input(
                "Search Symbol",
                key="today_filter_symbol",
                placeholder="e.g. AAPL, NVDA",
                help="Filter by symbol prefix or exact match.",
            ).strip().upper()

        with col_f2:
            obs_filter_options = [
                "All",
                "Signal (Legacy Heuristic)",
                "Below Threshold (Legacy)",
            ]
            obs_filter = st.selectbox(
                "Legacy Observation",
                obs_filter_options,
                key="today_filter_obs",
                help="Legacy scanner observation state; not a validated trade signal.",
            )

        with col_f3:
            unique_providers = sorted({c.provider for c in candidates})
            prov_filter_options = ["All"] + unique_providers
            prov_filter = st.selectbox(
                "Provider",
                prov_filter_options,
                key="today_filter_prov",
                help="Filter by market-data provider.",
            )

        with col_f4:
            comp_filter_options = ["All", "Complete", "Has missing data"]
            comp_filter = st.selectbox(
                "Data Completeness",
                comp_filter_options,
                key="today_filter_comp",
                help="Filter by data input completeness.",
            )

    # Apply filters deterministically
    filtered: list[TodayCandidateRow] = []
    for c in candidates:
        if search_query and search_query not in c.symbol:
            continue
        if obs_filter != "All" and c.legacy_observation_label != obs_filter:
            continue
        if prov_filter != "All" and c.provider != prov_filter:
            continue
        if comp_filter == "Complete" and c.missing_count > 0:
            continue
        if comp_filter == "Has missing data" and c.missing_count == 0:
            continue
        filtered.append(c)

    if not filtered:
        st.warning("No market observations match the current filter selection.")
        return

    # ── Primary Table Rendering ───────────────────────────────────────────────
    st.markdown(f"**Showing {len(filtered)} of {len(candidates)} market observations:**")

    # Build clean presentation dataframe (strictly excluding legacy score, RSI, vol ratio, earnings, ranking)
    table_rows = [
        {
            "Symbol": r.symbol,
            "Legacy Observation": r.legacy_observation_label,
            "Observed": r.observed_time_et,
            "Observed Close": r.formatted_close,
            "Provider": r.provider_display,
            "Data Completeness": r.data_completeness,
            "Snapshots": r.snapshot_count,
        }
        for r in filtered
    ]
    df_display = pd.DataFrame(table_rows)

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Symbol": st.column_config.TextColumn("Symbol", help="Ticker symbol observed."),
            "Legacy Observation": st.column_config.TextColumn(
                "Legacy Observation",
                help="Legacy scanner observation state; not a validated trade signal.",
            ),
            "Observed": st.column_config.TextColumn(
                "Observed",
                help="Point-in-time timestamp of observation in America/New_York (ET).",
            ),
            "Observed Close": st.column_config.TextColumn(
                "Observed Close",
                help="Observed close price at decision time.",
            ),
            "Provider": st.column_config.TextColumn(
                "Provider",
                help="Persisted market-data provider provenance.",
            ),
            "Data Completeness": st.column_config.TextColumn(
                "Data Completeness",
                help="Completeness of expected technical inputs.",
            ),
            "Snapshots": st.column_config.NumberColumn(
                "Snapshots",
                help="Total point-in-time snapshots captured for this symbol on this date.",
            ),
        },
    )

    # Interactive candidate drilldown selection
    st.markdown("---")
    st.markdown("#### 🔍 Inspect Candidate Detail")
    col_sel, col_btn = st.columns([3, 1])
    with col_sel:
        cand_map = {f"{r.symbol} ({r.legacy_observation_label}) · {r.observed_time_et}": r.candidate_id for r in filtered}
        chosen_label = st.selectbox(
            "Select observation to drill down:",
            options=list(cand_map.keys()),
            key="today_drilldown_picker",
            help="Select an observation to view complete point-in-time evidence and snapshot history.",
        )
    with col_btn:
        st.write("")  # align vertically
        if st.button("View Detail", key="btn_view_candidate_detail", type="primary", use_container_width=True):
            cand_id = cand_map[chosen_label]
            st.session_state["today_selected_candidate_id"] = cand_id
            st.rerun()


def _render_candidate_detail(candidate_id: str, *, settings: TradeXSettings) -> None:
    """Render the in-place Candidate Detail drill-down view."""
    # ── Back Navigation ───────────────────────────────────────────────────────
    if st.button("← Back to Today", key="btn_back_to_today"):
        st.session_state["today_selected_candidate_id"] = None
        st.rerun()
        return

    dossier: CandidateDossier | None = None
    try:
        dossier = get_candidate_dossier(candidate_id, settings=settings)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to load candidate detail from database: {exc}")
        return

    if dossier is None:
        st.error(f"Candidate detail record '{candidate_id}' not found.")
        return

    snap = dossier.snapshot
    screener_ev = next((ev for ev in dossier.evidence if ev.evidence_type == "screener_observation"), None)
    screener_meta = screener_ev.metadata if screener_ev else {}
    shadow_eval = next((e for e in dossier.evaluations if e.evaluator_id == "shadow_observation_evaluator"), None)
    dimensions = shadow_eval.dimensions if shadow_eval else {}
    data_conf = dimensions.get("data_confidence", {}) if isinstance(dimensions, dict) else {}
    context_dim = dimensions.get("context", {}) if isinstance(dimensions, dict) else {}

    obs_time_et = _format_market_time(snap.decision_timestamp, include_date=True)
    status_raw = screener_meta.get("observation_status") or "unknown"
    status_label = (
        "Signal (Legacy Heuristic)"
        if status_raw.lower() == "signal"
        else (
            "Below Threshold (Legacy)"
            if status_raw.lower() == "below_threshold"
            else status_raw.replace("_", " ").title()
        )
    )

    fallback_used = bool(data_conf.get("fallback_used", False))
    actual_provider = str(data_conf.get("actual_provider") or (screener_ev.provider if screener_ev else "unknown"))
    provider_display = f"{actual_provider} · Fallback" if fallback_used else actual_provider

    # ── 1. Header / Status ────────────────────────────────────────────────────
    st.subheader(f"Candidate Detail — {snap.symbol}")
    st.info("Point-in-time research observation. TradeX currently has no production-approved actionable strategy.")

    st.markdown(
        f"**Symbol:** `{snap.symbol}`  ·  "
        f"**Observed:** `{obs_time_et}`  ·  "
        f"**Status:** `{status_label}`  ·  "
        f"**Evidence State:** `exploratory`  ·  "
        f"**Provider:** `{provider_display}`"
    )

    # ── 2. Snapshot Summary ───────────────────────────────────────────────────
    st.markdown("### Snapshot Summary")
    c1, c2, c3, c4, c5 = st.columns(5)

    close_val = screener_meta.get("last_close")
    c1.metric("Observed Close", f"${float(close_val):.2f}" if close_val is not None else "—")

    vol_val = screener_meta.get("volume_ratio")
    c2.metric("Volume Ratio", f"{float(vol_val):.2f}x" if vol_val is not None else "—")

    rsi_val = screener_meta.get("rsi")
    c3.metric("RSI", f"{float(rsi_val):.1f}" if rsi_val is not None else "—")

    er_val = screener_meta.get("days_until_earnings")
    c4.metric("Earnings In", f"{int(er_val)} d" if er_val is not None else "Unavailable")

    timeframe_val = screener_meta.get("timeframe", "intraday")
    c5.metric("Timeframe", str(timeframe_val).capitalize())

    # ── 3. Legacy Scanner Evidence ────────────────────────────────────────────
    st.markdown("### Legacy Scanner Evidence")
    score_val = screener_meta.get("legacy_heuristic_score")
    st.markdown(
        f"**Legacy Scanner Score:** `{score_val if score_val is not None else '—'} / 100`  \n"
        "*Unvalidated heuristic discovery score. Not a probability, expected return, or approved trade ranking.*"
    )

    reasons_str = screener_meta.get("reasons")
    if reasons_str:
        st.markdown("**Captured Scanner Reason Strings:**")
        reason_list = [r.strip() for r in str(reasons_str).split("|") if r.strip()]
        for r in reason_list:
            st.markdown(f"- {r}")
    else:
        st.caption("No scanner reason strings recorded on this observation.")

    # ── 4. Descriptive Context ────────────────────────────────────────────────
    st.markdown("### Descriptive Context")
    if context_dim:
        ctx_df = pd.DataFrame(
            [
                {"Context Fact": k.replace("_", " ").title(), "Persisted Value": str(v)}
                for k, v in context_dim.items()
            ]
        )
        st.dataframe(ctx_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No descriptive context recorded.")

    # ── 5. Data Confidence / Completeness ─────────────────────────────────────
    st.markdown("### Data Confidence & Provenance")
    req_prov = data_conf.get("requested_provider", actual_provider)
    missing_count = len(dossier.missing_data)

    cd1, cd2, cd3, cd4 = st.columns(4)
    cd1.metric("Requested Provider", str(req_prov))
    cd2.metric("Actual Provider", str(actual_provider))
    cd3.metric("Fallback Used", "Yes" if fallback_used else "No")
    cd4.metric("Missing Inputs", str(missing_count))

    # ── 6. Missing Data Records ───────────────────────────────────────────────
    st.markdown("### Missing Data Records")
    if dossier.missing_data:
        missing_rows = [
            {
                "Input Name": m.input_name,
                "Data Family": m.data_family,
                "Status": str(m.status.value if hasattr(m.status, "value") else m.status),
                "Detail": m.detail or "—",
                "Provider": m.provider or "—",
                "Observed At (ET)": _format_market_time(m.observed_at),
            }
            for m in dossier.missing_data
        ]
        st.dataframe(pd.DataFrame(missing_rows), use_container_width=True, hide_index=True)
    else:
        st.success("All expected technical inputs complete. Zero missing inputs recorded.")

    # ── 7. Snapshot History ───────────────────────────────────────────────────
    st.markdown(f"### Snapshot History for {snap.symbol} ({snap.trading_date or 'Selected Date'})")
    if snap.trading_date:
        try:
            history = get_candidate_history_for_symbol(snap.symbol, snap.trading_date, settings=settings)
            if history:
                hist_rows = [
                    {
                        "Observed": h.observed_time_et,
                        "Legacy Observation": h.legacy_observation_label,
                        "Observed Close": h.formatted_close,
                        "Legacy Scanner Score": h.formatted_score,
                        "Volume Ratio": h.formatted_volume_ratio,
                        "RSI": h.formatted_rsi,
                        "Provider": h.provider_display,
                        "Data Completeness": h.data_completeness,
                    }
                    for h in history
                ]
                st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No prior snapshots found.")
        except StoreError as err:
            st.error(f"Failed to query snapshot history: {err}")
    else:
        st.caption("Snapshot has no assigned trading date; history unavailable.")

    # ── 8. Audit & Technical Details (Collapsed by default) ───────────────────
    with st.expander("🛠️ Audit & Technical Details", expanded=False):
        st.markdown(f"**Candidate ID:** `{snap.candidate_id}`")
        st.markdown(f"**Contract Version:** `{snap.contract_version}`")
        st.markdown(f"**Trading Date:** `{snap.trading_date or 'NULL'}`")
        st.markdown(f"**Decision Timestamp (UTC):** `{snap.decision_timestamp.isoformat()}`")
        st.markdown(f"**Created At (UTC):** `{snap.created_at.isoformat()}`")

        if screener_ev:
            st.markdown(f"**Source Ref Type:** `{screener_ev.source_ref_type}`")
            st.markdown(f"**Source Ref ID (Scan Session):** `{screener_ev.source_ref_id}`")
            st.markdown(f"**Evidence ID:** `{screener_ev.evidence_id}`")

        if shadow_eval:
            st.markdown(f"**Evaluator ID:** `{shadow_eval.evaluator_id}`")
            st.markdown(f"**Evaluator Version:** `{shadow_eval.evaluator_version}`")
            st.markdown(f"**Evidence State:** `{shadow_eval.evidence_state}`")
            st.markdown("**Dimensions JSON:**")
            st.json(shadow_eval.dimensions)

        if dossier.reasons:
            st.markdown("**Evaluator Reasons:**")
            reasons_table = [
                {
                    "Reason Code": r.reason_code,
                    "Dimension": str(r.dimension.value if hasattr(r.dimension, "value") else r.dimension),
                    "Polarity": str(r.polarity.value if hasattr(r.polarity, "value") else r.polarity),
                    "Severity": str(r.severity.value if hasattr(r.severity, "value") else r.severity),
                    "Human Text": r.human_text,
                }
                for r in dossier.reasons
            ]
            st.dataframe(pd.DataFrame(reasons_table), use_container_width=True, hide_index=True)
