"""Controlled coverage-matched reranking algorithm for LONG-002D2."""
from __future__ import annotations

import pandas as pd

from tradex.research.long_002d2.models import AnnualBreakdown
from tradex.research.long_002d2.spec import CandidateSpec


def run_coverage_matched_reranking(
    df_merged: pd.DataFrame,
    candidate_spec: CandidateSpec,
) -> tuple[
    dict,  # overall metrics dict
    list[AnnualBreakdown],
    dict,  # per-date results dict
]:
    """Execute the preregistered coverage-matched reranking algorithm.

    Algorithm steps per development date:
    1. Filter to non-null candidate observations on this date.
    2. Compute K(date) = count of frozen VAM5 top_10_flag == True.
    3. Coverage-matched baseline: sort by cross_sectional_rank ASC (tie-break ID ASC), select best K(date).
    4. Candidate pool: observations in candidate population where top_25_flag == True.
    5. Assert len(candidate_pool) >= K(date).
    6. Candidate reranker: sort by candidate feature DESC (tie-break ID ASC), select best K(date).
    7. Assert len(candidate_selected) == len(baseline_selected) == K(date).
    """
    feat_id = candidate_spec.feature_id

    # 1. Candidate-specific common population (drop null candidate feature values)
    df_valid = df_merged[df_merged[feat_id].notna()].copy()
    common_obs = len(df_valid)

    # Check coverage within frozen VAM5 top-25 pool
    top25_total = int((df_merged["top_25_flag"] == True).sum())
    top25_valid = int((df_valid["top_25_flag"] == True).sum())
    cov_within_top25 = float(top25_valid / top25_total) if top25_total > 0 else 0.0
    if cov_within_top25 < 0.95:
        raise ValueError(
            f"COVERAGE GATE BREACH for '{feat_id}': {cov_within_top25:.4f} < 0.95 minimum within top-25 pool"
        )

    # Sort dates chronologically
    unique_dates = sorted(df_valid["as_of_date"].unique().tolist())
    eval_dates_count = len(unique_dates)

    date_results: dict[str, dict] = {}
    tot_selected = 0
    cand_tot_clean = 0
    vam5_tot_clean = 0
    tot_overlap = 0

    annual_stats: dict[int, dict] = {}

    for d in unique_dates:
        df_d = df_valid[df_valid["as_of_date"] == d]

        # Step 3: K(date)
        k_date = int((df_d["top_10_flag"] == True).sum())
        if k_date == 0:
            date_results[d] = {
                "k_date": 0,
                "cand_clean": 0,
                "vam5_clean": 0,
                "overlap": 0,
                "cand_ids": set(),
                "vam5_ids": set(),
            }
            continue

        # Step 4: Coverage-matched frozen VAM5 baseline
        vam5_selected = df_d.sort_values(
            ["cross_sectional_rank", "immutable_security_id"],
            ascending=[True, True],
        ).head(k_date)
        if len(vam5_selected) != k_date:
            raise ValueError(
                f"BASELINE SELECTION COUNT MISMATCH on {d}: expected {k_date}, got {len(vam5_selected)}"
            )

        # Step 5: Candidate pool (within top-25 pool)
        cand_pool = df_d[df_d["top_25_flag"] == True]
        if len(cand_pool) < k_date:
            raise ValueError(
                f"CANDIDATE POOL DEFICIT on {d}: candidate top-25 pool has {len(cand_pool)} obs, "
                f"which is less than K(date)={k_date}"
            )

        # Step 6: Candidate reranking
        # Hypothesized direction HIGHER -> sort descending
        is_higher = candidate_spec.hypothesized_direction == "HIGHER"
        cand_selected = cand_pool.sort_values(
            [feat_id, "immutable_security_id"],
            ascending=[not is_higher, True],
        ).head(k_date)

        # Step 7: Required equality
        if len(cand_selected) != k_date:
            raise ValueError(
                f"CANDIDATE SELECTION COUNT MISMATCH on {d}: expected {k_date}, got {len(cand_selected)}"
            )

        c_clean = int(cand_selected["clean_target_reached"].sum())
        v_clean = int(vam5_selected["clean_target_reached"].sum())

        cand_ids = set(cand_selected["immutable_security_id"])
        vam5_ids = set(vam5_selected["immutable_security_id"])
        overlap = len(cand_ids.intersection(vam5_ids))

        date_results[d] = {
            "k_date": k_date,
            "cand_clean": c_clean,
            "vam5_clean": v_clean,
            "overlap": overlap,
            "cand_ids": cand_ids,
            "vam5_ids": vam5_ids,
        }

        tot_selected += k_date
        cand_tot_clean += c_clean
        vam5_tot_clean += v_clean
        tot_overlap += overlap

        # Annual aggregation
        year = int(d[:4])
        st = annual_stats.setdefault(
            year,
            {"dates": 0, "selected": 0, "cand_clean": 0, "vam5_clean": 0},
        )
        st["dates"] += 1
        st["selected"] += k_date
        st["cand_clean"] += c_clean
        st["vam5_clean"] += v_clean

    cand_precision = float(cand_tot_clean / tot_selected) if tot_selected > 0 else 0.0
    vam5_precision = float(vam5_tot_clean / tot_selected) if tot_selected > 0 else 0.0
    abs_delta = cand_precision - vam5_precision
    prec_ratio = float(cand_precision / vam5_precision) if vam5_precision > 0 else 0.0
    incremental_events = cand_tot_clean - vam5_tot_clean
    overlap_rate = float(tot_overlap / tot_selected) if tot_selected > 0 else 0.0

    # Build annual breakdowns
    annual_breakdowns: list[AnnualBreakdown] = []
    positive_years_count = 0
    for y in sorted(annual_stats.keys()):
        st = annual_stats[y]
        sel_y = st["selected"]
        c_clean_y = st["cand_clean"]
        v_clean_y = st["vam5_clean"]
        c_prec_y = float(c_clean_y / sel_y) if sel_y > 0 else 0.0
        v_prec_y = float(v_clean_y / sel_y) if sel_y > 0 else 0.0
        delta_y = c_prec_y - v_prec_y
        ratio_y = float(c_prec_y / v_prec_y) if v_prec_y > 0 else 0.0
        is_pos = delta_y > 0.0
        if is_pos:
            positive_years_count += 1

        annual_breakdowns.append(
            AnnualBreakdown(
                year=y,
                eval_dates_count=st["dates"],
                selected_count=sel_y,
                candidate_clean_count=c_clean_y,
                candidate_precision=round(c_prec_y, 6),
                matched_vam5_clean_count=v_clean_y,
                matched_vam5_precision=round(v_prec_y, 6),
                absolute_delta=round(delta_y, 6),
                precision_ratio=round(ratio_y, 4),
                positive_delta=is_pos,
            )
        )

    overall = {
        "common_observations": common_obs,
        "coverage_within_top_25": round(cov_within_top25, 6),
        "evaluation_dates_count": eval_dates_count,
        "total_selected_count": tot_selected,
        "candidate_clean_count": cand_tot_clean,
        "candidate_precision": round(cand_precision, 6),
        "matched_vam5_clean_count": vam5_tot_clean,
        "matched_vam5_precision": round(vam5_precision, 6),
        "absolute_precision_delta": round(abs_delta, 6),
        "precision_ratio": round(prec_ratio, 4),
        "incremental_clean_events": incremental_events,
        "selection_overlap_count": tot_overlap,
        "selection_overlap_rate": round(overlap_rate, 4),
        "positive_annual_years_count": positive_years_count,
    }

    return overall, annual_breakdowns, date_results
