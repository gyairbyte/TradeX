"""Tests for run_pit_slot: trading-day policy, drift guard, family isolation, same-universe invariant (MVP-ARCH-001-R7-PIT-001C1)."""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tradex.config import settings_from_mapping
from tradex.pit.models import (
    CaptureRunStatus,
    CaptureSlot,
    PITCaptureResult,
    PITCaptureRun,
    PITReferenceCaptureResult,
    PITReferenceCaptureRun,
)
from tradex.pit.ops import (
    PITOperationalStatus,
    PITOperationalUniverseConflictError,
    PITUniverseManifest,
    _check_universe_drift,
    run_pit_slot,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures and helpers
# ─────────────────────────────────────────────────────────────────────────────

# A known NYSE trading day (Wednesday 2026-09-02 — but we just need a valid XNYS date)
# Use 2026-01-02 (Friday); we'll patch is_trading_day where needed.
_TRADING_DATE = date(2026, 1, 2)
_NON_TRADING_DATE = date(2026, 1, 3)  # Saturday

def _manifest(symbols=("AAPL", "MSFT"), uid="test-universe", eff=None) -> PITUniverseManifest:
    return PITUniverseManifest(
        contract_version=1,
        universe_id=uid,
        universe_version="v1",
        effective_from=eff or date(2025, 1, 1),
        symbols=symbols,
        description="test",
    )


def _settings(tmp_path: Path):
    return settings_from_mapping({"TRADEX_DB_PATH": str(tmp_path / "signals.db")})


def _morning_now(d: date) -> datetime:
    """Return a time after 09:00 ET for the given date (14:30 UTC in winter = 09:30 ET = EST UTC-5)."""
    return datetime(d.year, d.month, d.day, 14, 30, tzinfo=UTC)


def _evening_now(d: date) -> datetime:
    """Return a time after 20:30 ET for the given date (01:00 UTC next day in winter)."""
    # 20:30 ET = 01:30 UTC next day (EST, UTC-5)
    return datetime(d.year, d.month, d.day, 21, 0, tzinfo=UTC)


def _before_morning_now(d: date) -> datetime:
    """Return a time BEFORE 09:00 ET — before the morning slot (13:30 UTC = 08:30 ET in winter)."""
    return datetime(d.year, d.month, d.day, 13, 30, tzinfo=UTC)


def _build_earnings_run(run_id: str, manifest: PITUniverseManifest) -> PITCaptureRun:
    from tradex.pit.models import PIT_CAPTURE_CONTRACT_VERSION, CaptureKind
    now = datetime(2026, 1, 2, 13, 30, tzinfo=UTC)
    return PITCaptureRun(
        capture_run_id=run_id,
        idempotency_key=f"pit-earnings-2026-01-02-morning-{run_id[:16]}",
        request_fingerprint="a" * 64,
        capture_kind=CaptureKind.EARNINGS,
        capture_slot=CaptureSlot.MORNING,
        capture_date=_TRADING_DATE,
        scheduled_for=datetime(2026, 1, 2, 14, 0, tzinfo=UTC),
        requested_at=now,
        completed_at=now,
        requested_provider="yahoo",
        universe_hash=manifest.universe_hash,
        requested_n=len(manifest.symbols),
        known_n=len(manifest.symbols),
        unavailable_n=0,
        error_n=0,
        status=CaptureRunStatus.SUCCEEDED,
        created_at=now,
        updated_at=now,
        contract_version=PIT_CAPTURE_CONTRACT_VERSION,
    )


def _earnings_result_succeeded(run_id: str, manifest: PITUniverseManifest) -> PITCaptureResult:
    run = _build_earnings_run(run_id, manifest)
    return PITCaptureResult(run=run, snapshots=())


def _reference_result_succeeded(run_id: str, manifest: PITUniverseManifest) -> PITReferenceCaptureResult:
    from tradex.pit.models import PIT_CAPTURE_CONTRACT_VERSION
    now = datetime(2026, 1, 2, 13, 30, tzinfo=UTC)
    run = PITReferenceCaptureRun(
        capture_run_id=run_id,
        idempotency_key=f"pit-reference-2026-01-02-morning-{run_id[:16]}",
        request_fingerprint="b" * 64,
        capture_slot=CaptureSlot.MORNING,
        capture_date=_TRADING_DATE,
        scheduled_for=datetime(2026, 1, 2, 14, 0, tzinfo=UTC),
        requested_at=now,
        completed_at=now,
        requested_provider="massive",
        universe_hash=manifest.universe_hash,
        requested_n=len(manifest.symbols),
        known_n=len(manifest.symbols),
        unavailable_n=0,
        ambiguous_n=0,
        error_n=0,
        status=CaptureRunStatus.SUCCEEDED,
        created_at=now,
        updated_at=now,
        contract_version=PIT_CAPTURE_CONTRACT_VERSION,
    )
    return PITReferenceCaptureResult(run=run, snapshots=())


# ─────────────────────────────────────────────────────────────────────────────
# Trading-day gate
# ─────────────────────────────────────────────────────────────────────────────

class TestRunPitSlotTradingDayGate:
    def test_non_trading_day_returns_not_due(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)

        # Saturday
        saturday = date(2026, 1, 3)

        with patch("tradex.pit.ops.is_trading_day", return_value=False):
            result = run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=manifest,
                settings=settings,
                db_path=tmp_path / "signals.db",
                now_fn=lambda: _morning_now(saturday),
            )

        assert result.operational_status == PITOperationalStatus.NOT_DUE
        assert result.earnings.capture_run_id is None
        assert result.reference.capture_run_id is None

    def test_non_trading_day_no_provider_calls(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        saturday = date(2026, 1, 3)

        mock_earnings = MagicMock(side_effect=AssertionError("Should not be called"))
        mock_reference = MagicMock(side_effect=AssertionError("Should not be called"))

        with patch("tradex.pit.ops.is_trading_day", return_value=False):
            result = run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=manifest,
                settings=settings,
                db_path=tmp_path / "signals.db",
                now_fn=lambda: _morning_now(saturday),
                earnings_capture=mock_earnings,
                reference_capture=mock_reference,
            )

        assert result.operational_status == PITOperationalStatus.NOT_DUE

    def test_before_slot_returns_not_due(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        d = _TRADING_DATE

        mock_earnings = MagicMock(side_effect=AssertionError("Should not be called"))
        mock_reference = MagicMock(side_effect=AssertionError("Should not be called"))

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            result = run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=manifest,
                settings=settings,
                db_path=tmp_path / "signals.db",
                now_fn=lambda: _before_morning_now(d),
                earnings_capture=mock_earnings,
                reference_capture=mock_reference,
            )

        assert result.operational_status == PITOperationalStatus.NOT_DUE


