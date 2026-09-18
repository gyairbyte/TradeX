"""Focused unit tests for point-in-time domain models, enums, serialization, and invariants."""
from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

import pytest

from tradex.pit.models import (
    PIT_CAPTURE_CONTRACT_VERSION,
    PIT_CAPTURE_WRITE_CONTRACT_VERSION,
    CaptureKind,
    CaptureRunStatus,
    CaptureSlot,
    ObservationStatus,
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


def test_capture_enums() -> None:
    assert CaptureSlot.EVENING.value == "evening"
    assert CaptureSlot.MORNING.value == "morning"
    assert CaptureKind.EARNINGS.value == "earnings"
    assert CaptureRunStatus.STARTED.value == "started"
    assert CaptureRunStatus.SUCCEEDED.value == "succeeded"
    assert CaptureRunStatus.PARTIAL.value == "partial"
    assert CaptureRunStatus.FAILED.value == "failed"
    assert ObservationStatus.KNOWN.value == "known"
    assert ObservationStatus.NOT_APPLICABLE.value == "not_applicable"
    assert ObservationStatus.UNAVAILABLE.value == "unavailable"
    assert ObservationStatus.ERROR.value == "error"
    assert PIT_CAPTURE_CONTRACT_VERSION == 2
    assert PIT_CAPTURE_WRITE_CONTRACT_VERSION == 1


def test_symbol_normalization() -> None:
    raw = [" msft ", "aapl", "NVDA", "AAPL", "msft"]
    normalized = normalize_symbols(raw)
    assert normalized == ("AAPL", "MSFT", "NVDA")

    with pytest.raises(ValueError, match="Blank or whitespace-only"):
        normalize_symbols(["AAPL", "  "])

    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_symbols([])

    with pytest.raises(TypeError):
        normalize_symbols("AAPL")  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        normalize_symbols(["AAPL", 123])  # type: ignore[list-item]


def test_universe_and_fingerprint_hashing() -> None:
    symbols = ("AAPL", "MSFT", "NVDA")
    uhash = compute_universe_hash(symbols)
    assert len(uhash) == 64
    assert uhash == hashlib.sha256(b"AAPL,MSFT,NVDA").hexdigest()

    fp = compute_request_fingerprint(
        contract_version=1,
        capture_kind="earnings",
        capture_slot="evening",
        capture_date="2026-08-30",
        scheduled_for_iso="2026-08-31T00:30:00Z",
        requested_provider="yahoo",
        normalized_symbols=symbols,
    )
    assert len(fp) == 64

    key = compute_default_idempotency_key("2026-08-30", CaptureSlot.EVENING, fp)
    assert key == f"pit-earnings-2026-08-30-evening-{fp[:16]}"


def test_canonical_fact_serialization_and_hash() -> None:
    payload_known = build_known_fact_payload(date(2026, 9, 15))
    serialized_known = serialize_canonical_fact_json(payload_known)
    assert serialized_known == '{"next_earnings_date":"2026-09-15"}'
    assert compute_fact_hash(serialized_known) == hashlib.sha256(serialized_known.encode("utf-8")).hexdigest()

    payload_unavail = build_unavailable_fact_payload("EarningsDataUnavailableError", "Upcoming earnings date unavailable for XYZ")
    serialized_unavail = serialize_canonical_fact_json(payload_unavail)
    assert serialized_unavail == '{"error_category":"EarningsDataUnavailableError","error_message":"Upcoming earnings date unavailable for XYZ","next_earnings_date":null}'
    assert compute_fact_hash(serialized_unavail) == hashlib.sha256(serialized_unavail.encode("utf-8")).hexdigest()


def test_pit_earnings_snapshot_invariants() -> None:
    now = datetime(2026, 8, 30, 13, 0, 0, tzinfo=UTC)
    fact_json = serialize_canonical_fact_json({"next_earnings_date": "2026-09-15"})
    fact_hash = compute_fact_hash(fact_json)

    # Valid known snapshot
    snap = PITEarningsSnapshot(
        snapshot_id="snap-1",
        capture_run_id="run-1",
        symbol="AAPL",
        observation_status=ObservationStatus.KNOWN,
        next_earnings_date=date(2026, 9, 15),
        provider="yahoo",
        provider_observed_at=None,
        request_started_at=now,
        response_received_at=now,
        fact_hash=fact_hash,
        fact_json=fact_json,
        error_category=None,
        error_message=None,
        created_at=now,
    )
    assert snap.symbol == "AAPL"
    assert snap.contract_version == PIT_CAPTURE_WRITE_CONTRACT_VERSION

    # Known observation missing next_earnings_date
    with pytest.raises(ValueError, match="next_earnings_date is required when observation_status is 'known'"):
        PITEarningsSnapshot(
            snapshot_id="snap-2",
            capture_run_id="run-1",
            symbol="AAPL",
            observation_status=ObservationStatus.KNOWN,
            next_earnings_date=None,
            provider="yahoo",
            provider_observed_at=None,
            request_started_at=now,
            response_received_at=now,
            fact_hash=fact_hash,
            fact_json=fact_json,
            error_category=None,
            error_message=None,
            created_at=now,
        )

    # Unavailable observation with fabricated date
    unavail_json = serialize_canonical_fact_json(build_unavailable_fact_payload("Error", "msg"))
    unavail_hash = compute_fact_hash(unavail_json)
    with pytest.raises(ValueError, match="next_earnings_date must be None"):
        PITEarningsSnapshot(
            snapshot_id="snap-3",
            capture_run_id="run-1",
            symbol="AAPL",
            observation_status=ObservationStatus.UNAVAILABLE,
            next_earnings_date=date(2026, 9, 15),
            provider="yahoo",
            provider_observed_at=None,
            request_started_at=now,
            response_received_at=now,
            fact_hash=unavail_hash,
            fact_json=unavail_json,
            error_category="Error",
            error_message="msg",
            created_at=now,
        )

    # Request timestamps order violation
    later = datetime(2026, 8, 30, 13, 0, 5, tzinfo=UTC)
    with pytest.raises(ValueError, match="request_started_at must be <= response_received_at"):
        PITEarningsSnapshot(
            snapshot_id="snap-4",
            capture_run_id="run-1",
            symbol="AAPL",
            observation_status=ObservationStatus.KNOWN,
            next_earnings_date=date(2026, 9, 15),
            provider="yahoo",
            provider_observed_at=None,
            request_started_at=later,
            response_received_at=now,
            fact_hash=fact_hash,
            fact_json=fact_json,
            error_category=None,
            error_message=None,
            created_at=now,
        )

    # Fact hash mismatch
    with pytest.raises(ValueError, match="does not match SHA-256"):
        PITEarningsSnapshot(
            snapshot_id="snap-5",
            capture_run_id="run-1",
            symbol="AAPL",
            observation_status=ObservationStatus.KNOWN,
            next_earnings_date=date(2026, 9, 15),
            provider="yahoo",
            provider_observed_at=None,
            request_started_at=now,
            response_received_at=now,
            fact_hash="wrong-hash",
            fact_json=fact_json,
            error_category=None,
            error_message=None,
            created_at=now,
        )


def test_pit_capture_run_invariants() -> None:
    now = datetime(2026, 8, 30, 13, 0, 0, tzinfo=UTC)

    # Valid started run
    run = PITCaptureRun(
        capture_run_id="run-1",
        idempotency_key="key-1",
        request_fingerprint="fp-1",
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
    assert run.status == CaptureRunStatus.STARTED

    # Terminal status requires completed_at
    with pytest.raises(ValueError, match="completed_at is required"):
        PITCaptureRun(
            capture_run_id="run-2",
            idempotency_key="key-2",
            request_fingerprint="fp-2",
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 8, 30),
            scheduled_for=now,
            requested_at=now,
            completed_at=None,
            requested_provider="yahoo",
            universe_hash="uhash",
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=now,
            updated_at=now,
        )

    # Terminal count mismatch
    with pytest.raises(ValueError, match="Count mismatch"):
        PITCaptureRun(
            capture_run_id="run-3",
            idempotency_key="key-3",
            request_fingerprint="fp-3",
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 8, 30),
            scheduled_for=now,
            requested_at=now,
            completed_at=now,
            requested_provider="yahoo",
            universe_hash="uhash",
            requested_n=2,
            known_n=1,
            unavailable_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=now,
            updated_at=now,
        )


