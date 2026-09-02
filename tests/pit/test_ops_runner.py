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
