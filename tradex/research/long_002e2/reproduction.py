"""Reproduction verification of E1 metrics and family-level annual context."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from tradex.research.long_002e2.spec import (
    E1_SAFE_ARTIFACTS_DIR,
    REPRESENTATIVE_CONFIGURATION_ID,
)


def verify_e1_reproduction(
    df_cand_10: pd.DataFrame,
    df_cand_25: pd.DataFrame,
    df_vam5_10: pd.DataFrame,
    df_vam5_25: pd.DataFrame,
) -> dict[str, Any]:
    """Verify that reconstructed candidate and baseline metrics match committed E1 evidence.

    Fails closed if any metric deviates beyond rounding tolerance.
    """
    total_10 = len(df_cand_10)
    total_25 = len(df_cand_25)

    c10_clean = int(df_cand_10["clean_target_reached"].sum())
    v10_clean = int(df_vam5_10["clean_target_reached"].sum())
    c25_clean = int(df_cand_25["clean_target_reached"].sum())
    v25_clean = int(df_vam5_25["clean_target_reached"].sum())

    p10_cand = c10_clean / total_10
    p10_vam5 = v10_clean / total_10
    delta_p10 = p10_cand - p10_vam5

    p25_cand = c25_clean / total_25
    p25_vam5 = v25_clean / total_25
    delta_p25 = p25_cand - p25_vam5

    # Annual metrics
    annual_metrics: dict[str, dict[str, float]] = {}
    years = ["2018", "2019", "2020"]

    for yr in years:
        c10_yr = df_cand_10[df_cand_10["as_of_date"].str.startswith(yr)]
        v10_yr = df_vam5_10[df_vam5_10["as_of_date"].str.startswith(yr)]
        n_yr = len(c10_yr)

        c_cl = int(c10_yr["clean_target_reached"].sum())
        v_cl = int(v10_yr["clean_target_reached"].sum())

        p_c = c_cl / n_yr
        p_v = v_cl / n_yr
        d_p = p_c - p_v

        annual_metrics[yr] = {
            "candidate_p10": p_c,
            "vam5_p10": p_v,
            "p10_delta": d_p,
            "selected_count": n_yr,
            "candidate_clean_hits": c_cl,
            "vam5_clean_hits": v_cl,
            "clean_hit_difference": c_cl - v_cl,
        }

    # Expected committed targets
    targets = {
        "p10_cand": 0.268109,
        "p10_vam5": 0.240893,
        "p25_cand": 0.252420,
        "p25_vam5": 0.209510,
        "annual_c10_2018": 0.217131,
        "annual_v10_2018": 0.177291,
        "annual_delta_2018": 0.039841,
        "annual_c10_2019": 0.286111,
        "annual_v10_2019": 0.236111,
        "annual_delta_2019": 0.050000,
        "annual_c10_2020": 0.306792,
        "annual_v10_2020": 0.321311,
        "annual_delta_2020": -0.014520,
    }

    tol = 1e-5
    assert abs(round(p10_cand, 6) - targets["p10_cand"]) <= tol, f"p10_cand mismatch: {p10_cand}"
    assert abs(round(p10_vam5, 6) - targets["p10_vam5"]) <= tol, f"p10_vam5 mismatch: {p10_vam5}"
    assert abs(round(p25_cand, 6) - targets["p25_cand"]) <= tol, f"p25_cand mismatch: {p25_cand}"
    assert abs(round(p25_vam5, 6) - targets["p25_vam5"]) <= tol, f"p25_vam5 mismatch: {p25_vam5}"

    assert (
        abs(round(annual_metrics["2018"]["candidate_p10"], 6) - targets["annual_c10_2018"]) <= tol
    )
    assert abs(round(annual_metrics["2018"]["vam5_p10"], 6) - targets["annual_v10_2018"]) <= tol
    assert abs(round(annual_metrics["2018"]["p10_delta"], 6) - targets["annual_delta_2018"]) <= tol

    assert (
        abs(round(annual_metrics["2019"]["candidate_p10"], 6) - targets["annual_c10_2019"]) <= tol
    )
    assert abs(round(annual_metrics["2019"]["vam5_p10"], 6) - targets["annual_v10_2019"]) <= tol
    assert abs(round(annual_metrics["2019"]["p10_delta"], 6) - targets["annual_delta_2019"]) <= tol

    assert (
        abs(round(annual_metrics["2020"]["candidate_p10"], 6) - targets["annual_c10_2020"]) <= tol
    )
    assert abs(round(annual_metrics["2020"]["vam5_p10"], 6) - targets["annual_v10_2020"]) <= tol
    assert abs(round(annual_metrics["2020"]["p10_delta"], 6) - targets["annual_delta_2020"]) <= tol

    return {
        "status": "exact_match",
        "representative_configuration_id": REPRESENTATIVE_CONFIGURATION_ID,
        "pooled_metrics": {
            "candidate_p10": round(p10_cand, 6),
            "vam5_p10": round(p10_vam5, 6),
            "p10_delta": round(delta_p10, 6),
            "candidate_p25": round(p25_cand, 6),
            "vam5_p25": round(p25_vam5, 6),
            "p25_delta": round(delta_p25, 6),
            "selected_count_10": total_10,
            "selected_count_25": total_25,
        },
        "annual_metrics": {
            yr: {
                "candidate_p10": round(annual_metrics[yr]["candidate_p10"], 6),
                "vam5_p10": round(annual_metrics[yr]["vam5_p10"], 6),
                "p10_delta": round(annual_metrics[yr]["p10_delta"], 6),
                "selected_count": annual_metrics[yr]["selected_count"],
                "candidate_clean_hits": annual_metrics[yr]["candidate_clean_hits"],
                "vam5_clean_hits": annual_metrics[yr]["vam5_clean_hits"],
                "clean_hit_difference": annual_metrics[yr]["clean_hit_difference"],
            }
            for yr in years
        },
    }


def analyze_family_annual_context() -> dict[str, Any]:
    """Inspect committed annual_stability.json to verify whether all 12 logistic configs share the annual sign pattern."""
    annual_stability_path = E1_SAFE_ARTIFACTS_DIR / "annual_stability.json"
    with annual_stability_path.open("r", encoding="utf-8") as f:
        stability_data: dict[str, Any] = json.load(f)

    logit_configs = [k for k in stability_data if k.startswith("LOGIT_")]
    if len(logit_configs) != 12:
        raise ValueError(
            f"Expected 12 LOGIT configurations in annual_stability.json, found {len(logit_configs)}"
        )

    all_share_pattern = True
    config_details: dict[str, dict[str, Any]] = {}

    for cfg in sorted(logit_configs):
        deltas = stability_data[cfg]["annual_precision_10_delta"]
        pos_count = stability_data[cfg]["annual_positive_years_count"]

        d2018 = deltas["2018"]
        d2019 = deltas["2019"]
        d2020 = deltas["2020"]

        matches = (d2018 > 0) and (d2019 > 0) and (d2020 < 0) and (pos_count == 2)
        if not matches:
            all_share_pattern = False

        config_details[cfg] = {
            "deltas": {
                "2018": d2018,
                "2019": d2019,
                "2020": d2020,
            },
            "annual_positive_years_count": pos_count,
            "matches_2018pos_2019pos_2020neg": matches,
        }

    return {
        "family": "regularized_probabilistic",
        "total_configurations_count": len(logit_configs),
        "all_12_share_2018pos_2019pos_2020neg_pattern": all_share_pattern,
        "interpretation": (
            "all 12 tested E1 logistic configurations exhibited the same annual sign pattern; "
            "therefore the 2020 reversal was not unique to LOGIT_S4_C300 within the tested Round-1 logistic grid."
            if all_share_pattern
            else "Annual patterns vary across logistic configurations."
        ),
        "configurations": config_details,
    }
