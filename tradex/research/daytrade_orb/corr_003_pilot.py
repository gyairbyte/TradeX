"""Corrected ORB real-data feasibility pilot logic for DAYTRADE-003D-CORR-003.

Implements:
1. Strict provider payload integrity validation (HTTP status, completed pagination,
   malformed timestamps, unexpected symbol identities, duplicate timestamps, invalid
   OHLCV bounds, out-of-session prints, and truncated responses).
2. Complete private raw OHLCV persistence and cryptographically verified deterministic
   offline replay without credentials or network access.
3. Strict Stage-B validation invariants, including conservative 15:59 ET liquidation-bar
   coverage for every selected actionable candidate, while preserving legitimate sparse intervals.
4. Immutable historical specification verification (003B, 003C, 003D, CORR-001, CORR-002, CORR-003).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tradex.research.daytrade_orb.corr_002_pilot import (
    CANDIDATE_SCREENING_GATE_THRESHOLD,
    DEFAULT_BATCH_SIZE,
    LOCKED_003B_SPEC_PATH,
    LOCKED_003B_SPEC_SHA256,
    LOCKED_003C_RESOLUTION_PATH,
    LOCKED_003C_RESOLUTION_SHA256,
    LOCKED_003D_CORR_001_SPEC_PATH,
    LOCKED_003D_CORR_001_SPEC_SHA256,
    LOCKED_003D_CORR_002_SPEC_SHA256,
    LOCKED_003D_SPEC_PATH,
    LOCKED_003D_SPEC_SHA256,
    MAX_PILOT_PAGES_LIMIT,
    MAX_PILOT_STORAGE_BYTES_LIMIT,
    PILOT_DATE,
    STRATEGY_ID,
    TARGET_EXCHANGE_MAPPING,
    BroadDailyAvailabilityAudit,
    CandidateScreeningAudit,
    CandidateScreeningOutcome,
    FrozenSelectionEvidence,
    TargetUniverseAudit,
    audit_broad_daily_availability,
    audit_candidate_screening,
    batch_symbols,
    filter_and_audit_target_universe,
    freeze_top_20_selection,
    get_prior_xnys_sessions,
    rank_and_select_top_20,
)
from tradex.research.daytrade_orb.models import (
    DailyBar,
    MinuteBar,
    OpeningRange,
    OpeningRangeVolumeObservation,
)
from tradex.research.daytrade_orb.ranking import evaluate_opening_range
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

logger = logging.getLogger(__name__)

__all__ = [
    "CANDIDATE_SCREENING_GATE_THRESHOLD",
    "CORR_002_SPEC_PATH",
    "CORR_003_ENV_SPEC_PATH",
    "CORR_003_SPEC_PATH",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_PRIVATE_ROOT",
    "LOCKED_003B_SPEC_PATH",
    "LOCKED_003B_SPEC_SHA256",
    "LOCKED_003C_RESOLUTION_PATH",
    "LOCKED_003C_RESOLUTION_SHA256",
    "LOCKED_003D_CORR_001_SPEC_PATH",
    "LOCKED_003D_CORR_001_SPEC_SHA256",
    "LOCKED_003D_CORR_002_SPEC_SHA256",
    "LOCKED_003D_CORR_003_ENV_SPEC_SHA256",
    "LOCKED_003D_CORR_003_SPEC_SHA256",
    "LOCKED_003D_SPEC_PATH",
    "LOCKED_003D_SPEC_SHA256",
    "MAX_PILOT_PAGES_LIMIT",
    "MAX_PILOT_STORAGE_BYTES_LIMIT",
    "PILOT_DATE",
    "STRATEGY_ID",
    "TARGET_EXCHANGE_MAPPING",
    "TASK_ID",
    "BatchIntegrityResult",
    "BroadDailyAvailabilityAudit",
    "CandidateScreeningAudit",
    "CandidateScreeningOutcome",
    "FrozenSelectionEvidence",
    "PayloadIntegrityStatus",
    "PilotDisposition",
    "ProviderPayloadIntegrityError",
    "RawBatchRecord",
    "ReplayIntegrityError",
    "ReplayResult",
    "StageBPathAudit",
    "TargetUniverseAudit",
    "acquire_atomic_pilot_run_lock",
    "audit_broad_daily_availability",
    "audit_candidate_screening",
    "audit_stage_b_price_path_corr_003",
    "batch_symbols",
    "check_one_shot_pilot_guard",
    "check_pilot_authorization",
    "check_pre_live_code_freeze",
    "check_resource_limits",
    "check_runtime_environment_freeze",
    "create_and_save_manifest",
    "determine_pilot_disposition_corr_003",
    "evaluate_opening_range",
    "filter_and_audit_target_universe",
    "freeze_top_20_selection",
    "get_prior_xnys_sessions",
    "hash_bytes",
    "hash_text",
    "is_allowed_post_freeze_drift",
    "json_hash",
    "persist_raw_stage_artifact",
    "rank_and_select_top_20",
    "replay_corr_003_pilot",
    "validate_batch_size",
    "validate_provider_batch_response",
    "validate_run_lock_marker",
    "verify_replay_manifest",
    "verify_upstream_spec_hashes",
]

MARKET_TIMEZONE = ZoneInfo("America/New_York")

TASK_ID = "DAYTRADE-003D-CORR-003"
CORR_002_SPEC_PATH = "docs/research/specs/DAYTRADE-003D-CORR-002-v1.json"
CORR_003_SPEC_PATH = "docs/research/specs/DAYTRADE-003D-CORR-003-v1.json"
LOCKED_003D_CORR_003_SPEC_SHA256 = (
    "2f86d1231f55180b8fe4f65832cde8783e7c6058788a1e98130353b5822a1cdb"
)
CORR_003_ENV_SPEC_PATH = "docs/research/specs/DAYTRADE-003D-CORR-003-ENVIRONMENT.json"
LOCKED_003D_CORR_003_ENV_SPEC_SHA256 = (
    "09d2edda68d9940a175d2333613e80defb8e5a3d0275c8b9554e48dd9947a58f"
)

DEFAULT_PRIVATE_ROOT = Path("C:/Users/Gary/.tradex/research/daytrade_003d_corr_003")


class PilotDisposition(str, Enum):
    """Prospective taxonomy for the final CORR-003 pilot disposition."""

    FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD = "FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD"
    BLOCKED_REFERENCE_OR_PROVIDER_ACCESS = "BLOCKED_REFERENCE_OR_PROVIDER_ACCESS"
    BLOCKED_PROVIDER_DATA_INTEGRITY = "BLOCKED_PROVIDER_DATA_INTEGRITY"
    BLOCKED_CANDIDATE_SCREENING_COVERAGE = "BLOCKED_CANDIDATE_SCREENING_COVERAGE"
    BLOCKED_STAGE_B_PRICE_PATH = "BLOCKED_STAGE_B_PRICE_PATH"
    INCONCLUSIVE_NO_ACTIONABLE_PILOT_CANDIDATE = "INCONCLUSIVE_NO_ACTIONABLE_PILOT_CANDIDATE"
    INVALID_CORR_003_IMPLEMENTATION = "INVALID_CORR_003_IMPLEMENTATION"


class PayloadIntegrityStatus(str, Enum):
    """Taxonomy for provider payload integrity verification."""

    VALID = "VALID"
    HTTP_ERROR = "HTTP_ERROR"
    PAGINATION_INCOMPLETE = "PAGINATION_INCOMPLETE"
    MALFORMED_TIMESTAMP = "MALFORMED_TIMESTAMP"
    UNEXPECTED_SYMBOL = "UNEXPECTED_SYMBOL"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    INVALID_OHLCV = "INVALID_OHLCV"
    OUT_OF_SESSION_BAR = "OUT_OF_SESSION_BAR"
    TRUNCATED_OR_MALFORMED_PAYLOAD = "TRUNCATED_OR_MALFORMED_PAYLOAD"


class ReplayIntegrityError(ValueError):
    """Raised when replay artifacts are missing, incomplete, or tampered."""


class ProviderPayloadIntegrityError(ValueError):
    """Raised when provider response violates integrity invariants."""


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def json_hash(obj: Any) -> str:
    serialized = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def verify_upstream_spec_hashes(
    repo_root: Path,
    include_corr_003: bool = True,
) -> tuple[bool, dict[str, str], list[str]]:
    """Verify SHA-256 hashes of all prior specifications: 003B, 003C, 003D, CORR-001, CORR-002, and CORR-003."""
    expected = {
        LOCKED_003B_SPEC_PATH: LOCKED_003B_SPEC_SHA256,
        LOCKED_003C_RESOLUTION_PATH: LOCKED_003C_RESOLUTION_SHA256,
        LOCKED_003D_SPEC_PATH: LOCKED_003D_SPEC_SHA256,
        LOCKED_003D_CORR_001_SPEC_PATH: LOCKED_003D_CORR_001_SPEC_SHA256,
        CORR_002_SPEC_PATH: LOCKED_003D_CORR_002_SPEC_SHA256,
    }
    if include_corr_003:
        expected[CORR_003_SPEC_PATH] = LOCKED_003D_CORR_003_SPEC_SHA256
        expected[CORR_003_ENV_SPEC_PATH] = LOCKED_003D_CORR_003_ENV_SPEC_SHA256

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


# -----------------------------------------------------------------------------
# Provider Payload Integrity Validation
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchIntegrityResult:
    """Detailed result of provider batch response integrity validation."""

    is_valid: bool
    status: PayloadIntegrityStatus
    error_message: str
    malformed_timestamp_count: int = 0
    duplicate_timestamp_count: int = 0
    out_of_session_bar_count: int = 0
    invalid_ohlcv_count: int = 0
    unexpected_symbols: tuple[str, ...] = ()


def validate_provider_batch_response(
    symbols_requested: list[str],
    meta: dict[str, Any],
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    expected_start: datetime | None = None,
    expected_end: datetime | None = None,
    expected_timezone: ZoneInfo = MARKET_TIMEZONE,
    allowed_time_window: tuple[time, time] | None = None,
    session_date: date | None = None,
    require_raw_pages: bool = False,
) -> BatchIntegrityResult:
    """Validate provider response before interpreting absent intervals as sparse minutes.

    Enforces:
    1. HTTP status is 200.
    2. Pagination completed without cycle or repeated tokens.
    3. Mandatory raw page evidence presence, count, and per-page HTTP status coherence.
    4. Terminal and intermediate next_page_token coherence.
    5. Exact bar parity between raw provider pages and aggregated bars_by_symbol.
    6. No unexpected symbol identities in response.
    7. Zero malformed timestamps.
    8. Zero duplicate timestamps per symbol.
    9. Bars within expected datetime/session range.
    10. Valid OHLCV values (positive prices, non-negative volume, high >= low, bounds).
    """
    if meta.get("http_status") is None or meta.get("pagination_complete") is None:
        return BatchIntegrityResult(
            is_valid=False,
            status=PayloadIntegrityStatus.PAGINATION_INCOMPLETE,
            error_message="Missing mandatory provenance metadata (http_status / pagination_complete)",
        )

    http_status = meta.get("http_status", 0)
    if http_status != 200:
        return BatchIntegrityResult(
            is_valid=False,
            status=PayloadIntegrityStatus.HTTP_ERROR,
            error_message=f"HTTP status {http_status} != 200 (error: {meta.get('safe_error_classification')})",
        )

    pagination_complete = meta.get("pagination_complete", False)
    repeated_page_token = meta.get("repeated_page_token", False)
    pagination_cycle = meta.get("pagination_cycle_detected", False)
    safe_error = meta.get("safe_error_classification", meta.get("safe_error", "none"))
    terminal_token_present = meta.get(
        "terminal_next_page_token_present",
        meta.get("unconsumed_page_token_present", False),
    )

    if (
        not pagination_complete
        or repeated_page_token
        or pagination_cycle
        or safe_error != "none"
        or terminal_token_present
    ):
        return BatchIntegrityResult(
            is_valid=False,
            status=PayloadIntegrityStatus.PAGINATION_INCOMPLETE,
            error_message=(
                f"Incomplete pagination: complete={pagination_complete}, repeated={repeated_page_token}, "
                f"cycle={pagination_cycle}, safe_error={safe_error}, terminal_token={terminal_token_present}"
            ),
        )

    raw_pages = meta.get("raw_pages")
    if require_raw_pages and raw_pages is None:
        return BatchIntegrityResult(
            is_valid=False,
            status=PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD,
            error_message="raw_pages evidence is mandatory for CORR-003 provider responses but is missing",
        )

    if raw_pages is not None:
        if not isinstance(raw_pages, list):
            return BatchIntegrityResult(
                is_valid=False,
                status=PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD,
                error_message="raw_pages in meta must be a list",
            )

        # A completed HTTP 200 provider batch MUST record at least 1 raw provider page
        if http_status == 200 and pagination_complete and len(raw_pages) == 0:
            return BatchIntegrityResult(
                is_valid=False,
                status=PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD,
                error_message="Completed HTTP 200 provider batch has empty raw_pages list (missing raw page evidence)",
            )

        # Page count consistency check
        expected_page_count = meta.get("page_count")
        if (
            expected_page_count is not None
            and isinstance(expected_page_count, int)
            and len(raw_pages) != expected_page_count
        ):
            return BatchIntegrityResult(
                is_valid=False,
                status=PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD,
                error_message=(
                    f"raw_pages count ({len(raw_pages)}) does not match metadata page_count ({expected_page_count})"
                ),
            )

        raw_page_bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for p_idx, p in enumerate(raw_pages):
            if not isinstance(p, dict):
                return BatchIntegrityResult(
                    is_valid=False,
                    status=PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD,
                    error_message=f"raw_pages[{p_idx}] is not a dict",
                )

            # Assert per-page HTTP status
            p_status = p.get("http_status", p.get("status_code", meta.get("http_status", 200)))
            if p_status != 200:
                return BatchIntegrityResult(
                    is_valid=False,
                    status=PayloadIntegrityStatus.HTTP_ERROR,
                    error_message=f"raw_pages[{p_idx}] http_status {p_status} != 200",
                )

            body = p.get("body")
            if not isinstance(body, dict):
                return BatchIntegrityResult(
                    is_valid=False,
                    status=PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD,
                    error_message=f"raw_pages[{p_idx}] body is not a dict",
                )

            # Check terminal vs intermediate pagination token coherence
            next_tok = body.get("next_page_token")
            is_last_page = (p_idx == len(raw_pages) - 1)
            if pagination_complete and is_last_page and next_tok:
                return BatchIntegrityResult(
                    is_valid=False,
                    status=PayloadIntegrityStatus.PAGINATION_INCOMPLETE,
                    error_message=(
                        f"Terminal raw page {p_idx} has unconsumed next_page_token '{next_tok}' "
                        f"despite pagination_complete=True"
                    ),
                )
            if not is_last_page and not next_tok:
                return BatchIntegrityResult(
                    is_valid=False,
                    status=PayloadIntegrityStatus.PAGINATION_INCOMPLETE,
                    error_message=f"Intermediate raw page {p_idx} is missing required next_page_token",
                )

            p_bars = body.get("bars")
            if not isinstance(p_bars, dict):
                return BatchIntegrityResult(
                    is_valid=False,
                    status=PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD,
                    error_message=f"raw_pages[{p_idx}] body missing or non-dict 'bars'",
                )

            for sym_k, b_list in p_bars.items():
                if not isinstance(b_list, list):
                    return BatchIntegrityResult(
                        is_valid=False,
                        status=PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD,
                        error_message=f"raw_pages[{p_idx}] bars for symbol '{sym_k}' is not a list",
                    )
                for b_item in b_list:
                    if not isinstance(b_item, dict):
                        return BatchIntegrityResult(
                            is_valid=False,
                            status=PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD,
                            error_message=f"raw_pages[{p_idx}] bar for symbol '{sym_k}' is not a dict",
                        )
                clean_sym = str(sym_k).upper()
                if clean_sym not in raw_page_bars_by_symbol:
                    raw_page_bars_by_symbol[clean_sym] = []
                raw_page_bars_by_symbol[clean_sym].extend(b_list)

        # Exact parity check between raw_pages and bars_by_symbol
        all_syms = set(bars_by_symbol.keys()) | set(raw_page_bars_by_symbol.keys())
        for sym in all_syms:
            clean_sym = str(sym).upper()
            agg_bars = bars_by_symbol.get(sym, bars_by_symbol.get(clean_sym, []))
            raw_bars = raw_page_bars_by_symbol.get(clean_sym, [])
            if agg_bars != raw_bars:
                return BatchIntegrityResult(
                    is_valid=False,
                    status=PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD,
                    error_message=(
                        f"Discrepancy between raw_pages bars ({len(raw_bars)}) "
                        f"and aggregated bars ({len(agg_bars)}) for symbol {sym}"
                    ),
                )

    req_set = {s.strip().upper() for s in symbols_requested}
    resp_symbols = set(meta.get("response_symbols", [])) | {s.strip().upper() for s in bars_by_symbol}
    if raw_pages is not None:
        for p in raw_pages:
            if isinstance(p, dict):
                body = p.get("body", {})
                if isinstance(body, dict):
                    p_bars = body.get("bars", {})
                    if isinstance(p_bars, dict):
                        resp_symbols.update(str(k).upper() for k in p_bars)
    unexpected = sorted(resp_symbols - req_set)
    if unexpected:
        return BatchIntegrityResult(
            is_valid=False,
            status=PayloadIntegrityStatus.UNEXPECTED_SYMBOL,
            error_message=f"Unexpected symbol identities in response: {unexpected}",
            unexpected_symbols=tuple(unexpected),
        )

    malformed_counts = meta.get("malformed_timestamp_counts", {})
    total_malformed = sum(malformed_counts.values()) if isinstance(malformed_counts, dict) else 0
    if total_malformed > 0:
        return BatchIntegrityResult(
            is_valid=False,
            status=PayloadIntegrityStatus.MALFORMED_TIMESTAMP,
            error_message=f"Response contains {total_malformed} malformed timestamps",
            malformed_timestamp_count=total_malformed,
        )

    duplicate_count = 0
    out_of_session_count = 0
    invalid_ohlcv_count = 0

    for sym, raw_bars in bars_by_symbol.items():
        if not raw_bars:
            continue

        seen_timestamps: set[datetime] = set()
        for b in raw_bars:
            raw_t = b.get("t")
            if not raw_t:
                return BatchIntegrityResult(
                    is_valid=False,
                    status=PayloadIntegrityStatus.MALFORMED_TIMESTAMP,
                    error_message=f"Missing timestamp field 't' for symbol {sym}",
                    malformed_timestamp_count=1,
                )

            try:
                if isinstance(raw_t, str):
                    ts = datetime.fromisoformat(raw_t)
                elif isinstance(raw_t, datetime):
                    ts = raw_t
                else:
                    raise TypeError(f"Unrecognized timestamp format: {type(raw_t)}")
                if ts.tzinfo is None:
                    raise ValueError("Naive timestamp")
            except Exception as exc:  # noqa: BLE001
                return BatchIntegrityResult(
                    is_valid=False,
                    status=PayloadIntegrityStatus.MALFORMED_TIMESTAMP,
                    error_message=f"Malformed timestamp '{raw_t}' for symbol {sym}: {exc}",
                    malformed_timestamp_count=1,
                )

            if ts in seen_timestamps:
                duplicate_count += 1
            seen_timestamps.add(ts)

            # Check expected datetime range
            if expected_start and ts < expected_start:
                out_of_session_count += 1
            if expected_end and ts > expected_end:
                out_of_session_count += 1

            local_dt = ts.astimezone(expected_timezone)
            if session_date and local_dt.date() != session_date:
                out_of_session_count += 1

            if allowed_time_window:
                win_start, win_end = allowed_time_window
                t_time = local_dt.time()
                if not (win_start <= t_time <= win_end):
                    out_of_session_count += 1

            # Validate OHLCV
            try:
                o_val = float(b.get("o", b.get("open", 0.0)))
                h_val = float(b.get("h", b.get("high", 0.0)))
                l_val = float(b.get("l", b.get("low", 0.0)))
                c_val = float(b.get("c", b.get("close", 0.0)))
                v_val = float(b.get("v", b.get("volume", 0.0)))

                if (
                    not all(math.isfinite(x) for x in (o_val, h_val, l_val, c_val, v_val))
                    or o_val <= 0
                    or h_val <= 0
                    or l_val <= 0
                    or c_val <= 0
                    or v_val < 0
                    or h_val < max(o_val, c_val)
                    or l_val > min(o_val, c_val)
                    or h_val < l_val
                ):
                    invalid_ohlcv_count += 1
            except (TypeError, ValueError):
                invalid_ohlcv_count += 1

    if duplicate_count > 0:
        return BatchIntegrityResult(
            is_valid=False,
            status=PayloadIntegrityStatus.DUPLICATE_TIMESTAMP,
            error_message=f"Response contains {duplicate_count} duplicate timestamps",
            duplicate_timestamp_count=duplicate_count,
        )

    if out_of_session_count > 0:
        return BatchIntegrityResult(
            is_valid=False,
            status=PayloadIntegrityStatus.OUT_OF_SESSION_BAR,
            error_message=f"Response contains {out_of_session_count} out-of-session bars",
            out_of_session_bar_count=out_of_session_count,
        )

    if invalid_ohlcv_count > 0:
        return BatchIntegrityResult(
            is_valid=False,
            status=PayloadIntegrityStatus.INVALID_OHLCV,
            error_message=f"Response contains {invalid_ohlcv_count} bars with invalid OHLCV bounds",
            invalid_ohlcv_count=invalid_ohlcv_count,
        )

    return BatchIntegrityResult(
        is_valid=True,
        status=PayloadIntegrityStatus.VALID,
        error_message="",
    )


# -----------------------------------------------------------------------------
# Stage-B Path Audit with Enforced Invariants
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class StageBPathAudit:
    """Safe audit of Stage-B price path availability, provider integrity, and evaluator compatibility."""

    selected_actionable_symbols_count: int
    total_expected_minutes: int
    total_actual_bars: int
    total_sparse_minutes: int
    missing_eod_bar_symbols_count: int
    provider_failure_count: int
    integrity_failure_count: int
    is_usable: bool
    unusable_reason: str
    unusable_reasons: tuple[str, ...] = ()


def audit_stage_b_price_path_corr_003(
    active_selected_symbols: list[str],
    stage_b_bars_by_symbol: dict[str, list[MinuteBar]],
    stage_b_provider_failures: set[str],
    expected_minutes: int = 385,
    session_date: date | None = None,
) -> StageBPathAudit:
    """Audit Stage-B minute bar availability, sparse intervals, provider integrity, and EOD liquidation bar presence.

    Enforces:
    1. Zero provider request failures.
    2. Zero payload integrity failures (timestamps 09:35..15:59 ET, unique, monotonic, valid OHLCV).
    3. Conservative 15:59 ET liquidation-bar coverage for EVERY selected actionable candidate.
       If any actionable candidate lacks a valid 15:59 bar, Stage-B is strictly UNUSABLE.
    4. Preserves legitimate sparse-bar behavior: missing minutes between 09:35 and 15:58 ET
       do not fail usability, provided provider integrity and the 15:59 liquidation bar hold.
    """
    total_expected = len(active_selected_symbols) * expected_minutes
    total_actual = 0
    total_sparse = 0
    missing_eod_symbols = 0
    provider_failures = 0
    integrity_failures = 0
    unusable_reasons: list[str] = []

    for sym in active_selected_symbols:
        if sym in stage_b_provider_failures:
            provider_failures += 1
            total_sparse += expected_minutes
            missing_eod_symbols += 1
            unusable_reasons.append(f"Provider request failed for {sym}")
            continue

        bars = stage_b_bars_by_symbol.get(sym, [])
        total_actual += len(bars)
        sparse_mins = max(0, expected_minutes - len(bars))
        total_sparse += sparse_mins

        if not bars:
            missing_eod_symbols += 1
            unusable_reasons.append(f"No Stage-B bars received for {sym}")
            continue

        # Inspect bars for symbol identity, timestamp bounds, ordering, and uniqueness
        seen_times: set[time] = set()
        sym_has_integrity_error = False

        for b in bars:
            if b.symbol.strip().upper() != sym.strip().upper():
                sym_has_integrity_error = True
                unusable_reasons.append(f"Symbol identity mismatch in bar: expected {sym}, got {b.symbol}")
                break

            local_dt = b.timestamp.astimezone(MARKET_TIMEZONE)
            if session_date and local_dt.date() != session_date:
                sym_has_integrity_error = True
                unusable_reasons.append(f"Bar date mismatch for {sym}: expected {session_date}, got {local_dt.date()}")
                break

            bar_t = local_dt.time()
            if not (time(9, 35) <= bar_t <= time(15, 59)):
                sym_has_integrity_error = True
                unusable_reasons.append(f"Out-of-session Stage-B bar for {sym} at {bar_t}")
                break

            if bar_t in seen_times:
                sym_has_integrity_error = True
                unusable_reasons.append(f"Duplicate timestamp in Stage-B for {sym} at {bar_t}")
                break
            seen_times.add(bar_t)

        if sym_has_integrity_error:
            integrity_failures += 1

        # Check conservative 15:59 ET liquidation-bar presence
        has_1559 = time(15, 59) in seen_times
        if not has_1559:
            missing_eod_symbols += 1
            unusable_reasons.append(f"Missing required 15:59 ET liquidation bar for {sym}")

    is_usable = (
        provider_failures == 0
        and integrity_failures == 0
        and missing_eod_symbols == 0
        and len(active_selected_symbols) > 0
    )

    primary_reason = ""
    if not is_usable:
        if len(active_selected_symbols) == 0:
            primary_reason = "No active selected symbols to evaluate"
        elif provider_failures > 0:
            primary_reason = f"Stage-B provider request failed for {provider_failures} symbol(s)"
        elif integrity_failures > 0:
            primary_reason = f"Stage-B bar integrity failure detected for {integrity_failures} symbol(s)"
        elif missing_eod_symbols > 0:
            primary_reason = f"Required 15:59 ET liquidation bar missing for {missing_eod_symbols} symbol(s)"

    return StageBPathAudit(
        selected_actionable_symbols_count=len(active_selected_symbols),
        total_expected_minutes=total_expected,
        total_actual_bars=total_actual,
        total_sparse_minutes=total_sparse,
        missing_eod_bar_symbols_count=missing_eod_symbols,
        provider_failure_count=provider_failures,
        integrity_failure_count=integrity_failures,
        is_usable=is_usable,
        unusable_reason=primary_reason,
        unusable_reasons=tuple(unusable_reasons),
    )


# -----------------------------------------------------------------------------
# Raw OHLCV Persistence & Cryptographic Manifest
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class RawBatchRecord:
    """Provenance and raw payload record for a multi-symbol provider request."""

    batch_index: int
    symbols_requested: list[str]
    http_status: int
    pagination_complete: bool
    page_count: int
    token_hashes: list[str]
    token_sequence_sha256: str
    bars_by_symbol: dict[str, list[dict[str, Any]]]
    integrity_status: str
    batch_sha256: str


def persist_raw_stage_artifact(
    path: Path,
    metadata: dict[str, Any],
    batches: list[dict[str, Any]],
) -> tuple[str, int]:
    """Persist raw provider evidence to JSON and return its SHA-256 hash and byte size."""
    payload = {
        "metadata": metadata,
        "batches": batches,
    }
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    raw_bytes = serialized.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw_bytes)
    return hash_bytes(raw_bytes), len(raw_bytes)


def create_and_save_manifest(
    output_dir: Path,
    artifacts_info: dict[str, dict[str, Any]],
    pilot_date: str = PILOT_DATE,
) -> tuple[Path, str]:
    """Create and save checksum manifest for all persisted replay artifacts."""
    manifest_data = {
        "schema_version": "1.0",
        "task_id": TASK_ID,
        "date": pilot_date,
        "created_at_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "artifacts": artifacts_info,
    }
    manifest_path = output_dir / f"manifest_{pilot_date}.json"
    serialized = json.dumps(manifest_data, indent=2, sort_keys=True)
    raw_bytes = serialized.encode("utf-8")
    manifest_path.write_bytes(raw_bytes)
    return manifest_path, hash_bytes(raw_bytes)


REQUIRED_MANIFEST_ARTIFACTS: tuple[str, ...] = (
    "massive_reference_{date}.json",
    "universe_{date}.json",
    "alpaca_daily_dec2023.json",
    "alpaca_current_or_{date}.json",
    "alpaca_prior_or_14sessions_{date}.json",
    "top_20_selection_{date}.json",
    "alpaca_stage_b_{date}.json",
)


def verify_replay_manifest(
    input_dir: Path,
    pilot_date: str = PILOT_DATE,
) -> tuple[bool, dict[str, Any], list[str]]:
    """Validate stored checksums and file sizes from manifest. Fails closed if tampered or missing."""
    manifest_path = input_dir / f"manifest_{pilot_date}.json"
    if not manifest_path.exists():
        return False, {}, [f"Missing manifest file: {manifest_path}"]

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, {}, [f"Malformed manifest JSON: {exc}"]

    errors: list[str] = []
    if manifest_data.get("schema_version") != "1.0":
        errors.append(
            f"Invalid manifest schema_version: expected '1.0', got '{manifest_data.get('schema_version')}'"
        )

    artifacts = manifest_data.get("artifacts", {})
    if not isinstance(artifacts, dict) or not artifacts:
        errors.append("Manifest has no valid artifacts dictionary")
        return False, manifest_data, errors

    # Enforce all required stage artifacts are listed in manifest
    expected_files = {template.format(date=pilot_date) for template in REQUIRED_MANIFEST_ARTIFACTS}
    missing_required = expected_files - set(artifacts.keys())
    for mf in sorted(missing_required):
        errors.append(f"Required artifact '{mf}' is missing from manifest")

    # Enforce checksum and size integrity for each manifest artifact
    for filename, info in artifacts.items():
        artifact_file = input_dir / filename
        if not artifact_file.exists():
            errors.append(f"Missing artifact file on disk: {filename}")
            continue

        file_bytes = artifact_file.read_bytes()
        actual_size = len(file_bytes)
        expected_size = info.get("size_bytes") if isinstance(info, dict) else None
        if expected_size is None or not isinstance(expected_size, int) or expected_size <= 0:
            errors.append(f"Artifact '{filename}' is missing mandatory positive 'size_bytes' in manifest")
        elif actual_size != expected_size:
            errors.append(f"File size mismatch for {filename}: expected {expected_size}, got {actual_size}")

        actual_hash = hash_bytes(file_bytes)
        expected_hash = info.get("sha256") if isinstance(info, dict) else None
        if not expected_hash or not isinstance(expected_hash, str) or len(expected_hash) != 64:
            errors.append(f"Artifact '{filename}' is missing mandatory valid 64-character 'sha256' in manifest")
        elif actual_hash != expected_hash:
            errors.append(f"SHA-256 checksum mismatch for {filename}: expected {expected_hash}, got {actual_hash}")

    # Validate durable run lock marker if present in manifest
    lock_marker_name = f".pilot_run_lock_{pilot_date}.json"
    if lock_marker_name in artifacts:
        lock_file = input_dir / lock_marker_name
        if lock_file.exists():
            errors.extend(validate_run_lock_marker(lock_file, pilot_date))

    # Enforce fail-closed check on unlisted extra files in directory
    manifest_filename = f"manifest_{pilot_date}.json"
    for file_path in input_dir.iterdir():
        if file_path.is_file() and file_path.name != manifest_filename and file_path.name not in artifacts:
            errors.append(f"Unlisted extra file detected in replay directory: {file_path.name}")

    return len(errors) == 0, manifest_data, errors


# -----------------------------------------------------------------------------
# Prospective Execution, Resource Bounds & Authorization Guards
# -----------------------------------------------------------------------------


def validate_run_lock_marker(lock_path: Path, expected_pilot_date: str = PILOT_DATE) -> list[str]:
    """Validate that the durable run lock marker contains consistent, uncorrupted metadata."""
    if not lock_path.exists():
        return [f"Run lock marker does not exist on disk: {lock_path.name}"]
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"Malformed run lock JSON in {lock_path.name}: {exc}"]
    if not isinstance(data, dict):
        return [f"Run lock in {lock_path.name} is not a valid JSON object"]

    errors: list[str] = []
    if data.get("task_id") != TASK_ID:
        errors.append(f"Run lock task_id mismatch: expected '{TASK_ID}', got '{data.get('task_id')}'")
    if data.get("pilot_date") != expected_pilot_date:
        errors.append(f"Run lock pilot_date mismatch: expected '{expected_pilot_date}', got '{data.get('pilot_date')}'")
    sha = data.get("pre_live_commit_sha")
    if not isinstance(sha, str) or len(sha) != 40:
        errors.append(f"Run lock pre_live_commit_sha is invalid 40-char SHA: '{sha}'")
    status = data.get("status")
    if status not in ("IN_PROGRESS", "COMPLETED"):
        errors.append(f"Run lock invalid status: '{status}'")
    initiated = data.get("initiated_at_utc")
    if not isinstance(initiated, str) or not initiated:
        errors.append(f"Run lock invalid initiated_at_utc timestamp: '{initiated}'")
    return errors


def acquire_atomic_pilot_run_lock(
    output_dir: Path,
    pilot_date: str = PILOT_DATE,
    pre_live_commit_sha: str = "",
) -> Path:
    """Enforce strict one-shot execution with atomic exclusive file creation.

    1. Checks one-shot guard (fails closed if manifest, existing lock, or unmanifested json files exist).
    2. Atomically creates lock marker '.pilot_run_lock_<date>.json' using 'xb' mode (O_CREAT | O_EXCL).
       Fails closed with RuntimeError on collision without modifying or truncating existing evidence.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    check_one_shot_pilot_guard(output_dir, pilot_date)

    lock_marker_path = output_dir / f".pilot_run_lock_{pilot_date}.json"
    lock_payload = {
        "task_id": TASK_ID,
        "pilot_date": pilot_date,
        "pre_live_commit_sha": pre_live_commit_sha,
        "status": "IN_PROGRESS",
        "initiated_at_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
    }
    lock_data = json.dumps(lock_payload, indent=2).encode("utf-8")

    try:
        with open(lock_marker_path, "xb") as f:
            f.write(lock_data)
    except FileExistsError as exc:
        raise RuntimeError(
            f"Atomic one-shot lock acquisition failed: lock marker '{lock_marker_path.name}' already exists in {output_dir}. "
            f"Concurrent execution or duplicate launch attempt detected. Existing marker and partial evidence preserved."
        ) from exc

    return lock_marker_path


