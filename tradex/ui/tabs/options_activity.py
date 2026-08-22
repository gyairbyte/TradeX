"""Options Activity tab renderer (extracted from dashboard.py)."""

from __future__ import annotations

import streamlit as st

from tradex.config import TradeXSettings
from tradex.options.flow import (
    get_put_call_activity,
    resolve_chain_source,
    resolve_flow_source,
    scan_chain_activity_with_report,
    scan_unusual_flow_with_report,
)
from tradex.options.models import OptionsActivityReport, OptionsDataKind, OptionsScanStatus
from tradex.ui.evidence import render_evidence_notice


def _options_source_status_message(status) -> str:
    """Human-readable summary of an options source capability status."""
    kind = status.data_kind.value.replace("_", " ") if status.data_kind else "unavailable"
    name = status.actual_source or status.requested_source
    msg = f"{name.title()}: {kind.title()}"
    if status.error:
        msg += f" — {status.error}"
    return msg


def _true_flow_disabled_message(status) -> str:
    """Return the disabled explanation for the true-flow scan button."""
    if status.available and status.data_kind == OptionsDataKind.TRUE_FLOW:
        return ""
    return (
        "No true options-flow source is configured. Tradier and Yahoo provide chain snapshots, "
        "not transaction-level flow. Configure Unusual Whales to enable this scanner."
    )


def _options_status_container(status, label: str) -> None:
    """Render a source status box for the given options capability."""
    if not status.available:
        st.error(f"{label}: {_options_source_status_message(status)}")
    elif status.error:
        st.warning(f"{label}: {_options_source_status_message(status)}")
    else:
        st.info(f"{label}: {_options_source_status_message(status)}")


def _chain_scan_disabled_message(status) -> str:
    """Return the disabled explanation for the chain-activity scan button."""
    if status.available and status.data_kind == OptionsDataKind.CHAIN_SNAPSHOT:
        return ""
    return (
        status.error
        or "No options-chain snapshot source is available for the selected source. "
           "Configure TRADIER_API_KEY or select Yahoo to enable this scanner."
    )


def _render_options_report(report: OptionsActivityReport, label: str, min_vol_oi: float) -> None:
    """Render a scan report, clearly separating results from partial/complete failures."""
    if report is None:
        return

    if report.status == OptionsScanStatus.SOURCE_UNAVAILABLE:
        st.error(
            f"{label}: source unavailable — "
            f"{report.source_status.error or 'check configuration'}"
        )
        return
    if report.status == OptionsScanStatus.NOT_FLOW_CAPABLE:
        st.error(
            f"{label}: not a true-flow source — "
            f"{report.source_status.error or 'selected source does not provide transaction-level flow'}"
        )
        return
    if report.status == OptionsScanStatus.COMPLETE_FAILURE:
        st.error(
            f"{label}: scan failed for all requested tickers. "
            f"Status: {report.status.value}"
        )
        with st.expander("Failures"):
            st.json(report.failures)
        return

    if report.total_matches:
        st.success(
            f"{report.total_matches} {label.lower()} found "
            f"(source: {report.actual_source}; "
            f"data_kind: {report.data_kind.value if report.data_kind else 'unknown'})"
        )
        st.dataframe(report.results, use_container_width=True)
    elif report.failures:
        st.warning(
            f"{label}: no matches; {len(report.failures)} ticker(s) failed. "
            f"Status: {report.status.value}"
        )
        with st.expander("Failures"):
            st.json(report.failures)
    else:
        st.info(
            f"{label}: no matches above {min_vol_oi}x Vol/OI ratio "
            f"(source: {report.actual_source or report.requested_source})."
        )

    if report.failures and report.total_matches:
        st.warning(
            f"Partial failure: {len(report.failures)} ticker(s) failed while other "
            f"tickers produced matches. Status: {report.status.value}"
        )
        with st.expander("Failures"):
            st.json(report.failures)


