"""Tests for tradex.pit.ops CLI entrypoints and exit codes (MVP-ARCH-001-R7-PIT-001C1)."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from tradex.pit.models import CaptureSlot
from tradex.pit.ops import (
    PITFamilyRunResult,
    PITOperationalStatus,
    PITSlotHealth,
    PITSlotHealthStatus,
    PITSlotRunResult,
    build_parser,
    main,
)

_VALID_MANIFEST_DICT = {
    "contract_version": 1,
    "universe_id": "test-cli-universe",
    "universe_version": "v1",
    "effective_from": "2025-01-01",
    "symbols": ["AAPL", "MSFT"],
    "description": "CLI test universe",
}


@pytest.fixture
def valid_manifest_file(tmp_path: Path) -> Path:
    p = tmp_path / "universe.json"
    p.write_text(json.dumps(_VALID_MANIFEST_DICT), encoding="utf-8")
    return p


@pytest.fixture
def invalid_manifest_file(tmp_path: Path) -> Path:
    p = tmp_path / "invalid_universe.json"
    # contract_version != 1 is invalid
    p.write_text(
        json.dumps({**_VALID_MANIFEST_DICT, "contract_version": 999}),
        encoding="utf-8",
    )
    return p


# ─────────────────────────────────────────────────────────────────────────────
# TestValidateUniverseCLI
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateUniverseCLI:
    def test_valid_manifest_exit_code_0(self, valid_manifest_file: Path, capsys):
        exit_code = main(["validate-universe", "--universe-file", str(valid_manifest_file)])
        captured = capsys.readouterr()
        assert exit_code == 0
        data = json.loads(captured.out)
        assert data["valid"] is True
        assert data["contract_version"] == 1
        assert data["universe_id"] == "test-cli-universe"
        assert data["symbol_count"] == 2
        assert "manifest_hash" in data
        assert "universe_hash" in data
        assert "minimum_pacing_floor_seconds" in data
        assert "maximum_pacing_floor_seconds" in data

    def test_valid_manifest_zero_side_effects(self, valid_manifest_file: Path, tmp_path: Path, capsys):
        db_file = tmp_path / "should_not_exist.db"
        exit_code = main(["validate-universe", "--universe-file", str(valid_manifest_file)])
        assert exit_code == 0
        assert not db_file.exists()

    def test_missing_manifest_file_exit_code_1(self, tmp_path: Path, capsys):
        missing = tmp_path / "nonexistent.json"
        exit_code = main(["validate-universe", "--universe-file", str(missing)])
        captured = capsys.readouterr()
        assert exit_code == 1
        data = json.loads(captured.out)
        assert data["valid"] is False
        assert "error" in data

    def test_invalid_manifest_content_exit_code_1(self, invalid_manifest_file: Path, capsys):
        exit_code = main(["validate-universe", "--universe-file", str(invalid_manifest_file)])
        captured = capsys.readouterr()
        assert exit_code == 1
        data = json.loads(captured.out)
        assert data["valid"] is False
        assert "error" in data


# ─────────────────────────────────────────────────────────────────────────────
# TestRunSlotCLI
# ─────────────────────────────────────────────────────────────────────────────

class TestRunSlotCLI:
    def test_parser_has_no_historical_or_backfill_flags(self):
        """Verify the run-slot parser rejects all historical, backfill, or as-if flags."""
        parser = build_parser()
        subparsers_actions = [
            action for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        assert len(subparsers_actions) == 1
        run_slot_subparser = subparsers_actions[0].choices["run-slot"]

        all_flags = set()
        for action in run_slot_subparser._actions:
            all_flags.update(action.option_strings)

        prohibited = [
            "--date",
            "--capture-date",
            "--historical",
            "--backfill",
            "--as-if",
            "--time",
            "--timestamp",
        ]
        for p in prohibited:
            assert p not in all_flags, f"run-slot must not accept {p}"

        # Verify attempting to pass prohibited flags causes parser exit
        for p in prohibited:
            with pytest.raises(SystemExit):
                parser.parse_args(["run-slot", p, "foo", "--universe-file", "u.json", "--slot", "morning"])

    def _dummy_slot_result(self, status: PITOperationalStatus) -> PITSlotRunResult:
        now = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
        family_res = PITFamilyRunResult(
            family="earnings",
            capture_run_id="run-1",
            status=None,
            known_n=0,
            unavailable_n=0,
            ambiguous_n=0,
            error_n=0,
            error_detail=None,
        )
        return PITSlotRunResult(
            contract_version=1,
            capture_date=date(2026, 1, 2),
            slot=CaptureSlot.MORNING,
            scheduled_for=now,
            requested_at=now,
            universe_id="test-cli-universe",
            universe_version="v1",
            manifest_hash="m" * 64,
            universe_hash="u" * 64,
            symbol_count=2,
            operational_status=status,
            earnings=family_res,
            reference=family_res,
        )

    def test_run_slot_succeeded_exit_code_0(self, valid_manifest_file: Path, capsys):
        dummy = self._dummy_slot_result(PITOperationalStatus.SUCCEEDED)
        with patch("tradex.pit.ops.run_pit_slot", return_value=dummy):
            exit_code = main([
                "run-slot",
                "--slot", "morning",
                "--universe-file", str(valid_manifest_file),
            ])
        captured = capsys.readouterr()
        assert exit_code == 0
        data = json.loads(captured.out)
        assert data["operational_status"] == "succeeded"

    def test_run_slot_not_due_exit_code_0(self, valid_manifest_file: Path, capsys):
        dummy = self._dummy_slot_result(PITOperationalStatus.NOT_DUE)
        with patch("tradex.pit.ops.run_pit_slot", return_value=dummy):
            exit_code = main([
                "run-slot",
                "--slot", "morning",
                "--universe-file", str(valid_manifest_file),
            ])
        captured = capsys.readouterr()
        assert exit_code == 0
        data = json.loads(captured.out)
        assert data["operational_status"] == "not_due"

    def test_run_slot_degraded_exit_code_2(self, valid_manifest_file: Path, capsys):
        dummy = self._dummy_slot_result(PITOperationalStatus.DEGRADED)
        with patch("tradex.pit.ops.run_pit_slot", return_value=dummy):
            exit_code = main([
                "run-slot",
                "--slot", "morning",
                "--universe-file", str(valid_manifest_file),
            ])
        captured = capsys.readouterr()
        assert exit_code == 2
        data = json.loads(captured.out)
        assert data["operational_status"] == "degraded"

    def test_run_slot_failed_exit_code_1(self, valid_manifest_file: Path, capsys):
        dummy = self._dummy_slot_result(PITOperationalStatus.FAILED)
        with patch("tradex.pit.ops.run_pit_slot", return_value=dummy):
            exit_code = main([
                "run-slot",
                "--slot", "morning",
                "--universe-file", str(valid_manifest_file),
            ])
        captured = capsys.readouterr()
        assert exit_code == 1
        data = json.loads(captured.out)
        assert data["operational_status"] == "failed"

    def test_run_slot_invalid_manifest_exit_code_1(self, invalid_manifest_file: Path, capsys):
        exit_code = main([
            "run-slot",
            "--slot", "morning",
            "--universe-file", str(invalid_manifest_file),
        ])
        captured = capsys.readouterr()
        assert exit_code == 1
        data = json.loads(captured.out)
        assert data["operational_status"] == "failed"
        assert "error" in data

    def test_run_slot_unexpected_exception_exit_code_1(self, valid_manifest_file: Path, capsys):
        with patch("tradex.pit.ops.run_pit_slot", side_effect=RuntimeError("database disk image is malformed")):
            exit_code = main([
                "run-slot",
                "--slot", "morning",
                "--universe-file", str(valid_manifest_file),
            ])
        captured = capsys.readouterr()
        assert exit_code == 1
        data = json.loads(captured.out)
        assert data["operational_status"] == "failed"
        assert "unexpected internal error" in data["error"]


# ─────────────────────────────────────────────────────────────────────────────
# TestHealthCLI
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthCLI:
    def _dummy_health(self, status: PITSlotHealthStatus) -> PITSlotHealth:
        now = datetime(2026, 1, 2, 14, 0, tzinfo=UTC)
        from tradex.pit.ops import PITFamilyHealth
        fh = PITFamilyHealth(
            family="earnings",
            expected=True,
            attempt_count=1,
            run_ids=("run-1",),
            statuses=("succeeded",),
            universe_hashes=("u" * 64,),
            latest_requested_at=now,
            latest_completed_at=now,
            snapshot_count=2,
            first_request_lag_seconds=0.0,
            completion_lag_seconds=0.0,
        )
        return PITSlotHealth(
            universe_id="test-cli-universe",
            universe_version="v1",
            manifest_hash="m" * 64,
            universe_hash="u" * 64,
            capture_date=date(2026, 1, 2),
            slot=CaptureSlot.MORNING,
            scheduled_for=now,
            health_checked_at=now,
            overall_status=status,
            earnings=fh,
            reference=fh,
        )

    def test_health_healthy_exit_code_0(self, valid_manifest_file: Path, capsys):
        dummy = self._dummy_health(PITSlotHealthStatus.HEALTHY)
        with patch("tradex.pit.ops.get_pit_slot_health", return_value=dummy):
            exit_code = main([
                "health",
                "--universe-file", str(valid_manifest_file),
                "--slot", "morning",
            ])
        captured = capsys.readouterr()
        assert exit_code == 0
        data = json.loads(captured.out)
        assert data["overall_status"] == "healthy"

    def test_health_not_due_exit_code_0(self, valid_manifest_file: Path, capsys):
        dummy = self._dummy_health(PITSlotHealthStatus.NOT_DUE)
        with patch("tradex.pit.ops.get_pit_slot_health", return_value=dummy):
            exit_code = main([
                "health",
                "--universe-file", str(valid_manifest_file),
                "--slot", "morning",
            ])
        captured = capsys.readouterr()
        assert exit_code == 0
        data = json.loads(captured.out)
        assert data["overall_status"] == "not_due"

    def test_health_missing_exit_code_2(self, valid_manifest_file: Path, capsys):
        dummy = self._dummy_health(PITSlotHealthStatus.MISSING)
        with patch("tradex.pit.ops.get_pit_slot_health", return_value=dummy):
            exit_code = main([
                "health",
                "--universe-file", str(valid_manifest_file),
                "--slot", "morning",
            ])
        captured = capsys.readouterr()
        assert exit_code == 2
        data = json.loads(captured.out)
        assert data["overall_status"] == "missing"

    def test_health_incomplete_exit_code_2(self, valid_manifest_file: Path, capsys):
        dummy = self._dummy_health(PITSlotHealthStatus.INCOMPLETE)
        with patch("tradex.pit.ops.get_pit_slot_health", return_value=dummy):
            exit_code = main([
                "health",
                "--universe-file", str(valid_manifest_file),
                "--slot", "morning",
            ])
        captured = capsys.readouterr()
        assert exit_code == 2
        data = json.loads(captured.out)
        assert data["overall_status"] == "incomplete"

    def test_health_degraded_exit_code_2(self, valid_manifest_file: Path, capsys):
        dummy = self._dummy_health(PITSlotHealthStatus.DEGRADED)
        with patch("tradex.pit.ops.get_pit_slot_health", return_value=dummy):
            exit_code = main([
                "health",
                "--universe-file", str(valid_manifest_file),
                "--slot", "morning",
            ])
        captured = capsys.readouterr()
        assert exit_code == 2
        data = json.loads(captured.out)
        assert data["overall_status"] == "degraded"

    def test_health_universe_conflict_exit_code_1(self, valid_manifest_file: Path, capsys):
        dummy = self._dummy_health(PITSlotHealthStatus.UNIVERSE_CONFLICT)
        with patch("tradex.pit.ops.get_pit_slot_health", return_value=dummy):
            exit_code = main([
                "health",
                "--universe-file", str(valid_manifest_file),
                "--slot", "morning",
            ])
        captured = capsys.readouterr()
        assert exit_code == 1
        data = json.loads(captured.out)
        assert data["overall_status"] == "universe_conflict"

    def test_health_invalid_date_format_exit_code_1(self, valid_manifest_file: Path, capsys):
        exit_code = main([
            "health",
            "--universe-file", str(valid_manifest_file),
            "--date", "2026/01/02",
        ])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Invalid --date format" in captured.err

    def test_health_invalid_manifest_exit_code_1(self, invalid_manifest_file: Path, capsys):
        exit_code = main([
            "health",
            "--universe-file", str(invalid_manifest_file),
        ])
        captured = capsys.readouterr()
        assert exit_code == 1
        data = json.loads(captured.out)
        assert "error" in data