def validate_batch_size(batch_size: int) -> None:
    """Validate that provider batch size is within strictly bounded safe limits."""
    if not isinstance(batch_size, int) or batch_size < 1 or batch_size > 100:
        raise ValueError(
            f"Invalid batch size {batch_size}: must be an integer between 1 and 100 inclusive"
        )


def check_one_shot_pilot_guard(output_dir: Path, pilot_date: str = PILOT_DATE) -> None:
    """Enforce strict one-shot execution: cannot rerun, restart, or overwrite existing completed or partial pilot run."""
    if not output_dir.exists():
        return
    manifest_path = output_dir / f"manifest_{pilot_date}.json"
    if manifest_path.exists():
        raise RuntimeError(
            f"One-shot pilot guard triggered: completed pilot manifest already exists at {manifest_path}. "
            f"A pilot run is strictly one-shot and cannot overwrite existing pilot evidence."
        )
    lock_path = output_dir / f".pilot_run_lock_{pilot_date}.json"
    if lock_path.exists():
        raise RuntimeError(
            f"One-shot pilot guard triggered: run lock marker exists at {lock_path}. "
            f"An existing or interrupted run was detected; cannot restart or overwrite partial evidence."
        )
    existing_json = [
        f for f in output_dir.iterdir()
        if f.is_file() and f.suffix == ".json" and not f.name.startswith(".")
    ]
    if existing_json:
        raise RuntimeError(
            f"One-shot pilot guard triggered: found {len(existing_json)} existing artifacts in {output_dir}. "
            f"A pilot run must begin in a clean directory to prevent partial evidence collision."
        )