# ─────────────────────────────────────────────────────────────────────────────
# Manifest effective_from gate
# ─────────────────────────────────────────────────────────────────────────────

class TestRunPitSlotEffectiveFrom:
    def test_future_effective_from_returns_failed(self, tmp_path):
        manifest = _manifest(eff=date(2099, 1, 1))
        settings = _settings(tmp_path)
        d = _TRADING_DATE

        mock_earnings = MagicMock(side_effect=AssertionError("Should not be called"))
        mock_reference = MagicMock(side_effect=AssertionError("Should not be called"))

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            result = run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=manifest,
                settings=settings,
                db_path=tmp_path / "signals.db",
                now_fn=lambda: _morning_now(d),
                earnings_capture=mock_earnings,
                reference_capture=mock_reference,
            )

        assert result.operational_status == PITOperationalStatus.FAILED
        assert result.earnings.error_detail is not None
        assert "effective_from" in result.earnings.error_detail

    def test_past_effective_from_proceeds(self, tmp_path):
        manifest = _manifest(eff=date(2020, 1, 1))
        settings = _settings(tmp_path)
        d = _TRADING_DATE

        e_res = _earnings_result_succeeded("e-run-001", manifest)
        r_res = _reference_result_succeeded("r-run-001", manifest)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            result = run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=manifest,
                settings=settings,
                db_path=tmp_path / "signals.db",
                now_fn=lambda: _morning_now(d),
                earnings_capture=lambda **kw: e_res,
                reference_capture=lambda **kw: r_res,
            )

        assert result.operational_status == PITOperationalStatus.SUCCEEDED


# ─────────────────────────────────────────────────────────────────────────────
# Universe drift guard
# ─────────────────────────────────────────────────────────────────────────────

