"""Specification loading and hash verification tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from tradex.research.daytrade_reversal.spec import (
    DAYTRADE_001B_SPEC_SHA256,
    LOCKED_UNIVERSE,
    SpecError,
    load_and_verify_spec,
)
from tradex.watchlists.presets import DOW30


def test_spec_loads_and_verifies_hash(locked_spec) -> None:
    """Locked spec loads cleanly and matches exact expected SHA-256."""
    assert locked_spec.task_id == "DAYTRADE-001B"
    assert locked_spec.sha256 == DAYTRADE_001B_SPEC_SHA256
    assert locked_spec.universe == DOW30
    assert len(locked_spec.universe) == 30
    assert locked_spec.trailing_sessions == 20
    assert locked_spec.quantile == 0.001
    assert locked_spec.bootstrap_resamples == 2000
    assert locked_spec.bootstrap_seed == 20260925


def test_spec_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    """Tampered spec file fails closed with SpecError."""
    tampered_file = tmp_path / "tampered_spec.json"
    tampered_file.write_text('{"task_id": "DAYTRADE-001B", "tampered": true}', encoding="utf-8")

    with pytest.raises(SpecError, match="SHA-256 mismatch"):
        load_and_verify_spec(tampered_file)


def test_spec_missing_file_fails_closed(tmp_path: Path) -> None:
    """Non-existent spec file fails closed with SpecError."""
    non_existent = tmp_path / "missing.json"
    with pytest.raises(SpecError, match="not found"):
        load_and_verify_spec(non_existent)


def test_universe_matches_frozen_dow30(locked_spec) -> None:
    """Universe must exactly match the locked 30 symbols from presets.DOW30."""
    assert locked_spec.universe == LOCKED_UNIVERSE
    assert "AAPL" in locked_spec.universe
    assert "MSFT" in locked_spec.universe
    assert "NVDA" in locked_spec.universe
