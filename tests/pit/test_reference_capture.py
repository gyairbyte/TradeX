"""Deterministic tests for prospective point-in-time reference capture orchestration."""
from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from typing import Any

import pytest

from tradex.config import TradeXSettings
from tradex.market.hours import MARKET_TIMEZONE
from tradex.pit.massive_reference import MassiveObservationResult
from tradex.pit.models import (
    CaptureRunStatus,
    CaptureSlot,
    ReferenceObservationStatus,
    build_ambiguous_reference_fact_payload,
    build_error_reference_fact_payload,
    build_known_reference_fact_payload,
    build_unavailable_reference_fact_payload,
    compute_fact_hash,
    serialize_canonical_fact_json,
)
from tradex.pit.reference import capture_reference_snapshot
from tradex.pit.store import (
    PITIdempotencyConflictError,
)

NOW_EVENING = datetime(2026, 8, 30, 20, 35, 0, tzinfo=MARKET_TIMEZONE).astimezone(UTC)


def _make_fake_lookup_fn(
    data_map: dict[str, dict[str, Any] | str],
    call_log: list[str] | None = None,
):
    def fake_lookup(symbol: str, pit_date: date, settings: TradeXSettings | None = None) -> MassiveObservationResult:
        if call_log is not None:
            call_log.append(symbol)

        entry = data_map.get(symbol)
        if entry is None or entry == "unavailable":
            fact_payload = build_unavailable_reference_fact_payload(
                ticker=symbol,
                error_category="MassiveDataUnavailableError",
                error_message=f"No record for {symbol}",
            )
            fact_json = serialize_canonical_fact_json(fact_payload)
            return MassiveObservationResult(
                observation_status=ReferenceObservationStatus.UNAVAILABLE,
                symbol=symbol,
                query_date=pit_date,
                request_ids=(f"req-{symbol}-1",),
                provider_ticker=None,
                provider_name=None,
                provider_market=None,
                provider_locale=None,
                provider_active=None,
                provider_type_code=None,
                provider_primary_exchange=None,
                provider_cik=None,
                provider_composite_figi=None,
                provider_share_class_figi=None,
                provider_last_updated_at=None,
                provider_delisted_at=None,
                missing_fields=(),
                fact_hash=compute_fact_hash(fact_json),
                fact_json=fact_json,
                error_category="MassiveDataUnavailableError",
                error_message=f"No record for {symbol}",
            )

        if entry == "ambiguous":
            candidates = [
                {"ticker": symbol, "name": f"{symbol} A", "cik": "0001"},
                {"ticker": symbol, "name": f"{symbol} B", "cik": "0002"},
            ]
            fact_payload = build_ambiguous_reference_fact_payload(
                ticker=symbol,
                candidates=candidates,
            )
            fact_json = serialize_canonical_fact_json(fact_payload)
            return MassiveObservationResult(
                observation_status=ReferenceObservationStatus.AMBIGUOUS,
                symbol=symbol,
                query_date=pit_date,
                request_ids=(f"req-{symbol}-ambig",),
                provider_ticker=None,
                provider_name=None,
                provider_market=None,
                provider_locale=None,
                provider_active=None,
                provider_type_code=None,
                provider_primary_exchange=None,
                provider_cik=None,
                provider_composite_figi=None,
                provider_share_class_figi=None,
                provider_last_updated_at=None,
                provider_delisted_at=None,
                missing_fields=(),
                fact_hash=compute_fact_hash(fact_json),
                fact_json=fact_json,
                error_category="MassiveAmbiguousIdentityError",
                error_message=f"Multiple records for {symbol}",
            )

        if entry == "error":
            fact_payload = build_error_reference_fact_payload(
                ticker=symbol,
                error_category="MassiveTransientError",
                error_message=f"Provider timeout for {symbol}",
            )
            fact_json = serialize_canonical_fact_json(fact_payload)
            return MassiveObservationResult(
                observation_status=ReferenceObservationStatus.ERROR,
                symbol=symbol,
                query_date=pit_date,
                request_ids=(f"req-{symbol}-err",),
                provider_ticker=None,
                provider_name=None,
                provider_market=None,
                provider_locale=None,
                provider_active=None,
                provider_type_code=None,
                provider_primary_exchange=None,
                provider_cik=None,
                provider_composite_figi=None,
                provider_share_class_figi=None,
                provider_last_updated_at=None,
                provider_delisted_at=None,
                missing_fields=(),
                fact_hash=compute_fact_hash(fact_json),
                fact_json=fact_json,
                error_category="MassiveTransientError",
                error_message=f"Provider timeout for {symbol}",
            )

        # Known dict
        assert isinstance(entry, dict)
        last_upd = datetime.fromisoformat(entry["last_updated_utc"]) if entry.get("last_updated_utc") else None
        fact_payload = build_known_reference_fact_payload(
            active=entry.get("active"),
            cik=entry.get("cik"),
            composite_figi=entry.get("composite_figi"),
            delisted_utc=entry.get("delisted_utc"),
            last_updated_utc=entry.get("last_updated_utc"),
            locale=entry.get("locale"),
            market=entry.get("market"),
            name=entry.get("name"),
            primary_exchange=entry.get("primary_exchange"),
            share_class_figi=entry.get("share_class_figi"),
            ticker=entry.get("ticker", symbol),
            type_code=entry.get("type"),
        )
        fact_json = serialize_canonical_fact_json(fact_payload)
        missing_f = tuple(sorted([k for k in ("composite_figi", "share_class_figi", "delisted_utc") if not entry.get(k)]))

        return MassiveObservationResult(
            observation_status=ReferenceObservationStatus.KNOWN,
            symbol=symbol,
            query_date=pit_date,
            request_ids=(f"req-{symbol}-ok",),
            provider_ticker=entry.get("ticker", symbol),
            provider_name=entry.get("name"),
            provider_market=entry.get("market"),
            provider_locale=entry.get("locale"),
            provider_active=entry.get("active"),
            provider_type_code=entry.get("type"),
            provider_primary_exchange=entry.get("primary_exchange"),
            provider_cik=entry.get("cik"),
            provider_composite_figi=entry.get("composite_figi"),
            provider_share_class_figi=entry.get("share_class_figi"),
            provider_last_updated_at=last_upd,
            provider_delisted_at=entry.get("delisted_utc"),
            missing_fields=missing_f,
            fact_hash=compute_fact_hash(fact_json),
            fact_json=fact_json,
            error_category=None,
            error_message=None,
        )
    return fake_lookup


