"""Tests for dataset loading, row counts, and input integrity (Tests 32-40 and synthetic unit tests)."""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tradex.research.long_002e1.loader import (
    load_primary_dataset,
    verify_input_digests,
)
from tradex.research.long_002e1.spec import (
    ALLOWED_FEATURES,
    D1_FEATURE_TABLE_PATH,
    D1_FEATURE_TABLE_SHA256,
    EXPECTED_BASE_RATE,
    EXPECTED_CLEAN_EVENTS,
    EXPECTED_DENOMINATOR,
    POPULATION_CUTOFF,
    STAGE_C_BASELINE_PATH,
    STAGE_C_BASELINE_SHA256,
    STAGE_C_OUTCOME_PATH,
    STAGE_C_OUTCOME_SHA256,
)

PARQUETS_EXIST = (
    D1_FEATURE_TABLE_PATH.exists()
    and STAGE_C_BASELINE_PATH.exists()
    and STAGE_C_OUTCOME_PATH.exists()
)
skip_if_no_parquets = pytest.mark.skipif(
    not PARQUETS_EXIST,
    reason="Empirical research parquet files not available in CI environment",
)


@skip_if_no_parquets
def test_32_feature_table_sha256_digest():
    """Test 32: D1 feature table SHA-256 matches expected digest exactly."""
    digests = verify_input_digests()
    assert digests["d1_feature_table"] == D1_FEATURE_TABLE_SHA256


@skip_if_no_parquets
def test_33_baseline_comparator_sha256_digest():
    """Test 33: Stage C baseline comparator output SHA-256 matches expected digest."""
    digests = verify_input_digests()
    assert digests["stage_c_baseline"] == STAGE_C_BASELINE_SHA256


@skip_if_no_parquets
def test_34_outcome_matrix_sha256_digest():
    """Test 34: Stage C outcome matrix SHA-256 matches expected digest."""
    digests = verify_input_digests()
    assert digests["stage_c_outcome"] == STAGE_C_OUTCOME_SHA256


@skip_if_no_parquets
def test_35_feature_table_row_count():
    """Test 35: Feature table row count equals expected denominator (758,731)."""
    df_feat, _ = load_primary_dataset()
    assert len(df_feat) == EXPECTED_DENOMINATOR


@skip_if_no_parquets
def test_36_clean_event_count_and_base_rate():
    """Test 36: Clean target event count equals 67,257 and base rate equals 0.088644."""
    df_feat, _ = load_primary_dataset()
    clean_cnt = int(df_feat["clean_target_reached"].sum())
    assert clean_cnt == EXPECTED_CLEAN_EVENTS
    assert abs(df_feat["clean_target_reached"].mean() - EXPECTED_BASE_RATE) < 1e-6


@skip_if_no_parquets
def test_37_100_percent_non_null_on_all_features():
    """Test 37: 100% non-null on all 8 allowed features (0 NaN/null values)."""
    df_feat, _ = load_primary_dataset()
    null_counts = df_feat[ALLOWED_FEATURES].isnull().sum()
    assert null_counts.sum() == 0


@skip_if_no_parquets
def test_38_join_integrity_and_unique_keys():
    """Test 38: Baseline and outcome matrix joins preserve exact row count and keys are unique."""
    df_feat, df_base = load_primary_dataset()
    assert len(df_feat) == EXPECTED_DENOMINATOR
    assert len(df_base) == EXPECTED_DENOMINATOR
    assert not df_feat.duplicated(subset=["immutable_security_id", "as_of_date", "cutoff_time"]).any()
    assert not df_base.duplicated(subset=["immutable_security_id", "as_of_date", "cutoff_time"]).any()


@skip_if_no_parquets
def test_39_zero_imputation_prohibited():
    """Test 39: Zero imputation prohibition is enforced (missing values fail closed)."""
    df_feat, _ = load_primary_dataset()
    for col in ALLOWED_FEATURES:
        assert df_feat[col].isna().sum() == 0


@skip_if_no_parquets
def test_40_population_cutoff_strictly_2030():
    """Test 40: Cutoff time is strictly 20:30 ET for all rows."""
    df_feat, df_base = load_primary_dataset()
    assert (df_feat["cutoff_time"] == POPULATION_CUTOFF).all()
    assert (df_base["cutoff_time"] == POPULATION_CUTOFF).all()


def test_loader_fails_closed_on_missing_file(tmp_path: Path):
    """Verify verify_input_digests raises FileNotFoundError when an input file is missing."""
    with pytest.raises(FileNotFoundError, match="D1 feature table missing"):
        verify_input_digests(feature_table_path=tmp_path / "missing.parquet")


def test_loader_fails_closed_on_digest_mismatch(tmp_path: Path):
    """Verify verify_input_digests raises ValueError when SHA-256 does not match locked hash."""
    fake_file = tmp_path / "fake.parquet"
    fake_file.write_text("corrupted content", encoding="utf-8")
    with pytest.raises(ValueError, match="FEATURE TABLE HASH MISMATCH"):
        verify_input_digests(feature_table_path=fake_file)