class TestUniverseDriftGuard:
    def test_conflict_on_existing_different_hash(self, tmp_path):
        """Existing run with different universe_hash raises PITOperationalUniverseConflictError."""
        from tradex.pit.models import PIT_CAPTURE_CONTRACT_VERSION, CaptureKind
        from tradex.pit.store import create_capture_run
        from tradex.tracker.store import init as store_init

        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"
        store_init(db_path=db_path, settings=settings)

        # Create an existing run with a DIFFERENT universe hash
        old_manifest = _manifest(symbols=("AAPL",))  # different from ("AAPL", "MSFT")
        now = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
        old_run = PITCaptureRun(
            capture_run_id="old-run",
            idempotency_key="pit-earnings-2026-01-02-morning-oldrn",
            request_fingerprint="c" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=_TRADING_DATE,
            scheduled_for=now,
            requested_at=now,
            completed_at=now,
            requested_provider="yahoo",
            universe_hash=old_manifest.universe_hash,
            requested_n=1,
            known_n=1,
            unavailable_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=now,
            updated_at=now,
            contract_version=PIT_CAPTURE_CONTRACT_VERSION,
        )
        create_capture_run(old_run, db_path=db_path, settings=settings)

        # New manifest with a different universe
        new_manifest = _manifest(symbols=("AAPL", "MSFT"))
        assert new_manifest.universe_hash != old_manifest.universe_hash

        with pytest.raises(PITOperationalUniverseConflictError) as exc_info:
            _check_universe_drift(
                _TRADING_DATE,
                CaptureSlot.MORNING,
                new_manifest.universe_hash,
                db_path=db_path,
                settings=settings,
            )
        assert exc_info.value.family == "earnings"

    def test_no_conflict_when_hash_matches(self, tmp_path):
        """No exception when existing run has the same universe hash."""
        from tradex.pit.models import PIT_CAPTURE_CONTRACT_VERSION, CaptureKind
        from tradex.pit.store import create_capture_run
        from tradex.tracker.store import init as store_init

        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"
        store_init(db_path=db_path, settings=settings)

        manifest = _manifest(symbols=("AAPL", "MSFT"))
        now = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
        run = PITCaptureRun(
            capture_run_id="match-run",
            idempotency_key="pit-earnings-2026-01-02-morning-matchrn",
            request_fingerprint="d" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=_TRADING_DATE,
            scheduled_for=now,
            requested_at=now,
            completed_at=now,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=now,
            updated_at=now,
            contract_version=PIT_CAPTURE_CONTRACT_VERSION,
        )
        create_capture_run(run, db_path=db_path, settings=settings)

        # Should not raise
        _check_universe_drift(
            _TRADING_DATE,
            CaptureSlot.MORNING,
            manifest.universe_hash,
            db_path=db_path,
            settings=settings,
        )

    def test_drift_guard_returns_failed_result(self, tmp_path):
        """run_pit_slot returns failed (not raises) when drift is detected."""
        from tradex.pit.models import PIT_CAPTURE_CONTRACT_VERSION, CaptureKind
        from tradex.pit.store import create_capture_run
        from tradex.tracker.store import init as store_init

        settings = _settings(tmp_path)
        db_path = tmp_path / "signals.db"
        store_init(db_path=db_path, settings=settings)

        old_manifest = _manifest(symbols=("AAPL",))
        new_manifest = _manifest(symbols=("AAPL", "MSFT"))
        assert old_manifest.universe_hash != new_manifest.universe_hash

        now = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
        old_run = PITCaptureRun(
            capture_run_id="old-drift",
            idempotency_key="pit-earnings-2026-01-02-morning-drift0",
            request_fingerprint="e" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=_TRADING_DATE,
            scheduled_for=now,
            requested_at=now,
            completed_at=now,
            requested_provider="yahoo",
            universe_hash=old_manifest.universe_hash,
            requested_n=1,
            known_n=1,
            unavailable_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=now,
            updated_at=now,
            contract_version=PIT_CAPTURE_CONTRACT_VERSION,
        )
        create_capture_run(old_run, db_path=db_path, settings=settings)

        mock_earnings = MagicMock(side_effect=AssertionError("Should not be called"))
        mock_reference = MagicMock(side_effect=AssertionError("Should not be called"))

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            result = run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=new_manifest,
                settings=settings,
                db_path=db_path,
                now_fn=lambda: _morning_now(_TRADING_DATE),
                earnings_capture=mock_earnings,
                reference_capture=mock_reference,
            )

        assert result.operational_status == PITOperationalStatus.FAILED


# ─────────────────────────────────────────────────────────────────────────────
# Family isolation: reference runs even if earnings fails
# ─────────────────────────────────────────────────────────────────────────────

class TestFamilyIsolation:
    def test_reference_runs_even_if_earnings_raises(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        d = _TRADING_DATE

        r_res = _reference_result_succeeded("r-run-isolation", manifest)

        def _fail_earnings(**kw):
            raise RuntimeError("Earnings provider down")

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            result = run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=manifest,
                settings=settings,
                db_path=tmp_path / "signals.db",
                now_fn=lambda: _morning_now(d),
                earnings_capture=_fail_earnings,
                reference_capture=lambda **kw: r_res,
            )

        assert result.earnings.capture_run_id is None
        assert result.earnings.error_detail is not None
        assert result.reference.capture_run_id == "r-run-isolation"
        assert result.operational_status == PITOperationalStatus.DEGRADED

    def test_earnings_runs_even_if_reference_fails(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        d = _TRADING_DATE

        e_res = _earnings_result_succeeded("e-run-isolated", manifest)

        def _fail_reference(**kw):
            raise RuntimeError("Reference provider down")

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            result = run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=manifest,
                settings=settings,
                db_path=tmp_path / "signals.db",
                now_fn=lambda: _morning_now(d),
                earnings_capture=lambda **kw: e_res,
                reference_capture=_fail_reference,
            )

        assert result.reference.capture_run_id is None
        assert result.reference.error_detail is not None
        assert result.earnings.capture_run_id == "e-run-isolated"
        assert result.operational_status == PITOperationalStatus.DEGRADED

    def test_both_fail_returns_failed(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        d = _TRADING_DATE

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            result = run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=manifest,
                settings=settings,
                db_path=tmp_path / "signals.db",
                now_fn=lambda: _morning_now(d),
                earnings_capture=lambda **kw: (_ for _ in ()).throw(RuntimeError("e fail")),
                reference_capture=lambda **kw: (_ for _ in ()).throw(RuntimeError("r fail")),
            )

        assert result.operational_status == PITOperationalStatus.FAILED


# ─────────────────────────────────────────────────────────────────────────────
# Same-universe invariant
# ─────────────────────────────────────────────────────────────────────────────

