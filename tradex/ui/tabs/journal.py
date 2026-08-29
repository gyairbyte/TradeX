"""Journal — Executable Strategy Journal Streamlit tab renderer (MVP-ARCH-001-R6-IMPL-B).

Provides a truthful, deterministic, read-only user interface for executable strategy trade plans,
execution records, append-only event logs, and versioned outcomes. Makes zero network or provider calls
and performs zero Journal or Candidate mutations.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st

from tradex.journal.queries import (
    JournalDetailReadModel,
    _format_market_time,
    get_journal_detail,
    get_journal_strategy_ids,
    list_journal_read_models,
)
from tradex.tracker.store import StoreError
from tradex.ui.evidence import render_evidence_notice

if TYPE_CHECKING:
    from tradex.config import TradeXSettings


def render_journal_tab(*, settings: TradeXSettings) -> None:
    """Render the top-level Journal tab with overview and in-place detail drill-down."""
    selected_journal_id = st.session_state.get("journal_selected_id")

    if selected_journal_id:
        _render_journal_detail(selected_journal_id, settings=settings)
    else:
        _render_journal_overview(settings=settings)


def _render_journal_overview(*, settings: TradeXSettings) -> None:
    """Render the primary Journal overview table, filters, and state disclosures."""
    st.subheader("Journal")
    st.caption("Executable Strategy Journal")
    render_evidence_notice("journal", st_module=st)

    try:
        # Check total unfiltered records count first
        all_records = list_journal_read_models(limit=1, settings=settings)
    except StoreError as err:
        st.error(f"Failed to load Journal records from database: {err}")
        return

    # Check active strategies in registry dynamically at call time
    import tradex.strategies.registry as registry_module

    active_authorized_strategies = [
        s
        for s in registry_module.APPROVED_PRODUCTION_STRATEGIES
        if "journal_execution" in s.capabilities
    ]
    has_active_strategy = len(active_authorized_strategies) > 0

    # ── Zero-record states (Case A & Case B) ──────────────────────────────────
    if not all_records:
        if not has_active_strategy:
            # Case A: zero records + no authorized strategy
            st.info(
                "**Executable Strategy Journal**\n\n"
                "No production-approved executable strategy is currently active. "
                "No Journal records exist.\n\n"
                "Legacy scanner outcomes remain available as descriptive telemetry under **Research Lab → Legacy Scanner Telemetry** "
                "and are not actual trade results."
            )
        else:
            # Case B: zero records + an authorized strategy exists
            st.info(
                "**Executable Strategy Journal**\n\n"
                "An executable production strategy is currently authorized, but no Journal records have been recorded yet.\n\n"
                "Persisted trade records will appear here as strategy executions occur."
            )
        return

    # ── Historical Read-Only Mode banner ──────────────────────────────────────
    if not has_active_strategy:
        st.info(
            "ℹ️ **Historical Read-Only Mode:** No production strategy is currently authorized for new Journal execution. "
            "Persisted trade records are displayed for historical audit purposes only."
        )

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.expander("🔍 Filter Journal Trades", expanded=True):
        col_f1, col_f2, col_f3 = st.columns(3)

        with col_f1:
            search_symbol = st.text_input(
                "Search Symbol",
                key="journal_filter_symbol",
                placeholder="e.g. AAPL, NVDA",
                help="Filter by symbol prefix or exact match.",
            ).strip().upper()

        with col_f2:
            state_options = [
                "All",
                "Planned",
                "Open",
                "Closed",
                "Cancelled",
                "Expired",
                "Invalidated",
            ]
            filter_state = st.selectbox(
                "Lifecycle State",
                state_options,
                key="journal_filter_state",
                help="Filter by trade lifecycle state.",
            )

        with col_f3:
            try:
                available_strategies = get_journal_strategy_ids(settings=settings)
            except StoreError:
                available_strategies = []
            strategy_options = ["All"] + available_strategies
            filter_strategy = st.selectbox(
                "Strategy",
                strategy_options,
                key="journal_filter_strategy",
                help="Filter by persisted strategy identifier.",
            )

    # ── Query filtered records ────────────────────────────────────────────────
    try:
        trades = list_journal_read_models(
            state=filter_state if filter_state != "All" else None,
            strategy_id=filter_strategy if filter_strategy != "All" else None,
            symbol=search_symbol if search_symbol else None,
            limit=500,
            settings=settings,
        )
    except StoreError as err:
        st.error(f"Failed to query filtered Journal trades: {err}")
        return

    if not trades:
        st.warning("No Journal trade records match the current filter selection.")
        return

    st.markdown(f"**Showing {len(trades)} executable trade record(s):**")

    # ── Build Overview Display DataFrame ──────────────────────────────────────
    table_rows = []
    for t in trades:
        strat_display = t.formatted_strategy
        if not t.is_strategy_authorized:
            strat_display = f"{strat_display} [Not Currently Authorized]"

        table_rows.append(
            {
                "Symbol": t.symbol,
                "State": t.formatted_state_badge,
                "Strategy": strat_display,
                "Side": t.side.upper(),
                "Planned Entry": t.formatted_planned_entry,
                "Qty": t.formatted_quantity,
                "Fill Price": t.formatted_fill_price,
                "Stop": t.formatted_stop_price,
                "Target": t.formatted_target_price,
                "Exit Price": t.formatted_exit_price,
                "Exit Reason": t.formatted_exit_reason,
                "Gross Return": t.formatted_gross_return,
                "Net Return": t.formatted_net_return,
                "Confidence": t.formatted_confidence_badge,
                "Provenance": t.formatted_fill_provenance_badge if t.fill_provenance else (t.formatted_exit_provenance_badge if t.exit_provenance else "—"),
                "Decision Time": t.formatted_decision_time,
            }
        )

    df_display = pd.DataFrame(table_rows)

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Symbol": st.column_config.TextColumn("Symbol", help="Ticker symbol of the trade plan."),
            "State": st.column_config.TextColumn("State", help="Lifecycle badge: Planned (⚪), Open (🔵), Closed (⚫ neutral), Cancelled (✖), Expired (⏳), Invalidated (🚫)."),
            "Strategy": st.column_config.TextColumn("Strategy", help="Strategy identity and version. Indicates if not currently authorized."),
            "Side": st.column_config.TextColumn("Side", help="Trade direction (LONG)."),
            "Planned Entry": st.column_config.TextColumn("Planned Entry", help="Planned entry trigger price."),
            "Qty": st.column_config.TextColumn("Qty", help="Execution position quantity."),
            "Fill Price": st.column_config.TextColumn("Fill Price", help="Realized entry fill price."),
            "Stop": st.column_config.TextColumn("Stop", help="Configured stop price."),
            "Target": st.column_config.TextColumn("Target", help="Configured target price."),
            "Exit Price": st.column_config.TextColumn("Exit Price", help="Realized exit fill price."),
            "Exit Reason": st.column_config.TextColumn("Exit Reason", help="Reason for trade exit."),
            "Gross Return": st.column_config.TextColumn("Gross Return", help="Gross realized return percentage (+X.XX% / -X.XX%)."),
            "Net Return": st.column_config.TextColumn("Net Return", help="Net realized return percentage after documented costs (+X.XX% / -X.XX%). Unknown if costs unavailable."),
            "Confidence": st.column_config.TextColumn("Confidence", help="Outcome confidence badge: Confirmed (🟢), Provisional (🟡), Unknown (⚪)."),
            "Provenance": st.column_config.TextColumn("Provenance", help="Execution source badge: Manual Reported (👤), Simulated (🧪), Broker Confirmed (🏦)."),
            "Decision Time": st.column_config.TextColumn("Decision Time", help="Point-in-time timestamp of the decision in America/New_York (ET)."),
        },
    )

    # ── Interactive Detail Drilldown Selection ─────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔍 Inspect Journal Trade Detail")
    col_sel, col_btn = st.columns([3, 1])
    with col_sel:
        trade_map = {
            f"{t.symbol} ({t.formatted_state_badge}) · {t.strategy_id}:{t.strategy_version} · {t.formatted_decision_time}": t.journal_id
            for t in trades
        }
        chosen_label = st.selectbox(
            "Select trade to inspect detail:",
            options=list(trade_map.keys()),
            key="journal_drilldown_picker",
            help="Select an executable trade record to view complete immutable plan, execution history, event timeline, and versioned outcomes.",
        )
    with col_btn:
        st.write("")
        if st.button("View Detail", key="btn_view_journal_detail", type="primary", use_container_width=True):
            j_id = trade_map[chosen_label]
            st.session_state["journal_selected_id"] = j_id
            st.rerun()


def _render_journal_detail(journal_id: str, *, settings: TradeXSettings) -> None:
    """Render complete in-place detail view for a specific Journal trade."""
    if st.button("← Back to Journal Overview", key="btn_back_to_journal"):
        st.session_state["journal_selected_id"] = None
        st.rerun()
        return

    try:
        detail: JournalDetailReadModel | None = get_journal_detail(journal_id, settings=settings)
    except StoreError as err:
        st.error(f"Failed to load Journal detail from database: {err}")
        return

    if detail is None:
        st.error(f"Journal trade record '{journal_id}' not found.")
        return

    trade = detail.trade

    # ── A. Trade Identity & Header ─────────────────────────────────────────────
    st.subheader(f"Journal Trade — {detail.symbol} ({trade.formatted_state_badge})")

    auth_tag = "Active (Authorized)" if detail.is_strategy_authorized else "Not Currently Authorized / Deprecated"
    st.markdown(
        f"**Symbol:** `{detail.symbol}`  ·  "
        f"**Journal ID:** `{trade.journal_id}`  ·  "
        f"**Candidate ID:** `{trade.candidate_id}`  ·  "
        f"**Strategy:** `{trade.strategy_id}:{trade.strategy_version}`  ·  "
        f"**Authorization Status:** `{auth_tag}`"
    )

    # ── B. Immutable Plan ──────────────────────────────────────────────────────
    st.markdown("### Immutable Trade Plan")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Planned Entry", trade.formatted_planned_entry)
    p2.metric("Stop Price", trade.formatted_stop_price)
    p3.metric("Target Price", trade.formatted_target_price)
    p4.metric("Expiration", _format_market_time(trade.expiration, include_date=True))

    if trade.invalidation_rule:
        st.markdown(
            f"**Invalidation Rule:** `{trade.invalidation_rule.rule_id}` (v`{trade.invalidation_rule.rule_version}`)"
        )
        if trade.invalidation_rule.params:
            st.json(trade.invalidation_rule.params)
    else:
        st.caption("No custom invalidation rule configured for this plan.")

    # ── C. Candidate Snapshot Context ──────────────────────────────────────────
    st.markdown("### Upstream Candidate Context")
    if detail.candidate_snapshot:
        snap = detail.candidate_snapshot
        status_val = snap.security_identity_status.value if hasattr(snap.security_identity_status, "value") else str(snap.security_identity_status)
        ver_val = snap.security_identity_version if snap.security_identity_version is not None else "NULL (None)"
        st.markdown(
            f"**Candidate ID:** `{snap.candidate_id}`  ·  "
            f"**Contract Version:** `v{snap.contract_version}`  ·  "
            f"**Decision Time:** `{_format_market_time(snap.decision_timestamp, include_date=True)}`  ·  "
            f"**Trading Date:** `{snap.trading_date or 'NULL'}`  ·  "
            f"**Security Identity Version:** `{ver_val}`  ·  "
            f"**Security Status:** `{status_val}`"
        )
    else:
        st.caption(f"Referenced CandidateSnapshot `{trade.candidate_id}` identity details unavailable.")

    if detail.candidate_evidence_summary:
        with st.expander("📄 Upstream Candidate Evidence Summary", expanded=False):
            for ev_type, ev_info in detail.candidate_evidence_summary.items():
                st.markdown(f"**Evidence Type:** `{ev_type}` (Provider: `{ev_info.get('provider', 'unknown')}`)")
                if ev_info.get("metadata"):
                    st.json(ev_info["metadata"])

    # ── D. Execution Details ───────────────────────────────────────────────────
    st.markdown("### Execution Details")
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Quantity", trade.formatted_quantity)
    e2.metric("Fill Price", trade.formatted_fill_price)
    e3.metric("Fill Time", _format_market_time(trade.fill_timestamp, include_date=True))
    e4.metric("Fill Provenance", trade.formatted_fill_provenance_badge)

    if trade.fill_provenance and trade.fill_provenance.simulation_rule:
        st.caption(
            f"Fill Simulation: rule `{trade.fill_provenance.simulation_rule}` via provider `{trade.fill_provenance.provider}` (Observer: `{trade.fill_provenance.observer}`)"
        )

    if trade.state.lower() in ("closed", "cancelled", "expired", "invalidated"):
        x1, x2, x3, x4 = st.columns(4)
        x1.metric("Exit Price", trade.formatted_exit_price)
        x2.metric("Exit Time", _format_market_time(trade.exit_timestamp, include_date=True))
        x3.metric("Exit Reason", trade.formatted_exit_reason)
        x4.metric("Exit Provenance", trade.formatted_exit_provenance_badge)

        if trade.exit_provenance and trade.exit_provenance.simulation_rule:
            st.caption(
                f"Exit Simulation: rule `{trade.exit_provenance.simulation_rule}` via provider `{trade.exit_provenance.provider}` (Observer: `{trade.exit_provenance.observer}`)"
            )

        if trade.terminal_reason:
            st.markdown(f"**Terminal Reason:** {trade.terminal_reason}")

    # ── E. Outcome & Returns ───────────────────────────────────────────────────
    st.markdown("### Realized Outcome")
    if detail.current_outcome:
        out = detail.current_outcome
        o1, o2, o3, o4, o5 = st.columns(5)
        o1.metric("Gross Return", out.formatted_gross_return, delta=f"{out.gross_return_pct:+.2f}%" if out.gross_return_pct is not None else None)
        o2.metric("Net Return", out.formatted_net_return, delta=f"{out.net_return_pct:+.2f}%" if out.net_return_pct is not None else None)
        o3.metric("Costs / Fees", f"${out.costs:.2f}" if out.costs is not None else "Unknown (NULL)")
        o4.metric("Entry Slippage", f"${out.entry_slippage:+.2f}" if out.entry_slippage is not None else "—")
        o5.metric("Confidence", out.formatted_confidence_badge)

        st.markdown(
            f"**Outcome ID:** `{out.outcome_id}`  ·  "
            f"**Computation Version:** `{out.computation_version}`  ·  "
            f"**Computed At:** `{out.formatted_computed_at}`  ·  "
            f"**Source Event Seq:** `{out.source_event_seq}`  ·  "
            f"**Inputs Hash:** `{out.inputs_hash}`"
        )
        st.markdown("**Strategy Drawdown:** `Unknown` *(Portfolio drawdown aggregation unsupported in R6 v1)*")

        # Expose persisted outcome computation inputs in inspectable read-only JSON surface
        with st.expander("🔍 Persisted Computation Inputs (Current Outcome)", expanded=False):
            if out.inputs:
                st.json(out.inputs)
            else:
                st.caption("No computation inputs recorded.")
    else:
        st.info("No realized outcome calculated yet for this trade setup.")

    # ── F. Event Audit Timeline ────────────────────────────────────────────────
    st.markdown("### Append-Only Event Audit Timeline")
    if detail.events:
        event_rows = [
            {
                "Seq": ev.seq,
                "Event Type": ev.formatted_event_type,
                "Event Time (ET)": ev.formatted_event_timestamp,
                "Recorded At (ET)": ev.formatted_recorded_at,
                "Payload Summary": json.dumps(ev.payload, sort_keys=True) if ev.payload else "{}",
            }
            for ev in detail.events
        ]
        st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No lifecycle events recorded.")

    # ── G. Versioned Outcome History ───────────────────────────────────────────
    st.markdown("### Versioned Outcome Audit History")
    if detail.outcomes:
        outcome_rows = [
            {
                "Outcome ID": oc.outcome_id,
                "Version": oc.computation_version,
                "Computed At (ET)": oc.formatted_computed_at,
                "Source Seq": oc.source_event_seq,
                "Gross Return": oc.formatted_gross_return,
                "Net Return": oc.formatted_net_return,
                "Confidence": oc.formatted_confidence_badge,
                "Inputs Hash": oc.inputs_hash,
            }
            for oc in detail.outcomes
        ]
        st.dataframe(pd.DataFrame(outcome_rows), use_container_width=True, hide_index=True)

        # Make inputs for each outcome version inspectable
        with st.expander("🔍 Inspect Historical Outcome Computation Inputs", expanded=False):
            for oc in detail.outcomes:
                st.markdown(
                    f"**Outcome `{oc.outcome_id}`** (v`{oc.computation_version}` · `{oc.formatted_computed_at}` · Hash: `{oc.inputs_hash}`)"
                )
                if oc.inputs:
                    st.json(oc.inputs)
                else:
                    st.caption("Empty or unrecorded inputs.")
    else:
        st.caption("No outcome computations recorded.")

