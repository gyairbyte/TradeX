"""Deterministic cross-sectional rank/score modeling for LONG-002E1."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tradex.research.long_002e1.configs import ConfigurationSpec


def evaluate_rank_model(
    df_eval: pd.DataFrame,
    config: ConfigurationSpec,
) -> pd.Series:
    """Evaluate a transparent rank/score model on evaluation observations.

    For each evaluation date:
    1. Computes cross-sectional percentile ranks for each feature in the subset:
       pct = 100.0 * (N - rank_idx) / N where higher is favorable (sorted DESC with sec_id ASC tie-break).
    2. Candidate score is the weighted sum of feature percentile ranks:
       score = sum(weight_j * pct_j).

    Returns:
        pd.Series of candidate scores indexed identically to df_eval.
    """
    weights = config.parameters["weights"]
    features = config.features
    scores = np.full(len(df_eval), np.nan, dtype=float)

    sec_ids = df_eval["immutable_security_id"].to_numpy()
    dates = df_eval["as_of_date"].to_numpy()

    # Pre-extract feature matrices
    feat_arrays = {f: df_eval[f].to_numpy(dtype=float) for f in features}

    # Group row indices by date
    date_to_indices: dict[str, list[int]] = {}
    for idx, d in enumerate(dates):
        date_to_indices.setdefault(d, []).append(idx)

    for d, row_indices in date_to_indices.items():
        n = len(row_indices)
        if n == 0:
            continue

        # Compute percentile rank for each feature on this date
        feat_pcts = {f: np.zeros(n, dtype=float) for f in features}

        for f in features:
            f_vals = feat_arrays[f]
            # Higher is favorable for all allowed features: sort descending by value, tie-break sec_id ASC
            sorted_indices = sorted(
                range(n),
                key=lambda i: (-f_vals[row_indices[i]], sec_ids[row_indices[i]]),
            )
            for rank_idx, orig_i in enumerate(sorted_indices):
                pct = 100.0 * (n - rank_idx) / n
                feat_pcts[f][orig_i] = pct

        # Weighted sum of percentile ranks
        for i in range(n):
            obs_score = 0.0
            for f in features:
                obs_score += weights[f] * feat_pcts[f][i]
            scores[row_indices[i]] = obs_score

    return pd.Series(scores, index=df_eval.index, name="candidate_score")
