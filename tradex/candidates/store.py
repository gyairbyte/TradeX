"""SQLite persistence and neutral retrieval primitives for candidate snapshots.

Implements atomic writes, exact-replay idempotency, conflict detection on immutable
re-use, and neutral query APIs for candidate snapshots and dossiers.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tradex.candidates.models import (
    CandidateDimension,
    CandidateDossier,
    CandidateEvaluation,
    CandidateEvidence,
    CandidateMissingData,
    CandidateReason,
    CandidateSnapshot,
    MissingDataStatus,
    ReasonPolarity,
    ReasonSeverity,
    SecurityIdentityStatus,
    _normalize_aware_dt,
    _normalize_symbol,
    _validate_json_serializable,
)
from tradex.tracker.store import StoreError, _conn, _resolve_db_path, _transaction

if TYPE_CHECKING:
    from tradex.config import TradeXSettings


def _parse_iso_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _row_to_snapshot(row: sqlite3.Row) -> CandidateSnapshot:
    return CandidateSnapshot(
        candidate_id=row["candidate_id"],
        symbol=row["symbol"],
        decision_timestamp=_parse_iso_dt(row["decision_timestamp"]),  # type: ignore[arg-type]
        contract_version=int(row["contract_version"]),
        trading_date=row["trading_date"],
        security_identity_version=row["security_identity_version"],
        security_identity_status=SecurityIdentityStatus(row["security_identity_status"]),
        created_at=_parse_iso_dt(row["created_at"]),  # type: ignore[arg-type]
    )


def _row_to_evaluation(row: sqlite3.Row) -> CandidateEvaluation:
    dims = json.loads(row["dimensions_json"]) if row["dimensions_json"] else {}
    return CandidateEvaluation(
        evaluation_id=row["evaluation_id"],
        candidate_id=row["candidate_id"],
        evaluator_id=row["evaluator_id"],
        evaluator_version=row["evaluator_version"],
        evidence_state=row["evidence_state"],
        dimensions=dims,
        created_at=_parse_iso_dt(row["created_at"]),  # type: ignore[arg-type]
    )


def _row_to_evidence(row: sqlite3.Row) -> CandidateEvidence:
    meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
    return CandidateEvidence(
        evidence_id=row["evidence_id"],
        candidate_id=row["candidate_id"],
        evidence_type=row["evidence_type"],
        source_ref_type=row["source_ref_type"],
        source_ref_id=row["source_ref_id"],
        provider=row["provider"],
        observed_at=_parse_iso_dt(row["observed_at"]),
        metadata=meta,
        created_at=_parse_iso_dt(row["created_at"]),  # type: ignore[arg-type]
    )


def _row_to_reason(row: sqlite3.Row) -> CandidateReason:
    dim = CandidateDimension(row["dimension"]) if row["dimension"] else None
    return CandidateReason(
        reason_id=row["reason_id"],
        candidate_id=row["candidate_id"],
        evaluation_id=row["evaluation_id"],
        dimension=dim,
        reason_code=row["reason_code"],
        polarity=ReasonPolarity(row["polarity"]),
        severity=ReasonSeverity(row["severity"]),
        human_text=row["human_text"],
        source_evidence_id=row["source_evidence_id"],
        created_at=_parse_iso_dt(row["created_at"]),  # type: ignore[arg-type]
    )


def _row_to_missing_data(row: sqlite3.Row) -> CandidateMissingData:
    return CandidateMissingData(
        record_id=row["record_id"],
        candidate_id=row["candidate_id"],
        evaluation_id=row["evaluation_id"],
        input_name=row["input_name"],
        data_family=row["data_family"],
        status=MissingDataStatus(row["status"]),
        detail=row["detail"],
        provider=row["provider"],
        observed_at=_parse_iso_dt(row["observed_at"]),
        created_at=_parse_iso_dt(row["created_at"]),  # type: ignore[arg-type]
    )


def _get_candidate_dossier_from_conn(con: sqlite3.Connection, candidate_id: str) -> CandidateDossier | None:
    snap_row = con.execute("SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
    if snap_row is None:
        return None

    eval_rows = con.execute(
        "SELECT * FROM candidate_evaluations WHERE candidate_id = ? ORDER BY created_at ASC, evaluation_id ASC",
        (candidate_id,),
    ).fetchall()
    evid_rows = con.execute(
        "SELECT * FROM candidate_evidence WHERE candidate_id = ? ORDER BY created_at ASC, evidence_id ASC",
        (candidate_id,),
    ).fetchall()
    reason_rows = con.execute(
        "SELECT * FROM candidate_reasons WHERE candidate_id = ? ORDER BY created_at ASC, reason_id ASC",
        (candidate_id,),
    ).fetchall()
    missing_rows = con.execute(
        "SELECT * FROM candidate_missing_data WHERE candidate_id = ? ORDER BY created_at ASC, record_id ASC",
        (candidate_id,),
    ).fetchall()

    return CandidateDossier(
        snapshot=_row_to_snapshot(snap_row),
        evaluations=tuple(_row_to_evaluation(r) for r in eval_rows),
        evidence=tuple(_row_to_evidence(r) for r in evid_rows),
        reasons=tuple(_row_to_reason(r) for r in reason_rows),
        missing_data=tuple(_row_to_missing_data(r) for r in missing_rows),
    )


def record_candidate_dossier(
    dossier: CandidateDossier,
    db_path: Path | str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> CandidateDossier:
    """Record a complete CandidateDossier atomically.

    Implements:
    - Atomic transaction: entire dossier or nothing.
    - Idempotency: exact replay returns existing dossier without mutation.
    - Immutability: reuse of candidate_id with conflicting content raises StoreError.
    """
    if not isinstance(dossier, CandidateDossier):
        raise TypeError(f"dossier must be CandidateDossier, got {type(dossier).__name__}")

    path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    cand_id = dossier.snapshot.candidate_id

    with _transaction(db_path=path) as con:
        existing = _get_candidate_dossier_from_conn(con, cand_id)
        if existing is not None:
            # Check for exact equality
            if existing == dossier:
                return existing
            raise StoreError(
                f"Candidate ID '{cand_id}' already exists with divergent immutable content. "
                "Existing candidate snapshots cannot be overwritten."
            )

        # Insert candidate snapshot header
        snap = dossier.snapshot
        con.execute(
            """
            INSERT INTO candidates (
                candidate_id, contract_version, symbol, decision_timestamp,
                trading_date, security_identity_version, security_identity_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snap.candidate_id,
                snap.contract_version,
                snap.symbol,
                snap.decision_timestamp.isoformat(),
                snap.trading_date,
                snap.security_identity_version,
                snap.security_identity_status.value,
                snap.created_at.isoformat(),
            ),
        )

        # Insert evaluations
        for ev in dossier.evaluations:
            con.execute(
                """
                INSERT INTO candidate_evaluations (
                    evaluation_id, candidate_id, evaluator_id, evaluator_version,
                    evidence_state, dimensions_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ev.evaluation_id,
                    ev.candidate_id,
                    ev.evaluator_id,
                    ev.evaluator_version,
                    ev.evidence_state,
                    _validate_json_serializable(ev.dimensions),
                    ev.created_at.isoformat(),
                ),
            )

        # Insert evidence
        for evid in dossier.evidence:
            con.execute(
                """
                INSERT INTO candidate_evidence (
                    evidence_id, candidate_id, evidence_type, source_ref_type,
                    source_ref_id, provider, observed_at, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evid.evidence_id,
                    evid.candidate_id,
                    evid.evidence_type,
                    evid.source_ref_type,
                    evid.source_ref_id,
                    evid.provider,
                    evid.observed_at.isoformat() if evid.observed_at else None,
                    _validate_json_serializable(evid.metadata),
                    evid.created_at.isoformat(),
                ),
            )

        # Insert reasons
        for r in dossier.reasons:
            con.execute(
                """
                INSERT INTO candidate_reasons (
                    reason_id, candidate_id, evaluation_id, dimension,
                    reason_code, polarity, severity, human_text, source_evidence_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r.reason_id,
                    r.candidate_id,
                    r.evaluation_id,
                    r.dimension,
                    r.reason_code,
                    r.polarity.value,
                    r.severity.value,
                    r.human_text,
                    r.source_evidence_id,
                    r.created_at.isoformat(),
                ),
            )

        # Insert missing data
        for m in dossier.missing_data:
            con.execute(
                """
                INSERT INTO candidate_missing_data (
                    record_id, candidate_id, evaluation_id, input_name,
                    data_family, status, detail, provider, observed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    m.record_id,
                    m.candidate_id,
                    m.evaluation_id,
                    m.input_name,
                    m.data_family,
                    m.status.value,
                    m.detail,
                    m.provider,
                    m.observed_at.isoformat() if m.observed_at else None,
                    m.created_at.isoformat(),
                ),
            )

    return dossier


