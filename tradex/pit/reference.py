"""Point-in-time prospective security/reference capture orchestration (MVP-ARCH-001-R7-PIT-001B).

Captures prospective reference and security master observations from Massive/Polygon
at canonical decision observation slots (evening 20:30 ET / morning 09:00 ET).
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.market.hours import MARKET_TIMEZONE
from tradex.pit.earnings import (
    _get_aware_utc_now,
    compute_scheduled_slot_time,
)
from tradex.pit.massive_reference import (
    MassiveObservationResult,
    MassiveReferenceClient,
    sanitize_text,
)
from tradex.pit.models import (
    CaptureRunStatus,
    CaptureSlot,
    PITReferenceCaptureResult,
    PITReferenceCaptureRun,
    PITReferenceSnapshot,
    ReferenceObservationStatus,
    build_error_reference_fact_payload,
    compute_fact_hash,
    compute_reference_default_idempotency_key,
    compute_request_fingerprint,
    compute_universe_hash,
    normalize_symbols,
    serialize_canonical_fact_json,
)

if TYPE_CHECKING:
    from tradex.pit.ops import PITUniverseManifest
from tradex.pit.store import (
    PITIdempotencyConflictError,
    create_reference_capture_run,
    finalize_reference_capture_run,
    get_reference_capture_run_by_idempotency_key,
    insert_reference_snapshots,
    list_reference_snapshots,
)

SUPPORTED_REFERENCE_PROVIDERS: tuple[str, ...] = ("massive",)


def _resolve_reference_source(source: str | None, settings: TradeXSettings | None = None) -> str:
    """Resolve and validate the reference provider source."""
    if source is None:
        return "massive"
    cleaned = source.strip().lower()
    if cleaned not in SUPPORTED_REFERENCE_PROVIDERS:
        raise ValueError(
            f"Unsupported reference provider {source!r}. "
            f"Only {list(SUPPORTED_REFERENCE_PROVIDERS)} is authorized for reference PIT capture."
        )
    return cleaned


def capture_reference_snapshot(
    *,
    symbols: Sequence[str],
    slot: CaptureSlot,
    capture_date: date | None = None,
    source: str | None = None,
    idempotency_key: str | None = None,
    settings: TradeXSettings | None = None,
    db_path: Path | None = None,
    now_fn: Callable[[], datetime] | None = None,
    reference_lookup: Callable[[str, date, TradeXSettings | None], MassiveObservationResult] | None = None,
    client: MassiveReferenceClient | None = None,
    contract_version: int = 1,
    manifest: PITUniverseManifest | None = None,
) -> PITReferenceCaptureResult:
    """Orchestrate prospective point-in-time security/reference observation capture.

    Steps:
    1. Resolve runtime settings and validate reference provider source ('massive').
    2. Normalize, deduplicate, and sort symbol universe.
    3. Enforce contract_version and manifest preflight guards.
    4. Validate prospective calendar date (rejecting future/historical) and scheduled slot time.
    5. Compute request fingerprint and derive default idempotency key.
    6. Perform side-effect-free preflight idempotency check against existing DB.
    7. For new capture requests, initialize Schema v8 and persist started capture run.
    8. For each symbol:
       a. Record request start time.
       b. Perform provider lookup with NO DB lock open, catching unexpected exceptions to yield
          truthfully recorded and sanitized per-symbol ERROR observations.
       c. Record response received time and validate clock monotonicity.
       d. Build immutable reference snapshot with correct contract_version.
       e. Immediately persist completed snapshot in SQLite.
    9. Atomically finalize capture run with terminal status and resolved counts.
    10. Return immutable read-model result.
    """
    if settings is None:
        settings = load_runtime_settings()

    if now_fn is None:
        now_fn = lambda: datetime.now(UTC)

    from tradex.tracker.store import _resolve_db_path

    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)

    # 1. Pure input validation and normalization
    resolved_provider = _resolve_reference_source(source, settings=settings)
    normalized_symbols = normalize_symbols(symbols)
    universe_hash = compute_universe_hash(normalized_symbols)

    # 2. Contract version and manifest preflight guards
    if contract_version not in (1, 2):
        raise ValueError(f"Unsupported contract_version {contract_version}; expected 1 or 2")

    if contract_version == 1:
        if manifest is not None:
            raise ValueError("manifest must be None when contract_version=1")
    elif contract_version == 2:
        if manifest is None:
            raise ValueError("manifest is required when contract_version=2")
        if manifest.contract_version != 2:
            raise ValueError(f"manifest.contract_version must be 2, got {manifest.contract_version}")
        if normalized_symbols != manifest.symbols:
            raise ValueError(
                f"symbols mismatch between arguments and manifest: {normalized_symbols} != {manifest.symbols}"
            )

    current_dt = _get_aware_utc_now(now_fn)
    current_ny_dt = current_dt.astimezone(MARKET_TIMEZONE)
    current_ny_date = current_ny_dt.date()

    if capture_date is not None:
        if not isinstance(capture_date, date):
            raise TypeError(f"capture_date must be a date instance, got {type(capture_date)}")
        if capture_date > current_ny_date:
            raise ValueError(
                f"Future capture date {capture_date.isoformat()} is rejected; "
                f"current ET date is {current_ny_date.isoformat()}."
            )
        if capture_date < current_ny_date:
            raise ValueError(
                f"Historical capture date {capture_date.isoformat()} is rejected; "
                f"current ET date is {current_ny_date.isoformat()}."
            )
        target_capture_date = capture_date
    else:
        target_capture_date = current_ny_date

    scheduled_for = compute_scheduled_slot_time(target_capture_date, slot)

    if current_dt < scheduled_for:
        raise ValueError(
            f"Capture requested at {current_dt.isoformat()} is before scheduled slot time "
            f"{scheduled_for.isoformat()} for {slot.value} slot on {target_capture_date.isoformat()}."
        )

    if contract_version == 1:
        manifest_hash_val: str | None = None
        fingerprint = compute_request_fingerprint(
            contract_version=1,
            capture_kind="reference",
            capture_slot=slot.value,
            capture_date=target_capture_date.isoformat(),
            scheduled_for_iso=scheduled_for.isoformat(),
            requested_provider=resolved_provider,
            normalized_symbols=normalized_symbols,
        )
    else:
        assert manifest is not None
        manifest_hash_val = manifest.manifest_hash
        fingerprint = compute_request_fingerprint(
            contract_version=2,
            capture_kind="reference",
            capture_slot=slot.value,
            capture_date=target_capture_date.isoformat(),
            scheduled_for_iso=scheduled_for.isoformat(),
            requested_provider=resolved_provider,
            normalized_symbols=normalized_symbols,
            manifest_hash=manifest_hash_val,
        )

    if idempotency_key is None:
        resolved_idempotency_key = compute_reference_default_idempotency_key(
            target_capture_date.isoformat(),
            slot,
            fingerprint,
        )
    else:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must be a non-empty string when provided")
        resolved_idempotency_key = idempotency_key.strip()

    # Preflight check for existing run with this idempotency key (zero writes/mutations).
    if target_path.exists():
        existing_run = get_reference_capture_run_by_idempotency_key(
            resolved_idempotency_key,
            db_path=target_path,
            settings=settings,
        )
        if existing_run is not None:
            if existing_run.request_fingerprint == fingerprint:
                # Exact replay: return existing run and persisted snapshots without calling provider.
                existing_snapshots = list_reference_snapshots(
                    existing_run.capture_run_id,
                    db_path=target_path,
                    settings=settings,
                )
                return PITReferenceCaptureResult(run=existing_run, snapshots=existing_snapshots)
            # Divergent replay: raise domain conflict without provider calls or DB writes.
            raise PITIdempotencyConflictError(
                f"Idempotency key {resolved_idempotency_key!r} already exists with divergent "
                f"request fingerprint {existing_run.request_fingerprint!r} != {fingerprint!r}"
            )

    # Valid new capture execution: ensure schema is initialized.
    from tradex.tracker import store
    store.init(db_path=target_path, settings=settings)

    run_id = uuid.uuid4().hex
    started_run = PITReferenceCaptureRun(
        capture_run_id=run_id,
        idempotency_key=resolved_idempotency_key,
        request_fingerprint=fingerprint,
        capture_slot=slot,
        capture_date=target_capture_date,
        scheduled_for=scheduled_for,
        requested_at=current_dt,
        completed_at=None,
        requested_provider=resolved_provider,
        universe_hash=universe_hash,
        requested_n=len(normalized_symbols),
        known_n=0,
        unavailable_n=0,
        ambiguous_n=0,
        error_n=0,
        status=CaptureRunStatus.STARTED,
        created_at=current_dt,
        updated_at=current_dt,
        contract_version=contract_version,
        manifest_hash=manifest_hash_val,
    )

    create_reference_capture_run(started_run, db_path=target_path, settings=settings)

    if reference_lookup is None and client is None:
        client = MassiveReferenceClient(settings=settings)

    snapshots: list[PITReferenceSnapshot] = []
    for sym in normalized_symbols:
        req_start = _get_aware_utc_now(now_fn)

        if contract_version == 1:
            if reference_lookup is not None:
                obs_res = reference_lookup(sym, target_capture_date, settings)
            else:
                assert client is not None
                obs_res = client.fetch_ticker_reference(sym, target_capture_date)
        else:
            try:
                if reference_lookup is not None:
                    obs_res = reference_lookup(sym, target_capture_date, settings)
                else:
                    assert client is not None
                    obs_res = client.fetch_ticker_reference(sym, target_capture_date)
            except Exception as exc:  # noqa: BLE001
                error_cat = type(exc).__name__
                clean_msg = sanitize_text(str(exc))
                fact_payload = build_error_reference_fact_payload(
                    ticker=sym,
                    error_category=error_cat,
                    error_message=clean_msg,
                )
                fact_json = serialize_canonical_fact_json(fact_payload)
                fact_hash = compute_fact_hash(fact_json)
                obs_res = MassiveObservationResult(
                    observation_status=ReferenceObservationStatus.ERROR,
                    symbol=sym,
                    query_date=target_capture_date,
                    request_ids=(),
                    provider_ticker=None,
                    provider_name=None,
                    provider_market=None,
                    provider_locale=None,
                    provider_active=None,
                    provider_type_code=None,
                    provider_primary_exchange=None,
                    provider_cik=None,
                    provider_composite_figi=None,
                    provider_share_class_figi=None,
                    provider_last_updated_at=None,
                    provider_delisted_at=None,
                    missing_fields=(),
                    fact_hash=fact_hash,
                    fact_json=fact_json,
                    error_category=error_cat,
                    error_message=clean_msg,
                )

        req_end = _get_aware_utc_now(now_fn)
        if req_end < req_start:
            raise ValueError(
                f"Clock moved backward during reference lookup for {sym}: {req_end.isoformat()} < {req_start.isoformat()}"
            )

        snap_id = uuid.uuid4().hex
        snapshot = PITReferenceSnapshot(
            snapshot_id=snap_id,
            capture_run_id=run_id,
            symbol=sym,
            observation_status=obs_res.observation_status,
            provider=resolved_provider,
            provider_query_date=target_capture_date,
            provider_request_ids=obs_res.request_ids,
            provider_ticker=obs_res.provider_ticker,
            provider_name=obs_res.provider_name,
            provider_market=obs_res.provider_market,
            provider_locale=obs_res.provider_locale,
            provider_active=obs_res.provider_active,
            provider_type_code=obs_res.provider_type_code,
            provider_primary_exchange=obs_res.provider_primary_exchange,
            provider_cik=obs_res.provider_cik,
            provider_composite_figi=obs_res.provider_composite_figi,
            provider_share_class_figi=obs_res.provider_share_class_figi,
            provider_last_updated_at=obs_res.provider_last_updated_at,
            provider_delisted_at=obs_res.provider_delisted_at,
            missing_fields=obs_res.missing_fields,
            request_started_at=req_start,
            response_received_at=req_end,
            fact_hash=obs_res.fact_hash,
            fact_json=obs_res.fact_json,
            error_category=obs_res.error_category,
            error_message=obs_res.error_message,
            created_at=req_end,
            contract_version=contract_version,
        )
        # Persist observation immediately upon completion of provider lookup.
        insert_reference_snapshots([snapshot], db_path=target_path, settings=settings)
        snapshots.append(snapshot)

    known_n = sum(1 for s in snapshots if s.observation_status == ReferenceObservationStatus.KNOWN)
    unavailable_n = sum(
        1 for s in snapshots if s.observation_status == ReferenceObservationStatus.UNAVAILABLE
    )
    ambiguous_n = sum(
        1 for s in snapshots if s.observation_status == ReferenceObservationStatus.AMBIGUOUS
    )
    error_n = sum(1 for s in snapshots if s.observation_status == ReferenceObservationStatus.ERROR)
    requested_n = len(snapshots)

    if contract_version == 1:
        if known_n == requested_n:
            terminal_status = CaptureRunStatus.SUCCEEDED
        elif known_n > 0:
            terminal_status = CaptureRunStatus.PARTIAL
        else:
            terminal_status = CaptureRunStatus.FAILED
    else:
        if error_n == 0:
            terminal_status = CaptureRunStatus.SUCCEEDED
        elif 0 < error_n < requested_n:
            terminal_status = CaptureRunStatus.PARTIAL
        else:
            terminal_status = CaptureRunStatus.FAILED

    completed_at = _get_aware_utc_now(now_fn)
    finalized_run = finalize_reference_capture_run(
        run_id,
        status=terminal_status,
        known_n=known_n,
        unavailable_n=unavailable_n,
        ambiguous_n=ambiguous_n,
        error_n=error_n,
        completed_at=completed_at,
        updated_at=completed_at,
        db_path=target_path,
        settings=settings,
    )

    return PITReferenceCaptureResult(run=finalized_run, snapshots=tuple(snapshots))