def test_models_reject_naive_timestamps_and_normalize_aware_to_utc() -> None:
    from zoneinfo import ZoneInfo
    ny_tz = ZoneInfo("America/New_York")
    aware_ny = datetime(2026, 8, 30, 9, 30, 0, tzinfo=ny_tz)
    naive_dt = datetime(2026, 8, 30, 9, 30, 0)  # noqa: DTZ001

    # 1. Run model with aware NY timestamp normalizes to UTC
    run = PITCaptureRun(
        capture_run_id="run-utc-1",
        idempotency_key="key-utc-1",
        request_fingerprint="fp-utc-1",
        capture_kind=CaptureKind.EARNINGS,
        capture_slot=CaptureSlot.MORNING,
        capture_date=date(2026, 8, 30),
        scheduled_for=aware_ny,
        requested_at=aware_ny,
        completed_at=None,
        requested_provider="yahoo",
        universe_hash="uhash",
        requested_n=1,
        created_at=aware_ny,
        updated_at=aware_ny,
    )
    assert run.scheduled_for.tzinfo == UTC
    assert run.scheduled_for.hour == 13  # 9:30 AM EDT is 13:30 UTC
    assert run.requested_at.tzinfo == UTC
    assert run.created_at.tzinfo == UTC
    assert run.updated_at.tzinfo == UTC

    # 2. Run model rejects naive timestamp
    with pytest.raises(ValueError, match="naive datetimes are rejected"):
        PITCaptureRun(
            capture_run_id="run-naive",
            idempotency_key="key-naive",
            request_fingerprint="fp-naive",
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 8, 30),
            scheduled_for=naive_dt,
            requested_at=naive_dt,
            completed_at=None,
            requested_provider="yahoo",
            universe_hash="uhash",
            requested_n=1,
        )

    # 3. Snapshot model with aware NY timestamp normalizes to UTC
    fact_json = serialize_canonical_fact_json({"next_earnings_date": "2026-09-15"})
    fact_hash = compute_fact_hash(fact_json)
    snap = PITEarningsSnapshot(
        snapshot_id="snap-utc-1",
        capture_run_id="run-utc-1",
        symbol="AAPL",
        observation_status=ObservationStatus.KNOWN,
        next_earnings_date=date(2026, 9, 15),
        provider="yahoo",
        provider_observed_at=aware_ny,
        request_started_at=aware_ny,
        response_received_at=aware_ny,
        fact_hash=fact_hash,
        fact_json=fact_json,
        error_category=None,
        error_message=None,
        created_at=aware_ny,
    )
    assert snap.request_started_at.tzinfo == UTC
    assert snap.response_received_at.tzinfo == UTC
    assert snap.created_at.tzinfo == UTC
    assert snap.provider_observed_at is not None and snap.provider_observed_at.tzinfo == UTC

    # 4. Snapshot model rejects naive timestamp
    with pytest.raises(ValueError, match="naive datetimes are rejected"):
        PITEarningsSnapshot(
            snapshot_id="snap-naive",
            capture_run_id="run-utc-1",
            symbol="AAPL",
            observation_status=ObservationStatus.KNOWN,
            next_earnings_date=date(2026, 9, 15),
            provider="yahoo",
            provider_observed_at=None,
            request_started_at=naive_dt,
            response_received_at=naive_dt,
            fact_hash=fact_hash,
            fact_json=fact_json,
            error_category=None,
            error_message=None,
            created_at=naive_dt,
        )