def test_all_known_run_succeeds(tmp_path) -> None:
    db_path = tmp_path / "test_success.db"
    now_dt = NOW_EVENING  # evening after 20:30 ET

    data_map = {
        "AAPL": {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "market": "stocks",
            "locale": "us",
            "active": True,
            "type": "CS",
            "primary_exchange": "XNAS",
            "cik": "0000320193",
            "composite_figi": "FIGI_AAPL",
            "share_class_figi": "FIGI_SC_AAPL",
            "last_updated_utc": "2026-08-29T20:00:00Z",
            "delisted_utc": None,
        },
        "MSFT": {
            "ticker": "MSFT",
            "name": "Microsoft Corp",
            "market": "stocks",
            "locale": "us",
            "active": True,
            "type": "CS",
            "primary_exchange": "XNAS",
            "cik": "0000789019",
            "composite_figi": "FIGI_MSFT",
            "share_class_figi": "FIGI_SC_MSFT",
            "last_updated_utc": "2026-08-29T20:00:00Z",
            "delisted_utc": None,
        },
    }

    call_log: list[str] = []
    fake_lookup = _make_fake_lookup_fn(data_map, call_log=call_log)

    res = capture_reference_snapshot(
        symbols=["AAPL", "MSFT"],
        slot=CaptureSlot.EVENING,
        capture_date=date(2026, 8, 30),
        db_path=db_path,
        now_fn=lambda: now_dt,
        reference_lookup=fake_lookup,
    )

    assert res.run.status == CaptureRunStatus.SUCCEEDED
    assert res.run.requested_n == 2
    assert res.run.known_n == 2
    assert res.run.unavailable_n == 0
    assert res.run.ambiguous_n == 0
    assert res.run.error_n == 0
    assert len(res.snapshots) == 2
    assert res.snapshots[0].symbol == "AAPL"
    assert res.snapshots[1].symbol == "MSFT"
    assert call_log == ["AAPL", "MSFT"]


