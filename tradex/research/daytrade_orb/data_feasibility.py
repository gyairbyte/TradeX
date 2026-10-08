"""Deterministic real-data acquisition and feasibility probe logic for DAYTRADE-003D.

Research-only probe verifying source-faithful feasibility of constructing the
two-stage Stocks-in-Play 5-minute ORB dataset using Massive reference data
and Alpaca SIP bars, without strategy evaluation, trade simulation, or PnL inspection.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from tradex.research.daytrade_orb.dataset_contract import (
    TwoStageDatasetManifest,
    compute_manifest_sha256,
    manifest_to_json,
    validate_dataset_manifest_invariants,
)
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

TASK_ID = "DAYTRADE-003D-ORB-DATA-FEASIBILITY-001"
STRATEGY_ID = "DAYTRADE-003B-ORB-SIP5M"

LOCKED_003B_SPEC_PATH = "docs/research/specs/DAYTRADE-003B-ORB-v1.json"
LOCKED_003B_SPEC_SHA256 = "62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0"

LOCKED_003C_RESOLUTION_PATH = "docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json"
LOCKED_003C_RESOLUTION_SHA256 = "20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6"

PROBE_DATES = ("2024-01-02", "2024-06-03", "2024-12-02")
PILOT_DATE = "2024-01-02"

TARGET_EXCHANGE_MAPPING: tuple[str, ...] = ("XNYS", "XNAS")
EXCLUDED_KNOWN_EXCHANGES: tuple[str, ...] = ("ARCX", "BATS", "XASE", "XBOS", "OTCM")

DEFAULT_BATCH_SIZE = 100
SAFETY_MAX_PAGES = 50
MAX_PILOT_PAGES_LIMIT = 1000
MAX_PILOT_STORAGE_BYTES_LIMIT = 2 * 1024 * 1024 * 1024  # 2 GB

DEFAULT_PRIVATE_ROOT = Path("C:/Users/Gary/.tradex/research/daytrade_003d_orb_probe")


class FeasibilityDisposition(str, Enum):
    """Preregistered feasibility probe disposition hierarchy in fixed precedence order."""

    FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD = "FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD"
    BLOCKED_MASSIVE_ENTITLEMENT = "BLOCKED_MASSIVE_ENTITLEMENT"
    BLOCKED_ALPACA_SIP_ENTITLEMENT = "BLOCKED_ALPACA_SIP_ENTITLEMENT"
    BLOCKED_REFERENCE_EXCHANGE_MAPPING = "BLOCKED_REFERENCE_EXCHANGE_MAPPING"
    BLOCKED_REFERENCE_POINT_IN_TIME_SEMANTICS = "BLOCKED_REFERENCE_POINT_IN_TIME_SEMANTICS"
    BLOCKED_CROSS_PROVIDER_SYMBOL_IDENTITY = "BLOCKED_CROSS_PROVIDER_SYMBOL_IDENTITY"
    BLOCKED_CANDIDATE_POOL_HISTORY_SEMANTICS = "BLOCKED_CANDIDATE_POOL_HISTORY_SEMANTICS"
    BLOCKED_STAGE_A_DATA_COMPLETENESS = "BLOCKED_STAGE_A_DATA_COMPLETENESS"
    BLOCKED_STAGE_B_PATH_COMPLETENESS = "BLOCKED_STAGE_B_PATH_COMPLETENESS"
    BLOCKED_RESOURCE_BOUND = "BLOCKED_RESOURCE_BOUND"
    INVALID_PROBE_IMPLEMENTATION_DEFECT = "INVALID_PROBE_IMPLEMENTATION_DEFECT"
    INVALID_PROVIDER_RESPONSE_INTEGRITY = "INVALID_PROVIDER_RESPONSE_INTEGRITY"


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def json_hash(obj: Any) -> str:
    serialized = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def verify_upstream_spec_hashes(
    repo_root: Path,
) -> tuple[bool, str, str, list[str]]:
    """Verify exact SHA-256 hashes of DAYTRADE-003B and DAYTRADE-003C specifications."""
    errors = []
    path_003b = repo_root / LOCKED_003B_SPEC_PATH
    if not path_003b.exists():
        errors.append(f"Missing 003B spec at {path_003b}")
        actual_003b = ""
    else:
        actual_003b = hash_bytes(path_003b.read_bytes())
        if actual_003b != LOCKED_003B_SPEC_SHA256:
            errors.append(
                f"003B spec hash mismatch: expected {LOCKED_003B_SPEC_SHA256}, got {actual_003b}"
            )

    path_003c = repo_root / LOCKED_003C_RESOLUTION_PATH
    if not path_003c.exists():
        errors.append(f"Missing 003C spec at {path_003c}")
        actual_003c = ""
    else:
        actual_003c = hash_bytes(path_003c.read_bytes())
        if actual_003c != LOCKED_003C_RESOLUTION_SHA256:
            errors.append(
                f"003C spec hash mismatch: expected {LOCKED_003C_RESOLUTION_SHA256}, got {actual_003c}"
            )

    return len(errors) == 0, actual_003b, actual_003c, errors


def load_probe_credentials(
    dotenv_path: str | Path | None = None,
) -> tuple[str, str, str]:
    """Safely load provider credentials from environment or dotenv without logging values."""
    # First check process environment
    massive_key = os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY") or ""
    alpaca_key = os.environ.get("ALPACA_API_KEY") or ""
    alpaca_secret = os.environ.get("ALPACA_SECRET_KEY") or ""

    if massive_key and alpaca_key and alpaca_secret:
        return massive_key.strip(), alpaca_key.strip(), alpaca_secret.strip()

    # Search standard .env locations
    candidates = []
    if dotenv_path:
        candidates.append(Path(dotenv_path))
    candidates.extend([
        Path.cwd() / ".env",
        Path("C:/Users/Gary/Projects/TradeX/.env"),
        Path.home() / ".tradex" / ".env",
        Path.home() / ".env",
    ])

    for p in candidates:
        if p.exists() and p.is_file():
            try:
                from tradex.config import load_runtime_settings
                s = load_runtime_settings(dotenv_path=p)
                if not massive_key and s.data.massive_api_key:
                    massive_key = s.data.massive_api_key
                if not alpaca_key and s.data.alpaca_api_key:
                    alpaca_key = s.data.alpaca_api_key
                if not alpaca_secret and s.data.alpaca_secret_key:
                    alpaca_secret = s.data.alpaca_secret_key
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed loading dotenv from %s: %s", p, exc)

        if massive_key and alpaca_key and alpaca_secret:
            break

    return massive_key.strip(), alpaca_key.strip(), alpaca_secret.strip()


@dataclass(frozen=True)
class MassiveSnapshotEvidence:
    """Safe aggregate metadata and audit statistics for one Massive PIT snapshot."""

    date: str
    active: bool
    page_count: int
    row_count: int
    canonical_ticker_count: int
    blank_ticker_count: int
    duplicate_ticker_count: int
    unresolved_duplicate_count: int
    pagination_complete: bool
    repeated_cursor: bool
    cycle_detected: bool
    http_status: int | None
    raw_sha256: str
    canonical_sha256: str
    primary_exchange_distribution: dict[str, int]
    type_distribution: dict[str, int]
    elapsed_seconds: float
    error: str | None = None


@dataclass(frozen=True)
class AlpacaSmokeEvidence:
    """Safe capability test results for Alpaca SIP historical bars."""

    symbol: str
    sip_entitled: bool
    daily_bars_count: int
    minute_bars_count: int
    raw_adjustment_verified: bool
    asof_verified: bool
    http_statuses: list[int]
    error: str | None = None


@dataclass(frozen=True)
class PilotUniverseEvidence:
    """Safe summary of the PIT candidate target universe constructed from Massive."""

    date: str
    total_snapshot_rows: int
    target_universe_count: int
    universe_sha256: str
    target_exchange_distribution: dict[str, int]
    excluded_exchange_distribution: dict[str, int]
    type_distribution: dict[str, int]
    blank_ticker_count: int
    duplicate_ticker_count: int
    unresolved_duplicate_count: int


@dataclass(frozen=True)
class PilotResourcePlan:
    """Estimated vs bounded resource plan before broad pilot acquisition."""

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
    exceeds_pages_limit: bool
    exceeds_storage_limit: bool
    is_within_bounds: bool


@dataclass(frozen=True)
class StageAAuditEvidence:
    """Audit metrics for candidate pool completeness and indicator computability."""

    total_universe_symbols: int
    daily_history_complete_count: int
    prior_or_history_complete_count: int
    current_or_complete_count: int
    candidate_pool_computable_count: int
    incomplete_history_ipo_or_listing_count: int
    missing_provider_bars_count: int
    data_integrity_error_count: int
    cross_provider_unmapped_count: int
    candidate_pool_completeness_pct: float
    is_100_percent_computable: bool


@dataclass(frozen=True)
class StageASelectionEvidence:
    """Safe cryptographic summary of the frozen Stage-A Top-20 selection."""

    eligible_candidates_count: int
    selected_count: int
    selection_sha256: str
    selection_timestamp: str
    doji_count: int


@dataclass(frozen=True)
class StageBAuditEvidence:
    """Safe audit summary of the 09:35..15:59 regular-session path for selected Top 20."""

    symbols_count: int
    expected_minutes_per_symbol: int
    total_expected_bars: int
    total_observed_bars: int
    missing_minutes_count: int
    duplicate_minutes_count: int
    malformed_bars_count: int
    path_complete: bool


@dataclass(frozen=True)
class FullYearResourceEstimate:
    """Conservative full-year 2024 development build projection based on pilot metrics."""

    full_year_sessions_count: int
    pilot_universe_size: int
    estimated_daily_pit_universe_size: int
    extrapolated_massive_snapshots: int
    extrapolated_massive_pages: int
    extrapolated_massive_requests: int
    extrapolated_alpaca_stage_a_calls: int
    extrapolated_alpaca_stage_b_calls: int
    extrapolated_alpaca_total_pages: int
    extrapolated_total_rows: int
    extrapolated_storage_bytes: int
    extrapolated_runtime_hours: float
    rate_limit_exposure_summary: str


def audit_exchange_distribution(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count frequency of primary_exchange values in raw Massive rows."""
    counter: Counter[str] = Counter()
    for r in rows:
        ex = str(r.get("primary_exchange") or "").strip().upper() or "EMPTY"
        counter[ex] += 1
    return dict(sorted(counter.items(), key=lambda x: (-x[1], x[0])))