class TestSameUniverseInvariant:
    def test_both_families_receive_same_symbols(self, tmp_path):
        """Earnings and reference capture are called with the same symbols tuple."""
        manifest = _manifest(symbols=("AAPL", "MSFT", "NVDA"))
        settings = _settings(tmp_path)
        d = _TRADING_DATE

        received_earnings_symbols = []
        received_reference_symbols = []

        def _capture_earnings(**kw):
            received_earnings_symbols.extend(kw.get("symbols", []))
            return _earnings_result_succeeded("e-inv", manifest)

        def _capture_reference(**kw):
            received_reference_symbols.extend(kw.get("symbols", []))
            return _reference_result_succeeded("r-inv", manifest)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            result = run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=manifest,
                settings=settings,
                db_path=tmp_path / "signals.db",
                now_fn=lambda: _morning_now(d),
                earnings_capture=_capture_earnings,
                reference_capture=_capture_reference,
            )

        assert tuple(received_earnings_symbols) == manifest.symbols
        assert tuple(received_reference_symbols) == manifest.symbols
        assert result.universe_hash == manifest.universe_hash
        assert result.operational_status == PITOperationalStatus.SUCCEEDED


# ─────────────────────────────────────────────────────────────────────────────
# Result metadata
# ─────────────────────────────────────────────────────────────────────────────

class TestRunPitSlotResultMetadata:
    def test_result_contains_manifest_metadata(self, tmp_path):
        manifest = _manifest(uid="meta-universe")
        settings = _settings(tmp_path)
        d = _TRADING_DATE

        e_res = _earnings_result_succeeded("e-meta", manifest)
        r_res = _reference_result_succeeded("r-meta", manifest)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            result = run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=manifest,
                settings=settings,
                db_path=tmp_path / "signals.db",
                now_fn=lambda: _morning_now(d),
                earnings_capture=lambda **kw: e_res,
                reference_capture=lambda **kw: r_res,
            )

        assert result.universe_id == "meta-universe"
        assert result.universe_version == manifest.universe_version
        assert result.manifest_hash == manifest.manifest_hash
        assert result.universe_hash == manifest.universe_hash
        assert result.symbol_count == len(manifest.symbols)
        assert result.slot == CaptureSlot.MORNING
        assert result.contract_version == 1


# ─────────────────────────────────────────────────────────────────────────────
# 1. Real End-to-End Exact Replay Test (Section 1)
# ─────────────────────────────────────────────────────────────────────────────

