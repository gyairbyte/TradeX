"""Aggregate selection concentration diagnostics for LONG-002E2."""

from __future__ import annotations

from typing import Any

import pandas as pd


def compute_concentration_metrics(df_selections: pd.DataFrame) -> dict[str, Any]:
    """Compute deterministic aggregate concentration statistics for a set of selections.

    Strictly produces aggregate statistics only; does not return or commit
    ticker names, company names, or immutable security IDs.
    """
    total = len(df_selections)
    if total == 0:
        return {
            "total_selections_count": 0,
            "distinct_immutable_securities_count": 0,
            "maximum_selection_count": 0,
            "top_5_securities_share": 0.0,
            "top_10_securities_share": 0.0,
            "herfindahl_hirschman_index": 0.0,
            "effective_number_of_securities": 0.0,
        }

    counts = df_selections["immutable_security_id"].value_counts().values
    distinct = len(counts)
    max_count = int(counts[0])

    top5_sum = int(counts[:5].sum())
    top10_sum = int(counts[:10].sum())

    top5_share = top5_sum / total
    top10_share = top10_sum / total

    shares = counts / total
    hhi = float((shares**2).sum())
    eff_n = 1.0 / hhi if hhi > 0 else 0.0

    return {
        "total_selections_count": total,
        "distinct_immutable_securities_count": distinct,
        "maximum_selection_count": max_count,
        "top_5_securities_share": round(top5_share, 4),
        "top_10_securities_share": round(top10_share, 4),
        "herfindahl_hirschman_index": round(hhi, 6),
        "effective_number_of_securities": round(eff_n, 2),
    }


def evaluate_selection_concentration(
    df_cand_10: pd.DataFrame,
    df_vam5_10: pd.DataFrame,
) -> dict[str, Any]:
    """Evaluate aggregate concentration for candidate and VAM5 overall and by year."""
    c10 = df_cand_10.copy()
    v10 = df_vam5_10.copy()
    c10["year"] = c10["as_of_date"].str[:4]
    v10["year"] = v10["as_of_date"].str[:4]

    years = ["2018", "2019", "2020"]
    annual_concentration: dict[str, dict[str, Any]] = {}

    for yr in years:
        annual_concentration[yr] = {
            "candidate": compute_concentration_metrics(c10[c10["year"] == yr]),
            "matched_vam5": compute_concentration_metrics(v10[v10["year"] == yr]),
        }

    overall_concentration = {
        "candidate": compute_concentration_metrics(c10),
        "matched_vam5": compute_concentration_metrics(v10),
    }

    return {
        "overall": overall_concentration,
        "by_year": annual_concentration,
    }
