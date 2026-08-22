"""Evidence notices and classification metadata for TradeX dashboard surfaces.

Part of MVP-ARCH-001-R1: Truthful UI/help labeling and evidence-state notices.
Provides static, immutable metadata and rendering helpers for all ten dashboard tabs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceNotice:
    """Immutable evidence classification and disclosure for a dashboard tab."""

    tab_id: str
    evidence_state: str
    badge_label: str
    summary: str
    level: str = "info"  # "info" or "warning"


EVIDENCE_NOTICES: dict[str, EvidenceNotice] = {
    "scanner": EvidenceNotice(
        tab_id="scanner",
        evidence_state="legacy_heuristic",
        badge_label="Legacy Heuristic — Discovery Only",
        summary=(
            "The Signal Scanner computes additive technical-condition scores (0–100) across a watchlist. "
            "This score is an unvalidated discovery heuristic, not a probability, conviction metric, or "
            "validated trade recommendation. Higher scores indicate more simultaneous conditions met, "
            "not verified executable edge."
        ),
        level="info",
    ),
    "coil_detector": EvidenceNotice(
        tab_id="coil_detector",
        evidence_state="exploratory",
        badge_label="Exploratory Context — Non-Predictive",
        summary=(
            "The Coil Detector summarizes scan persistence, score stability, and prior price movement "
            "from historical scan observations. It is exploratory context and has not been validated as a "
            "predictive indicator or executable trading edge."
        ),
        level="info",
    ),
    "confluence": EvidenceNotice(
        tab_id="confluence",
        evidence_state="exploratory",
        badge_label="Exploratory Context — Multi-Timeframe Alignment",
        summary=(
            "Confluence is a coverage-aware weighted aggregation of unvalidated legacy heuristic scores "
            "across intraday, short-term, and long-term timeframes. It describes multi-timeframe score alignment, "
            "but does not establish trade conviction, probability, expected return, or executable strategy edge."
        ),
        level="info",
    ),
    "pattern_similarity": EvidenceNotice(
        tab_id="pattern_similarity",
        evidence_state="rejected",
        badge_label="Rejected on Holdout — Research Only",
        summary=(
            "Pattern similarity was formally evaluated under PATTERN-001 and rejected on holdout data. "
            "It is retained for experimental research only and is strictly excluded from production scoring, "
            "ranking, candidate eligibility, and automatic actionable alerts."
        ),
        level="warning",
    ),
    "premarket": EvidenceNotice(
        tab_id="premarket",
        evidence_state="exploratory",
        badge_label="Exploratory Event Context — Non-Actionable by Itself",
        summary=(
            "Pre-market gap size, volume, spread, and catalyst data describe overnight price adjustments "
            "and pre-market activity. Pre-market events do not independently constitute an approved trade "
            "signal or directional trade recommendation."
        ),
        level="info",
    ),
    "options_activity": EvidenceNotice(
        tab_id="options_activity",
        evidence_state="exploratory",
        badge_label="Exploratory Context — Non-Directional",
        summary=(
            "Options volume, open interest, and flow data represent exploratory market context. "
            "There is no approved executable TradeX strategy using options activity. Options-chain "
            "snapshots describe aggregate positioning and are non-directional."
        ),
        level="info",
    ),
    "alerts": EvidenceNotice(
        tab_id="alerts",
        evidence_state="settings_infrastructure",
        badge_label="Delivery Infrastructure — Legacy/Exploratory Triggers",
        summary=(
            "Alert channels provide delivery infrastructure. Current automatic alerts trigger on legacy "
            "heuristic scores and exploratory thresholds (coil strength, confluence, gap size) rather than "
            "production-approved actionable strategies. They must not be interpreted as validated strategy alerts."
        ),
        level="info",
    ),
    "signal_journal": EvidenceNotice(
        tab_id="signal_journal",
        evidence_state="legacy_signal_telemetry",
        badge_label="Legacy Signal Telemetry — Generic Horizons",
        summary=(
            "The Signal Journal tracks descriptive price changes at generic 1, 3, and 5-session horizons "
            "following historical scan signals. It does not model strategy-specific entry rules, stop losses, "
            "profit targets, expirations, invalidations, slippage, or execution costs, and cannot establish "
            "mathematical edge or executable strategy expectancy."
        ),
        level="info",
    ),
    "weights": EvidenceNotice(
        tab_id="weights",
        evidence_state="legacy_heuristic",
        badge_label="Legacy Heuristic Controls — Unvalidated",
        summary=(
            "Weight adjustments alter the point contributions of individual technical conditions in legacy "
            "heuristic scores. User-tuned weights have not been validated through controlled research and "
            "risk post-hoc overfitting to past observations."
        ),
        level="info",
    ),
    "help": EvidenceNotice(
        tab_id="help",
        evidence_state="documentation",
        badge_label="TradeX Governance & Evidence Reference",
        summary=(
            "This documentation reflects the evidence-based state of all TradeX components. "
            "TradeX is a research and decision-support application with no production-approved executable "
            "strategies. All current scanners and metrics provide discovery heuristics and exploratory context."
        ),
        level="info",
    ),
}


def get_evidence_notice(tab_id: str) -> EvidenceNotice:
    """Return the static EvidenceNotice for a given tab_id."""
    if tab_id not in EVIDENCE_NOTICES:
        raise KeyError(f"Unknown dashboard tab_id for evidence notice: {tab_id!r}")
    return EVIDENCE_NOTICES[tab_id]


def render_evidence_notice(tab_id: str, st_module: Any = None) -> EvidenceNotice:
    """Render the evidence notice badge and summary near the top of a tab.

    Accepts an explicit Streamlit module/mock for clean dependency injection and testing.
    """
    if st_module is None:
        import streamlit as st_module  # type: ignore[no-redef]
    notice = get_evidence_notice(tab_id)
    text = f"**[{notice.badge_label}]** {notice.summary}"
    if notice.level == "warning":
        st_module.warning(text)
    else:
        st_module.info(text)
    return notice