class TestRealEndToEndExactReplay:
    """End-to-end integration test with real run_pit_slot and real capture functions.

    Proves that running twice on the exact same date, slot, and manifest results in:
    - Same earnings run ID and reference run ID
    - Zero additional provider calls
    - Zero duplicate snapshots or runs
    - Fully deterministic result
    """

    def test_exact_replay_idempotency(self, tmp_path):
        from tradex.pit.earnings import capture_earnings_snapshot
        from tradex.pit.massive_reference import MassiveObservationResult
        from tradex.pit.models import (
            ReferenceObservationStatus,
            build_known_reference_fact_payload,
            compute_fact_hash,
            serialize_canonical_fact_json,
        )
        from tradex.pit.reference import capture_reference_snapshot
        from tradex.pit.store import (
            list_earnings_capture_runs,
            list_earnings_snapshots,
            list_reference_capture_runs,
            list_reference_snapshots,
        )

        db_path = tmp_path / "signals.db"
        settings = _settings(tmp_path)
        manifest = _manifest(symbols=("AAPL", "MSFT"), eff=date(2025, 1, 1))

        # Friday 2026-01-02 (trading day), slot morning (09:00 ET = 14:00 UTC)
        slot_dt = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
        now_fn = lambda: slot_dt

        yahoo_calls = 0
        massive_calls = 0

        def fake_yahoo_lookup(symbol: str, source: str = "yahoo", settings=None):
            nonlocal yahoo_calls
            yahoo_calls += 1
            return date(2026, 2, 1)

        def _make_fake_ref_result(symbol: str, query_date: date):
            fact_payload = build_known_reference_fact_payload(
                ticker=symbol,
                name=f"{symbol} Corp",
                market="stocks",
                locale="us",
                active=True,
                type_code="CS",
                primary_exchange="XNAS",
                cik="0000000000",
                composite_figi="BBG000000000",
                share_class_figi="BBG000000001",
                last_updated_utc=None,
                delisted_utc=None,
            )
            fact_json = serialize_canonical_fact_json(fact_payload)
            fact_hash = compute_fact_hash(fact_json)
            return MassiveObservationResult(
                observation_status=ReferenceObservationStatus.KNOWN,
                symbol=symbol,
                query_date=query_date,
                request_ids=(f"req-{symbol}",),
                provider_ticker=symbol,
                provider_name=f"{symbol} Corp",
                provider_market="stocks",
                provider_locale="us",
                provider_active=True,
                provider_type_code="CS",
                provider_primary_exchange="XNAS",
                provider_cik="0000000000",
                provider_composite_figi="BBG000000000",
                provider_share_class_figi="BBG000000001",
                provider_last_updated_at=None,
                provider_delisted_at=None,
                missing_fields=(),
                fact_hash=fact_hash,
                fact_json=fact_json,
                error_category=None,
                error_message=None,
            )

        class FakeMassiveClient:
            def fetch_ticker_reference(self, symbol: str, query_date: date) -> MassiveObservationResult:
                nonlocal massive_calls
                massive_calls += 1
                return _make_fake_ref_result(symbol, query_date)

        def wrapped_earnings(**kw):
            return capture_earnings_snapshot(**kw, earnings_lookup=fake_yahoo_lookup)

        def wrapped_reference(**kw):
            return capture_reference_snapshot(**kw, client=FakeMassiveClient())


        # ── First Execution ──
        res1 = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            db_path=db_path,
            now_fn=now_fn,
            earnings_capture=wrapped_earnings,
            reference_capture=wrapped_reference,
        )

        assert res1.operational_status == PITOperationalStatus.SUCCEEDED
        assert res1.earnings.status == CaptureRunStatus.SUCCEEDED
        assert res1.reference.status == CaptureRunStatus.SUCCEEDED
        assert res1.earnings.capture_run_id is not None
        assert res1.reference.capture_run_id is not None

        # Provider calls for 2 symbols
        assert yahoo_calls == 2
        assert massive_calls == 2

        # Verify DB counts
        e_runs1 = list_earnings_capture_runs(date(2026, 1, 2), CaptureSlot.MORNING, db_path=db_path, settings=settings)
        r_runs1 = list_reference_capture_runs(date(2026, 1, 2), CaptureSlot.MORNING, db_path=db_path, settings=settings)
        assert len(e_runs1) == 1
        assert len(r_runs1) == 1

        e_snaps1 = list_earnings_snapshots(res1.earnings.capture_run_id, db_path=db_path, settings=settings)
        r_snaps1 = list_reference_snapshots(res1.reference.capture_run_id, db_path=db_path, settings=settings)
        assert len(e_snaps1) == 2
        assert len(r_snaps1) == 2

        # ── Second Execution (Exact Replay) ──
        res2 = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            db_path=db_path,
            now_fn=now_fn,
            earnings_capture=wrapped_earnings,
            reference_capture=wrapped_reference,
        )

        # Proves identical run IDs returned
        assert res2.earnings.capture_run_id == res1.earnings.capture_run_id
        assert res2.reference.capture_run_id == res1.reference.capture_run_id
        assert res2.operational_status == PITOperationalStatus.SUCCEEDED

        # Proves zero additional provider calls
        assert yahoo_calls == 2
        assert massive_calls == 2

        # Proves zero duplicate runs or snapshots in DB
        e_runs2 = list_earnings_capture_runs(date(2026, 1, 2), CaptureSlot.MORNING, db_path=db_path, settings=settings)
        r_runs2 = list_reference_capture_runs(date(2026, 1, 2), CaptureSlot.MORNING, db_path=db_path, settings=settings)
        assert len(e_runs2) == 1
        assert len(r_runs2) == 1

        e_snaps2 = list_earnings_snapshots(res2.earnings.capture_run_id, db_path=db_path, settings=settings)
        r_snaps2 = list_reference_snapshots(res2.reference.capture_run_id, db_path=db_path, settings=settings)
        assert len(e_snaps2) == 2
        assert len(r_snaps2) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 2. Truthfully Report Runs Created Before Exception (Section 2)
# ─────────────────────────────────────────────────────────────────────────────

