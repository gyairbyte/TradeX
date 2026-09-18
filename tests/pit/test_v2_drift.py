"""Contract v2 drift guard & audit identity test suite.

Verifies:
1. Universe symbol drift across existing runs raises PITOperationalUniverseConflictError.
2. Manifest drift across existing runs raises PITOperationalManifestConflictError.
3. Cross-version conflict across existing runs raises PITOperationalManifestConflictError.
4. Exact replay idempotency: repeating the same v2 execution returns the existing run
   with zero provider calls and zero DB mutations.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

from tradex.pit.earnings import capture_earnings_snapshot
from tradex.pit.models import (
    CaptureKind,
    CaptureRunStatus,
    CaptureSlot,
    PITCaptureRun,
)
from tradex.pit.ops import (
    PITOperationalStatus,
    PITUniverseManifest,
    run_pit_slot,
)
from tradex.pit.store import create_capture_run
from tradex.tracker import store


def _manifest(
    uid: str = "u1",
    desc: str = "d1",
    symbols: tuple[str, ...] = ("AAPL", "MSFT"),
    cv: int = 2,
) -> PITUniverseManifest:
    return PITUniverseManifest(
        contract_version=cv,
        universe_id=uid,
        universe_version="v1",
        effective_from=date(2025, 1, 1),
        symbols=symbols,
        description=desc,
        applicability={s: {"earnings": "required", "reference": "required"} for s in symbols},
    )


class TestV2DriftGuardsAndExactReplay:
    """Test drift fail-closed behavior and exact replay idempotency."""

    def test_universe_symbol_drift_fails_closed(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest_a = _manifest(symbols=("AAPL", "MSFT"))
        manifest_b = _manifest(symbols=("AAPL", "GOOG"))  # different symbols

        t = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        # Run A persisted
        run_a = PITCaptureRun(
            capture_run_id="run-a",
            idempotency_key="key-a",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 1, 2),
            scheduled_for=t,
            requested_at=t,
            completed_at=t,
            requested_provider="yahoo",
            universe_hash=manifest_a.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            not_applicable_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t,
            updated_at=t,
            contract_version=2,
            manifest_hash=manifest_a.manifest_hash,
        )
        create_capture_run(run_a, db_path=db_path)

        mock_e = MagicMock()
        mock_r = MagicMock()

        # Invoking with manifest_b triggers universe conflict
        result = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest_b,
            db_path=db_path,
            now_fn=lambda: t,
            earnings_capture=mock_e,
            reference_capture=mock_r,
        )

        assert result.operational_status == PITOperationalStatus.FAILED
        assert "Universe conflict" in (result.earnings.error_detail or "")
        assert mock_e.call_count == 0
        assert mock_r.call_count == 0

    def test_manifest_drift_same_symbols_different_hash_fails_closed(self, tmp_path: Path) -> None:
        """Same symbols but different universe_id produces identical universe_hash but different manifest_hash."""
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest_1 = _manifest(uid="u1")
        manifest_2 = _manifest(uid="u2")
        assert manifest_1.universe_hash == manifest_2.universe_hash
        assert manifest_1.manifest_hash != manifest_2.manifest_hash

        t = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        run_1 = PITCaptureRun(
            capture_run_id="run-1",
            idempotency_key="key-1",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 1, 2),
            scheduled_for=t,
            requested_at=t,
            completed_at=t,
            requested_provider="yahoo",
            universe_hash=manifest_1.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            not_applicable_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t,
            updated_at=t,
            contract_version=2,
            manifest_hash=manifest_1.manifest_hash,
        )
        create_capture_run(run_1, db_path=db_path)

        mock_e = MagicMock()
        mock_r = MagicMock()

        result = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest_2,
            db_path=db_path,
            now_fn=lambda: t,
            earnings_capture=mock_e,
            reference_capture=mock_r,
        )

        assert result.operational_status == PITOperationalStatus.FAILED
        assert "Manifest conflict" in (result.earnings.error_detail or "")
        assert mock_e.call_count == 0
        assert mock_r.call_count == 0

    def test_cross_version_conflict_fails_closed(self, tmp_path: Path) -> None:
        """Existing run is v1, incoming manifest is v2: cross-version conflict fails closed."""
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest_v2 = _manifest(cv=2)

        t = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        # v1 run in DB
        run_v1 = PITCaptureRun(
            capture_run_id="run-v1",
            idempotency_key="key-v1",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 1, 2),
            scheduled_for=t,
            requested_at=t,
            completed_at=t,
            requested_provider="yahoo",
            universe_hash=manifest_v2.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            not_applicable_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t,
            updated_at=t,
            contract_version=1,
            manifest_hash=None,
        )
        create_capture_run(run_v1, db_path=db_path)

        mock_e = MagicMock()
        mock_r = MagicMock()

        result = run_pit_slot(
            slot=CaptureSlot.MORNING,
            universe_manifest=manifest_v2,
            db_path=db_path,
            now_fn=lambda: t,
            earnings_capture=mock_e,
            reference_capture=mock_r,
        )

        assert result.operational_status == PITOperationalStatus.FAILED
        assert "Cross-version conflict" in (result.earnings.error_detail or "")
        assert mock_e.call_count == 0
        assert mock_r.call_count == 0

    def test_exact_replay_idempotency(self, tmp_path: Path) -> None:
        """Executing twice with identical v2 parameters returns existing run without provider calls."""
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest = _manifest()

        t = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
        calls = 0

        def lookup(sym: str, source: str = "yahoo", settings=None):
            nonlocal calls
            calls += 1
            return date(2026, 3, 1)

        # Run 1: initial execution
        res1 = capture_earnings_snapshot(
            symbols=manifest.symbols,
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=lambda: t,
            earnings_lookup=lookup,
        )
        assert calls == 2
        run1_id = res1.run.capture_run_id

        # Run 2: exact replay
        res2 = capture_earnings_snapshot(
            symbols=manifest.symbols,
            slot=CaptureSlot.MORNING,
            contract_version=2,
            manifest=manifest,
            db_path=db_path,
            now_fn=lambda: t,
            earnings_lookup=lookup,
        )
        # Provider calls remain 2 (0 additional calls)
        assert calls == 2
        assert res2.run.capture_run_id == run1_id
        assert len(res2.snapshots) == 2
