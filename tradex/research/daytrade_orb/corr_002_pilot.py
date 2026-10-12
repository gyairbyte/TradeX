"""Corrected ORB real-data feasibility pilot logic for DAYTRADE-003D-CORR-002.

Implements corrected sparse-bar semantics, inexpensive technical pre-filtering,
meaningful 95% candidate-screening gate among daily-base-qualified symbols,
Stage-B sparse-minute compatibility auditing without trade simulation,
and immutable historical specification verification.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tradex.research.daytrade_orb.corrected_pilot import (
    DEFAULT_BATCH_SIZE,
    MAX_PILOT_PAGES_LIMIT,
    MAX_PILOT_STORAGE_BYTES_LIMIT,
    TARGET_EXCHANGE_MAPPING,
    TargetUniverseAudit,
    batch_symbols,
    filter_and_audit_target_universe,
)
from tradex.research.daytrade_orb.indicators import (
    compute_adv14,
    compute_atr14_wilder,
    compute_relative_volume,
    get_prior_xnys_sessions,
)
from tradex.research.daytrade_orb.models import (
    Candidate,
    DailyBar,
    MinuteBar,
    OpeningRange,
    OpeningRangeVolumeObservation,
    OrderStatus,
    RankedCandidate,
)
from tradex.research.daytrade_orb.ranking import (
    evaluate_candidate,
    evaluate_opening_range,
    rank_and_select_top_20,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CANDIDATE_SCREENING_GATE_THRESHOLD",
    "CORR_002_SPEC_PATH",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_PRIVATE_ROOT",
    "LOCKED_003B_SPEC_PATH",
    "LOCKED_003B_SPEC_SHA256",
    "LOCKED_003C_RESOLUTION_PATH",
    "LOCKED_003C_RESOLUTION_SHA256",
    "LOCKED_003D_CORR_001_SPEC_PATH",
    "LOCKED_003D_CORR_001_SPEC_SHA256",
    "LOCKED_003D_CORR_002_SPEC_SHA256",
    "LOCKED_003D_SPEC_PATH",
    "LOCKED_003D_SPEC_SHA256",
    "MAX_PILOT_PAGES_LIMIT",
    "MAX_PILOT_STORAGE_BYTES_LIMIT",
    "PILOT_DATE",
    "STRATEGY_ID",
    "TARGET_EXCHANGE_MAPPING",
    "TASK_ID",
    "BroadDailyAvailabilityAudit",
    "CandidateScreeningAudit",
    "CandidateScreeningOutcome",
    "FrozenSelectionEvidence",
    "PilotDisposition",
    "StageBPathAudit",
    "TargetUniverseAudit",
    "audit_broad_daily_availability",
    "audit_candidate_screening",
    "audit_stage_b_price_path",
    "batch_symbols",
    "determine_pilot_disposition",
    "evaluate_opening_range",
    "filter_and_audit_target_universe",
    "freeze_top_20_selection",
    "get_prior_xnys_sessions",
    "hash_bytes",
    "hash_text",
    "json_hash",
    "rank_and_select_top_20",
    "verify_upstream_spec_hashes",
]

MARKET_TIMEZONE = ZoneInfo("America/New_York")

TASK_ID = "DAYTRADE-003D-CORR-002"
STRATEGY_ID = "DAYTRADE-003B-ORB-SIP5M"
PILOT_DATE = "2024-01-02"

# Locked upstream specification hashes (must remain immutable)
LOCKED_003B_SPEC_PATH = "docs/research/specs/DAYTRADE-003B-ORB-v1.json"
LOCKED_003B_SPEC_SHA256 = "62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0"

LOCKED_003C_RESOLUTION_PATH = "docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json"
LOCKED_003C_RESOLUTION_SHA256 = "20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6"

LOCKED_003D_SPEC_PATH = "docs/research/specs/DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json"
LOCKED_003D_SPEC_SHA256 = "533f6e3ef756cfbfa7bd49a4627fe960d9ba84546ea57bab2f57d7e385e2fb5c"

LOCKED_003D_CORR_001_SPEC_PATH = "docs/research/specs/DAYTRADE-003D-CORR-001-v1.json"
LOCKED_003D_CORR_001_SPEC_SHA256 = "d978a012851a597918a5e6965a72752be05b36f2f1d637179a9dede7d6ba1fbd"

CORR_002_SPEC_PATH = "docs/research/specs/DAYTRADE-003D-CORR-002-v1.json"
LOCKED_003D_CORR_002_SPEC_SHA256 = "d63cca87100cb80de86faf6c909766c3894b983fe3c486da99de3963f6eb311c"

DEFAULT_PRIVATE_ROOT = Path("C:/Users/Gary/.tradex/research/daytrade_003d_corr_002")

# Operational bounds
CANDIDATE_SCREENING_GATE_THRESHOLD = 0.95  # 95.0% completeness among daily-base-qualified


class PilotDisposition(str, Enum):
    """Prospective taxonomy for the final pilot disposition."""

    FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD = "FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD"
    BLOCKED_REFERENCE_OR_PROVIDER_ACCESS = "BLOCKED_REFERENCE_OR_PROVIDER_ACCESS"
    BLOCKED_PROVIDER_DATA_INTEGRITY = "BLOCKED_PROVIDER_DATA_INTEGRITY"
    BLOCKED_CANDIDATE_SCREENING_COVERAGE = "BLOCKED_CANDIDATE_SCREENING_COVERAGE"
    BLOCKED_STAGE_B_PRICE_PATH = "BLOCKED_STAGE_B_PRICE_PATH"
    INCONCLUSIVE_NO_ACTIONABLE_PILOT_CANDIDATE = "INCONCLUSIVE_NO_ACTIONABLE_PILOT_CANDIDATE"
    INVALID_CORR_002_IMPLEMENTATION = "INVALID_CORR_002_IMPLEMENTATION"


class CandidateScreeningOutcome(str, Enum):
    """Classification taxonomy for candidate screening among daily-base-qualified symbols."""

    NO_OPENING_PRINT_NO_SETUP = "NO_OPENING_PRINT_NO_SETUP"
    PRICE_REJECTED = "PRICE_REJECTED"
    UNRANKABLE_ZERO_RV_BASELINE = "UNRANKABLE_ZERO_RV_BASELINE"
    RV_REJECTED = "RV_REJECTED"
    ELIGIBLE = "ELIGIBLE"
    PROVIDER_DATA_FAILURE = "PROVIDER_DATA_FAILURE"


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def json_hash(obj: Any) -> str:
    serialized = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def verify_upstream_spec_hashes(repo_root: Path) -> tuple[bool, dict[str, str], list[str]]:
    """Verify SHA-256 hashes of all four prior specifications: 003B, 003C, 003D, and CORR-001."""
    expected = {
        LOCKED_003B_SPEC_PATH: LOCKED_003B_SPEC_SHA256,
        LOCKED_003C_RESOLUTION_PATH: LOCKED_003C_RESOLUTION_SHA256,
        LOCKED_003D_SPEC_PATH: LOCKED_003D_SPEC_SHA256,
        LOCKED_003D_CORR_001_SPEC_PATH: LOCKED_003D_CORR_001_SPEC_SHA256,
    }
    actual: dict[str, str] = {}
    errors: list[str] = []

    for rel_path, exp_hash in expected.items():
        p = repo_root / rel_path
        if not p.exists():
            errors.append(f"Missing spec file: {rel_path}")
            actual[rel_path] = ""
        else:
            h = hash_bytes(p.read_bytes())
            actual[rel_path] = h
            if h != exp_hash:
                errors.append(f"Spec hash mismatch for {rel_path}: expected {exp_hash}, got {h}")

    return len(errors) == 0, actual, errors


@dataclass(frozen=True)
class BroadDailyAvailabilityAudit:
    """Safe summary of broad PIT universe daily data availability."""

    canonical_target_universe_count: int
    daily_computable_count: int
    daily_availability_pct: float
    missing_daily_data_count: int
    daily_base_qualified_count: int
    adv_min: float = 1_000_000.0
    atr_min: float = 0.50


def audit_broad_daily_availability(
    valid_target_symbols: list[str],
    ambiguous_symbols: list[str],
    daily_bars_by_symbol: dict[str, list[DailyBar]],
    target_session: date,
    lookback: int = 14,
    adv_min: float = 1_000_000.0,
    atr_min: float = 0.50,
) -> tuple[BroadDailyAvailabilityAudit, list[str], list[str]]:
    """Audit daily data availability across the broad target universe and find daily-base-qualified symbols.

    Returns:
        (audit, computable_symbols, daily_base_qualified_symbols)
    """
    total_canonical = len(valid_target_symbols) + len(ambiguous_symbols)
    computable_symbols: list[str] = []
    daily_base_qualified_symbols: list[str] = []

    for sym in valid_target_symbols:
        bars = daily_bars_by_symbol.get(sym, [])
        if len(bars) < lookback + 1:
            continue
        adv = compute_adv14(bars, target_session, lookback=lookback)
        atr = compute_atr14_wilder(bars, target_session, lookback=lookback)
        if adv is None or atr is None:
            continue
        computable_symbols.append(sym)
        if adv >= adv_min and atr > atr_min:
            daily_base_qualified_symbols.append(sym)

    computable_count = len(computable_symbols)
    avail_pct = (
        (computable_count / float(total_canonical) * 100.0)
        if total_canonical > 0
        else 0.0
    )
    missing_count = total_canonical - computable_count

    audit = BroadDailyAvailabilityAudit(
        canonical_target_universe_count=total_canonical,
        daily_computable_count=computable_count,
        daily_availability_pct=round(avail_pct, 4),
        missing_daily_data_count=missing_count,
        daily_base_qualified_count=len(daily_base_qualified_symbols),
        adv_min=adv_min,
        atr_min=atr_min,
    )
    return audit, computable_symbols, daily_base_qualified_symbols


@dataclass(frozen=True)
class CandidateScreeningAudit:
    """Safe audit of candidate-screening completeness among daily-base-qualified symbols."""

    daily_base_qualified_count: int
    validly_determined_count: int
    screening_completeness_pct: float
    screening_gate_threshold_pct: float
    meets_screening_gate: bool
    outcome_distribution: dict[str, int]
    no_opening_print_count: int
    zero_rv_baseline_count: int
    provider_failure_count: int
    eligible_candidate_count: int


@dataclass(frozen=True)
class FrozenSelectionEvidence:
    """Cryptographic evidence of the frozen Top-20 selection."""

    eligible_candidates_count: int
    selected_count: int
    doji_count: int
    selection_sha256: str


def freeze_top_20_selection(
    ranked_candidates: list[RankedCandidate],
) -> tuple[FrozenSelectionEvidence, list[dict[str, Any]], list[str]]:
    """Serialize and hash the frozen Top-20 selection without disclosing ticker identities in public summaries."""
    records: list[dict[str, Any]] = []
    selected_symbols: list[str] = []
    doji_count = 0

    for rc in ranked_candidates:
        sym = rc.candidate.symbol
        selected_symbols.append(sym)
        is_doji = rc.order_intent.status == OrderStatus.NO_ORDER_DOJI
        if is_doji:
            doji_count += 1

        rec = {
            "rank": rc.rank,
            "symbol": sym,
            "session_date": str(rc.candidate.session_date),
            "opening_price": rc.candidate.opening_price,
            "adv14": rc.candidate.adv14,
            "atr14": rc.candidate.atr14,
            "or_volume": rc.candidate.or_volume,
            "mean_prior_or_volume": rc.candidate.mean_prior_or_volume,
            "relative_volume": rc.candidate.relative_volume,
            "direction": rc.opening_range.direction.value,
            "stop_level": rc.opening_range.stop_level,
            "order_intent_status": rc.order_intent.status.value,
            "desired_shares": rc.order_intent.desired_shares,
            "risk_per_share": rc.order_intent.risk_per_share,
        }
        records.append(rec)

    sel_hash = json_hash(records)
    evidence = FrozenSelectionEvidence(
        eligible_candidates_count=len(ranked_candidates),
        selected_count=len(records),
        doji_count=doji_count,
        selection_sha256=sel_hash,
    )
    return evidence, records, selected_symbols


@dataclass(frozen=True)
class StageBPathAudit:
    """Safe audit of Stage-B price path availability and evaluator compatibility."""

    selected_actionable_symbols_count: int
    total_expected_minutes: int
    total_actual_bars: int
    total_sparse_minutes: int
    missing_eod_bar_symbols_count: int
    provider_failure_count: int
    is_usable: bool
    unusable_reason: str


def audit_candidate_screening(
    daily_base_qualified_symbols: list[str],
    current_or_by_symbol: dict[str, OpeningRange | None],
    current_or_provider_failures: set[str],
    prior_or_obs_by_symbol: dict[str, list[OpeningRangeVolumeObservation]],
    prior_or_provider_failures: set[str],
    daily_bars_by_symbol: dict[str, list[DailyBar]],
    target_session: date,
    price_min: float = 5.0,
    adv_min: float = 1_000_000.0,
    atr_min: float = 0.50,
    rv_min: float = 1.0,
    gate_threshold: float = CANDIDATE_SCREENING_GATE_THRESHOLD,
) -> tuple[
    CandidateScreeningAudit,
    dict[str, CandidateScreeningOutcome],
    list[Candidate],
    dict[str, OpeningRange],
]:
    """Audit candidate-screening completeness among daily-base-qualified symbols.

    Returns:
        (audit, outcomes_by_symbol, eligible_candidates, surviving_opening_ranges)
    """
    total_daily_base = len(daily_base_qualified_symbols)
    outcomes: dict[str, CandidateScreeningOutcome] = {}
    eligible_candidates: list[Candidate] = []
    surviving_opening_ranges: dict[str, OpeningRange] = {}

    for sym in daily_base_qualified_symbols:
        # Check current opening range request failure
        if sym in current_or_provider_failures:
            outcomes[sym] = CandidateScreeningOutcome.PROVIDER_DATA_FAILURE
            continue

        cur_or = current_or_by_symbol.get(sym)
        if cur_or is None:
            # Verified completed provider response with zero trades in 09:30-09:34
            outcomes[sym] = CandidateScreeningOutcome.NO_OPENING_PRINT_NO_SETUP
            continue

        # Check price filter (> 5.0)
        if cur_or.or_open <= price_min:
            outcomes[sym] = CandidateScreeningOutcome.PRICE_REJECTED
            continue

        # Surviving symbol that needs RV
        if sym in prior_or_provider_failures:
            outcomes[sym] = CandidateScreeningOutcome.PROVIDER_DATA_FAILURE
            continue

        prior_obs = prior_or_obs_by_symbol.get(sym, [])
        rv, mean_vol = compute_relative_volume(prior_obs, cur_or.or_volume, target_session)
        if mean_vol is None or (rv is None and mean_vol > 0):
            # Incomplete prior observations (fewer than 14 sessions or invalid)
            outcomes[sym] = CandidateScreeningOutcome.PROVIDER_DATA_FAILURE
            continue

        if mean_vol == 0.0:
            # Undefined RV baseline: all 14 prior sessions had zero 5-minute volume
            outcomes[sym] = CandidateScreeningOutcome.UNRANKABLE_ZERO_RV_BASELINE
            continue

        # Valid RV computed
        daily_bars = daily_bars_by_symbol.get(sym, [])
        adv14 = compute_adv14(daily_bars, target_session)
        atr14 = compute_atr14_wilder(daily_bars, target_session)
        cand = evaluate_candidate(
            symbol=sym,
            session_date=target_session,
            opening_range=cur_or,
            adv14=adv14,
            atr14=atr14,
            mean_prior_or_volume=mean_vol,
            rv=rv,
            price_min=price_min,
            adv_min=adv_min,
            atr_min=atr_min,
            rv_min=rv_min,
        )

        if cand.is_eligible:
            outcomes[sym] = CandidateScreeningOutcome.ELIGIBLE
            eligible_candidates.append(cand)
            surviving_opening_ranges[sym] = cur_or
        else:
            outcomes[sym] = CandidateScreeningOutcome.RV_REJECTED

    validly_determined = sum(
        1 for o in outcomes.values() if o != CandidateScreeningOutcome.PROVIDER_DATA_FAILURE
    )
    provider_failures = sum(
        1 for o in outcomes.values() if o == CandidateScreeningOutcome.PROVIDER_DATA_FAILURE
    )
    completeness_pct = (
        (validly_determined / float(total_daily_base) * 100.0) if total_daily_base > 0 else 0.0
    )
    meets_gate = completeness_pct >= (gate_threshold * 100.0)

    audit = CandidateScreeningAudit(
        daily_base_qualified_count=total_daily_base,
        validly_determined_count=validly_determined,
        screening_completeness_pct=round(completeness_pct, 4),
        screening_gate_threshold_pct=round(gate_threshold * 100.0, 2),
        meets_screening_gate=meets_gate,
        outcome_distribution=dict(sorted(Counter(o.value for o in outcomes.values()).items())),
        no_opening_print_count=sum(
            1 for o in outcomes.values() if o == CandidateScreeningOutcome.NO_OPENING_PRINT_NO_SETUP
        ),
        zero_rv_baseline_count=sum(
            1
            for o in outcomes.values()
            if o == CandidateScreeningOutcome.UNRANKABLE_ZERO_RV_BASELINE
        ),
        provider_failure_count=provider_failures,
        eligible_candidate_count=len(eligible_candidates),
    )
    return audit, outcomes, eligible_candidates, surviving_opening_ranges


def audit_stage_b_price_path(
    active_selected_symbols: list[str],
    stage_b_bars_by_symbol: dict[str, list[MinuteBar]],
    stage_b_provider_failures: set[str],
    expected_minutes: int = 385,
) -> StageBPathAudit:
    """Audit Stage-B minute bar availability, sparse intervals, and EOD liquidation bar presence."""
    from datetime import time

    total_expected = len(active_selected_symbols) * expected_minutes
    total_actual = 0
    total_sparse = 0
    missing_eod_symbols = 0
    failures = len(stage_b_provider_failures)

    for sym in active_selected_symbols:
        if sym in stage_b_provider_failures:
            total_sparse += expected_minutes
            missing_eod_symbols += 1
            continue
        bars = stage_b_bars_by_symbol.get(sym, [])
        total_actual += len(bars)
        sparse_mins = max(0, expected_minutes - len(bars))
        total_sparse += sparse_mins

        has_1559 = any(
            b.timestamp.astimezone(MARKET_TIMEZONE).time() == time(15, 59)
            for b in bars
        )
        if not has_1559:
            missing_eod_symbols += 1

    is_usable = failures == 0
    unusable_reason = ""
    if failures > 0:
        unusable_reason = f"Stage-B provider request failed for {failures} symbol(s)"

    return StageBPathAudit(
        selected_actionable_symbols_count=len(active_selected_symbols),
        total_expected_minutes=total_expected,
        total_actual_bars=total_actual,
        total_sparse_minutes=total_sparse,
        missing_eod_bar_symbols_count=missing_eod_symbols,
        provider_failure_count=failures,
        is_usable=is_usable,
        unusable_reason=unusable_reason,
    )


def determine_pilot_disposition(
    reference_success: bool,
    provider_access_success: bool,
    provider_data_integrity_success: bool,
    candidate_screening_gate_passed: bool,
    eligible_candidate_count: int,
    stage_b_path_usable: bool,
    implementation_defect: bool = False,
) -> tuple[PilotDisposition, list[str]]:
    """Determine final pilot disposition using strict prospective taxonomy and precedence."""
    blocker_details: list[str] = []

    if implementation_defect:
        blocker_details.append("Material implementation defect detected")
        return PilotDisposition.INVALID_CORR_002_IMPLEMENTATION, blocker_details

    if not reference_success or not provider_access_success:
        blocker_details.append("Failed reference retrieval or provider capability access")
        return PilotDisposition.BLOCKED_REFERENCE_OR_PROVIDER_ACCESS, blocker_details

    if not provider_data_integrity_success:
        blocker_details.append("Provider data integrity failure (malformed or corrupt response)")
        return PilotDisposition.BLOCKED_PROVIDER_DATA_INTEGRITY, blocker_details

    if not candidate_screening_gate_passed:
        blocker_details.append("Candidate-screening completeness gate (< 95.0%) failed")
        return PilotDisposition.BLOCKED_CANDIDATE_SCREENING_COVERAGE, blocker_details

    if eligible_candidate_count == 0:
        blocker_details.append("No actionable candidate met all ORB eligibility filters on pilot session")
        return PilotDisposition.INCONCLUSIVE_NO_ACTIONABLE_PILOT_CANDIDATE, blocker_details

    if not stage_b_path_usable:
        blocker_details.append("Stage-B price path unusable under evaluator compatibility rules")
        return PilotDisposition.BLOCKED_STAGE_B_PRICE_PATH, blocker_details

    return PilotDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD, []

