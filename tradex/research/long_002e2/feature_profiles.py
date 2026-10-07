"""Feature-profile drift descriptive diagnostics for LONG-002E2."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from tradex.research.long_002e2.spec import FROZEN_FEATURES


def compute_cross_sectional_feature_percentiles(
    df_features: pd.DataFrame,
) -> pd.DataFrame:
    """Compute deterministic within-date cross-sectional percentile ranks for the 8 frozen features.

    Method:
    - On each date, valid observations sorted descending by feature value.
    - Tie-break: immutable_security_id ASC.
    - Percentile: 100.0 * (n_valid - rank_idx) / n_valid.
    """
    df_out = df_features[["immutable_security_id", "as_of_date", "cutoff_time"]].copy()

    sec_ids = df_features["immutable_security_id"].to_numpy()
    dates = df_features["as_of_date"].to_numpy()

    date_to_indices: dict[str, list[int]] = {}
    for idx, d in enumerate(dates):
        date_to_indices.setdefault(d, []).append(idx)

    for f in FROZEN_FEATURES:
        feat_vals = df_features[f].to_numpy(dtype=float)
        pct_col = np.full(len(df_features), np.nan, dtype=float)

        for d, row_indices in date_to_indices.items():
            n = len(row_indices)
            if n == 0:
                continue

            # Sort descending by value, tie-break sec_id ASC
            sorted_indices = sorted(
                row_indices,
                key=lambda idx: (-feat_vals[idx], sec_ids[idx]),
            )
            for rank_idx, orig_idx in enumerate(sorted_indices):
                pct = 100.0 * (n - rank_idx) / n
                pct_col[orig_idx] = pct

        df_out[f"{f}_percentile"] = pct_col

    return df_out


def evaluate_feature_profile_drift(
    df_percentiles: pd.DataFrame,
    df_logit_only: pd.DataFrame,
    df_vam5_only: pd.DataFrame,
) -> dict[str, Any]:
    """Compare the feature percentile profiles of LOGIT_ONLY vs VAM5_ONLY selections."""
    join_keys = ["immutable_security_id", "as_of_date", "cutoff_time"]
    pct_cols = [f"{f}_percentile" for f in FROZEN_FEATURES]

    # Merge percentile ranks onto the selection subsets
    logit_merged = df_logit_only[join_keys].merge(
        df_percentiles[join_keys + pct_cols],
        on=join_keys,
        how="inner",
    )
    vam5_merged = df_vam5_only[join_keys].merge(
        df_percentiles[join_keys + pct_cols],
        on=join_keys,
        how="inner",
    )

    logit_merged["year"] = logit_merged["as_of_date"].str[:4]
    vam5_merged["year"] = vam5_merged["as_of_date"].str[:4]

    years = ["2018", "2019", "2020"]
    annual_profiles: dict[str, list[dict[str, Any]]] = {}

    for yr in years:
        l_yr = logit_merged[logit_merged["year"] == yr]
        v_yr = vam5_merged[vam5_merged["year"] == yr]

        feat_list: list[dict[str, Any]] = []
        for f in FROZEN_FEATURES:
            col = f"{f}_percentile"
            l_vals = l_yr[col].dropna().to_numpy()
            v_vals = v_yr[col].dropna().to_numpy()

            l_mean = float(np.mean(l_vals)) if len(l_vals) > 0 else 0.0
            v_mean = float(np.mean(v_vals)) if len(v_vals) > 0 else 0.0
            l_med = float(np.median(l_vals)) if len(l_vals) > 0 else 0.0
            v_med = float(np.median(v_vals)) if len(v_vals) > 0 else 0.0

            feat_list.append(
                {
                    "feature": f,
                    "logit_only_mean_percentile": round(l_mean, 2),
                    "vam5_only_mean_percentile": round(v_mean, 2),
                    "mean_percentile_difference": round(l_mean - v_mean, 2),
                    "logit_only_median_percentile": round(l_med, 2),
                    "vam5_only_median_percentile": round(v_med, 2),
                    "median_percentile_difference": round(l_med - v_med, 2),
                }
            )
        annual_profiles[yr] = feat_list

    # Overall profile
    overall_list: list[dict[str, Any]] = []
    for f in FROZEN_FEATURES:
        col = f"{f}_percentile"
        l_vals = logit_merged[col].dropna().to_numpy()
        v_vals = vam5_merged[col].dropna().to_numpy()

        l_mean = float(np.mean(l_vals)) if len(l_vals) > 0 else 0.0
        v_mean = float(np.mean(v_vals)) if len(v_vals) > 0 else 0.0
        l_med = float(np.median(l_vals)) if len(l_vals) > 0 else 0.0
        v_med = float(np.median(v_vals)) if len(v_vals) > 0 else 0.0

        overall_list.append(
            {
                "feature": f,
                "logit_only_mean_percentile": round(l_mean, 2),
                "vam5_only_mean_percentile": round(v_mean, 2),
                "mean_percentile_difference": round(l_mean - v_mean, 2),
                "logit_only_median_percentile": round(l_med, 2),
                "vam5_only_median_percentile": round(v_med, 2),
                "median_percentile_difference": round(l_med - v_med, 2),
            }
        )

    return {
        "features_evaluated": FROZEN_FEATURES,
        "methodology": "Within-date cross-sectional percentile rank, higher is higher value, sec_id ASC tie-break.",
        "overall": overall_list,
        "by_year": annual_profiles,
    }
