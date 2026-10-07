"""Fixed calendar-quarter decomposition for LONG-002E2."""

from __future__ import annotations

from typing import Any

import pandas as pd

CALENDAR_QUARTERS = [
    "2018Q1",
    "2018Q2",
    "2018Q3",
    "2018Q4",
    "2019Q1",
    "2019Q2",
    "2019Q3",
    "2019Q4",
    "2020Q1",
    "2020Q2",
    "2020Q3",
    "2020Q4",
]


def date_to_quarter(date_str: str) -> str:
    """Map YYYY-MM-DD date string to YYYYQq format."""
    year = date_str[:4]
    month = int(date_str[5:7])
    q = (month - 1) // 3 + 1
    return f"{year}Q{q}"


def evaluate_quarterly_decomposition(
    df_cand_10: pd.DataFrame,
    df_cand_25: pd.DataFrame,
    df_vam5_10: pd.DataFrame,
    df_vam5_25: pd.DataFrame,
) -> dict[str, Any]:
    """Compute performance metrics across the 12 fixed calendar quarters."""
    quarters_results: dict[str, dict[str, Any]] = {}

    # Pre-assign quarter column
    c10 = df_cand_10.copy()
    c10["quarter"] = c10["as_of_date"].apply(date_to_quarter)

    v10 = df_vam5_10.copy()
    v10["quarter"] = v10["as_of_date"].apply(date_to_quarter)

    c25 = df_cand_25.copy()
    c25["quarter"] = c25["as_of_date"].apply(date_to_quarter)

    v25 = df_vam5_25.copy()
    v25["quarter"] = v25["as_of_date"].apply(date_to_quarter)

    annual_hit_deltas: dict[str, int] = {"2018": 0, "2019": 0, "2020": 0}

    for q in CALENDAR_QUARTERS:
        c10_q = c10[c10["quarter"] == q]
        v10_q = v10[v10["quarter"] == q]
        c25_q = c25[c25["quarter"] == q]
        v25_q = v25[v25["quarter"] == q]

        eval_dates = sorted(c10_q["as_of_date"].unique().tolist())
        d_count = len(eval_dates)

        sel_10_c = len(c10_q)
        sel_10_v = len(v10_q)
        if sel_10_c != sel_10_v:
            raise ValueError(f"Selection count mismatch in quarter {q}: {sel_10_c} != {sel_10_v}")

        clean_10_c = int(c10_q["clean_target_reached"].sum()) if sel_10_c > 0 else 0
        clean_10_v = int(v10_q["clean_target_reached"].sum()) if sel_10_v > 0 else 0
        clean_diff_10 = clean_10_c - clean_10_v

        p10_c = clean_10_c / sel_10_c if sel_10_c > 0 else 0.0
        p10_v = clean_10_v / sel_10_v if sel_10_v > 0 else 0.0
        p10_delta = p10_c - p10_v

        sel_25_c = len(c25_q)
        sel_25_v = len(v25_q)
        clean_25_c = int(c25_q["clean_target_reached"].sum()) if sel_25_c > 0 else 0
        clean_25_v = int(v25_q["clean_target_reached"].sum()) if sel_25_v > 0 else 0

        p25_c = clean_25_c / sel_25_c if sel_25_c > 0 else 0.0
        p25_v = clean_25_v / sel_25_v if sel_25_v > 0 else 0.0
        p25_delta = p25_c - p25_v

        adv_10_c = float(c10_q["adverse_excursion"].astype(bool).mean()) if sel_10_c > 0 else 0.0
        adv_10_v = float(v10_q["adverse_excursion"].astype(bool).mean()) if sel_10_v > 0 else 0.0

        ecmv_10_c = float(c10_q["realized_clean_tier"].mean()) if sel_10_c > 0 else 0.0
        ecmv_10_v = float(v10_q["realized_clean_tier"].mean()) if sel_10_v > 0 else 0.0

        # Overlap @ 10
        overlap_count = 0
        for d in eval_dates:
            c_set = set(c10_q[c10_q["as_of_date"] == d]["immutable_security_id"])
            v_set = set(v10_q[v10_q["as_of_date"] == d]["immutable_security_id"])
            overlap_count += len(c_set.intersection(v_set))
        overlap_pct = overlap_count / sel_10_c if sel_10_c > 0 else 0.0

        yr = q[:4]
        annual_hit_deltas[yr] += clean_diff_10

        quarters_results[q] = {
            "quarter": q,
            "year": yr,
            "evaluation_dates_count": d_count,
            "candidate_selected_count": sel_10_c,
            "vam5_selected_count": sel_10_v,
            "candidate_clean_hits": clean_10_c,
            "vam5_clean_hits": clean_10_v,
            "clean_hit_difference": clean_diff_10,
            "candidate_p10": round(p10_c, 6),
            "vam5_p10": round(p10_v, 6),
            "p10_delta": round(p10_delta, 6),
            "candidate_p25": round(p25_c, 6),
            "vam5_p25": round(p25_v, 6),
            "p25_delta": round(p25_delta, 6),
            "candidate_adverse_rate_10": round(adv_10_c, 4),
            "vam5_adverse_rate_10": round(adv_10_v, 4),
            "candidate_ecmv_10": round(ecmv_10_c, 4),
            "vam5_ecmv_10": round(ecmv_10_v, 4),
            "top10_overlap_pct": round(overlap_pct, 4),
        }

    return {
        "quarters_count": len(CALENDAR_QUARTERS),
        "annual_hit_deltas_from_quarters": annual_hit_deltas,
        "quarters": quarters_results,
    }
