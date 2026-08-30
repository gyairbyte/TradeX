"""Point-in-time prospective earnings capture orchestration (MVP-ARCH-001-R7-PIT-001A).

Captures prospective next earnings dates from the configured earnings provider (Yahoo)
at canonical decision observation slots (evening 20:30 ET / morning 09:00 ET) while
strictly bypassing the 24-hour persistent earnings cache.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import ProviderCapabilityError, ProviderDataUnavailableError
from tradex.earnings.calendar import (
    EarningsDataUnavailableError,
    _resolve_earnings_source,
    get_next_earnings,
)
from tradex.market.hours import MARKET_TIMEZONE
from tradex.pit.models import (
    PIT_CAPTURE_CONTRACT_VERSION,
    CaptureKind,
    CaptureRunStatus,
    CaptureSlot,
    ObservationStatus,
    PITCaptureResult,
    PITCaptureRun,
    PITEarningsSnapshot,
    build_known_fact_payload,
    build_unavailable_fact_payload,
    compute_default_idempotency_key,
    compute_fact_hash,
    compute_request_fingerprint,
    compute_universe_hash,
    normalize_symbols,
    serialize_canonical_fact_json,
)
from tradex.pit.store import (
    PITIdempotencyConflictError,
    create_capture_run,
    finalize_capture_run,
    get_capture_run_by_idempotency_key,
    insert_earnings_snapshots,
    list_earnings_snapshots,
)

SLOT_SCHEDULED_TIMES: dict[CaptureSlot, time] = {
    CaptureSlot.EVENING: time(20, 30),  # 8:30 PM America/New_York
    CaptureSlot.MORNING: time(9, 0),   # 9:00 AM America/New_York
}


def compute_scheduled_slot_time(
    slot_date: date,
    slot: CaptureSlot,
    tz: ZoneInfo = MARKET_TIMEZONE,
) -> datetime:
    """Compute the canonical scheduled UTC datetime for a given calendar date and slot."""
    local_time = SLOT_SCHEDULED_TIMES[slot]
    local_dt = datetime.combine(slot_date, local_time, tzinfo=tz)
    return local_dt.astimezone(UTC)


def _default_earnings_lookup(
    symbol: str,
    *,
    source: str,
    settings: TradeXSettings | None = None,
) -> date:
    """Default production lookup performing fresh un-cached provider retrieval."""
    return get_next_earnings(
        symbol,
        force_refresh=True,
        source=source,
        use_cache=False,
        settings=settings,
    )


def capture_earnings_snapshot(
    *,
    symbols: Sequence[str],
    slot: CaptureSlot,
    capture_date: date | None = None,
    source: str | None = None,
    idempotency_key: str | None = None,
    settings: TradeXSettings | None = None,
    db_path: Path | None = None,
    now_fn: Callable[[], datetime] | None = None,
    earnings_lookup: Callable[..., date] | None = None,
) -> PITCaptureResult:
    """Orchestrate prospective point-in-time earnings observation capture.

    Steps:
    1. Resolve settings and provider identity.
    2. Normalize and deduplicate symbol universe.
    3. Determine and validate prospective calendar date and scheduled slot time.
    4. Compute request fingerprint and check idempotency contracts.
    5. Atomically initialize started capture run in SQLite.
    6. Perform fresh provider lookups symbol-by-symbol without cache.
    7. Atomically persist immutable observation snapshots.
    8. Atomically finalize capture run with terminal status and counts.
    9. Return immutable read-model result.
    """
    if settings is None:
        settings = load_runtime_settings()

    if now_fn is None:
        now_fn = lambda: datetime.now(UTC)
    if earnings_lookup is None:
        earnings_lookup = _default_earnings_lookup

    from tradex.tracker import store
    store.init(db_path=db_path, settings=settings)

    resolved_provider = _resolve_earnings_source(source, settings=settings)
    normalized_symbols = normalize_symbols(symbols)
    universe_hash = compute_universe_hash(normalized_symbols)

    current_dt = now_fn()
    if current_dt.tzinfo is None:
        raise ValueError("now_fn returned naive datetime; timezone-aware UTC is required")
    current_dt = current_dt.astimezone(UTC)

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
        capture_kind=CaptureKind.EARNINGS.value,
        capture_slot=slot.value,
        capture_date=target_capture_date.isoformat(),
        scheduled_for_iso=scheduled_for.isoformat(),
        requested_provider=resolved_provider,
        normalized_symbols=normalized_symbols,
    )

    if idempotency_key is None:
        resolved_idempotency_key = compute_default_idempotency_key(
            target_capture_date.isoformat(),
            slot,
            fingerprint,
        )
    else:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must be a non-empty string when provided")
        resolved_idempotency_key = idempotency_key.strip()

    # Check for existing run with this idempotency key.
    existing_run = get_capture_run_by_idempotency_key(
        resolved_idempotency_key,
        db_path=db_path,
        settings=settings,
    )
    if existing_run is not None:
        if existing_run.request_fingerprint == fingerprint:
            # Exact replay: return existing run and snapshots without calling provider.
            existing_snapshots = list_earnings_snapshots(
                existing_run.capture_run_id,
                db_path=db_path,
                settings=settings,
            )
            return PITCaptureResult(run=existing_run, snapshots=existing_snapshots)
        # Divergent replay: raise domain conflict without provider calls or DB writes.
        raise PITIdempotencyConflictError(
            f"Idempotency key {resolved_idempotency_key!r} already exists with divergent "
            f"request fingerprint {existing_run.request_fingerprint!r} != {fingerprint!r}"
        )

    run_id = uuid.uuid4().hex
    started_run = PITCaptureRun(
        capture_run_id=run_id,
        idempotency_key=resolved_idempotency_key,
        request_fingerprint=fingerprint,
        capture_kind=CaptureKind.EARNINGS,
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
        error_n=0,
        status=CaptureRunStatus.STARTED,
        created_at=current_dt,
        updated_at=current_dt,
        contract_version=PIT_CAPTURE_CONTRACT_VERSION,
    )

    create_capture_run(started_run, db_path=db_path, settings=settings)

    snapshots: list[PITEarningsSnapshot] = []
    for sym in normalized_symbols:
        req_start = now_fn().astimezone(UTC)
        obs_status: ObservationStatus
        next_earnings_date: date | None = None
        error_cat: str | None = None
        error_msg: str | None = None

        try:
            nxt = earnings_lookup(sym, source=resolved_provider, settings=settings)
            req_end = now_fn().astimezone(UTC)
            if nxt is not None and isinstance(nxt, date):
                obs_status = ObservationStatus.KNOWN
                next_earnings_date = nxt
                fact_payload = build_known_fact_payload(nxt)
            else:
                obs_status = ObservationStatus.UNAVAILABLE
                error_cat = "EarningsDataUnavailableError"
                error_msg = f"Upcoming earnings date unavailable for {sym}"
                fact_payload = build_unavailable_fact_payload(error_cat, error_msg)
        except (
            ProviderDataUnavailableError,
            ProviderCapabilityError,
            EarningsDataUnavailableError,
        ) as exc:
            req_end = now_fn().astimezone(UTC)
            obs_status = ObservationStatus.UNAVAILABLE
            error_cat = type(exc).__name__
            error_msg = f"Upcoming earnings date unavailable for {sym}"
            fact_payload = build_unavailable_fact_payload(error_cat, error_msg)
        except Exception as exc:  # noqa: BLE001
            req_end = now_fn().astimezone(UTC)
            obs_status = ObservationStatus.ERROR
            error_cat = type(exc).__name__
            error_msg = f"Earnings lookup failed for {sym}"
            fact_payload = build_unavailable_fact_payload(error_cat, error_msg)

        req_end = max(req_end, req_start)

        fact_json = serialize_canonical_fact_json(fact_payload)
        fact_hash = compute_fact_hash(fact_json)
        snap_id = uuid.uuid4().hex

        snapshot = PITEarningsSnapshot(
            snapshot_id=snap_id,
            capture_run_id=run_id,
            symbol=sym,
            observation_status=obs_status,
            next_earnings_date=next_earnings_date,
            provider=resolved_provider,
            provider_observed_at=None,
            request_started_at=req_start,
            response_received_at=req_end,
            fact_hash=fact_hash,
            fact_json=fact_json,
            error_category=error_cat,
            error_message=error_msg,
            created_at=req_end,
            contract_version=PIT_CAPTURE_CONTRACT_VERSION,
        )
        snapshots.append(snapshot)

    insert_earnings_snapshots(snapshots, db_path=db_path, settings=settings)

    known_n = sum(1 for s in snapshots if s.observation_status == ObservationStatus.KNOWN)
    unavailable_n = sum(
        1 for s in snapshots if s.observation_status == ObservationStatus.UNAVAILABLE
    )
    error_n = sum(1 for s in snapshots if s.observation_status == ObservationStatus.ERROR)
    requested_n = len(snapshots)

    if known_n == requested_n:
        terminal_status = CaptureRunStatus.SUCCEEDED
    elif known_n > 0:
        terminal_status = CaptureRunStatus.PARTIAL
    else:
        terminal_status = CaptureRunStatus.FAILED

    completed_at = now_fn().astimezone(UTC)
    finalized_run = finalize_capture_run(
        run_id,
        status=terminal_status,
        known_n=known_n,
        unavailable_n=unavailable_n,
        error_n=error_n,
        completed_at=completed_at,
        updated_at=completed_at,
        db_path=db_path,
        settings=settings,
    )

    return PITCaptureResult(run=finalized_run, snapshots=tuple(snapshots))
