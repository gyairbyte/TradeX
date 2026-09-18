"""SQLite persistence primitives and row mapping for point-in-time capture (MVP-ARCH-001-R7-PIT-001A).

Implements atomic run creation, immutable snapshot insertion, run finalization,
and neutral audit/read APIs according to Schema v6.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tradex.pit.models import (
    CaptureKind,
    CaptureRunStatus,
    CaptureSlot,
    ObservationStatus,
    PITCaptureResult,
    PITCaptureRun,
    PITEarningsSnapshot,
    PITReferenceCaptureResult,
    PITReferenceCaptureRun,
    PITReferenceSnapshot,
    ReferenceObservationStatus,
    _normalize_aware_utc,
)
from tradex.tracker.store import StoreError, _conn, _resolve_db_path, _transaction

if TYPE_CHECKING:
    from tradex.config import TradeXSettings


class PITStoreError(StoreError):
    """Base persistence exception for point-in-time capture."""


class PITIdempotencyConflictError(PITStoreError):
    """Raised when an existing idempotency key is reused with divergent request parameters."""


def _parse_dt(iso_str: str | None, field_name: str = "timestamp") -> datetime | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str)
    except Exception as exc:
        raise PITStoreError(f"Malformed persisted timestamp for {field_name}: {iso_str!r}") from exc
    if dt.tzinfo is None:
        raise PITStoreError(f"Persisted timestamp for {field_name} is naive; canonical UTC required: {iso_str!r}")
    return dt.astimezone(UTC)


def _row_to_run(row: sqlite3.Row) -> PITCaptureRun:
    try:
        cap_date = date.fromisoformat(row["capture_date"])
    except Exception as exc:
        raise PITStoreError(f"Malformed persisted date for capture_date: {row['capture_date']!r}") from exc

    sched_for = _parse_dt(row["scheduled_for"], "scheduled_for")
    req_at = _parse_dt(row["requested_at"], "requested_at")
    comp_at = _parse_dt(row["completed_at"], "completed_at")
    created_at = _parse_dt(row["created_at"], "created_at")
    updated_at = _parse_dt(row["updated_at"], "updated_at")

    row_keys = set(row.keys())
    manifest_hash = row["manifest_hash"] if "manifest_hash" in row_keys else None
    not_applicable_n = int(row["not_applicable_n"]) if "not_applicable_n" in row_keys else 0

    return PITCaptureRun(
        capture_run_id=row["capture_run_id"],
        idempotency_key=row["idempotency_key"],
        request_fingerprint=row["request_fingerprint"],
        capture_kind=CaptureKind(row["capture_kind"]),
        capture_slot=CaptureSlot(row["capture_slot"]),
        capture_date=cap_date,
        scheduled_for=sched_for,  # type: ignore[arg-type]
        requested_at=req_at,  # type: ignore[arg-type]
        completed_at=comp_at,
        requested_provider=row["requested_provider"],
        universe_hash=row["universe_hash"],
        manifest_hash=manifest_hash,
        requested_n=int(row["requested_n"]),
        known_n=int(row["known_n"]),
        not_applicable_n=not_applicable_n,
        unavailable_n=int(row["unavailable_n"]),
        error_n=int(row["error_n"]),
        status=CaptureRunStatus(row["status"]),
        created_at=created_at,  # type: ignore[arg-type]
        updated_at=updated_at,  # type: ignore[arg-type]
        contract_version=int(row["contract_version"]),
    )


def _row_to_snapshot(row: sqlite3.Row) -> PITEarningsSnapshot:
    if row["next_earnings_date"]:
        try:
            nxt_date = date.fromisoformat(row["next_earnings_date"])
        except Exception as exc:
            raise PITStoreError(f"Malformed persisted date for next_earnings_date: {row['next_earnings_date']!r}") from exc
    else:
        nxt_date = None

    prov_obs_at = _parse_dt(row["provider_observed_at"], "provider_observed_at")
    req_started = _parse_dt(row["request_started_at"], "request_started_at")
    resp_rcvd = _parse_dt(row["response_received_at"], "response_received_at")
    created_at = _parse_dt(row["created_at"], "created_at")

    row_keys = set(row.keys())
    obs_origin = row["observation_origin"] if "observation_origin" in row_keys else "provider"
    app_source = row["applicability_source"] if "applicability_source" in row_keys else None
    prov_call_att = bool(row["provider_call_attempted"]) if "provider_call_attempted" in row_keys else True

    return PITEarningsSnapshot(
        snapshot_id=row["snapshot_id"],
        capture_run_id=row["capture_run_id"],
        symbol=row["symbol"],
        observation_status=ObservationStatus(row["observation_status"]),
        observation_origin=obs_origin,
        applicability_source=app_source,
        provider_call_attempted=prov_call_att,
        next_earnings_date=nxt_date,
        provider=row["provider"],
        provider_observed_at=prov_obs_at,
        request_started_at=req_started,  # type: ignore[arg-type]
        response_received_at=resp_rcvd,  # type: ignore[arg-type]
        fact_hash=row["fact_hash"],
        fact_json=row["fact_json"],
        error_category=row["error_category"],
        error_message=row["error_message"],
        created_at=created_at,  # type: ignore[arg-type]
        contract_version=int(row["contract_version"]),
    )


def _row_to_reference_run(row: sqlite3.Row) -> PITReferenceCaptureRun:
    try:
        cap_date = date.fromisoformat(row["capture_date"])
    except Exception as exc:
        raise PITStoreError(f"Malformed persisted date for capture_date: {row['capture_date']!r}") from exc

    sched_for = _parse_dt(row["scheduled_for"], "scheduled_for")
    req_at = _parse_dt(row["requested_at"], "requested_at")
    comp_at = _parse_dt(row["completed_at"], "completed_at")
    created_at = _parse_dt(row["created_at"], "created_at")
    updated_at = _parse_dt(row["updated_at"], "updated_at")

    row_keys = set(row.keys())
    manifest_hash = row["manifest_hash"] if "manifest_hash" in row_keys else None

    return PITReferenceCaptureRun(
        capture_run_id=row["capture_run_id"],
        idempotency_key=row["idempotency_key"],
        request_fingerprint=row["request_fingerprint"],
        capture_slot=CaptureSlot(row["capture_slot"]),
        capture_date=cap_date,
        scheduled_for=sched_for,  # type: ignore[arg-type]
        requested_at=req_at,  # type: ignore[arg-type]
        completed_at=comp_at,
        requested_provider=row["requested_provider"],
        universe_hash=row["universe_hash"],
        manifest_hash=manifest_hash,
        requested_n=int(row["requested_n"]),
        known_n=int(row["known_n"]),
        unavailable_n=int(row["unavailable_n"]),
        ambiguous_n=int(row["ambiguous_n"]),
        error_n=int(row["error_n"]),
        status=CaptureRunStatus(row["status"]),
        created_at=created_at,  # type: ignore[arg-type]
        updated_at=updated_at,  # type: ignore[arg-type]
        contract_version=int(row["contract_version"]),
    )


def _row_to_reference_snapshot(row: sqlite3.Row) -> PITReferenceSnapshot:
    try:
        query_date = date.fromisoformat(row["provider_query_date"])
    except Exception as exc:
        raise PITStoreError(f"Malformed persisted date for provider_query_date: {row['provider_query_date']!r}") from exc

    req_ids = tuple(json.loads(row["provider_request_ids_json"])) if row["provider_request_ids_json"] else ()
    missing_fields = tuple(json.loads(row["missing_fields_json"])) if row["missing_fields_json"] else ()

    prov_active: bool | None = None
    if row["provider_active"] is not None:
        raw_val = row["provider_active"]
        if raw_val not in (0, 1):
            raise PITStoreError(f"Persisted provider_active must be 0, 1, or NULL, got {raw_val!r}")
        prov_active = bool(raw_val)

    prov_last_upd = _parse_dt(row["provider_last_updated_at"], "provider_last_updated_at")
    req_started = _parse_dt(row["request_started_at"], "request_started_at")
    resp_rcvd = _parse_dt(row["response_received_at"], "response_received_at")
    created_at = _parse_dt(row["created_at"], "created_at")

    return PITReferenceSnapshot(
        snapshot_id=row["snapshot_id"],
        capture_run_id=row["capture_run_id"],
        symbol=row["symbol"],
        observation_status=ReferenceObservationStatus(row["observation_status"]),
        provider=row["provider"],
        provider_query_date=query_date,
        provider_request_ids=req_ids,
        provider_ticker=row["provider_ticker"],
        provider_name=row["provider_name"],
        provider_market=row["provider_market"],
        provider_locale=row["provider_locale"],
        provider_active=prov_active,
        provider_type_code=row["provider_type_code"],
        provider_primary_exchange=row["provider_primary_exchange"],
        provider_cik=row["provider_cik"],
        provider_composite_figi=row["provider_composite_figi"],
        provider_share_class_figi=row["provider_share_class_figi"],
        provider_last_updated_at=prov_last_upd,
        provider_delisted_at=row["provider_delisted_at"],
        missing_fields=missing_fields,
        request_started_at=req_started,  # type: ignore[arg-type]
        response_received_at=resp_rcvd,  # type: ignore[arg-type]
        fact_hash=row["fact_hash"],
        fact_json=row["fact_json"],
        error_category=row["error_category"],
        error_message=row["error_message"],
        created_at=created_at,  # type: ignore[arg-type]
        contract_version=int(row["contract_version"]),
    )


def create_capture_run(
    run: PITCaptureRun,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITCaptureRun:
    """Atomically insert a new started capture run into SQLite."""
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _transaction(db_path=target_path) as con:
        con.execute(
            """
            INSERT INTO pit_capture_runs (
                capture_run_id, contract_version, idempotency_key, request_fingerprint,
                capture_kind, capture_slot, capture_date, scheduled_for, requested_at,
                completed_at, requested_provider, universe_hash, manifest_hash,
                requested_n, known_n, not_applicable_n, unavailable_n, error_n,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.capture_run_id,
                run.contract_version,
                run.idempotency_key,
                run.request_fingerprint,
                run.capture_kind.value,
                run.capture_slot.value,
                run.capture_date.isoformat(),
                run.scheduled_for.astimezone(UTC).isoformat(),
                run.requested_at.astimezone(UTC).isoformat(),
                run.completed_at.astimezone(UTC).isoformat() if run.completed_at else None,
                run.requested_provider,
                run.universe_hash,
                run.manifest_hash,
                run.requested_n,
                run.known_n,
                run.not_applicable_n,
                run.unavailable_n,
                run.error_n,
                run.status.value,
                run.created_at.astimezone(UTC).isoformat(),
                run.updated_at.astimezone(UTC).isoformat(),
            ),
        )
    return run


