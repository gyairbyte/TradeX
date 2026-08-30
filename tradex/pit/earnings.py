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


_BuiltinDatetime = datetime


def _get_aware_utc_now(now_fn: Callable[[], datetime]) -> datetime:
    """Invoke clock function, reject naive datetimes, and return canonical UTC."""
    dt = now_fn()
    if not isinstance(dt, _BuiltinDatetime):
        raise TypeError(f"Clock function must return a datetime instance, got {type(dt)}")
    if dt.tzinfo is None:
        raise ValueError("now_fn returned naive datetime; timezone-aware UTC is required")
    return dt.astimezone(UTC)


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
    2. Normalize and deduplicate symbol universe (pure validation).
    3. Resolve current UTC/ET time and validate prospective calendar date & scheduled slot time.
    4. Compute request fingerprint and derive canonical idempotency key.
    5. Perform side-effect-free preflight idempotency check against existing DB.
    6. For new capture requests, initialize Schema v6 and persist started capture run.
    7. For each symbol:
       a. Record request start time.
       b. Perform provider lookup with NO DB lock open.
       c. Record response received time and validate clock monotonicity.
       d. Build immutable observation snapshot.
       e. Immediately persist completed snapshot in SQLite.
    8. Atomically finalize capture run with terminal status and counts.
    9. Return immutable read-model result.
    """
    if settings is None:
        settings = load_runtime_settings()

    if now_fn is None:
        now_fn = lambda: datetime.now(UTC)
    if earnings_lookup is None:
        earnings_lookup = _default_earnings_lookup

    from tradex.tracker.store import _resolve_db_path

    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)

    # 1. Pure input validation and normalization
    resolved_provider = _resolve_earnings_source(source, settings=settings)
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

    # Preflight check for existing run with this idempotency key (zero writes/mutations).
    if target_path.exists():
        existing_run = get_capture_run_by_idempotency_key(
            resolved_idempotency_key,
            db_path=target_path,
            settings=settings,
        )
        if existing_run is not None:
            if existing_run.request_fingerprint == fingerprint:
                # Exact replay: return existing run and persisted snapshots without calling provider.
                existing_snapshots = list_earnings_snapshots(
                    existing_run.capture_run_id,
                    db_path=target_path,
                    settings=settings,
                )
                return PITCaptureResult(run=existing_run, snapshots=existing_snapshots)
            # Divergent replay: raise domain conflict without provider calls or DB writes.
            raise PITIdempotencyConflictError(
                f"Idempotency key {resolved_idempotency_key!r} already exists with divergent "
                f"request fingerprint {existing_run.request_fingerprint!r} != {fingerprint!r}"
            )

    # Valid new capture execution: ensure schema is initialized.
    from tradex.tracker import store
    store.init(db_path=target_path, settings=settings)

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

    create_capture_run(started_run, db_path=target_path, settings=settings)

    snapshots: list[PITEarningsSnapshot] = []
    for sym in normalized_symbols:
        req_start = _get_aware_utc_now(now_fn)
        obs_status: ObservationStatus
        next_earnings_date: date | None = None
        error_cat: str | None = None
        error_msg: str | None = None

        try:
            nxt = earnings_lookup(sym, source=resolved_provider, settings=settings)
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
            obs_status = ObservationStatus.UNAVAILABLE
            error_cat = type(exc).__name__
            error_msg = f"Upcoming earnings date unavailable for {sym}"
            fact_payload = build_unavailable_fact_payload(error_cat, error_msg)
        except Exception as exc:  # noqa: BLE001
            obs_status = ObservationStatus.ERROR
            error_cat = type(exc).__name__
            error_msg = f"Earnings lookup failed for {sym}"
            fact_payload = build_unavailable_fact_payload(error_cat, error_msg)

        req_end = _get_aware_utc_now(now_fn)
        if req_end < req_start:
            raise ValueError(
                f"Clock moved backward during lookup for {sym}: {req_end.isoformat()} < {req_start.isoformat()}"
            )

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
        # Persist observation immediately upon completion of provider lookup.
        insert_earnings_snapshots([snapshot], db_path=target_path, settings=settings)
        snapshots.append(snapshot)

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

    completed_at = _get_aware_utc_now(now_fn)
    finalized_run = finalize_capture_run(
        run_id,
        status=terminal_status,
        known_n=known_n,
        unavailable_n=unavailable_n,
        error_n=error_n,
        completed_at=completed_at,
        updated_at=completed_at,
        db_path=target_path,
        settings=settings,
    )

    return PITCaptureResult(run=finalized_run, snapshots=tuple(snapshots))
