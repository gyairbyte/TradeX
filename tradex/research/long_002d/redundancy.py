"""Pairwise redundancy and Spearman correlation analysis for LONG-002D1."""
from __future__ import annotations

from typing import Any

import pandas as pd


def compute_pairwise_redundancy(
    df_features: pd.DataFrame,
    feature_ids: list[str],
    threshold: float = 0.95,
) -> tuple[pd.DataFrame, list[dict[str, Any]], set[str]]:
    """Compute pairwise Spearman rank correlations on the common non-null subset.

    Parameters:
        df_features: DataFrame containing feature columns.
        feature_ids: list of feature names to correlate.
        threshold: absolute correlation threshold to flag as high_redundancy_candidate.

    Returns:
        (df_corr_matrix, high_redundancy_pairs, high_redundancy_features)
    """
    # Restrict to requested feature columns
    sub_df = df_features[feature_ids].dropna()

    n_common = len(sub_df)
    corr_matrix = sub_df.corr(method="spearman").round(4)

    high_pairs: list[dict[str, Any]] = []
    high_features: set[str] = set()

    for i, f1 in enumerate(feature_ids):
        for j in range(i + 1, len(feature_ids)):
            f2 = feature_ids[j]
            rho_val = float(corr_matrix.loc[f1, f2])

            if abs(rho_val) >= threshold:
                high_pairs.append({
                    "feature_1": f1,
                    "feature_2": f2,
                    "spearman_rho": rho_val,
                    "common_sample_size": n_common,
                    "flag": "high_redundancy_candidate",
                })
                high_features.add(f1)
                high_features.add(f2)

    return corr_matrix, high_pairs, high_features
