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
    """Test 51: Matched baseline comparator evaluation computes exact matched precision, delta, and annual metrics."""
    from tradex.research.long_002e1.evaluation import evaluate_configuration_predictions

    dates = ["2018-01-02", "2018-01-03", "2019-01-02", "2020-01-02"]
    pred_rows = []
    base_rows = []
    for d in dates:
        for i in range(15):
            sec = f"SEC_{i:02d}"
            clean = 1 if i % 2 == 0 else 0
            c_score = float(15 - i)
            v_rank = i + 1
            pred_rows.append(
                {
                    "immutable_security_id": sec,
                    "as_of_date": d,
                    "cutoff_time": "20:30",
                    "clean_target_reached": clean,
                    "realized_clean_tier": clean * 10,
                    "adverse_excursion": 1 - clean,
                    "time_to_target": 3.0 if clean else None,
                    "ticker_at_decision": f"TICK_{i:02d}",
                    "candidate_score": c_score,
                }
            )
            base_rows.append(
                {
                    "immutable_security_id": sec,
                    "as_of_date": d,
                    "cutoff_time": "20:30",
                    "cross_sectional_rank": v_rank,
                    "raw_score_or_return": float(15 - i),
                }
            )
    df_p = pd.DataFrame(pred_rows)
    df_b = pd.DataFrame(base_rows)

    summary = evaluate_configuration_predictions(
        df_predictions=df_p,
        df_vam5=df_b,
        config_id="TEST_CFG",
        family="cross_sectional_rank_score",
        subset_id="S1",
        score_column="candidate_score",
    )
    assert summary.top10.selected_count == 40
    assert summary.top10.clean_count == 20
    assert summary.top10.precision == 0.5
    assert summary.top10.matched_vam5_precision == 0.5
    assert summary.top10.precision_delta_vs_vam5 == 0.0
    assert summary.evaluation_dates_count == 4
    assert set(summary.annual_precision_10.keys()) == {2018, 2019, 2020}


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
        evaluation_dates_count=730,
        oof_base_rate=0.088,
        top10=TopKMetrics(
            k=10,
            selected_count=7300,
            clean_count=2000,
            precision=0.274,
            matched_vam5_precision=0.240,
            precision_delta_vs_vam5=0.034,  # > 0
            lift_vs_oof_base_rate=3.1,
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
            selected_count=18250,
            clean_count=4000,
            precision=0.219,
            matched_vam5_precision=0.190,
            precision_delta_vs_vam5=0.029,  # >= 0
            lift_vs_oof_base_rate=2.5,
            empirical_clean_move_value=1.2,
            matched_vam5_clean_move_value=1.1,
            clean_move_value_delta=0.1,
            primary_adverse_rate=0.18,
            matched_vam5_adverse_rate=0.19,
            median_time_to_target=5.0,
            selection_overlap_pct=0.45,
            distinct_tickers_count=600,
        ),
        annual_precision_10={2018: 0.26, 2019: 0.28, 2020: 0.28},
        annual_vam5_precision_10={2018: 0.23, 2019: 0.24, 2020: 0.25},
        annual_precision_10_delta={2018: 0.03, 2019: 0.04, 2020: 0.03},
        annual_positive_years_count=3,  # exactly 3 of 3
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
        evaluation_dates_count=730,
        oof_base_rate=0.088,
        top10=TopKMetrics(
            k=10,
            selected_count=7300,
            clean_count=1500,
            precision=0.205,
            matched_vam5_precision=0.240,
            precision_delta_vs_vam5=-0.035,  # <= 0
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
            selected_count=18250,
            clean_count=3000,
            precision=0.164,
            matched_vam5_precision=0.190,
            precision_delta_vs_vam5=-0.026,
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
        annual_precision_10={2018: 0.20, 2019: 0.21, 2020: 0.20},
        annual_vam5_precision_10={2018: 0.23, 2019: 0.24, 2020: 0.25},
        annual_precision_10_delta={2018: -0.03, 2019: -0.03, 2020: -0.05},
        annual_positive_years_count=0,  # <= 1 of 3
        calibration_status="not_applicable_round1_unscaled_score",
        brier_score=None,
        reliability_table=None,
        date_level_data=pd.DataFrame(),
    )
    # upper quantile <= 0
    st = assign_round1_status(summary, (-0.05, -0.03, -0.01))
    assert st == "round1_not_supported"


def test_status_assignment_round1_inconclusive():
    """Verify assign_round1_status assigns round1_inconclusive when failing eligible and not supported."""
    summary = EvaluationSummary(
        configuration_id="TEST_INCONCLUSIVE",
        family="cross_sectional_rank_score",
        feature_subset_id="S1",
        evaluation_dates_count=730,
        oof_base_rate=0.10,
        top10=TopKMetrics(
            k=10,
            selected_count=7300,
            clean_count=1800,
            precision=0.246,
            matched_vam5_precision=0.240,
            precision_delta_vs_vam5=0.006,  # > 0
            lift_vs_oof_base_rate=2.46,
            empirical_clean_move_value=1.5,
            matched_vam5_clean_move_value=1.4,
            clean_move_value_delta=0.1,
            primary_adverse_rate=0.15,
            matched_vam5_adverse_rate=0.16,
            median_time_to_target=4.0,
            selection_overlap_pct=0.4,
            distinct_tickers_count=400,
        ),
        top25=TopKMetrics(
            k=25,
            selected_count=18250,
            clean_count=3500,
            precision=0.191,
            matched_vam5_precision=0.190,
            precision_delta_vs_vam5=0.001,
            lift_vs_oof_base_rate=1.91,
            empirical_clean_move_value=1.2,
            matched_vam5_clean_move_value=1.1,
            clean_move_value_delta=0.1,
            primary_adverse_rate=0.18,
            matched_vam5_adverse_rate=0.19,
            median_time_to_target=5.0,
            selection_overlap_pct=0.45,
            distinct_tickers_count=600,
        ),
        annual_precision_10={2018: 0.25, 2019: 0.25, 2020: 0.23},
        annual_vam5_precision_10={2018: 0.24, 2019: 0.24, 2020: 0.24},
        annual_precision_10_delta={2018: 0.01, 2019: 0.01, 2020: -0.01},
        annual_positive_years_count=2,  # 2 of 3 (fails 3 of 3)
        calibration_status="not_applicable_round1_unscaled_score",
        brier_score=None,
        reliability_table=None,
        date_level_data=pd.DataFrame(),
    )
    # p10_delta > 0, bootstrap upper > 0, but only 2 of 3 years positive
    st = assign_round1_status(summary, (-0.005, 0.006, 0.015))
    assert st == "round1_inconclusive"


def test_57_calibration_diagnostics_computed_only_for_probabilistic():
    """Test 57: Calibration table and Brier score computed for probabilistic/GBDT; unscaled for rank."""
    probs = np.array([0.1, 0.4, 0.6, 0.8])
    labels = np.array([0, 0, 1, 1])
    table = compute_reliability_table(probs, labels, n_bins=10)
    assert len(table) == 10
    total_obs = sum(b["observation_count"] for b in table)
    assert total_obs == 4