def test_mixed_known_and_unavailable_yields_partial(tmp_path) -> None:
    db_path = tmp_path / "test_partial.db"
    now_dt = NOW_EVENING

    data_map = {
        "AAPL": {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "market": "stocks",
            "active": True,
            "type": "CS",
        },
        "UNKNOWN": "unavailable",
    }

    res = capture_reference_snapshot(
        symbols=["AAPL", "UNKNOWN"],
        slot=CaptureSlot.EVENING,
        capture_date=date(2026, 8, 30),
        db_path=db_path,
        now_fn=lambda: now_dt,
        reference_lookup=_make_fake_lookup_fn(data_map),
    )

    assert res.run.status == CaptureRunStatus.PARTIAL
    assert res.run.known_n == 1
    assert res.run.unavailable_n == 1
    assert res.run.ambiguous_n == 0
    assert res.run.error_n == 0


def test_known_and_ambiguous_yields_partial(tmp_path) -> None:
    db_path = tmp_path / "test_ambig_partial.db"
    now_dt = NOW_EVENING

    data_map = {
        "AAPL": {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "market": "stocks",
            "active": True,
            "type": "CS",
        },
        "AMBIG": "ambiguous",
    }

    res = capture_reference_snapshot(
        symbols=["AAPL", "AMBIG"],
        slot=CaptureSlot.EVENING,
        capture_date=date(2026, 8, 30),
        db_path=db_path,
        now_fn=lambda: now_dt,
        reference_lookup=_make_fake_lookup_fn(data_map),
    )

    assert res.run.status == CaptureRunStatus.PARTIAL
    assert res.run.known_n == 1
    assert res.run.ambiguous_n == 1
    assert res.run.unavailable_n == 0
    assert res.run.error_n == 0


def test_zero_known_yields_failed(tmp_path) -> None:
    db_path = tmp_path / "test_failed.db"
    now_dt = NOW_EVENING

    data_map = {
        "SYM1": "unavailable",
        "SYM2": "error",
    }

    res = capture_reference_snapshot(
        symbols=["SYM1", "SYM2"],
        slot=CaptureSlot.EVENING,
        capture_date=date(2026, 8, 30),
        db_path=db_path,
        now_fn=lambda: now_dt,
        reference_lookup=_make_fake_lookup_fn(data_map),
    )

    assert res.run.status == CaptureRunStatus.FAILED
    assert res.run.known_n == 0
    assert res.run.unavailable_n == 1
    assert res.run.error_n == 1


def test_provider_otc_field_preserved(tmp_path) -> None:
    db_path = tmp_path / "test_otc.db"
    now_dt = NOW_EVENING

    data_map = {
        "OTCP": {
            "ticker": "OTCP",
            "name": "OTC Security",
            "market": "otc",
            "locale": "us",
            "active": True,
            "type": "CS",
            "primary_exchange": "OTCM",
        }
    }

    res = capture_reference_snapshot(
        symbols=["OTCP"],
        slot=CaptureSlot.EVENING,
        capture_date=date(2026, 8, 30),
        db_path=db_path,
        now_fn=lambda: now_dt,
        reference_lookup=_make_fake_lookup_fn(data_map),
    )

    assert res.run.status == CaptureRunStatus.SUCCEEDED
    assert res.snapshots[0].provider_market == "otc"
    assert res.snapshots[0].provider_primary_exchange == "OTCM"


def test_exact_replay_makes_zero_provider_calls(tmp_path) -> None:
    db_path = tmp_path / "test_replay.db"
    now_dt = NOW_EVENING

    data_map = {
        "AAPL": {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "market": "stocks",
            "active": True,
            "type": "CS",
        }
    }

    call_log: list[str] = []
    fake_lookup = _make_fake_lookup_fn(data_map, call_log=call_log)

    res1 = capture_reference_snapshot(
        symbols=["AAPL"],
        slot=CaptureSlot.EVENING,
        capture_date=date(2026, 8, 30),
        db_path=db_path,
        now_fn=lambda: now_dt,
        reference_lookup=fake_lookup,
    )
    assert call_log == ["AAPL"]

    # Replay identical request
    res2 = capture_reference_snapshot(
        symbols=["AAPL"],
        slot=CaptureSlot.EVENING,
        capture_date=date(2026, 8, 30),
        db_path=db_path,
        now_fn=lambda: now_dt,
        reference_lookup=fake_lookup,
    )

    assert call_log == ["AAPL"]  # Zero extra calls
    assert res2.run.capture_run_id == res1.run.capture_run_id
    assert len(res2.snapshots) == 1
    assert res2.snapshots[0].snapshot_id == res1.snapshots[0].snapshot_id