def insert_earnings_snapshots(
    snapshots: Sequence[PITEarningsSnapshot],
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> None:
    """Atomically insert immutable point-in-time earnings observation snapshots."""
    if not snapshots:
        return
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _transaction(db_path=target_path) as con:
        for snap in snapshots:
            con.execute(
                """
                INSERT INTO pit_earnings_snapshots (
                    snapshot_id, contract_version, capture_run_id, symbol,
                    observation_status, observation_origin, applicability_source,
                    provider_call_attempted, next_earnings_date, provider,
                    provider_observed_at, request_started_at, response_received_at,
                    fact_hash, fact_json, error_category, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap.snapshot_id,
                    snap.contract_version,
                    snap.capture_run_id,
                    snap.symbol,
                    snap.observation_status.value,
                    snap.observation_origin,
                    snap.applicability_source,
                    1 if snap.provider_call_attempted else 0,
                    snap.next_earnings_date.isoformat() if snap.next_earnings_date else None,
                    snap.provider,
                    snap.provider_observed_at.astimezone(UTC).isoformat() if snap.provider_observed_at else None,
                    snap.request_started_at.astimezone(UTC).isoformat() if snap.request_started_at else None,
                    snap.response_received_at.astimezone(UTC).isoformat() if snap.response_received_at else None,
                    snap.fact_hash,
                    snap.fact_json,
                    snap.error_category,
                    snap.error_message,
                    snap.created_at.astimezone(UTC).isoformat(),
                ),
            )


def finalize_capture_run(
    capture_run_id: str,
    *,
    status: CaptureRunStatus,
    known_n: int,
    unavailable_n: int,
    error_n: int,
    completed_at: datetime,
    updated_at: datetime,
    not_applicable_n: int = 0,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITCaptureRun:
    """Atomically transition a capture run from started to terminal status with resolved counts."""
    if status == CaptureRunStatus.STARTED:
        raise ValueError("Cannot finalize capture run to status 'started'")

    norm_completed_at = _normalize_aware_utc(completed_at, "completed_at")
    norm_updated_at = _normalize_aware_utc(updated_at, "updated_at")

    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _transaction(db_path=target_path) as con:
        cursor = con.execute(
            """
            UPDATE pit_capture_runs
            SET status = ?,
                known_n = ?,
                not_applicable_n = ?,
                unavailable_n = ?,
                error_n = ?,
                completed_at = ?,
                updated_at = ?
            WHERE capture_run_id = ? AND status = ?
            """,
            (
                status.value,
                known_n,
                not_applicable_n,
                unavailable_n,
                error_n,
                norm_completed_at.isoformat(),
                norm_updated_at.isoformat(),
                capture_run_id,
                CaptureRunStatus.STARTED.value,
            ),
        )
        if cursor.rowcount == 0:
            existing = con.execute(
                "SELECT status FROM pit_capture_runs WHERE capture_run_id = ?",
                (capture_run_id,),
            ).fetchone()
            if not existing:
                raise PITStoreError(f"Capture run {capture_run_id} not found during finalization")
            raise PITStoreError(
                f"Cannot finalize capture run {capture_run_id}: run is already in terminal state '{existing['status']}'"
            )
        row = con.execute(
            "SELECT * FROM pit_capture_runs WHERE capture_run_id = ?",
            (capture_run_id,),
        ).fetchone()
        if not row:
            raise PITStoreError(f"Capture run {capture_run_id} not found after finalization")
        return _row_to_run(row)


def get_capture_run(
    capture_run_id: str,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITCaptureRun | None:
    """Fetch capture run by ID or return None if not found."""
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    if not target_path.exists():
        return None
    with _conn(db_path=target_path) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pit_capture_runs'").fetchone():
            return None
        row = con.execute(
            "SELECT * FROM pit_capture_runs WHERE capture_run_id = ?",
            (capture_run_id,),
        ).fetchone()
        return _row_to_run(row) if row else None


def get_capture_run_by_idempotency_key(
    idempotency_key: str,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITCaptureRun | None:
    """Fetch capture run by idempotency key or return None if not found."""
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    if not target_path.exists():
        return None
    with _conn(db_path=target_path) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pit_capture_runs'").fetchone():
            return None
        row = con.execute(
            "SELECT * FROM pit_capture_runs WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return _row_to_run(row) if row else None


def list_earnings_snapshots(
    capture_run_id: str,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> tuple[PITEarningsSnapshot, ...]:
    """Return all snapshots for a capture run in deterministic order (symbol ASC, snapshot_id ASC)."""
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    if not target_path.exists():
        return ()
    with _conn(db_path=target_path) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pit_earnings_snapshots'").fetchone():
            return ()
        rows = con.execute(
            """
            SELECT * FROM pit_earnings_snapshots
            WHERE capture_run_id = ?
            ORDER BY symbol ASC, snapshot_id ASC
            """,
            (capture_run_id,),
        ).fetchall()
        return tuple(_row_to_snapshot(row) for row in rows)


def get_capture_result(
    capture_run_id: str,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITCaptureResult | None:
    """Fetch a capture run and its snapshots as a unified read model."""
    run = get_capture_run(capture_run_id, db_path=db_path, settings=settings)
    if run is None:
        return None
    snapshots = list_earnings_snapshots(capture_run_id, db_path=db_path, settings=settings)
    return PITCaptureResult(run=run, snapshots=snapshots)


def create_reference_capture_run(
    run: PITReferenceCaptureRun,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITReferenceCaptureRun:
    """Atomically insert a new started reference capture run into SQLite."""
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _transaction(db_path=target_path) as con:
        con.execute(
            """
            INSERT INTO pit_reference_capture_runs (
                capture_run_id, contract_version, idempotency_key, request_fingerprint,
                capture_slot, capture_date, scheduled_for, requested_at,
                completed_at, requested_provider, universe_hash, manifest_hash,
                requested_n, known_n, unavailable_n, ambiguous_n, error_n,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.capture_run_id,
                run.contract_version,
                run.idempotency_key,
                run.request_fingerprint,
                run.capture_slot.value,
                run.capture_date.isoformat(),
                run.scheduled_for.astimezone(UTC).isoformat(),
                run.requested_at.astimezone(UTC).isoformat(),
                run.completed_at.astimezone(UTC).isoformat() if run.completed_at else None,
                run.requested_provider,
                run.universe_hash,
                run.manifest_hash,
                run.requested_n,
                run.known_n,
                run.unavailable_n,
                run.ambiguous_n,
                run.error_n,
                run.status.value,
                run.created_at.astimezone(UTC).isoformat(),
                run.updated_at.astimezone(UTC).isoformat(),
            ),
        )
    return run


def insert_reference_snapshots(
    snapshots: Sequence[PITReferenceSnapshot],
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> None:
    """Atomically insert immutable point-in-time reference observation snapshots."""
    if not snapshots:
        return
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _transaction(db_path=target_path) as con:
        for snap in snapshots:
            con.execute(
                """
                INSERT INTO pit_reference_snapshots (
                    snapshot_id, contract_version, capture_run_id, symbol,
                    observation_status, provider, provider_query_date,
                    provider_request_ids_json, provider_ticker, provider_name,
                    provider_market, provider_locale, provider_active,
                    provider_type_code, provider_primary_exchange, provider_cik,
                    provider_composite_figi, provider_share_class_figi,
                    provider_last_updated_at, provider_delisted_at,
                    missing_fields_json, request_started_at, response_received_at,
                    fact_hash, fact_json, error_category, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap.snapshot_id,
                    snap.contract_version,
                    snap.capture_run_id,
                    snap.symbol,
                    snap.observation_status.value,
                    snap.provider,
                    snap.provider_query_date.isoformat(),
                    json.dumps(list(snap.provider_request_ids), sort_keys=True, separators=(",", ":")),
                    snap.provider_ticker,
                    snap.provider_name,
                    snap.provider_market,
                    snap.provider_locale,
                    (1 if snap.provider_active else 0) if snap.provider_active is not None else None,
                    snap.provider_type_code,
                    snap.provider_primary_exchange,
                    snap.provider_cik,
                    snap.provider_composite_figi,
                    snap.provider_share_class_figi,
                    snap.provider_last_updated_at.astimezone(UTC).isoformat() if snap.provider_last_updated_at else None,
                    snap.provider_delisted_at,
                    json.dumps(list(snap.missing_fields), sort_keys=True, separators=(",", ":")),
                    snap.request_started_at.astimezone(UTC).isoformat(),
                    snap.response_received_at.astimezone(UTC).isoformat(),
                    snap.fact_hash,
                    snap.fact_json,
                    snap.error_category,
                    snap.error_message,
                    snap.created_at.astimezone(UTC).isoformat(),
                ),
            )


def finalize_reference_capture_run(
    capture_run_id: str,
    *,
    status: CaptureRunStatus,
    known_n: int,
    unavailable_n: int,
    ambiguous_n: int,
    error_n: int,
    completed_at: datetime,
    updated_at: datetime,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITReferenceCaptureRun:
    """Atomically transition a reference capture run from started to terminal status with resolved counts."""
    if status == CaptureRunStatus.STARTED:
        raise ValueError("Cannot finalize capture run to status 'started'")

    norm_completed_at = _normalize_aware_utc(completed_at, "completed_at")
    norm_updated_at = _normalize_aware_utc(updated_at, "updated_at")

    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _transaction(db_path=target_path) as con:
        cursor = con.execute(
            """
            UPDATE pit_reference_capture_runs
            SET status = ?,
                known_n = ?,
                unavailable_n = ?,
                ambiguous_n = ?,
                error_n = ?,
                completed_at = ?,
                updated_at = ?
            WHERE capture_run_id = ? AND status = ?
            """,
            (
                status.value,
                known_n,
                unavailable_n,
                ambiguous_n,
                error_n,
                norm_completed_at.isoformat(),
                norm_updated_at.isoformat(),
                capture_run_id,
                CaptureRunStatus.STARTED.value,
            ),
        )
        if cursor.rowcount == 0:
            existing = con.execute(
                "SELECT status FROM pit_reference_capture_runs WHERE capture_run_id = ?",
                (capture_run_id,),
            ).fetchone()
            if not existing:
                raise PITStoreError(f"Reference capture run {capture_run_id} not found during finalization")
            raise PITStoreError(
                f"Cannot finalize reference capture run {capture_run_id}: run is already in terminal state '{existing['status']}'"
            )
        row = con.execute(
            "SELECT * FROM pit_reference_capture_runs WHERE capture_run_id = ?",
            (capture_run_id,),
        ).fetchone()
        if not row:
            raise PITStoreError(f"Reference capture run {capture_run_id} not found after finalization")
        return _row_to_reference_run(row)


def get_reference_capture_run(
    capture_run_id: str,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITReferenceCaptureRun | None:
    """Fetch reference capture run by ID or return None if not found."""
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    if not target_path.exists():
        return None
    with _conn(db_path=target_path) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pit_reference_capture_runs'").fetchone():
            return None
        row = con.execute(
            "SELECT * FROM pit_reference_capture_runs WHERE capture_run_id = ?",
            (capture_run_id,),
        ).fetchone()
        return _row_to_reference_run(row) if row else None


def get_reference_capture_run_by_idempotency_key(
    idempotency_key: str,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITReferenceCaptureRun | None:
    """Fetch reference capture run by idempotency key or return None if not found."""
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    if not target_path.exists():
        return None
    with _conn(db_path=target_path) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pit_reference_capture_runs'").fetchone():
            return None
        row = con.execute(
            "SELECT * FROM pit_reference_capture_runs WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return _row_to_reference_run(row) if row else None


def list_reference_snapshots(
    capture_run_id: str,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> tuple[PITReferenceSnapshot, ...]:
    """Return all reference snapshots for a capture run in deterministic order (symbol ASC, snapshot_id ASC)."""
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    if not target_path.exists():
        return ()
    with _conn(db_path=target_path) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pit_reference_snapshots'").fetchone():
            return ()
        rows = con.execute(
            """
            SELECT * FROM pit_reference_snapshots
            WHERE capture_run_id = ?
            ORDER BY symbol ASC, snapshot_id ASC
            """,
            (capture_run_id,),
        ).fetchall()
        return tuple(_row_to_reference_snapshot(row) for row in rows)


def get_reference_capture_result(
    capture_run_id: str,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITReferenceCaptureResult | None:
    """Fetch a reference capture run and its snapshots as a unified read model."""
    run = get_reference_capture_run(capture_run_id, db_path=db_path, settings=settings)
    if run is None:
        return None
    snapshots = list_reference_snapshots(capture_run_id, db_path=db_path, settings=settings)
    return PITReferenceCaptureResult(run=run, snapshots=snapshots)


def list_earnings_capture_runs(
    capture_date: date,
    slot: CaptureSlot,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> tuple[PITCaptureRun, ...]:
    """Return all earnings capture runs for a specific date and slot in deterministic order.

    Read-only: does not create the database if it does not exist.
    Order: requested_at ASC, capture_run_id ASC.
    """
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    if not target_path.exists():
        return ()
    with _conn(db_path=target_path) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pit_capture_runs'").fetchone():
            return ()
        rows = con.execute(
            """
            SELECT * FROM pit_capture_runs
            WHERE capture_date = ? AND capture_slot = ?
            ORDER BY requested_at ASC, capture_run_id ASC
            """,
            (capture_date.isoformat(), slot.value),
        ).fetchall()
        return tuple(_row_to_run(row) for row in rows)


def list_reference_capture_runs(
    capture_date: date,
    slot: CaptureSlot,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> tuple[PITReferenceCaptureRun, ...]:
    """Return all reference capture runs for a specific date and slot in deterministic order.

    Read-only: does not create the database if it does not exist.
    Order: requested_at ASC, capture_run_id ASC.
    """
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    if not target_path.exists():
        return ()
    with _conn(db_path=target_path) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pit_reference_capture_runs'").fetchone():
            return ()
        rows = con.execute(
            """
            SELECT * FROM pit_reference_capture_runs
            WHERE capture_date = ? AND capture_slot = ?
            ORDER BY requested_at ASC, capture_run_id ASC
            """,
            (capture_date.isoformat(), slot.value),
        ).fetchall()
        return tuple(_row_to_reference_run(row) for row in rows)
