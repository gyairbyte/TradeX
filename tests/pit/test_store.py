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
    PITReferenceCaptureRun,
    PITReferenceSnapshot,
    ReferenceObservationStatus,
    build_known_fact_payload,
    build_known_reference_fact_payload,
    build_not_applicable_earnings_fact_payload,
    compute_fact_hash,
    serialize_canonical_fact_json,
)
from tradex.pit.store import (
    PITStoreError,
    create_capture_run,
    create_reference_capture_run,
    finalize_capture_run,
    get_capture_result,
    get_capture_run,
    get_capture_run_by_idempotency_key,
    insert_earnings_snapshots,
    insert_reference_snapshots,
    list_earnings_snapshots,
    list_reference_capture_runs,
    list_reference_snapshots,
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


def test_finalize_capture_run_rejects_naive_timestamps_and_normalizes_aware(tmp_path) -> None:
    from zoneinfo import ZoneInfo

    db_path = tmp_path / "finalize_naive.db"
    store.init(db_path)

    t_start = datetime(2026, 8, 30, 13, 0, 0, tzinfo=UTC)
    run = PITCaptureRun(
        capture_run_id="run-finalize-test",
        idempotency_key="key-finalize-test",
        request_fingerprint="fp-finalize-test",
        capture_kind=CaptureKind.EARNINGS,
        capture_slot=CaptureSlot.MORNING,
        capture_date=date(2026, 8, 30),
        scheduled_for=t_start,
        requested_at=t_start,
        completed_at=None,
        requested_provider="yahoo",
        universe_hash="uhash",
        requested_n=2,
        status=CaptureRunStatus.STARTED,
        created_at=t_start,
        updated_at=t_start,
    )
    create_capture_run(run, db_path=db_path)

    naive_ts = datetime(2026, 8, 30, 13, 5, 0)  # noqa: DTZ001
    aware_utc = datetime(2026, 8, 30, 13, 5, 0, tzinfo=UTC)

    # A. naive completed_at: raises ValueError, run remains started with zero mutation
    with pytest.raises(ValueError, match="completed_at must be timezone-aware; naive datetimes are rejected"):
        finalize_capture_run(
            "run-finalize-test",
            status=CaptureRunStatus.SUCCEEDED,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            completed_at=naive_ts,
            updated_at=aware_utc,
            db_path=db_path,
        )

    current_a = get_capture_run("run-finalize-test", db_path=db_path)
    assert current_a is not None
    assert current_a.status == CaptureRunStatus.STARTED
    assert current_a.known_n == 0
    assert current_a.unavailable_n == 0
    assert current_a.error_n == 0
    assert current_a.completed_at is None
    assert current_a.updated_at == t_start

    # B. naive updated_at: raises ValueError, run remains started with zero mutation
    with pytest.raises(ValueError, match="updated_at must be timezone-aware; naive datetimes are rejected"):
        finalize_capture_run(
            "run-finalize-test",
            status=CaptureRunStatus.SUCCEEDED,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            completed_at=aware_utc,
            updated_at=naive_ts,
            db_path=db_path,
        )

    current_b = get_capture_run("run-finalize-test", db_path=db_path)
    assert current_b is not None
    assert current_b.status == CaptureRunStatus.STARTED
    assert current_b.known_n == 0
    assert current_b.unavailable_n == 0
    assert current_b.error_n == 0
    assert current_b.completed_at is None
    assert current_b.updated_at == t_start

    # C. non-UTC aware finalization timestamp: accepted and persisted as equivalent canonical UTC
    ny_tz = ZoneInfo("America/New_York")
    aware_ny = datetime(2026, 8, 30, 9, 5, 0, tzinfo=ny_tz)  # 9:05 AM EDT == 13:05 UTC

    finalized = finalize_capture_run(
        "run-finalize-test",
        status=CaptureRunStatus.SUCCEEDED,
        known_n=2,
        unavailable_n=0,
        error_n=0,
        completed_at=aware_ny,
        updated_at=aware_ny,
        db_path=db_path,
    )

    assert finalized.status == CaptureRunStatus.SUCCEEDED
    assert finalized.completed_at == aware_utc
    assert finalized.completed_at.tzinfo == UTC
    assert finalized.updated_at == aware_utc
    assert finalized.updated_at.tzinfo == UTC

    # Read back from database
    persisted = get_capture_run("run-finalize-test", db_path=db_path)
    assert persisted is not None
    assert persisted.status == CaptureRunStatus.SUCCEEDED
    assert persisted.completed_at == aware_utc
    assert persisted.completed_at.tzinfo == UTC
    assert persisted.updated_at == aware_utc
    assert persisted.updated_at.tzinfo == UTC


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


def test_v2_store_crud_round_trip(tmp_path) -> None:
    """Verify v2 earnings run, v2 provider snapshot, v2 manifest N-A snapshot, and v2 reference run/snapshot round trip in Schema v8."""
    db_path = tmp_path / "v2_store_test.db"
    store.init(db_path)

    now = datetime(2026, 8, 30, 13, 0, 0, tzinfo=UTC)
    mhash = "m" * 64

    # 1. Create v2 earnings run with manifest_hash and not_applicable_n
    run_v2 = PITCaptureRun(
        capture_run_id="run-v2-100",
        idempotency_key="key-v2-100",
        request_fingerprint="fp-v2-100",
        capture_kind=CaptureKind.EARNINGS,
        capture_slot=CaptureSlot.MORNING,
        capture_date=date(2026, 8, 30),
        scheduled_for=now,
        requested_at=now,
        completed_at=None,
        requested_provider="yahoo",
        universe_hash="uhash-v2",
        manifest_hash=mhash,
        requested_n=2,
        known_n=0,
        not_applicable_n=1,
        unavailable_n=0,
        error_n=0,
        status=CaptureRunStatus.STARTED,
        created_at=now,
        updated_at=now,
        contract_version=2,
    )
    created = create_capture_run(run_v2, db_path=db_path)
    assert created.contract_version == 2
    assert created.manifest_hash == mhash
    assert created.not_applicable_n == 1

    fetched_run = get_capture_run("run-v2-100", db_path=db_path)
    assert fetched_run is not None
    assert fetched_run.contract_version == 2
    assert fetched_run.manifest_hash == mhash
    assert fetched_run.not_applicable_n == 1

    # 2. Insert v2 snapshots: 1 provider-origin known, 1 manifest-origin NOT_APPLICABLE
    fact_known = serialize_canonical_fact_json(build_known_fact_payload(date(2026, 9, 15)))
    snap_known = PITEarningsSnapshot(
        snapshot_id="snap-v2-known",
        capture_run_id="run-v2-100",
        symbol="AAPL",
        observation_status=ObservationStatus.KNOWN,
        observation_origin="provider",
        applicability_source=None,
        provider_call_attempted=True,
        next_earnings_date=date(2026, 9, 15),
        provider="yahoo",
        provider_observed_at=None,
        request_started_at=now,
        response_received_at=now,
        fact_hash=compute_fact_hash(fact_known),
        fact_json=fact_known,
        error_category=None,
        error_message=None,
        created_at=now,
        contract_version=2,
    )
    fact_na = serialize_canonical_fact_json(build_not_applicable_earnings_fact_payload())
    snap_na = PITEarningsSnapshot(
        snapshot_id="snap-v2-na",
        capture_run_id="run-v2-100",
        symbol="SPY",
        observation_status=ObservationStatus.NOT_APPLICABLE,
        observation_origin="manifest",
        applicability_source="manifest",
        provider_call_attempted=False,
        next_earnings_date=None,
        provider=None,
        provider_observed_at=None,
        request_started_at=None,
        response_received_at=None,
        fact_hash=compute_fact_hash(fact_na),
        fact_json=fact_na,
        error_category=None,
        error_message=None,
        created_at=now,
        contract_version=2,
    )
    insert_earnings_snapshots([snap_known, snap_na], db_path=db_path)

    snapshots = list_earnings_snapshots("run-v2-100", db_path=db_path)
    assert len(snapshots) == 2
    by_sym = {s.symbol: s for s in snapshots}

    s_aapl = by_sym["AAPL"]
    assert s_aapl.contract_version == 2
    assert s_aapl.observation_origin == "provider"
    assert s_aapl.applicability_source is None
    assert s_aapl.provider_call_attempted is True
    assert s_aapl.provider == "yahoo"

    s_spy = by_sym["SPY"]
    assert s_spy.contract_version == 2
    assert s_spy.observation_status == ObservationStatus.NOT_APPLICABLE
    assert s_spy.observation_origin == "manifest"
    assert s_spy.applicability_source == "manifest"
    assert s_spy.provider_call_attempted is False
    assert s_spy.provider is None
    assert s_spy.request_started_at is None
    assert s_spy.response_received_at is None

    # 3. Finalize run
    finalized = finalize_capture_run(
        "run-v2-100",
        status=CaptureRunStatus.SUCCEEDED,
        known_n=1,
        not_applicable_n=1,
        unavailable_n=0,
        error_n=0,
        completed_at=now,
        updated_at=now,
        db_path=db_path,
    )
    assert finalized.status == CaptureRunStatus.SUCCEEDED
    assert finalized.known_n == 1
    assert finalized.not_applicable_n == 1

    persisted_final = get_capture_run("run-v2-100", db_path=db_path)
    assert persisted_final is not None
    assert persisted_final.status == CaptureRunStatus.SUCCEEDED
    assert persisted_final.not_applicable_n == 1

    # 4. Reference run & snapshot v2 round-trip
    ref_run_v2 = PITReferenceCaptureRun(
        capture_run_id="ref-run-v2-100",
        idempotency_key="ref-key-v2-100",
        request_fingerprint="ref-fp-v2-100",
        capture_slot=CaptureSlot.MORNING,
        capture_date=date(2026, 8, 30),
        scheduled_for=now,
        requested_at=now,
        completed_at=now,
        requested_provider="massive",
        universe_hash="ref-uhash-v2",
        manifest_hash=mhash,
        requested_n=1,
        known_n=1,
        unavailable_n=0,
        ambiguous_n=0,
        error_n=0,
        status=CaptureRunStatus.SUCCEEDED,
        created_at=now,
        updated_at=now,
        contract_version=2,
    )
    create_reference_capture_run(ref_run_v2, db_path=db_path)

    ref_fact_payload = build_known_reference_fact_payload(
        active=True,
        cik="0000320193",
        composite_figi="FIGI123",
        delisted_utc=None,
        last_updated_utc="2026-08-29T20:00:00Z",
        locale="us",
        market="stocks",
        name="Apple Inc",
        primary_exchange="XNAS",
        share_class_figi="FIGI456",
        ticker="AAPL",
        type_code="CS",
    )
    ref_fact_json = serialize_canonical_fact_json(ref_fact_payload)
    ref_fact_hash = compute_fact_hash(ref_fact_json)
    ref_snap_v2 = PITReferenceSnapshot(
        snapshot_id="ref-snap-v2-100",
        capture_run_id="ref-run-v2-100",
        symbol="AAPL",
        observation_status=ReferenceObservationStatus.KNOWN,
        provider="massive",
        provider_query_date=date(2026, 8, 30),
        provider_request_ids=("req-1",),
        provider_ticker="AAPL",
        provider_name="Apple Inc",
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
        fact_hash=ref_fact_hash,
        fact_json=ref_fact_json,
        error_category=None,
        error_message=None,
        created_at=now,
        contract_version=2,
    )
    insert_reference_snapshots([ref_snap_v2], db_path=db_path)

    ref_runs = list_reference_capture_runs(date(2026, 8, 30), CaptureSlot.MORNING, db_path=db_path)
    assert len(ref_runs) == 1
    assert ref_runs[0].contract_version == 2
    assert ref_runs[0].manifest_hash == mhash

    ref_snaps = list_reference_snapshots("ref-run-v2-100", db_path=db_path)
    assert len(ref_snaps) == 1
    assert ref_snaps[0].contract_version == 2


def test_legacy_schema_v7_pre_init_row_reads(tmp_path) -> None:
    """Verify row mappers defensively supply defaults when reading rows from unmigrated Schema v7 tables before store.init()."""
    db_path = tmp_path / "legacy_v7_preflight.db"

    # Build raw Schema v7 database without calling store.init()
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE pit_capture_runs (
                capture_run_id TEXT PRIMARY KEY,
                contract_version INTEGER NOT NULL DEFAULT 1 CHECK (contract_version = 1),
                idempotency_key TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL,
                capture_kind TEXT NOT NULL CHECK (capture_kind = 'earnings'),
                capture_slot TEXT NOT NULL CHECK (capture_slot IN ('morning', 'evening')),
                capture_date TEXT NOT NULL CHECK (length(capture_date) = 10),
                scheduled_for TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                completed_at TEXT,
                requested_provider TEXT NOT NULL,
                universe_hash TEXT NOT NULL,
                requested_n INTEGER NOT NULL CHECK (requested_n >= 0),
                known_n INTEGER NOT NULL DEFAULT 0 CHECK (known_n >= 0),
                unavailable_n INTEGER NOT NULL DEFAULT 0 CHECK (unavailable_n >= 0),
                error_n INTEGER NOT NULL DEFAULT 0 CHECK (error_n >= 0),
                status TEXT NOT NULL CHECK (status IN ('started', 'succeeded', 'partial', 'failed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        con.execute(
            """
            CREATE TABLE pit_earnings_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                contract_version INTEGER NOT NULL DEFAULT 1 CHECK (contract_version = 1),
                capture_run_id TEXT NOT NULL REFERENCES pit_capture_runs(capture_run_id) ON DELETE CASCADE,
                symbol TEXT NOT NULL,
                observation_status TEXT NOT NULL CHECK (observation_status IN ('known', 'unavailable', 'error')),
                next_earnings_date TEXT,
                provider TEXT NOT NULL,
                provider_observed_at TEXT,
                request_started_at TEXT NOT NULL,
                response_received_at TEXT NOT NULL,
                fact_hash TEXT NOT NULL,
                fact_json TEXT NOT NULL,
                error_category TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        con.execute(
            """
            CREATE TABLE pit_reference_capture_runs (
                capture_run_id TEXT PRIMARY KEY,
                contract_version INTEGER NOT NULL DEFAULT 1 CHECK (contract_version = 1),
                idempotency_key TEXT NOT NULL UNIQUE,
                request_fingerprint TEXT NOT NULL,
                capture_slot TEXT NOT NULL CHECK (capture_slot IN ('morning', 'evening')),
                capture_date TEXT NOT NULL CHECK (length(capture_date) = 10),
                scheduled_for TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                completed_at TEXT,
                requested_provider TEXT NOT NULL,
                universe_hash TEXT NOT NULL,
                requested_n INTEGER NOT NULL CHECK (requested_n >= 0),
                known_n INTEGER NOT NULL DEFAULT 0 CHECK (known_n >= 0),
                unavailable_n INTEGER NOT NULL DEFAULT 0 CHECK (unavailable_n >= 0),
                ambiguous_n INTEGER NOT NULL DEFAULT 0 CHECK (ambiguous_n >= 0),
                error_n INTEGER NOT NULL DEFAULT 0 CHECK (error_n >= 0),
                status TEXT NOT NULL CHECK (status IN ('started', 'succeeded', 'partial', 'failed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        con.execute("PRAGMA user_version = 7;")

        # Insert historical rows into v7 tables
        now_iso = "2026-08-30T13:00:00+00:00"
        con.execute(
            """
            INSERT INTO pit_capture_runs (
                capture_run_id, contract_version, idempotency_key, request_fingerprint,
                capture_kind, capture_slot, capture_date, scheduled_for, requested_at,
                completed_at, requested_provider, universe_hash, requested_n, known_n,
                unavailable_n, error_n, status, created_at, updated_at
            ) VALUES ('run-v7-1', 1, 'key-v7-1', 'fp-v7', 'earnings', 'morning', '2026-08-30',
                      ?, ?, ?, 'yahoo', 'uhash-v7', 1, 1, 0, 0, 'succeeded', ?, ?);
            """,
            (now_iso, now_iso, now_iso, now_iso, now_iso),
        )
        v7_fact_json = '{"next_earnings_date":"2026-09-15"}'
        v7_fact_hash = compute_fact_hash(v7_fact_json)
        con.execute(
            """
            INSERT INTO pit_earnings_snapshots (
                snapshot_id, contract_version, capture_run_id, symbol, observation_status,
                next_earnings_date, provider, provider_observed_at, request_started_at,
                response_received_at, fact_hash, fact_json, error_category, error_message, created_at
            ) VALUES ('snap-v7-1', 1, 'run-v7-1', 'AAPL', 'known', '2026-09-15', 'yahoo',
                      NULL, ?, ?, ?, ?, NULL, NULL, ?);
            """,
            (now_iso, now_iso, v7_fact_hash, v7_fact_json, now_iso),
        )
        con.execute(
            """
            INSERT INTO pit_reference_capture_runs (
                capture_run_id, contract_version, idempotency_key, request_fingerprint,
                capture_slot, capture_date, scheduled_for, requested_at, completed_at,
                requested_provider, universe_hash, requested_n, known_n, unavailable_n,
                ambiguous_n, error_n, status, created_at, updated_at
            ) VALUES ('ref-v7-1', 1, 'ref-key-v7-1', 'ref-fp-v7', 'morning', '2026-08-30',
                      ?, ?, ?, 'massive', 'uhash-v7', 1, 1, 0, 0, 0, 'succeeded', ?, ?);
            """,
            (now_iso, now_iso, now_iso, now_iso, now_iso),
        )
        con.commit()
    finally:
        con.close()

    # Preflight read BEFORE store.init() migration
    run = get_capture_run("run-v7-1", db_path=db_path)
    assert run is not None
    assert run.contract_version == 1
    assert run.manifest_hash is None
    assert run.not_applicable_n == 0

    snaps = list_earnings_snapshots("run-v7-1", db_path=db_path)
    assert len(snaps) == 1
    s = snaps[0]
    assert s.contract_version == 1
    assert s.observation_origin == "provider"
    assert s.applicability_source is None
    assert s.provider_call_attempted is True
    assert s.provider == "yahoo"

    ref_runs = list_reference_capture_runs(date(2026, 8, 30), CaptureSlot.MORNING, db_path=db_path)
    assert len(ref_runs) == 1
    assert ref_runs[0].contract_version == 1
    assert ref_runs[0].manifest_hash is None
