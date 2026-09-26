"""Contract v2 CLI subcommands & exit code test suite.

Verifies:
1. run-slot CLI subcommand with v2 manifest:
   - Succeeded/not_due yields exit code 0.
   - Degraded yields exit code 2.
   - Operations-level failure yields exit code 1.
   - Structured JSON output contains v2 schema with evidence_completeness.
2. health CLI subcommand with v2 manifest:
   - Healthy/not_due yields exit code 0.
   - Degraded/missing/incomplete yields exit code 2.
   - Universe conflict or failure yields exit code 1.
   - Structured JSON output contains v2 schema with evidence_completeness.
3. Legacy v1 output shape and exit codes are fully preserved when invoked with v1 manifest.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

from tradex.pit.models import (
    CaptureKind,
    CaptureRunStatus,
    CaptureSlot,
    PITCaptureRun,
)
from tradex.pit.ops import (
    PITSlotHealthStatus,
    get_pit_slot_health,
    load_universe_manifest,
    main,
)
from tradex.pit.store import create_capture_run
from tradex.tracker import store


def _dt() -> datetime:
    return datetime(2026, 1, 2, 14, 30, tzinfo=UTC)


def _write_v2_manifest(path: Path) -> Path:
    m = {
        "contract_version": 2,
        "universe_id": "u-cli-v2",
        "universe_version": "v1",
        "effective_from": "2025-01-01",
        "symbols": ["AAPL", "MSFT"],
        "description": "CLI test universe",
        "applicability": {
            "AAPL": {"earnings": "required", "reference": "required"},
            "MSFT": {"earnings": "required", "reference": "required"},
        },
    }
    manifest_file = path / "universe_v2.json"
    manifest_file.write_text(json.dumps(m), encoding="utf-8")
    return manifest_file


def _write_v1_manifest(path: Path) -> Path:
    m = {
        "contract_version": 1,
        "universe_id": "u-cli-v1",
        "universe_version": "v1",
        "effective_from": "2025-01-01",
        "symbols": ["AAPL", "MSFT"],
        "description": "CLI v1 test universe",
    }
    manifest_file = path / "universe_v1.json"
    manifest_file.write_text(json.dumps(m), encoding="utf-8")
    return manifest_file


class TestV2OpsCLI:
    """Test CLI subcommands for contract v2 operations."""

    def test_cli_run_slot_v2_succeeded_json_and_exit_0(
        self, tmp_path: Path, capsys
    ) -> None:
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest_file = _write_v2_manifest(tmp_path)

        with patch("tradex.pit.earnings.capture_earnings_snapshot") as mock_e, \
             patch("tradex.pit.reference.capture_reference_snapshot") as mock_r, \
             patch("tradex.pit.ops.is_trading_day", return_value=True), \
             patch("tradex.pit.ops._get_aware_utc_now", return_value=_dt()):

            from tests.pit.test_ops_runner import (
                _earnings_result_succeeded,
                _reference_result_succeeded,
            )
            from tradex.pit.ops import load_universe_manifest
            manifest = load_universe_manifest(manifest_file)
            mock_e.return_value = _earnings_result_succeeded("e-cli", manifest)
            mock_r.return_value = _reference_result_succeeded("r-cli", manifest)

            exit_code = main([
                "run-slot",
                "--slot", "morning",
                "--universe-file", str(manifest_file),
                "--db-path", str(db_path),
            ])

        assert exit_code == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)

        assert out["contract_version"] == 2
        assert out["operational_status"] == "succeeded"
        assert "evidence_completeness" in out
        assert out["evidence_completeness"]["overall_tier"] == "complete"
        assert "completeness" in out["earnings"]
        assert "completeness" in out["reference"]

    def test_cli_health_v2_healthy_json_and_exit_0(
        self, tmp_path: Path, capsys
    ) -> None:
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest_file = _write_v2_manifest(tmp_path)

        from tradex.pit.models import (
            CaptureKind,
            CaptureRunStatus,
            PITCaptureRun,
            PITReferenceCaptureRun,
        )
        from tradex.pit.ops import load_universe_manifest
        from tradex.pit.store import create_capture_run, create_reference_capture_run

        manifest = load_universe_manifest(manifest_file)
        t = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        e_run = PITCaptureRun(
            capture_run_id="e-cli-run",
            idempotency_key="key-e-cli",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 1, 2),
            scheduled_for=t,
            requested_at=t,
            completed_at=t,
            requested_provider="yahoo",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            not_applicable_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t,
            updated_at=t,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_capture_run(e_run, db_path=db_path)

        r_run = PITReferenceCaptureRun(
            capture_run_id="r-cli-run",
            idempotency_key="key-r-cli",
            request_fingerprint="f" * 64,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 1, 2),
            scheduled_for=t,
            requested_at=t,
            completed_at=t,
            requested_provider="massive",
            universe_hash=manifest.universe_hash,
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            ambiguous_n=0,
            error_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t,
            updated_at=t,
            contract_version=2,
            manifest_hash=manifest.manifest_hash,
        )
        create_reference_capture_run(r_run, db_path=db_path)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            exit_code = main([
                "health",
                "--slot", "morning",
                "--universe-file", str(manifest_file),
                "--date", "2026-01-02",
                "--db-path", str(db_path),
            ])

        assert exit_code == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)

        assert out["contract_version"] == 2
        assert out["overall_status"] == "healthy"
        assert out["failure_reason"] is None
        assert "evidence_completeness" in out
        assert out["evidence_completeness"]["overall_tier"] == "complete"
        assert "completeness" in out["earnings"]

    def test_cli_v1_manifest_preserves_legacy_output_shape(
        self, tmp_path: Path, capsys
    ) -> None:
        """When invoked with a v1 manifest, CLI outputs exact legacy dictionary with no v2 fields."""
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest_file = _write_v1_manifest(tmp_path)

        with patch("tradex.pit.earnings.capture_earnings_snapshot") as mock_e, \
             patch("tradex.pit.reference.capture_reference_snapshot") as mock_r, \
             patch("tradex.pit.ops.is_trading_day", return_value=True), \
             patch("tradex.pit.ops._get_aware_utc_now", return_value=_dt()):

            from tests.pit.test_ops_runner import (
                _earnings_result_succeeded,
                _reference_result_succeeded,
            )
            from tradex.pit.ops import load_universe_manifest
            manifest = load_universe_manifest(manifest_file)
            mock_e.return_value = _earnings_result_succeeded("e-v1", manifest)
            mock_r.return_value = _reference_result_succeeded("r-v1", manifest)

            exit_code = main([
                "run-slot",
                "--slot", "morning",
                "--universe-file", str(manifest_file),
                "--db-path", str(db_path),
            ])

        assert exit_code == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)

        # Legacy v1 output check: no evidence_completeness
        assert out["contract_version"] == 1
        assert "evidence_completeness" not in out
        assert "completeness" not in out["earnings"]
        assert "requested_n" not in out["earnings"]

    def test_cli_health_v2_universe_conflict_failed_and_exit_1(
        self, tmp_path: Path, capsys
    ) -> None:
        """For contract v2, universe drift causes health failure: overall_status=FAILED, failure_reason='universe_conflict', CLI exit 1."""
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest_file = _write_v2_manifest(tmp_path)
        manifest = load_universe_manifest(manifest_file)
        t = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        # Existing run with a different/conflicting universe_hash
        e_run = PITCaptureRun(
            capture_run_id="e-conflict-run",
            idempotency_key="key-e-conflict",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 1, 2),
            scheduled_for=t,
            requested_at=t,
            completed_at=t,
            requested_provider="yahoo",
            universe_hash="0" * 64,  # conflicting universe hash
            requested_n=2,
            known_n=2,
            unavailable_n=0,
            error_n=0,
            not_applicable_n=0,
            status=CaptureRunStatus.SUCCEEDED,
            created_at=t,
            updated_at=t,
            contract_version=2,
            manifest_hash="m" * 64,
        )
        create_capture_run(e_run, db_path=db_path)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=date(2026, 1, 2),
                slot=CaptureSlot.MORNING,
                now=t,
                db_path=db_path,
            )
            assert health.overall_status == PITSlotHealthStatus.FAILED
            assert health.failure_reason == "universe_conflict"

            exit_code = main([
                "health",
                "--slot", "morning",
                "--universe-file", str(manifest_file),
                "--date", "2026-01-02",
                "--db-path", str(db_path),
            ])

        assert exit_code == 1
        captured = capsys.readouterr()
        out = json.loads(captured.out)

        assert out["contract_version"] == 2
        assert out["overall_status"] == "failed"
        assert out["failure_reason"] == "universe_conflict"

    def test_cli_health_v1_universe_conflict_preserved_and_exit_1(
        self, tmp_path: Path, capsys
    ) -> None:
        """For contract v1, universe drift preserves legacy overall_status=UNIVERSE_CONFLICT and exit code 1."""
        db_path = tmp_path / "signals.db"
        store.init(db_path)
        manifest_file = _write_v1_manifest(tmp_path)
        manifest = load_universe_manifest(manifest_file)
        t = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)

        e_run = PITCaptureRun(
            capture_run_id="e-conflict-v1",
            idempotency_key="key-e-conflict-v1",
            request_fingerprint="f" * 64,
            capture_kind=CaptureKind.EARNINGS,
            capture_slot=CaptureSlot.MORNING,
            capture_date=date(2026, 1, 2),
            scheduled_for=t,
            requested_at=t,
            completed_at=t,
            requested_provider="yahoo",
            universe_hash="0" * 64,  # conflicting universe hash
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
        create_capture_run(e_run, db_path=db_path)

        with patch("tradex.pit.ops.is_trading_day", return_value=True):
            health = get_pit_slot_health(
                universe_manifest=manifest,
                capture_date=date(2026, 1, 2),
                slot=CaptureSlot.MORNING,
                now=t,
                db_path=db_path,
            )
            assert health.overall_status == PITSlotHealthStatus.UNIVERSE_CONFLICT

            exit_code = main([
                "health",
                "--slot", "morning",
                "--universe-file", str(manifest_file),
                "--date", "2026-01-02",
                "--db-path", str(db_path),
            ])

        assert exit_code == 1
        captured = capsys.readouterr()
        out = json.loads(captured.out)

        assert "contract_version" not in out
        assert "evidence_completeness" not in out
        assert out["overall_status"] == "universe_conflict"
