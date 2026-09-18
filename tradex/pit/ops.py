"""Deterministic PIT operations runner, versioned universe manifest, and capture health (MVP-ARCH-001-R7-PIT-001C1).

Provides:
- PITUniverseManifest: explicit, versioned, immutable universe description (loaded from JSON file)
- load_universe_manifest: validated JSON loader
- PITCapacityEstimate: deterministic pacing-floor calculation (no network)
- estimate_capacity: pure capacity math from manifest and pacing constant
- run_pit_slot: deterministic operational slot runner (earnings then reference, same universe)
- get_pit_slot_health: fully read-only capture health inspector
- CLI: validate-universe, run-slot, health subcommands

Governance:
- NO OS scheduler is installed or activated.
- NO active production universe is selected.
- NO Candidate or Journal writes.
- NO automatic watchlist/preset/scanner-derived universe selection.
- Schema remains v7.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from tradex.market.hours import MARKET_TIMEZONE, is_trading_day
from tradex.pit.earnings import (
    _get_aware_utc_now,
    compute_scheduled_slot_time,
)
from tradex.pit.massive_reference import DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS
from tradex.pit.models import (
    CaptureRunStatus,
    CaptureSlot,
    ObservationStatus,
    PITCaptureResult,
    PITEvidenceCompletenessTier,
    PITFamilyCompleteness,
    PITReferenceCaptureResult,
    PITSlotCompleteness,
    ReferenceObservationStatus,
    compute_universe_hash,
    normalize_symbols,
)
from tradex.pit.store import (
    list_earnings_capture_runs,
    list_earnings_snapshots,
    list_reference_capture_runs,
    list_reference_snapshots,
)

if TYPE_CHECKING:
    from tradex.config import TradeXSettings

# Universe manifest contract versions supported by this implementation.
_MANIFEST_CONTRACT_VERSION: int = 1
_MANIFEST_CONTRACT_VERSIONS: tuple[int, ...] = (1, 2)

# Pattern for syntactically valid universe_id: alphanumeric, hyphens, underscores, 1-64 chars.
_UNIVERSE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


# ─────────────────────────────────────────────────────────────────────────────
# Exception
# ─────────────────────────────────────────────────────────────────────────────

class PITOperationalUniverseConflictError(Exception):
    """Raised when existing PIT runs for the same date/slot used a materially different universe.

    This is a merge-gate requirement: changing the operational universe for a date/slot
    must be an explicit future operational decision, never automatic.
    """

    def __init__(
        self,
        message: str,
        *,
        existing_hash: str,
        new_hash: str,
        family: str,
    ) -> None:
        super().__init__(message)
        self.existing_hash = existing_hash
        self.new_hash = new_hash
        self.family = family


class PITOperationalManifestConflictError(Exception):
    """Raised when existing PIT runs for the same date/slot have a conflicting manifest or contract version."""

    def __init__(
        self,
        message: str,
        *,
        existing_hash: str | None = None,
        new_hash: str | None = None,
        family: str,
    ) -> None:
        super().__init__(message)
        self.existing_hash = existing_hash
        self.new_hash = new_hash
        self.family = family


# ─────────────────────────────────────────────────────────────────────────────
# Universe Manifest
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PITUniverseManifest:
    """Explicit, versioned, immutable operational symbol universe.

    Loaded from a JSON file with the canonical contract schema.
    All material fields are validated and normalized at load time.

    This prevents dynamic/mutable universe sources (watchlists, scanners, scores,
    candidates, journals) from being silently substituted.
    """

    contract_version: int
    universe_id: str
    universe_version: str
    effective_from: date
    symbols: tuple[str, ...]
    description: str
    applicability: Mapping[str, Mapping[str, str]] | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.contract_version, bool)
            or not isinstance(self.contract_version, int)
            or self.contract_version not in _MANIFEST_CONTRACT_VERSIONS
        ):
            raise ValueError(
                f"Unsupported manifest contract_version {self.contract_version!r}; "
                f"only contract_versions {_MANIFEST_CONTRACT_VERSIONS} are supported."
            )
        if not isinstance(self.universe_id, str) or not self.universe_id.strip():
            raise ValueError("universe_id must be a non-empty string")
        normalized_uid = self.universe_id.strip()
        if not _UNIVERSE_ID_PATTERN.match(normalized_uid):
            raise ValueError(
                f"universe_id {self.universe_id!r} is syntactically invalid; "
                "must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
            )
        object.__setattr__(self, "universe_id", normalized_uid)
        if not isinstance(self.universe_version, str) or not self.universe_version.strip():
            raise ValueError("universe_version must be a non-empty string")
        object.__setattr__(self, "universe_version", self.universe_version.strip())
        if not isinstance(self.effective_from, date) or isinstance(self.effective_from, datetime):
            raise TypeError("effective_from must be a date instance and not a datetime instance")
        if not isinstance(self.symbols, tuple) or len(self.symbols) == 0:
            raise ValueError("symbols must be a non-empty tuple of strings")
        if not isinstance(self.description, str):
            raise TypeError("description must be a str")
        # Normalize and deduplicate symbols (frozen dataclass: use object.__setattr__).
        # This ensures manifest.universe_hash == compute_universe_hash(symbols) always.
        normalized = normalize_symbols(self.symbols)
        object.__setattr__(self, "symbols", normalized)

        # Validate and normalize applicability
        if self.contract_version == 1:
            # v1: synthesize immutable {sym: {"earnings": "required", "reference": "required"}} in memory
            synthesized = MappingProxyType({
                sym: MappingProxyType({"earnings": "required", "reference": "required"})
                for sym in normalized
            })
            object.__setattr__(self, "applicability", synthesized)
        elif self.contract_version == 2:
            if self.applicability is None:
                raise ValueError("applicability field is required for contract_version=2")
            if not isinstance(self.applicability, (dict, Mapping)):
                raise TypeError(f"applicability must be a dict or mapping, got {type(self.applicability).__name__}")

            app_keys = set(self.applicability.keys())
            sym_set = set(normalized)

            missing_symbols = sorted(sym_set - app_keys)
            if missing_symbols:
                raise ValueError(f"Missing applicability declarations for symbols: {missing_symbols}")

            extra_symbols = sorted(app_keys - sym_set)
            if extra_symbols:
                raise ValueError(f"Extra symbols in applicability not present in symbols: {extra_symbols}")

            canonical_app: dict[str, Mapping[str, str]] = {}
            for sym in normalized:
                entry = self.applicability[sym]
                if not isinstance(entry, (dict, Mapping)):
                    raise TypeError(f"Applicability entry for symbol {sym!r} must be a dict, got {type(entry).__name__}")
                families = set(entry.keys())
                expected_families = {"earnings", "reference"}
                if families != expected_families:
                    raise ValueError(
                        f"Applicability for symbol {sym!r} must contain exactly {expected_families}, got {families}"
                    )
                earn_val = entry["earnings"]
                if earn_val not in ("required", "not_applicable"):
                    raise ValueError(
                        f"Invalid earnings applicability {earn_val!r} for symbol {sym!r}; must be 'required' or 'not_applicable'"
                    )
                ref_val = entry["reference"]
                if ref_val != "required":
                    raise ValueError(
                        f"Invalid reference applicability {ref_val!r} for symbol {sym!r}; must be 'required'"
                    )
                canonical_app[sym] = MappingProxyType({
                    "earnings": earn_val,
                    "reference": ref_val,
                })
            object.__setattr__(self, "applicability", MappingProxyType(canonical_app))

    @property
    def universe_hash(self) -> str:
        """SHA-256 hash of the normalized sorted symbol universe.

        Identical to compute_universe_hash(self.symbols), which is what
        earnings and reference capture services use. This identity is required
        for the same-universe-across-families invariant.
        """
        return compute_universe_hash(self.symbols)

    @property
    def manifest_hash(self) -> str:
        """SHA-256 hash of the canonical material manifest fields.

        Material fields (deterministically serialized):
          v1: contract_version, universe_id, universe_version, effective_from, symbols
          v2: contract_version, universe_id, universe_version, effective_from, symbols, applicability
        Non-material fields (excluded):
          description, filesystem path, file mtime, JSON key ordering
        """
        return _compute_manifest_hash(self)


def _compute_manifest_hash(manifest: PITUniverseManifest) -> str:
    """Compute deterministic SHA-256 hash of the manifest material fields."""
    if manifest.contract_version == 1:
        payload: dict[str, Any] = {
            "contract_version": 1,
            "effective_from": manifest.effective_from.isoformat(),
            "symbols": list(manifest.symbols),
            "universe_id": manifest.universe_id,
            "universe_version": manifest.universe_version,
        }
    elif manifest.contract_version == 2:
        assert manifest.applicability is not None
        payload = {
            "applicability": {
                sym: {
                    fam: manifest.applicability[sym][fam]
                    for fam in sorted(manifest.applicability[sym].keys())
                }
                for sym in sorted(manifest.symbols)
            },
            "contract_version": 2,
            "effective_from": manifest.effective_from.isoformat(),
            "symbols": list(manifest.symbols),
            "universe_id": manifest.universe_id,
            "universe_version": manifest.universe_version,
        }
    else:
        raise ValueError(f"Unsupported manifest contract_version {manifest.contract_version}")

    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def load_universe_manifest(path: Path | str) -> PITUniverseManifest:
    """Load and validate a PITUniverseManifest from a JSON file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If any material field is invalid or the manifest is malformed.
        TypeError: If field types are invalid.

    Symbols are normalized (trimmed, uppercased, deduplicated, sorted) before
    being stored in the manifest.  Any blank or non-string symbol causes a
    hard validation failure (no silent removal).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Universe manifest file not found: {p}")

    try:
        with p.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Manifest file is not valid JSON: {p}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Manifest root must be a JSON object, got {type(raw).__name__}")  # noqa: TRY004

    # Validate contract_version
    cv = raw.get("contract_version")
    if isinstance(cv, bool) or not isinstance(cv, int) or cv not in _MANIFEST_CONTRACT_VERSIONS:
        raise ValueError(
            f"contract_version must be integer in {_MANIFEST_CONTRACT_VERSIONS}, got "
            f"{type(cv).__name__ if cv is not None else 'missing'} ({cv!r})"
        )

    # Validate universe_id
    uid = raw.get("universe_id")
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError("universe_id must be a non-empty string")
    uid = uid.strip()
    if not _UNIVERSE_ID_PATTERN.match(uid):
        raise ValueError(
            f"universe_id {uid!r} is syntactically invalid; "
            "must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
        )

    # Validate universe_version
    uver = raw.get("universe_version")
    if not isinstance(uver, str) or not uver.strip():
        raise ValueError("universe_version must be a non-empty string")
    uver = uver.strip()

    # Validate effective_from
    eff_raw = raw.get("effective_from")
    if not isinstance(eff_raw, str) or not eff_raw.strip():
        raise ValueError("effective_from must be a non-empty ISO date string (YYYY-MM-DD)")
    try:
        effective_from = date.fromisoformat(eff_raw.strip())
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"effective_from {eff_raw!r} is not a valid ISO date (YYYY-MM-DD)"
        ) from exc

    # Validate symbols
    syms_raw = raw.get("symbols")
    if syms_raw is None:
        raise ValueError("symbols field is required")
    if not isinstance(syms_raw, list):
        raise ValueError(f"symbols must be a JSON array, got {type(syms_raw).__name__}")  # noqa: TRY004

    try:
        normalized = normalize_symbols(syms_raw)
    except TypeError as exc:
        raise TypeError(f"Invalid symbol in manifest: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"Invalid symbols in manifest: {exc}") from exc

    # Validate applicability for v2 manifests
    applicability: Mapping[str, Mapping[str, str]] | None = None
    if cv == 2:
        if "applicability" not in raw:
            raise ValueError("applicability field is required for contract_version=2")
        app_raw = raw["applicability"]
        if not isinstance(app_raw, dict):
            raise TypeError(f"applicability must be a JSON object, got {type(app_raw).__name__}")
        applicability = app_raw
    elif "applicability" in raw and raw["applicability"] is not None:
        if not isinstance(raw["applicability"], dict):
            raise TypeError(f"applicability must be a JSON object, got {type(raw['applicability']).__name__}")
        applicability = raw["applicability"]

    # Optional description
    desc_raw = raw.get("description", "")
    if not isinstance(desc_raw, str):
        raise TypeError("description must be a string if provided")
    description = desc_raw

    return PITUniverseManifest(
        contract_version=cv,
        universe_id=uid,
        universe_version=uver,
        effective_from=effective_from,
        symbols=normalized,
        description=description,
        applicability=applicability,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Capacity Estimation (no network, no DB)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PITCapacityEstimate:
    """Deterministic pacing-floor capacity estimate for one universe.

    These are ESTIMATES only:
    - They represent pacing-floor minimums, not guaranteed completion times.
    - Actual provider/network latency is excluded.
    - Retries are excluded.
    """

    universe_id: str
    universe_version: str
    symbol_count: int
    minimum_reference_requests: int   # N  (one active request per symbol)
    maximum_reference_requests: int   # 2N (active + inactive fallback per symbol)
    pacing_interval_seconds: float
    minimum_pacing_floor_seconds: float   # max(N - 1, 0) * interval
    maximum_pacing_floor_seconds: float   # max(2N - 1, 0) * interval


def estimate_capacity(
    manifest: PITUniverseManifest,
    *,
    pacing_interval_seconds: float | None = None,
) -> PITCapacityEstimate:
    """Compute deterministic pacing-floor capacity estimate from a manifest.

    No network calls. No DB writes. No sleeps.

    Args:
        manifest: The validated universe manifest.
        pacing_interval_seconds: Override for the Massive pacing interval.
            Defaults to DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS (currently 12.1 s).

    Returns:
        PITCapacityEstimate with pacing-floor math for N and 2N requests.
    """
    if pacing_interval_seconds is None:
        interval = DEFAULT_MASSIVE_MIN_INTERVAL_SECONDS
    else:
        if isinstance(pacing_interval_seconds, bool):
            raise TypeError("pacing_interval_seconds cannot be a boolean")
        if not isinstance(pacing_interval_seconds, (int, float)):
            raise TypeError(
                f"pacing_interval_seconds must be numeric (int or float), got {type(pacing_interval_seconds).__name__}"
            )
        if not math.isfinite(pacing_interval_seconds):
            raise ValueError(
                f"pacing_interval_seconds must be finite, got {pacing_interval_seconds!r}"
            )
        if pacing_interval_seconds < 0.0:
            raise ValueError(
                f"pacing_interval_seconds must be non-negative, got {pacing_interval_seconds!r}"
            )
        interval = float(pacing_interval_seconds)

    n = len(manifest.symbols)
    min_requests = n
    max_requests = 2 * n
    return PITCapacityEstimate(
        universe_id=manifest.universe_id,
        universe_version=manifest.universe_version,
        symbol_count=n,
        minimum_reference_requests=min_requests,
        maximum_reference_requests=max_requests,
        pacing_interval_seconds=interval,
        minimum_pacing_floor_seconds=max(min_requests - 1, 0) * interval,
        maximum_pacing_floor_seconds=max(max_requests - 1, 0) * interval,
    )



# ─────────────────────────────────────────────────────────────────────────────
# Slot Run Result
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Evidence Completeness Functions
# ─────────────────────────────────────────────────────────────────────────────

def compute_family_completeness(
    family: str,
    *,
    requested_n: int,
    known_n: int,
    not_applicable_n: int = 0,
) -> PITFamilyCompleteness:
    """Derive deterministic evidence completeness read model for a capture family."""
    applicable_n = requested_n - not_applicable_n if family == "earnings" else requested_n
    all_na = (applicable_n == 0)

    if all_na:
        ratio = 1.0
        tier = PITEvidenceCompletenessTier.COMPLETE
    else:
        ratio = known_n / applicable_n
        if known_n == applicable_n:
            tier = PITEvidenceCompletenessTier.COMPLETE
        elif known_n > 0:
            tier = PITEvidenceCompletenessTier.PARTIAL
        else:
            tier = PITEvidenceCompletenessTier.SPARSE

    pct = round(ratio * 100.0, 4)
    return PITFamilyCompleteness(
        tier=tier,
        ratio=ratio,
        pct=pct,
        applicable_n=applicable_n,
        known_n=known_n,
        all_not_applicable=all_na,
    )


def aggregate_slot_completeness(
    earnings: PITFamilyCompleteness,
    reference: PITFamilyCompleteness,
) -> PITSlotCompleteness:
    """Aggregate family evidence completeness into a slot-level read model."""
    total_app = earnings.applicable_n + reference.applicable_n
    total_known = earnings.known_n + reference.known_n

    if total_app == 0:
        pooled_ratio = 1.0
    else:
        pooled_ratio = total_known / total_app
    pooled_pct = round(pooled_ratio * 100.0, 4)

    if earnings.tier == PITEvidenceCompletenessTier.COMPLETE and reference.tier == PITEvidenceCompletenessTier.COMPLETE:
        overall_tier = PITEvidenceCompletenessTier.COMPLETE
    elif earnings.tier == PITEvidenceCompletenessTier.SPARSE or reference.tier == PITEvidenceCompletenessTier.SPARSE:
        overall_tier = PITEvidenceCompletenessTier.SPARSE
    else:
        overall_tier = PITEvidenceCompletenessTier.PARTIAL

    return PITSlotCompleteness(
        overall_tier=overall_tier,
        pooled_ratio=pooled_ratio,
        pooled_pct=pooled_pct,
        total_applicable_n=total_app,
        total_known_n=total_known,
    )


class PITOperationalStatus(str, Enum):
    """Operational status of a PIT slot run."""

    NOT_DUE = "not_due"
    SUCCEEDED = "succeeded"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PITFamilyRunResult:
    """Result of one PIT capture family within a slot run."""

    family: str                     # "earnings" or "reference"
    capture_run_id: str | None      # None if a run was never created
    status: CaptureRunStatus | None # None if capture never started
    known_n: int
    unavailable_n: int
    ambiguous_n: int  # reference only; 0 for earnings
    error_n: int
    error_detail: str | None        # sanitized, no credentials
    requested_n: int = 0
    not_applicable_n: int = 0
    completeness: PITFamilyCompleteness | None = None


@dataclass(frozen=True, slots=True)
class PITSlotRunResult:
    """Deterministic result of a full PIT slot run operation."""

    contract_version: int
    capture_date: date
    slot: CaptureSlot
    scheduled_for: datetime
    requested_at: datetime
    universe_id: str
    universe_version: str
    manifest_hash: str
    universe_hash: str
    symbol_count: int
    operational_status: PITOperationalStatus
    earnings: PITFamilyRunResult
    reference: PITFamilyRunResult
    evidence_completeness: PITSlotCompleteness | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Health Read Model
# ─────────────────────────────────────────────────────────────────────────────

class PITSlotHealthStatus(str, Enum):
    """Health status of a PIT slot."""

    NOT_DUE = "not_due"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    MISSING = "missing"
    INCOMPLETE = "incomplete"
    UNIVERSE_CONFLICT = "universe_conflict"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PITFamilyHealth:
    """Health evidence for one PIT capture family."""

    family: str
    expected: bool                          # True if the slot is due for this family
    attempt_count: int                      # Number of run records found
    run_ids: tuple[str, ...]
    statuses: tuple[str, ...]               # CaptureRunStatus values as strings
    universe_hashes: tuple[str, ...]
    latest_requested_at: datetime | None
    latest_completed_at: datetime | None
    snapshot_count: int
    first_request_lag_seconds: float | None # seconds from scheduled_for to first request
    completion_lag_seconds: float | None    # seconds from scheduled_for to first completion
    manifest_hashes: tuple[str, ...] = ()
    completeness: PITFamilyCompleteness | None = None


@dataclass(frozen=True, slots=True)
class PITSlotHealth:
    """Fully read-only health report for a PIT slot."""

    universe_id: str
    universe_version: str
    manifest_hash: str
    universe_hash: str
    capture_date: date
    slot: CaptureSlot
    scheduled_for: datetime
    health_checked_at: datetime
    overall_status: PITSlotHealthStatus
    earnings: PITFamilyHealth
    reference: PITFamilyHealth
    contract_version: int = 1
    failure_reason: str | None = None
    evidence_completeness: PITSlotCompleteness | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Operational Slot Runner
# ─────────────────────────────────────────────────────────────────────────────

def _sanitize_error(exc: Exception) -> str:
    """Return a safe sanitized error string with no credentials."""
    from tradex.pit.massive_reference import sanitize_text
    return sanitize_text(str(exc))


def _family_result_from_capture(
    family: str,
    result: PITCaptureResult | PITReferenceCaptureResult,
    *,
    completeness: PITFamilyCompleteness | None = None,
) -> PITFamilyRunResult:
    """Build a PITFamilyRunResult from a successful capture result."""
    run = result.run
    ambiguous_n = getattr(run, "ambiguous_n", 0)
    not_applicable_n = getattr(run, "not_applicable_n", 0)
    return PITFamilyRunResult(
        family=family,
        capture_run_id=run.capture_run_id,
        status=run.status,
        known_n=run.known_n,
        unavailable_n=run.unavailable_n,
        ambiguous_n=ambiguous_n,
        error_n=run.error_n,
        error_detail=None,
        requested_n=run.requested_n,
        not_applicable_n=not_applicable_n,
        completeness=completeness,
    )


def _family_result_on_exception(
    family: str,
    *,
    capture_date: date,
    slot: CaptureSlot,
    expected_universe_hash: str,
    pre_existing_run_ids: set[str],
    db_path: Path | None,
    settings: TradeXSettings | None,
    requested_n: int = 0,
    contract_version: int = 1,
    manifest: PITUniverseManifest | None = None,
) -> PITFamilyRunResult:
    """Build PITFamilyRunResult truthfully reflecting any durably created run, with safe generic error."""
    safe_error_detail = (
        "Earnings capture failed due to an internal error."
        if family == "earnings"
        else "Reference capture failed due to an internal error."
    )
    if family == "earnings":
        post_runs = list_earnings_capture_runs(capture_date, slot, db_path=db_path, settings=settings)
    else:
        post_runs = list_reference_capture_runs(capture_date, slot, db_path=db_path, settings=settings)

    new_runs = [
        r for r in post_runs
        if r.universe_hash == expected_universe_hash and r.capture_run_id not in pre_existing_run_ids
    ]

    if len(new_runs) == 1:
        durable_run = new_runs[0]
        ambiguous_n = getattr(durable_run, "ambiguous_n", 0)
        not_applicable_n = getattr(durable_run, "not_applicable_n", 0)

        family_comp = None
        if contract_version == 2 and manifest is not None:
            if durable_run.status == CaptureRunStatus.STARTED:
                if family == "earnings":
                    snaps = list_earnings_snapshots(durable_run.capture_run_id, db_path=db_path, settings=settings)
                    known_n = sum(1 for s in snaps if s.observation_status == ObservationStatus.KNOWN)
                    na_n = sum(1 for s in snaps if s.observation_status == ObservationStatus.NOT_APPLICABLE)
                else:
                    snaps = list_reference_snapshots(durable_run.capture_run_id, db_path=db_path, settings=settings)
                    known_n = sum(1 for s in snaps if s.observation_status == ReferenceObservationStatus.KNOWN)
                    na_n = 0
                family_comp = compute_family_completeness(
                    family,
                    requested_n=requested_n or durable_run.requested_n,
                    known_n=known_n,
                    not_applicable_n=na_n,
                )
            else:
                family_comp = compute_family_completeness(
                    family,
                    requested_n=durable_run.requested_n,
                    known_n=durable_run.known_n,
                    not_applicable_n=not_applicable_n,
                )

        return PITFamilyRunResult(
            family=family,
            capture_run_id=durable_run.capture_run_id,
            status=durable_run.status,
            known_n=durable_run.known_n,
            unavailable_n=durable_run.unavailable_n,
            ambiguous_n=ambiguous_n,
            error_n=durable_run.error_n,
            error_detail=safe_error_detail,
            requested_n=durable_run.requested_n,
            not_applicable_n=not_applicable_n,
            completeness=family_comp,
        )

    family_comp = None
    if contract_version == 2 and manifest is not None:
        na_n = (
            sum(1 for sym in manifest.symbols if manifest.applicability.get(sym, {}).get("earnings") == "not_applicable")
            if family == "earnings"
            else 0
        )
        family_comp = compute_family_completeness(
            family,
            requested_n=requested_n or len(manifest.symbols),
            known_n=0,
            not_applicable_n=na_n,
        )

    return PITFamilyRunResult(
        family=family,
        capture_run_id=None,
        status=None,
        known_n=0,
        unavailable_n=0,
        ambiguous_n=0,
        error_n=0,
        error_detail=safe_error_detail,
        requested_n=requested_n,
        not_applicable_n=0,
        completeness=family_comp,
    )


def _not_due_result(
    capture_date: date,
    slot: CaptureSlot,
    scheduled_for: datetime,
    requested_at: datetime,
    manifest: PITUniverseManifest,
) -> PITSlotRunResult:
    """Build a not_due result with zero side effects."""
    e_comp = None
    r_comp = None
    slot_comp = None
    if manifest.contract_version == 2:
        na_n = sum(1 for sym in manifest.symbols if manifest.applicability.get(sym, {}).get("earnings") == "not_applicable")
        e_comp = compute_family_completeness("earnings", requested_n=len(manifest.symbols), known_n=0, not_applicable_n=na_n)
        r_comp = compute_family_completeness("reference", requested_n=len(manifest.symbols), known_n=0, not_applicable_n=0)
        slot_comp = aggregate_slot_completeness(e_comp, r_comp)

    return PITSlotRunResult(
        contract_version=manifest.contract_version,
        capture_date=capture_date,
        slot=slot,
        scheduled_for=scheduled_for,
        requested_at=requested_at,
        universe_id=manifest.universe_id,
        universe_version=manifest.universe_version,
        manifest_hash=manifest.manifest_hash,
        universe_hash=manifest.universe_hash,
        symbol_count=len(manifest.symbols),
        operational_status=PITOperationalStatus.NOT_DUE,
        earnings=PITFamilyRunResult(
            family="earnings", capture_run_id=None, status=None,
            known_n=0, unavailable_n=0, ambiguous_n=0, error_n=0, error_detail=None,
            requested_n=len(manifest.symbols),
            completeness=e_comp,
        ),
        reference=PITFamilyRunResult(
            family="reference", capture_run_id=None, status=None,
            known_n=0, unavailable_n=0, ambiguous_n=0, error_n=0, error_detail=None,
            requested_n=len(manifest.symbols),
            completeness=r_comp,
        ),
        evidence_completeness=slot_comp,
    )


def _failed_result(
    capture_date: date,
    slot: CaptureSlot,
    scheduled_for: datetime,
    requested_at: datetime,
    manifest: PITUniverseManifest,
    error_detail: str,
) -> PITSlotRunResult:
    """Build a failed result with the given error detail."""
    e_comp = None
    r_comp = None
    slot_comp = None
    if manifest.contract_version == 2:
        na_n = sum(1 for sym in manifest.symbols if manifest.applicability.get(sym, {}).get("earnings") == "not_applicable")
        e_comp = compute_family_completeness("earnings", requested_n=len(manifest.symbols), known_n=0, not_applicable_n=na_n)
        r_comp = compute_family_completeness("reference", requested_n=len(manifest.symbols), known_n=0, not_applicable_n=0)
        slot_comp = aggregate_slot_completeness(e_comp, r_comp)

    return PITSlotRunResult(
        contract_version=manifest.contract_version,
        capture_date=capture_date,
        slot=slot,
        scheduled_for=scheduled_for,
        requested_at=requested_at,
        universe_id=manifest.universe_id,
        universe_version=manifest.universe_version,
        manifest_hash=manifest.manifest_hash,
        universe_hash=manifest.universe_hash,
        symbol_count=len(manifest.symbols),
        operational_status=PITOperationalStatus.FAILED,
        earnings=PITFamilyRunResult(
            family="earnings", capture_run_id=None, status=None,
            known_n=0, unavailable_n=0, ambiguous_n=0, error_n=0,
            error_detail=error_detail,
            requested_n=len(manifest.symbols),
            completeness=e_comp,
        ),
        reference=PITFamilyRunResult(
            family="reference", capture_run_id=None, status=None,
            known_n=0, unavailable_n=0, ambiguous_n=0, error_n=0,
            error_detail=error_detail,
            requested_n=len(manifest.symbols),
            completeness=r_comp,
        ),
        evidence_completeness=slot_comp,
    )


def _compute_operational_status(
    earnings_result: PITFamilyRunResult,
    ref_result: PITFamilyRunResult,
    *,
    contract_version: int = 1,
    had_fatal_error: bool = False,
) -> PITOperationalStatus:
    if contract_version == 1:
        if earnings_result.capture_run_id is None and ref_result.capture_run_id is None:
            return PITOperationalStatus.FAILED
        both_succeeded = (
            earnings_result.status == CaptureRunStatus.SUCCEEDED
            and ref_result.status == CaptureRunStatus.SUCCEEDED
        )
        if both_succeeded:
            return PITOperationalStatus.SUCCEEDED
        return PITOperationalStatus.DEGRADED

    # Contract v2
    if had_fatal_error:
        return PITOperationalStatus.FAILED
    if (
        earnings_result.capture_run_id is None
        or ref_result.capture_run_id is None
        or earnings_result.status == CaptureRunStatus.FAILED
        or ref_result.status == CaptureRunStatus.FAILED
        or earnings_result.error_detail is not None
        or ref_result.error_detail is not None
    ):
        return PITOperationalStatus.FAILED

    if (
        earnings_result.status in (CaptureRunStatus.STARTED, CaptureRunStatus.PARTIAL)
        or ref_result.status in (CaptureRunStatus.STARTED, CaptureRunStatus.PARTIAL)
    ):
        return PITOperationalStatus.DEGRADED

    if (
        earnings_result.status == CaptureRunStatus.SUCCEEDED
        and ref_result.status == CaptureRunStatus.SUCCEEDED
    ):
        return PITOperationalStatus.SUCCEEDED

    return PITOperationalStatus.FAILED


def _check_universe_drift(
    capture_date: date,
    slot: CaptureSlot,
    expected_universe_hash: str,
    *,
    expected_contract_version: int = 1,
    expected_manifest_hash: str | None = None,
    db_path: Path | None,
    settings: TradeXSettings | None,
) -> None:
    """Inspect existing runs for universe hash and manifest drift.

    Raises PITOperationalUniverseConflictError if any existing run for this
    date/slot has a materially different universe hash.
    Raises PITOperationalManifestConflictError if existing runs have cross-version conflicts
    or manifest hash conflicts.

    Zero provider calls, zero writes, zero new runs.
    """
    existing_earnings = list_earnings_capture_runs(
        capture_date, slot, db_path=db_path, settings=settings
    )
    for run in existing_earnings:
        if run.contract_version != expected_contract_version:
            raise PITOperationalManifestConflictError(
                f"Cross-version conflict for earnings on {capture_date.isoformat()} {slot.value}: "
                f"existing run {run.capture_run_id!r} has contract_version {run.contract_version}, "
                f"which cannot execute under contract v{expected_contract_version} runtime.",
                existing_hash=getattr(run, "manifest_hash", None),
                new_hash=expected_manifest_hash,
                family="earnings",
            )
        if run.universe_hash != expected_universe_hash:
            raise PITOperationalUniverseConflictError(
                f"Universe conflict for earnings on {capture_date.isoformat()} {slot.value}: "
                f"existing run {run.capture_run_id!r} has universe_hash {run.universe_hash!r} "
                f"but supplied manifest has {expected_universe_hash!r}. "
                "Changing the operational universe for a date/slot requires an explicit "
                "future operational decision.",
                existing_hash=run.universe_hash,
                new_hash=expected_universe_hash,
                family="earnings",
            )
        if expected_contract_version == 2 and getattr(run, "manifest_hash", None) != expected_manifest_hash:
            raise PITOperationalManifestConflictError(
                f"Manifest conflict for earnings on {capture_date.isoformat()} {slot.value}: "
                f"existing run {run.capture_run_id!r} has manifest_hash {getattr(run, 'manifest_hash', None)!r} "
                f"but supplied manifest has {expected_manifest_hash!r}.",
                existing_hash=getattr(run, "manifest_hash", None),
                new_hash=expected_manifest_hash,
                family="earnings",
            )

    existing_ref = list_reference_capture_runs(
        capture_date, slot, db_path=db_path, settings=settings
    )
    for run in existing_ref:
        if run.contract_version != expected_contract_version:
            raise PITOperationalManifestConflictError(
                f"Cross-version conflict for reference on {capture_date.isoformat()} {slot.value}: "
                f"existing run {run.capture_run_id!r} has contract_version {run.contract_version}, "
                f"which cannot execute under contract v{expected_contract_version} runtime.",
                existing_hash=getattr(run, "manifest_hash", None),
                new_hash=expected_manifest_hash,
                family="reference",
            )
        if run.universe_hash != expected_universe_hash:
            raise PITOperationalUniverseConflictError(
                f"Universe conflict for reference on {capture_date.isoformat()} {slot.value}: "
                f"existing run {run.capture_run_id!r} has universe_hash {run.universe_hash!r} "
                f"but supplied manifest has {expected_universe_hash!r}. "
                "Changing the operational universe for a date/slot requires an explicit "
                "future operational decision.",
                existing_hash=run.universe_hash,
                new_hash=expected_universe_hash,
                family="reference",
            )
        if expected_contract_version == 2 and getattr(run, "manifest_hash", None) != expected_manifest_hash:
            raise PITOperationalManifestConflictError(
                f"Manifest conflict for reference on {capture_date.isoformat()} {slot.value}: "
                f"existing run {run.capture_run_id!r} has manifest_hash {getattr(run, 'manifest_hash', None)!r} "
                f"but supplied manifest has {expected_manifest_hash!r}.",
                existing_hash=getattr(run, "manifest_hash", None),
                new_hash=expected_manifest_hash,
                family="reference",
            )


def run_pit_slot(
    *,
    slot: CaptureSlot,
    universe_manifest: PITUniverseManifest,
    settings: TradeXSettings | None = None,
    db_path: Path | None = None,
    now_fn: Callable[[], datetime] | None = None,
    earnings_capture: Callable[..., PITCaptureResult] | None = None,
    reference_capture: Callable[..., PITReferenceCaptureResult] | None = None,
) -> PITSlotRunResult:
    """Run deterministic PIT slot capture for both earnings and reference families.

    Execution rules:
    1. Derive the current ET date from now_fn.
    2. Return not_due if NOT a XNYS trading day (zero writes, zero provider calls).
    3. Return not_due if slot has not yet been reached (zero writes, zero provider calls).
    4. Return failed if manifest effective_from > current ET date.
    5. Return failed if manifest contract_version != 1 (v2 execution activation deferred to PR B).
    6. Universe drift guard: fail closed if existing runs have different hash.
    7. Run earnings capture (family 1).
    8. Run reference capture (family 2) regardless of earnings outcome.
    9. Return deterministic PITSlotRunResult.

    No OS scheduler. No retry loops. No Candidate/Journal writes.
    The same normalized symbol tuple is used for BOTH families (invariant).
    """
    from tradex.config import load_runtime_settings
    from tradex.pit.earnings import capture_earnings_snapshot as _default_earnings_capture
    from tradex.pit.reference import capture_reference_snapshot as _default_reference_capture

    if settings is None:
        settings = load_runtime_settings()
    if now_fn is None:
        now_fn = lambda: datetime.now(UTC)
    if earnings_capture is None:
        earnings_capture = _default_earnings_capture
    if reference_capture is None:
        reference_capture = _default_reference_capture

    current_dt = _get_aware_utc_now(now_fn)
    current_ny_date = current_dt.astimezone(MARKET_TIMEZONE).date()
    scheduled_for = compute_scheduled_slot_time(current_ny_date, slot)

    # Manifest contract_version gate
    if universe_manifest.contract_version not in (1, 2):
        err_msg = (
            f"Manifest contract_version {universe_manifest.contract_version} execution is not supported."
        )
        return _failed_result(current_ny_date, slot, scheduled_for, current_dt, universe_manifest, err_msg)

    # Trading-day gate: zero side effects on non-trading dates
    if not is_trading_day(current_ny_date):
        return _not_due_result(current_ny_date, slot, scheduled_for, current_dt, universe_manifest)

    # Slot time gate: zero side effects before slot
    if current_dt < scheduled_for:
        return _not_due_result(current_ny_date, slot, scheduled_for, current_dt, universe_manifest)

    # Manifest effective_from gate
    if current_ny_date < universe_manifest.effective_from:
        err_msg = (
            f"Manifest effective_from {universe_manifest.effective_from.isoformat()} "
            f"is in the future relative to current ET date {current_ny_date.isoformat()}."
        )
        return _failed_result(current_ny_date, slot, scheduled_for, current_dt, universe_manifest, err_msg)

    # Universe drift guard (zero writes, zero provider calls on conflict)
    try:
        _check_universe_drift(
            current_ny_date,
            slot,
            universe_manifest.universe_hash,
            expected_contract_version=universe_manifest.contract_version,
            expected_manifest_hash=universe_manifest.manifest_hash,
            db_path=db_path,
            settings=settings,
        )
    except (PITOperationalUniverseConflictError, PITOperationalManifestConflictError) as exc:
        return _failed_result(
            current_ny_date, slot, scheduled_for, current_dt, universe_manifest,
            _sanitize_error(exc),
        )

    # The same normalized symbol tuple is used for BOTH families (required invariant).
    symbols = universe_manifest.symbols
    had_fatal_error = False

    # ── Earnings capture (family 1) ────────────────────────────────────────
    pre_earnings_runs = list_earnings_capture_runs(
        current_ny_date, slot, db_path=db_path, settings=settings
    )
    pre_earnings_ids = {
        r.capture_run_id for r in pre_earnings_runs if r.universe_hash == universe_manifest.universe_hash
    }

    earnings_result: PITFamilyRunResult
    try:
        if universe_manifest.contract_version == 1:
            e_capture = earnings_capture(
                symbols=symbols,
                slot=slot,
                settings=settings,
                db_path=db_path,
                now_fn=now_fn,
            )
        else:
            e_capture = earnings_capture(
                symbols=symbols,
                slot=slot,
                settings=settings,
                db_path=db_path,
                now_fn=now_fn,
                contract_version=2,
                manifest=universe_manifest,
            )
        e_comp = None
        if universe_manifest.contract_version == 2:
            e_comp = compute_family_completeness(
                "earnings",
                requested_n=e_capture.run.requested_n,
                known_n=e_capture.run.known_n,
                not_applicable_n=getattr(e_capture.run, "not_applicable_n", 0),
            )
        earnings_result = _family_result_from_capture("earnings", e_capture, completeness=e_comp)
    except Exception:  # noqa: BLE001
        # Family failure isolation: controlled exception captured, continue to reference.
        had_fatal_error = True
        earnings_result = _family_result_on_exception(
            "earnings",
            capture_date=current_ny_date,
            slot=slot,
            expected_universe_hash=universe_manifest.universe_hash,
            pre_existing_run_ids=pre_earnings_ids,
            db_path=db_path,
            settings=settings,
            requested_n=len(symbols),
            contract_version=universe_manifest.contract_version,
            manifest=universe_manifest,
        )

    # ── Reference capture (family 2) ──────────────────────────────────────
    # Reference capture is attempted even if earnings failed.
    pre_ref_runs = list_reference_capture_runs(
        current_ny_date, slot, db_path=db_path, settings=settings
    )
    pre_ref_ids = {
        r.capture_run_id for r in pre_ref_runs if r.universe_hash == universe_manifest.universe_hash
    }

    ref_result: PITFamilyRunResult
    try:
        if universe_manifest.contract_version == 1:
            r_capture = reference_capture(
                symbols=symbols,
                slot=slot,
                settings=settings,
                db_path=db_path,
                now_fn=now_fn,
            )
        else:
            r_capture = reference_capture(
                symbols=symbols,
                slot=slot,
                settings=settings,
                db_path=db_path,
                now_fn=now_fn,
                contract_version=2,
                manifest=universe_manifest,
            )
        r_comp = None
        if universe_manifest.contract_version == 2:
            r_comp = compute_family_completeness(
                "reference",
                requested_n=r_capture.run.requested_n,
                known_n=r_capture.run.known_n,
                not_applicable_n=0,
            )
        ref_result = _family_result_from_capture("reference", r_capture, completeness=r_comp)
    except Exception:  # noqa: BLE001
        had_fatal_error = True
        ref_result = _family_result_on_exception(
            "reference",
            capture_date=current_ny_date,
            slot=slot,
            expected_universe_hash=universe_manifest.universe_hash,
            pre_existing_run_ids=pre_ref_ids,
            db_path=db_path,
            settings=settings,
            requested_n=len(symbols),
            contract_version=universe_manifest.contract_version,
            manifest=universe_manifest,
        )

    operational_status = _compute_operational_status(
        earnings_result,
        ref_result,
        contract_version=universe_manifest.contract_version,
        had_fatal_error=had_fatal_error,
    )

    evidence_completeness = None
    if (
        universe_manifest.contract_version == 2
        and earnings_result.completeness is not None
        and ref_result.completeness is not None
    ):
        evidence_completeness = aggregate_slot_completeness(
            earnings_result.completeness,
            ref_result.completeness,
        )

    return PITSlotRunResult(
        contract_version=universe_manifest.contract_version,
        capture_date=current_ny_date,
        slot=slot,
        scheduled_for=scheduled_for,
        requested_at=current_dt,
        universe_id=universe_manifest.universe_id,
        universe_version=universe_manifest.universe_version,
        manifest_hash=universe_manifest.manifest_hash,
        universe_hash=universe_manifest.universe_hash,
        symbol_count=len(universe_manifest.symbols),
        operational_status=operational_status,
        earnings=earnings_result,
        reference=ref_result,
        evidence_completeness=evidence_completeness,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Health Read Model (fully read-only)
# ─────────────────────────────────────────────────────────────────────────────

def _build_family_health(
    family: str,
    runs: tuple,
    expected_hash: str,
    scheduled_for: datetime,
    slot_due: bool,
    *,
    db_path: Path | None,
    settings: TradeXSettings | None,
    manifest_hashes: tuple[str, ...] = (),
    completeness: PITFamilyCompleteness | None = None,
) -> PITFamilyHealth:
    """Build PITFamilyHealth from existing run records (read-only)."""
    run_ids = tuple(r.capture_run_id for r in runs)
    statuses = tuple(r.status.value for r in runs)
    universe_hashes = tuple(r.universe_hash for r in runs)
    latest_requested_at = max((r.requested_at for r in runs), default=None) if runs else None
    completed_times = [r.completed_at for r in runs if r.completed_at is not None]
    latest_completed_at = max(completed_times) if completed_times else None

    # Count snapshots from runs with matching universe hash
    snapshot_count = 0
    for r in runs:
        if r.universe_hash == expected_hash:
            if family == "earnings":
                snaps = list_earnings_snapshots(r.capture_run_id, db_path=db_path, settings=settings)
            else:
                snaps = list_reference_snapshots(r.capture_run_id, db_path=db_path, settings=settings)
            snapshot_count += len(snaps)

    # Lag metrics (from earliest matching run / earliest completion)
    matching_runs = [r for r in runs if r.universe_hash == expected_hash]
    first_request_lag_seconds: float | None = None
    completion_lag_seconds: float | None = None
    if matching_runs:
        earliest_requested = min(r.requested_at for r in matching_runs)
        first_request_lag_seconds = (earliest_requested - scheduled_for).total_seconds()
        completed_times = [r.completed_at for r in matching_runs if r.completed_at is not None]
        if completed_times:
            earliest_completed = min(completed_times)
            completion_lag_seconds = (earliest_completed - scheduled_for).total_seconds()


    return PITFamilyHealth(
        family=family,
        expected=slot_due,
        attempt_count=len(runs),
        run_ids=run_ids,
        statuses=statuses,
        universe_hashes=universe_hashes,
        manifest_hashes=manifest_hashes,
        latest_requested_at=latest_requested_at,
        latest_completed_at=latest_completed_at,
        snapshot_count=snapshot_count,
        first_request_lag_seconds=first_request_lag_seconds,
        completion_lag_seconds=completion_lag_seconds,
        completeness=completeness,
    )


def _derive_slot_health_status(
    slot_due: bool,
    earnings_runs: tuple,
    ref_runs: tuple,
    expected_hash: str,
) -> PITSlotHealthStatus:
    """Derive overall slot health from run evidence."""
    if not slot_due:
        return PITSlotHealthStatus.NOT_DUE

    # Universe conflict check: any run with mismatched universe_hash
    all_runs = list(earnings_runs) + list(ref_runs)
    if any(r.universe_hash != expected_hash for r in all_runs):
        return PITSlotHealthStatus.UNIVERSE_CONFLICT

    # Missing: no runs for one or both families
    if not earnings_runs or not ref_runs:
        return PITSlotHealthStatus.MISSING

    # Incomplete: any run still in started state
    if any(r.status == CaptureRunStatus.STARTED for r in all_runs):
        return PITSlotHealthStatus.INCOMPLETE

    # Find terminal matching runs (matching universe hash and not started)
    e_terminal = [
        r for r in earnings_runs
        if r.universe_hash == expected_hash and r.status != CaptureRunStatus.STARTED
    ]
    r_terminal = [
        r for r in ref_runs
        if r.universe_hash == expected_hash and r.status != CaptureRunStatus.STARTED
    ]

    if not e_terminal or not r_terminal:
        return PITSlotHealthStatus.MISSING

    # Healthy: both have a terminal succeeded run
    e_succeeded = any(r.status == CaptureRunStatus.SUCCEEDED for r in e_terminal)
    r_succeeded = any(r.status == CaptureRunStatus.SUCCEEDED for r in r_terminal)

    if e_succeeded and r_succeeded:
        return PITSlotHealthStatus.HEALTHY

    # Degraded: both have terminal evidence but not both succeeded
    return PITSlotHealthStatus.DEGRADED


def _derive_family_completeness_read_model(
    family: str,
    runs: tuple,
    manifest: PITUniverseManifest,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITFamilyCompleteness:
    """Derive family completeness independently from matching runs."""
    candidate_runs = [
        r for r in runs
        if r.universe_hash == manifest.universe_hash
        and getattr(r, "manifest_hash", None) == manifest.manifest_hash
    ]
    if candidate_runs:
        authoritative_attempt = max(candidate_runs, key=lambda r: (r.requested_at, r.capture_run_id))
        if authoritative_attempt.status in (
            CaptureRunStatus.SUCCEEDED,
            CaptureRunStatus.PARTIAL,
            CaptureRunStatus.FAILED,
        ):
            return compute_family_completeness(
                family,
                requested_n=authoritative_attempt.requested_n,
                known_n=authoritative_attempt.known_n,
                not_applicable_n=getattr(authoritative_attempt, "not_applicable_n", 0),
            )
        if authoritative_attempt.status == CaptureRunStatus.STARTED:
            if family == "earnings":
                from tradex.pit.models import ObservationStatus
                from tradex.pit.store import list_earnings_snapshots

                snaps = list_earnings_snapshots(
                    authoritative_attempt.capture_run_id,
                    db_path=db_path,
                    settings=settings,
                )
                known_n = sum(1 for s in snaps if s.observation_status == ObservationStatus.KNOWN)
                na_n = sum(
                    1
                    for sym in manifest.symbols
                    if (manifest.applicability or {}).get(sym, {}).get("earnings") == "not_applicable"
                )
                return compute_family_completeness(
                    family,
                    requested_n=len(manifest.symbols),
                    known_n=known_n,
                    not_applicable_n=na_n,
                )
            else:
                from tradex.pit.models import ReferenceObservationStatus
                from tradex.pit.store import list_reference_snapshots

                snaps = list_reference_snapshots(
                    authoritative_attempt.capture_run_id,
                    db_path=db_path,
                    settings=settings,
                )
                known_n = sum(1 for s in snaps if s.observation_status == ReferenceObservationStatus.KNOWN)
                return compute_family_completeness(
                    family,
                    requested_n=len(manifest.symbols),
                    known_n=known_n,
                    not_applicable_n=0,
                )

    na_n = (
        sum(1 for sym in manifest.symbols if (manifest.applicability or {}).get(sym, {}).get("earnings") == "not_applicable")
        if family == "earnings"
        else 0
    )
    return compute_family_completeness(
        family,
        requested_n=len(manifest.symbols),
        known_n=0,
        not_applicable_n=na_n,
    )


def get_pit_slot_health(
    *,
    universe_manifest: PITUniverseManifest,
    capture_date: date,
    slot: CaptureSlot,
    now: datetime,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITSlotHealth:
    """Return fully read-only health for a PIT slot.

    This function NEVER:
    - Triggers provider calls.
    - Triggers capture execution.
    - Creates or migrates the database.
    - Retries or backfills.

    It MAY inspect historical dates because health is read-only.

    Args:
        universe_manifest: The validated universe manifest to compare against.
        capture_date: The date to inspect (may be historical for read-only purposes).
        slot: The observation slot to check.
        now: The current time (must be timezone-aware).
        db_path: Optional explicit database path.
        settings: Optional settings; loaded from runtime if None.
    """
    from tradex.config import load_runtime_settings
    if settings is None:
        settings = load_runtime_settings()

    if now.tzinfo is None:
        raise ValueError("now must be a timezone-aware datetime")
    now_utc = now.astimezone(UTC)

    scheduled_for = compute_scheduled_slot_time(capture_date, slot)

    # Determine whether this slot is "due"
    trading_day = is_trading_day(capture_date)
    slot_due = trading_day and now_utc >= scheduled_for

    if universe_manifest.contract_version not in (1, 2):
        raise ValueError(
            f"Manifest contract_version {universe_manifest.contract_version} health evaluation is not supported."
        )

    # Read existing runs (read-only, does not create DB)
    earnings_runs = list_earnings_capture_runs(
        capture_date, slot, db_path=db_path, settings=settings
    )
    ref_runs = list_reference_capture_runs(
        capture_date, slot, db_path=db_path, settings=settings
    )

    all_runs = list(earnings_runs) + list(ref_runs)
    expected_hash = universe_manifest.universe_hash

    if universe_manifest.contract_version == 1:
        if any(r.contract_version != 1 for r in all_runs):
            raise ValueError(
                "Existing contract-v2 run cannot be evaluated under contract v1 health semantics (deferred to PR B)."
            )

        overall_status = _derive_slot_health_status(
            slot_due, earnings_runs, ref_runs, expected_hash
        )

        earnings_health = _build_family_health(
            "earnings", earnings_runs, expected_hash, scheduled_for, slot_due,
            db_path=db_path, settings=settings,
        )
        ref_health = _build_family_health(
            "reference", ref_runs, expected_hash, scheduled_for, slot_due,
            db_path=db_path, settings=settings,
        )

        return PITSlotHealth(
            universe_id=universe_manifest.universe_id,
            universe_version=universe_manifest.universe_version,
            manifest_hash=universe_manifest.manifest_hash,
            universe_hash=expected_hash,
            capture_date=capture_date,
            slot=slot,
            scheduled_for=scheduled_for,
            health_checked_at=now_utc,
            overall_status=overall_status,
            earnings=earnings_health,
            reference=ref_health,
            contract_version=1,
            failure_reason=None,
            evidence_completeness=None,
        )

    # Contract v2 Health Evaluation
    has_cv_conflict = any(r.contract_version != 2 for r in all_runs)
    has_universe_conflict = any(r.universe_hash != expected_hash for r in all_runs)
    has_manifest_conflict = any(
        getattr(r, "manifest_hash", None) != universe_manifest.manifest_hash
        for r in all_runs
    )

    overall_status: PITSlotHealthStatus
    failure_reason: str | None = None

    if has_universe_conflict:
        overall_status = PITSlotHealthStatus.FAILED
        failure_reason = "universe_conflict"
    elif has_cv_conflict or has_manifest_conflict:
        overall_status = PITSlotHealthStatus.FAILED
        failure_reason = "manifest_conflict"
    elif not slot_due:
        overall_status = PITSlotHealthStatus.NOT_DUE
        failure_reason = None
    elif not earnings_runs or not ref_runs:
        overall_status = PITSlotHealthStatus.FAILED
        failure_reason = "missing_due_family"
    elif any(r.status == CaptureRunStatus.STARTED for r in all_runs):
        overall_status = PITSlotHealthStatus.DEGRADED
        failure_reason = "run_in_progress"
    else:
        e_terminal = [r for r in earnings_runs if r.status != CaptureRunStatus.STARTED]
        r_terminal = [r for r in ref_runs if r.status != CaptureRunStatus.STARTED]
        if not e_terminal or not r_terminal:
            overall_status = PITSlotHealthStatus.FAILED
            failure_reason = "missing_due_family"
        else:
            latest_e = max(e_terminal, key=lambda r: (r.requested_at, r.capture_run_id))
            latest_r = max(r_terminal, key=lambda r: (r.requested_at, r.capture_run_id))

            if latest_e.status == CaptureRunStatus.FAILED or latest_r.status == CaptureRunStatus.FAILED:
                overall_status = PITSlotHealthStatus.FAILED
                failure_reason = "capture_failed"
            elif latest_e.status == CaptureRunStatus.PARTIAL or latest_r.status == CaptureRunStatus.PARTIAL:
                overall_status = PITSlotHealthStatus.DEGRADED
                failure_reason = "partial_evidence"
            elif latest_e.status == CaptureRunStatus.SUCCEEDED and latest_r.status == CaptureRunStatus.SUCCEEDED:
                overall_status = PITSlotHealthStatus.HEALTHY
                failure_reason = None
            else:
                overall_status = PITSlotHealthStatus.FAILED
                failure_reason = "capture_failed"

    e_comp = _derive_family_completeness_read_model(
        "earnings", earnings_runs, universe_manifest, db_path=db_path, settings=settings
    )
    r_comp = _derive_family_completeness_read_model(
        "reference", ref_runs, universe_manifest, db_path=db_path, settings=settings
    )
    slot_comp = aggregate_slot_completeness(e_comp, r_comp)

    earnings_health = _build_family_health(
        "earnings", earnings_runs, expected_hash, scheduled_for, slot_due,
        db_path=db_path, settings=settings,
        manifest_hashes=tuple(getattr(r, "manifest_hash", "") for r in earnings_runs if getattr(r, "manifest_hash", None)),
        completeness=e_comp,
    )
    ref_health = _build_family_health(
        "reference", ref_runs, expected_hash, scheduled_for, slot_due,
        db_path=db_path, settings=settings,
        manifest_hashes=tuple(getattr(r, "manifest_hash", "") for r in ref_runs if getattr(r, "manifest_hash", None)),
        completeness=r_comp,
    )

    return PITSlotHealth(
        universe_id=universe_manifest.universe_id,
        universe_version=universe_manifest.universe_version,
        manifest_hash=universe_manifest.manifest_hash,
        universe_hash=expected_hash,
        capture_date=capture_date,
        slot=slot,
        scheduled_for=scheduled_for,
        health_checked_at=now_utc,
        overall_status=overall_status,
        failure_reason=failure_reason,
        earnings=earnings_health,
        reference=ref_health,
        contract_version=2,
        evidence_completeness=slot_comp,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_validate_universe_output(
    manifest: PITUniverseManifest,
    capacity: PITCapacityEstimate,
) -> dict[str, Any]:
    """Build structured validate-universe output."""
    return {
        "contract_version": manifest.contract_version,
        "universe_id": manifest.universe_id,
        "universe_version": manifest.universe_version,
        "effective_from": manifest.effective_from.isoformat(),
        "symbol_count": len(manifest.symbols),
        "manifest_hash": manifest.manifest_hash,
        "universe_hash": manifest.universe_hash,
        "minimum_reference_requests": capacity.minimum_reference_requests,
        "maximum_reference_requests": capacity.maximum_reference_requests,
        "pacing_interval_seconds": capacity.pacing_interval_seconds,
        "minimum_pacing_floor_seconds": capacity.minimum_pacing_floor_seconds,
        "maximum_pacing_floor_seconds": capacity.maximum_pacing_floor_seconds,
        "timing_note": (
            "Pacing floors are estimates only. "
            "Actual completion time excludes provider/network latency, retries, and other delays."
        ),
    }


def _build_run_slot_output(result: PITSlotRunResult) -> dict[str, Any]:
    """Build structured run-slot output."""
    if result.contract_version == 1:
        def _family_dict(f: PITFamilyRunResult) -> dict[str, Any]:
            return {
                "capture_run_id": f.capture_run_id,
                "status": f.status.value if f.status is not None else None,
                "known_n": f.known_n,
                "unavailable_n": f.unavailable_n,
                "ambiguous_n": f.ambiguous_n,
                "error_n": f.error_n,
                "error_detail": f.error_detail,
            }

        return {
            "contract_version": result.contract_version,
            "capture_date": result.capture_date.isoformat(),
            "slot": result.slot.value,
            "scheduled_for": result.scheduled_for.isoformat(),
            "requested_at": result.requested_at.isoformat(),
            "universe_id": result.universe_id,
            "universe_version": result.universe_version,
            "manifest_hash": result.manifest_hash,
            "universe_hash": result.universe_hash,
            "symbol_count": result.symbol_count,
            "operational_status": result.operational_status.value,
            "earnings": _family_dict(result.earnings),
            "reference": _family_dict(result.reference),
        }

    # Contract v2 output
    def _v2_family_dict(f: PITFamilyRunResult) -> dict[str, Any]:
        d: dict[str, Any] = {
            "capture_run_id": f.capture_run_id,
            "status": f.status.value if f.status is not None else None,
            "requested_n": f.requested_n,
            "known_n": f.known_n,
            "unavailable_n": f.unavailable_n,
            "ambiguous_n": f.ambiguous_n,
            "error_n": f.error_n,
            "not_applicable_n": f.not_applicable_n,
            "error_detail": f.error_detail,
        }
        if f.completeness is not None:
            d["completeness"] = {
                "tier": f.completeness.tier.value,
                "ratio": f.completeness.ratio,
                "pct": f.completeness.pct,
                "applicable_n": f.completeness.applicable_n,
                "known_n": f.completeness.known_n,
                "all_not_applicable": f.completeness.all_not_applicable,
            }
        else:
            d["completeness"] = None
        return d

    v2_output: dict[str, Any] = {
        "contract_version": result.contract_version,
        "capture_date": result.capture_date.isoformat(),
        "slot": result.slot.value,
        "scheduled_for": result.scheduled_for.isoformat(),
        "requested_at": result.requested_at.isoformat(),
        "universe_id": result.universe_id,
        "universe_version": result.universe_version,
        "manifest_hash": result.manifest_hash,
        "universe_hash": result.universe_hash,
        "symbol_count": result.symbol_count,
        "operational_status": result.operational_status.value,
        "earnings": _v2_family_dict(result.earnings),
        "reference": _v2_family_dict(result.reference),
    }
    if result.evidence_completeness is not None:
        v2_output["evidence_completeness"] = {
            "overall_tier": result.evidence_completeness.overall_tier.value,
            "pooled_ratio": result.evidence_completeness.pooled_ratio,
            "pooled_pct": result.evidence_completeness.pooled_pct,
            "total_applicable_n": result.evidence_completeness.total_applicable_n,
            "total_known_n": result.evidence_completeness.total_known_n,
        }
    else:
        v2_output["evidence_completeness"] = None
    return v2_output


def _build_health_output(health: PITSlotHealth) -> dict[str, Any]:
    """Build structured health output."""
    if health.contract_version == 1:
        def _fh_dict(fh: PITFamilyHealth) -> dict[str, Any]:
            return {
                "family": fh.family,
                "expected": fh.expected,
                "attempt_count": fh.attempt_count,
                "run_ids": list(fh.run_ids),
                "statuses": list(fh.statuses),
                "universe_hashes": list(fh.universe_hashes),
                "latest_requested_at": (
                    fh.latest_requested_at.isoformat() if fh.latest_requested_at else None
                ),
                "latest_completed_at": (
                    fh.latest_completed_at.isoformat() if fh.latest_completed_at else None
                ),
                "snapshot_count": fh.snapshot_count,
                "first_request_lag_seconds": fh.first_request_lag_seconds,
                "completion_lag_seconds": fh.completion_lag_seconds,
            }

        return {
            "universe_id": health.universe_id,
            "universe_version": health.universe_version,
            "manifest_hash": health.manifest_hash,
            "universe_hash": health.universe_hash,
            "capture_date": health.capture_date.isoformat(),
            "slot": health.slot.value,
            "scheduled_for": health.scheduled_for.isoformat(),
            "health_checked_at": health.health_checked_at.isoformat(),
            "overall_status": health.overall_status.value,
            "earnings": _fh_dict(health.earnings),
            "reference": _fh_dict(health.reference),
        }

    # Contract v2 output
    def _v2_fh_dict(fh: PITFamilyHealth) -> dict[str, Any]:
        d: dict[str, Any] = {
            "family": fh.family,
            "expected": fh.expected,
            "attempt_count": fh.attempt_count,
            "run_ids": list(fh.run_ids),
            "statuses": list(fh.statuses),
            "universe_hashes": list(fh.universe_hashes),
            "manifest_hashes": list(fh.manifest_hashes),
            "latest_requested_at": (
                fh.latest_requested_at.isoformat() if fh.latest_requested_at else None
            ),
            "latest_completed_at": (
                fh.latest_completed_at.isoformat() if fh.latest_completed_at else None
            ),
            "snapshot_count": fh.snapshot_count,
            "first_request_lag_seconds": fh.first_request_lag_seconds,
            "completion_lag_seconds": fh.completion_lag_seconds,
        }
        if fh.completeness is not None:
            d["completeness"] = {
                "tier": fh.completeness.tier.value,
                "ratio": fh.completeness.ratio,
                "pct": fh.completeness.pct,
                "applicable_n": fh.completeness.applicable_n,
                "known_n": fh.completeness.known_n,
                "all_not_applicable": fh.completeness.all_not_applicable,
            }
        else:
            d["completeness"] = None
        return d

    v2_health: dict[str, Any] = {
        "contract_version": 2,
        "universe_id": health.universe_id,
        "universe_version": health.universe_version,
        "manifest_hash": health.manifest_hash,
        "universe_hash": health.universe_hash,
        "capture_date": health.capture_date.isoformat(),
        "slot": health.slot.value,
        "scheduled_for": health.scheduled_for.isoformat(),
        "health_checked_at": health.health_checked_at.isoformat(),
        "overall_status": health.overall_status.value,
        "failure_reason": health.failure_reason,
        "earnings": _v2_fh_dict(health.earnings),
        "reference": _v2_fh_dict(health.reference),
    }
    if health.evidence_completeness is not None:
        v2_health["evidence_completeness"] = {
            "overall_tier": health.evidence_completeness.overall_tier.value,
            "pooled_ratio": health.evidence_completeness.pooled_ratio,
            "pooled_pct": health.evidence_completeness.pooled_pct,
            "total_applicable_n": health.evidence_completeness.total_applicable_n,
            "total_known_n": health.evidence_completeness.total_known_n,
        }
    else:
        v2_health["evidence_completeness"] = None
    return v2_health


def _cmd_validate_universe(args: argparse.Namespace) -> int:
    """Subcommand: validate-universe — validate manifest and report capacity.

    Exit codes:
        0: valid
        1: invalid
    """
    try:
        manifest = load_universe_manifest(args.universe_file)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        err_dict: dict[str, Any] = {"error": str(exc), "valid": False}
        sys.stdout.write(json.dumps(err_dict, indent=2) + "\n")
        return 1

    capacity = estimate_capacity(manifest)
    output = _build_validate_universe_output(manifest, capacity)
    output["valid"] = True
    sys.stdout.write(json.dumps(output, indent=2) + "\n")
    return 0


def _cmd_run_slot(args: argparse.Namespace) -> int:
    """Subcommand: run-slot — run deterministic PIT slot capture.

    Exit codes:
        0: succeeded or not_due
        2: degraded
        1: operations-level failure
    """
    try:
        manifest = load_universe_manifest(args.universe_file)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        err_dict: dict[str, Any] = {"error": str(exc), "operational_status": "failed"}
        sys.stdout.write(json.dumps(err_dict, indent=2) + "\n")
        return 1

    slot = CaptureSlot(args.slot)
    db_path = Path(args.db_path) if args.db_path else None

    try:
        result = run_pit_slot(
            slot=slot,
            universe_manifest=manifest,
            db_path=db_path,
        )
    except Exception:  # noqa: BLE001

        err_dict = {
            "error": "An unexpected internal error occurred.",
            "operational_status": "failed",
        }
        sys.stdout.write(json.dumps(err_dict, indent=2) + "\n")
        return 1

    output = _build_run_slot_output(result)
    sys.stdout.write(json.dumps(output, indent=2) + "\n")

    status = result.operational_status
    if status in (PITOperationalStatus.NOT_DUE, PITOperationalStatus.SUCCEEDED):
        return 0
    if status == PITOperationalStatus.DEGRADED:
        return 2
    return 1  # FAILED


def _cmd_health(args: argparse.Namespace) -> int:
    """Subcommand: health — read-only slot health inspection.

    Exit codes:
        0: healthy or not_due
        2: degraded / missing / incomplete
        1: universe_conflict / corrupt audit state / validation failure
    """
    try:
        manifest = load_universe_manifest(args.universe_file)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        err_dict: dict[str, Any] = {"error": str(exc)}
        sys.stdout.write(json.dumps(err_dict, indent=2) + "\n")
        return 1

    now = datetime.now(UTC)
    now_et = now.astimezone(MARKET_TIMEZONE)
    today_et = now_et.date()

    target_date: date
    if args.date:
        try:
            target_date = date.fromisoformat(args.date.strip())
        except ValueError:
            sys.stderr.write(f"Error: Invalid --date format {args.date!r}; use YYYY-MM-DD.\n")
            return 1
    else:
        target_date = today_et

    db_path = Path(args.db_path) if args.db_path else None

    if args.slot:
        slots_to_check = [CaptureSlot(args.slot)]
    else:
        slots_to_check = [CaptureSlot.MORNING, CaptureSlot.EVENING]

    has_conflict_or_error = False
    has_degraded_missing_incomplete = False
    results: list[dict[str, Any]] = []
    for slot in slots_to_check:
        try:
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=target_date,
                slot=slot,
                now=now,
                db_path=db_path,
            )
        except Exception:  # noqa: BLE001
            err_dict = {
                "slot": slot.value,
                "error": "An unexpected internal error occurred during health inspection.",
            }
            results.append(err_dict)
            has_conflict_or_error = True
            continue

        output = _build_health_output(health)
        results.append(output)

        s = health.overall_status
        if s in (PITSlotHealthStatus.UNIVERSE_CONFLICT, PITSlotHealthStatus.FAILED):
            has_conflict_or_error = True
        elif s in (
            PITSlotHealthStatus.DEGRADED,
            PITSlotHealthStatus.MISSING,
            PITSlotHealthStatus.INCOMPLETE,
        ):
            has_degraded_missing_incomplete = True

    if len(results) == 1:
        sys.stdout.write(json.dumps(results[0], indent=2) + "\n")
    else:
        sys.stdout.write(json.dumps(results, indent=2) + "\n")

    if has_conflict_or_error:
        return 1
    if has_degraded_missing_incomplete:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for tradex.pit.ops CLI."""
    parser = argparse.ArgumentParser(
        prog="tradex.pit.ops",
        description="PIT operations runner: validate-universe, run-slot, health.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # ── validate-universe ──────────────────────────────────────────────────
    val_parser = subparsers.add_parser(
        "validate-universe",
        help="Validate a universe manifest and report capacity (no network, no DB writes).",
    )
    val_parser.add_argument(
        "--universe-file",
        type=Path,
        required=True,
        help="Path to the universe manifest JSON file.",
    )

    # ── run-slot ───────────────────────────────────────────────────────────
    run_parser = subparsers.add_parser(
        "run-slot",
        help="Run deterministic PIT slot capture for earnings and reference families.",
    )
    run_parser.add_argument(
        "--slot",
        type=str,
        required=True,
        choices=["morning", "evening"],
        help="Observation slot ('morning' = 09:00 ET, 'evening' = 20:30 ET).",
    )
    run_parser.add_argument(
        "--universe-file",
        type=Path,
        required=True,
        help="Path to the universe manifest JSON file.",
    )
    run_parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Optional path to signals.db SQLite database.",
    )

    # ── health ─────────────────────────────────────────────────────────────
    health_parser = subparsers.add_parser(
        "health",
        help="Read-only PIT slot health inspection (no provider calls, no DB writes).",
    )
    health_parser.add_argument(
        "--universe-file",
        type=Path,
        required=True,
        help="Path to the universe manifest JSON file.",
    )
    health_parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Optional ISO date YYYY-MM-DD to inspect (defaults to current ET date).",
    )
    health_parser.add_argument(
        "--slot",
        type=str,
        default=None,
        choices=["morning", "evening"],
        help="Optional slot (defaults to both morning and evening).",
    )
    health_parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Optional path to signals.db SQLite database.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for tradex.pit.ops."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "validate-universe":
        return _cmd_validate_universe(args)
    if args.subcommand == "run-slot":
        return _cmd_run_slot(args)
    if args.subcommand == "health":
        return _cmd_health(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