class TestTruthfulPostFailureRunReporting:
    def test_earnings_post_create_failure_surfaces_durable_started_run(self, tmp_path):
        """When earnings capture creates a run before throwing, C1 surfaces the durable run ID and STARTED status."""
        from tradex.pit.earnings import capture_earnings_snapshot
        from tradex.pit.store import list_earnings_capture_runs

        db_path = tmp_path / "signals.db"
        settings = _settings(tmp_path)
        manifest = _manifest(symbols=("AAPL",), eff=date(2025, 1, 1))

        # Clock moves backward between lookup start and end, raising ValueError after started_run is persisted
        clock_seq = [
            datetime(2026, 1, 2, 14, 30, 10, tzinfo=UTC),  # 1: run_pit_slot gate
            datetime(2026, 1, 2, 14, 30, 10, tzinfo=UTC),  # 2: capture_earnings_snapshot preflight
            datetime(2026, 1, 2, 14, 30, 20, tzinfo=UTC),  # 3: req_start
            datetime(2026, 1, 2, 14, 30, 5, tzinfo=UTC),   # 4: req_end < req_start -> ValueError
        ]
        seq_idx = 0

        def backwards_clock():
            nonlocal seq_idx
            val = clock_seq[min(seq_idx, len(clock_seq) - 1)]
            seq_idx += 1
            return val

        ref_mock = MagicMock(return_value=_reference_result_succeeded("r-ok", manifest))


        result = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            db_path=db_path,
            now_fn=backwards_clock,
            earnings_capture=lambda **kw: capture_earnings_snapshot(**kw, earnings_lookup=lambda s, **k: date(2026, 3, 1)),
            reference_capture=ref_mock,
        )

        # Earnings failed with controlled exception
        e_runs = list_earnings_capture_runs(date(2026, 1, 2), CaptureSlot.MORNING, db_path=db_path, settings=settings)
        assert len(e_runs) == 1
        persisted_run = e_runs[0]
        assert persisted_run.status == CaptureRunStatus.STARTED

        # C1 truthfully surfaces the persisted run ID and STARTED status
        assert result.earnings.capture_run_id == persisted_run.capture_run_id
        assert result.earnings.status == CaptureRunStatus.STARTED
        assert result.earnings.error_detail == "Earnings capture failed due to an internal error."

        # DB row was NOT mutated by C1
        e_runs_after = list_earnings_capture_runs(date(2026, 1, 2), CaptureSlot.MORNING, db_path=db_path, settings=settings)
        assert e_runs_after[0].status == CaptureRunStatus.STARTED

    def test_reference_post_create_failure_surfaces_durable_started_run(self, tmp_path):
        """When reference capture creates a run before throwing, C1 surfaces the durable run ID and STARTED status."""
        from tradex.pit.reference import capture_reference_snapshot
        from tradex.pit.store import list_reference_capture_runs

        db_path = tmp_path / "signals.db"
        settings = _settings(tmp_path)
        manifest = _manifest(symbols=("AAPL",), eff=date(2025, 1, 1))

        calls = 0
        def backwards_clock():
            nonlocal calls
            calls += 1
            if calls <= 3:
                return datetime(2026, 1, 2, 14, 30, 10, tzinfo=UTC)
            elif calls == 4:
                return datetime(2026, 1, 2, 14, 30, 20, tzinfo=UTC)  # req_start
            else:
                return datetime(2026, 1, 2, 14, 30, 5, tzinfo=UTC)   # req_end < req_start -> ValueError

        e_mock = MagicMock(return_value=_earnings_result_succeeded("e-ok", manifest))

        result = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            db_path=db_path,
            now_fn=backwards_clock,
            earnings_capture=e_mock,
            reference_capture=lambda **kw: capture_reference_snapshot(**kw, reference_lookup=lambda s, **k: None),
        )

        r_runs = list_reference_capture_runs(date(2026, 1, 2), CaptureSlot.MORNING, db_path=db_path, settings=settings)
        assert len(r_runs) == 1
        persisted_run = r_runs[0]
        assert persisted_run.status == CaptureRunStatus.STARTED

        assert result.reference.capture_run_id == persisted_run.capture_run_id
        assert result.reference.status == CaptureRunStatus.STARTED
        assert result.reference.error_detail == "Reference capture failed due to an internal error."

        # DB row was NOT mutated by C1
        r_runs_after = list_reference_capture_runs(date(2026, 1, 2), CaptureSlot.MORNING, db_path=db_path, settings=settings)
        assert r_runs_after[0].status == CaptureRunStatus.STARTED

    def test_base_exception_propagates_without_interception(self, tmp_path):
        """Genuine BaseException (e.g. KeyboardInterrupt) propagates truthfully and is not converted to a family result."""
        manifest = _manifest()
        settings = _settings(tmp_path)

        def interrupt_earnings(**kw):
            raise KeyboardInterrupt("Interrupted by user")

        with pytest.raises(KeyboardInterrupt, match="Interrupted by user"):
            run_pit_slot(
                slot=CaptureSlot.MORNING,
                universe_manifest=manifest,
                settings=settings,
                db_path=tmp_path / "signals.db",
                now_fn=lambda: _morning_now(_TRADING_DATE),
                earnings_capture=interrupt_earnings,
                reference_capture=MagicMock(),
            )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Secret-Safe Error Detail (Section 3)
# ─────────────────────────────────────────────────────────────────────────────

class TestSecretSafeFamilyFailure:
    def test_secrets_never_leak_in_operational_result_or_json(self, tmp_path):
        """Prove that sensitive tokens/paths are completely absent from operational result and serialized JSON."""
        import json

        from tradex.pit.ops import _build_run_slot_output

        manifest = _manifest()
        settings = _settings(tmp_path)

        secret_text = "token=SUPERSECRET123 apiKey=KEY999 C:\\Users\\Gary\\private\\credentials.txt"

        def leaking_earnings(**kw):
            raise RuntimeError(secret_text)

        def leaking_reference(**kw):
            raise RuntimeError(secret_text)

        result = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            db_path=tmp_path / "signals.db",
            now_fn=lambda: _morning_now(_TRADING_DATE),
            earnings_capture=leaking_earnings,
            reference_capture=leaking_reference,
        )

        forbidden = ["SUPERSECRET123", "KEY999", "apiKey=", "C:\\Users\\Gary", "credentials.txt"]

        # Check in result object
        for token in forbidden:
            assert token not in str(result.earnings.error_detail)
            assert token not in str(result.reference.error_detail)

        # Check in serialized output
        serialized = json.dumps(_build_run_slot_output(result))
        for token in forbidden:
            assert token not in serialized


# ─────────────────────────────────────────────────────────────────────────────
# 4. Real XNYS Market Calendar Acceptance (Section 7)
# ─────────────────────────────────────────────────────────────────────────────

