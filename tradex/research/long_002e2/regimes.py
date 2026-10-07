"""SPY market-context regime diagnostics for LONG-002E2."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def compute_spy_date_regimes(
    df_features: pd.DataFrame,
) -> tuple[dict[str, str], float, float, dict[str, int]]:
    """Map each evaluation date to one of three descriptive SPY 20-session return regimes.

    1. Collapses spy_return_20 to one value per evaluation date after verifying within-date constancy.
    2. Computes q30 and q70 across all 730 evaluation dates using numpy.quantile linear method.
    3. Partitions into:
       - LOWER: value <= q30
       - MIDDLE: q30 < value <= q70
       - UPPER: value > q70

    Returns:
        (date_regime_map, q30, q70, regime_date_counts)
    """
    # Verify date-level constancy
    grouped = df_features.groupby("as_of_date")["spy_return_20"].agg(["min", "max", "count"])
    diff = (grouped["max"] - grouped["min"]).abs()
    if (diff > 1e-6).any():
        bad_dates = grouped[diff > 1e-6].index.tolist()
        raise ValueError(f"SPY RETURN NOT CONSTANT WITHIN DATES: {bad_dates[:5]}")

    date_spy = grouped["min"].to_dict()
    eval_dates = sorted(date_spy.keys())
    if len(eval_dates) != 730:
        raise ValueError(f"Expected 730 evaluation dates for SPY regimes, found {len(eval_dates)}")

    vals = np.array([date_spy[d] for d in eval_dates], dtype=float)
    q30_val, q70_val = np.quantile(vals, [0.30, 0.70], method="linear")
    q30 = float(q30_val)
    q70 = float(q70_val)

    date_regime_map: dict[str, str] = {}
    regime_date_counts: dict[str, int] = {"LOWER": 0, "MIDDLE": 0, "UPPER": 0}

    for d in eval_dates:
        v = date_spy[d]
        if v <= q30:
            regime = "LOWER"
        elif v <= q70:
            regime = "MIDDLE"
        else:
            regime = "UPPER"
        date_regime_map[d] = regime
        regime_date_counts[regime] += 1

    return date_regime_map, round(q30, 6), round(q70, 6), regime_date_counts


def evaluate_spy_regime_diagnostics(
    df_cand_10: pd.DataFrame,
    df_cand_25: pd.DataFrame,
    df_vam5_10: pd.DataFrame,
    df_vam5_25: pd.DataFrame,
    date_regime_map: dict[str, str],
    q30: float,
    q70: float,
    regime_date_counts: dict[str, int],
) -> dict[str, Any]:
    """Compute candidate vs VAM5 performance across SPY return regimes overall and by year x regime."""
    # Annotate selections with regime
    c10 = df_cand_10.copy()
    c10["regime"] = c10["as_of_date"].map(date_regime_map)
    v10 = df_vam5_10.copy()
    v10["regime"] = v10["as_of_date"].map(date_regime_map)

    c25 = df_cand_25.copy()
    c25["regime"] = c25["as_of_date"].map(date_regime_map)
    v25 = df_vam5_25.copy()
    v25["regime"] = v25["as_of_date"].map(date_regime_map)

    c10["year"] = c10["as_of_date"].str[:4]
    v10["year"] = v10["as_of_date"].str[:4]
    c25["year"] = c25["as_of_date"].str[:4]
    v25["year"] = v25["as_of_date"].str[:4]

    regimes = ["LOWER", "MIDDLE", "UPPER"]
    years = ["2018", "2019", "2020"]

    def _calc_subset_metrics(
        c10_sub: pd.DataFrame, v10_sub: pd.DataFrame, c25_sub: pd.DataFrame, v25_sub: pd.DataFrame
    ) -> dict[str, Any]:
        sel_10_c = len(c10_sub)
        sel_10_v = len(v10_sub)
        if sel_10_c != sel_10_v:
            raise ValueError(f"Selection count mismatch: {sel_10_c} != {sel_10_v}")

        clean_10_c = int(c10_sub["clean_target_reached"].sum()) if sel_10_c > 0 else 0
        clean_10_v = int(v10_sub["clean_target_reached"].sum()) if sel_10_v > 0 else 0
        p10_c = clean_10_c / sel_10_c if sel_10_c > 0 else 0.0
        p10_v = clean_10_v / sel_10_v if sel_10_v > 0 else 0.0

        sel_25_c = len(c25_sub)
        sel_25_v = len(v25_sub)
        clean_25_c = int(c25_sub["clean_target_reached"].sum()) if sel_25_c > 0 else 0
        clean_25_v = int(v25_sub["clean_target_reached"].sum()) if sel_25_v > 0 else 0
        p25_c = clean_25_c / sel_25_c if sel_25_c > 0 else 0.0
        p25_v = clean_25_v / sel_25_v if sel_25_v > 0 else 0.0

        adv_10_c = float(c10_sub["adverse_excursion"].astype(bool).mean()) if sel_10_c > 0 else 0.0
        adv_10_v = float(v10_sub["adverse_excursion"].astype(bool).mean()) if sel_10_v > 0 else 0.0

        ecmv_10_c = float(c10_sub["realized_clean_tier"].mean()) if sel_10_c > 0 else 0.0
        ecmv_10_v = float(v10_sub["realized_clean_tier"].mean()) if sel_10_v > 0 else 0.0

        # Overlap @ 10
        overlap_count = 0
        eval_dates = sorted(c10_sub["as_of_date"].unique().tolist())
        for d in eval_dates:
            c_set = set(c10_sub[c10_sub["as_of_date"] == d]["immutable_security_id"])
            v_set = set(v10_sub[v10_sub["as_of_date"] == d]["immutable_security_id"])
            overlap_count += len(c_set.intersection(v_set))
        overlap_pct = overlap_count / sel_10_c if sel_10_c > 0 else 0.0

        return {
            "evaluation_dates_count": len(eval_dates),
            "candidate_selected_count": sel_10_c,
            "vam5_selected_count": sel_10_v,
            "candidate_clean_hits": clean_10_c,
            "vam5_clean_hits": clean_10_v,
            "clean_hit_difference": clean_10_c - clean_10_v,
            "candidate_p10": round(p10_c, 6),
            "vam5_p10": round(p10_v, 6),
            "delta_p10": round(p10_c - p10_v, 6),
            "candidate_p25": round(p25_c, 6),
            "vam5_p25": round(p25_v, 6),
            "delta_p25": round(p25_c - p25_v, 6),
            "candidate_adverse_rate_10": round(adv_10_c, 4),
            "vam5_adverse_rate_10": round(adv_10_v, 4),
            "candidate_ecmv_10": round(ecmv_10_c, 4),
            "vam5_ecmv_10": round(ecmv_10_v, 4),
            "selection_overlap_pct": round(overlap_pct, 4),
        }

    overall_regimes: dict[str, dict[str, Any]] = {}
    for r in regimes:
        overall_regimes[r] = _calc_subset_metrics(
            c10[c10["regime"] == r],
            v10[v10["regime"] == r],
            c25[c25["regime"] == r],
            v25[v25["regime"] == r],
        )

    # Year x Regime
    year_x_regime: dict[str, dict[str, dict[str, Any]]] = {}
    for yr in years:
        year_x_regime[yr] = {}
        for r in regimes:
            year_x_regime[yr][r] = _calc_subset_metrics(
                c10[(c10["year"] == yr) & (c10["regime"] == r)],
                v10[(v10["year"] == yr) & (v10["regime"] == r)],
                c25[(c25["year"] == yr) & (c25["regime"] == r)],
                v25[(v25["year"] == yr) & (v25["regime"] == r)],
            )

    return {
        "context_variable": "spy_return_20",
        "q30": q30,
        "q70": q70,
        "regime_date_counts": regime_date_counts,
        "overall_regimes": overall_regimes,
        "year_x_regime": year_x_regime,
    }
