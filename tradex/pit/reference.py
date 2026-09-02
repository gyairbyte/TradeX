"""Point-in-time prospective security/reference capture orchestration (MVP-ARCH-001-R7-PIT-001B).

Captures prospective reference and security master observations from Massive/Polygon
at canonical decision observation slots (evening 20:30 ET / morning 09:00 ET).
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.market.hours import MARKET_TIMEZONE
from tradex.pit.earnings import (
    _get_aware_utc_now,
    compute_scheduled_slot_time,
)
from tradex.pit.massive_reference import (
    MassiveObservationResult,
    MassiveReferenceClient,
)
from tradex.pit.models import (
    PIT_CAPTURE_CONTRACT_VERSION,
    CaptureRunStatus,
    CaptureSlot,
    PITReferenceCaptureResult,
    PITReferenceCaptureRun,
    PITReferenceSnapshot,
    ReferenceObservationStatus,
    compute_reference_default_idempotency_key,
    compute_request_fingerprint,
    compute_universe_hash,
    normalize_symbols,
)
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
) -> PITReferenceCaptureResult:
    """Orchestrate prospective point-in-time security/reference observation capture.

    Steps:
    1. Resolve runtime settings and validate reference provider source ('massive').
    2. Normalize, deduplicate, and sort symbol universe.
    3. Validate prospective calendar date (rejecting future/historical) and scheduled slot time.
    4. Compute request fingerprint and derive default idempotency key.
    5. Perform side-effect-free preflight idempotency check against existing DB.
    6. For new capture requests, initialize Schema v7 and persist started capture run.
    7. For each symbol:
       a. Record request start time.
       b. Perform provider lookup with NO DB lock open.
       c. Record response received time and validate clock monotonicity.
       d. Build immutable reference snapshot.
       e. Immediately persist completed snapshot in SQLite.
    8. Atomically finalize capture run with terminal status and resolved counts.
    9. Return immutable read-model result.
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

    fingerprint = compute_request_fingerprint(
        contract_version=PIT_CAPTURE_CONTRACT_VERSION,
        capture_kind="reference",
        capture_slot=slot.value,
        capture_date=target_capture_date.isoformat(),
        scheduled_for_iso=scheduled_for.isoformat(),
        requested_provider=resolved_provider,
        normalized_symbols=normalized_symbols,
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
        contract_version=PIT_CAPTURE_CONTRACT_VERSION,
    )

    create_reference_capture_run(started_run, db_path=target_path, settings=settings)

    if reference_lookup is None and client is None:
        client = MassiveReferenceClient(settings=settings)

    snapshots: list[PITReferenceSnapshot] = []
    for sym in normalized_symbols:
        req_start = _get_aware_utc_now(now_fn)

        if reference_lookup is not None:
            obs_res = reference_lookup(sym, target_capture_date, settings)
        else:
            assert client is not None
            obs_res = client.fetch_ticker_reference(sym, target_capture_date)

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
            contract_version=PIT_CAPTURE_CONTRACT_VERSION,
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

    if known_n == requested_n:
        terminal_status = CaptureRunStatus.SUCCEEDED
    elif known_n > 0:
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
