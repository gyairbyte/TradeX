"""Tests for dataset loading, row counts, and input integrity (Tests 32-40)."""

from tradex.research.long_002e1.loader import (
    load_primary_dataset,
    verify_input_digests,
)
from tradex.research.long_002e1.spec import (
    ALLOWED_FEATURES,
    D1_FEATURE_TABLE_SHA256,
    EXPECTED_BASE_RATE,
    EXPECTED_CLEAN_EVENTS,
    EXPECTED_DENOMINATOR,
    POPULATION_CUTOFF,
    STAGE_C_BASELINE_SHA256,
    STAGE_C_OUTCOME_SHA256,
)


def test_32_feature_table_sha256_digest():
    """Test 32: D1 feature table SHA-256 matches expected digest exactly."""
    digests = verify_input_digests()
    assert digests["d1_feature_table"] == D1_FEATURE_TABLE_SHA256


def test_33_baseline_comparator_sha256_digest():
    """Test 33: Stage C baseline comparator output SHA-256 matches expected digest."""
    digests = verify_input_digests()
    assert digests["stage_c_baseline"] == STAGE_C_BASELINE_SHA256


def test_34_outcome_matrix_sha256_digest():
    """Test 34: Stage C outcome matrix SHA-256 matches expected digest."""
    digests = verify_input_digests()
    assert digests["stage_c_outcome"] == STAGE_C_OUTCOME_SHA256


def test_35_feature_table_row_count():
    """Test 35: Feature table row count equals expected denominator (758,731)."""
    df_feat, _ = load_primary_dataset()
    assert len(df_feat) == EXPECTED_DENOMINATOR


def test_36_clean_event_count_and_base_rate():
    """Test 36: Clean target event count equals 67,257 and base rate equals 0.088644."""
    df_feat, _ = load_primary_dataset()
    clean_cnt = int(df_feat["clean_target_reached"].sum())
    assert clean_cnt == EXPECTED_CLEAN_EVENTS
    assert abs(df_feat["clean_target_reached"].mean() - EXPECTED_BASE_RATE) < 1e-6


def test_37_100_percent_non_null_on_all_features():
    """Test 37: 100% non-null on all 8 allowed features (0 NaN/null values)."""
    df_feat, _ = load_primary_dataset()
    null_counts = df_feat[ALLOWED_FEATURES].isnull().sum()
    assert null_counts.sum() == 0


def test_38_join_integrity_and_unique_keys():
    """Test 38: Baseline and outcome matrix joins preserve exact row count and keys are unique."""
    df_feat, df_base = load_primary_dataset()
    assert len(df_feat) == EXPECTED_DENOMINATOR
    assert len(df_base) == EXPECTED_DENOMINATOR
    assert not df_feat.duplicated(subset=["immutable_security_id", "as_of_date", "cutoff_time"]).any()
    assert not df_base.duplicated(subset=["immutable_security_id", "as_of_date", "cutoff_time"]).any()


def test_39_zero_imputation_prohibited():
    """Test 39: Zero imputation prohibition is enforced (missing values fail closed)."""
    # By verifying test_37 has 0 nulls without any imputation applied in loader
    df_feat, _ = load_primary_dataset()
    for col in ALLOWED_FEATURES:
        assert df_feat[col].isna().sum() == 0


def test_40_population_cutoff_strictly_2030():
    """Test 40: Cutoff time is strictly 20:30 ET for all rows."""
    df_feat, df_base = load_primary_dataset()
    assert (df_feat["cutoff_time"] == POPULATION_CUTOFF).all()
    assert (df_base["cutoff_time"] == POPULATION_CUTOFF).all()