class TestRealXNYSMarketCalendar:
    """Acceptance tests using real tradex.market.hours without patching is_trading_day."""

    def test_non_trading_days(self, tmp_path):
        manifest = _manifest()
        settings = _settings(tmp_path)
        mock_e = MagicMock()
        mock_r = MagicMock()

        # Saturday 2026-01-03
        sat_now = lambda: datetime(2026, 1, 3, 14, 30, tzinfo=UTC)
        res_sat = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=sat_now,
            earnings_capture=mock_e,
            reference_capture=mock_r,
        )
        assert res_sat.operational_status == PITOperationalStatus.NOT_DUE
        assert mock_e.call_count == 0

        # Sunday 2026-01-04
        sun_now = lambda: datetime(2026, 1, 4, 14, 30, tzinfo=UTC)
        res_sun = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=sun_now,
            earnings_capture=mock_e,
            reference_capture=mock_r,
        )
        assert res_sun.operational_status == PITOperationalStatus.NOT_DUE
        assert mock_e.call_count == 0

        # New Year's Day holiday: 2026-01-01 (Thursday)
        nyd_now = lambda: datetime(2026, 1, 1, 14, 30, tzinfo=UTC)
        res_nyd = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=nyd_now,
            earnings_capture=mock_e,
            reference_capture=mock_r,
        )
        assert res_nyd.operational_status == PITOperationalStatus.NOT_DUE
        assert mock_e.call_count == 0

    def test_morning_slot_timing_winter_est(self, tmp_path):
        """Winter EST (UTC-5): 09:00 ET = 14:00 UTC."""
        manifest = _manifest()
        settings = _settings(tmp_path)
        e_res = _earnings_result_succeeded("e", manifest)
        r_res = _reference_result_succeeded("r", manifest)

        # 08:59:59 ET = 13:59:59 UTC -> not_due
        res_before = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=lambda: datetime(2026, 1, 2, 13, 59, 59, tzinfo=UTC),
            earnings_capture=lambda **kw: e_res,
            reference_capture=lambda **kw: r_res,
        )
        assert res_before.operational_status == PITOperationalStatus.NOT_DUE

        # 09:00:00 ET = 14:00:00 UTC -> due
        res_at = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=lambda: datetime(2026, 1, 2, 14, 0, 0, tzinfo=UTC),
            earnings_capture=lambda **kw: e_res,
            reference_capture=lambda **kw: r_res,
        )
        assert res_at.operational_status == PITOperationalStatus.SUCCEEDED

        # 09:01:00 ET = 14:01:00 UTC -> due
        res_after = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=lambda: datetime(2026, 1, 2, 14, 1, 0, tzinfo=UTC),
            earnings_capture=lambda **kw: e_res,
            reference_capture=lambda **kw: r_res,
        )
        assert res_after.operational_status == PITOperationalStatus.SUCCEEDED

    def test_evening_slot_timing_winter_est(self, tmp_path):
        """Winter EST (UTC-5): 20:30 ET = 01:30 UTC next day."""
        manifest = _manifest()
        settings = _settings(tmp_path)
        e_res = _earnings_result_succeeded("e", manifest)
        r_res = _reference_result_succeeded("r", manifest)

        # 20:29:59 ET = 01:29:59 UTC next day (2026-01-03) -> not_due
        res_before = run_pit_slot(
            slot=CaptureSlot.EVENING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=lambda: datetime(2026, 1, 3, 1, 29, 59, tzinfo=UTC),
            earnings_capture=lambda **kw: e_res,
            reference_capture=lambda **kw: r_res,
        )
        assert res_before.operational_status == PITOperationalStatus.NOT_DUE

        # 20:30:00 ET = 01:30:00 UTC next day (2026-01-03) -> due
        res_at = run_pit_slot(
            slot=CaptureSlot.EVENING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=lambda: datetime(2026, 1, 3, 1, 30, 0, tzinfo=UTC),
            earnings_capture=lambda **kw: e_res,
            reference_capture=lambda **kw: r_res,
        )
        assert res_at.operational_status == PITOperationalStatus.SUCCEEDED

    def test_timing_summer_edt(self, tmp_path):
        """Summer EDT (UTC-4): Wednesday 2026-06-17.
        Morning 09:00 ET = 13:00 UTC. Evening 20:30 ET = 00:30 UTC next day.
        """
        manifest = _manifest(eff=date(2026, 1, 1))
        settings = _settings(tmp_path)
        e_res = _earnings_result_succeeded("e", manifest)
        r_res = _reference_result_succeeded("r", manifest)

        # Morning before (12:59:59 UTC) -> not_due
        res_m_before = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=lambda: datetime(2026, 6, 17, 12, 59, 59, tzinfo=UTC),
            earnings_capture=lambda **kw: e_res,
            reference_capture=lambda **kw: r_res,
        )
        assert res_m_before.operational_status == PITOperationalStatus.NOT_DUE

        # Morning at (13:00:00 UTC) -> due
        res_m_at = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=lambda: datetime(2026, 6, 17, 13, 0, 0, tzinfo=UTC),
            earnings_capture=lambda **kw: e_res,
            reference_capture=lambda **kw: r_res,
        )
        assert res_m_at.operational_status == PITOperationalStatus.SUCCEEDED

        # Evening before (00:29:59 UTC on 2026-06-18) -> not_due
        res_e_before = run_pit_slot(
            slot=CaptureSlot.EVENING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=lambda: datetime(2026, 6, 18, 0, 29, 59, tzinfo=UTC),
            earnings_capture=lambda **kw: e_res,
            reference_capture=lambda **kw: r_res,
        )
        assert res_e_before.operational_status == PITOperationalStatus.NOT_DUE

        # Evening at (00:30:00 UTC on 2026-06-18) -> due
        res_e_at = run_pit_slot(
            slot=CaptureSlot.EVENING,
            universe_manifest=manifest,
            settings=settings,
            now_fn=lambda: datetime(2026, 6, 18, 0, 30, 0, tzinfo=UTC),
            earnings_capture=lambda **kw: e_res,
            reference_capture=lambda **kw: r_res,
        )
        assert res_e_at.operational_status == PITOperationalStatus.SUCCEEDED


