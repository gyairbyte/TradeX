import sqlite3
from datetime import UTC, date, datetime

import pytest

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
    PITStoreError,
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


def test_finalize_capture_run_immutability(tmp_path) -> None:
    db_path = tmp_path / "immutability.db"
    store.init(db_path)

    now = datetime(2026, 8, 30, 13, 0, 0, tzinfo=UTC)

    def _make_run(run_id: str, idempotency_key: str) -> PITCaptureRun:
        return PITCaptureRun(
            capture_run_id=run_id,
            idempotency_key=idempotency_key,
            request_fingerprint=f"fp-{run_id}",
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 8, 30),
            scheduled_for=now,
            requested_at=now,
            completed_at=None,
            requested_provider="yahoo",
            universe_hash="uhash",
            requested_n=2,
            status=CaptureRunStatus.STARTED,
            created_at=now,
            updated_at=now,
        )

    # 1. started -> succeeded works
    create_capture_run(_make_run("run-succeed", "key-succeed"), db_path=db_path)
    t1 = datetime(2026, 8, 30, 13, 1, 0, tzinfo=UTC)
    res_succeed = finalize_capture_run(
        "run-succeed",
        status=CaptureRunStatus.SUCCEEDED,
        known_n=2,
        unavailable_n=0,
        error_n=0,
        completed_at=t1,
        updated_at=t1,
        db_path=db_path,
    )
    assert res_succeed.status == CaptureRunStatus.SUCCEEDED

    # Cannot re-finalize succeeded
    t2 = datetime(2026, 8, 30, 13, 2, 0, tzinfo=UTC)
    with pytest.raises(PITStoreError, match="already in terminal state 'succeeded'"):
        finalize_capture_run(
            "run-succeed",
            status=CaptureRunStatus.FAILED,
            known_n=0,
            unavailable_n=0,
            error_n=2,
            completed_at=t2,
            updated_at=t2,
            db_path=db_path,
        )
    # State remained succeeded and unmutated
    current = get_capture_run("run-succeed", db_path=db_path)
    assert current is not None
    assert current.status == CaptureRunStatus.SUCCEEDED
    assert current.known_n == 2
    assert current.completed_at == t1

    # 2. started -> partial works
    create_capture_run(_make_run("run-partial", "key-partial"), db_path=db_path)
    res_partial = finalize_capture_run(
        "run-partial",
        status=CaptureRunStatus.PARTIAL,
        known_n=1,
        unavailable_n=1,
        error_n=0,
        completed_at=t1,
        updated_at=t1,
        db_path=db_path,
    )
    assert res_partial.status == CaptureRunStatus.PARTIAL

    # Cannot re-finalize partial
    with pytest.raises(PITStoreError, match="already in terminal state 'partial'"):
        finalize_capture_run(
            "run-partial",
            status=CaptureRunStatus.SUCCEEDED,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            completed_at=t2,
            updated_at=t2,
            db_path=db_path,
        )

    # 3. started -> failed works
    create_capture_run(_make_run("run-failed", "key-failed"), db_path=db_path)
    res_failed = finalize_capture_run(
        "run-failed",
        status=CaptureRunStatus.FAILED,
        known_n=0,
        unavailable_n=0,
        error_n=2,
        completed_at=t1,
        updated_at=t1,
        db_path=db_path,
    )
    assert res_failed.status == CaptureRunStatus.FAILED

    # Cannot re-finalize failed
    with pytest.raises(PITStoreError, match="already in terminal state 'failed'"):
        finalize_capture_run(
            "run-failed",
            status=CaptureRunStatus.SUCCEEDED,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            completed_at=t2,
            updated_at=t2,
            db_path=db_path,
        )

    # 4. Finalizing non-existent run ID raises PITStoreError
    with pytest.raises(PITStoreError, match="Capture run nonexistent-run not found"):
        finalize_capture_run(
            "nonexistent-run",
            status=CaptureRunStatus.SUCCEEDED,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            completed_at=t1,
            updated_at=t1,
            db_path=db_path,
        )


def test_store_rejects_naive_and_malformed_persisted_timestamps(tmp_path) -> None:
    db_path = tmp_path / "naive_test.db"
    store.init(db_path)

    # 1. Insert raw run with naive scheduled_for
    with sqlite3.connect(db_path) as con:
        con.execute(
            """
            INSERT INTO pit_capture_runs (
                capture_run_id, contract_version, idempotency_key, request_fingerprint,
                capture_kind, capture_slot, capture_date, scheduled_for, requested_at,
                completed_at, requested_provider, universe_hash, requested_n, known_n,
                unavailable_n, error_n, status, created_at, updated_at
            ) VALUES (?, 1, ?, 'fp', 'earnings', 'morning', '2026-08-30', ?, ?, NULL, 'yahoo', 'uhash', 1, 0, 0, 0, 'started', ?, ?)
            """,
            ("run-naive", "key-naive", "2026-08-30T13:00:00", "2026-08-30T13:00:00+00:00", "2026-08-30T13:00:00+00:00", "2026-08-30T13:00:00+00:00"),
        )
        con.commit()

    with pytest.raises(PITStoreError, match="is naive; canonical UTC required"):
        get_capture_run("run-naive", db_path=db_path)

    # 2. Insert raw snapshot with naive created_at
    with sqlite3.connect(db_path) as con:
        con.execute(
            """
            INSERT INTO pit_earnings_snapshots (
                snapshot_id, contract_version, capture_run_id, symbol,
                observation_status, next_earnings_date, provider,
                provider_observed_at, request_started_at, response_received_at,
                fact_hash, fact_json, error_category, error_message, created_at
            ) VALUES ('snap-naive', 1, 'run-naive', 'AAPL', 'known', '2026-09-15', 'yahoo', NULL,
                      '2026-08-30T13:00:00+00:00', '2026-08-30T13:00:01+00:00',
                      'hash', '{}', NULL, NULL, '2026-08-30T13:00:01')
            """
        )
        con.commit()

    with pytest.raises(PITStoreError, match="is naive; canonical UTC required"):
        list_earnings_snapshots("run-naive", db_path=db_path)

    # 3. Malformed timestamp string
    with sqlite3.connect(db_path) as con:
        con.execute(
            "UPDATE pit_capture_runs SET scheduled_for = 'invalid-timestamp' WHERE capture_run_id = 'run-naive'"
        )
        con.commit()

    with pytest.raises(PITStoreError, match="Malformed persisted timestamp"):
        get_capture_run("run-naive", db_path=db_path)


def test_read_queries_on_nonexistent_db_do_not_create_file(tmp_path) -> None:
    nonexistent = tmp_path / "sub" / "does_not_exist.db"
    assert not nonexistent.exists()

    assert get_capture_run("any-id", db_path=nonexistent) is None
    assert not nonexistent.exists()

    assert get_capture_run_by_idempotency_key("any-key", db_path=nonexistent) is None
    assert not nonexistent.exists()

    assert list_earnings_snapshots("any-id", db_path=nonexistent) == ()
    assert not nonexistent.exists()

    assert get_capture_result("any-id", db_path=nonexistent) is None
    assert not nonexistent.exists()