def test_divergent_replay_raises_conflict(tmp_path) -> None:
    db_path = tmp_path / "test_divergent.db"
    now_dt = NOW_EVENING

    data_map = {
        "AAPL": {"ticker": "AAPL", "name": "Apple Inc.", "active": True},
        "MSFT": {"ticker": "MSFT", "name": "Microsoft Corp", "active": True},
    }

    fake_lookup = _make_fake_lookup_fn(data_map)

    # First call with explicit idempotency key
    capture_reference_snapshot(
        symbols=["AAPL"],
        slot=CaptureSlot.EVENING,
        capture_date=date(2026, 8, 30),
        idempotency_key="my-custom-key-001",
        db_path=db_path,
        now_fn=lambda: now_dt,
        reference_lookup=fake_lookup,
    )

    # Second call with same idempotency key but different symbols
    with pytest.raises(PITIdempotencyConflictError, match="divergent request fingerprint"):
        capture_reference_snapshot(
            symbols=["MSFT"],
            slot=CaptureSlot.EVENING,
            capture_date=date(2026, 8, 30),
            idempotency_key="my-custom-key-001",
            db_path=db_path,
            now_fn=lambda: now_dt,
            reference_lookup=fake_lookup,
        )


def test_immediate_persistence_and_interruption_survival(tmp_path) -> None:
    db_path = tmp_path / "test_crash.db"
    now_dt = NOW_EVENING

    def failing_lookup(symbol: str, pit_date: date, settings: TradeXSettings | None = None) -> MassiveObservationResult:
        if symbol == "FAIL":
            raise KeyboardInterrupt("Simulated fatal crash during provider retrieval")
        return _make_fake_lookup_fn({"AAPL": {"ticker": "AAPL", "name": "Apple Inc.", "active": True}})(symbol, pit_date, settings)

    with pytest.raises(KeyboardInterrupt, match="Simulated fatal crash"):
        capture_reference_snapshot(
            symbols=["AAPL", "FAIL"],
            slot=CaptureSlot.EVENING,
            capture_date=date(2026, 8, 30),
            db_path=db_path,
            now_fn=lambda: now_dt,
            reference_lookup=failing_lookup,
        )

    # Check that the run remains 'started' and AAPL snapshot was persisted immediately
    with sqlite3.connect(str(db_path)) as con:
        con.row_factory = sqlite3.Row
        run_row = con.execute("SELECT * FROM pit_reference_capture_runs").fetchone()
        assert run_row is not None
        assert run_row["status"] == "started"
        assert run_row["completed_at"] is None

        snap_rows = con.execute("SELECT * FROM pit_reference_snapshots").fetchall()
        assert len(snap_rows) == 1
        assert snap_rows[0]["symbol"] == "AAPL"


def test_db_write_boundary_only_writes_reference_tables(tmp_path) -> None:
    db_path = tmp_path / "write_boundary.db"
    now_dt = NOW_EVENING

    data_map = {
        "AAPL": {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "market": "stocks",
            "active": True,
            "type": "CS",
        }
    }

    capture_reference_snapshot(
        symbols=["AAPL"],
        slot=CaptureSlot.EVENING,
        capture_date=date(2026, 8, 30),
        db_path=db_path,
        now_fn=lambda: now_dt,
        reference_lookup=_make_fake_lookup_fn(data_map),
    )

    with sqlite3.connect(str(db_path)) as con:
        # Reference tables received exactly 1 run and 1 snapshot
        assert con.execute("SELECT COUNT(*) FROM pit_reference_capture_runs").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM pit_reference_snapshots").fetchone()[0] == 1

        # All other production tables have ZERO rows
        assert con.execute("SELECT COUNT(*) FROM signal_history").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM scan_sessions").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM scan_observations").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM candidate_evaluations").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM candidate_evidence").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM candidate_reasons").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM candidate_missing_data").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM journal_trades").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM journal_events").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM journal_outcomes").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM pit_capture_runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM pit_earnings_snapshots").fetchone()[0] == 0


def test_early_capture_before_slot_is_rejected(tmp_path) -> None:
    db_path = tmp_path / "early.db"
    early_dt = datetime(2026, 8, 30, 19, 0, tzinfo=UTC)  # 15:00 ET, before 20:30 ET

    with pytest.raises(ValueError, match="is before scheduled slot time"):
        capture_reference_snapshot(
            symbols=["AAPL"],
            slot=CaptureSlot.EVENING,
            capture_date=date(2026, 8, 30),
            db_path=db_path,
            now_fn=lambda: early_dt,
            reference_lookup=_make_fake_lookup_fn({}),
        )
