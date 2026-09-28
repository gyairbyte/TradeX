"""Integration and boundary tests for dataset loading and join verification."""
from __future__ import annotations

from tradex.research.long_002d2.loader import (
    load_and_verify_datasets,
    verify_input_hashes,
)
from tradex.research.long_002d2.spec import (
    D1_FEATURE_TABLE_SHA256,
    EXPECTED_DENOMINATOR,
    STAGE_C_BASELINE_SHA256,
)


def test_verify_input_hashes_succeeds() -> None:
    """Verify that verify_input_hashes confirms the exact expected digests."""
    hashes = verify_input_hashes()
    assert hashes["feature_table_sha256"] == D1_FEATURE_TABLE_SHA256
    assert hashes["baseline_sha256"] == STAGE_C_BASELINE_SHA256


def test_load_and_verify_datasets_real_inputs() -> None:
    """Verify that load_and_verify_datasets loads the exact expected denominator."""
    df_merged, audit = load_and_verify_datasets()

    assert len(df_merged) == EXPECTED_DENOMINATOR
    assert audit.feature_table_rows == EXPECTED_DENOMINATOR
    assert audit.gates_passed is True
    assert audit.zero_validation_rows is True
    assert audit.zero_holdout_rows is True
    assert audit.zero_shadow_rows is True
    assert audit.zero_network_calls is True
    assert audit.join_keys_unique is True
    assert audit.all_dates_within_dev is True
    assert audit.all_cutoffs_20_30 is True

    # Check required columns
    expected_cols = [
        "immutable_security_id",
        "as_of_date",
        "cutoff_time",
        "clean_target_reached",
        "relative_volume_20",
        "sma20_slope_5",
        "spy_return_20",
        "comparator_id",
        "cross_sectional_rank",
        "raw_score_or_return",
        "top_10_flag",
        "top_25_flag",
    ]
    for col in expected_cols:
        assert col in df_merged.columns
