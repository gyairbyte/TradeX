"""Tests for determinism, seed reproducibility, and redundancy invariance."""
from __future__ import annotations

import numpy as np
import pandas as pd

from tradex.research.long_002d.bootstrap import run_feature_block_bootstrap
from tradex.research.long_002d.census import compute_cross_sectional_ranks_for_feature
from tradex.research.long_002d.spec import FEATURE_MAP


def test_stock_minus_spy_produces_identical_ranking_as_return_20():
    """Verify redundancy invariant: stock_minus_spy_20 ranking is identical to return_20."""
    # Synthetic cross section on a single date
    dates = ["2016-01-15"] * 5
    sec_ids = ["SEC_A", "SEC_B", "SEC_C", "SEC_D", "SEC_E"]
    returns_20 = [0.05, 0.12, -0.03, 0.20, 0.08]
    spy_ret_20 = 0.04
    stock_minus_spy = [r - spy_ret_20 for r in returns_20]

    df = pd.DataFrame(
        {
            "as_of_date": dates,
            "immutable_security_id": sec_ids,
            "return_20": returns_20,
            "stock_minus_spy_20": stock_minus_spy,
        }
    )

    f_ret20 = FEATURE_MAP["return_20"]
    f_diff = FEATURE_MAP["stock_minus_spy_20"]

    pct_ret, dec_ret, top10_ret, _ = compute_cross_sectional_ranks_for_feature(df, f_ret20)
    pct_diff, dec_diff, top10_diff, _ = compute_cross_sectional_ranks_for_feature(df, f_diff)

    assert np.array_equal(pct_ret, pct_diff)
    assert np.array_equal(dec_ret, dec_diff)
    assert np.array_equal(top10_ret, top10_diff)


def test_bootstrap_determinism_with_fixed_seed():
    """Verify that repeated bootstrap executions with fixed seed produce identical distributions."""
    rng = np.random.default_rng(123)
    n = 1000
    dates = np.array(["2016-01-04"] * 500 + ["2016-01-05"] * 500)
    valid_mask = np.ones(n, dtype=bool)
    fav_mask = rng.random(n) < 0.10
    clean_labels = rng.random(n) < 0.0886
    sessions = ["2016-01-04", "2016-01-05"]

    res1_sum, res1_dist = run_feature_block_bootstrap(
        dates=dates,
        valid_mask=valid_mask,
        fav_mask=fav_mask,
        clean_labels=clean_labels,
        sessions_ordered=sessions,
        block_sizes=(21,),
        num_bootstraps=100,
        seed=20260927,
    )

    res2_sum, res2_dist = run_feature_block_bootstrap(
        dates=dates,
        valid_mask=valid_mask,
        fav_mask=fav_mask,
        clean_labels=clean_labels,
        sessions_ordered=sessions,
        block_sizes=(21,),
        num_bootstraps=100,
        seed=20260927,
    )

    assert res1_sum[21] == res2_sum[21]
    assert np.array_equal(res1_dist[21], res2_dist[21])
