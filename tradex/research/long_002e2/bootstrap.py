"""Paired calendar-block bootstrap uncertainty estimation for LONG-002E2."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from tradex.research.long_002e2.spec import (
    BOOTSTRAP_BLOCK_SIZE,
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
)


def run_annual_paired_bootstrap(
    date_records: list[dict[str, Any]],
    block_size: int = BOOTSTRAP_BLOCK_SIZE,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Execute 21-session paired calendar-block bootstrap separately for 2018, 2019, 2020.

    Preserves full daily cross-sections within sampled blocks.
    Candidate and VAM5 baseline evaluate on identical sampled blocks.
    """
    df_dates = pd.DataFrame(date_records).sort_values("as_of_date").reset_index(drop=True)
    years = ["2018", "2019", "2020"]
    annual_results: dict[str, dict[str, Any]] = {}

    for yr in years:
        df_yr = df_dates[df_dates["as_of_date"].str.startswith(yr)].reset_index(drop=True)
        n_dates = len(df_yr)
        if n_dates == 0:
            continue

        # Form non-overlapping contiguous calendar blocks of block_size
        n_blocks = int(np.ceil(n_dates / block_size))
        blocks: list[pd.DataFrame] = []
        for b in range(n_blocks):
            start_idx = b * block_size
            end_idx = min(start_idx + block_size, n_dates)
            blocks.append(df_yr.iloc[start_idx:end_idx])

        # Pre-extract totals per block (k10_selected, c10_clean, v10_clean)
        block_totals = np.zeros((len(blocks), 3), dtype=float)
        for i, blk in enumerate(blocks):
            block_totals[i, 0] = blk["k10_selected"].sum()
            block_totals[i, 1] = blk["c10_clean"].sum()
            block_totals[i, 2] = blk["v10_clean"].sum()

        rng = np.random.default_rng(seed)
        p10_deltas = np.zeros(replicates, dtype=float)

        for r in range(replicates):
            # Sample block indices with replacement
            sampled_idx = rng.choice(len(blocks), size=len(blocks), replace=True)
            sampled_sums = block_totals[sampled_idx].sum(axis=0)

            k10_tot = sampled_sums[0]
            c_clean = sampled_sums[1]
            v_clean = sampled_sums[2]

            if k10_tot > 0:
                p_c = c_clean / k10_tot
                p_v = v_clean / k10_tot
                p10_deltas[r] = p_c - p_v
            else:
                p10_deltas[r] = 0.0

        p10_q = np.quantile(p10_deltas, [0.025, 0.50, 0.975])

        total_selected = int(df_yr["k10_selected"].sum())
        total_c_clean = int(df_yr["c10_clean"].sum())
        total_v_clean = int(df_yr["v10_clean"].sum())
        cand_p10 = total_c_clean / total_selected
        vam5_p10 = total_v_clean / total_selected
        delta_p10 = cand_p10 - vam5_p10

        annual_results[yr] = {
            "candidate_p10": round(cand_p10, 6),
            "vam5_p10": round(vam5_p10, 6),
            "delta": round(delta_p10, 6),
            "bootstrap_median": round(float(p10_q[1]), 6),
            "ci_2_5": round(float(p10_q[0]), 6),
            "ci_97_5": round(float(p10_q[2]), 6),
            "selected_observations": total_selected,
            "candidate_clean_hits": total_c_clean,
            "vam5_clean_hits": total_v_clean,
            "clean_hit_difference": total_c_clean - total_v_clean,
            "dates_count": n_dates,
            "blocks_count": len(blocks),
        }

    return {
        "block_size_sessions": block_size,
        "replicates_count": replicates,
        "seed": seed,
        "years": annual_results,
    }
