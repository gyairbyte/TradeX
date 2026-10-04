"""Tests for input dataset integrity and cryptographic hash verification."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tradex.research.long_002d2.spec import (
    D1_FEATURE_TABLE_PATH,
    D1_FEATURE_TABLE_SHA256,
    STAGE_C_BASELINE_PATH,
    STAGE_C_BASELINE_SHA256,
    STAGE_C_OUTCOME_PATH,
    STAGE_C_OUTCOME_SHA256,
)


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def test_d1_feature_table_hash() -> None:
    """Verify that the D1 feature table file exists and matches locked hash."""
    if not D1_FEATURE_TABLE_PATH.exists():
        pytest.skip(f"D1 feature table not present at {D1_FEATURE_TABLE_PATH}")
    computed = _compute_sha256(D1_FEATURE_TABLE_PATH)
    assert computed == D1_FEATURE_TABLE_SHA256


def test_stage_c_baseline_hash() -> None:
    """Verify that the Stage C baseline comparator outputs file matches locked hash."""
    if not STAGE_C_BASELINE_PATH.exists():
        pytest.skip(f"Stage C baseline outputs not present at {STAGE_C_BASELINE_PATH}")
    computed = _compute_sha256(STAGE_C_BASELINE_PATH)
    assert computed == STAGE_C_BASELINE_SHA256


def test_stage_c_outcome_hash() -> None:
    """Verify that Stage C outcome matrix matches locked hash if present."""
    if not STAGE_C_OUTCOME_PATH.exists():
        pytest.skip(f"Stage C outcome matrix not present at {STAGE_C_OUTCOME_PATH}")
    computed = _compute_sha256(STAGE_C_OUTCOME_PATH)
    assert computed == STAGE_C_OUTCOME_SHA256