def audit_type_distribution(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count frequency of security type values in raw Massive rows."""
    counter: Counter[str] = Counter()
    for r in rows:
        t = str(r.get("type") or "").strip().upper() or "EMPTY"
        counter[t] += 1
    return dict(sorted(counter.items(), key=lambda x: (-x[1], x[0])))


def filter_target_universe(
    rows: list[dict[str, Any]],
    allowed_exchanges: tuple[str, ...] = TARGET_EXCHANGE_MAPPING,
) -> tuple[list[str], dict[str, dict[str, Any]], PilotUniverseEvidence]:
    """Filter Massive snapshot rows by primary exchange and canonicalize symbols deterministically."""
    allowed_set = {x.upper() for x in allowed_exchanges}
    target_symbols_map: dict[str, dict[str, Any]] = {}
    target_exchange_counts: Counter[str] = Counter()
    excluded_exchange_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()

    blank_count = 0
    ticker_occurrences: Counter[str] = Counter()

    for r in rows:
        raw_ticker = str(r.get("ticker") or "").strip()
        if not raw_ticker:
            blank_count += 1
            continue
        ticker = raw_ticker.upper()
        ticker_occurrences[ticker] += 1

        ex = str(r.get("primary_exchange") or "").strip().upper()
        sec_type = str(r.get("type") or "").strip().upper() or "EMPTY"

        if ex in allowed_set:
            target_exchange_counts[ex] += 1
            type_counts[sec_type] += 1
            if ticker not in target_symbols_map:
                target_symbols_map[ticker] = r
        else:
            excluded_exchange_counts[ex or "EMPTY"] += 1

    duplicate_count = sum(1 for c in ticker_occurrences.values() if c > 1)

    sorted_canonical_symbols = sorted(target_symbols_map.keys())
    universe_hash = json_hash(sorted_canonical_symbols)

    evidence = PilotUniverseEvidence(
        date=str(rows[0].get("date", "")) if rows else "",
        total_snapshot_rows=len(rows),
        target_universe_count=len(sorted_canonical_symbols),
        universe_sha256=universe_hash,
        target_exchange_distribution=dict(sorted(target_exchange_counts.items())),
        excluded_exchange_distribution=dict(
            sorted(excluded_exchange_counts.items(), key=lambda x: (-x[1], x[0]))
        ),
        type_distribution=dict(sorted(type_counts.items(), key=lambda x: (-x[1], x[0]))),
        blank_ticker_count=blank_count,
        duplicate_ticker_count=duplicate_count,
        unresolved_duplicate_count=0,
    )

    return sorted_canonical_symbols, target_symbols_map, evidence


def calculate_pilot_resource_plan(
    universe_size: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    daily_lookback_sessions: int = 20,
    or_lookback_sessions: int = 14,
    massive_pages_actual: int = 36,
) -> PilotResourcePlan:
    """Calculate projected provider calls, pages, and storage for the pilot date."""
    batch_count = math.ceil(universe_size / batch_size) if universe_size > 0 else 0

    # Daily bars: 1 call per batch for the 20 XNYS sessions in Dec 2023.
    # 100 symbols * 20 bars = 2,000 bars per batch, easily fits in 1 page (limit 10,000).
    planned_daily_requests = batch_count

    # Opening range bars: 1 call per batch per session for 15 sessions (14 prior + current D).
    # 100 symbols * 5 bars = 500 bars per call, easily fits in 1 page.
    total_or_sessions = or_lookback_sessions + 1  # 15
    planned_or_requests = batch_count * total_or_sessions

    # Stage B: 20 symbols for 385 minutes = 7,700 bars -> 1 call/page.
    planned_stage_b_requests = 1

    total_planned_alpaca_pages = (
        planned_daily_requests + planned_or_requests + planned_stage_b_requests
    )
    total_planned_pages = total_planned_alpaca_pages + massive_pages_actual

    # Estimated rows:
    # Daily: universe_size * 20
    # OR: universe_size * 15 * 5 = universe_size * 75
    # Stage B: 20 * 385 = 7,700
    estimated_rows = (universe_size * daily_lookback_sessions) + (universe_size * total_or_sessions * 5) + 7700

    # Estimated private storage: approx 200 bytes per row + metadata
    estimated_storage_bytes = estimated_rows * 200

    exceeds_pages = total_planned_pages > MAX_PILOT_PAGES_LIMIT
    exceeds_storage = estimated_storage_bytes > MAX_PILOT_STORAGE_BYTES_LIMIT

    return PilotResourcePlan(
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
        exceeds_pages_limit=exceeds_pages,
        exceeds_storage_limit=exceeds_storage,
        is_within_bounds=(not exceeds_pages and not exceeds_storage),
    )


def batch_symbols(symbols: list[str], batch_size: int = DEFAULT_BATCH_SIZE) -> list[list[str]]:
    """Partition a list of symbols into deterministic, bounded batches."""
    sorted_syms = sorted({s.strip().upper() for s in symbols if s.strip()})
    return [sorted_syms[i : i + batch_size] for i in range(0, len(sorted_syms), batch_size)]


def audit_candidate_pool_completeness(
    target_universe: list[str],
    daily_bars_by_symbol: dict[str, list[DailyBar]],
    prior_or_obs_by_symbol: dict[str, list[OpeningRangeVolumeObservation]],
    current_or_by_symbol: dict[str, OpeningRange],
    target_session: date,
    required_lookback: int = 14,
) -> tuple[StageAAuditEvidence, dict[str, str]]:
    """Audit Stage-A candidate pool completeness across the entire target universe.

    Enforces 100% candidate-pool computability under the locked DAYTRADE-003C contract.
    Surfaces newly listed / insufficient-history members with explicit classification.
    """
    total = len(target_universe)
    expected_prior_sessions = get_prior_xnys_sessions(target_session, required_lookback)
    expected_prior_set = set(expected_prior_sessions)

    daily_complete = 0
    prior_or_complete = 0
    current_or_complete = 0
    computable_count = 0

    ipo_or_listing_count = 0
    missing_provider_count = 0
    integrity_error_count = 0
    unmapped_count = 0

    reasons_by_symbol: dict[str, str] = {}

    for sym in target_universe:
        daily_bars = daily_bars_by_symbol.get(sym, [])
        prior_or = prior_or_obs_by_symbol.get(sym, [])
        current_or = current_or_by_symbol.get(sym)

        # Audit daily bars for ADV14 and Wilder ATR14
        adv = compute_adv14(daily_bars, target_session, lookback=required_lookback)
        atr = compute_atr14_wilder(daily_bars, target_session, lookback=required_lookback)
        has_daily = adv is not None and atr is not None
        if has_daily:
            daily_complete += 1

        # Audit prior opening-range observations
        prior_dates = {obs.session_date for obs in prior_or}
        has_prior_or = expected_prior_set.issubset(prior_dates) and len(prior_or) >= required_lookback
        if has_prior_or:
            prior_or_complete += 1

        # Audit current session opening range
        has_current_or = current_or is not None
        if has_current_or:
            current_or_complete += 1

        # Overall computability for candidate evaluation
        if has_daily and has_prior_or and has_current_or:
            computable_count += 1
        else:
            # Classify why it failed
            if not daily_bars and not prior_or and not current_or:
                unmapped_count += 1
                reasons_by_symbol[sym] = "unmapped_or_no_provider_data"
            elif len(daily_bars) < required_lookback + 1:
                # Genuinely active on 2024-01-02 but lacks 14 prior sessions (IPO / listing age)
                ipo_or_listing_count += 1
                reasons_by_symbol[sym] = f"insufficient_history_ipo_or_symbol_change:daily_count={len(daily_bars)}"
            elif not has_prior_or:
                missing_provider_count += 1
                reasons_by_symbol[sym] = f"missing_prior_or_bars:found={len(prior_or)}/expected={required_lookback}"
            elif not has_current_or:
                missing_provider_count += 1
                reasons_by_symbol[sym] = "missing_current_session_or_bars"
            else:
                integrity_error_count += 1
                reasons_by_symbol[sym] = "daily_or_integrity_failure"

    pct = (computable_count / float(total) * 100.0) if total > 0 else 0.0
    is_100_pct = (computable_count == total and total > 0)

    evidence = StageAAuditEvidence(
        total_universe_symbols=total,
        daily_history_complete_count=daily_complete,
        prior_or_history_complete_count=prior_or_complete,
        current_or_complete_count=current_or_complete,
        candidate_pool_computable_count=computable_count,
        incomplete_history_ipo_or_listing_count=ipo_or_listing_count,
        missing_provider_bars_count=missing_provider_count,
        data_integrity_error_count=integrity_error_count,
        cross_provider_unmapped_count=unmapped_count,
        candidate_pool_completeness_pct=round(pct, 4),
        is_100_percent_computable=is_100_pct,
    )
    return evidence, reasons_by_symbol


def compute_and_freeze_stage_a_selection(
    universe_symbols: list[str],
    daily_bars_by_symbol: dict[str, list[DailyBar]],
    prior_or_obs_by_symbol: dict[str, list[OpeningRangeVolumeObservation]],
    current_or_by_symbol: dict[str, OpeningRange],
    target_session: date,
    session_start_equity: float = 25000.0,
    top_n: int = 20,
) -> tuple[StageASelectionEvidence, list[dict[str, Any]], list[str]]:
    """Compute indicator filters, rank by RV descending, and freeze Top 20 selection artifact."""
    candidates = []
    for sym in universe_symbols:
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

    evidence = StageASelectionEvidence(
        eligible_candidates_count=sum(1 for c in candidates if c.is_eligible),
        selected_count=len(ranked),
        selection_sha256=selection_sha,
        selection_timestamp=timestamp,
        doji_count=doji_count,
    )

    return evidence, selection_records, selected_symbols


def audit_stage_b_path(
    selected_symbols: list[str],
    bars_by_symbol: dict[str, list[MinuteBar]],
    target_session: date,
    expected_start_time: str = "09:35",
    expected_end_time: str = "15:59",
) -> tuple[StageBAuditEvidence, dict[str, list[str]]]:
    """Audit the complete 09:35..15:59 regular-session path for the selected Top-20 symbols."""
    # Generate expected minute timestamps in ET
    expected_times: list[datetime] = []
    curr_dt = datetime(target_session.year, target_session.month, target_session.day, 9, 35, tzinfo=MARKET_TIMEZONE)
    end_dt = datetime(target_session.year, target_session.month, target_session.day, 15, 59, tzinfo=MARKET_TIMEZONE)
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

    evidence = StageBAuditEvidence(
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


def compute_full_year_estimate(
    pilot_universe_size: int,
    pilot_massive_pages: int,
    pilot_alpaca_pages: int,
    pilot_private_bytes: int,
    pilot_elapsed_seconds: float,
    full_year_sessions_count: int = 249,
) -> FullYearResourceEstimate:
    """Extrapolate full 2024 development build resources conservatively from measured pilot stats."""
    # In 2024 there are 249 full sessions (3 early close sessions excluded).
    # Each session requires:
    # 1 Massive reference snapshot per day (249 snapshots).
    # Pages per snapshot based on measured pilot:
    massive_pages_per_snap = pilot_massive_pages if pilot_massive_pages > 0 else 12
    total_massive_pages = full_year_sessions_count * massive_pages_per_snap

    # Alpaca calls per session:
    # Daily batches + OR batches + Stage B
    alpaca_pages_per_session = pilot_alpaca_pages if pilot_alpaca_pages > 0 else 881
    total_alpaca_pages = full_year_sessions_count * alpaca_pages_per_session

    # Rows per session: approx (universe * 20 daily) + (universe * 15 * 5 OR) + (20 * 385 Stage B)
    rows_per_session = (pilot_universe_size * 20) + (pilot_universe_size * 75) + 7700
    total_rows = full_year_sessions_count * rows_per_session

    # Storage: approx pilot_private_bytes per session
    total_storage = full_year_sessions_count * pilot_private_bytes

    # Runtime: estimated from provider limits
    # Massive free tier (5 req/min) -> 3000 pages / 5 = 600 min = 10 hrs.
    # Alpaca SIP: 200 req/min -> 220,000 pages / 200 = 1,100 min = ~18.3 hrs.
    est_runtime_hours = round((total_alpaca_pages / 200.0 / 60.0) + (total_massive_pages / 5.0 / 60.0), 1)

    rate_limit_summary = (
        f"Full 2024 build requires ~{total_massive_pages:,} Massive pages "
        f"and ~{total_alpaca_pages:,} Alpaca HTTP pages across {full_year_sessions_count} sessions. "
        "Massive requires rate-limit spacing (5 req/min on free tier) or unlimited tier; "
        "Alpaca SIP requires multi-symbol batching with 200 req/min rate limit compliance."
    )

    return FullYearResourceEstimate(
        full_year_sessions_count=full_year_sessions_count,
        pilot_universe_size=pilot_universe_size,
        estimated_daily_pit_universe_size=pilot_universe_size,
        extrapolated_massive_snapshots=full_year_sessions_count,
        extrapolated_massive_pages=total_massive_pages,
        extrapolated_massive_requests=total_massive_pages,
        extrapolated_alpaca_stage_a_calls=full_year_sessions_count * (alpaca_pages_per_session - 1),
        extrapolated_alpaca_stage_b_calls=full_year_sessions_count * 1,
        extrapolated_alpaca_total_pages=total_alpaca_pages,
        extrapolated_total_rows=total_rows,
        extrapolated_storage_bytes=total_storage,
        extrapolated_runtime_hours=est_runtime_hours,
        rate_limit_exposure_summary=rate_limit_summary,
    )


def determine_top_level_disposition(
    massive_entitled: bool,
    alpaca_entitled: bool,
    exchange_mapping_resolved: bool,
    pit_semantics_demonstrated: bool,
    symbol_identity_resolved: bool,
    candidate_pool_complete: bool,
    candidate_pool_has_ipo_semantics_gap: bool,
    stage_a_data_complete: bool,
    stage_b_path_complete: bool,
    resource_bounds_passed: bool,
    implementation_defect: bool = False,
    response_integrity_defect: bool = False,
) -> FeasibilityDisposition:
    """Evaluate gates in strict preregistered precedence order to select the single top-level disposition."""
    if not massive_entitled:
        return FeasibilityDisposition.BLOCKED_MASSIVE_ENTITLEMENT

    if not alpaca_entitled:
        return FeasibilityDisposition.BLOCKED_ALPACA_SIP_ENTITLEMENT

    if not exchange_mapping_resolved:
        return FeasibilityDisposition.BLOCKED_REFERENCE_EXCHANGE_MAPPING

    if not pit_semantics_demonstrated:
        return FeasibilityDisposition.BLOCKED_REFERENCE_POINT_IN_TIME_SEMANTICS

    if not symbol_identity_resolved:
        return FeasibilityDisposition.BLOCKED_CROSS_PROVIDER_SYMBOL_IDENTITY

    if candidate_pool_has_ipo_semantics_gap:
        return FeasibilityDisposition.BLOCKED_CANDIDATE_POOL_HISTORY_SEMANTICS

    if not stage_a_data_complete or not candidate_pool_complete:
        return FeasibilityDisposition.BLOCKED_STAGE_A_DATA_COMPLETENESS

    if not stage_b_path_complete:
        return FeasibilityDisposition.BLOCKED_STAGE_B_PATH_COMPLETENESS

    if not resource_bounds_passed:
        return FeasibilityDisposition.BLOCKED_RESOURCE_BOUND

    if implementation_defect:
        return FeasibilityDisposition.INVALID_PROBE_IMPLEMENTATION_DEFECT

    if response_integrity_defect:
        return FeasibilityDisposition.INVALID_PROVIDER_RESPONSE_INTEGRITY

    return FeasibilityDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD


def write_safe_probe_artifacts(
    output_dir: Path,
    summary_data: dict[str, Any],
    resource_estimate_data: dict[str, Any],
    provider_evidence_data: dict[str, Any] | None = None,
) -> None:
    """Write public safe JSON artifacts containing only aggregate statistics, counts, and hashes."""
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "probe_summary.json"
    summary_path.write_text(json.dumps(summary_data, indent=2, sort_keys=True), encoding="utf-8")

    estimate_path = output_dir / "resource_estimate.json"
    estimate_path.write_text(json.dumps(resource_estimate_data, indent=2, sort_keys=True), encoding="utf-8")

    if provider_evidence_data is not None:
        evidence_path = output_dir / "provider_evidence.json"
        evidence_path.write_text(
            json.dumps(provider_evidence_data, indent=2, sort_keys=True), encoding="utf-8"
        )


def write_private_manifest(
    private_root: Path,
    manifest: TwoStageDatasetManifest,
) -> str:
    """Serialize and write TwoStageDatasetManifest to the private dataset root."""
    private_root.mkdir(parents=True, exist_ok=True)
    invariants = validate_dataset_manifest_invariants(manifest)
    if invariants:
        raise ValueError(f"Manifest invariant validation failed: {invariants}")

    manifest_json = manifest_to_json(manifest, indent=2)
    manifest_path = private_root / "manifest.json"
    manifest_path.write_text(manifest_json, encoding="utf-8")
    return compute_manifest_sha256(manifest)
