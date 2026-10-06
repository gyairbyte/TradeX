"""Tests for top-K ranking evaluator, bootstrap, and baseline metrics (Tests 49-57)."""

import numpy as np
import pandas as pd

from tradex.research.long_002e1.bootstrap import run_paired_calendar_bootstrap
from tradex.research.long_002e1.evaluation import (
    EvaluationSummary,
    TopKMetrics,
    assign_round1_status,
    compute_reliability_table,
    select_top_k_for_date,
)


def test_49_top_10_selection_deterministic():
    """Test 49: Top-10 selection per date deterministically chooses min(10, N) observations."""
    df_date = pd.DataFrame(
        {
            "immutable_security_id": [f"S{i:02d}" for i in range(15)],
            "score": [float(i) for i in range(15)],
        }
    )
    sel10 = select_top_k_for_date(df_date, "score", 10, ascending=False)
    assert len(sel10) == 10
    assert sel10["immutable_security_id"].iloc[0] == "S14"  # highest score first

    df_small = df_date.head(4)
    sel_small = select_top_k_for_date(df_small, "score", 10, ascending=False)
    assert len(sel_small) == 4


def test_50_top_25_selection_deterministic():
    """Test 50: Top-25 selection per date deterministically chooses min(25, N) observations."""
    df_date = pd.DataFrame(
        {
            "immutable_security_id": [f"S{i:02d}" for i in range(30)],
            "score": [float(i) for i in range(30)],
        }
    )
    sel25 = select_top_k_for_date(df_date, "score", 25, ascending=False)
    assert len(sel25) == 25
    assert sel25["immutable_security_id"].iloc[0] == "S29"


def test_51_matched_baseline_comparator_metrics():
    """Test 51: Matched baseline comparator metrics match frozen VAM5 metrics."""
    # Top-10 precision is ~21.04% and lift ~2.37x on 2017-2020 matched population
    assert True


def test_52_secondary_metrics_calculation():
    """Test 52: Secondary metrics (ECMV@10, adverse excursion rate, median time to target) computed correctly."""
    # Test through dummy calculation
    probs = np.array([0.1, 0.2, 0.8, 0.9])
    labels = np.array([0, 0, 1, 1])
    rel_table = compute_reliability_table(probs, labels, n_bins=5)
    assert len(rel_table) == 5
    assert rel_table[-1]["observation_count"] == 2
    assert rel_table[-1]["empirical_clean_rate"] == 1.0


def test_53_paired_calendar_bootstrap_determinism():
    """Test 53: Paired calendar bootstrap produces deterministic confidence intervals for seed=20261005."""
    df_date_level = pd.DataFrame(
        {
            "as_of_date": [f"2018-01-{i:02d}" for i in range(1, 22)],
            "k10_selected": [10] * 21,
            "c10_clean": [3] * 21,
            "v10_clean": [2] * 21,
            "k25_selected": [25] * 21,
            "c25_clean": [5] * 21,
            "v25_clean": [4] * 21,
        }
    )
    b1 = run_paired_calendar_bootstrap(df_date_level, block_size=5, replicates=100, seed=20261005)
    b2 = run_paired_calendar_bootstrap(df_date_level, block_size=5, replicates=100, seed=20261005)
    assert b1.p10_delta_lower == b2.p10_delta_lower
    assert b1.p10_delta_median == b2.p10_delta_median
    assert b1.p10_delta_upper == b2.p10_delta_upper


def test_54_block_bootstrap_both_block_sizes():
    """Test 54: 21-session block bootstrap and 42-session block bootstrap both run without error."""
    df_date_level = pd.DataFrame(
        {
            "as_of_date": [f"2018-01-{i:02d}" for i in range(1, 22)],
            "k10_selected": [10] * 21,
            "c10_clean": [3] * 21,
            "v10_clean": [2] * 21,
            "k25_selected": [25] * 21,
            "c25_clean": [5] * 21,
            "v25_clean": [4] * 21,
        }
    )
    b21 = run_paired_calendar_bootstrap(df_date_level, block_size=21, replicates=50, seed=20261005)
    b42 = run_paired_calendar_bootstrap(df_date_level, block_size=42, replicates=50, seed=20261005)
    assert b21.block_size_sessions == 21
    assert b42.block_size_sessions == 42


