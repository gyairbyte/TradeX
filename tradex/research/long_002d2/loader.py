"""Dataset loading, join verification, and input integrity checks for LONG-002D2."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from tradex.research.long_002d2.models import InputIntegrityAudit
from tradex.research.long_002d2.spec import (
    D1_FEATURE_TABLE_PATH,
    D1_FEATURE_TABLE_SHA256,
    DEV_END,
    DEV_START,
    EXPECTED_DENOMINATOR,
    FROZEN_BASELINE_ID,
    POPULATION_CUTOFF,
    STAGE_C_BASELINE_PATH,
    STAGE_C_BASELINE_SHA256,
    STAGE_C_OUTCOME_PATH,
    STAGE_C_OUTCOME_SHA256,
    enforce_cutoff_guard,
    enforce_split_guard,
)


def compute_file_sha256(path: Path) -> str:
    """Compute the SHA-256 digest of a file in streaming chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def verify_input_hashes(
    feature_table_path: Path = D1_FEATURE_TABLE_PATH,
    baseline_path: Path = STAGE_C_BASELINE_PATH,
    outcome_matrix_path: Path | None = STAGE_C_OUTCOME_PATH,
) -> dict[str, str]:
    """Verify input parquet SHA-256 digests against locked spec hashes."""
    if not feature_table_path.exists():
        raise FileNotFoundError(f"D1 feature table missing at {feature_table_path}")
    if not baseline_path.exists():
        raise FileNotFoundError(f"Stage C baseline outputs missing at {baseline_path}")

    feat_sha = compute_file_sha256(feature_table_path)
    if feat_sha != D1_FEATURE_TABLE_SHA256:
        raise ValueError(
            f"D1 FEATURE TABLE HASH MISMATCH: {feat_sha} != {D1_FEATURE_TABLE_SHA256}"
        )

    base_sha = compute_file_sha256(baseline_path)
    if base_sha != STAGE_C_BASELINE_SHA256:
        raise ValueError(
            f"BASELINE OUTPUTS HASH MISMATCH: {base_sha} != {STAGE_C_BASELINE_SHA256}"
        )

    out_sha = None
    if outcome_matrix_path is not None and outcome_matrix_path.exists():
        out_sha = compute_file_sha256(outcome_matrix_path)
        if out_sha != STAGE_C_OUTCOME_SHA256:
            raise ValueError(
                f"OUTCOME MATRIX HASH MISMATCH: {out_sha} != {STAGE_C_OUTCOME_SHA256}"
            )

    return {
        "feature_table_sha256": feat_sha,
        "baseline_sha256": base_sha,
        "outcome_matrix_sha256": out_sha or "not_used_or_absent",
    }


def load_and_verify_datasets(
    feature_table_path: Path = D1_FEATURE_TABLE_PATH,
    baseline_path: Path = STAGE_C_BASELINE_PATH,
    outcome_matrix_path: Path | None = STAGE_C_OUTCOME_PATH,
) -> tuple[pd.DataFrame, InputIntegrityAudit]:
    """Load, verify, and join D1 feature table with frozen VAM5 baseline outputs.

    Fail-closed guarantees:
    - Rejects any file failing SHA-256.
    - Rejects dates outside development window (2016-01-01 to 2020-12-31).
    - Rejects cutoffs other than 20:30.
    - Rejects duplicate join keys.
    - Asserts exactly one-to-one join cardinality.
    - Zero network or provider calls.
    """
    hashes = verify_input_hashes(feature_table_path, baseline_path, outcome_matrix_path)

    # 1. Load D1 feature table
    feat_cols = [
        "immutable_security_id",
        "as_of_date",
        "cutoff_time",
        "clean_target_reached",
        "relative_volume_20",
        "sma20_slope_5",
        "spy_return_20",
    ]
    df_feat = pq.read_table(
        feature_table_path,
        columns=feat_cols,
        filters=[("cutoff_time", "=", POPULATION_CUTOFF)],
    ).to_pandas()

    feat_rows = len(df_feat)
    if feat_rows != EXPECTED_DENOMINATOR:
        raise ValueError(
            f"POPULATION DENOMINATOR DRIFT: Expected {EXPECTED_DENOMINATOR}, found {feat_rows} rows"
        )

    # 2. Load frozen VAM5 baseline outputs
    base_cols = [
        "immutable_security_id",
        "as_of_date",
        "cutoff_time",
        "comparator_id",
        "cross_sectional_rank",
        "raw_score_or_return",
        "top_10_flag",
        "top_25_flag",
    ]
    df_base = pq.read_table(
        baseline_path,
        columns=base_cols,
        filters=[
            ("cutoff_time", "=", POPULATION_CUTOFF),
            ("comparator_id", "=", FROZEN_BASELINE_ID),
        ],
    ).to_pandas()

    base_rows = len(df_base)

    # 3. Validate dates and cutoffs
    for d in df_feat["as_of_date"].unique():
        enforce_split_guard(str(d))
    for c in df_feat["cutoff_time"].unique():
        enforce_cutoff_guard(str(c))

    for d in df_base["as_of_date"].unique():
        enforce_split_guard(str(d))
    for c in df_base["cutoff_time"].unique():
        enforce_cutoff_guard(str(c))

    # 4. Check join key uniqueness
    join_keys = ["immutable_security_id", "as_of_date", "cutoff_time"]
    if df_feat.duplicated(subset=join_keys).any():
        raise ValueError("DUPLICATE KEYS in D1 feature table!")
    if df_base.duplicated(subset=join_keys).any():
        raise ValueError("DUPLICATE KEYS in Stage C baseline outputs!")

    # 5. Merge datasets (1:1 inner join)
    merged = pd.merge(df_feat, df_base, on=join_keys, how="inner")
    if len(merged) != EXPECTED_DENOMINATOR:
        raise ValueError(
            f"JOIN CARDINALITY MISMATCH: Expected {EXPECTED_DENOMINATOR} merged rows, got {len(merged)}"
        )

    # Check outcome labels
    if merged["clean_target_reached"].isna().any():
        raise ValueError("NULL OUTCOME LABELS detected in joined dataset!")

    audit = InputIntegrityAudit(
        feature_table_path=str(feature_table_path),
        feature_table_sha256=hashes["feature_table_sha256"],
        feature_table_rows=feat_rows,
        baseline_path=str(baseline_path),
        baseline_sha256=hashes["baseline_sha256"],
        baseline_rows=base_rows,
        outcome_matrix_path=str(outcome_matrix_path) if outcome_matrix_path and outcome_matrix_path.exists() else None,
        outcome_matrix_sha256=hashes.get("outcome_matrix_sha256"),
        zero_validation_rows=True,
        zero_holdout_rows=True,
        zero_shadow_rows=True,
        zero_network_calls=True,
        join_keys_unique=True,
        all_dates_within_dev=True,
        all_cutoffs_20_30=True,
        gates_passed=True,
        gate_details={
            "merged_rows": len(merged),
            "dev_start": DEV_START,
            "dev_end": DEV_END,
            "cutoff": POPULATION_CUTOFF,
        },
    )

    return merged, audit
