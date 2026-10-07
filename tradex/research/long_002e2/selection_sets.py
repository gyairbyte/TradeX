"""Selection-set decomposition (OVERLAP, LOGIT_ONLY, VAM5_ONLY) for LONG-002E2."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from tradex.research.long_002e2.quarters import CALENDAR_QUARTERS, date_to_quarter


def partition_date_selections(
    cand_10_by_date: dict[str, pd.DataFrame],
    vam5_10_by_date: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Partition Top-10 selections into mutually exclusive OVERLAP, LOGIT_ONLY, VAM5_ONLY frames."""
    overlap_rows: list[pd.DataFrame] = []
    logit_only_rows: list[pd.DataFrame] = []
    vam5_only_rows: list[pd.DataFrame] = []

    for d in sorted(cand_10_by_date.keys()):
        c10 = cand_10_by_date[d]
        v10 = vam5_10_by_date[d]

        c_ids = set(c10["immutable_security_id"])
        v_ids = set(v10["immutable_security_id"])

        overlap_ids = c_ids.intersection(v_ids)
        logit_only_ids = c_ids - v_ids
        vam5_only_ids = v_ids - c_ids

        # Candidate = overlap + logit_only
        assert len(c10) == len(overlap_ids) + len(logit_only_ids)
        # Baseline = overlap + vam5_only
        assert len(v10) == len(overlap_ids) + len(vam5_only_ids)

        if overlap_ids:
            # Row data from candidate frame
            overlap_rows.append(c10[c10["immutable_security_id"].isin(overlap_ids)])
        if logit_only_ids:
            logit_only_rows.append(c10[c10["immutable_security_id"].isin(logit_only_ids)])
        if vam5_only_ids:
            vam5_only_rows.append(v10[v10["immutable_security_id"].isin(vam5_only_ids)])

    df_overlap = pd.concat(overlap_rows, ignore_index=True) if overlap_rows else pd.DataFrame()
    df_logit_only = (
        pd.concat(logit_only_rows, ignore_index=True) if logit_only_rows else pd.DataFrame()
    )
    df_vam5_only = (
        pd.concat(vam5_only_rows, ignore_index=True) if vam5_only_rows else pd.DataFrame()
    )

    return df_overlap, df_logit_only, df_vam5_only


def compute_partition_metrics(df_sub: pd.DataFrame) -> dict[str, Any]:
    """Compute aggregate outcome statistics for a single partition subset."""
    n = len(df_sub)
    if n == 0:
        return {
            "observation_count": 0,
            "clean_count": 0,
            "clean_rate": 0.0,
            "adverse_rate": 0.0,
            "ecmv": 0.0,
            "median_time_to_target": None,
        }

    clean_cnt = int(df_sub["clean_target_reached"].sum())
    clean_rate = clean_cnt / n
    adv_rate = float(df_sub["adverse_excursion"].astype(bool).mean())
    ecmv = float(df_sub["realized_clean_tier"].mean())

    successful = df_sub[df_sub["clean_target_reached"].astype(bool)]
    if len(successful) > 0 and "time_to_target" in successful.columns:
        med_ttt = float(np.nanmedian(successful["time_to_target"].to_numpy(dtype=float)))
    else:
        med_ttt = None

    return {
        "observation_count": n,
        "clean_count": clean_cnt,
        "clean_rate": round(clean_rate, 6),
        "adverse_rate": round(adv_rate, 4),
        "ecmv": round(ecmv, 4),
        "median_time_to_target": round(med_ttt, 1) if med_ttt is not None else None,
    }


def evaluate_selection_set_decomposition(
    df_overlap: pd.DataFrame,
    df_logit_only: pd.DataFrame,
    df_vam5_only: pd.DataFrame,
) -> dict[str, Any]:
    """Evaluate performance across OVERLAP, LOGIT_ONLY, and VAM5_ONLY partitions overall, by year, and by quarter."""
    # Annotate with year and quarter
    for df in [df_overlap, df_logit_only, df_vam5_only]:
        if len(df) > 0:
            df["year"] = df["as_of_date"].str[:4]
            df["quarter"] = df["as_of_date"].apply(date_to_quarter)

    partitions = {
        "OVERLAP": df_overlap,
        "LOGIT_ONLY": df_logit_only,
        "VAM5_ONLY": df_vam5_only,
    }

    # 1. Overall
    overall_results = {
        p_name: compute_partition_metrics(df_p) for p_name, df_p in partitions.items()
    }

    # 2. By year
    years = ["2018", "2019", "2020"]
    annual_results: dict[str, dict[str, Any]] = {}
    for yr in years:
        annual_results[yr] = {}
        for p_name, df_p in partitions.items():
            df_yr = df_p[df_p["year"] == yr] if len(df_p) > 0 else pd.DataFrame()
            annual_results[yr][p_name] = compute_partition_metrics(df_yr)

    # 3. By quarter
    quarterly_results: dict[str, dict[str, Any]] = {}
    for q in CALENDAR_QUARTERS:
        quarterly_results[q] = {}
        for p_name, df_p in partitions.items():
            df_q = df_p[df_p["quarter"] == q] if len(df_p) > 0 else pd.DataFrame()
            quarterly_results[q][p_name] = compute_partition_metrics(df_q)

    return {
        "overall": overall_results,
        "by_year": annual_results,
        "by_quarter": quarterly_results,
    }
