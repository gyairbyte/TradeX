"""Integration and boundary tests for dataset loading and join verification."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tradex.research.long_002d2.loader import (
    compute_file_sha256,
    load_and_verify_datasets,
    verify_input_hashes,
)
from tradex.research.long_002d2.spec import (
    D1_FEATURE_TABLE_PATH,
    D1_FEATURE_TABLE_SHA256,
    EXPECTED_DENOMINATOR,
    STAGE_C_BASELINE_PATH,
    STAGE_C_BASELINE_SHA256,
)

# ======================================================================
# Real-artifact tests (Skipped in CI when large Parquets are absent)
# ======================================================================


def test_verify_input_hashes_succeeds() -> None:
    """Verify that verify_input_hashes confirms the exact expected digests when artifacts are present."""
    if not D1_FEATURE_TABLE_PATH.exists() or not STAGE_C_BASELINE_PATH.exists():
        pytest.skip("Large external Parquet files absent in environment")
    hashes = verify_input_hashes()
    assert hashes["feature_table_sha256"] == D1_FEATURE_TABLE_SHA256
    assert hashes["baseline_sha256"] == STAGE_C_BASELINE_SHA256


def test_load_and_verify_datasets_real_inputs() -> None:
    """Verify that load_and_verify_datasets loads the exact expected denominator when artifacts are present."""
    if not D1_FEATURE_TABLE_PATH.exists() or not STAGE_C_BASELINE_PATH.exists():
        pytest.skip("Large external Parquet files absent in environment")
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


# ======================================================================
# Synthetic Unit Tests (Fail-Closed & Schema Verification in CI)
# ======================================================================


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    table = pa.Table.from_pandas(df)
    pq.write_table(table, path)


def test_verify_input_hashes_missing_files(tmp_path: Path) -> None:
    """Missing input files must fail closed with FileNotFoundError."""
    missing_feat = tmp_path / "missing_feat.parquet"
    missing_base = tmp_path / "missing_base.parquet"

    with pytest.raises(FileNotFoundError, match="D1 feature table missing"):
        verify_input_hashes(feature_table_path=missing_feat, baseline_path=missing_base)

    dummy_feat = tmp_path / "dummy_feat.parquet"
    dummy_feat.write_bytes(b"dummy")
    with pytest.raises(FileNotFoundError, match="Stage C baseline outputs missing"):
        verify_input_hashes(feature_table_path=dummy_feat, baseline_path=missing_base)


def test_verify_input_hashes_bad_sha(tmp_path: Path) -> None:
    """Files with mismatched hashes must fail closed with ValueError."""
    dummy_feat = tmp_path / "feat.parquet"
    dummy_feat.write_bytes(b"bad feature bytes")
    dummy_base = tmp_path / "base.parquet"
    dummy_base.write_bytes(b"bad baseline bytes")

    with pytest.raises(ValueError, match="D1 FEATURE TABLE HASH MISMATCH"):
        verify_input_hashes(feature_table_path=dummy_feat, baseline_path=dummy_base)

    # If feature table hash matches, baseline hash mismatch must still fail
    feat_sha = compute_file_sha256(dummy_feat)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("tradex.research.long_002d2.loader.D1_FEATURE_TABLE_SHA256", feat_sha)
        with pytest.raises(ValueError, match="BASELINE OUTPUTS HASH MISMATCH"):
            verify_input_hashes(feature_table_path=dummy_feat, baseline_path=dummy_base)

    # If both match, bad outcome matrix must fail
    base_sha = compute_file_sha256(dummy_base)
    dummy_out = tmp_path / "out.parquet"
    dummy_out.write_bytes(b"bad outcome bytes")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("tradex.research.long_002d2.loader.D1_FEATURE_TABLE_SHA256", feat_sha)
        mp.setattr("tradex.research.long_002d2.loader.STAGE_C_BASELINE_SHA256", base_sha)
        with pytest.raises(ValueError, match="OUTCOME MATRIX HASH MISMATCH"):
            verify_input_hashes(
                feature_table_path=dummy_feat,
                baseline_path=dummy_base,
                outcome_matrix_path=dummy_out,
            )


def test_load_and_verify_datasets_synthetic_success_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthetic dataset test covering successful load, denominator drift, split guards, and duplicate keys."""
    feat_path = tmp_path / "feat.parquet"
    base_path = tmp_path / "base.parquet"

    feat_df = pd.DataFrame({
        "immutable_security_id": ["sec_1", "sec_2"],
        "as_of_date": ["2018-05-01", "2018-05-01"],
        "cutoff_time": ["20:30", "20:30"],
        "clean_target_reached": [1, 0],
        "relative_volume_20": [1.5, 0.8],
        "sma20_slope_5": [0.02, -0.01],
        "spy_return_20": [0.015, 0.015],
    })
    base_df = pd.DataFrame({
        "immutable_security_id": ["sec_1", "sec_2"],
        "as_of_date": ["2018-05-01", "2018-05-01"],
        "cutoff_time": ["20:30", "20:30"],
        "comparator_id": ["volatility_aware_momentum_5", "volatility_aware_momentum_5"],
        "cross_sectional_rank": [1, 2],
        "raw_score_or_return": [0.85, 0.42],
        "top_10_flag": [1, 1],
        "top_25_flag": [1, 1],
    })

    _write_parquet(feat_df, feat_path)
    _write_parquet(base_df, base_path)

    # Bypass file hash check for synthetic unit testing
    monkeypatch.setattr(
        "tradex.research.long_002d2.loader.verify_input_hashes",
        lambda *args, **kwargs: {
            "feature_table_sha256": "mock_sha_feat",
            "baseline_sha256": "mock_sha_base",
            "outcome_matrix_sha256": "not_used_or_absent",
        },
    )

    # 1. Denominator drift fails closed
    monkeypatch.setattr("tradex.research.long_002d2.loader.EXPECTED_DENOMINATOR", 999)
    with pytest.raises(ValueError, match="POPULATION DENOMINATOR DRIFT"):
        load_and_verify_datasets(feature_table_path=feat_path, baseline_path=base_path, outcome_matrix_path=None)

    # Set expected denominator to 2 for subsequent tests
    monkeypatch.setattr("tradex.research.long_002d2.loader.EXPECTED_DENOMINATOR", 2)

    # 2. Split guard violation fails closed (date in 2021)
    bad_date_feat = feat_df.copy()
    bad_date_feat["as_of_date"] = ["2021-01-05", "2021-01-05"]
    _write_parquet(bad_date_feat, feat_path)
    with pytest.raises(ValueError, match="SPLIT QUARANTINE BREACH"):
        load_and_verify_datasets(feature_table_path=feat_path, baseline_path=base_path, outcome_matrix_path=None)
    _write_parquet(feat_df, feat_path)  # Restore

    # 3. Cutoff guard violation fails closed (cutoff 09:30)
    bad_cutoff_feat = feat_df.copy()
    bad_cutoff_feat["cutoff_time"] = ["09:30", "09:30"]
    _write_parquet(bad_cutoff_feat, feat_path)
    # Note: pq.read_table filters on cutoff_time == POPULATION_CUTOFF, so filtered length will be 0 -> POPULATION DENOMINATOR DRIFT
    with pytest.raises(ValueError, match="POPULATION DENOMINATOR DRIFT"):
        load_and_verify_datasets(feature_table_path=feat_path, baseline_path=base_path, outcome_matrix_path=None)
    _write_parquet(feat_df, feat_path)  # Restore

    # 4. Duplicate join keys fail closed
    dup_feat = pd.DataFrame({
        "immutable_security_id": ["sec_1", "sec_1"],
        "as_of_date": ["2018-05-01", "2018-05-01"],
        "cutoff_time": ["20:30", "20:30"],
        "clean_target_reached": [1, 0],
        "relative_volume_20": [1.5, 0.8],
        "sma20_slope_5": [0.02, -0.01],
        "spy_return_20": [0.015, 0.015],
    })
    _write_parquet(dup_feat, feat_path)
    with pytest.raises(ValueError, match="DUPLICATE KEYS in D1 feature table"):
        load_and_verify_datasets(feature_table_path=feat_path, baseline_path=base_path, outcome_matrix_path=None)
    _write_parquet(feat_df, feat_path)  # Restore

    # 5. Join cardinality mismatch fails closed
    mismatched_base = base_df.copy()
    mismatched_base["immutable_security_id"] = ["sec_99", "sec_100"]
    _write_parquet(mismatched_base, base_path)
    with pytest.raises(ValueError, match="JOIN CARDINALITY MISMATCH"):
        load_and_verify_datasets(feature_table_path=feat_path, baseline_path=base_path, outcome_matrix_path=None)
    _write_parquet(base_df, base_path)  # Restore

    # 6. Null outcome labels fail closed
    null_feat = feat_df.copy()
    null_feat["clean_target_reached"] = [np.nan, 0]
    _write_parquet(null_feat, feat_path)
    with pytest.raises(ValueError, match="NULL OUTCOME LABELS"):
        load_and_verify_datasets(feature_table_path=feat_path, baseline_path=base_path, outcome_matrix_path=None)
    _write_parquet(feat_df, feat_path)  # Restore

    # 7. Success path
    df_merged, audit = load_and_verify_datasets(
        feature_table_path=feat_path,
        baseline_path=base_path,
        outcome_matrix_path=None,
    )
    assert len(df_merged) == 2
    assert audit.gates_passed is True
    assert audit.join_keys_unique is True
    assert audit.all_dates_within_dev is True
    assert audit.all_cutoffs_20_30 is True