def render_options_activity_tab(
    *,
    settings: TradeXSettings,
    watchlist: list[str],
    options_source: str,
) -> None:
    """Render the Options Activity tab."""
    st.subheader("Options Activity")
    render_evidence_notice("options_activity", st_module=st)
    st.caption(
        "Distinguishes true options-flow events from delayed options-chain snapshots. "
        "Chain volume and open interest describe aggregate positioning, not direction or intent."
    )

    with st.expander("How to read options activity", expanded=False):
        st.markdown("""
**Options basics:**
- A **call option** gives the holder the right to buy a stock at a set price.
- A **put option** gives the holder the right to sell a stock at a set price.
- **Volume** = number of contracts traded in a period.
- **Open Interest (OI)** = total number of contracts currently outstanding.

**True options flow vs. chain snapshots:**
- **True flow** = transaction-level events (sweeps, block trades, reported premium). Only available
  from a true-flow provider such as Unusual Whales when configured.
- **Chain snapshots** = a provider's listing of contracts with volume, OI, bid, ask, and last price.
  Tradier and Yahoo provide snapshots, not individual trade events. Sweep, side, and timestamp fields
  are not inferred from a snapshot.

**Why Vol/OI ratio is reported:**
A high volume-to-open-interest ratio can flag unusual turnover on a contract, but it only measures
how much trading happened relative to outstanding contracts. It does not identify the trade side,
whether the activity was opening or closing, or who initiated the trade.

|| Vol/OI Ratio | Reading |
|---|---|---|
|| > 10x | Very high turnover relative to outstanding contracts |
|| 3–10x | Elevated turnover |
|| 1–3x | Typical to slightly elevated |

**Sweeps:** Only a true-flow provider can report whether a trade was a sweep. A sweep indicator
must come from the provider; it is never inferred from a chain snapshot.

**Call/Put volume balance:**
Aggregate call and put volume is a non-directional description of activity. It is **not** a
bullish/bearish signal. A high call/put ratio only tells you more calls traded than puts; those
calls could be bought or sold, opening or closing.

**Data sources:**
- **Unusual Whales** — true options-flow events when `UNUSUAL_WHALES_API_KEY` is configured.
- **Tradier** — options-chain snapshots when `TRADIER_API_KEY` is configured.
- **Yahoo** — delayed options-chain snapshots, no credentials required.
        """)

    st.caption(f"Selected options source: **{options_source}**")
    flow_status = resolve_flow_source(options_source, settings=settings)
    chain_status = resolve_chain_source(options_source, settings=settings)

    o_col1, o_col2 = st.columns(2)
    min_vol_oi = o_col1.slider(
        "Min Vol/OI ratio", 1.0, 20.0, 3.0, step=0.5, key="min_vol_oi",
        help=(
            "Only show options contracts where volume exceeds this multiple of open interest.\n\n"
            "• **1–2x** — slightly elevated, lots of noise.\n"
            "• **3x (default)** — meaningful turnover threshold.\n"
            "• **10x+** — very high turnover."
        ),
    )
    o_col2.markdown("""
**Vol/OI guide:**
- **>10x** — very high turnover
- **3–10x** — elevated turnover
- **1–3x** — typical to slightly elevated
    """)

    st.divider()
    st.subheader("True Options Flow")
    st.caption("Transaction-level flow events from Unusual Whales. Requires a configured API key.")
    _options_status_container(flow_status, "True-flow source")

    flow_disabled = _true_flow_disabled_message(flow_status)
    if flow_disabled:
        st.warning(flow_disabled)

    flow_report = None
    if st.button(
        "Scan True Options Flow",
        type="primary",
        key="btn_options",
        disabled=not flow_status.available,
        help="Scan for transaction-level flow events (sweeps, premium, side) from Unusual Whales.",
    ):
        with st.spinner(f"Scanning true options flow for {len(watchlist)} tickers…"):
            flow_report = scan_unusual_flow_with_report(
                watchlist, min_vol_oi=min_vol_oi, source=options_source, settings=settings
            )

    _render_options_report(flow_report, "True Options Flow", min_vol_oi)

    st.divider()
    st.subheader("Options Chain Activity")
    st.caption("Options-chain snapshots from Tradier or Yahoo. Volume, OI, bid/ask/last only.")
    _options_status_container(chain_status, "Chain source")

    chain_disabled = not chain_status.available or chain_status.data_kind != OptionsDataKind.CHAIN_SNAPSHOT
    chain_disabled_message = _chain_scan_disabled_message(chain_status)
    if chain_disabled_message:
        st.warning(chain_disabled_message)

    chain_report = None
    if st.button(
        "Scan Options Chain Activity",
        key="btn_options_chain",
        disabled=chain_disabled,
        help="Scan Tradier or Yahoo option chains for elevated volume/OI turnover.",
    ):
        with st.spinner(f"Scanning options chains for {len(watchlist)} tickers…"):
            chain_report = scan_chain_activity_with_report(
                watchlist, min_vol_oi=min_vol_oi, source=options_source, settings=settings
            )

    _render_options_report(chain_report, "Options Chain Activity", min_vol_oi)

    st.divider()
    st.subheader("Call/Put Volume Balance")
    st.caption("Aggregate call vs. put volume from the selected chain source. This is non-directional.")
    pc_ticker = st.selectbox("Select ticker", watchlist, key="sel_pc")
    if st.button(
        "Get Volume Balance",
        key="btn_pc",
        help="Fetch the options chain and compute a non-directional call/put volume balance.",
    ):
        with st.spinner(f"Fetching options data for {pc_ticker}…"):
            activity = get_put_call_activity(pc_ticker, source=options_source, settings=settings)
        if activity.get("error"):
            st.error(activity["error"])
        else:
            s_col1, s_col2, s_col3, s_col4 = st.columns(4)
            s_col1.metric(
                "Put/Call Ratio",
                activity.get("put_call_volume_ratio", "N/A"),
                help="Put volume ÷ Call volume. Non-directional description of aggregate volume.",
            )
            s_col2.metric("Call Volume", activity.get("call_volume", 0))
            s_col3.metric("Put Volume", activity.get("put_volume", 0))
            s_col4.metric("Volume Balance", activity.get("volume_balance", "unknown").upper())
            if not activity.get("directional_inference"):
                st.info(
                    "Volume balance is non-directional. It does not imply bullish or bearish intent."
                )
