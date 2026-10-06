"""Tests for LONG-002E2 dataset loading, input integrity, and quarantine boundaries."""

from __future__ import annotations

import pandas as pd
import pytest

from tradex.research.long_002e2.loader import (
    enforce_split_guards,
    verify_input_integrity,
)
from tradex.research.long_002e2.spec import (
    E1_PREDICTION_PATH,
    EXPECTED_D1_FEATURE_TABLE_SHA256,
    EXPECTED_E1_PREDICTION_SHA256,
    EXPECTED_STAGE_C_BASELINE_SHA256,
)


def test_10_11_12_input_hashes_match_when_present() -> None:
    """Verify input file hashes match expected digests if files exist locally."""
    if not E1_PREDICTION_PATH.exists():
        pytest.skip("E1 prediction parquet not present in CI environment.")
    digests = verify_input_integrity()
    assert digests["e1_representative_prediction_parquet"] == EXPECTED_E1_PREDICTION_SHA256
    assert digests["d1_feature_table"] == EXPECTED_D1_FEATURE_TABLE_SHA256
    assert digests["stage_c_baseline_comparator_outputs"] == EXPECTED_STAGE_C_BASELINE_SHA256


def test_16_valid_dates_accepted() -> None:
    """Verify 2018-2020 development dates pass split guards."""
    valid_dates = pd.Series(["2018-01-02", "2019-06-15", "2020-11-23"])
    enforce_split_guards(valid_dates)  # should not raise


def test_17_validation_dates_rejected() -> None:
    """Verify 2021-2022 validation dates trigger quarantine breach."""
    val_dates = pd.Series(["2019-01-01", "2021-05-10", "2020-01-01"])
    with pytest.raises(ValueError, match="QUARANTINE BREACH: Validation dates present"):
        enforce_split_guards(val_dates)


def test_18_holdout_dates_rejected() -> None:
    """Verify 2023-2025 holdout dates trigger quarantine breach."""
    hold_dates = pd.Series(["2019-01-01", "2024-03-15", "2020-01-01"])
    with pytest.raises(ValueError, match="QUARANTINE BREACH: Holdout dates present"):
        enforce_split_guards(hold_dates)


def test_19_shadow_dates_rejected() -> None:
    """Verify 2026+ shadow dates trigger quarantine breach."""
    shadow_dates = pd.Series(["2019-01-01", "2026-02-01", "2020-01-01"])
    with pytest.raises(ValueError, match="QUARANTINE BREACH: Shadow dates present"):
        enforce_split_guards(shadow_dates)


def test_pre_dev_dates_rejected() -> None:
    """Verify pre-2018 dates trigger split guard breach."""
    pre_dates = pd.Series(["2017-12-31", "2019-01-01"])
    with pytest.raises(ValueError, match="SPLIT GUARD BREACH"):
        enforce_split_guards(pre_dates)


def test_post_dev_dates_rejected() -> None:
    """Verify dates beyond DEV_END trigger split guard breach."""
    post_dates = pd.Series(["2020-01-01", "2021-01-01"])
    with pytest.raises(ValueError, match="QUARANTINE BREACH: Validation dates present"):
        enforce_split_guards(post_dates)