# ─────────────────────────────────────────────────────────────────────────────
# 5. Zero Side Effects for Not-Due Execution (Section 8)
# ─────────────────────────────────────────────────────────────────────────────

class TestNotDueZeroSideEffects:
    def test_weekend_missing_db_no_create_no_provider_calls(self, tmp_path):
        manifest = _manifest()
        missing_db = tmp_path / "nonexistent" / "signals.db"
        settings = settings_from_mapping({"TRADEX_DB_PATH": str(missing_db)})
        mock_e = MagicMock()
        mock_r = MagicMock()

        # Saturday
        res = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            db_path=missing_db,
            now_fn=lambda: datetime(2026, 1, 3, 14, 30, tzinfo=UTC),
            earnings_capture=mock_e,
            reference_capture=mock_r,
        )
        assert res.operational_status == PITOperationalStatus.NOT_DUE
        assert not missing_db.exists()
        assert mock_e.call_count == 0
        assert mock_r.call_count == 0

    def test_before_slot_missing_db_no_create_no_provider_calls(self, tmp_path):
        manifest = _manifest()
        missing_db = tmp_path / "nonexistent" / "signals.db"
        settings = settings_from_mapping({"TRADEX_DB_PATH": str(missing_db)})
        mock_e = MagicMock()
        mock_r = MagicMock()

        # Friday before morning slot (08:30 ET = 13:30 UTC)
        res = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest,
            settings=settings,
            db_path=missing_db,
            now_fn=lambda: datetime(2026, 1, 2, 13, 30, tzinfo=UTC),
            earnings_capture=mock_e,
            reference_capture=mock_r,
        )
        assert res.operational_status == PITOperationalStatus.NOT_DUE
        assert not missing_db.exists()
        assert mock_e.call_count == 0
        assert mock_r.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 6. Strengthened Universe Drift Proof (Section 9)
# ─────────────────────────────────────────────────────────────────────────────

class TestStrengthenedUniverseDrift:
    def test_universe_drift_performs_zero_writes_and_preserves_existing_data(self, tmp_path):
        """When universe drift is detected, zero provider calls and zero DB mutations occur."""
        import sqlite3

        from tradex.pit.models import PIT_CAPTURE_CONTRACT_VERSION, CaptureKind
        from tradex.pit.store import create_capture_run
        from tradex.tracker.store import init as store_init

        db_path = tmp_path / "signals.db"
        settings = _settings(tmp_path)
        store_init(db_path=db_path, settings=settings)

        manifest_a = _manifest(symbols=("AAPL", "MSFT"), uid="universe-a")
        manifest_b = _manifest(symbols=("AAPL", "GOOG"), uid="universe-b")

        # Persist a run for manifest_a
        now = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
        run_a = PITCaptureRun(
            capture_run_id="run-a-123",
            idempotency_key="pit-earnings-2026-01-02-morning-run-a-123",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 1, 2),
            scheduled_for=datetime(2026, 1, 2, 14, 0, tzinfo=UTC),
            requested_at=now,
            completed_at=now,
            requested_provider="yahoo",
            universe_hash=manifest_a.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=now,
            updated_at=now,
            contract_version=PIT_CAPTURE_CONTRACT_VERSION,
        )
        create_capture_run(run_a, db_path=db_path, settings=settings)

        # Snapshot exact DB state before calling with manifest_b
        def dump_db():
            con = sqlite3.connect(str(db_path))
            try:
                tables = ["pit_capture_runs", "pit_earnings_snapshots", "pit_reference_capture_runs", "pit_reference_snapshots"]
                data = {}
                for t in tables:
                    rows = con.execute(f"SELECT * FROM {t}").fetchall()
                    data[t] = rows
                return data
            finally:
                con.close()

        db_before = dump_db()
        assert len(db_before["pit_capture_runs"]) == 1

        mock_e = MagicMock()
        mock_r = MagicMock()

        # Invoke with manifest_b on same date/slot
        result = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest_b,
            settings=settings,
            db_path=db_path,
            now_fn=lambda: now,
            earnings_capture=mock_e,
            reference_capture=mock_r,
        )

        assert result.operational_status == PITOperationalStatus.FAILED
        assert "Universe conflict" in result.earnings.error_detail
        assert mock_e.call_count == 0
        assert mock_r.call_count == 0

        db_after = dump_db()
        assert db_before == db_after
