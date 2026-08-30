"""SQLite persistence primitives and row mapping for point-in-time capture (MVP-ARCH-001-R7-PIT-001A).

Implements atomic run creation, immutable snapshot insertion, run finalization,
and neutral audit/read APIs according to Schema v6.
"""
from __future__ import annotations

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
)
from tradex.tracker.store import StoreError, _conn, _resolve_db_path, _transaction

if TYPE_CHECKING:
    from tradex.config import TradeXSettings


class PITStoreError(StoreError):
    """Base persistence exception for point-in-time capture."""


class PITIdempotencyConflictError(PITStoreError):
    """Raised when an existing idempotency key is reused with divergent request parameters."""


def _parse_dt(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _row_to_run(row: sqlite3.Row) -> PITCaptureRun:
    cap_date = date.fromisoformat(row["capture_date"])
    sched_for = _parse_dt(row["scheduled_for"])
    req_at = _parse_dt(row["requested_at"])
    comp_at = _parse_dt(row["completed_at"])
    created_at = _parse_dt(row["created_at"])
    updated_at = _parse_dt(row["updated_at"])

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
        requested_n=int(row["requested_n"]),
        known_n=int(row["known_n"]),
        unavailable_n=int(row["unavailable_n"]),
        error_n=int(row["error_n"]),
        status=CaptureRunStatus(row["status"]),
        created_at=created_at,  # type: ignore[arg-type]
        updated_at=updated_at,  # type: ignore[arg-type]
        contract_version=int(row["contract_version"]),
    )


def _row_to_snapshot(row: sqlite3.Row) -> PITEarningsSnapshot:
    nxt_date = date.fromisoformat(row["next_earnings_date"]) if row["next_earnings_date"] else None
    prov_obs_at = _parse_dt(row["provider_observed_at"])
    req_started = _parse_dt(row["request_started_at"])
    resp_rcvd = _parse_dt(row["response_received_at"])
    created_at = _parse_dt(row["created_at"])

    return PITEarningsSnapshot(
        snapshot_id=row["snapshot_id"],
        capture_run_id=row["capture_run_id"],
        symbol=row["symbol"],
        observation_status=ObservationStatus(row["observation_status"]),
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
                completed_at, requested_provider, universe_hash, requested_n, known_n,
                unavailable_n, error_n, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.capture_run_id,
                run.contract_version,
                run.idempotency_key,
                run.request_fingerprint,
                run.capture_kind.value,
                run.capture_slot.value,
                run.capture_date.isoformat(),
                run.scheduled_for.isoformat(),
                run.requested_at.isoformat(),
                run.completed_at.isoformat() if run.completed_at else None,
                run.requested_provider,
                run.universe_hash,
                run.requested_n,
                run.known_n,
                run.unavailable_n,
                run.error_n,
                run.status.value,
                run.created_at.isoformat(),
                run.updated_at.isoformat(),
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
                    observation_status, next_earnings_date, provider,
                    provider_observed_at, request_started_at, response_received_at,
                    fact_hash, fact_json, error_category, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap.snapshot_id,
                    snap.contract_version,
                    snap.capture_run_id,
                    snap.symbol,
                    snap.observation_status.value,
                    snap.next_earnings_date.isoformat() if snap.next_earnings_date else None,
                    snap.provider,
                    snap.provider_observed_at.isoformat() if snap.provider_observed_at else None,
                    snap.request_started_at.isoformat(),
                    snap.response_received_at.isoformat(),
                    snap.fact_hash,
                    snap.fact_json,
                    snap.error_category,
                    snap.error_message,
                    snap.created_at.isoformat(),
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
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITCaptureRun:
    """Atomically transition a capture run from started to terminal status with resolved counts."""
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _transaction(db_path=target_path) as con:
        con.execute(
            """
            UPDATE pit_capture_runs
            SET status = ?,
                known_n = ?,
                unavailable_n = ?,
                error_n = ?,
                completed_at = ?,
                updated_at = ?
            WHERE capture_run_id = ?
            """,
            (
                status.value,
                known_n,
                unavailable_n,
                error_n,
                completed_at.isoformat(),
                updated_at.isoformat(),
                capture_run_id,
            ),
        )
        row = con.execute(
            "SELECT * FROM pit_capture_runs WHERE capture_run_id = ?",
            (capture_run_id,),
        ).fetchone()
        if not row:
            raise PITStoreError(f"Capture run {capture_run_id} not found during finalization")
        return _row_to_run(row)


def get_capture_run(
    capture_run_id: str,
    *,
    db_path: Path | None = None,
    settings: TradeXSettings | None = None,
) -> PITCaptureRun | None:
    """Fetch capture run by ID or return None if not found."""
    target_path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _conn(db_path=target_path) as con:
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
    with _conn(db_path=target_path) as con:
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
    with _conn(db_path=target_path) as con:
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
