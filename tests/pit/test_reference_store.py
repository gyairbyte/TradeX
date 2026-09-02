"""Deterministic persistence tests for reference PIT store APIs and Schema v7 primitives."""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tradex.pit.models import (
    CaptureRunStatus,
    CaptureSlot,
    PITReferenceCaptureRun,
    PITReferenceSnapshot,
    ReferenceObservationStatus,
    build_known_reference_fact_payload,
    compute_fact_hash,
    serialize_canonical_fact_json,
)
from tradex.pit.store import (
    PITStoreError,
    create_reference_capture_run,
    finalize_reference_capture_run,
    get_reference_capture_result,
    get_reference_capture_run,
    get_reference_capture_run_by_idempotency_key,
    insert_reference_snapshots,
    list_reference_snapshots,
)
from tradex.tracker import store


def _seed_started_ref_run(
    db_path: Path,
    run_id: str = "ref-run-001",
    idempotency_key: str = "pit-ref-key-001",
    symbols_n: int = 2,
) -> PITReferenceCaptureRun:
    store.init(db_path)
    now = datetime(2026, 8, 30, 13, 0, 0, tzinfo=UTC)
    run = PITReferenceCaptureRun(
        capture_run_id=run_id,
        idempotency_key=idempotency_key,
        request_fingerprint="fp-ref-001",
        capture_slot=CaptureSlot.EVENING,
        capture_date=date(2026, 8, 30),
        scheduled_for=now,
        requested_at=now,
        completed_at=None,
        requested_provider="massive",
        universe_hash="uhash-ref-001",
        requested_n=symbols_n,
        known_n=0,
        unavailable_n=0,
        ambiguous_n=0,
        error_n=0,
        status=CaptureRunStatus.STARTED,
        created_at=now,
        updated_at=now,
    )
    return create_reference_capture_run(run, db_path=db_path)


def _make_snapshot(
    run_id: str,
    symbol: str,
    status: ReferenceObservationStatus = ReferenceObservationStatus.KNOWN,
    snap_id: str | None = None,
) -> PITReferenceSnapshot:
    fact_payload = build_known_reference_fact_payload(
        active=True,
        cik="0000320193",
        composite_figi="FIGI123",
        delisted_utc=None,
        last_updated_utc="2026-08-29T20:00:00Z",
        locale="us",
        market="stocks",
        name=f"{symbol} Corp",
        primary_exchange="XNAS",
        share_class_figi="FIGI456",
        ticker=symbol,
        type_code="CS",
    )
    fact_json = serialize_canonical_fact_json(fact_payload)
    fact_hash = compute_fact_hash(fact_json)
    now = datetime(2026, 8, 30, 13, 0, 1, tzinfo=UTC)

    return PITReferenceSnapshot(
        snapshot_id=snap_id or f"snap-{symbol}",
        capture_run_id=run_id,
        symbol=symbol,
        observation_status=status,
        provider="massive",
        provider_query_date=date(2026, 8, 30),
        provider_request_ids=("req-1",),
        provider_ticker=symbol,
        provider_name=f"{symbol} Corp",
        provider_market="stocks",
        provider_locale="us",
        provider_active=True,
        provider_type_code="CS",
        provider_primary_exchange="XNAS",
        provider_cik="0000320193",
        provider_composite_figi="FIGI123",
        provider_share_class_figi="FIGI456",
        provider_last_updated_at=datetime(2026, 8, 29, 20, 0, tzinfo=UTC),
        provider_delisted_at=None,
        missing_fields=("delisted_utc",),
        request_started_at=now,
        response_received_at=now,
        fact_hash=fact_hash,
        fact_json=fact_json,
        error_category=None,
        error_message=None,
        created_at=now,
    )


def test_create_and_get_reference_capture_run(tmp_path) -> None:
    db_path = tmp_path / "ref_store.db"
    _seed_started_ref_run(db_path)

    fetched = get_reference_capture_run("ref-run-001", db_path=db_path)
    assert fetched is not None
    assert fetched.capture_run_id == "ref-run-001"
    assert fetched.status == CaptureRunStatus.STARTED
    assert fetched.requested_n == 2

    by_idem = get_reference_capture_run_by_idempotency_key("pit-ref-key-001", db_path=db_path)
    assert by_idem is not None
    assert by_idem.capture_run_id == "ref-run-001"


def test_insert_and_list_reference_snapshots_ordering(tmp_path) -> None:
    db_path = tmp_path / "ref_snaps.db"
    _seed_started_ref_run(db_path, symbols_n=3)

    snap_msft = _make_snapshot("ref-run-001", "MSFT", snap_id="snap-2")
    snap_aapl = _make_snapshot("ref-run-001", "AAPL", snap_id="snap-1")
    snap_nvda = _make_snapshot("ref-run-001", "NVDA", snap_id="snap-3")

    # Insert out of alphabetical order
    insert_reference_snapshots([snap_msft, snap_aapl, snap_nvda], db_path=db_path)

    snapshots = list_reference_snapshots("ref-run-001", db_path=db_path)
    assert len(snapshots) == 3
    # Deterministically sorted: AAPL, MSFT, NVDA
    assert snapshots[0].symbol == "AAPL"
    assert snapshots[1].symbol == "MSFT"
    assert snapshots[2].symbol == "NVDA"
    assert snapshots[0].provider_request_ids == ("req-1",)
    assert snapshots[0].missing_fields == ("delisted_utc",)


def test_finalize_reference_capture_run_immutability(tmp_path) -> None:
    db_path = tmp_path / "ref_finalize.db"
    _seed_started_ref_run(db_path, symbols_n=2)

    comp_time = datetime(2026, 8, 30, 13, 1, 0, tzinfo=UTC)
    finalized = finalize_reference_capture_run(
        "ref-run-001",
        status=CaptureRunStatus.SUCCEEDED,
        known_n=2,
        unavailable_n=0,
        ambiguous_n=0,
        error_n=0,
        completed_at=comp_time,
        updated_at=comp_time,
        db_path=db_path,
    )

    assert finalized.status == CaptureRunStatus.SUCCEEDED
    assert finalized.known_n == 2
    assert finalized.completed_at == comp_time

    # Attempting to finalize again must raise PITStoreError
    with pytest.raises(PITStoreError, match="already in terminal state"):
        finalize_reference_capture_run(
            "ref-run-001",
            status=CaptureRunStatus.FAILED,
            known_n=0,
            unavailable_n=2,
            ambiguous_n=0,
            error_n=0,
            completed_at=comp_time,
            updated_at=comp_time,
            db_path=db_path,
        )


def test_get_reference_capture_result_unified(tmp_path) -> None:
    db_path = tmp_path / "ref_res.db"
    _seed_started_ref_run(db_path, symbols_n=1)
    snap = _make_snapshot("ref-run-001", "AAPL")
    insert_reference_snapshots([snap], db_path=db_path)

    res = get_reference_capture_result("ref-run-001", db_path=db_path)
    assert res is not None
    assert res.run.capture_run_id == "ref-run-001"
    assert len(res.snapshots) == 1
    assert res.snapshots[0].symbol == "AAPL"


def test_nonexistent_db_returns_none_without_creating_file(tmp_path) -> None:
    db_path = tmp_path / "does_not_exist.db"
    assert not db_path.exists()
    assert get_reference_capture_run("r1", db_path=db_path) is None
    assert get_reference_capture_run_by_idempotency_key("k1", db_path=db_path) is None
    assert list_reference_snapshots("r1", db_path=db_path) == ()
    assert get_reference_capture_result("r1", db_path=db_path) is None
    assert not db_path.exists()
