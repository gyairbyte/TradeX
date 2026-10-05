"""Synthetic tests for the future main study contract and pilot exclusion enforcement."""
from __future__ import annotations

from pathlib import Path

import pytest

from tradex.research.long_002d3a.main_contract import (
    MAIN_STUDY_BATCH_COUNT,
    MAIN_STUDY_BATCH_SIZE,
    MAIN_STUDY_MAX_TICKER_FREQUENCY,
    MAIN_STUDY_SEED,
    MAIN_STUDY_SIZE,
    MAIN_STUDY_STRATA_COUNTS,
    assert_main_study_not_generated,
    get_main_study_contract_summary,
    validate_pilot_exclusion_from_main,
)


def test_main_study_contract_structural_counts() -> None:
    """Verify future main study structural counts sum to exactly 240."""
    assert MAIN_STUDY_SIZE == 240
    assert sum(MAIN_STUDY_STRATA_COUNTS.values()) == 240
    assert MAIN_STUDY_STRATA_COUNTS["positive_master_episode"] == 120
    assert MAIN_STUDY_STRATA_COUNTS["ordinary_non_mover"] == 40
    assert MAIN_STUDY_STRATA_COUNTS["near_miss"] == 40
    assert MAIN_STUDY_STRATA_COUNTS["adverse_trap"] == 40
    assert MAIN_STUDY_BATCH_COUNT * MAIN_STUDY_BATCH_SIZE == 240
    assert MAIN_STUDY_MAX_TICKER_FREQUENCY == 2
    assert MAIN_STUDY_SEED == 20261004


def test_main_study_contract_summary() -> None:
    """Verify the summary dictionary matches contract specifications."""
    summary = get_main_study_contract_summary()
    assert summary["future_main_study_total_cases"] == 240
    assert summary["future_main_study_seed"] == 20261004
    assert summary["pilot_exclusion_count"] == 24
    assert summary["main_sample_generated"] is False
    assert summary["status"] == "LOCKED_FOUNDATION_UNGENERATED"


def test_pilot_exclusion_validation_passes_on_disjoint_sets() -> None:
    """Disjoint main and pilot keys must pass validation cleanly."""
    pilot_keys = [
        ("SEC-A", "2018-01-05", "20:30"),
        ("SEC-B", "2019-02-10", "20:30"),
    ]
    main_keys = [
        ("SEC-C", "2018-01-05", "20:30"),
        ("SEC-D", "2019-02-10", "20:30"),
    ]
    validate_pilot_exclusion_from_main(main_keys, pilot_keys)


def test_pilot_exclusion_validation_fails_on_overlap() -> None:
    """Overlapping pilot key in main keys must fail closed with ValueError."""
    pilot_keys = [
        ("SEC-A", "2018-01-05", "20:30"),
        ("SEC-B", "2019-02-10", "20:30"),
    ]
    main_keys = [
        ("SEC-A", "2018-01-05", "20:30"),  # Overlap!
        ("SEC-C", "2019-02-10", "20:30"),
    ]
    with pytest.raises(ValueError, match="FAIL-CLOSED PILOT EXCLUSION BREACH"):
        validate_pilot_exclusion_from_main(main_keys, pilot_keys)


def test_assert_main_study_not_generated_passes_clean_dir(tmp_path: Path) -> None:
    """assert_main_study_not_generated passes when no main study files exist."""
    assert_main_study_not_generated(tmp_path)


def test_assert_main_study_not_generated_fails_if_main_file_exists(tmp_path: Path) -> None:
    """assert_main_study_not_generated raises RuntimeError if main study files exist."""
    main_file = tmp_path / "main_study_cases.json"
    main_file.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Main study 240-case generation is UNAUTHORIZED"):
        assert_main_study_not_generated(tmp_path)
