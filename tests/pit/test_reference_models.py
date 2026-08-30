"""Deterministic unit tests for reference PIT domain models, builders, and immutability invariants."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from tradex.pit.models import (
    PIT_CAPTURE_CONTRACT_VERSION,
    CaptureRunStatus,
    CaptureSlot,
    PITReferenceCaptureRun,
    PITReferenceSnapshot,
    ReferenceObservationStatus,
    audit_missing_reference_fields,
    build_known_reference_fact_payload,
    compute_fact_hash,
    compute_reference_default_idempotency_key,
    serialize_canonical_fact_json,
)


def _make_valid_snapshot(
    *,
    snapshot_id: str = "snap-001",
    capture_run_id: str = "run-001",
    symbol: str = "AAPL",
    observation_status: ReferenceObservationStatus = ReferenceObservationStatus.KNOWN,
    provider: str = "massive",
    provider_query_date: date = date(2026, 8, 30),
    provider_request_ids: tuple[str, ...] = ("req-1",),
    provider_ticker: str | None = "AAPL",
    provider_name: str | None = "Apple Inc.",
    provider_market: str | None = "stocks",
    provider_locale: str | None = "us",
    provider_active: bool | None = True,
    provider_type_code: str | None = "CS",
    provider_primary_exchange: str | None = "XNAS",
    provider_cik: str | None = "0000320193",
    provider_composite_figi: str | None = "BBG000B9XRY4",
    provider_share_class_figi: str | None = "BBG001S5N8V8",
    provider_last_updated_at: datetime | None = datetime(2026, 8, 29, 20, 0, tzinfo=UTC),
    provider_delisted_at: str | None = None,
    missing_fields: tuple[str, ...] = ("delisted_utc",),
    request_started_at: datetime = datetime(2026, 8, 30, 13, 0, 0, tzinfo=UTC),
    response_received_at: datetime = datetime(2026, 8, 30, 13, 0, 1, tzinfo=UTC),
    created_at: datetime = datetime(2026, 8, 30, 13, 0, 1, tzinfo=UTC),
    contract_version: int = PIT_CAPTURE_CONTRACT_VERSION,
) -> PITReferenceSnapshot:
    fact_payload = build_known_reference_fact_payload(
        active=provider_active,
        cik=provider_cik,
        composite_figi=provider_composite_figi,
        delisted_utc=provider_delisted_at,
        last_updated_utc=provider_last_updated_at.isoformat() if provider_last_updated_at else None,
        locale=provider_locale,
        market=provider_market,
        name=provider_name,
        primary_exchange=provider_primary_exchange,
        share_class_figi=provider_share_class_figi,
        ticker=provider_ticker or symbol,
        type_code=provider_type_code,
    )
    fact_json = serialize_canonical_fact_json(fact_payload)
    fact_hash = compute_fact_hash(fact_json)

    return PITReferenceSnapshot(
        snapshot_id=snapshot_id,
        capture_run_id=capture_run_id,
        symbol=symbol,
        observation_status=observation_status,
        provider=provider,
        provider_query_date=provider_query_date,
        provider_request_ids=provider_request_ids,
        provider_ticker=provider_ticker,
        provider_name=provider_name,
        provider_market=provider_market,
        provider_locale=provider_locale,
        provider_active=provider_active,
        provider_type_code=provider_type_code,
        provider_primary_exchange=provider_primary_exchange,
        provider_cik=provider_cik,
        provider_composite_figi=provider_composite_figi,
        provider_share_class_figi=provider_share_class_figi,
        provider_last_updated_at=provider_last_updated_at,
        provider_delisted_at=provider_delisted_at,
        missing_fields=missing_fields,
        request_started_at=request_started_at,
        response_received_at=response_received_at,
        fact_hash=fact_hash,
        fact_json=fact_json,
        error_category=None,
        error_message=None,
        created_at=created_at,
        contract_version=contract_version,
    )


def test_snapshot_valid_construction() -> None:
    snap = _make_valid_snapshot()
    assert snap.symbol == "AAPL"
    assert snap.observation_status == ReferenceObservationStatus.KNOWN
    assert snap.provider_active is True
    assert snap.contract_version == 1


def test_snapshot_rejects_invalid_contract_version() -> None:
    with pytest.raises(ValueError, match="Invalid contract_version"):
        _make_valid_snapshot(contract_version=2)


def test_snapshot_rejects_invalid_symbol() -> None:
    with pytest.raises(ValueError, match="symbol must be non-empty and uppercase"):
        _make_valid_snapshot(symbol="")
    with pytest.raises(ValueError, match="symbol must be non-empty and uppercase"):
        _make_valid_snapshot(symbol="aapl")


def test_snapshot_rejects_naive_datetimes() -> None:
    naive_dt = datetime(2026, 8, 30, 13, 0)  # noqa: DTZ001
    with pytest.raises(ValueError, match="must be timezone-aware"):
        _make_valid_snapshot(request_started_at=naive_dt)


def test_snapshot_rejects_backward_clock() -> None:
    t1 = datetime(2026, 8, 30, 13, 0, 5, tzinfo=UTC)
    t2 = datetime(2026, 8, 30, 13, 0, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="request_started_at must be <= response_received_at"):
        _make_valid_snapshot(request_started_at=t1, response_received_at=t2)


def test_snapshot_rejects_fact_hash_mismatch() -> None:
    fact_json = '{"ticker":"AAPL"}'
    with pytest.raises(ValueError, match="fact_hash"):
        PITReferenceSnapshot(
            snapshot_id="s1",
            capture_run_id="r1",
            symbol="AAPL",
            observation_status=ReferenceObservationStatus.KNOWN,
            provider="massive",
            provider_query_date=date(2026, 8, 30),
            provider_request_ids=(),
            provider_ticker="AAPL",
            provider_name="Apple",
            provider_market="stocks",
            provider_locale="us",
            provider_active=True,
            provider_type_code="CS",
            provider_primary_exchange="XNAS",
            provider_cik="0000320193",
            provider_composite_figi="FIGI",
            provider_share_class_figi="FIGI2",
            provider_last_updated_at=None,
            provider_delisted_at=None,
            missing_fields=(),
            request_started_at=datetime(2026, 8, 30, 13, 0, tzinfo=UTC),
            response_received_at=datetime(2026, 8, 30, 13, 0, 1, tzinfo=UTC),
            fact_hash="wrong_hash",
            fact_json=fact_json,
            error_category=None,
            error_message=None,
            created_at=datetime(2026, 8, 30, 13, 0, 1, tzinfo=UTC),
        )


def test_run_valid_construction() -> None:
    run = PITReferenceCaptureRun(
        capture_run_id="run-001",
        idempotency_key="idem-001",
        request_fingerprint="fp-001",
        capture_slot=CaptureSlot.EVENING,
        capture_date=date(2026, 8, 30),
        scheduled_for=datetime(2026, 8, 31, 0, 30, tzinfo=UTC),
        requested_at=datetime(2026, 8, 31, 0, 30, tzinfo=UTC),
        completed_at=datetime(2026, 8, 31, 0, 30, 5, tzinfo=UTC),
        requested_provider="massive",
        universe_hash="uhash-001",
        requested_n=2,
        known_n=1,
        unavailable_n=1,
        ambiguous_n=0,
        error_n=0,
        status=CaptureRunStatus.PARTIAL,
    )
    assert run.requested_n == 2
    assert run.status == CaptureRunStatus.PARTIAL


def test_run_terminal_requires_completed_at_and_matching_counts() -> None:
    with pytest.raises(ValueError, match="completed_at is required"):
        PITReferenceCaptureRun(
            capture_run_id="run-001",
            idempotency_key="idem-001",
            request_fingerprint="fp-001",
            capture_slot=CaptureSlot.EVENING,
            capture_date=date(2026, 8, 30),
            scheduled_for=datetime(2026, 8, 31, 0, 30, tzinfo=UTC),
            requested_at=datetime(2026, 8, 31, 0, 30, tzinfo=UTC),
            completed_at=None,
            requested_provider="massive",
            universe_hash="uhash-001",
            requested_n=1,
            known_n=1,
            status=CaptureRunStatus.SUCCEEDED,
        )

    with pytest.raises(ValueError, match="Count mismatch"):
        PITReferenceCaptureRun(
            capture_run_id="run-001",
            idempotency_key="idem-001",
            request_fingerprint="fp-001",
            capture_slot=CaptureSlot.EVENING,
            capture_date=date(2026, 8, 30),
            scheduled_for=datetime(2026, 8, 31, 0, 30, tzinfo=UTC),
            requested_at=datetime(2026, 8, 31, 0, 30, tzinfo=UTC),
            completed_at=datetime(2026, 8, 31, 0, 30, 5, tzinfo=UTC),
            requested_provider="massive",
            universe_hash="uhash-001",
            requested_n=3,
            known_n=1,
            unavailable_n=1,
            ambiguous_n=0,
            error_n=0,
            status=CaptureRunStatus.PARTIAL,
        )


def test_audit_missing_reference_fields() -> None:
    data = {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "market": "stocks",
        "locale": "us",
        "active": True,
        "type": "CS",
        "primary_exchange": "XNAS",
        "cik": "0000320193",
    }
    missing = audit_missing_reference_fields(data)
    assert "composite_figi" in missing
    assert "share_class_figi" in missing
    assert "last_updated_utc" in missing
    assert "delisted_utc" in missing
    assert "ticker" not in missing
    assert "name" not in missing


def test_reference_default_idempotency_key() -> str:
    key = compute_reference_default_idempotency_key("2026-08-30", CaptureSlot.EVENING, "abcdef0123456789extra")
    assert key == "pit-reference-2026-08-30-evening-abcdef0123456789"
