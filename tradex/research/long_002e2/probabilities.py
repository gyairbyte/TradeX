"""Raw probability stability and calibration diagnostics for LONG-002E2."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss


def compute_reliability_table(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> list[dict[str, Any]]:
    """Compute reliability/calibration table across 10 probability bins."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    table: list[dict[str, Any]] = []

    for i in range(n_bins):
        b_low = bins[i]
        b_high = bins[i + 1]
        if i == n_bins - 1:
            mask = (probs >= b_low) & (probs <= b_high)
        else:
            mask = (probs >= b_low) & (probs < b_high)

        count = int(np.sum(mask))
        if count > 0:
            mean_pred = float(np.mean(probs[mask]))
            empirical_rate = float(np.mean(labels[mask]))
        else:
            mean_pred = None
            empirical_rate = None

        table.append(
            {
                "bin_index": i + 1,
                "bin_lower": round(float(b_low), 3),
                "bin_upper": round(float(b_high), 3),
                "observation_count": count,
                "mean_predicted_probability": round(mean_pred, 4)
                if mean_pred is not None
                else None,
                "empirical_clean_rate": round(empirical_rate, 4)
                if empirical_rate is not None
                else None,
            }
        )

    return table


def evaluate_probability_stability(df_pred: pd.DataFrame) -> dict[str, Any]:
    """Compute Brier score, mean/median predicted probability, and 10-bin reliability table by year.

    Prohibits fitting any probability calibration model.
    """
    df = df_pred.copy()
    df["year"] = df["as_of_date"].str[:4]

    years = ["2018", "2019", "2020"]
    annual_stability: dict[str, dict[str, Any]] = {}

    for yr in years:
        df_yr = df[df["year"] == yr]
        probs = df_yr["candidate_probability"].to_numpy(dtype=float)
        labels = df_yr["clean_target_reached"].to_numpy(dtype=int)

        brier = float(brier_score_loss(labels, probs))
        mean_prob = float(np.mean(probs))
        median_prob = float(np.median(probs))
        base_rate = float(np.mean(labels))
        rel_table = compute_reliability_table(probs, labels, n_bins=10)

        annual_stability[yr] = {
            "observation_count": len(df_yr),
            "empirical_base_rate": round(base_rate, 6),
            "brier_score": round(brier, 6),
            "mean_predicted_probability": round(mean_prob, 6),
            "median_predicted_probability": round(median_prob, 6),
            "reliability_table": rel_table,
        }

    # Overall (2018-2020)
    all_probs = df["candidate_probability"].to_numpy(dtype=float)
    all_labels = df["clean_target_reached"].to_numpy(dtype=int)
    overall = {
        "observation_count": len(df),
        "empirical_base_rate": round(float(np.mean(all_labels)), 6),
        "brier_score": round(float(brier_score_loss(all_labels, all_probs)), 6),
        "mean_predicted_probability": round(float(np.mean(all_probs)), 6),
        "median_predicted_probability": round(float(np.median(all_probs)), 6),
        "reliability_table": compute_reliability_table(all_probs, all_labels, n_bins=10),
    }

    return {
        "calibration_status": "raw_oof_probabilities_uncalibrated",
        "fitting_performed": False,
        "overall": overall,
        "by_year": annual_stability,
    }