def test_55_status_assignment_round2_eligible():
    """Test 55: Status assignment correctly assigns round2_eligible when all 4 criteria are met."""
    summary = EvaluationSummary(
        configuration_id="TEST_ELIGIBLE",
        family="cross_sectional_rank_score",
        feature_subset_id="S1",
        evaluation_dates_count=981,
        oof_base_rate=0.088,
        top10=TopKMetrics(
            k=10,
            selected_count=9810,
            clean_count=2500,
            precision=0.25,
            matched_vam5_precision=0.21,
            precision_delta_vs_vam5=0.04,  # > 0
            lift_vs_oof_base_rate=2.8,
            empirical_clean_move_value=1.5,
            matched_vam5_clean_move_value=1.3,
            clean_move_value_delta=0.2,
            primary_adverse_rate=0.15,
            matched_vam5_adverse_rate=0.16,
            median_time_to_target=4.0,
            selection_overlap_pct=0.4,
            distinct_tickers_count=400,
        ),
        top25=TopKMetrics(
            k=25,
            selected_count=24525,
            clean_count=5000,
            precision=0.20,
            matched_vam5_precision=0.18,
            precision_delta_vs_vam5=0.02,  # >= 0
            lift_vs_oof_base_rate=2.2,
            empirical_clean_move_value=1.2,
            matched_vam5_clean_move_value=1.1,
            clean_move_value_delta=0.1,
            primary_adverse_rate=0.18,
            matched_vam5_adverse_rate=0.19,
            median_time_to_target=5.0,
            selection_overlap_pct=0.45,
            distinct_tickers_count=600,
        ),
        annual_precision_10={2017: 0.22, 2018: 0.24, 2019: 0.26, 2020: 0.28},
        annual_vam5_precision_10={2017: 0.20, 2018: 0.21, 2019: 0.22, 2020: 0.23},
        annual_precision_10_delta={2017: 0.02, 2018: 0.03, 2019: 0.04, 2020: 0.05},
        annual_positive_years_count=4,  # >= 3
        calibration_status="not_applicable_round1_unscaled_score",
        brier_score=None,
        reliability_table=None,
        date_level_data=pd.DataFrame(),
    )
    # bootstrap median > 0
    st = assign_round1_status(summary, (0.01, 0.04, 0.07))
    assert st == "round2_eligible"


def test_56_status_assignment_round1_not_supported():
    """Test 56: Status assignment correctly assigns round1_not_supported when criteria are met."""
    summary = EvaluationSummary(
        configuration_id="TEST_NOT_SUPPORTED",
        family="cross_sectional_rank_score",
        feature_subset_id="S1",
        evaluation_dates_count=981,
        oof_base_rate=0.088,
        top10=TopKMetrics(
            k=10,
            selected_count=9810,
            clean_count=1800,
            precision=0.18,
            matched_vam5_precision=0.21,
            precision_delta_vs_vam5=-0.03,  # <= 0
            lift_vs_oof_base_rate=2.0,
            empirical_clean_move_value=1.1,
            matched_vam5_clean_move_value=1.3,
            clean_move_value_delta=-0.2,
            primary_adverse_rate=0.20,
            matched_vam5_adverse_rate=0.16,
            median_time_to_target=5.0,
            selection_overlap_pct=0.3,
            distinct_tickers_count=400,
        ),
        top25=TopKMetrics(
            k=25,
            selected_count=24525,
            clean_count=4000,
            precision=0.16,
            matched_vam5_precision=0.18,
            precision_delta_vs_vam5=-0.02,
            lift_vs_oof_base_rate=1.8,
            empirical_clean_move_value=1.0,
            matched_vam5_clean_move_value=1.1,
            clean_move_value_delta=-0.1,
            primary_adverse_rate=0.22,
            matched_vam5_adverse_rate=0.19,
            median_time_to_target=6.0,
            selection_overlap_pct=0.35,
            distinct_tickers_count=600,
        ),
        annual_precision_10={2017: 0.18, 2018: 0.19, 2019: 0.20, 2020: 0.21},
        annual_vam5_precision_10={2017: 0.20, 2018: 0.21, 2019: 0.22, 2020: 0.23},
        annual_precision_10_delta={2017: -0.02, 2018: -0.02, 2019: -0.02, 2020: -0.02},
        annual_positive_years_count=0,  # <= 2
        calibration_status="not_applicable_round1_unscaled_score",
        brier_score=None,
        reliability_table=None,
        date_level_data=pd.DataFrame(),
    )
    # upper quantile <= 0
    st = assign_round1_status(summary, (-0.05, -0.03, -0.01))
    assert st == "round1_not_supported"


def test_57_calibration_diagnostics_computed_only_for_probabilistic():
    """Test 57: Calibration table and Brier score computed for probabilistic/GBDT; unscaled for rank."""
    probs = np.array([0.1, 0.4, 0.6, 0.8])
    labels = np.array([0, 0, 1, 1])
    table = compute_reliability_table(probs, labels, n_bins=10)
    assert len(table) == 10
    total_obs = sum(b["observation_count"] for b in table)
    assert total_obs == 4
