"""Empirical reproduction and integration tests for LONG-002E2."""

from __future__ import annotations

import pytest

from tradex.research.long_002e2.diagnostics import run_all_e2_diagnostics
from tradex.research.long_002e2.loader import load_e2_datasets
from tradex.research.long_002e2.selection import build_date_selections
from tradex.research.long_002e2.spec import (
    DEV_END,
    DEV_START,
    E1_PREDICTION_PATH,
    EXPECTED_PREDICTION_ROW_COUNT,
    JOIN_KEYS,
    POPULATION_CUTOFF,
)


@pytest.fixture(scope="module")
def real_e2_datasets():
    """Load real datasets if present, skip test if absent (safe for CI)."""
    if not E1_PREDICTION_PATH.exists():
        pytest.skip("Required E1 prediction parquet not found (safe for CI).")
    return load_e2_datasets()


def test_14_15_20_dataset_integrity(real_e2_datasets) -> None:
    df_pred, _df_vam5, _df_features, _digests = real_e2_datasets
    assert len(df_pred) == EXPECTED_PREDICTION_ROW_COUNT
    assert df_pred.duplicated(subset=JOIN_KEYS).sum() == 0
    assert (df_pred["cutoff_time"] == POPULATION_CUTOFF).all()
    assert str(df_pred["as_of_date"].min()) >= DEV_START
    assert str(df_pred["as_of_date"].max()) <= DEV_END
    assert df_pred["as_of_date"].nunique() == 730


def test_21_through_27_reproduction(real_e2_datasets) -> None:
    df_pred, df_vam5, _df_features, _digests = real_e2_datasets

    # Merge on join keys
    df_joined = df_pred.merge(
        df_vam5[
            [
                "immutable_security_id",
                "as_of_date",
                "cutoff_time",
                "cross_sectional_rank",
                "raw_score_or_return",
            ]
        ],
        on=JOIN_KEYS,
        how="inner",
        validate="one_to_one",
    )
    cand_10, cand_25, vam5_10, vam5_25, records = build_date_selections(df_joined)

    # Candidate and baseline selected count equal per date (Requirement 27)
    for r in records:
        d = r["as_of_date"]
        assert len(cand_10[d]) == len(vam5_10[d])
        assert len(cand_25[d]) == len(vam5_25[d])

    # Check pooled selection counts
    total_10_selected = sum(r["k10_selected"] for r in records)
    total_25_selected = sum(r["k25_selected"] for r in records)
    assert total_10_selected == 7165
    assert total_25_selected == 17875

    # Run full diagnostics
    diag_res = run_all_e2_diagnostics()
    reprod = diag_res["reproduction_check"]

    assert reprod["status"] == "exact_match"
    assert abs(reprod["pooled_metrics"]["candidate_p10"] - 0.268109) <= 1e-5
    assert abs(reprod["pooled_metrics"]["vam5_p10"] - 0.240893) <= 1e-5
    assert abs(reprod["pooled_metrics"]["p10_delta"] - 0.027216) <= 1e-5
    assert abs(reprod["pooled_metrics"]["candidate_p25"] - 0.252420) <= 1e-5
    assert abs(reprod["pooled_metrics"]["vam5_p25"] - 0.209510) <= 1e-5

    ann = reprod["annual_metrics"]
    assert abs(ann["2018"]["p10_delta"] - 0.039841) <= 1e-5
    assert abs(ann["2019"]["p10_delta"] - 0.050000) <= 1e-5
    assert abs(ann["2020"]["p10_delta"] - (-0.014520)) <= 1e-5

    # All 12 logistic configs share the 2018+/2019+/2020- pattern
    assert diag_res["family_context"]["all_12_share_2018pos_2019pos_2020neg_pattern"] is True