def check_resource_limits(
    page_count: int,
    storage_bytes: int,
    max_pages: int = MAX_PILOT_PAGES_LIMIT,
    max_storage: int = MAX_PILOT_STORAGE_BYTES_LIMIT,
) -> None:
    """Enforce strict resource ceilings for external provider pages and private storage."""
    if page_count > max_pages:
        raise RuntimeError(
            f"Resource ceiling exceeded: total provider pages {page_count} > limit {max_pages}"
        )
    if storage_bytes > max_storage:
        raise RuntimeError(
            f"Storage ceiling exceeded: private storage {storage_bytes} bytes > limit {max_storage} bytes"
        )


def is_allowed_post_freeze_drift(file_path: str) -> bool:
    """Deliberate post-freeze allowlist:
    Only the approved Gary authorization record and explicitly non-executable documentation
    are permitted to change between freeze commit F and authorization commit A.
    All executable code, dependencies (pyproject.toml, uv.lock), scripts, tests, specs,
    and runtime configurations are strictly forbidden.
    """
    normalized = file_path.replace("\\", "/").strip()
    if not normalized:
        return True

    # 1. Approved Gary authorization record
    if normalized == "docs/research/authorizations/DAYTRADE-003D-CORR-003-AUTHORIZATION.json":
        return True

    # 2. Frozen upstream specs are NEVER allowed to drift
    if normalized.startswith("docs/research/specs/"):
        return False

    # 3. Explicitly non-executable documentation under docs/ (.md, .txt, .rst)
    if normalized.startswith("docs/") and normalized.endswith((".md", ".txt", ".rst")):
        return True

    # 4. Standard non-executable repository documentation files at root
    # Fail closed on all executable code, dependencies (pyproject.toml, uv.lock), workflows, etc.
    return normalized in ("README.md", "CONTRIBUTING.md", "CHANGELOG.md")


