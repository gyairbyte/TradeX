"""Dataset loading, join verification, and input integrity checks for LONG-002E1."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from tradex.research.long_002e1.spec import (
    ALLOWED_FEATURES,
    D1_FEATURE_TABLE_PATH,
    D1_FEATURE_TABLE_SHA256,
    DEV_END,
    DEV_START,
    EXPECTED_BASE_RATE,
    EXPECTED_CLEAN_EVENTS,
    EXPECTED_DENOMINATOR,
    POPULATION_CUTOFF,
    STAGE_C_BASELINE_PATH,
    STAGE_C_BASELINE_SHA256,
    STAGE_C_OUTCOME_PATH,
    STAGE_C_OUTCOME_SHA256,
    compute_file_sha256,
)


def verify_input_digests(
    feature_table_path: Path = D1_FEATURE_TABLE_PATH,
    baseline_path: Path = STAGE_C_BASELINE_PATH,
    outcome_matrix_path: Path = STAGE_C_OUTCOME_PATH,
) -> dict[str, str]:
    """Verify input parquet SHA-256 digests against locked spec hashes.

    Fails closed if any file is missing or hash mismatches.
    """
    digests: dict[str, str] = {}

    if not feature_table_path.exists():
        raise FileNotFoundError(f"D1 feature table missing at {feature_table_path}")
    feat_sha = compute_file_sha256(feature_table_path)
    if feat_sha != D1_FEATURE_TABLE_SHA256:
        raise ValueError(
            f"FEATURE TABLE HASH MISMATCH: {feat_sha} != {D1_FEATURE_TABLE_SHA256}"
        )
    digests["d1_feature_table"] = feat_sha

    if not baseline_path.exists():
        raise FileNotFoundError(f"Stage C baseline outputs missing at {baseline_path}")
    base_sha = compute_file_sha256(baseline_path)
    if base_sha != STAGE_C_BASELINE_SHA256:
        raise ValueError(
            f"BASELINE OUTPUTS HASH MISMATCH: {base_sha} != {STAGE_C_BASELINE_SHA256}"
        )
    digests["stage_c_baseline"] = base_sha

    if not outcome_matrix_path.exists():
        raise FileNotFoundError(f"Stage C outcome matrix missing at {outcome_matrix_path}")
    out_sha = compute_file_sha256(outcome_matrix_path)
    if out_sha != STAGE_C_OUTCOME_SHA256:
        raise ValueError(
            f"OUTCOME MATRIX HASH MISMATCH: {out_sha} != {STAGE_C_OUTCOME_SHA256}"
        )
    digests["stage_c_outcome"] = out_sha

    return digests


def enforce_split_guards(dates: pd.Series) -> None:
    """Enforce strict date bounds. Fails closed on validation, holdout, or shadow dates."""
    min_date = dates.min()
    max_date = dates.max()

    if min_date < DEV_START:
        raise ValueError(f"SPLIT GUARD BREACH: Found date {min_date} prior to DEV_START {DEV_START}")

    # Explicit quarantine assertions
    val_dates = dates[(dates >= "2021-01-01") & (dates <= "2022-12-31")]
    if len(val_dates) > 0:
        raise ValueError(f"QUARANTINE BREACH: Validation dates present! {val_dates.iloc[0]}")

    hold_dates = dates[(dates >= "2023-01-01") & (dates <= "2025-12-31")]
    if len(hold_dates) > 0:
        raise ValueError(f"QUARANTINE BREACH: Holdout dates present! {hold_dates.iloc[0]}")

    shadow_dates = dates[dates >= "2026-01-01"]
    if len(shadow_dates) > 0:
        raise ValueError(f"QUARANTINE BREACH: Shadow dates present! {shadow_dates.iloc[0]}")

    if max_date > DEV_END:
        raise ValueError(f"SPLIT GUARD BREACH: Found date {max_date} after DEV_END {DEV_END}")


def load_primary_dataset(
    feature_table_path: Path = D1_FEATURE_TABLE_PATH,
    baseline_path: Path = STAGE_C_BASELINE_PATH,
    outcome_matrix_path: Path = STAGE_C_OUTCOME_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and verify common development study population and baseline comparator.

    Returns:
        (df_features, df_vam5)
    """
    verify_input_digests(feature_table_path, baseline_path, outcome_matrix_path)

    # 1. Load feature table
    cols_feat = [
        "immutable_security_id",
        "as_of_date",
        "cutoff_time",
        "ticker_at_decision",
        "clean_target_reached",
    ] + ALLOWED_FEATURES

    df_feat = pq.read_table(feature_table_path, columns=cols_feat).to_pandas()

    if len(df_feat) != EXPECTED_DENOMINATOR:
        raise ValueError(
            f"FEATURE TABLE ROW COUNT MISMATCH: {len(df_feat)} != {EXPECTED_DENOMINATOR}"
        )

    # Enforce cutoff
    df_feat = df_feat[df_feat["cutoff_time"] == POPULATION_CUTOFF].copy()
    if len(df_feat) != EXPECTED_DENOMINATOR:
        raise ValueError(
            f"NON-20:30 ROWS FOUND: {len(df_feat)} != {EXPECTED_DENOMINATOR}"
        )

    # Enforce split bounds
    enforce_split_guards(df_feat["as_of_date"])

    # Enforce unique join keys
    dups = df_feat.duplicated(subset=["immutable_security_id", "as_of_date", "cutoff_time"]).sum()
    if dups > 0:
        raise ValueError(f"DUPLICATE JOIN KEYS FOUND: {dups}")

    # Enforce 100% non-null on all 8 frozen features (no zero imputation)
    null_counts = df_feat[ALLOWED_FEATURES].isnull().sum()
    total_nulls = int(null_counts.sum())
    if total_nulls > 0:
        raise ValueError(
            f"MISSING FEATURE VALUES FOUND: {null_counts[null_counts > 0].to_dict()}. "
            "Zero imputation is strictly prohibited."
        )

    # Verify event counts and base rate
    clean_events = int(df_feat["clean_target_reached"].sum())
    if clean_events != EXPECTED_CLEAN_EVENTS:
        raise ValueError(
            f"CLEAN EVENT COUNT MISMATCH: {clean_events} != {EXPECTED_CLEAN_EVENTS}"
        )
    base_rate = float(df_feat["clean_target_reached"].mean())
    if abs(base_rate - EXPECTED_BASE_RATE) > 1e-6:
        raise ValueError(f"BASE RATE MISMATCH: {base_rate} != {EXPECTED_BASE_RATE}")

    # 2. Load frozen baseline comparator outputs (VAM5)
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
    df_base = pq.read_table(baseline_path, columns=cols_base, filters=filters_base).to_pandas()

    if len(df_base) != EXPECTED_DENOMINATOR:
        raise ValueError(
            f"BASELINE ROW COUNT MISMATCH: {len(df_base)} != {EXPECTED_DENOMINATOR}"
        )

    # Check join integrity with feature table
    merged_test = df_feat[["immutable_security_id", "as_of_date", "cutoff_time"]].merge(
        df_base[["immutable_security_id", "as_of_date", "cutoff_time"]],
        on=["immutable_security_id", "as_of_date", "cutoff_time"],
        how="inner",
    )
    if len(merged_test) != EXPECTED_DENOMINATOR:
        raise ValueError(
            f"BASELINE POPULATION MISMATCH: inner join yielded {len(merged_test)} rows != {EXPECTED_DENOMINATOR}"
        )

    # 3. Load secondary outcome matrix columns (+20, +30, adverse excursion, time to target)
    filters_out = [
        ("cutoff_time", "=", POPULATION_CUTOFF),
        ("horizon_sessions", "=", 10),
    ]
    cols_out = [
        "immutable_security_id",
        "as_of_date",
        "cutoff_time",
        "target_pct",
        "clean_target_reached",
        "adverse_excursion",
        "time_to_target",
    ]
    df_out_raw = pq.read_table(outcome_matrix_path, columns=cols_out, filters=filters_out).to_pandas()

    # Pivot target_pct to get clean_10, clean_20, clean_30
    df_10 = df_out_raw[df_out_raw["target_pct"] == 10.0].copy()
    df_20 = df_out_raw[df_out_raw["target_pct"] == 20.0][
        ["immutable_security_id", "as_of_date", "cutoff_time", "clean_target_reached"]
    ].rename(columns={"clean_target_reached": "clean_target_reached_20"})
    df_30 = df_out_raw[df_out_raw["target_pct"] == 30.0][
        ["immutable_security_id", "as_of_date", "cutoff_time", "clean_target_reached"]
    ].rename(columns={"clean_target_reached": "clean_target_reached_30"})

    df_outcomes = df_10.merge(
        df_20, on=["immutable_security_id", "as_of_date", "cutoff_time"], how="inner"
    ).merge(
        df_30, on=["immutable_security_id", "as_of_date", "cutoff_time"], how="inner"
    )

    if len(df_outcomes) != EXPECTED_DENOMINATOR:
        raise ValueError(
            f"OUTCOMES PIVOT ROW COUNT MISMATCH: {len(df_outcomes)} != {EXPECTED_DENOMINATOR}"
        )

    # Compute realized clean tier: 30 if clean_30 else 20 if clean_20 else 10 if clean_10 else 0
    c10 = df_outcomes["clean_target_reached"].astype(bool)
    c20 = df_outcomes["clean_target_reached_20"].astype(bool)
    c30 = df_outcomes["clean_target_reached_30"].astype(bool)

    tier = pd.Series(0, index=df_outcomes.index, dtype=int)
    tier[c10] = 10
    tier[c20] = 20
    tier[c30] = 30
    df_outcomes["realized_clean_tier"] = tier

    # Attach outcome columns to df_feat
    df_feat["realized_clean_tier"] = df_outcomes["realized_clean_tier"]
    df_feat["adverse_excursion"] = df_outcomes["adverse_excursion"]
    df_feat["time_to_target"] = df_outcomes["time_to_target"]

    return df_feat, df_base
