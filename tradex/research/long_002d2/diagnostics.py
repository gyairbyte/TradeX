"""SPY market-regime descriptive diagnostics for LONG-002D2."""
from __future__ import annotations

import pandas as pd

from tradex.research.long_002d2.models import RegimeDiagnosticMetrics


def compute_spy_date_regimes(
    df_merged: pd.DataFrame,
) -> dict[str, str]:
    """Map each unique development date to one of three fixed SPY 20-session return regimes.

    Semantics (matching D1 date-level ranking):
    - Unique dates sorted descending by spy_return_20, tie-break date ASC.
    - Percentile: 100.0 * (N_dates - rank_idx) / N_dates.
    - lower_regime: percentile <= 30.0 (bottom 30%).
    - middle_regime: 30.0 < percentile < 70.0 (middle 40%).
    - upper_regime: percentile >= 70.0 (top 30%).

    Returns:
        dict mapping date_str -> regime_name
    """
    # Extract unique date-level SPY returns
    date_spy_df = (
        df_merged[["as_of_date", "spy_return_20"]]
        .dropna()
        .drop_duplicates(subset=["as_of_date"])
    )
    date_val_map: dict[str, float] = dict(
        zip(date_spy_df["as_of_date"], date_spy_df["spy_return_20"])
    )

    # Sort descending by return, date ascending
    sorted_dates = sorted(
        date_val_map.items(),
        key=lambda item: (-item[1], item[0]),
    )
    n_dates = len(sorted_dates)
    if n_dates == 0:
        return {}

    date_regime_map: dict[str, str] = {}
    for rank_idx, (d, _) in enumerate(sorted_dates):
        pct = 100.0 * (n_dates - rank_idx) / n_dates
        if pct <= 30.0:
            regime = "lower_regime"
        elif pct >= 70.0:
            regime = "upper_regime"
        else:
            regime = "middle_regime"
        date_regime_map[d] = regime

    return date_regime_map


def evaluate_regime_diagnostics(
    date_results: dict[str, dict],
    date_regime_map: dict[str, str],
) -> list[RegimeDiagnosticMetrics]:
    """Compute descriptive performance metrics across the 3 fixed SPY return regimes."""
    regime_defs = [
        ("lower_regime", "bottom 30% of DEVELOPMENT dates by SPY 20-session return", 0.0, 30.0),
        ("middle_regime", "middle 40% of DEVELOPMENT dates by SPY 20-session return", 30.0, 70.0),
        ("upper_regime", "top 30% of DEVELOPMENT dates by SPY 20-session return", 70.0, 100.0),
    ]

    metrics_list: list[RegimeDiagnosticMetrics] = []

    for name, desc, p_min, p_max in regime_defs:
        regime_dates = [d for d, r in date_regime_map.items() if r == name]
        d_count = len(regime_dates)
        tot_sel = 0
        c_clean = 0
        v_clean = 0

        for d in regime_dates:
            res = date_results.get(d)
            if res is not None:
                tot_sel += res["k_date"]
                c_clean += res["cand_clean"]
                v_clean += res["vam5_clean"]

        c_prec = float(c_clean / tot_sel) if tot_sel > 0 else 0.0
        v_prec = float(v_clean / tot_sel) if tot_sel > 0 else 0.0
        abs_delta = c_prec - v_prec
        ratio = float(c_prec / v_prec) if v_prec > 0 else 0.0

        metrics_list.append(
            RegimeDiagnosticMetrics(
                regime_name=name,
                description=desc,
                percentile_min=p_min,
                percentile_max=p_max,
                date_count=d_count,
                selected_count=tot_sel,
                candidate_clean_count=c_clean,
                candidate_precision=round(c_prec, 6),
                matched_vam5_clean_count=v_clean,
                matched_vam5_precision=round(v_prec, 6),
                absolute_delta=round(abs_delta, 6),
                precision_ratio=round(ratio, 4),
            )
        )

    return metrics_list
