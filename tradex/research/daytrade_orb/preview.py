"""Pure deterministic research-only ORB Candidate Preview service.

Implements DAYTRADE-003E-ORB-PREVIEW-001:
- Reuses existing indicators and ranking functions from tradex.research.daytrade_orb.
- Enforces strict 09:35 ET time-gating and point-in-time boundaries.
- Isolates errors per symbol so corrupt entries never crash the entire preview.
- Classifies non-qualifying symbols as TECHNICAL_FILTER, DATA_UNAVAILABLE, or INTEGRITY_BLOCKED.
- Ranks top 20 by RV descending (ticker ascending tie-breaker).
- Displays theoretical stop-loss offset (0.10 * ATR14) without fabricating executed fills or definitive stop prices.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from .indicators import compute_adv14, compute_atr14_wilder, compute_relative_volume
from .models import (
    Candidate,
    Direction,
    OpeningRange,
    OrderStatus,
)
from .ranking import evaluate_candidate, evaluate_opening_range, rank_and_select_top_20
from .snapshot import ORBSnapshot, SnapshotSymbolPayload

MARKET_TIMEZONE = ZoneInfo("America/New_York")
ORB_RANKING_EARLIEST_TIME = time(9, 35)

RESEARCH_PREVIEW_DISCLAIMER = (
    "RESEARCH PREVIEW ONLY — NOT AN ACTIONABLE TRADING STRATEGY. "
    "Zarattini, Barbon, Aziz (2024) is external prior literature; published historical returns "
    "have NOT been validated or replicated in TradeX. This preview ranks candidate setups strictly "
    "within the uploaded or demo constituent set as of 09:35 ET. No simulated orders, fills, "
    "slippage, broker interactions, or investment recommendations are provided."
)


class ExclusionCategory(str, Enum):
    """Taxonomy for excluded or non-qualifying symbols."""

    TECHNICAL_FILTER = "TECHNICAL_FILTER"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    INTEGRITY_BLOCKED = "INTEGRITY_BLOCKED"


@dataclass(frozen=True)
class SymbolExclusion:
    """Detailed record of why a symbol did not qualify for the Top-20 preview."""

    symbol: str
    category: ExclusionCategory
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidatePreviewRow:
    """User-facing presentation row for an eligible Top-20 ranked candidate."""

    rank: int
    symbol: str
    direction: Direction
    or_open: float
    or_high: float
    or_low: float
    or_close: float
    or_volume: float
    adv14: float
    atr14: float
    rv14: float
    stop_entry_trigger: float | None
    theoretical_stop_offset: float
    order_intent_status: OrderStatus
    explanation: str


@dataclass(frozen=True)
class PreviewUniverseCoverage:
    """Constituent coverage and universe completeness metadata."""

    provided_count: int
    eligible_count: int
    top_n_selected: int
    completeness_status: str  # "unknown" | "watchlist_only" | "declared_complete"
    completeness_warning: str
    notes: str = ""


@dataclass(frozen=True)
class ORBCandidatePreviewResult:
    """Immutable result of generating an ORB Candidate Preview for a session."""

    session_date: date
    as_of_time: datetime
    source_type: str
    source_label: str
    universe_coverage: PreviewUniverseCoverage
    is_time_gated: bool
    time_gate_message: str | None
    candidates: list[CandidatePreviewRow]
    unranked_eligible_candidates: list[Candidate]
    exclusions: list[SymbolExclusion]
    warnings: list[str]
    disclaimer: str = RESEARCH_PREVIEW_DISCLAIMER


def generate_orb_candidate_preview(
    snapshot: ORBSnapshot,
    session_start_equity: float = 25000.0,
    top_n: int = 20,
) -> ORBCandidatePreviewResult:
    """Generate a deterministic, research-only ORB Candidate Preview from a snapshot.

    Guarantees:
    1. Input order invariance: symbols are sorted deterministically before evaluation.
    2. Per-symbol isolation: data failure or corruption in one symbol never affects others.
    3. Strict time gating: snapshots as-of prior to 09:35 ET block candidate ranking.
    4. Exact rule fidelity: Price > $5, ADV14 >= 1M, ATR14 > $0.50, RV14 >= 1.0.
    5. No-order Doji: Doji setups in the Top 20 produce NO_ORDER and are not backfilled.
    6. Theoretical stop offset: displayed as 0.10 * ATR14 relative to future entry fill.
    """
    ny_as_of = snapshot.as_of_time.astimezone(MARKET_TIMEZONE)
    session_date = snapshot.session_date

    # 1. Time-gating: candidate ranking is blocked prior to 09:35:00 ET
    is_before_935 = ny_as_of.time() < ORB_RANKING_EARLIEST_TIME
    if is_before_935:
        gate_msg = (
            f"Candidate ranking is blocked: snapshot as-of time {ny_as_of.strftime('%H:%M:%S %Z')} "
            f"is prior to {ORB_RANKING_EARLIEST_TIME.strftime('%H:%M')} ET. "
            "The 5-minute Opening Range Breakout strategy requires complete 09:30–09:34 ET bars."
        )
        return ORBCandidatePreviewResult(
            session_date=session_date,
            as_of_time=snapshot.as_of_time,
            source_type=snapshot.source_type,
            source_label=snapshot.source_label,
            universe_coverage=PreviewUniverseCoverage(
                provided_count=len(snapshot.symbols),
                eligible_count=0,
                top_n_selected=0,
                completeness_status=snapshot.completeness_status,
                completeness_warning="Preview is time-gated before 09:35 ET; no ranking performed.",
                notes=snapshot.notes,
            ),
            is_time_gated=True,
            time_gate_message=gate_msg,
            candidates=[],
            unranked_eligible_candidates=[],
            exclusions=[],
            warnings=[gate_msg],
        )

    # 2. Evaluate all symbols deterministically (sorted by ticker symbol)
    sorted_symbols = sorted(snapshot.symbols.keys())
    eligible_candidates: list[Candidate] = []
    opening_ranges: dict[str, OpeningRange] = {}
    exclusions: list[SymbolExclusion] = []
    warnings: list[str] = []

    for sym in sorted_symbols:
        payload: SnapshotSymbolPayload = snapshot.symbols[sym]

        # Check for symbol-level integrity failure captured during snapshot ingestion
        if payload.integrity_error:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.INTEGRITY_BLOCKED,
                    reason=f"Data integrity error: {payload.integrity_error}",
                )
            )
            continue

        # Check for future-bar leakage in opening range minute bars
        has_future_bar = False
        for bar in payload.opening_range_bars:
            bar_ny_time = bar.timestamp.astimezone(MARKET_TIMEZONE).time()
            if bar_ny_time >= ORB_RANKING_EARLIEST_TIME:
                exclusions.append(
                    SymbolExclusion(
                        symbol=sym,
                        category=ExclusionCategory.INTEGRITY_BLOCKED,
                        reason=(
                            f"Future-bar leakage: opening range minute bar timestamp "
                            f"{bar.timestamp.astimezone(MARKET_TIMEZONE).strftime('%H:%M:%S')} "
                            f"is at or after {ORB_RANKING_EARLIEST_TIME.strftime('%H:%M')} ET"
                        ),
                    )
                )
                has_future_bar = True
                break
        if has_future_bar:
            continue

        # Evaluate opening range (09:30-09:34 ET)
        op_range = evaluate_opening_range(payload.opening_range_bars, require_five_bars=False)
        if op_range is None:
            if len(payload.opening_range_bars) == 0:
                exclusions.append(
                    SymbolExclusion(
                        symbol=sym,
                        category=ExclusionCategory.DATA_UNAVAILABLE,
                        reason="No opening range prints in 09:30–09:34 ET regular session (NO_OPENING_PRINT_NO_SETUP)",
                    )
                )
            else:
                exclusions.append(
                    SymbolExclusion(
                        symbol=sym,
                        category=ExclusionCategory.INTEGRITY_BLOCKED,
                        reason="Opening range bars failed validation or contained contradictory timestamps",
                    )
                )
            continue

        # Compute ADV14 through D-1
        adv14 = compute_adv14(payload.daily_bars, session_date)
        if adv14 is None:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.DATA_UNAVAILABLE,
                    reason="ADV14 non-computable: missing or non-contiguous prior 14 completed XNYS daily sessions",
                )
            )
            continue

        # Compute Wilder ATR14 through D-1
        atr14 = compute_atr14_wilder(payload.daily_bars, session_date)
        if atr14 is None:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.DATA_UNAVAILABLE,
                    reason="ATR14 non-computable: requires 15 contiguous completed XNYS daily sessions through D-1",
                )
            )
            continue

        # Compute Relative Volume
        rv, mean_prior_or_vol = compute_relative_volume(
            payload.prior_opening_range_volumes,
            op_range.or_volume,
            session_date,
        )
        if rv is None:
            if mean_prior_or_vol == 0.0:
                exclusions.append(
                    SymbolExclusion(
                        symbol=sym,
                        category=ExclusionCategory.DATA_UNAVAILABLE,
                        reason="Zero RV baseline: mean prior 14-session opening range volume is 0.0 (unrankable)",
                    )
                )
            else:
                exclusions.append(
                    SymbolExclusion(
                        symbol=sym,
                        category=ExclusionCategory.DATA_UNAVAILABLE,
                        reason="RV14 non-computable: missing required prior 14 completed XNYS opening range sessions",
                    )
                )
            continue

        # Evaluate candidate eligibility filters
        cand = evaluate_candidate(
            symbol=sym,
            session_date=session_date,
            opening_range=op_range,
            adv14=adv14,
            atr14=atr14,
            mean_prior_or_volume=mean_prior_or_vol,
            rv=rv,
        )

        if not cand.is_eligible:
            reasons = "; ".join(cand.rejection_reasons)
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.TECHNICAL_FILTER,
                    reason=f"Technical filter rejected: {reasons}",
                    details={
                        "price": cand.opening_price,
                        "adv14": cand.adv14,
                        "atr14": cand.atr14,
                        "rv14": cand.relative_volume,
                    },
                )
            )
            continue

        eligible_candidates.append(cand)
        opening_ranges[sym] = op_range

    # 3. Deterministic Top-20 ranking
    ranked_top_20 = rank_and_select_top_20(
        candidates=eligible_candidates,
        opening_ranges=opening_ranges,
        session_start_equity=session_start_equity,
        top_n=top_n,
    )

    # 4. Format CandidatePreviewRow objects
    preview_candidates: list[CandidatePreviewRow] = []
    selected_symbols = set()

    for item in ranked_top_20:
        c = item.candidate
        op = item.opening_range
        intent = item.order_intent
        selected_symbols.add(c.symbol)

        if op.direction == Direction.LONG:
            explanation = (
                f"Long setup (OR close ${op.or_close:.2f} > open ${op.or_open:.2f}). "
                f"Prospective stop-entry trigger at OR high ${op.or_high:.2f}."
            )
        elif op.direction == Direction.SHORT:
            explanation = (
                f"Short setup (OR close ${op.or_close:.2f} < open ${op.or_open:.2f}). "
                f"Prospective stop-entry trigger at OR low ${op.or_low:.2f}."
            )
        else:
            explanation = (
                "Doji setup (OR close == open). NO_ORDER generated; "
                "doji candidates receive no order and are not backfilled."
            )

        preview_candidates.append(
            CandidatePreviewRow(
                rank=item.rank,
                symbol=c.symbol,
                direction=op.direction,
                or_open=op.or_open,
                or_high=op.or_high,
                or_low=op.or_low,
                or_close=op.or_close,
                or_volume=op.or_volume,
                adv14=c.adv14,
                atr14=c.atr14,
                rv14=c.relative_volume,
                stop_entry_trigger=intent.stop_level,
                theoretical_stop_offset=intent.protective_stop_offset,
                order_intent_status=intent.status,
                explanation=explanation,
            )
        )

    # 5. Handle eligible candidates beyond Top 20 (cutoff without backfill)
    # Sort all eligible candidates in ranking order: RV desc, symbol asc
    all_eligible_sorted = sorted(eligible_candidates, key=lambda c: (-c.relative_volume, c.symbol))
    unranked_eligible = all_eligible_sorted[top_n:]

    for idx, unranked in enumerate(unranked_eligible, start=top_n + 1):
        exclusions.append(
            SymbolExclusion(
                symbol=unranked.symbol,
                category=ExclusionCategory.TECHNICAL_FILTER,
                reason=(
                    f"Eligible candidate ranked #{idx} by RV (exceeds Top-{top_n} cutoff; "
                    "no backfill for Doji or unselected candidates)"
                ),
                details={"rv14": unranked.relative_volume},
            )
        )

    # 6. Universe completeness warning
    completeness_warning = (
        "Universe coverage is limited to the provided constituent set "
        f"({len(snapshot.symbols)} symbols provided, completeness: {snapshot.completeness_status}). "
        "This preview ranks candidates solely within this provided input and must NOT be interpreted "
        "as reproducing the source paper's full-market ~7,000 equity universe."
    )
    if snapshot.completeness_status != "declared_complete":
        warnings.append(completeness_warning)

    universe_cov = PreviewUniverseCoverage(
        provided_count=len(snapshot.symbols),
        eligible_count=len(eligible_candidates),
        top_n_selected=len(preview_candidates),
        completeness_status=snapshot.completeness_status,
        completeness_warning=completeness_warning,
        notes=snapshot.notes,
    )

    return ORBCandidatePreviewResult(
        session_date=session_date,
        as_of_time=snapshot.as_of_time,
        source_type=snapshot.source_type,
        source_label=snapshot.source_label,
        universe_coverage=universe_cov,
        is_time_gated=False,
        time_gate_message=None,
        candidates=preview_candidates,
        unranked_eligible_candidates=unranked_eligible,
        exclusions=exclusions,
        warnings=warnings,
    )