def check_pre_live_code_freeze(
    repo_root: Path,
    expected_sha: str,
    verify_environment: bool = True,
) -> None:
    """Validate that execution tree matches or is an authorized clean descendant of the approved freeze commit.

    Two-commit workflow:
    1. Audited implementation freeze commit F (expected_sha).
    2. Optional authorization commit A where F is an ancestor of HEAD (A).
       Between F and A, zero code, spec, test, dependency, or configuration drift is permitted:
       only the approved authorization record and explicitly non-executable documentation may change.
    3. Working tree must be completely clean.
    4. Active runtime dependency environment matches the frozen environment fingerprint.
    """
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        actual_sha = res.stdout.strip()
    except Exception as exc:
        raise RuntimeError(f"Failed to inspect git repository HEAD: {exc}") from exc

    try:
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        dirty = status_res.stdout.strip()
    except Exception as exc:
        raise RuntimeError(f"Failed to inspect git status: {exc}") from exc

    if dirty:
        raise RuntimeError(f"Pre-live freeze verification failed: working tree is dirty:\n{dirty}")

    if actual_sha == expected_sha:
        if verify_environment and (repo_root / CORR_003_ENV_SPEC_PATH).exists():
            check_runtime_environment_freeze(
                repo_root,
                require_live_provider_packages=False,
                check_uv_lock=True,
            )
        return

    # Check ancestry: expected_sha must be an ancestor of actual_sha
    try:
        anc_res = subprocess.run(
            ["git", "merge-base", "--is-ancestor", expected_sha, actual_sha],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        is_ancestor = anc_res.returncode == 0
    except Exception as exc:
        raise RuntimeError(f"Failed to check git merge-base ancestry: {exc}") from exc

    if not is_ancestor:
        raise RuntimeError(
            f"Pre-live freeze verification failed: expected freeze commit ({expected_sha}) "
            f"is not an ancestor of current HEAD ({actual_sha})"
        )

    # Check for code/spec/test/dependency drift between freeze commit and HEAD
    try:
        diff_res = subprocess.run(
            ["git", "diff", "--name-only", f"{expected_sha}..{actual_sha}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        changed_files = [f.strip() for f in diff_res.stdout.splitlines() if f.strip()]
    except Exception as exc:
        raise RuntimeError(f"Failed to check git diff between freeze commit and HEAD: {exc}") from exc

    disallowed_drift = [f for f in changed_files if not is_allowed_post_freeze_drift(f)]
    if disallowed_drift:
        raise RuntimeError(
            f"Pre-live freeze verification failed: forbidden code/spec/test drift between freeze "
            f"({expected_sha}) and current HEAD ({actual_sha}) outside post-freeze allowlist: {disallowed_drift}"
        )

    if verify_environment and (repo_root / CORR_003_ENV_SPEC_PATH).exists():
        check_runtime_environment_freeze(
            repo_root,
            require_live_provider_packages=False,
            check_uv_lock=True,
        )


def check_runtime_environment_freeze(
    repo_root: Path,
    spec_path: Path | None = None,
    require_live_provider_packages: bool = True,
    check_uv_lock: bool = True,
    verify_spec_hash: bool = True,
) -> dict[str, Any]:
    """Validate that the active runtime environment matches the frozen environment fingerprint.

    Hard Execution Gate before loading credentials or calling live market-data APIs:
    1. Verifies that the frozen environment specification file exists and matches
       the preregistered SHA-256 hash (LOCKED_003D_CORR_003_ENV_SPEC_SHA256).
    2. Enforces Python major/minor version (e.g. 3.11).
    3. Checks the ignored uv.lock on disk: when check_uv_lock=True, requires uv.lock to
       exist on disk and match one of the audited SHA-256 digests in accepted_uv_lock_sha256.
       Fails closed if uv.lock is missing, malformed, modified, or re-resolved on disk
       (even though untracked by Git).
    4. Enforces exact version matching via importlib.metadata for all required core runtime
       dependencies (dataframe, calendar, hours, market data clients, indicators, etc.).
    5. When require_live_provider_packages=True, additionally enforces provider packages
       (e.g. alpaca-py, pydantic, pydantic-core).
    """
    import importlib.metadata

    if spec_path is None:
        spec_path = repo_root / CORR_003_ENV_SPEC_PATH

    if not spec_path.exists():
        raise RuntimeError(f"Runtime environment freeze specification not found: {spec_path}")

    raw_spec_bytes = spec_path.read_bytes()
    actual_spec_hash = hashlib.sha256(raw_spec_bytes).hexdigest()

    if verify_spec_hash and actual_spec_hash != LOCKED_003D_CORR_003_ENV_SPEC_SHA256:
        raise RuntimeError(
            f"Runtime environment freeze specification hash mismatch: "
            f"expected '{LOCKED_003D_CORR_003_ENV_SPEC_SHA256}', got '{actual_spec_hash}'"
        )

    try:
        env_spec = json.loads(raw_spec_bytes.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Failed to parse runtime environment freeze specification JSON: {exc}") from exc

    errors: list[str] = []

    # 1. Enforce Python major/minor version
    current_py = f"{sys.version_info.major}.{sys.version_info.minor}"
    expected_py = env_spec.get("python_version_major_minor", "3.11")
    if current_py != expected_py:
        errors.append(f"Python version mismatch: expected '{expected_py}', got '{current_py}'")

    # 2. Enforce uv.lock SHA-256 integrity on disk (even if ignored by git)
    if check_uv_lock:
        uv_lock_path = repo_root / "uv.lock"
        if not uv_lock_path.exists():
            errors.append(
                f"Missing required uv.lock on disk at '{uv_lock_path}'. "
                f"Because uv.lock is ignored by git, the operator must restore or synchronize the audited "
                f"lockfile before running the live pilot (e.g. run 'uv sync --extra dev --extra all')."
            )
        else:
            raw_accepted = env_spec.get("accepted_uv_lock_sha256") or env_spec.get("uv_lock_sha256")
            if not raw_accepted:
                errors.append(
                    "Runtime environment specification is missing required 'accepted_uv_lock_sha256' "
                    "or 'uv_lock_sha256' field."
                )
            else:
                if isinstance(raw_accepted, dict):
                    accepted_hashes = list(raw_accepted.values())
                elif isinstance(raw_accepted, (list, tuple, set)):
                    accepted_hashes = list(raw_accepted)
                else:
                    accepted_hashes = [str(raw_accepted)]
                accepted_hashes = [h for h in accepted_hashes if isinstance(h, str) and h.strip()]
                if not accepted_hashes:
                    errors.append(
                        "Runtime environment specification contains empty or invalid accepted lockfile hashes."
                    )
                else:
                    actual_uv_sha = hashlib.sha256(uv_lock_path.read_bytes()).hexdigest()
                    if actual_uv_sha not in accepted_hashes:
                        errors.append(
                            f"Ignored uv.lock has been modified or re-resolved on disk: "
                            f"expected SHA-256 in {accepted_hashes}, got '{actual_uv_sha}'. "
                            f"To reproduce the audited lockfile, run 'uv sync --extra dev --extra all'."
                        )

    # 3. Enforce exact installed package versions
    packages_to_check: dict[str, str] = {}
    packages_to_check.update(env_spec.get("core_runtime_packages", {}))
    if require_live_provider_packages:
        packages_to_check.update(env_spec.get("live_provider_packages", {}))

    for pkg_name, exp_ver in packages_to_check.items():
        try:
            actual_ver = importlib.metadata.version(pkg_name)
            if actual_ver != exp_ver:
                errors.append(
                    f"Mismatched package version for '{pkg_name}': expected '{exp_ver}', got '{actual_ver}'"
                )
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"Missing required package: '{pkg_name}' (expected version '{exp_ver}')")

    if errors:
        raise RuntimeError(
            f"Runtime environment freeze verification failed ({len(errors)} errors):\n  "
            + "\n  ".join(errors)
        )

    return env_spec


def check_pilot_authorization(
    repo_root: Path,
    expected_sha: str,
    authorized_by_gary: bool = False,
    pilot_date: str = PILOT_DATE,
) -> None:
    """Validate explicit committed authorization record from Gary Yang before live provider access."""
    if not authorized_by_gary:
        raise PermissionError(
            "Live execution gate active: Gary Yang has not granted live pilot authorization. "
            "Deliver draft PR with passing offline replay tests and stop at execution gate."
        )

    auth_path = repo_root / "docs" / "research" / "authorizations" / "DAYTRADE-003D-CORR-003-AUTHORIZATION.json"
    if not auth_path.exists():
        raise PermissionError(
            f"Live execution gate active: Missing Gary Yang authorization file at {auth_path}. "
            f"A user-supplied CLI flag is insufficient; an explicit committed authorization record is required."
        )

    try:
        auth_data = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PermissionError(f"Malformed authorization record: {exc}") from exc

    if auth_data.get("authorized_by") != "Gary Yang":
        raise PermissionError("Authorization record is not authorized by Gary Yang")
    if auth_data.get("task_id") != TASK_ID:
        raise PermissionError(f"Authorization record task_id mismatch: {auth_data.get('task_id')} != {TASK_ID}")
    if auth_data.get("pilot_date") != pilot_date:
        raise PermissionError(f"Authorization record pilot_date mismatch: {auth_data.get('pilot_date')} != {pilot_date}")

    frozen_sha = auth_data.get("frozen_implementation_sha", auth_data.get("frozen_sha"))
    if frozen_sha != expected_sha:
        raise PermissionError(f"Authorization record SHA mismatch: {frozen_sha} != {expected_sha}")

    if auth_data.get("run_scope") != "ONE_SHOT_PILOT_JAN_2_2024":
        raise PermissionError(
            f"Authorization record run_scope mismatch: {auth_data.get('run_scope')} != ONE_SHOT_PILOT_JAN_2_2024"
        )

    try:
        st_res = subprocess.run(
            ["git", "status", "--porcelain", str(auth_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if st_res.returncode != 0:
            raise PermissionError(f"Failed to check git status of authorization file: {st_res.stderr.strip()}")
        if st_res.stdout.strip():
            raise PermissionError("Authorization file is modified or untracked in git working tree")
    except PermissionError:
        raise
    except Exception as exc:
        raise PermissionError(f"Failed to check git status of authorization file: {exc}") from exc


# -----------------------------------------------------------------------------
# Deterministic Offline Replay
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayResult:
    """Result of deterministic offline replay from persisted private raw evidence."""

    disposition: PilotDisposition
    blockers: list[str]
    target_audit: TargetUniverseAudit
    daily_audit: BroadDailyAvailabilityAudit
    screening_audit: CandidateScreeningAudit
    selection_evidence: FrozenSelectionEvidence
    stage_b_audit: StageBPathAudit
    selection_records: list[dict[str, Any]]
    manifest_sha256: str
    replayed_at_utc: str
    daily_provider_failures: tuple[str, ...] = ()
    provider_data_integrity_success: bool = True


def _extract_batch_meta_strict(batch_dict: dict[str, Any]) -> dict[str, Any]:
    """Extract metadata from persisted batch payload without inventing optimistic defaults."""
    if "meta" in batch_dict and isinstance(batch_dict["meta"], dict):
        m = batch_dict["meta"].copy()
        if "http_status" in batch_dict:
            m["http_status"] = batch_dict["http_status"]
        if "pagination_complete" in batch_dict:
            m["pagination_complete"] = batch_dict["pagination_complete"]
        if "page_count" not in m and "page_count" in batch_dict:
            m["page_count"] = batch_dict["page_count"]
        if "raw_pages" not in m and "raw_pages" in batch_dict:
            m["raw_pages"] = batch_dict["raw_pages"]
        if "response_symbols" not in m and "response_symbols" in batch_dict:
            m["response_symbols"] = batch_dict["response_symbols"]
        return m

    # Extract provenance fields directly from top-level batch dictionary
    # Fail closed: do NOT invent http_status=200 or pagination_complete=True!
    m = {}
    for key in (
        "http_status",
        "pagination_complete",
        "page_count",
        "safe_error_classification",
        "safe_error",
        "repeated_page_token",
        "pagination_cycle_detected",
        "terminal_next_page_token_present",
        "unconsumed_page_token_present",
        "terminal_next_page_token",
        "response_symbols",
        "malformed_timestamp_counts",
        "token_hashes",
        "token_sequence_sha256",
        "raw_pages",
        "request_params",
    ):
        if key in batch_dict:
            m[key] = batch_dict[key]
    return m


def _verify_request_params_consistency(
    batch_dict: dict[str, Any],
    symbols_requested: list[str],
    expected_timeframe: str | None = None,
    expected_feed: str | None = None,
    expected_adjustment: str | None = None,
    expected_asof: str | None = None,
    expected_start: datetime | None = None,
    expected_end: datetime | None = None,
) -> None:
    """Verify that persisted request_params are genuine, consistent, and match expected stage parameters."""
    req_params = batch_dict.get("request_params")
    if not req_params and isinstance(batch_dict.get("meta"), dict):
        req_params = batch_dict["meta"].get("request_params")

    if not req_params or not isinstance(req_params, dict):
        raise ReplayIntegrityError("Missing or invalid request_params in batch artifact")

    # 1. Symbol provenance: support comma-separated string (standard Alpaca client) and list
    p_syms = req_params.get("symbols")
    if isinstance(p_syms, str):
        parsed_syms = [s.strip().upper() for s in p_syms.split(",") if s.strip()]
    elif isinstance(p_syms, list):
        parsed_syms = [s.strip().upper() for s in p_syms if isinstance(s, str) and s.strip()]
    else:
        raise ReplayIntegrityError(f"Missing or invalid request_params symbols format: {type(p_syms)}")

    expected_syms = sorted(s.strip().upper() for s in symbols_requested)
    if sorted(parsed_syms) != expected_syms:
        raise ReplayIntegrityError(
            f"Contradictory request parameters: request_params symbols {parsed_syms} != symbols_requested {expected_syms}"
        )

    # 2. Stage-specific PIT parameter checks (fail closed: reject missing/contradictory)
    if expected_timeframe is not None:
        actual_tf = req_params.get("timeframe")
        if actual_tf != expected_timeframe:
            raise ReplayIntegrityError(
                f"Contradictory request timeframe: expected '{expected_timeframe}', got '{actual_tf}'"
            )

    if expected_feed is not None:
        actual_feed = req_params.get("feed")
        if actual_feed != expected_feed:
            raise ReplayIntegrityError(
                f"Contradictory request feed: expected '{expected_feed}', got '{actual_feed}'"
            )

    if expected_adjustment is not None:
        actual_adj = req_params.get("adjustment")
        if actual_adj != expected_adjustment:
            raise ReplayIntegrityError(
                f"Contradictory request adjustment: expected '{expected_adjustment}', got '{actual_adj}'"
            )

    if expected_asof is not None:
        actual_asof = req_params.get("asof")
        if actual_asof != expected_asof:
            raise ReplayIntegrityError(
                f"Contradictory request asof: expected '{expected_asof}', got '{actual_asof}'"
            )

    if expected_start is not None:
        actual_start = req_params.get("start")
        if not actual_start:
            raise ReplayIntegrityError("Missing request start parameter")
        exp_start_str = expected_start.isoformat().replace("+00:00", "Z")
        if actual_start != exp_start_str:
            raise ReplayIntegrityError(
                f"Contradictory request start: expected '{exp_start_str}', got '{actual_start}'"
            )

    if expected_end is not None:
        actual_end = req_params.get("end")
        if not actual_end:
            raise ReplayIntegrityError("Missing request end parameter")
        exp_end_str = expected_end.isoformat().replace("+00:00", "Z")
        if actual_end != exp_end_str:
            raise ReplayIntegrityError(
                f"Contradictory request end: expected '{exp_end_str}', got '{actual_end}'"
            )

    # 3. Token sequence parity
    meta = batch_dict.get("meta")
    if isinstance(meta, dict):
        tok_hashes = meta.get("token_hashes", batch_dict.get("token_hashes"))
        tok_seq = meta.get("token_sequence_sha256", batch_dict.get("token_sequence_sha256"))
        if tok_hashes is not None and tok_seq is not None:
            expected_seq = hashlib.sha256("".join(tok_hashes).encode("utf-8")).hexdigest()
            if tok_seq != expected_seq:
                raise ReplayIntegrityError(
                    f"Token sequence hash mismatch: persisted '{tok_seq}' != recomputed '{expected_seq}'"
                )


def determine_pilot_disposition_corr_003(
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
        return PilotDisposition.INVALID_CORR_003_IMPLEMENTATION, blocker_details

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


def replay_corr_003_pilot(
    input_dir: Path,
    repo_root: Path,
    pilot_date: str = PILOT_DATE,
) -> ReplayResult:
    """Execute complete deterministic offline replay from persisted raw provider artifacts.

    Guarantees:
    - Zero network calls.
    - Zero credentials required.
    - Upstream specification hashes verified.
    - Manifest and artifact checksums verified; fails closed on missing or tampered files.
    - Provider payload integrity validated.
    - Screening, candidate selection, Top-20 ranking, and Stage-B usability reproduced deterministically.
    """
    # 1. Spec hash verification
    specs_ok, _hashes, spec_errors = verify_upstream_spec_hashes(repo_root)
    if not specs_ok:
        raise ReplayIntegrityError(f"Upstream specification hash verification failed: {spec_errors}")

    # 2. Production strategy registry check
    if APPROVED_PRODUCTION_STRATEGIES != ():
        raise ReplayIntegrityError(
            f"Production strategy registry is not empty: {APPROVED_PRODUCTION_STRATEGIES}"
        )

    # 3. Manifest checksum verification
    manifest_ok, _manifest_data, manifest_errors = verify_replay_manifest(input_dir, pilot_date)
    if not manifest_ok:
        raise ReplayIntegrityError(
            f"Replay manifest verification failed closed: {manifest_errors}"
        )
    manifest_sha = hash_bytes((input_dir / f"manifest_{pilot_date}.json").read_bytes())

    # -------------------------------------------------------------------------
    # PHASE 1: Parse Massive Reference Snapshot & Target Universe
    # -------------------------------------------------------------------------
    ref_path = input_dir / f"massive_reference_{pilot_date}.json"
    if not ref_path.exists():
        raise ReplayIntegrityError(f"Missing reference snapshot file: {ref_path}")
    raw_reference_rows = json.loads(ref_path.read_text(encoding="utf-8"))
    target_audit, _target_rows = filter_and_audit_target_universe(raw_reference_rows)

    # Validate persisted target universe artifact matches deterministic recomputation
    univ_path = input_dir / f"universe_{pilot_date}.json"
    if not univ_path.exists():
        raise ReplayIntegrityError(f"Missing target universe artifact: {univ_path}")
    univ_payload = json.loads(univ_path.read_text(encoding="utf-8"))
    if univ_payload.get("universe_sha256") != target_audit.universe_sha256:
        raise ReplayIntegrityError(
            f"Universe hash mismatch: persisted {univ_payload.get('universe_sha256')} != recomputed {target_audit.universe_sha256}"
        )
    if univ_payload.get("canonical_target_universe_count") != target_audit.canonical_target_universe_count:
        raise ReplayIntegrityError(
            f"Universe count mismatch: persisted {univ_payload.get('canonical_target_universe_count')} != recomputed {target_audit.canonical_target_universe_count}"
        )
    if sorted(univ_payload.get("valid_symbols", [])) != sorted(target_audit.valid_target_symbols):
        raise ReplayIntegrityError("Universe valid symbols mismatch between persisted and recomputed")
    if sorted(univ_payload.get("ambiguous_symbols", [])) != sorted(target_audit.ambiguous_symbols):
        raise ReplayIntegrityError("Universe ambiguous symbols mismatch between persisted and recomputed")

    # -------------------------------------------------------------------------
    # PHASE 2: Broad Daily Screening across Target Universe
    # -------------------------------------------------------------------------
    daily_path = input_dir / "alpaca_daily_dec2023.json"
    if not daily_path.exists():
        raise ReplayIntegrityError(f"Missing daily bars artifact: {daily_path}")
    daily_payload = json.loads(daily_path.read_text(encoding="utf-8"))
    daily_batches = daily_payload.get("batches", [])

    # Validate complete expected target symbol coverage across daily batches
    daily_requested_all: set[str] = set()
    for b in daily_batches:
        daily_requested_all.update(s.strip().upper() for s in b.get("symbols_requested", []))
    missing_daily_coverage = set(target_audit.valid_target_symbols) - daily_requested_all
    if missing_daily_coverage:
        raise ReplayIntegrityError(
            f"Daily batches missing coverage for canonical target symbols: {sorted(missing_daily_coverage)}"
        )

    daily_bars_by_symbol: dict[str, list[DailyBar]] = {}
    daily_provider_failures: set[str] = set()
    target_dt = date.fromisoformat(pilot_date)

    for b in daily_batches:
        symbols_req = b.get("symbols_requested", [])
        bars_by_sym = b.get("bars_by_symbol", {})
        meta_dict = _extract_batch_meta_strict(b)
        _verify_request_params_consistency(
            b,
            symbols_req,
            expected_timeframe="1Day",
            expected_feed="sip",
            expected_adjustment="raw",
            expected_asof=pilot_date,
            expected_start=datetime(2023, 12, 1, 0, 0, tzinfo=ZoneInfo("UTC")),
            expected_end=datetime(2023, 12, 29, 23, 59, tzinfo=ZoneInfo("UTC")),
        )

        batch_check = validate_provider_batch_response(
            symbols_requested=symbols_req,
            meta=meta_dict,
            bars_by_symbol=bars_by_sym,
            expected_start=datetime(2023, 12, 1, 0, 0, tzinfo=ZoneInfo("UTC")),
            expected_end=datetime(2023, 12, 31, 23, 59, tzinfo=ZoneInfo("UTC")),
            require_raw_pages=True,
        )
        if not batch_check.is_valid:
            daily_provider_failures.update(symbols_req)
            continue

        for sym, raw_bars in bars_by_sym.items():
            sym_clean = sym.strip().upper()
            bars: list[DailyBar] = []
            for rb in raw_bars:
                raw_t = rb["t"]
                ts = (
                    datetime.fromisoformat(raw_t)
                    if isinstance(raw_t, str)
                    else raw_t
                )
                ny_d = ts.astimezone(MARKET_TIMEZONE).date()
                bars.append(
                    DailyBar(
                        symbol=sym_clean,
                        session_date=ny_d,
                        open=float(rb.get("o", rb.get("open", 0.0))),
                        high=float(rb.get("h", rb.get("high", 0.0))),
                        low=float(rb.get("l", rb.get("low", 0.0))),
                        close=float(rb.get("c", rb.get("close", 0.0))),
                        volume=float(rb.get("v", rb.get("volume", 0.0))),
                    )
                )
            if bars:
                daily_bars_by_symbol[sym_clean] = sorted(bars, key=lambda x: x.session_date)

    daily_audit, _computable, daily_base_qualified = audit_broad_daily_availability(
        valid_target_symbols=target_audit.valid_target_symbols,
        ambiguous_symbols=target_audit.ambiguous_symbols,
        daily_bars_by_symbol=daily_bars_by_symbol,
        target_session=target_dt,
        lookback=14,
        adv_min=1_000_000.0,
        atr_min=0.50,
    )

    # -------------------------------------------------------------------------
    # PHASE 3: Current Opening Range & Prior 14 Sessions RV
    # -------------------------------------------------------------------------
    current_or_path = input_dir / f"alpaca_current_or_{pilot_date}.json"
    if not current_or_path.exists():
        raise ReplayIntegrityError(f"Missing current opening range artifact: {current_or_path}")
    cur_payload = json.loads(current_or_path.read_text(encoding="utf-8"))
    cur_batches = cur_payload.get("batches", [])

    # Validate complete expected daily-base-qualified coverage across current OR batches
    cur_requested_all: set[str] = set()
    for b in cur_batches:
        cur_requested_all.update(s.strip().upper() for s in b.get("symbols_requested", []))
    missing_cur_coverage = set(daily_base_qualified) - cur_requested_all
    if missing_cur_coverage:
        raise ReplayIntegrityError(
            f"Current OR batches missing coverage for daily-base-qualified symbols: {sorted(missing_cur_coverage)}"
        )

    current_or_by_symbol: dict[str, OpeningRange | None] = {}
    current_or_failures: set[str] = set()

    for b in cur_batches:
        symbols_req = b.get("symbols_requested", [])
        bars_by_sym = b.get("bars_by_symbol", {})
        meta_dict = _extract_batch_meta_strict(b)
        _verify_request_params_consistency(
            b,
            symbols_req,
            expected_timeframe="1Min",
            expected_feed="sip",
            expected_adjustment="raw",
            expected_asof=pilot_date,
            expected_start=datetime(target_dt.year, target_dt.month, target_dt.day, 9, 30, tzinfo=MARKET_TIMEZONE).astimezone(ZoneInfo("UTC")),
            expected_end=datetime(target_dt.year, target_dt.month, target_dt.day, 9, 34, 59, tzinfo=MARKET_TIMEZONE).astimezone(ZoneInfo("UTC")),
        )

        batch_check = validate_provider_batch_response(
            symbols_requested=symbols_req,
            meta=meta_dict,
            bars_by_symbol=bars_by_sym,
            allowed_time_window=(time(9, 30), time(9, 34)),
            session_date=target_dt,
            require_raw_pages=True,
        )
        if not batch_check.is_valid:
            current_or_failures.update(symbols_req)
            continue

        for sym in symbols_req:
            sym_clean = sym.strip().upper()
            raw_bars = bars_by_sym.get(sym_clean, [])
            if not raw_bars:
                current_or_by_symbol[sym_clean] = None
            else:
                m_bars: list[MinuteBar] = []
                for rb in raw_bars:
                    raw_t = rb["t"]
                    ts = (
                        datetime.fromisoformat(raw_t)
                        if isinstance(raw_t, str)
                        else raw_t
                    )
                    m_bars.append(
                        MinuteBar(
                            symbol=sym_clean,
                            timestamp=ts,
                            session_date=target_dt,
                            open=float(rb.get("o", rb.get("open", 0.0))),
                            high=float(rb.get("h", rb.get("high", 0.0))),
                            low=float(rb.get("l", rb.get("low", 0.0))),
                            close=float(rb.get("c", rb.get("close", 0.0))),
                            volume=float(rb.get("v", rb.get("volume", 0.0))),
                        )
                    )
                op = evaluate_opening_range(m_bars, require_five_bars=False)
                current_or_by_symbol[sym_clean] = op

    prior_or_path = input_dir / f"alpaca_prior_or_14sessions_{pilot_date}.json"
    if not prior_or_path.exists():
        raise ReplayIntegrityError(f"Missing prior OR artifact: {prior_or_path}")
    prior_payload = json.loads(prior_or_path.read_text(encoding="utf-8"))
    sessions_data = prior_payload.get("sessions_data", {})

    expected_prior_sessions = [s.isoformat() for s in get_prior_xnys_sessions(target_dt, 14)]
    missing_prior_sessions = set(expected_prior_sessions) - set(sessions_data.keys())
    if missing_prior_sessions:
        raise ReplayIntegrityError(
            f"Prior OR artifact missing expected sessions: {sorted(missing_prior_sessions)}"
        )

    prior_obs_by_symbol: dict[str, list[OpeningRangeVolumeObservation]] = {}
    prior_or_failures: set[str] = set()

    for sess_str, b_list in sessions_data.items():
        sess_d = date.fromisoformat(sess_str)
        for b in b_list:
            symbols_req = b.get("symbols_requested", [])
            bars_by_sym = b.get("bars_by_symbol", {})
            meta_dict = _extract_batch_meta_strict(b)
            _verify_request_params_consistency(
                b,
                symbols_req,
                expected_timeframe="1Min",
                expected_feed="sip",
                expected_adjustment="raw",
                expected_asof=pilot_date,
                expected_start=datetime(sess_d.year, sess_d.month, sess_d.day, 9, 30, tzinfo=MARKET_TIMEZONE).astimezone(ZoneInfo("UTC")),
                expected_end=datetime(sess_d.year, sess_d.month, sess_d.day, 9, 34, 59, tzinfo=MARKET_TIMEZONE).astimezone(ZoneInfo("UTC")),
            )

            batch_check = validate_provider_batch_response(
                symbols_requested=symbols_req,
                meta=meta_dict,
                bars_by_symbol=bars_by_sym,
                allowed_time_window=(time(9, 30), time(9, 34)),
                session_date=sess_d,
                require_raw_pages=True,
            )
            if not batch_check.is_valid:
                prior_or_failures.update(symbols_req)
                continue

            for sym in symbols_req:
                sym_clean = sym.strip().upper()
                raw_bars = bars_by_sym.get(sym_clean, [])
                vol = (
                    sum(float(rb.get("v", rb.get("volume", 0.0))) for rb in raw_bars)
                    if raw_bars
                    else 0.0
                )
                prior_obs_by_symbol.setdefault(sym_clean, []).append(
                    OpeningRangeVolumeObservation(
                        symbol=sym_clean,
                        session_date=sess_d,
                        volume=vol,
                    )
                )

    (
        screening_audit,
        _outcomes,
        eligible_candidates,
        surviving_ors,
    ) = audit_candidate_screening(
        daily_base_qualified_symbols=daily_base_qualified,
        current_or_by_symbol=current_or_by_symbol,
        current_or_provider_failures=current_or_failures,
        prior_or_obs_by_symbol=prior_obs_by_symbol,
        prior_or_provider_failures=prior_or_failures,
        daily_bars_by_symbol=daily_bars_by_symbol,
        target_session=target_dt,
        price_min=5.0,
        adv_min=1_000_000.0,
        atr_min=0.50,
        rv_min=1.0,
        gate_threshold=CANDIDATE_SCREENING_GATE_THRESHOLD,
    )

    # -------------------------------------------------------------------------
    # PHASE 4: Freeze Top-20 Selection & Parity Verification
    # -------------------------------------------------------------------------
    ranked_candidates = rank_and_select_top_20(
        candidates=eligible_candidates,
        opening_ranges=surviving_ors,
        session_start_equity=25000.0,
        top_n=20,
    )
    (
        selection_evidence,
        selection_records,
        _selected_syms,
    ) = freeze_top_20_selection(ranked_candidates)

    # Validate persisted Top-20 selection artifact matches recomputation
    sel_path = input_dir / f"top_20_selection_{pilot_date}.json"
    if not sel_path.exists():
        raise ReplayIntegrityError(f"Missing Top-20 selection artifact: {sel_path}")
    sel_payload = json.loads(sel_path.read_text(encoding="utf-8"))
    if sel_payload.get("selection_sha256") != selection_evidence.selection_sha256:
        raise ReplayIntegrityError(
            f"Top-20 selection hash mismatch: persisted {sel_payload.get('selection_sha256')} != recomputed {selection_evidence.selection_sha256}"
        )
    if sel_payload.get("selected_count") != selection_evidence.selected_count:
        raise ReplayIntegrityError(
            f"Top-20 selected count mismatch: persisted {sel_payload.get('selected_count')} != recomputed {selection_evidence.selected_count}"
        )
    if sel_payload.get("doji_count") != selection_evidence.doji_count:
        raise ReplayIntegrityError(
            f"Top-20 doji count mismatch: persisted {sel_payload.get('doji_count')} != recomputed {selection_evidence.doji_count}"
        )
    if sel_payload.get("eligible_candidates_count") != selection_evidence.eligible_candidates_count:
        raise ReplayIntegrityError(
            f"Top-20 eligible candidates count mismatch: persisted {sel_payload.get('eligible_candidates_count')} != recomputed {selection_evidence.eligible_candidates_count}"
        )
    if sel_payload.get("records") != selection_records:
        raise ReplayIntegrityError(
            "Top-20 selection records mismatch between persisted artifact and recomputed selection"
        )

    # -------------------------------------------------------------------------
    # PHASE 5: Stage-B Minutes for Actionable Symbols
    # -------------------------------------------------------------------------
    actionable_symbols = [
        r["symbol"] for r in selection_records if r["order_intent_status"] != "NO_ORDER"
    ]
    stage_b_path = input_dir / f"alpaca_stage_b_{pilot_date}.json"
    if not stage_b_path.exists():
        raise ReplayIntegrityError(f"Missing Stage-B artifact: {stage_b_path}")
    sb_payload = json.loads(stage_b_path.read_text(encoding="utf-8"))
    sb_batches = sb_payload.get("batches", [])

    # Validate complete expected actionable symbol coverage across Stage-B batches
    if actionable_symbols:
        sb_requested_all: set[str] = set()
        for b in sb_batches:
            sb_requested_all.update(s.strip().upper() for s in b.get("symbols_requested", []))
        missing_sb_coverage = set(actionable_symbols) - sb_requested_all
        if missing_sb_coverage:
            raise ReplayIntegrityError(
                f"Stage-B batches missing coverage for actionable symbols: {sorted(missing_sb_coverage)}"
            )

    stage_b_bars_by_symbol: dict[str, list[MinuteBar]] = {}
    stage_b_failures: set[str] = set()

    for b in sb_batches:
        symbols_req = b.get("symbols_requested", [])
        bars_by_sym = b.get("bars_by_symbol", {})
        meta_dict = _extract_batch_meta_strict(b)
        _verify_request_params_consistency(
            b,
            symbols_req,
            expected_timeframe="1Min",
            expected_feed="sip",
            expected_adjustment="raw",
            expected_asof=pilot_date,
            expected_start=datetime(target_dt.year, target_dt.month, target_dt.day, 9, 35, tzinfo=MARKET_TIMEZONE).astimezone(ZoneInfo("UTC")),
            expected_end=datetime(target_dt.year, target_dt.month, target_dt.day, 15, 59, 59, tzinfo=MARKET_TIMEZONE).astimezone(ZoneInfo("UTC")),
        )

        batch_check = validate_provider_batch_response(
            symbols_requested=symbols_req,
            meta=meta_dict,
            bars_by_symbol=bars_by_sym,
            allowed_time_window=(time(9, 35), time(15, 59)),
            session_date=target_dt,
            require_raw_pages=True,
        )
        if not batch_check.is_valid:
            stage_b_failures.update(symbols_req)
            continue

        for sym in symbols_req:
            sym_clean = sym.strip().upper()
            raw_bars = bars_by_sym.get(sym_clean, [])
            m_bars = []
            for rb in raw_bars:
                raw_t = rb["t"]
                ts = (
                    datetime.fromisoformat(raw_t)
                    if isinstance(raw_t, str)
                    else raw_t
                )
                m_bars.append(
                    MinuteBar(
                        symbol=sym_clean,
                        timestamp=ts,
                        session_date=target_dt,
                        open=float(rb.get("o", rb.get("open", 0.0))),
                        high=float(rb.get("h", rb.get("high", 0.0))),
                        low=float(rb.get("l", rb.get("low", 0.0))),
                        close=float(rb.get("c", rb.get("close", 0.0))),
                        volume=float(rb.get("v", rb.get("volume", 0.0))),
                    )
                )
            stage_b_bars_by_symbol[sym_clean] = sorted(m_bars, key=lambda x: x.timestamp)

    stage_b_audit = audit_stage_b_price_path_corr_003(
        active_selected_symbols=actionable_symbols,
        stage_b_bars_by_symbol=stage_b_bars_by_symbol,
        stage_b_provider_failures=stage_b_failures,
        expected_minutes=385,
        session_date=target_dt,
    )

    # -------------------------------------------------------------------------
    # PHASE 6: Final Disposition
    # -------------------------------------------------------------------------
    provider_data_integrity_success = (
        len(daily_provider_failures) == 0
        and len(current_or_failures) == 0
        and len(prior_or_failures) == 0
        and stage_b_audit.provider_failure_count == 0
        and stage_b_audit.integrity_failure_count == 0
    )

    disposition, blockers = determine_pilot_disposition_corr_003(
        reference_success=True,
        provider_access_success=True,
        provider_data_integrity_success=provider_data_integrity_success,
        candidate_screening_gate_passed=screening_audit.meets_screening_gate,
        eligible_candidate_count=screening_audit.eligible_candidate_count,
        stage_b_path_usable=stage_b_audit.is_usable,
    )

    return ReplayResult(
        disposition=disposition,
        blockers=blockers,
        target_audit=target_audit,
        daily_audit=daily_audit,
        screening_audit=screening_audit,
        selection_evidence=selection_evidence,
        stage_b_audit=stage_b_audit,
        selection_records=selection_records,
        manifest_sha256=manifest_sha,
        replayed_at_utc=datetime.now(ZoneInfo("UTC")).isoformat(),
        daily_provider_failures=tuple(sorted(daily_provider_failures)),
        provider_data_integrity_success=provider_data_integrity_success,
    )
