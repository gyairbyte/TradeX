"""Manual market preparation service and persistent local cache for ORB scanning.

Implements DAYTRADE-003G:
- Discovers the eligible U.S. stock universe (NYSE/Nasdaq) before market open.
- Retrieves exactly 15 completed XNYS daily sessions through D-1 for Wilder ATR14 and ADV14.
- Applies preliminary ADV14 (>= 1M shares) and ATR14 (> $0.50) technical filters.
- Retrieves exactly the preceding 14 completed XNYS sessions' opening-range volume observations.
- Strictly avoids applying the $5 opening-price filter during preparation (requires session D regular-session open).
- Strictly avoids retrieving or simulating session D 09:30-09:34 ET minute bars during preparation.
- Persists audited preparation artifacts to a versioned local cache outside git with atomic write/replace.
- Validates cache artifacts on session date, provider, feed, lookback calendar, and data integrity.
- Never stores API keys, OAuth tokens, or secrets.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.market.hours import (
    MARKET_TIMEZONE,
    get_market_session,
    is_trading_day,
)

from .indicators import (
    compute_adv14,
    compute_atr14_wilder,
    get_prior_xnys_sessions,
)
from .models import OpeningRangeVolumeObservation
from .preview import (
    RESEARCH_PREVIEW_DISCLAIMER,
    ExclusionCategory,
    SymbolExclusion,
)
from .provider import ORBMarketDataProvider, ORBProviderError

logger = logging.getLogger(__name__)

PREPARATION_SCHEMA_VERSION = "1.0"
DATA_ADJUSTMENT_CONVENTION = "raw_daily_raw_intraday"


class PreparationStatus(str, Enum):
    """Lifecycle and integrity status of a prepared market snapshot."""

    NOT_PREPARED = "NOT_PREPARED"
    PREPARING = "PREPARING"
    READY = "READY"        # Full, complete, authoritative preparation
    PARTIAL = "PARTIAL"    # Completed preparation with partial/provisional coverage
    FAILED = "FAILED"      # Preparation failed or artifact corrupted
    STALE = "STALE"        # Incompatible session date, provider, or feed


class PreparationStage(str, Enum):
    """Stages of manual market preparation execution."""

    INIT = "INIT"
    DISCOVERY = "DISCOVERY"
    DAILY_SCREENING = "DAILY_SCREENING"
    PRIOR_OR_VOLUMES = "PRIOR_OR_VOLUMES"
    PERSISTENCE = "PERSISTENCE"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PreparationProgress:
    """Progress snapshot emitted during market preparation."""

    stage: PreparationStage
    message: str
    discovered_count: int = 0
    evaluated_daily_count: int = 0
    daily_qualified_count: int = 0
    prior_or_volume_count: int = 0
    stage_timings: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PreparedMarketSnapshot:
    """Immutable, versioned artifact containing pre-computed historical market data.

    Stores strictly pre-session-D data:
    - Exactly 15 completed daily bars (D-15..D-1) metrics: ADV14 and Wilder ATR14.
    - Exactly 14 completed prior sessions (D-14..D-1) opening-range volume baselines.
    - Universe identity, exclusions, and coverage metadata.
    Contains NO session D prices, NO session D opening-range bars, and NO secrets.
    """

    schema_version: str
    session_date: date
    provider: str
    feed: str
    is_feed_consolidated: bool
    feed_disclosure: str
    data_adjustment_convention: str
    created_at_utc: str
    created_at_et: str
    completed_at_utc: str
    completed_at_et: str
    status: PreparationStatus
    universe_size_discovered: int
    discovered_universe: list[str]
    historical_daily_sessions: list[date]
    prior_or_volume_sessions: list[date]
    daily_eligible_symbols: list[str]
    daily_metrics: dict[str, tuple[float, float]]  # sym -> (adv14, atr14)
    prior_opening_range_volumes: dict[str, list[OpeningRangeVolumeObservation]]
    exclusions: list[SymbolExclusion]
    coverage_statistics: dict[str, Any]
    integrity_hash: str = ""

    def compute_integrity_hash(self) -> str:
        """Compute deterministic SHA-256 hash over canonical payload representation."""
        payload = self.to_dict(include_hash=False)
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        """Verify that the stored integrity hash matches the current payload content."""
        if not self.integrity_hash:
            return False
        return self.integrity_hash == self.compute_integrity_hash()

    def to_dict(self, include_hash: bool = True) -> dict[str, Any]:
        """Serialize snapshot to a pure JSON-serializable dictionary."""
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "session_date": self.session_date.isoformat(),
            "provider": self.provider,
            "feed": self.feed,
            "is_feed_consolidated": self.is_feed_consolidated,
            "feed_disclosure": self.feed_disclosure,
            "data_adjustment_convention": self.data_adjustment_convention,
            "created_at_utc": self.created_at_utc,
            "created_at_et": self.created_at_et,
            "completed_at_utc": self.completed_at_utc,
            "completed_at_et": self.completed_at_et,
            "status": self.status.value,
            "universe_size_discovered": self.universe_size_discovered,
            "discovered_universe": self.discovered_universe,
            "historical_daily_sessions": [s.isoformat() for s in self.historical_daily_sessions],
            "prior_or_volume_sessions": [s.isoformat() for s in self.prior_or_volume_sessions],
            "daily_eligible_symbols": self.daily_eligible_symbols,
            "daily_metrics": {
                sym: {"adv14": m[0], "atr14": m[1]}
                for sym, m in self.daily_metrics.items()
            },
            "prior_opening_range_volumes": {
                sym: [
                    {
                        "symbol": obs.symbol,
                        "session_date": obs.session_date.isoformat(),
                        "volume": obs.volume,
                    }
                    for obs in obs_list
                ]
                for sym, obs_list in self.prior_opening_range_volumes.items()
            },
            "exclusions": [
                {
                    "symbol": e.symbol,
                    "category": e.category.value if hasattr(e.category, "value") else str(e.category),
                    "reason": e.reason,
                }
                for e in self.exclusions
            ],
            "coverage_statistics": self.coverage_statistics,
        }
        if include_hash:
            d["integrity_hash"] = self.integrity_hash
        return d

    def to_json(self) -> str:
        """Serialize snapshot to indented JSON string."""
        d = self.to_dict(include_hash=True)
        return json.dumps(d, indent=2)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PreparedMarketSnapshot:
        """Deserialize from dictionary, constructing typed domain objects."""
        daily_metrics_raw = d.get("daily_metrics", {})
        daily_metrics = {
            sym: (float(val["adv14"]), float(val["atr14"]))
            for sym, val in daily_metrics_raw.items()
        }

        prior_or_vols_raw = d.get("prior_opening_range_volumes", {})
        prior_or_vols = {
            sym: [
                OpeningRangeVolumeObservation(
                    symbol=obs["symbol"],
                    session_date=date.fromisoformat(obs["session_date"]),
                    volume=float(obs["volume"]),
                )
                for obs in obs_list
            ]
            for sym, obs_list in prior_or_vols_raw.items()
        }

        exclusions_raw = d.get("exclusions", [])
        exclusions = [
            SymbolExclusion(
                symbol=e["symbol"],
                category=ExclusionCategory(e["category"]),
                reason=e["reason"],
            )
            for e in exclusions_raw
        ]

        historical_daily_sessions = [
            date.fromisoformat(s) for s in d.get("historical_daily_sessions", [])
        ]
        prior_or_volume_sessions = [
            date.fromisoformat(s) for s in d.get("prior_or_volume_sessions", [])
        ]

        return cls(
            schema_version=str(d.get("schema_version", PREPARATION_SCHEMA_VERSION)),
            session_date=date.fromisoformat(d["session_date"]),
            provider=str(d.get("provider", "")),
            feed=str(d.get("feed", "")),
            is_feed_consolidated=bool(d.get("is_feed_consolidated", False)),
            feed_disclosure=str(d.get("feed_disclosure", "")),
            data_adjustment_convention=str(
                d.get("data_adjustment_convention", DATA_ADJUSTMENT_CONVENTION)
            ),
            created_at_utc=str(d.get("created_at_utc", "")),
            created_at_et=str(d.get("created_at_et", "")),
            completed_at_utc=str(d.get("completed_at_utc", "")),
            completed_at_et=str(d.get("completed_at_et", "")),
            status=PreparationStatus(d.get("status", PreparationStatus.FAILED.value)),
            universe_size_discovered=int(d.get("universe_size_discovered", 0)),
            discovered_universe=list(d.get("discovered_universe", [])),
            historical_daily_sessions=historical_daily_sessions,
            prior_or_volume_sessions=prior_or_volume_sessions,
            daily_eligible_symbols=list(d.get("daily_eligible_symbols", [])),
            daily_metrics=daily_metrics,
            prior_opening_range_volumes=prior_or_vols,
            exclusions=exclusions,
            coverage_statistics=dict(d.get("coverage_statistics", {})),
            integrity_hash=str(d.get("integrity_hash", "")),
        )

    @classmethod
    def from_json(cls, text: str) -> PreparedMarketSnapshot:
        """Parse JSON string into a PreparedMarketSnapshot."""
        d = json.loads(text)
        return cls.from_dict(d)


@dataclass(frozen=True)
class CacheValidationResult:
    """Result of evaluating a cached preparation artifact."""

    is_valid: bool
    status: PreparationStatus
    reason: str
    snapshot: PreparedMarketSnapshot | None = None
    artifact_path: Path | None = None


@dataclass(frozen=True)
class PreparationResult:
    """Result of a manual market preparation execution."""

    session_date: date
    provider: str
    feed: str
    status: PreparationStatus
    universe_size_discovered: int
    daily_eligible_count: int
    artifact_path: Path | None
    coverage_status: str
    coverage_warning: str
    timings: dict[str, float]
    warnings: list[str]
    snapshot: PreparedMarketSnapshot | None = None
    error_message: str | None = None
    disclaimer: str = RESEARCH_PREVIEW_DISCLAIMER


# ═══════════════════════════════════════════════════════════════════════════════
# Cache Path & Persistence Utilities
# ═══════════════════════════════════════════════════════════════════════════════

def get_default_cache_dir(settings: TradeXSettings | None = None) -> Path:
    """Resolve the base directory for ORB preparation snapshots."""
    if settings is not None:
        return settings.paths.orb_cache_dir.expanduser()
    return load_runtime_settings().paths.orb_cache_dir.expanduser()


def get_snapshot_filename(session_date: date, provider: str, feed: str) -> str:
    """Construct canonical filename for a preparation snapshot."""
    safe_provider = provider.strip().lower()
    safe_feed = feed.strip().lower()
    return f"orb_prep_{session_date.isoformat()}_{safe_provider}_{safe_feed}.json"


def save_prepared_snapshot(
    snapshot: PreparedMarketSnapshot,
    cache_dir: Path | None = None,
) -> Path:
    """Save snapshot to versioned local artifact using atomic write/replace.

    Guarantees:
    - Creates target directory if it does not exist.
    - Writes to a temporary file first, flushes, fsyncs, then atomically renames.
    - A failed write cannot corrupt a previously valid cached snapshot.
    """
    base_dir = cache_dir if cache_dir is not None else get_default_cache_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    filename = get_snapshot_filename(snapshot.session_date, snapshot.provider, snapshot.feed)
    target_path = base_dir / filename
    temp_path = base_dir / f"{filename}.tmp_{uuid.uuid4().hex}"

    # Compute and set integrity hash before serialization
    computed_hash = snapshot.compute_integrity_hash()
    snapshot_with_hash = PreparedMarketSnapshot(
        schema_version=snapshot.schema_version,
        session_date=snapshot.session_date,
        provider=snapshot.provider,
        feed=snapshot.feed,
        is_feed_consolidated=snapshot.is_feed_consolidated,
        feed_disclosure=snapshot.feed_disclosure,
        data_adjustment_convention=snapshot.data_adjustment_convention,
        created_at_utc=snapshot.created_at_utc,
        created_at_et=snapshot.created_at_et,
        completed_at_utc=snapshot.completed_at_utc,
        completed_at_et=snapshot.completed_at_et,
        status=snapshot.status,
        universe_size_discovered=snapshot.universe_size_discovered,
        discovered_universe=snapshot.discovered_universe,
        historical_daily_sessions=snapshot.historical_daily_sessions,
        prior_or_volume_sessions=snapshot.prior_or_volume_sessions,
        daily_eligible_symbols=snapshot.daily_eligible_symbols,
        daily_metrics=snapshot.daily_metrics,
        prior_opening_range_volumes=snapshot.prior_opening_range_volumes,
        exclusions=snapshot.exclusions,
        coverage_statistics=snapshot.coverage_statistics,
        integrity_hash=computed_hash,
    )

    json_str = snapshot_with_hash.to_json()

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(json_str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target_path)
    except Exception:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise

    return target_path


def load_prepared_snapshot(
    session_date: date,
    provider: str,
    feed: str,
    cache_dir: Path | None = None,
) -> PreparedMarketSnapshot | None:
    """Load a prepared snapshot from local storage if present and valid."""
    base_dir = cache_dir if cache_dir is not None else get_default_cache_dir()
    filename = get_snapshot_filename(session_date, provider, feed)
    file_path = base_dir / filename

    if not file_path.exists():
        return None

    try:
        text = file_path.read_text(encoding="utf-8")
        snapshot = PreparedMarketSnapshot.from_json(text)
        if not snapshot.verify_integrity():
            logger.warning(
                "Integrity hash verification failed for preparation snapshot at %s; discarding corrupt cache.",
                file_path,
            )
            return None
        return snapshot
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as err:
        logger.warning(
            "Failed to parse preparation snapshot at %s: %s; discarding corrupt cache.",
            file_path,
            err,
        )
        return None


def validate_prior_or_volume_baseline(
    observations: list[OpeningRangeVolumeObservation],
    expected_sessions: list[date],
    symbol: str,
) -> tuple[bool, SymbolExclusion | None]:
    """Validate that prior opening range volume observations are complete and contiguous.

    Checks:
    - No duplicate session dates (INTEGRITY_BLOCKED).
    - No out-of-window session dates (INTEGRITY_BLOCKED).
    - All expected sessions present with finite, non-negative volume (DATA_UNAVAILABLE).

    Returns:
        (True, None) if complete and valid.
        (False, SymbolExclusion) if duplicate, out-of-window, or missing observations exist.
    """
    expected_set = set(expected_sessions)
    seen_dates: set[date] = set()
    valid_dates: set[date] = set()

    for obs in observations:
        if obs.session_date in seen_dates:
            return False, SymbolExclusion(
                symbol=symbol,
                category=ExclusionCategory.INTEGRITY_BLOCKED,
                reason=f"Conflicting duplicate opening-range volume observations detected for date {obs.session_date.isoformat()}",
            )
        seen_dates.add(obs.session_date)

        if obs.session_date not in expected_set:
            return False, SymbolExclusion(
                symbol=symbol,
                category=ExclusionCategory.INTEGRITY_BLOCKED,
                reason=f"Out-of-window opening-range volume observation detected for date {obs.session_date.isoformat()}",
            )

        if (
            obs.volume is not None
            and isinstance(obs.volume, (int, float))
            and math.isfinite(obs.volume)
            and obs.volume >= 0
        ):
            valid_dates.add(obs.session_date)

    if valid_dates != expected_set:
        return False, SymbolExclusion(
            symbol=symbol,
            category=ExclusionCategory.DATA_UNAVAILABLE,
            reason="RV14 non-computable: missing prior opening-range observations in the 14-session baseline",
        )

    return True, None


def validate_prepared_snapshot(
    snapshot: PreparedMarketSnapshot | None,
    target_session: date,
    provider: str,
    feed: str,
    artifact_path: Path | None = None,
) -> CacheValidationResult:
    """Validate that a prepared snapshot matches the requested scan parameters.

    Checks:
    - Snapshot presence.
    - Session date match.
    - Provider and feed match.
    - Lookback calendar requirements (exact 15 daily and 14 prior OR sessions).
    - Data integrity hash verification.
    - Completion status (READY or PARTIAL).
    - Semantic completeness of metrics and baselines for READY status.
    """
    if snapshot is None:
        return CacheValidationResult(
            is_valid=False,
            status=PreparationStatus.NOT_PREPARED,
            reason="No prepared market snapshot found on disk.",
            artifact_path=artifact_path,
        )

    # 1. Target Session Check
    if snapshot.session_date != target_session:
        return CacheValidationResult(
            is_valid=False,
            status=PreparationStatus.STALE,
            reason=(
                f"Prepared snapshot is for session {snapshot.session_date.isoformat()}, "
                f"which does not match target session {target_session.isoformat()}."
            ),
            snapshot=snapshot,
            artifact_path=artifact_path,
        )

    # 2. Provider and Feed Check
    expected_prov = provider.strip().lower()
    expected_feed = feed.strip().lower()
    actual_prov = snapshot.provider.strip().lower()
    actual_feed = snapshot.feed.strip().lower()

    if actual_prov != expected_prov or actual_feed != expected_feed:
        return CacheValidationResult(
            is_valid=False,
            status=PreparationStatus.STALE,
            reason=(
                f"Prepared snapshot configuration ({snapshot.provider} / {snapshot.feed}) "
                f"does not match selected scanner configuration ({provider} / {feed})."
            ),
            snapshot=snapshot,
            artifact_path=artifact_path,
        )

    # 3. Calendar Lookback Check
    try:
        expected_daily_sessions = get_prior_xnys_sessions(target_session, 15)
        expected_or_sessions = get_prior_xnys_sessions(target_session, 14)
    except ValueError as err:
        return CacheValidationResult(
            is_valid=False,
            status=PreparationStatus.FAILED,
            reason=f"Failed to resolve prior XNYS trading calendar for {target_session.isoformat()}: {err}",
            snapshot=snapshot,
            artifact_path=artifact_path,
        )

    if snapshot.historical_daily_sessions != expected_daily_sessions:
        return CacheValidationResult(
            is_valid=False,
            status=PreparationStatus.STALE,
            reason=(
                f"Historical daily session sequence does not match expected 15 sessions through D-1: "
                f"expected {expected_daily_sessions[0]}..{expected_daily_sessions[-1]}, "
                f"got {snapshot.historical_daily_sessions[0] if snapshot.historical_daily_sessions else 'none'}.."
                f"{snapshot.historical_daily_sessions[-1] if snapshot.historical_daily_sessions else 'none'}."
            ),
            snapshot=snapshot,
            artifact_path=artifact_path,
        )

    if snapshot.prior_or_volume_sessions != expected_or_sessions:
        return CacheValidationResult(
            is_valid=False,
            status=PreparationStatus.STALE,
            reason=(
                f"Prior opening-range volume session sequence does not match expected 14 sessions: "
                f"expected {expected_or_sessions[0]}..{expected_or_sessions[-1]}, "
                f"got {snapshot.prior_or_volume_sessions[0] if snapshot.prior_or_volume_sessions else 'none'}.."
                f"{snapshot.prior_or_volume_sessions[-1] if snapshot.prior_or_volume_sessions else 'none'}."
            ),
            snapshot=snapshot,
            artifact_path=artifact_path,
        )

    # 4. Integrity Hash Verification
    if not snapshot.verify_integrity():
        return CacheValidationResult(
            is_valid=False,
            status=PreparationStatus.FAILED,
            reason="Snapshot integrity verification failed (tampered or corrupted JSON content).",
            snapshot=snapshot,
            artifact_path=artifact_path,
        )

    # 5. Schema Version and Adjustment Convention
    if snapshot.schema_version != PREPARATION_SCHEMA_VERSION:
        return CacheValidationResult(
            is_valid=False,
            status=PreparationStatus.FAILED,
            reason=f"Incompatible schema version: expected {PREPARATION_SCHEMA_VERSION}, got {snapshot.schema_version}.",
            snapshot=snapshot,
            artifact_path=artifact_path,
        )

    if snapshot.data_adjustment_convention != DATA_ADJUSTMENT_CONVENTION:
        return CacheValidationResult(
            is_valid=False,
            status=PreparationStatus.FAILED,
            reason=(
                f"Incompatible adjustment convention: expected {DATA_ADJUSTMENT_CONVENTION}, "
                f"got {snapshot.data_adjustment_convention}."
            ),
            snapshot=snapshot,
            artifact_path=artifact_path,
        )

    # 6. Preparation Status Check
    if snapshot.status not in (PreparationStatus.READY, PreparationStatus.PARTIAL):
        return CacheValidationResult(
            is_valid=False,
            status=snapshot.status,
            reason=f"Snapshot status is {snapshot.status.value}; cannot be used for scan execution.",
            snapshot=snapshot,
            artifact_path=artifact_path,
        )

    # 7. Semantic Validation for READY Status
    if snapshot.status == PreparationStatus.READY:
        excluded_symbols = {e.symbol for e in snapshot.exclusions}
        for sym in snapshot.daily_eligible_symbols:
            metrics = snapshot.daily_metrics.get(sym)
            if not metrics or len(metrics) != 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in metrics):
                return CacheValidationResult(
                    is_valid=False,
                    status=PreparationStatus.FAILED,
                    reason=f"Semantic validation failed: symbol {sym} marked daily-eligible but missing valid ADV14/ATR14 metrics.",
                    snapshot=snapshot,
                    artifact_path=artifact_path,
                )
            if sym not in excluded_symbols:
                or_vols = snapshot.prior_opening_range_volumes.get(sym)
                if or_vols is None or len(or_vols) != len(snapshot.prior_or_volume_sessions):
                    return CacheValidationResult(
                        is_valid=False,
                        status=PreparationStatus.FAILED,
                        reason=(
                            f"Semantic validation failed: symbol {sym} marked daily-eligible without exclusion but has incomplete "
                            f"prior OR volume baseline ({len(or_vols) if or_vols else 0}/{len(snapshot.prior_or_volume_sessions)} sessions)."
                        ),
                        snapshot=snapshot,
                        artifact_path=artifact_path,
                    )

    return CacheValidationResult(
        is_valid=True,
        status=snapshot.status,
        reason=(
            f"Valid prepared snapshot ready for session {target_session.isoformat()} "
            f"({snapshot.status.value}, {len(snapshot.daily_eligible_symbols):,} qualified symbols)."
        ),
        snapshot=snapshot,
        artifact_path=artifact_path,
    )


def inspect_cache_status(
    target_session: date,
    provider: str,
    feed: str,
    cache_dir: Path | None = None,
) -> CacheValidationResult:
    """Inspect and validate local cache status without side effects."""
    base_dir = cache_dir if cache_dir is not None else get_default_cache_dir()
    filename = get_snapshot_filename(target_session, provider, feed)
    file_path = base_dir / filename

    if not file_path.exists():
        # Check if there is an artifact for a previous session in cache_dir
        pattern = f"orb_prep_*_{provider.strip().lower()}_{feed.strip().lower()}.json"
        try:
            prior_files = sorted(base_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
            for prior_p in prior_files:
                if prior_p.name == filename:
                    continue
                try:
                    prior_text = prior_p.read_text(encoding="utf-8")
                    prior_snap = PreparedMarketSnapshot.from_json(prior_text)
                    if prior_snap.session_date != target_session:
                        return CacheValidationResult(
                            is_valid=False,
                            status=PreparationStatus.STALE,
                            reason=(
                                f"Snapshot found for previous session {prior_snap.session_date.isoformat()} "
                                f"is stale for target session {target_session.isoformat()}. "
                                "Click Prepare Market to update data for the active trading session."
                            ),
                            snapshot=prior_snap,
                            artifact_path=prior_p,
                        )
                except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
                    continue
        except OSError:
            pass

        return CacheValidationResult(
            is_valid=False,
            status=PreparationStatus.NOT_PREPARED,
            reason=f"No prepared market snapshot found on disk for session {target_session.isoformat()}.",
            artifact_path=file_path,
        )

    try:
        text = file_path.read_text(encoding="utf-8")
        snapshot = PreparedMarketSnapshot.from_json(text)
        return validate_prepared_snapshot(snapshot, target_session, provider, feed, artifact_path=file_path)
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as err:
        return CacheValidationResult(
            is_valid=False,
            status=PreparationStatus.FAILED,
            reason=f"Cached snapshot file could not be read or is corrupted: {err}",
            artifact_path=file_path,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Preparation Service Execution
# ═══════════════════════════════════════════════════════════════════════════════

def prepare_market(
    provider: ORBMarketDataProvider,
    session_date: date | None = None,
    as_of_time: datetime | None = None,
    progress_callback: Callable[[PreparationProgress], None] | None = None,
    cache_dir: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PreparationResult:
    """Execute manual market preparation before market open.

    1. Resolves target regular XNYS trading session D.
    2. Rejects non-trading days (weekends, holidays) and early closures.
    3. Discovers broad U.S. equities universe.
    4. Retrieves exactly 15 completed daily bars (D-15..D-1) and calculates ADV14 and Wilder ATR14.
    5. Filters ADV14 >= 1M shares and ATR14 > $0.50 (does NOT apply opening price > $5 filter).
    6. Retrieves preceding 14 completed sessions' opening-range volume observations.
    7. Validates all inputs and persists snapshot atomically to local cache.
    """
    timings: dict[str, float] = {}
    warnings: list[str] = []

    # Adopt provider defaults if present (e.g. Mock populated fixture)
    provider_default_as_of = getattr(provider, "default_as_of_time", None)
    if as_of_time is None and provider_default_as_of is not None:
        as_of_time = provider_default_as_of
    provider_default_session = getattr(provider, "default_session_date", None)
    if session_date is None and provider_default_session is not None:
        session_date = provider_default_session

    now_et = datetime.now(MARKET_TIMEZONE)
    if as_of_time is None:
        eval_as_of = now_et
    else:
        eval_as_of = as_of_time.astimezone(MARKET_TIMEZONE)

    if session_date is None:
        eval_date = eval_as_of.date()
    else:
        eval_date = session_date

    def _notify(stage: PreparationStage, msg: str, **kwargs: Any) -> None:
        if progress_callback:
            progress_callback(
                PreparationProgress(
                    stage=stage,
                    message=msg,
                    stage_timings=timings,
                    **kwargs,
                )
            )

    _notify(PreparationStage.INIT, f"Initializing market preparation for session {eval_date.isoformat()}...")

    # Calendar & Session Validation: non-trading day and early closure handling
    if not is_trading_day(eval_date):
        err_msg = (
            f"Cannot prepare market: target date {eval_date.isoformat()} is a weekend or holiday "
            "(not an active XNYS regular trading session)."
        )
        return PreparationResult(
            session_date=eval_date,
            provider=provider.provider_name,
            feed=provider.feed_name,
            status=PreparationStatus.FAILED,
            universe_size_discovered=0,
            daily_eligible_count=0,
            artifact_path=None,
            coverage_status="failed",
            coverage_warning=err_msg,
            timings={},
            warnings=[err_msg],
            error_message=err_msg,
        )

    market_session_info = get_market_session(eval_date)
    if market_session_info is not None and market_session_info.is_early_close:
        err_msg = (
            f"Cannot prepare market: target session {eval_date.isoformat()} is an exchange early-close session "
            "(closes before 16:00 ET). Early-close sessions are deterministically excluded from DAYTRADE-003 evaluation."
        )
        return PreparationResult(
            session_date=eval_date,
            provider=provider.provider_name,
            feed=provider.feed_name,
            status=PreparationStatus.FAILED,
            universe_size_discovered=0,
            daily_eligible_count=0,
            artifact_path=None,
            coverage_status="failed",
            coverage_warning=err_msg,
            timings={},
            warnings=[err_msg],
            error_message=err_msg,
        )

    try:
        prior_15_daily_sessions = get_prior_xnys_sessions(eval_date, 15)
        d_start = prior_15_daily_sessions[0]
        d_end = prior_15_daily_sessions[-1]  # D-1
        prior_14_sessions = get_prior_xnys_sessions(eval_date, 14)
    except ValueError as err:
        err_msg = f"Failed to resolve prior XNYS trading sessions for {eval_date.isoformat()}: {err}"
        return PreparationResult(
            session_date=eval_date,
            provider=provider.provider_name,
            feed=provider.feed_name,
            status=PreparationStatus.FAILED,
            universe_size_discovered=0,
            daily_eligible_count=0,
            artifact_path=None,
            coverage_status="failed",
            coverage_warning=err_msg,
            timings={},
            warnings=[err_msg],
            error_message=err_msg,
        )

    # -------------------------------------------------------------------------
    # STAGE 1: Broad Universe Discovery
    # -------------------------------------------------------------------------
    t0 = time.time()
    _notify(PreparationStage.DISCOVERY, "Stage 1: Discovering active NYSE and Nasdaq equities...")
    try:
        discovered_universe = provider.discover_universe()
        timings["discovery"] = round(time.time() - t0, 3)
    except (ORBProviderError, RuntimeError, OSError) as err:
        err_msg = f"Universe discovery failed at Stage 1: {err}"
        return PreparationResult(
            session_date=eval_date,
            provider=provider.provider_name,
            feed=provider.feed_name,
            status=PreparationStatus.FAILED,
            universe_size_discovered=0,
            daily_eligible_count=0,
            artifact_path=None,
            coverage_status="failed",
            coverage_warning=err_msg,
            timings=timings,
            warnings=[err_msg],
            error_message=err_msg,
        )

    universe_size = len(discovered_universe)
    _notify(
        PreparationStage.DISCOVERY,
        f"Stage 1 Complete: Discovered {universe_size:,} active U.S. equities.",
        discovered_count=universe_size,
    )

    if universe_size == 0:
        err_msg = "Discovered universe was empty."
        return PreparationResult(
            session_date=eval_date,
            provider=provider.provider_name,
            feed=provider.feed_name,
            status=PreparationStatus.FAILED,
            universe_size_discovered=0,
            daily_eligible_count=0,
            artifact_path=None,
            coverage_status="empty",
            coverage_warning=err_msg,
            timings=timings,
            warnings=[err_msg],
            error_message=err_msg,
        )

    # -------------------------------------------------------------------------
    # STAGE 2: Daily History & Liquidity Screening (ADV14 >= 1M, ATR14 > $0.50)
    # -------------------------------------------------------------------------
    t1 = time.time()
    _notify(
        PreparationStage.DAILY_SCREENING,
        f"Stage 2: Evaluating daily history ({d_start.isoformat()} to {d_end.isoformat()}) across {universe_size:,} securities...",
        discovered_count=universe_size,
    )

    try:
        daily_bars_by_sym = provider.fetch_daily_bars(discovered_universe, d_start, d_end)
    except (ORBProviderError, RuntimeError, OSError) as err:
        err_msg = f"Daily history fetch failed: {err}"
        return PreparationResult(
            session_date=eval_date,
            provider=provider.provider_name,
            feed=provider.feed_name,
            status=PreparationStatus.FAILED,
            universe_size_discovered=universe_size,
            daily_eligible_count=0,
            artifact_path=None,
            coverage_status="failed",
            coverage_warning=err_msg,
            timings=timings,
            warnings=[err_msg],
            error_message=err_msg,
        )

    exclusions: list[SymbolExclusion] = []
    daily_qualified_symbols: list[str] = []
    daily_metrics_by_sym: dict[str, tuple[float, float]] = {}
    daily_history_complete_count = 0

    for sym in sorted(discovered_universe):
        bars = daily_bars_by_sym.get(sym, [])

        # Check duplicate daily bar dates
        seen_dates: set[date] = set()
        has_dup_date = False
        for b in bars:
            if b.session_date in seen_dates:
                exclusions.append(
                    SymbolExclusion(
                        symbol=sym,
                        category=ExclusionCategory.INTEGRITY_BLOCKED,
                        reason=f"Conflicting duplicate daily bars detected for date {b.session_date.isoformat()}",
                    )
                )
                has_dup_date = True
                break
            seen_dates.add(b.session_date)
        if has_dup_date:
            continue

        # Check ADV14 lookback availability
        adv14 = compute_adv14(bars, eval_date, 14)
        if adv14 is None:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.DATA_UNAVAILABLE,
                    reason="ADV14 non-computable: missing or non-contiguous prior 14 completed XNYS daily sessions",
                )
            )
            continue

        # Check ATR14 lookback availability
        atr14 = compute_atr14_wilder(bars, eval_date, 14)
        if atr14 is None:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.DATA_UNAVAILABLE,
                    reason="ATR14 non-computable: requires 15 contiguous completed XNYS daily sessions through D-1",
                )
            )
            continue

        daily_history_complete_count += 1

        # Preliminary Technical Filters:
        # NOTE: $5.00 opening-price filter is NOT applied here; it applies to session D regular-session open.
        if adv14 < 1_000_000.0:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.TECHNICAL_FILTER,
                    reason=f"ADV14 {adv14:,.0f} shares < 1,000,000 minimum threshold",
                )
            )
            continue

        if atr14 <= 0.50:
            exclusions.append(
                SymbolExclusion(
                    symbol=sym,
                    category=ExclusionCategory.TECHNICAL_FILTER,
                    reason=f"ATR14 ${atr14:.2f} <= $0.50 minimum threshold",
                )
            )
            continue

        daily_qualified_symbols.append(sym)
        daily_metrics_by_sym[sym] = (adv14, atr14)

    timings["daily_screening"] = round(time.time() - t1, 3)
    daily_qual_count = len(daily_qualified_symbols)

    _notify(
        PreparationStage.DAILY_SCREENING,
        f"Stage 2 Complete: {daily_qual_count:,} securities passed daily liquidity screening (ADV >= 1M, ATR > $0.50).",
        discovered_count=universe_size,
        evaluated_daily_count=daily_history_complete_count,
        daily_qualified_count=daily_qual_count,
    )

    # -------------------------------------------------------------------------
    # STAGE 3: Prior 14-Session Opening Range Volume Baseline Retrieval
    # -------------------------------------------------------------------------
    t2 = time.time()
    prior_or_vols_by_sym: dict[str, list[OpeningRangeVolumeObservation]] = {}
    rv_baseline_complete_count = 0

    if daily_qual_count > 0:
        _notify(
            PreparationStage.PRIOR_OR_VOLUMES,
            f"Stage 3: Retrieving 14-session opening-range volume baseline for {daily_qual_count:,} candidates...",
            discovered_count=universe_size,
            evaluated_daily_count=daily_history_complete_count,
            daily_qualified_count=daily_qual_count,
        )

        try:
            prior_or_vols_by_sym = provider.fetch_prior_opening_range_volumes(
                daily_qualified_symbols, prior_14_sessions
            )
        except (ORBProviderError, RuntimeError, OSError) as err:
            err_msg = f"Prior opening-range volume baseline fetch failed: {err}"
            return PreparationResult(
                session_date=eval_date,
                provider=provider.provider_name,
                feed=provider.feed_name,
                status=PreparationStatus.FAILED,
                universe_size_discovered=universe_size,
                daily_eligible_count=daily_qual_count,
                artifact_path=None,
                coverage_status="failed",
                coverage_warning=err_msg,
                timings=timings,
                warnings=[err_msg],
                error_message=err_msg,
            )

        # Validate prior opening range volume completeness for each candidate
        for sym in daily_qualified_symbols:
            obs_list = prior_or_vols_by_sym.get(sym, [])
            is_valid, exc = validate_prior_or_volume_baseline(obs_list, prior_14_sessions, sym)
            if not is_valid:
                if exc is not None:
                    exclusions.append(exc)
            else:
                rv_baseline_complete_count += 1

    timings["prior_or_volumes"] = round(time.time() - t2, 3)

    _notify(
        PreparationStage.PRIOR_OR_VOLUMES,
        f"Stage 3 Complete: Retrieved prior OR volume baselines ({rv_baseline_complete_count:,} complete 14-day baselines).",
        discovered_count=universe_size,
        evaluated_daily_count=daily_history_complete_count,
        daily_qualified_count=daily_qual_count,
        prior_or_volume_count=rv_baseline_complete_count,
    )

    # -------------------------------------------------------------------------
    # STAGE 4: Coverage Assessment and Preparation Status
    # -------------------------------------------------------------------------
    missing_data_count = sum(
        1 for e in exclusions if e.category in (ExclusionCategory.DATA_UNAVAILABLE, ExclusionCategory.INTEGRITY_BLOCKED)
    )
    securities_evaluated = universe_size - missing_data_count
    completeness_pct = round((securities_evaluated / universe_size) * 100.0, 1) if universe_size > 0 else 0.0

    is_synthetic = (
        provider.provider_name.strip().lower() in ("mock", "synthetic")
        or provider.feed_name.strip().lower() in ("mock", "synthetic")
    )

    if is_synthetic:
        coverage_status = "synthetic_demo"
        cov_warn = (
            f"HISTORICAL SYNTHETIC DEMO: Prepared {securities_evaluated:,} of {universe_size:,} simulated securities "
            f"({completeness_pct:.1f}% fixture coverage) using synthetic research snapshot fixture."
        )
        prep_status = PreparationStatus.READY
    elif not provider.is_feed_consolidated:
        coverage_status = "provisional_iex"
        cov_warn = (
            f"PROVISIONAL PREPARATION (IEX FEED ONLY): Prepared {securities_evaluated:,} of {universe_size:,} securities "
            f"({completeness_pct:.1f}% data completeness) using Alpaca free-tier IEX feed (~2% of market volume)."
        )
        prep_status = PreparationStatus.PARTIAL
    elif missing_data_count > 0 or securities_evaluated < universe_size:
        coverage_status = "provisional_incomplete"
        cov_warn = (
            f"PARTIAL PREPARATION: Prepared {securities_evaluated:,} of {universe_size:,} discovered securities "
            f"({completeness_pct:.1f}% data completeness). {missing_data_count:,} securities were excluded due to missing "
            "or incomplete provider data."
        )
        prep_status = PreparationStatus.PARTIAL
    else:
        coverage_status = "full_market_sip"
        cov_warn = (
            f"FULL AUTHORITATIVE PREPARATION: Prepared all {securities_evaluated:,} of {universe_size:,} discovered securities "
            f"(100.0% verified coverage) using consolidated SIP market data."
        )
        prep_status = PreparationStatus.READY

    coverage_stats = {
        "universe_size_discovered": universe_size,
        "securities_evaluated": securities_evaluated,
        "daily_history_complete_count": daily_history_complete_count,
        "daily_eligible_count": daily_qual_count,
        "rv_baseline_complete_count": rv_baseline_complete_count,
        "missing_data_count": missing_data_count,
        "completeness_pct": completeness_pct,
        "coverage_status": coverage_status,
        "coverage_warning": cov_warn,
    }

    # -------------------------------------------------------------------------
    # STAGE 5: Persistence to Local Cache
    # -------------------------------------------------------------------------
    t3 = time.time()
    _notify(PreparationStage.PERSISTENCE, "Stage 5: Persisting preparation artifact to local cache...")

    completed_at = datetime.now(MARKET_TIMEZONE)
    created_at_utc = eval_as_of.astimezone(UTC).isoformat()
    created_at_et = eval_as_of.isoformat()
    completed_at_utc = completed_at.astimezone(UTC).isoformat()
    completed_at_et = completed_at.isoformat()

    snapshot = PreparedMarketSnapshot(
        schema_version=PREPARATION_SCHEMA_VERSION,
        session_date=eval_date,
        provider=provider.provider_name,
        feed=provider.feed_name,
        is_feed_consolidated=provider.is_feed_consolidated,
        feed_disclosure=provider.feed_disclosure,
        data_adjustment_convention=DATA_ADJUSTMENT_CONVENTION,
        created_at_utc=created_at_utc,
        created_at_et=created_at_et,
        completed_at_utc=completed_at_utc,
        completed_at_et=completed_at_et,
        status=prep_status,
        universe_size_discovered=universe_size,
        discovered_universe=sorted(discovered_universe),
        historical_daily_sessions=prior_15_daily_sessions,
        prior_or_volume_sessions=prior_14_sessions,
        daily_eligible_symbols=sorted(daily_qualified_symbols),
        daily_metrics=daily_metrics_by_sym,
        prior_opening_range_volumes=prior_or_vols_by_sym,
        exclusions=exclusions,
        coverage_statistics=coverage_stats,
    )

    try:
        artifact_path = save_prepared_snapshot(snapshot, cache_dir=cache_dir)
        timings["persistence"] = round(time.time() - t3, 3)
    except (OSError, RuntimeError, ValueError, TypeError) as err:
        err_msg = f"Failed to persist preparation artifact: {err}"
        return PreparationResult(
            session_date=eval_date,
            provider=provider.provider_name,
            feed=provider.feed_name,
            status=PreparationStatus.FAILED,
            universe_size_discovered=universe_size,
            daily_eligible_count=daily_qual_count,
            artifact_path=None,
            coverage_status="failed",
            coverage_warning=err_msg,
            timings=timings,
            warnings=[err_msg],
            error_message=err_msg,
        )

    timings["total"] = round(sum(timings.values()), 3)

    _notify(
        PreparationStage.COMPLETE,
        f"Preparation complete in {timings['total']}s: {daily_qual_count:,} historically eligible candidates saved to cache.",
        discovered_count=universe_size,
        evaluated_daily_count=daily_history_complete_count,
        daily_qualified_count=daily_qual_count,
        prior_or_volume_count=rv_baseline_complete_count,
    )

    return PreparationResult(
        session_date=eval_date,
        provider=provider.provider_name,
        feed=provider.feed_name,
        status=prep_status,
        universe_size_discovered=universe_size,
        daily_eligible_count=daily_qual_count,
        artifact_path=artifact_path,
        coverage_status=coverage_status,
        coverage_warning=cov_warn,
        timings=timings,
        warnings=warnings,
        snapshot=snapshot,
    )
