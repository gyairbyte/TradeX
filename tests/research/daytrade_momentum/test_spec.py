"""Tests for locked specification verification and frozen universe."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradex.research.daytrade_momentum.spec import (
    DAYTRADE_002A_SPEC_SHA256,
    LOCKED_FROZEN_UNIVERSE,
    DaytradeSpec,
    SpecError,
    load_and_verify_spec,
    verify_spec,
)


def test_spec_loading_and_sha256(locked_spec: DaytradeSpec) -> None:
    """Verify that canonical DAYTRADE-002A spec loads and matches locked SHA-256."""
    assert locked_spec.task_id == "DAYTRADE-002A"
    assert locked_spec.spec_version == 1
    assert locked_spec.sha256 == DAYTRADE_002A_SPEC_SHA256
    assert verify_spec() is True


def test_frozen_universe_isolation(locked_spec: DaytradeSpec) -> None:
    """Verify universe is strictly frozen to 15 liquid ETFs without runtime preset dependency."""
    expected = (
        "XLK", "XLV", "XLF", "XLY", "XLP",
        "XLE", "XLI", "XLB", "XLU", "XLRE",
        "XLC", "SPY", "QQQ", "IWM", "DIA",
    )
    assert locked_spec.universe == expected
    assert LOCKED_FROZEN_UNIVERSE == expected
    assert len(locked_spec.universe) == 15


def test_partitions_and_warmup_guard(locked_spec: DaytradeSpec) -> None:
    """Verify partition date boundaries and ensure warmup cannot be evaluated."""
    assert locked_spec.warmup.start == "2026-01-02"
    assert locked_spec.warmup.end == "2026-01-30"

    assert locked_spec.development.start == "2026-02-02"
    assert locked_spec.development.end == "2026-04-30"

    assert locked_spec.validation.start == "2026-05-01"
    assert locked_spec.validation.end == "2026-06-30"

    assert locked_spec.holdout.start == "2026-07-01"
    assert locked_spec.holdout.end == "2026-08-31"

    # Evaluatable split accessor should reject warmup
    with pytest.raises(ValueError, match="Warmup is history-only"):
        locked_spec.get_evaluatable_split_dates("warmup")

    dev_dates = locked_spec.get_evaluatable_split_dates("development")
    assert dev_dates.start == "2026-02-02"
    assert dev_dates.end == "2026-04-30"


def test_spec_tamper_rejection(temp_output_dir: Path) -> None:
    """Verify that tampering with any spec parameter fails SHA-256 verification."""
    spec_path = Path("docs/research/specs/DAYTRADE-002A-v1.json")
    with open(spec_path, encoding="utf-8") as f:
        data = json.load(f)

    # Tamper with universe
    tampered_data = dict(data)
    tampered_data["universe"] = list(data["universe"]) + ["XBI"]

    tampered_file = temp_output_dir / "tampered_spec.json"
    with open(tampered_file, "w", encoding="utf-8") as f:
        json.dump(tampered_data, f)

    with pytest.raises(SpecError, match="SHA-256 mismatch"):
        load_and_verify_spec(tampered_file)
