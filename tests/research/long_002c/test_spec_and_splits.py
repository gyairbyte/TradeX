"""Tests for spec verification and fail-closed split boundaries in LONG-002C."""
from __future__ import annotations

import pytest

from tradex.research.long_002c.spec import (
    DEV_END,
    DEV_START,
    FEASIBILITY_FALLBACK_ENDPOINT,
    HOLDOUT_END,
    HOLDOUT_START,
    PRIMARY_ENDPOINT,
    SHADOW_START,
    TARGET_GRID,
    VALIDATION_END,
    VALIDATION_START,
    WARMUP_END,
    WARMUP_START,
    SplitGuardViolationError,
    enforce_split_guard,
    verify_upstream_spec_hashes,
)


def test_upstream_spec_hashes_verify_cleanly() -> None:
    """Verify all 11 referenced upstream specification hashes."""
    verified = verify_upstream_spec_hashes()
    assert len(verified) == 11
    assert "docs/research/specs/LONG-002-v1.json" in verified
    assert "docs/research/specs/LONG-002B-data-contract-v1.json" in verified
    assert "docs/research/specs/LONG-002B-AMEND-002.json" in verified


def test_split_definitions_match_locked_boundaries() -> None:
    """Verify exact split boundary dates."""
    assert WARMUP_START == "2015-01-01"
    assert WARMUP_END == "2015-12-31"
    assert DEV_START == "2016-01-01"
    assert DEV_END == "2020-12-31"
    assert VALIDATION_START == "2021-01-01"
    assert VALIDATION_END == "2022-12-31"
    assert HOLDOUT_START == "2023-01-01"
    assert HOLDOUT_END == "2025-12-31"
    assert SHADOW_START == "2026-01-01"


def test_split_guard_allows_development_and_warmup() -> None:
    """Development and warmup dates pass split guard."""
    enforce_split_guard("2015-06-15")
    enforce_split_guard("2016-01-04")
    enforce_split_guard("2020-12-31")


def test_split_guard_rejects_validation_holdout_shadow() -> None:
    """Split guard rejects any date in 2021-01-01 onward."""
    with pytest.raises(SplitGuardViolationError, match="quarantined split"):
        enforce_split_guard("2021-01-01")

    with pytest.raises(SplitGuardViolationError, match="quarantined split"):
        enforce_split_guard("2021-06-15")

    with pytest.raises(SplitGuardViolationError, match="quarantined split"):
        enforce_split_guard("2023-01-01")

    with pytest.raises(SplitGuardViolationError, match="quarantined split"):
        enforce_split_guard("2026-09-21")


def test_split_guard_rejects_quarantined_paths() -> None:
    """Split guard rejects paths containing quarantined tokens."""
    with pytest.raises(SplitGuardViolationError, match="references quarantined split token"):
        enforce_split_guard("data/validation/prices.parquet")

    with pytest.raises(SplitGuardViolationError, match="references quarantined split token"):
        enforce_split_guard("data/holdout/dataset.parquet")

    with pytest.raises(SplitGuardViolationError, match="references quarantined split token"):
        enforce_split_guard("data/2021/daily.csv")


def test_target_grid_and_endpoints() -> None:
    """Target grid contains all 9 cells and endpoints match locked choices."""
    assert len(TARGET_GRID) == 9
    assert (10.0, 5) in TARGET_GRID
    assert (10.0, 10) in TARGET_GRID
    assert (10.0, 21) in TARGET_GRID
    assert (20.0, 5) in TARGET_GRID
    assert (20.0, 10) in TARGET_GRID
    assert (20.0, 21) in TARGET_GRID
    assert (30.0, 5) in TARGET_GRID
    assert (30.0, 10) in TARGET_GRID
    assert (30.0, 21) in TARGET_GRID

    assert PRIMARY_ENDPOINT == (10.0, 10)
    assert FEASIBILITY_FALLBACK_ENDPOINT == (10.0, 21)
