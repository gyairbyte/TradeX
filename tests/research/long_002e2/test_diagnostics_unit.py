"""Deterministic synthetic unit tests for all diagnostic algorithms in LONG-002E2."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradex.research.long_002e2.bootstrap import run_annual_paired_bootstrap
from tradex.research.long_002e2.concentration import (
    compute_concentration_metrics,
)
from tradex.research.long_002e2.feature_profiles import (
    compute_cross_sectional_feature_percentiles,
)
from tradex.research.long_002e2.localization import compute_localization_metrics
from tradex.research.long_002e2.probabilities import (
    compute_reliability_table,
)
from tradex.research.long_002e2.quarters import (
    CALENDAR_QUARTERS,
    date_to_quarter,
)
from tradex.research.long_002e2.regimes import (
    compute_spy_date_regimes,
)
from tradex.research.long_002e2.selection import build_date_selections
from tradex.research.long_002e2.selection_sets import (
    partition_date_selections,
)
from tradex.research.long_002e2.spec import (
    BOOTSTRAP_BLOCK_SIZE,
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
)


@pytest.fixture
def synthetic_joined_data() -> pd.DataFrame:
    """Generate synthetic joined evaluation data across 2 dates with 20 securities each."""
    rows = []
    dates = ["2018-01-02", "2018-01-03", "2019-01-02", "2020-01-02"]
    for d in dates:
        for i in range(20):
            sec_id = f"SEC_{i:03d}"
            prob = (i + 1) / 20.0  # higher i has higher prob
            rank = 20 - i  # lower rank is higher momentum
            rows.append(
                {
                    "immutable_security_id": sec_id,
                    "as_of_date": d,
                    "cutoff_time": "20:30",
                    "candidate_probability": prob,
                    "cross_sectional_rank": rank,
                    "clean_target_reached": (i % 2 == 0),
                    "realized_clean_tier": 10 if (i % 2 == 0) else 0,
                    "adverse_excursion": (i % 3 == 0),
                    "time_to_target": 4.0 if (i % 2 == 0) else np.nan,
                }
            )
    return pd.DataFrame(rows)


# --- Requirements 28-32: Annual Paired Bootstrap ---
def test_28_through_32_bootstrap_deterministic() -> None:
    # Synthetic date records
    records = []
    for yr in ["2018", "2019", "2020"]:
        for d in range(1, 45):  # 44 dates per year
            records.append(
                {
                    "as_of_date": f"{yr}-02-{d:02d}" if d <= 28 else f"{yr}-03-{d - 28:02d}",
                    "k10_selected": 10,
                    "c10_clean": 3,
                    "v10_clean": 2,
                    "hit_delta_10": 1,
                }
            )
    res = run_annual_paired_bootstrap(
        records,
        block_size=BOOTSTRAP_BLOCK_SIZE,
        replicates=BOOTSTRAP_REPLICATES,
        seed=BOOTSTRAP_SEED,
    )
    assert res["block_size_sessions"] == 21
    assert res["replicates_count"] == 1000
    assert res["seed"] == 20261006
    assert set(res["years"].keys()) == {"2018", "2019", "2020"}
    for yr in ["2018", "2019", "2020"]:
        yr_res = res["years"][yr]
        assert yr_res["candidate_p10"] == 0.3
        assert yr_res["vam5_p10"] == 0.2
        assert yr_res["delta"] == 0.1
        assert yr_res["ci_2_5"] <= yr_res["bootstrap_median"] <= yr_res["ci_97_5"]


# --- Requirements 33-36: Quarters Decomposition ---
def test_33_through_36_calendar_quarters() -> None:
    assert len(CALENDAR_QUARTERS) == 12
    assert date_to_quarter("2018-01-15") == "2018Q1"
    assert date_to_quarter("2018-04-01") == "2018Q2"
    assert date_to_quarter("2019-07-20") == "2019Q3"
    assert date_to_quarter("2020-11-10") == "2020Q4"


# --- Requirements 37-41: SPY Regimes ---
def test_37_through_41_spy_regimes() -> None:
    # Function checks 730 dates, so let's mock 730 dates
    rows_730 = []
    for d_idx in range(730):
        d = f"2018-01-01_{d_idx}"
        ret = float(d_idx) / 730.0
        for s in range(2):
            rows_730.append(
                {
                    "immutable_security_id": f"SEC_{s}",
                    "as_of_date": d,
                    "cutoff_time": "20:30",
                    "spy_return_20": ret,
                }
            )
    df_730 = pd.DataFrame(rows_730)
    mapping, q30, q70, counts = compute_spy_date_regimes(df_730)
    assert len(mapping) == 730
    assert set(counts.keys()) == {"LOWER", "MIDDLE", "UPPER"}
    assert counts["LOWER"] + counts["MIDDLE"] + counts["UPPER"] == 730
    assert q30 <= q70


# --- Requirements 42-45: Selection Sets ---
def test_42_through_45_selection_sets(synthetic_joined_data: pd.DataFrame) -> None:
    cand_10, _cand_25, vam5_10, _vam5_25, _records = build_date_selections(synthetic_joined_data)
    df_overlap, df_logit, df_vam5 = partition_date_selections(cand_10, vam5_10)

    # For each date, candidate = overlap + logit_only, baseline = overlap + vam5_only
    for d in cand_10:
        c_ids = set(cand_10[d]["immutable_security_id"])
        v_ids = set(vam5_10[d]["immutable_security_id"])

        o_ids = (
            set(df_overlap[df_overlap["as_of_date"] == d]["immutable_security_id"])
            if len(df_overlap)
            else set()
        )
        l_ids = (
            set(df_logit[df_logit["as_of_date"] == d]["immutable_security_id"])
            if len(df_logit)
            else set()
        )
        vm_ids = (
            set(df_vam5[df_vam5["as_of_date"] == d]["immutable_security_id"])
            if len(df_vam5)
            else set()
        )

        assert c_ids == o_ids.union(l_ids)
        assert v_ids == o_ids.union(vm_ids)
        assert len(o_ids.intersection(l_ids)) == 0
        assert len(o_ids.intersection(vm_ids)) == 0
        assert len(l_ids.intersection(vm_ids)) == 0


# --- Requirements 46-49: Feature Profile Drift ---
def test_46_through_49_feature_percentiles() -> None:
    dates = ["2018-01-02"]
    rows = []
    for s_idx in range(5):
        rows.append(
            {
                "immutable_security_id": f"SEC_{s_idx}",
                "as_of_date": dates[0],
                "cutoff_time": "20:30",
                "return_5": float(s_idx),  # SEC_4 has highest (4.0), SEC_0 has lowest (0.0)
                "atr_pct_14": float(s_idx),
                "return_20": float(s_idx),
                "return_60": float(s_idx),
                "close_vs_sma20": float(s_idx),
                "close_vs_sma60": float(s_idx),
                "sma20_slope_5": float(s_idx),
                "relative_volume_20": float(s_idx),
            }
        )
    df_feat = pd.DataFrame(rows)
    df_pct = compute_cross_sectional_feature_percentiles(df_feat)
    # Highest value should get 100.0%, lowest gets 20.0%
    sec_4_pct = df_pct[df_pct["immutable_security_id"] == "SEC_4"]["return_5_percentile"].iloc[0]
    sec_0_pct = df_pct[df_pct["immutable_security_id"] == "SEC_0"]["return_5_percentile"].iloc[0]
    assert sec_4_pct == 100.0
    assert sec_0_pct == 20.0


# --- Requirements 50-51: Concentration Metrics ---
def test_50_51_concentration_deterministic() -> None:
    # 4 selections of equal counts -> HHI = 4 * (0.25^2) = 0.25, eff_n = 4.0
    df_sel = pd.DataFrame(
        {
            "immutable_security_id": ["A", "B", "C", "D"],
            "as_of_date": ["2018-01-02"] * 4,
        }
    )
    res = compute_concentration_metrics(df_sel)
    assert res["distinct_immutable_securities_count"] == 4
    assert res["maximum_selection_count"] == 1
    assert res["top_5_securities_share"] == 1.0
    assert res["herfindahl_hirschman_index"] == 0.25
    assert res["effective_number_of_securities"] == 4.0


# --- Requirements 52-54: Probabilities ---
def test_52_through_54_probabilities() -> None:
    probs = np.array([0.05, 0.15, 0.25, 0.85, 0.95])
    labels = np.array([0, 0, 1, 1, 1])
    table = compute_reliability_table(probs, labels, n_bins=10)
    assert len(table) == 10
    total_obs = sum(b["observation_count"] for b in table)
    assert total_obs == 5


# --- Requirements 55-59: Localization Rules ---
def test_55_through_59_localization_decision_rules() -> None:
    # Case 1: Quarter 1 accounts for 80% of negative hit loss, remaining 3 have >= 0 delta -> Rule A PASSES
    q_res = {
        "2020Q1": {"clean_hit_difference": -80},
        "2020Q2": {"clean_hit_difference": -20},
        "2020Q3": {"clean_hit_difference": 15},
        "2020Q4": {"clean_hit_difference": 10},
    }
    # annual delta = -80 + -20 + 15 + 10 = -75
    # remaining for Q1 = -75 - (-80) = +5 >= 0
    # Q1 loss = 80, Q2 loss = 20, total loss = 100 -> Q1 share = 80 / 100 = 80% >= 60%
    r_res = {
        "2020": {
            "LOWER": {"clean_hit_difference": -30},
            "MIDDLE": {"clean_hit_difference": -25},
            "UPPER": {"clean_hit_difference": -20},
        }
    }
    ann_metrics = {"2020": {"clean_hit_difference": -75}}
    _loc, dec = compute_localization_metrics(q_res, r_res, ann_metrics)
    assert dec["calendar_localization_passed"] is True
    assert dec["diagnostic_disposition"] == "bounded_followup_hypothesis_warranted"
    assert dec["recommended_next_action"] == "preregister_one_bounded_followup_hypothesis"

    # Case 2: Diffuse losses across quarters and regimes -> NEITHER PASSES
    q_res_diffuse = {
        "2020Q1": {"clean_hit_difference": -25},
        "2020Q2": {"clean_hit_difference": -25},
        "2020Q3": {"clean_hit_difference": -25},
        "2020Q4": {"clean_hit_difference": -25},
    }
    r_res_diffuse = {
        "2020": {
            "LOWER": {"clean_hit_difference": -35},
            "MIDDLE": {"clean_hit_difference": -35},
            "UPPER": {"clean_hit_difference": -30},
        }
    }
    ann_metrics_diffuse = {"2020": {"clean_hit_difference": -100}}
    _loc2, dec2 = compute_localization_metrics(q_res_diffuse, r_res_diffuse, ann_metrics_diffuse)
    assert dec2["calendar_localization_passed"] is False
    assert dec2["market_context_localization_passed"] is False
    assert dec2["diagnostic_disposition"] == "no_bounded_regime_hypothesis_supported"
    assert (
        dec2["recommended_next_action"] == "close_initial_long_002e_search_preserve_unused_budget"
    )
