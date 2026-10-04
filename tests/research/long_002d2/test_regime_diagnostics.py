"""Tests for SPY market regime diagnostics."""
from __future__ import annotations

import pandas as pd

from tradex.research.long_002d2.diagnostics import (
    compute_spy_date_regimes,
    evaluate_regime_diagnostics,
)


def test_spy_date_regime_mapping() -> None:
    """Verify that dates are partitioned into Lower (30%), Middle (40%), and Upper (30%)."""
    # Create 10 unique dates with distinct SPY returns from 1.0 to 10.0
    rows = []
    for i in range(1, 11):
        d = f"2017-01-{i:02d}"
        rows.append({"as_of_date": d, "spy_return_20": float(i)})
    df = pd.DataFrame(rows)

    regimes = compute_spy_date_regimes(df)
    assert len(regimes) == 10

    # With 10 dates sorted descending:
    # rank 0: 10.0 (pct 100%) -> upper
    # rank 1: 9.0  (pct 90%)  -> upper
    # rank 2: 8.0  (pct 80%)  -> upper
    # rank 3: 7.0  (pct 70%)  -> upper (pct >= 70)
    # rank 4: 6.0  (pct 60%)  -> middle
    # rank 5: 5.0  (pct 50%)  -> middle
    # rank 6: 4.0  (pct 40%)  -> middle
    # rank 7: 3.0  (pct 30%)  -> lower (pct <= 30)
    # rank 8: 2.0  (pct 20%)  -> lower
    # rank 9: 1.0  (pct 10%)  -> lower
    upper_dates = [d for d, r in regimes.items() if r == "upper_regime"]
    middle_dates = [d for d, r in regimes.items() if r == "middle_regime"]
    lower_dates = [d for d, r in regimes.items() if r == "lower_regime"]

    assert len(lower_dates) == 3
    assert len(middle_dates) == 3 or len(middle_dates) == 4
    assert len(upper_dates) == 4 or len(upper_dates) == 3
    assert len(lower_dates) + len(middle_dates) + len(upper_dates) == 10


def test_regime_diagnostics_calculation() -> None:
    """Verify calculation of descriptive regime metrics."""
    date_regime_map = {
        "2017-01-01": "lower_regime",
        "2017-01-02": "middle_regime",
        "2017-01-03": "upper_regime",
    }
    date_results = {
        "2017-01-01": {"k_date": 10, "cand_clean": 2, "vam5_clean": 1},
        "2017-01-02": {"k_date": 10, "cand_clean": 3, "vam5_clean": 2},
        "2017-01-03": {"k_date": 10, "cand_clean": 4, "vam5_clean": 3},
    }
    metrics = evaluate_regime_diagnostics(date_results, date_regime_map)
    assert len(metrics) == 3
    by_name = {m.regime_name: m for m in metrics}

    lower = by_name["lower_regime"]
    assert lower.selected_count == 10
    assert lower.candidate_clean_count == 2
    assert lower.matched_vam5_clean_count == 1
    assert lower.candidate_precision == 0.20
    assert lower.matched_vam5_precision == 0.10
    assert lower.absolute_delta == 0.10