def get_candidate(
    candidate_id: str,
    db_path: Path | str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> CandidateSnapshot | None:
    """Retrieve the immutable candidate snapshot header for candidate_id."""
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _conn(db_path=path) as con:
        row = con.execute("SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            return None
        return _row_to_snapshot(row)


def get_candidate_dossier(
    candidate_id: str,
    db_path: Path | str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> CandidateDossier | None:
    """Retrieve the complete CandidateDossier for candidate_id."""
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    with _conn(db_path=path) as con:
        return _get_candidate_dossier_from_conn(con, candidate_id)


def list_candidates(
    symbol: str | None = None,
    trading_date: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int | None = None,
    db_path: Path | str | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> list[CandidateSnapshot]:
    """Neutral query API returning candidate snapshot headers.

    Uses deterministic non-ranked ordering (decision_timestamp DESC, candidate_id ASC).
    Does NOT rank, score, filter by quality, or recommend candidates.
    """
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    query = ["SELECT * FROM candidates WHERE 1=1"]
    params: list[object] = []

    if symbol is not None:
        query.append("AND symbol = ?")
        params.append(_normalize_symbol(symbol))

    if trading_date is not None:
        query.append("AND trading_date = ?")
        params.append(trading_date.strip())

    if start_time is not None:
        norm_start = _normalize_aware_dt(start_time, "start_time")
        query.append("AND decision_timestamp >= ?")
        params.append(norm_start.isoformat())

    if end_time is not None:
        norm_end = _normalize_aware_dt(end_time, "end_time")
        query.append("AND decision_timestamp <= ?")
        params.append(norm_end.isoformat())

    query.append("ORDER BY decision_timestamp DESC, candidate_id ASC")

    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        query.append("LIMIT ?")
        params.append(limit)

    sql = " ".join(query)
    with _conn(db_path=path) as con:
        rows = con.execute(sql, tuple(params)).fetchall()
        return [_row_to_snapshot(r) for r in rows]
