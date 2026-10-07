"""Dataset loading, join verification, and input integrity checks for LONG-002E2."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from tradex.research.long_002e2.spec import (
    D1_FEATURE_TABLE_PATH,
    DEV_END,
    DEV_START,
    E1_PREDICTION_PATH,
    E1_SAFE_ARTIFACT_HASHES,
    E1_SAFE_ARTIFACTS_DIR,
    EXPECTED_D1_FEATURE_TABLE_SHA256,
    EXPECTED_E1_PREDICTION_SHA256,
    EXPECTED_PREDICTION_ROW_COUNT,
    EXPECTED_STAGE_C_BASELINE_SHA256,
    FROZEN_FEATURES,
    JOIN_KEYS,
    POPULATION_CUTOFF,
    STAGE_C_BASELINE_PATH,
    compute_file_sha256,
    verify_e2_spec_hash,
)


def verify_input_integrity(
    e1_pred_path: Path = E1_PREDICTION_PATH,
    d1_feature_path: Path = D1_FEATURE_TABLE_PATH,
    baseline_path: Path = STAGE_C_BASELINE_PATH,
) -> dict[str, str]:
    """Verify all input artifact SHA-256 digests against locked specification constants.

    Fails closed if any file is missing or has a hash mismatch.
    """
    verify_e2_spec_hash()
    digests: dict[str, str] = {}

    # 1. E1 representative prediction parquet
    if not e1_pred_path.exists():
        raise FileNotFoundError(f"E1 representative prediction parquet missing at {e1_pred_path}")
    pred_sha = compute_file_sha256(e1_pred_path)
    if pred_sha != EXPECTED_E1_PREDICTION_SHA256:
        raise ValueError(
            f"E1 PREDICTION PARQUET HASH MISMATCH: {pred_sha} != {EXPECTED_E1_PREDICTION_SHA256}"
        )
    digests["e1_representative_prediction_parquet"] = pred_sha

    # 2. D1 feature table
    if not d1_feature_path.exists():
        raise FileNotFoundError(f"D1 feature table missing at {d1_feature_path}")
    d1_sha = compute_file_sha256(d1_feature_path)
    if d1_sha != EXPECTED_D1_FEATURE_TABLE_SHA256:
        raise ValueError(
            f"D1 FEATURE TABLE HASH MISMATCH: {d1_sha} != {EXPECTED_D1_FEATURE_TABLE_SHA256}"
        )
    digests["d1_feature_table"] = d1_sha

    # 3. Stage C baseline outputs
    if not baseline_path.exists():
        raise FileNotFoundError(f"Stage C baseline outputs missing at {baseline_path}")
    base_sha = compute_file_sha256(baseline_path)
    if base_sha != EXPECTED_STAGE_C_BASELINE_SHA256:
        raise ValueError(
            f"STAGE C BASELINE HASH MISMATCH: {base_sha} != {EXPECTED_STAGE_C_BASELINE_SHA256}"
        )
    digests["stage_c_baseline_comparator_outputs"] = base_sha

    # 4. Committed E1 safe artifacts
    if not E1_SAFE_ARTIFACTS_DIR.exists():
        raise FileNotFoundError(f"E1 safe artifacts directory missing at {E1_SAFE_ARTIFACTS_DIR}")
    for filename, expected_sha in E1_SAFE_ARTIFACT_HASHES.items():
        artifact_path = E1_SAFE_ARTIFACTS_DIR / filename
        if not artifact_path.exists():
            raise FileNotFoundError(f"E1 safe artifact missing: {artifact_path}")
        computed_sha = compute_file_sha256(artifact_path)
        if computed_sha != expected_sha:
            raise ValueError(
                f"E1 SAFE ARTIFACT HASH MISMATCH ({filename}): {computed_sha} != {expected_sha}"
            )
        digests[f"e1_safe_artifact_{filename}"] = computed_sha

    return digests


def enforce_split_guards(dates: pd.Series) -> None:
    """Enforce strict date bounds. Fails closed on validation, holdout, or shadow dates."""
    min_date = str(dates.min())
    max_date = str(dates.max())

    if min_date < DEV_START:
        raise ValueError(
            f"SPLIT GUARD BREACH: Found date {min_date} prior to DEV_START {DEV_START}"
        )

    # Validation quarantine
    val_dates = dates[(dates >= "2021-01-01") & (dates <= "2022-12-31")]
    if len(val_dates) > 0:
        raise ValueError(f"QUARANTINE BREACH: Validation dates present! {val_dates.iloc[0]}")

    # Holdout quarantine
    hold_dates = dates[(dates >= "2023-01-01") & (dates <= "2025-12-31")]
    if len(hold_dates) > 0:
        raise ValueError(f"QUARANTINE BREACH: Holdout dates present! {hold_dates.iloc[0]}")

    # Shadow quarantine
    shadow_dates = dates[dates >= "2026-01-01"]
    if len(shadow_dates) > 0:
        raise ValueError(f"QUARANTINE BREACH: Shadow dates present! {shadow_dates.iloc[0]}")

    if max_date > DEV_END:
        raise ValueError(f"SPLIT GUARD BREACH: Found date {max_date} after DEV_END {DEV_END}")


def load_e2_datasets(
    e1_pred_path: Path = E1_PREDICTION_PATH,
    d1_feature_path: Path = D1_FEATURE_TABLE_PATH,
    baseline_path: Path = STAGE_C_BASELINE_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Load and cross-verify datasets for LONG-002E2 diagnostic.

    Returns:
        (df_pred, df_vam5, df_features, digests)
    """
    digests = verify_input_integrity(e1_pred_path, d1_feature_path, baseline_path)

    # 1. Load E1 LOGIT_S4_C300 predictions
    df_pred = pq.read_table(e1_pred_path).to_pandas()
    if len(df_pred) != EXPECTED_PREDICTION_ROW_COUNT:
        raise ValueError(
            f"PREDICTION ROW COUNT MISMATCH: {len(df_pred)} != {EXPECTED_PREDICTION_ROW_COUNT}"
        )

    # Enforce cutoff & date bounds
    if (df_pred["cutoff_time"] != POPULATION_CUTOFF).any():
        raise ValueError("NON-20:30 ROWS FOUND in predictions!")
    enforce_split_guards(df_pred["as_of_date"])

    dups = df_pred.duplicated(subset=JOIN_KEYS).sum()
    if dups > 0:
        raise ValueError(f"DUPLICATE JOIN KEYS IN PREDICTIONS: {dups}")

    eval_dates = sorted(df_pred["as_of_date"].unique().tolist())
    if len(eval_dates) != 730:
        raise ValueError(f"EVALUATION DATES COUNT MISMATCH: {len(eval_dates)} != 730")

    # 2. Load Stage C baseline outputs (VAM5)
    cols_base = [
        "immutable_security_id",
        "as_of_date",
        "cutoff_time",
        "comparator_id",
        "cross_sectional_rank",
        "cross_sectional_percentile",
        "top_10_flag",
        "top_25_flag",
        "raw_score_or_return",
    ]
    filters_base = [
        ("comparator_id", "=", "volatility_aware_momentum_5"),
        ("cutoff_time", "=", POPULATION_CUTOFF),
    ]
    df_vam5 = pq.read_table(baseline_path, columns=cols_base, filters=filters_base).to_pandas()
    df_vam5 = df_vam5[df_vam5["as_of_date"].isin(eval_dates)].copy()

    # Verify 1:1 join with predictions on evaluation population
    merged_check = df_pred[JOIN_KEYS].merge(
        df_vam5[JOIN_KEYS],
        on=JOIN_KEYS,
        how="inner",
        validate="one_to_one",
    )
    if len(merged_check) != EXPECTED_PREDICTION_ROW_COUNT:
        raise ValueError(
            f"BASELINE POPULATION MISMATCH: {len(merged_check)} != {EXPECTED_PREDICTION_ROW_COUNT}"
        )

    # 3. Load D1 feature table
    cols_feat = JOIN_KEYS + FROZEN_FEATURES + ["spy_return_20"]
    filters_feat = [("cutoff_time", "=", POPULATION_CUTOFF)]
    df_features = pq.read_table(
        d1_feature_path, columns=cols_feat, filters=filters_feat
    ).to_pandas()
    df_features = df_features[df_features["as_of_date"].isin(eval_dates)].copy()

    # Check join with feature table
    feat_merged = df_pred[JOIN_KEYS].merge(
        df_features[JOIN_KEYS],
        on=JOIN_KEYS,
        how="inner",
        validate="one_to_one",
    )
    if len(feat_merged) != EXPECTED_PREDICTION_ROW_COUNT:
        raise ValueError(
            f"FEATURE TABLE POPULATION MISMATCH: {len(feat_merged)} != {EXPECTED_PREDICTION_ROW_COUNT}"
        )

    # Check no nulls in frozen features
    nulls = df_features[FROZEN_FEATURES].isnull().sum()
    if nulls.sum() > 0:
        raise ValueError(f"NULL FEATURE VALUES FOUND: {nulls[nulls > 0].to_dict()}")

    return df_pred, df_vam5, df_features, digests
