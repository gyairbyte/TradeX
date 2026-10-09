"""Corrected ORB real-data feasibility pilot logic for DAYTRADE-003D-CORR-001.

Implements practical missing-data handling, 95% Stage-A coverage gate,
fail-closed duplicate canonical symbol resolution, corrected 5,000-page runaway
guard, and bounded 2024-01-02 pilot execution without strategy simulation or PnL.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from tradex.research.daytrade_orb.indicators import (
    compute_adv14,
    compute_atr14_wilder,
    compute_relative_volume,
    get_prior_xnys_sessions,
)
from tradex.research.daytrade_orb.models import (
    DailyBar,
    MinuteBar,
    OpeningRange,
    OpeningRangeVolumeObservation,
)
from tradex.research.daytrade_orb.ranking import (
    evaluate_candidate,
    rank_and_select_top_20,
)

logger = logging.getLogger(__name__)

MARKET_TIMEZONE = ZoneInfo("America/New_York")

TASK_ID = "DAYTRADE-003D-CORR-001"
STRATEGY_ID = "DAYTRADE-003B-ORB-SIP5M"
PILOT_DATE = "2024-01-02"

LOCKED_003B_SPEC_PATH = "docs/research/specs/DAYTRADE-003B-ORB-v1.json"
LOCKED_003B_SPEC_SHA256 = "62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0"

LOCKED_003C_RESOLUTION_PATH = "docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json"
LOCKED_003C_RESOLUTION_SHA256 = "20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6"

LOCKED_003D_SPEC_PATH = "docs/research/specs/DAYTRADE-003D-ORB-DATA-FEASIBILITY-v1.json"
LOCKED_003D_SPEC_SHA256 = "533f6e3ef756cfbfa7bd49a4627fe960d9ba84546ea57bab2f57d7e385e2fb5c"

TARGET_EXCHANGE_MAPPING: tuple[str, ...] = ("XNYS", "XNAS")

DEFAULT_BATCH_SIZE = 100
MAX_PILOT_PAGES_LIMIT = 5000
MAX_PILOT_STORAGE_BYTES_LIMIT = 2 * 1024 * 1024 * 1024  # 2 GB
STAGE_A_COVERAGE_THRESHOLD = 0.95  # 95.0%

DEFAULT_PRIVATE_ROOT = Path("C:/Users/Gary/.tradex/research/daytrade_003d_corr_001")


class PilotDisposition(str, Enum):
    """Preregistered pilot disposition outcomes in fixed precedence order."""

    FEASIBLE_FOR_2024_DEVELOPMENT_DATASET = "FEASIBLE_FOR_2024_DEVELOPMENT_DATASET"
    BLOCKED_MASSIVE_REFERENCE = "BLOCKED_MASSIVE_REFERENCE"
    BLOCKED_PROVIDER_BATCH_CAPABILITY = "BLOCKED_PROVIDER_BATCH_CAPABILITY"
    BLOCKED_ALPACA_SIP = "BLOCKED_ALPACA_SIP"
    BLOCKED_STAGE_A_COVERAGE = "BLOCKED_STAGE_A_COVERAGE"
    BLOCKED_STAGE_B_COVERAGE = "BLOCKED_STAGE_B_COVERAGE"
    INVALID_CORRECTED_PROBE_IMPLEMENTATION = "INVALID_CORRECTED_PROBE_IMPLEMENTATION"


class UnavailableReason(str, Enum):
    """Taxonomy of prospective data-availability classifications for Stage A."""

    AMBIGUOUS_IDENTITY = "AMBIGUOUS_IDENTITY"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    CROSS_PROVIDER_UNMAPPED = "CROSS_PROVIDER_UNMAPPED"
    MISSING_DAILY_DATA = "MISSING_DAILY_DATA"
    MISSING_PRIOR_OR_DATA = "MISSING_PRIOR_OR_DATA"
    MISSING_CURRENT_OR_DATA = "MISSING_CURRENT_OR_DATA"
    MALFORMED_DATA = "MALFORMED_DATA"


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def json_hash(obj: Any) -> str:
    serialized = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def verify_all_upstream_spec_hashes(repo_root: Path) -> tuple[bool, dict[str, str], list[str]]:
    """Verify SHA-256 hashes of DAYTRADE-003B, DAYTRADE-003C, and DAYTRADE-003D specifications."""
    expected = {
        LOCKED_003B_SPEC_PATH: LOCKED_003B_SPEC_SHA256,
        LOCKED_003C_RESOLUTION_PATH: LOCKED_003C_RESOLUTION_SHA256,
        LOCKED_003D_SPEC_PATH: LOCKED_003D_SPEC_SHA256,
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


def resolve_ticker_duplicates(
    ticker: str,
    rows: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any] | None]:
    """Determine if duplicate rows for a canonical ticker can be proven identical.

    Returns:
        (is_identical, collapsed_row): True and the collapsed representative row
        if proven identical using provider identity metadata; False and None if
        ambiguous.
    """
    if len(rows) <= 1:
        return True, rows[0] if rows else None

    # Check exchange, type, active
    exchanges = {str(r.get("primary_exchange") or "").strip().upper() for r in rows}
    types = {str(r.get("type") or "").strip().upper() for r in rows}
    actives = {bool(r.get("active", True)) for r in rows}

    if len(exchanges) > 1 or len(types) > 1 or len(actives) > 1:
        return False, None

    # Strong identity fields
    strong_fields = ("composite_figi", "share_class_figi", "figi", "cik")
    has_matching_strong_id = False

    for field in strong_fields:
        vals = {str(r.get(field) or "").strip() for r in rows if r.get(field)}
        if len(vals) > 1:
            # Conflicting values for the same strong identity field
            return False, None
        if len(vals) == 1 and "" not in vals:
            has_matching_strong_id = True

    if not has_matching_strong_id:
        # Check if all row fields across all keys are completely identical
        canon_rows = [{k: str(v).strip() for k, v in r.items() if v is not None} for r in rows]
        first = canon_rows[0]
        if all(r == first for r in canon_rows[1:]):
            has_matching_strong_id = True
        else:
            return False, None

    # Proven identical: select deterministically
    sorted_rows = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))
    return True, sorted_rows[0]


@dataclass(frozen=True)
class TargetUniverseAudit:
    """Audit results for canonical target universe filtering and duplicate handling."""

    date: str
    total_snapshot_rows: int
    target_filtered_rows: int
    canonical_target_universe_count: int  # Denominator: valid + ambiguous symbols
    valid_target_symbols: list[str]  # Computable candidate pool symbols to query
    ambiguous_symbols: list[str]  # AMBIGUOUS_IDENTITY symbols (excluded from Stage A)
    collapsed_duplicates_count: int
    blank_ticker_count: int
    duplicate_ticker_count: int
    target_exchange_distribution: dict[str, int]
    excluded_exchange_distribution: dict[str, int]
    type_distribution: dict[str, int]
    universe_sha256: str


def filter_and_audit_target_universe(
    rows: list[dict[str, Any]],
    allowed_exchanges: tuple[str, ...] = TARGET_EXCHANGE_MAPPING,
) -> tuple[TargetUniverseAudit, dict[str, dict[str, Any]]]:
    """Filter Massive snapshot rows by exchange and resolve duplicates with fail-closed integrity.

    Returns:
        (audit, target_rows_by_symbol)
    """
    allowed_set = {x.upper() for x in allowed_exchanges}
    target_rows_by_ticker: dict[str, list[dict[str, Any]]] = {}
    target_exchange_counts: Counter[str] = Counter()
    excluded_exchange_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()

    blank_count = 0
    all_ticker_occurrences: Counter[str] = Counter()

    for r in rows:
        raw_ticker = str(r.get("ticker") or "").strip()
        if not raw_ticker:
            blank_count += 1
            continue
        ticker = raw_ticker.upper()
        all_ticker_occurrences[ticker] += 1

        ex = str(r.get("primary_exchange") or "").strip().upper()
        sec_type = str(r.get("type") or "").strip().upper() or "EMPTY"

        if ex in allowed_set:
            target_exchange_counts[ex] += 1
            type_counts[sec_type] += 1
            target_rows_by_ticker.setdefault(ticker, []).append(r)
        else:
            excluded_exchange_counts[ex or "EMPTY"] += 1

    valid_symbols: list[str] = []
    ambiguous_symbols: list[str] = []
    target_rows_map: dict[str, dict[str, Any]] = {}
    collapsed_count = 0

    for ticker, ticker_rows in sorted(target_rows_by_ticker.items()):
        if len(ticker_rows) == 1:
            valid_symbols.append(ticker)
            target_rows_map[ticker] = ticker_rows[0]
        else:
            is_identical, collapsed_row = resolve_ticker_duplicates(ticker, ticker_rows)
            if is_identical and collapsed_row is not None:
                valid_symbols.append(ticker)
                target_rows_map[ticker] = collapsed_row
                collapsed_count += 1
            else:
                # Ambiguous identity: excluded from candidate ranking, counted in denominator
                ambiguous_symbols.append(ticker)

    valid_symbols.sort()
    ambiguous_symbols.sort()

    total_target_count = len(valid_symbols) + len(ambiguous_symbols)
    total_duplicate_tickers = sum(1 for c in all_ticker_occurrences.values() if c > 1)

    # Cryptographic hash of canonical target symbols (both valid and ambiguous)
    all_target_canonical = sorted(valid_symbols + ambiguous_symbols)
    universe_hash = json_hash(all_target_canonical)

    audit = TargetUniverseAudit(
        date=str(rows[0].get("date", "")) if rows else "",
        total_snapshot_rows=len(rows),
        target_filtered_rows=sum(len(r) for r in target_rows_by_ticker.values()),
        canonical_target_universe_count=total_target_count,
        valid_target_symbols=valid_symbols,
        ambiguous_symbols=ambiguous_symbols,
        collapsed_duplicates_count=collapsed_count,
        blank_ticker_count=blank_count,
        duplicate_ticker_count=total_duplicate_tickers,
        target_exchange_distribution=dict(sorted(target_exchange_counts.items())),
        excluded_exchange_distribution=dict(
            sorted(excluded_exchange_counts.items(), key=lambda x: (-x[1], x[0]))
        ),
        type_distribution=dict(sorted(type_counts.items(), key=lambda x: (-x[1], x[0]))),
        universe_sha256=universe_hash,
    )
    return audit, target_rows_map


@dataclass(frozen=True)
class CorrectedPilotResourcePlan:
    """Operational runaway bounds and planned request sizing for the pilot."""

    universe_size: int
    batch_size: int
    batch_count: int
    daily_lookback_sessions: int
    or_lookback_sessions: int
    planned_daily_requests: int
    planned_or_requests: int
    planned_stage_b_requests: int
    total_planned_alpaca_pages: int
    massive_pages_actual: int
    total_planned_pages: int
    estimated_rows: int
    estimated_storage_bytes: int
    max_pages_limit: int
    max_storage_bytes_limit: int
    exceeds_pages_limit: bool
    exceeds_storage_limit: bool
    is_within_bounds: bool


def calculate_corrected_resource_plan(
    universe_size: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    daily_lookback_sessions: int = 20,
    or_lookback_sessions: int = 14,
    massive_pages_actual: int = 12,
    max_pages_limit: int = MAX_PILOT_PAGES_LIMIT,
    max_storage_bytes_limit: int = MAX_PILOT_STORAGE_BYTES_LIMIT,
) -> CorrectedPilotResourcePlan:
    """Calculate projected provider calls and enforce broad 5,000-page runaway bounds."""
    batch_count = math.ceil(universe_size / batch_size) if universe_size > 0 else 0

    # Daily bars: 1 call per batch for 20 XNYS sessions in Dec 2023
    planned_daily_requests = batch_count

    # Opening range bars: 1 call per batch per session for 15 sessions (14 prior + current D)
    total_or_sessions = or_lookback_sessions + 1  # 15
    planned_or_requests = batch_count * total_or_sessions

    # Stage B: 20 symbols for 385 minutes = 7,700 bars -> 1 call/page
    planned_stage_b_requests = 1

    total_planned_alpaca_pages = (
        planned_daily_requests + planned_or_requests + planned_stage_b_requests
    )
    total_planned_pages = total_planned_alpaca_pages + massive_pages_actual

    # Estimated rows
    estimated_rows = (
        (universe_size * daily_lookback_sessions)
        + (universe_size * total_or_sessions * 5)
        + 7700
    )
    estimated_storage_bytes = estimated_rows * 200

    exceeds_pages = total_planned_pages > max_pages_limit
    exceeds_storage = estimated_storage_bytes > max_storage_bytes_limit

    return CorrectedPilotResourcePlan(
        universe_size=universe_size,
        batch_size=batch_size,
        batch_count=batch_count,
        daily_lookback_sessions=daily_lookback_sessions,
        or_lookback_sessions=or_lookback_sessions,
        planned_daily_requests=planned_daily_requests,
        planned_or_requests=planned_or_requests,
        planned_stage_b_requests=planned_stage_b_requests,
        total_planned_alpaca_pages=total_planned_alpaca_pages,
        massive_pages_actual=massive_pages_actual,
        total_planned_pages=total_planned_pages,
        estimated_rows=estimated_rows,
        estimated_storage_bytes=estimated_storage_bytes,
        max_pages_limit=max_pages_limit,
        max_storage_bytes_limit=max_storage_bytes_limit,
        exceeds_pages_limit=exceeds_pages,
        exceeds_storage_limit=exceeds_storage,
        is_within_bounds=(not exceeds_pages and not exceeds_storage),
    )


def batch_symbols(symbols: list[str], batch_size: int = DEFAULT_BATCH_SIZE) -> list[list[str]]:
    """Partition a list of symbols into deterministic, bounded batches."""
    sorted_syms = sorted({s.strip().upper() for s in symbols if s.strip()})
    return [sorted_syms[i : i + batch_size] for i in range(0, len(sorted_syms), batch_size)]


@dataclass(frozen=True)
class StageACoverageAudit:
    """Safe audit summary of Stage-A computability and the 95% coverage gate."""

    canonical_target_universe_count: int
    computable_stage_a_symbols_count: int
    stage_a_coverage_pct: float
    coverage_threshold_pct: float
    meets_coverage_threshold: bool
    unavailable_counts_by_reason: dict[str, int]


def audit_stage_a_coverage(
    valid_target_symbols: list[str],
    ambiguous_symbols: list[str],
    daily_bars_by_symbol: dict[str, list[DailyBar]],
    prior_or_obs_by_symbol: dict[str, list[OpeningRangeVolumeObservation]],
    current_or_by_symbol: dict[str, OpeningRange],
    target_session: date,
    required_lookback: int = 14,
    coverage_threshold: float = STAGE_A_COVERAGE_THRESHOLD,
) -> tuple[StageACoverageAudit, dict[str, str], list[str]]:
    """Audit Stage-A candidate pool computability and evaluate the 95% coverage gate.

    Returns:
        (audit, unavailable_reasons_by_symbol, computable_symbols)
    """
    expected_prior_sessions = get_prior_xnys_sessions(target_session, required_lookback)
    expected_prior_set = set(expected_prior_sessions)

    total_target_count = len(valid_target_symbols) + len(ambiguous_symbols)
    reasons_by_symbol: dict[str, str] = {}
    reason_counts: Counter[str] = Counter()
    computable_symbols: list[str] = []

    # 1. Ambiguous duplicates are automatically unavailable
    for sym in ambiguous_symbols:
        reason = UnavailableReason.AMBIGUOUS_IDENTITY.value
        reasons_by_symbol[sym] = reason
        reason_counts[reason] += 1

    # 2. Audit valid target symbols
    for sym in valid_target_symbols:
        daily_bars = daily_bars_by_symbol.get(sym, [])
        prior_or = prior_or_obs_by_symbol.get(sym, [])
        current_or = current_or_by_symbol.get(sym)

        # Check for cross-provider unmapped / missing completely
        if not daily_bars and not prior_or and current_or is None:
            reason = UnavailableReason.CROSS_PROVIDER_UNMAPPED.value
            reasons_by_symbol[sym] = reason
            reason_counts[reason] += 1
            continue

        # Check for listing history age / IPO
        if len(daily_bars) < required_lookback + 1:
            reason = UnavailableReason.INSUFFICIENT_HISTORY.value
            reasons_by_symbol[sym] = reason
            reason_counts[reason] += 1
            continue

        # Check daily indicators
        adv = compute_adv14(daily_bars, target_session, lookback=required_lookback)
        atr = compute_atr14_wilder(daily_bars, target_session, lookback=required_lookback)
        if adv is None or atr is None:
            reason = UnavailableReason.MISSING_DAILY_DATA.value
            reasons_by_symbol[sym] = reason
            reason_counts[reason] += 1
            continue

        # Check prior opening range observations
        prior_dates = {obs.session_date for obs in prior_or}
        has_prior_or = expected_prior_set.issubset(prior_dates) and len(prior_or) >= required_lookback
        if not has_prior_or:
            reason = UnavailableReason.MISSING_PRIOR_OR_DATA.value
            reasons_by_symbol[sym] = reason
            reason_counts[reason] += 1
            continue

        # Check current session opening range
        if current_or is None:
            reason = UnavailableReason.MISSING_CURRENT_OR_DATA.value
            reasons_by_symbol[sym] = reason
            reason_counts[reason] += 1
            continue

        # Check for malformed data
        is_malformed = (
            adv < 0
            or atr <= 0
            or current_or.or_open <= 0
            or current_or.or_high <= 0
            or current_or.or_low <= 0
            or current_or.or_close <= 0
            or current_or.or_high < current_or.or_low
            or current_or.or_volume < 0
        )
        if is_malformed:
            reason = UnavailableReason.MALFORMED_DATA.value
            reasons_by_symbol[sym] = reason
            reason_counts[reason] += 1
            continue

        # Fully computable!
        computable_symbols.append(sym)

    computable_count = len(computable_symbols)
    coverage_pct = (
        (computable_count / float(total_target_count) * 100.0)
        if total_target_count > 0
        else 0.0
    )
    meets_threshold = coverage_pct >= (coverage_threshold * 100.0)

    audit = StageACoverageAudit(
        canonical_target_universe_count=total_target_count,
        computable_stage_a_symbols_count=computable_count,
        stage_a_coverage_pct=round(coverage_pct, 4),
        coverage_threshold_pct=round(coverage_threshold * 100.0, 2),
        meets_coverage_threshold=meets_threshold,
        unavailable_counts_by_reason=dict(sorted(reason_counts.items())),
    )
    return audit, reasons_by_symbol, computable_symbols


@dataclass(frozen=True)
class CorrectedStageASelectionEvidence:
    """Safe cryptographic summary of the frozen Stage-A Top-20 selection."""

    eligible_candidates_count: int
    selected_count: int
    selection_sha256: str
    selection_timestamp: str
    doji_count: int


def compute_and_freeze_corrected_stage_a_selection(
    computable_symbols: list[str],
    daily_bars_by_symbol: dict[str, list[DailyBar]],
    prior_or_obs_by_symbol: dict[str, list[OpeningRangeVolumeObservation]],
    current_or_by_symbol: dict[str, OpeningRange],
    target_session: date,
    session_start_equity: float = 25000.0,
    top_n: int = 20,
) -> tuple[CorrectedStageASelectionEvidence, list[dict[str, Any]], list[str]]:
    """Compute indicator filters, rank by RV descending, and freeze Top 20 selection artifact."""
    candidates = []
    for sym in computable_symbols:
        daily_bars = daily_bars_by_symbol.get(sym, [])
        prior_or = prior_or_obs_by_symbol.get(sym, [])
        current_or = current_or_by_symbol.get(sym)

        if not current_or:
            continue

        adv14 = compute_adv14(daily_bars, target_session, lookback=14)
        atr14 = compute_atr14_wilder(daily_bars, target_session, lookback=14)
        rv, mean_prior_vol = compute_relative_volume(
            prior_or,
            current_or.or_volume,
            target_session,
            lookback=14,
        )

        cand = evaluate_candidate(
            symbol=sym,
            session_date=target_session,
            opening_range=current_or,
            adv14=adv14,
            atr14=atr14,
            mean_prior_or_volume=mean_prior_vol,
            rv=rv,
        )
        candidates.append(cand)

    ranked = rank_and_select_top_20(
        candidates=candidates,
        opening_ranges=current_or_by_symbol,
        session_start_equity=session_start_equity,
        top_n=top_n,
    )

    selection_records: list[dict[str, Any]] = []
    selected_symbols: list[str] = []
    doji_count = 0

    for rc in ranked:
        selected_symbols.append(rc.candidate.symbol)
        if rc.opening_range.direction.value == "DOJI":
            doji_count += 1
        selection_records.append({
            "rank": rc.rank,
            "symbol": rc.candidate.symbol,
            "relative_volume": rc.candidate.relative_volume,
            "opening_price": rc.candidate.opening_price,
            "adv14": rc.candidate.adv14,
            "atr14": rc.candidate.atr14,
            "order_intent_status": rc.order_intent.status.value,
            "desired_shares": rc.order_intent.desired_shares,
            "stop_level": rc.order_intent.stop_level,
        })

    selection_sha = json_hash(selection_records)
    timestamp = datetime.now(UTC).isoformat()

    evidence = CorrectedStageASelectionEvidence(
        eligible_candidates_count=sum(1 for c in candidates if c.is_eligible),
        selected_count=len(ranked),
        selection_sha256=selection_sha,
        selection_timestamp=timestamp,
        doji_count=doji_count,
    )
    return evidence, selection_records, selected_symbols


@dataclass(frozen=True)
class CorrectedStageBAuditEvidence:
    """Safe audit summary of the 09:35..15:59 regular-session path for selected Top 20."""

    symbols_count: int
    expected_minutes_per_symbol: int
    total_expected_bars: int
    total_observed_bars: int
    missing_minutes_count: int
    duplicate_minutes_count: int
    malformed_bars_count: int
    path_complete: bool


def audit_corrected_stage_b_path(
    selected_symbols: list[str],
    bars_by_symbol: dict[str, list[MinuteBar]],
    target_session: date,
    expected_start_time: str = "09:35",
    expected_end_time: str = "15:59",
) -> tuple[CorrectedStageBAuditEvidence, dict[str, list[str]]]:
    """Audit the complete 09:35..15:59 regular-session path for selected Top-20 symbols."""
    expected_times: list[datetime] = []
    curr_dt = datetime(
        target_session.year,
        target_session.month,
        target_session.day,
        9,
        35,
        tzinfo=MARKET_TIMEZONE,
    )
    end_dt = datetime(
        target_session.year,
        target_session.month,
        target_session.day,
        15,
        59,
        tzinfo=MARKET_TIMEZONE,
    )
    while curr_dt <= end_dt:
        expected_times.append(curr_dt)
        curr_dt = curr_dt + pd.Timedelta(minutes=1)

    expected_minutes_per_sym = len(expected_times)  # 385
    total_expected = len(selected_symbols) * expected_minutes_per_sym

    observed_count = 0
    missing_minutes = 0
    duplicate_minutes = 0
    malformed_bars = 0
    missing_by_sym: dict[str, list[str]] = {}

    for sym in selected_symbols:
        bars = bars_by_symbol.get(sym, [])
        observed_count += len(bars)
        bars_by_time: dict[datetime, MinuteBar] = {}
        for b in bars:
            et_dt = b.timestamp.astimezone(MARKET_TIMEZONE)
            if et_dt in bars_by_time:
                duplicate_minutes += 1
            bars_by_time[et_dt] = b
            if b.open <= 0 or b.high < b.low or b.volume < 0:
                malformed_bars += 1

        sym_missing = []
        for exp in expected_times:
            if exp not in bars_by_time:
                missing_minutes += 1
                sym_missing.append(exp.strftime("%H:%M"))
        if sym_missing:
            missing_by_sym[sym] = sym_missing

    path_complete = (
        len(selected_symbols) > 0
        and missing_minutes == 0
        and duplicate_minutes == 0
        and malformed_bars == 0
    )

    evidence = CorrectedStageBAuditEvidence(
        symbols_count=len(selected_symbols),
        expected_minutes_per_symbol=expected_minutes_per_sym,
        total_expected_bars=total_expected,
        total_observed_bars=observed_count,
        missing_minutes_count=missing_minutes,
        duplicate_minutes_count=duplicate_minutes,
        malformed_bars_count=malformed_bars,
        path_complete=path_complete,
    )
    return evidence, missing_by_sym


def write_pilot_summary_artifact(
    output_path: Path,
    summary_data: dict[str, Any],
) -> None:
    """Write safe pilot summary artifact ensuring no symbols, OHLC, or secrets are leaked."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary_data, indent=2, sort_keys=True), encoding="utf-8")
