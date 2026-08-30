"""Persistence and query tests for point-in-time capture tables (MVP-ARCH-001-R7-PIT-001A)."""
from __future__ import annotations

from datetime import UTC, date, datetime

from tradex.pit.models import (
    CaptureKind,
    CaptureRunStatus,
    CaptureSlot,
    ObservationStatus,
    PITCaptureRun,
    PITEarningsSnapshot,
    build_known_fact_payload,
    compute_fact_hash,
    serialize_canonical_fact_json,
)
from tradex.pit.store import (
    create_capture_run,
    finalize_capture_run,
    get_capture_result,
    get_capture_run,
    get_capture_run_by_idempotency_key,
    insert_earnings_snapshots,
    list_earnings_snapshots,
)
from tradex.tracker import store


def test_store_crud_lifecycle(tmp_path) -> None:
    db_path = tmp_path / "test_store.db"
    store.init(db_path)

    now = datetime(2026, 8, 30, 13, 0, 0, tzinfo=UTC)

    # 1. Create run
    run = PITCaptureRun(
        capture_run_id="run-100",
        idempotency_key="key-100",
        request_fingerprint="fp-100",
        capture_kind=CaptureKind.EARNINGS,
        capture_slot=CaptureSlot.MORNING,
        capture_date=date(2026, 8, 30),
        scheduled_for=now,
        requested_at=now,
        completed_at=None,
        requested_provider="yahoo",
        universe_hash="uhash-100",
        requested_n=2,
        status=CaptureRunStatus.STARTED,
        created_at=now,
        updated_at=now,
    )
    created = create_capture_run(run, db_path=db_path)
    assert created.status == CaptureRunStatus.STARTED

    # Fetch by ID and key
    fetched = get_capture_run("run-100", db_path=db_path)
    assert fetched is not None
    assert fetched.idempotency_key == "key-100"

    fetched_key = get_capture_run_by_idempotency_key("key-100", db_path=db_path)
    assert fetched_key is not None
    assert fetched_key.capture_run_id == "run-100"

    # 2. Insert snapshots
    fact_aapl = serialize_canonical_fact_json(build_known_fact_payload(date(2026, 9, 15)))
    snap1 = PITEarningsSnapshot(
        snapshot_id="snap-1",
        capture_run_id="run-100",
        symbol="AAPL",
        observation_status=ObservationStatus.KNOWN,
        next_earnings_date=date(2026, 9, 15),
        provider="yahoo",
        provider_observed_at=None,
        request_started_at=now,
        response_received_at=now,
        fact_hash=compute_fact_hash(fact_aapl),
        fact_json=fact_aapl,
        error_category=None,
        error_message=None,
        created_at=now,
    )
    fact_msft = serialize_canonical_fact_json(build_known_fact_payload(date(2026, 9, 20)))
    snap2 = PITEarningsSnapshot(
        snapshot_id="snap-2",
        capture_run_id="run-100",
        symbol="MSFT",
        observation_status=ObservationStatus.KNOWN,
        next_earnings_date=date(2026, 9, 20),
        provider="yahoo",
        provider_observed_at=None,
        request_started_at=now,
        response_received_at=now,
        fact_hash=compute_fact_hash(fact_msft),
        fact_json=fact_msft,
        error_category=None,
        error_message=None,
        created_at=now,
    )
    insert_earnings_snapshots([snap2, snap1], db_path=db_path)

    # 3. List snapshots (must be sorted by symbol ASC, snapshot_id ASC)
    snaps = list_earnings_snapshots("run-100", db_path=db_path)
    assert len(snaps) == 2
    assert snaps[0].symbol == "AAPL"
    assert snaps[1].symbol == "MSFT"

    # 4. Finalize run
    completed_time = datetime(2026, 8, 30, 13, 1, 0, tzinfo=UTC)
    finalized = finalize_capture_run(
        "run-100",
        status=CaptureRunStatus.SUCCEEDED,
        known_n=2,
        unavailable_n=0,
        error_n=0,
        completed_at=completed_time,
        updated_at=completed_time,
        db_path=db_path,
    )
    assert finalized.status == CaptureRunStatus.SUCCEEDED
    assert finalized.completed_at == completed_time

    # 5. Read model
    result = get_capture_result("run-100", db_path=db_path)
    assert result is not None
    assert result.run.status == CaptureRunStatus.SUCCEEDED
    assert len(result.snapshots) == 2
