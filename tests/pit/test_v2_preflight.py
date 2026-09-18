"""Contract v2 preflight validation and interface guards test suite.

Verifies strict preflight parameter checking for capture_earnings_snapshot
and capture_reference_snapshot, ensuring fail-closed behavior before any
provider calls or database writes occur.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradex.pit.earnings import capture_earnings_snapshot
from tradex.pit.models import CaptureSlot
from tradex.pit.ops import PITUniverseManifest
from tradex.pit.reference import capture_reference_snapshot


def _v2_manifest(
    symbols: tuple[str, ...] = ("AAPL", "MSFT"),
    cv: int = 2,
) -> PITUniverseManifest:
    return PITUniverseManifest(
        contract_version=cv,
        universe_id="u-v2-preflight",
        universe_version="v1",
        effective_from=date(2025, 1, 1),
        symbols=symbols,
        description="preflight test manifest",
        applicability={s: {"earnings": "required", "reference": "required"} for s in symbols},
    )


def _dt() -> datetime:
    return datetime(2026, 1, 2, 14, 30, tzinfo=UTC)


class TestV2PreflightGuards:
    """Test strict preflight validation rules for capture services."""

    def test_earnings_unsupported_contract_version(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        lookup = MagicMock()
        with pytest.raises(ValueError, match="Unsupported contract_version 3"):
            capture_earnings_snapshot(
                symbols=("AAPL",),
                slot=CaptureSlot.MORNING,
                contract_version=3,
                db_path=db_path,
                now_fn=_dt,
                earnings_lookup=lookup,
            )
        assert lookup.call_count == 0
        assert not db_path.exists()

    def test_reference_unsupported_contract_version(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        lookup = MagicMock()
        with pytest.raises(ValueError, match="Unsupported contract_version 0"):
            capture_reference_snapshot(
                symbols=("AAPL",),
                slot=CaptureSlot.MORNING,
                contract_version=0,
                db_path=db_path,
                now_fn=_dt,
                reference_lookup=lookup,
            )
        assert lookup.call_count == 0
        assert not db_path.exists()

    def test_earnings_v1_rejects_manifest_presence(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        manifest = _v2_manifest()
        lookup = MagicMock()
        with pytest.raises(ValueError, match="manifest must be None when contract_version=1"):
            capture_earnings_snapshot(
                symbols=("AAPL", "MSFT"),
                slot=CaptureSlot.MORNING,
                contract_version=1,
                manifest=manifest,
                db_path=db_path,
                now_fn=_dt,
                earnings_lookup=lookup,
            )
        assert lookup.call_count == 0
        assert not db_path.exists()

    def test_reference_v1_rejects_manifest_presence(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        manifest = _v2_manifest()
        lookup = MagicMock()
        with pytest.raises(ValueError, match="manifest must be None when contract_version=1"):
            capture_reference_snapshot(
                symbols=("AAPL", "MSFT"),
                slot=CaptureSlot.MORNING,
                contract_version=1,
                manifest=manifest,
                db_path=db_path,
                now_fn=_dt,
                reference_lookup=lookup,
            )
        assert lookup.call_count == 0
        assert not db_path.exists()

    def test_earnings_v2_requires_manifest(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        lookup = MagicMock()
        with pytest.raises(ValueError, match="manifest is required when contract_version=2"):
            capture_earnings_snapshot(
                symbols=("AAPL",),
                slot=CaptureSlot.MORNING,
                contract_version=2,
                manifest=None,
                db_path=db_path,
                now_fn=_dt,
                earnings_lookup=lookup,
            )
        assert lookup.call_count == 0
        assert not db_path.exists()

    def test_reference_v2_requires_manifest(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        lookup = MagicMock()
        with pytest.raises(ValueError, match="manifest is required when contract_version=2"):
            capture_reference_snapshot(
                symbols=("AAPL",),
                slot=CaptureSlot.MORNING,
                contract_version=2,
                manifest=None,
                db_path=db_path,
                now_fn=_dt,
                reference_lookup=lookup,
            )
        assert lookup.call_count == 0
        assert not db_path.exists()

    def test_earnings_v2_rejects_v1_manifest(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        manifest = _v2_manifest(cv=1)
        lookup = MagicMock()
        with pytest.raises(ValueError, match="manifest.contract_version must be 2"):
            capture_earnings_snapshot(
                symbols=("AAPL", "MSFT"),
                slot=CaptureSlot.MORNING,
                contract_version=2,
                manifest=manifest,
                db_path=db_path,
                now_fn=_dt,
                earnings_lookup=lookup,
            )
        assert lookup.call_count == 0
        assert not db_path.exists()

    def test_reference_v2_rejects_v1_manifest(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        manifest = _v2_manifest(cv=1)
        lookup = MagicMock()
        with pytest.raises(ValueError, match="manifest.contract_version must be 2"):
            capture_reference_snapshot(
                symbols=("AAPL", "MSFT"),
                slot=CaptureSlot.MORNING,
                contract_version=2,
                manifest=manifest,
                db_path=db_path,
                now_fn=_dt,
                reference_lookup=lookup,
            )
        assert lookup.call_count == 0
        assert not db_path.exists()

    def test_earnings_v2_rejects_symbol_mismatch(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        manifest = _v2_manifest(symbols=("AAPL", "MSFT"))
        lookup = MagicMock()
        with pytest.raises(ValueError, match="symbols mismatch between arguments and manifest"):
            capture_earnings_snapshot(
                symbols=("AAPL", "GOOG"),
                slot=CaptureSlot.MORNING,
                contract_version=2,
                manifest=manifest,
                db_path=db_path,
                now_fn=_dt,
                earnings_lookup=lookup,
            )
        assert lookup.call_count == 0
        assert not db_path.exists()

    def test_reference_v2_rejects_symbol_mismatch(self, tmp_path: Path) -> None:
        db_path = tmp_path / "signals.db"
        manifest = _v2_manifest(symbols=("AAPL", "MSFT"))
        lookup = MagicMock()
        with pytest.raises(ValueError, match="symbols mismatch between arguments and manifest"):
            capture_reference_snapshot(
                symbols=("AAPL", "GOOG"),
                slot=CaptureSlot.MORNING,
                contract_version=2,
                manifest=manifest,
                db_path=db_path,
                now_fn=_dt,
                reference_lookup=lookup,
            )
        assert lookup.call_count == 0
        assert not db_path.exists()
