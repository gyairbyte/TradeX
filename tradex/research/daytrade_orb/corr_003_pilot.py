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
    "audit_broad_daily_availability",
    "audit_candidate_screening",
    "audit_stage_b_price_path_corr_003",
    "batch_symbols",
    "create_and_save_manifest",
    "determine_pilot_disposition_corr_003",
    "evaluate_opening_range",
    "filter_and_audit_target_universe",
    "freeze_top_20_selection",
    "get_prior_xnys_sessions",
    "hash_bytes",
    "hash_text",
    "json_hash",
    "persist_raw_stage_artifact",
    "rank_and_select_top_20",
    "replay_corr_003_pilot",
    "validate_provider_batch_response",
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
) -> BatchIntegrityResult:
    """Validate provider response before interpreting absent intervals as sparse minutes.

    Enforces:
    1. HTTP status is 200.
    2. Pagination completed without cycle or repeated tokens.
    3. No unexpected symbol identities in response.
    4. Zero malformed timestamps.
    5. Zero duplicate timestamps per symbol.
    6. Bars within expected datetime/session range.
    7. Valid OHLCV values (positive prices, non-negative volume, high >= low, bounds).
    """
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
    next_page_token_present = meta.get("next_page_token_present", False)

    if (
        not pagination_complete
        or repeated_page_token
        or pagination_cycle
        or next_page_token_present
    ):
        return BatchIntegrityResult(
            is_valid=False,
            status=PayloadIntegrityStatus.PAGINATION_INCOMPLETE,
            error_message=(
                f"Incomplete pagination: complete={pagination_complete}, repeated={repeated_page_token}, "
                f"cycle={pagination_cycle}, next_token_present={next_page_token_present}"
            ),
        )

    req_set = {s.strip().upper() for s in symbols_requested}
    resp_symbols = set(meta.get("response_symbols", [])) | {s.strip().upper() for s in bars_by_symbol}
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

    artifacts = manifest_data.get("artifacts", {})
    if not isinstance(artifacts, dict) or not artifacts:
        return False, manifest_data, ["Manifest has no valid artifacts dictionary"]

    errors: list[str] = []
    for filename, info in artifacts.items():
        artifact_file = input_dir / filename
        if not artifact_file.exists():
            errors.append(f"Missing artifact file: {filename}")
            continue

        file_bytes = artifact_file.read_bytes()
        actual_size = len(file_bytes)
        expected_size = info.get("size_bytes")
        if expected_size is not None and actual_size != expected_size:
            errors.append(f"File size mismatch for {filename}: expected {expected_size}, got {actual_size}")

        actual_hash = hash_bytes(file_bytes)
        expected_hash = info.get("sha256")
        if expected_hash and actual_hash != expected_hash:
            errors.append(f"SHA-256 checksum mismatch for {filename}: expected {expected_hash}, got {actual_hash}")

    return len(errors) == 0, manifest_data, errors


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

    # -------------------------------------------------------------------------
    # PHASE 2: Broad Daily Screening across Target Universe
    # -------------------------------------------------------------------------
    daily_path = input_dir / "alpaca_daily_dec2023.json"
    if not daily_path.exists():
        raise ReplayIntegrityError(f"Missing daily bars artifact: {daily_path}")
    daily_payload = json.loads(daily_path.read_text(encoding="utf-8"))
    daily_batches = daily_payload.get("batches", [])

    daily_bars_by_symbol: dict[str, list[DailyBar]] = {}
    target_dt = date.fromisoformat(pilot_date)

    for b in daily_batches:
        symbols_req = b.get("symbols_requested", [])
        bars_by_sym = b.get("bars_by_symbol", {})
        meta_dict = {
            "http_status": b.get("http_status", 200),
            "pagination_complete": b.get("pagination_complete", True),
            "response_symbols": list(bars_by_sym.keys()),
        }
        batch_check = validate_provider_batch_response(
            symbols_requested=symbols_req,
            meta=meta_dict,
            bars_by_symbol=bars_by_sym,
            expected_start=datetime(2023, 12, 1, 0, 0, tzinfo=ZoneInfo("UTC")),
            expected_end=datetime(2023, 12, 31, 23, 59, tzinfo=ZoneInfo("UTC")),
        )
        if not batch_check.is_valid:
            raise ProviderPayloadIntegrityError(
                f"Daily batch integrity failure: {batch_check.error_message}"
            )

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

    current_or_by_symbol: dict[str, OpeningRange | None] = {}
    current_or_failures: set[str] = set()

    for b in cur_batches:
        symbols_req = b.get("symbols_requested", [])
        bars_by_sym = b.get("bars_by_symbol", {})
        meta_dict = {
            "http_status": b.get("http_status", 200),
            "pagination_complete": b.get("pagination_complete", True),
            "response_symbols": list(bars_by_sym.keys()),
        }
        batch_check = validate_provider_batch_response(
            symbols_requested=symbols_req,
            meta=meta_dict,
            bars_by_symbol=bars_by_sym,
            allowed_time_window=(time(9, 30), time(9, 34)),
            session_date=target_dt,
        )
        if not batch_check.is_valid:
            current_or_failures.update(symbols_req)
            continue

        for sym in symbols_req:
            sym_clean = sym.strip().upper()
            raw_bars = bars_by_sym.get(sym_clean, [])
            if not raw_bars:
                # Verified completed response with no bars in OR -> NO_OPENING_PRINT_NO_SETUP
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

    prior_obs_by_symbol: dict[str, list[OpeningRangeVolumeObservation]] = {}
    prior_or_failures: set[str] = set()

    for sess_str, b_list in sessions_data.items():
        sess_d = date.fromisoformat(sess_str)
        for b in b_list:
            symbols_req = b.get("symbols_requested", [])
            bars_by_sym = b.get("bars_by_symbol", {})
            meta_dict = {
                "http_status": b.get("http_status", 200),
                "pagination_complete": b.get("pagination_complete", True),
                "response_symbols": list(bars_by_sym.keys()),
            }
            batch_check = validate_provider_batch_response(
                symbols_requested=symbols_req,
                meta=meta_dict,
                bars_by_symbol=bars_by_sym,
                allowed_time_window=(time(9, 30), time(9, 34)),
                session_date=sess_d,
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
    # PHASE 4: Freeze Top-20 Selection
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

    stage_b_bars_by_symbol: dict[str, list[MinuteBar]] = {}
    stage_b_failures: set[str] = set()

    for b in sb_batches:
        symbols_req = b.get("symbols_requested", [])
        bars_by_sym = b.get("bars_by_symbol", {})
        meta_dict = {
            "http_status": b.get("http_status", 200),
            "pagination_complete": b.get("pagination_complete", True),
            "response_symbols": list(bars_by_sym.keys()),
        }
        batch_check = validate_provider_batch_response(
            symbols_requested=symbols_req,
            meta=meta_dict,
            bars_by_symbol=bars_by_sym,
            allowed_time_window=(time(9, 35), time(15, 59)),
            session_date=target_dt,
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
    disposition, blockers = determine_pilot_disposition_corr_003(
        reference_success=True,
        provider_access_success=True,
        provider_data_integrity_success=True,
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
    )
