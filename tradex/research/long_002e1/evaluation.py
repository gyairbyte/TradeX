"""Top-K ranking evaluation, calibration, and metrics calculation for LONG-002E1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss


@dataclass
class TopKMetrics:
    """Metrics evaluated at a specific K cutoff (e.g. K=10 or K=25)."""

    k: int
    selected_count: int
    clean_count: int
    precision: float
    matched_vam5_precision: float
    precision_delta_vs_vam5: float
    lift_vs_oof_base_rate: float
    empirical_clean_move_value: float
    matched_vam5_clean_move_value: float
    clean_move_value_delta: float
    primary_adverse_rate: float
    matched_vam5_adverse_rate: float
    median_time_to_target: float | None
    selection_overlap_pct: float
    distinct_tickers_count: int


@dataclass
class EvaluationSummary:
    """Complete OOF evaluation metrics for a single configuration."""

    configuration_id: str
    family: str
    feature_subset_id: str
    evaluation_dates_count: int
    oof_base_rate: float
    top10: TopKMetrics
    top25: TopKMetrics
    annual_precision_10: dict[int, float | None]
    annual_vam5_precision_10: dict[int, float]
    annual_precision_10_delta: dict[int, float | None]
    annual_positive_years_count: int
    calibration_status: str
    brier_score: float | None
    reliability_table: list[dict[str, Any]] | None
    date_level_data: pd.DataFrame


def select_top_k_for_date(
    df_date: pd.DataFrame,
    score_column: str,
    k: int,
    ascending: bool = False,
) -> pd.DataFrame:
    """Deterministically select top K observations for a single date.

    Tie-break: immutable_security_id ASC.
    If date has fewer than K observations, returns all observations without backfill.
    """
    n = len(df_date)
    k_actual = min(k, n)
    if k_actual == 0:
        return df_date.head(0)

    # Sort by score (DESC if ascending=False), tie-break immutable_security_id ASC
    sorted_df = df_date.sort_values(
        by=[score_column, "immutable_security_id"],
        ascending=[ascending, True],
    )
    return sorted_df.head(k_actual)


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
                "bin_lower": round(b_low, 3),
                "bin_upper": round(b_high, 3),
                "observation_count": count,
                "mean_predicted_prob": round(mean_pred, 4) if mean_pred is not None else None,
                "empirical_clean_rate": round(empirical_rate, 4) if empirical_rate is not None else None,
            }
        )

    return table


def evaluate_configuration_predictions(
    df_predictions: pd.DataFrame,
    df_vam5: pd.DataFrame,
    config_id: str,
    family: str,
    subset_id: str,
    score_column: str = "candidate_score",
) -> EvaluationSummary:
    """Evaluate candidate predictions against matched VAM5 baseline over identical dates/population.

    df_predictions must contain:
    [immutable_security_id, as_of_date, cutoff_time, clean_target_reached,
     realized_clean_tier, adverse_excursion, time_to_target, ticker_at_decision, score_column]
    """
    # Filter to valid prediction rows and match with VAM5
    df_cand = df_predictions[df_predictions[score_column].notna()].copy()

    # Join with VAM5 on identical keys
    joined = df_cand.merge(
        df_vam5[[
            "immutable_security_id",
            "as_of_date",
            "cutoff_time",
            "cross_sectional_rank",
            "raw_score_or_return",
        ]],
        on=["immutable_security_id", "as_of_date", "cutoff_time"],
        how="inner",
    )

    unique_dates = sorted(joined["as_of_date"].unique().tolist())
    eval_dates_count = len(unique_dates)
    oof_base_rate = float(joined["clean_target_reached"].mean()) if len(joined) > 0 else 0.0

    # Date-level Top 10 and Top 25 selections
    cand_10_list: list[pd.DataFrame] = []
    cand_25_list: list[pd.DataFrame] = []
    vam5_10_list: list[pd.DataFrame] = []
    vam5_25_list: list[pd.DataFrame] = []

    date_level_records: list[dict[str, Any]] = []

    for d in unique_dates:
        df_d = joined[joined["as_of_date"] == d]

        # Candidate selections (DESC by score_column, tie-break ID ASC)
        c10 = select_top_k_for_date(df_d, score_column, 10, ascending=False)
        c25 = select_top_k_for_date(df_d, score_column, 25, ascending=False)

        # Matched VAM5 selections (ASC by cross_sectional_rank, tie-break ID ASC)
        v10 = select_top_k_for_date(df_d, "cross_sectional_rank", 10, ascending=True)
        v25 = select_top_k_for_date(df_d, "cross_sectional_rank", 25, ascending=True)

        cand_10_list.append(c10)
        cand_25_list.append(c25)
        vam5_10_list.append(v10)
        vam5_25_list.append(v25)

        # Date-level record
        c10_clean = int(c10["clean_target_reached"].sum())
        v10_clean = int(v10["clean_target_reached"].sum())
        c25_clean = int(c25["clean_target_reached"].sum())
        v25_clean = int(v25["clean_target_reached"].sum())

        overlap_10 = len(set(c10["immutable_security_id"]).intersection(set(v10["immutable_security_id"])))
        overlap_25 = len(set(c25["immutable_security_id"]).intersection(set(v25["immutable_security_id"])))

        date_level_records.append(
            {
                "as_of_date": d,
                "n_eval": len(df_d),
                "k10_selected": len(c10),
                "c10_clean": c10_clean,
                "v10_clean": v10_clean,
                "k10_overlap": overlap_10,
                "k25_selected": len(c25),
                "c25_clean": c25_clean,
                "v25_clean": v25_clean,
                "k25_overlap": overlap_25,
            }
        )

    df_cand_10 = pd.concat(cand_10_list, ignore_index=True) if cand_10_list else pd.DataFrame()
    df_cand_25 = pd.concat(cand_25_list, ignore_index=True) if cand_25_list else pd.DataFrame()
    df_vam5_10 = pd.concat(vam5_10_list, ignore_index=True) if vam5_10_list else pd.DataFrame()
    df_vam5_25 = pd.concat(vam5_25_list, ignore_index=True) if vam5_25_list else pd.DataFrame()

    def _calc_k_metrics(df_c: pd.DataFrame, df_v: pd.DataFrame, k: int) -> TopKMetrics:
        sel_cnt = len(df_c)
        if sel_cnt == 0:
            return TopKMetrics(
                k=k,
                selected_count=0,
                clean_count=0,
                precision=0.0,
                matched_vam5_precision=0.0,
                precision_delta_vs_vam5=0.0,
                lift_vs_oof_base_rate=0.0,
                empirical_clean_move_value=0.0,
                matched_vam5_clean_move_value=0.0,
                clean_move_value_delta=0.0,
                primary_adverse_rate=0.0,
                matched_vam5_adverse_rate=0.0,
                median_time_to_target=None,
                selection_overlap_pct=0.0,
                distinct_tickers_count=0,
            )

        c_clean = int(df_c["clean_target_reached"].sum())
        v_clean = int(df_v["clean_target_reached"].sum())

        p_c = float(c_clean / sel_cnt)
        p_v = float(v_clean / len(df_v))
        p_delta = float(p_c - p_v)
        lift = float(p_c / oof_base_rate) if oof_base_rate > 0 else 0.0

        ecmv_c = float(df_c["realized_clean_tier"].mean())
        ecmv_v = float(df_v["realized_clean_tier"].mean())
        ecmv_delta = float(ecmv_c - ecmv_v)

        adv_c = float(df_c["adverse_excursion"].astype(bool).mean())
        adv_v = float(df_v["adverse_excursion"].astype(bool).mean())

        succ_c = df_c[df_c["clean_target_reached"].astype(bool)]["time_to_target"].dropna()
        med_ttt = float(succ_c.median()) if len(succ_c) > 0 else None

        # Overlap across all selected rows
        c_pairs = set(zip(df_c["as_of_date"], df_c["immutable_security_id"]))
        v_pairs = set(zip(df_v["as_of_date"], df_v["immutable_security_id"]))
        overlap_cnt = len(c_pairs.intersection(v_pairs))
        overlap_pct = float(overlap_cnt / sel_cnt) if sel_cnt > 0 else 0.0

        distinct_tickers = int(df_c["ticker_at_decision"].nunique())

        return TopKMetrics(
            k=k,
            selected_count=sel_cnt,
            clean_count=c_clean,
            precision=p_c,
            matched_vam5_precision=p_v,
            precision_delta_vs_vam5=p_delta,
            lift_vs_oof_base_rate=lift,
            empirical_clean_move_value=ecmv_c,
            matched_vam5_clean_move_value=ecmv_v,
            clean_move_value_delta=ecmv_delta,
            primary_adverse_rate=adv_c,
            matched_vam5_adverse_rate=adv_v,
            median_time_to_target=med_ttt,
            selection_overlap_pct=overlap_pct,
            distinct_tickers_count=distinct_tickers,
        )

    m10 = _calc_k_metrics(df_cand_10, df_vam5_10, 10)
    m25 = _calc_k_metrics(df_cand_25, df_vam5_25, 25)

    # Annual breakdown for Precision@10 (2018, 2019, 2020)
    annual_p10: dict[int, float | None] = {}
    annual_vam5_p10: dict[int, float] = {}
    annual_p10_delta: dict[int, float | None] = {}
    pos_years = 0

    for yr in [2018, 2019, 2020]:
        sub_c = df_cand_10[df_cand_10["as_of_date"].str.startswith(str(yr))] if len(df_cand_10) > 0 else pd.DataFrame()
        sub_v = df_vam5_10[df_vam5_10["as_of_date"].str.startswith(str(yr))] if len(df_vam5_10) > 0 else pd.DataFrame()

        if len(sub_v) > 0:
            vp = float(sub_v["clean_target_reached"].mean())
        else:
            vp = 0.0
        annual_vam5_p10[yr] = vp

        if len(sub_c) > 0:
            cp = float(sub_c["clean_target_reached"].mean())
            delta = float(cp - vp)
            annual_p10[yr] = cp
            annual_p10_delta[yr] = delta
            if delta > 0.0:
                pos_years += 1
        else:
            annual_p10[yr] = None
            annual_p10_delta[yr] = None

    # Calibration & probability metrics
    if family in ("regularized_probabilistic", "shallow_strongly_regularized_gbdt"):
        calibration_status = "raw_oof_probabilities_uncalibrated"
        probs_all = joined[score_column].to_numpy(dtype=float)
        labels_all = joined["clean_target_reached"].to_numpy(dtype=int)
        brier = float(brier_score_loss(labels_all, probs_all))
        rel_table = compute_reliability_table(probs_all, labels_all, n_bins=10)
    else:
        calibration_status = "not_applicable_round1_unscaled_score"
        brier = None
        rel_table = None

    return EvaluationSummary(
        configuration_id=config_id,
        family=family,
        feature_subset_id=subset_id,
        evaluation_dates_count=eval_dates_count,
        oof_base_rate=oof_base_rate,
        top10=m10,
        top25=m25,
        annual_precision_10=annual_p10,
        annual_vam5_precision_10=annual_vam5_p10,
        annual_precision_10_delta=annual_p10_delta,
        annual_positive_years_count=pos_years,
        calibration_status=calibration_status,
        brier_score=brier,
        reliability_table=rel_table,
        date_level_data=pd.DataFrame(date_level_records),
    )


def assign_round1_status(
    summary: EvaluationSummary,
    bootstrap_p10_ci_21: tuple[float, float, float] | None,  # (lower, median, upper)
    execution_failed: bool = False,
) -> str:
    """Assign Round-1 disposition status according to preregistered rules.

    Possible statuses:
    - round2_eligible
    - round1_inconclusive
    - round1_not_supported
    - invalid_configuration
    """
    if execution_failed:
        return "invalid_configuration"

    if bootstrap_p10_ci_21 is None:
        return "invalid_configuration"

    _bs_lower_21, bs_median_21, bs_upper_21 = bootstrap_p10_ci_21

    p10_delta = summary.top10.precision_delta_vs_vam5
    p25_delta = summary.top25.precision_delta_vs_vam5
    pos_years = summary.annual_positive_years_count

    # Criterion 1: round2_eligible
    # All of:
    # 1. pooled OOF Precision@10 delta > 0
    # 2. pooled OOF Precision@25 delta >= 0
    # 3. exactly 3 of 3 OOF years have positive Precision@10 delta (ceil(0.75 * 3) = 3)
    # 4. 21-session bootstrap median Precision@10 delta > 0
    if (
        p10_delta > 0.0
        and p25_delta >= 0.0
        and pos_years >= 3
        and bs_median_21 > 0.0
    ):
        return "round2_eligible"

    # Criterion 2: round1_not_supported
    # Either:
    # - 21-session bootstrap 97.5th percentile Precision@10 delta <= 0
    # OR
    # - pooled Precision@10 delta <= 0 AND positive annual Precision@10 delta years <= 1 of 3
    if (
        bs_upper_21 <= 0.0
        or (p10_delta <= 0.0 and pos_years <= 1)
    ):
        return "round1_not_supported"

    return "round1_inconclusive"