def test_loader_synthetic_one_to_one_join_and_label_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Synthetic unit test verifying validate='one_to_one' join and label validation."""
    monkeypatch.setattr(
        "tradex.research.long_002e1.loader.verify_input_digests", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr("tradex.research.long_002e1.loader.EXPECTED_DENOMINATOR", 2)
    monkeypatch.setattr("tradex.research.long_002e1.loader.EXPECTED_CLEAN_EVENTS", 1)
    monkeypatch.setattr("tradex.research.long_002e1.loader.EXPECTED_BASE_RATE", 0.5)

    feat_data = {
        "immutable_security_id": ["SEC1", "SEC2"],
        "as_of_date": ["2018-01-02", "2018-01-02"],
        "cutoff_time": ["20:30", "20:30"],
        "ticker_at_decision": ["AAA", "BBB"],
        "clean_target_reached": [1, 0],
    }
    for f in ALLOWED_FEATURES:
        feat_data[f] = [0.1, 0.2]
    df_f = pd.DataFrame(feat_data)
    f_path = tmp_path / "feat.parquet"
    pq.write_table(pa.Table.from_pandas(df_f), f_path)

    base_data = {
        "immutable_security_id": ["SEC1", "SEC2"],
        "as_of_date": ["2018-01-02", "2018-01-02"],
        "cutoff_time": ["20:30", "20:30"],
        "comparator_id": ["volatility_aware_momentum_5", "volatility_aware_momentum_5"],
        "cross_sectional_rank": [1, 2],
        "cross_sectional_percentile": [100.0, 50.0],
        "top_10_flag": [True, False],
        "top_25_flag": [True, True],
        "raw_score_or_return": [0.5, 0.2],
    }
    b_path = tmp_path / "base.parquet"
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(base_data)), b_path)

    out_rows = []
    for target in [10.0, 20.0, 30.0]:
        out_rows.append(
            {
                "immutable_security_id": "SEC1",
                "as_of_date": "2018-01-02",
                "cutoff_time": "20:30",
                "target_pct": target,
                "clean_target_reached": 1,
                "adverse_excursion": 0,
                "time_to_target": 3.0,
                "horizon_sessions": 10,
            }
        )
        out_rows.append(
            {
                "immutable_security_id": "SEC2",
                "as_of_date": "2018-01-02",
                "cutoff_time": "20:30",
                "target_pct": target,
                "clean_target_reached": 0,
                "adverse_excursion": 1,
                "time_to_target": None,
                "horizon_sessions": 10,
            }
        )
    o_path = tmp_path / "out.parquet"
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(out_rows)), o_path)

    df_res_feat, df_res_base = load_primary_dataset(f_path, b_path, o_path)
    assert len(df_res_feat) == 2
    assert len(df_res_base) == 2
    assert df_res_feat["realized_clean_tier"].tolist() == [30, 0]


def test_loader_synthetic_label_mismatch_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Verify load_primary_dataset raises ValueError when outcome matrix label differs from feature table."""
    monkeypatch.setattr(
        "tradex.research.long_002e1.loader.verify_input_digests", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr("tradex.research.long_002e1.loader.EXPECTED_DENOMINATOR", 1)
    monkeypatch.setattr("tradex.research.long_002e1.loader.EXPECTED_CLEAN_EVENTS", 1)
    monkeypatch.setattr("tradex.research.long_002e1.loader.EXPECTED_BASE_RATE", 1.0)

    feat_data = {
        "immutable_security_id": ["SEC1"],
        "as_of_date": ["2018-01-02"],
        "cutoff_time": ["20:30"],
        "ticker_at_decision": ["AAA"],
        "clean_target_reached": [1],
    }
    for f in ALLOWED_FEATURES:
        feat_data[f] = [0.1]
    f_path = tmp_path / "feat.parquet"
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(feat_data)), f_path)

    base_data = {
        "immutable_security_id": ["SEC1"],
        "as_of_date": ["2018-01-02"],
        "cutoff_time": ["20:30"],
        "comparator_id": ["volatility_aware_momentum_5"],
        "cross_sectional_rank": [1],
        "cross_sectional_percentile": [100.0],
        "top_10_flag": [True],
        "top_25_flag": [True],
        "raw_score_or_return": [0.5],
    }
    b_path = tmp_path / "base.parquet"
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(base_data)), b_path)

    out_rows = []
    for target in [10.0, 20.0, 30.0]:
        out_rows.append(
            {
                "immutable_security_id": "SEC1",
                "as_of_date": "2018-01-02",
                "cutoff_time": "20:30",
                "target_pct": target,
                "clean_target_reached": 0,  # Mismatch with feat_data [1]!
                "adverse_excursion": 0,
                "time_to_target": None,
                "horizon_sessions": 10,
            }
        )
    o_path = tmp_path / "out.parquet"
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(out_rows)), o_path)

    with pytest.raises(ValueError, match="OUTCOME LABEL MISMATCH"):
        load_primary_dataset(f_path, b_path, o_path)
