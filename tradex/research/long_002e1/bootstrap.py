"""Paired calendar-block bootstrap uncertainty estimation for LONG-002E1."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradex.research.long_002e1.spec import (
    BOOTSTRAP_PRIMARY_BLOCK,
    BOOTSTRAP_REPLICATES,
    DETERMINISTIC_SEED,
)


@dataclass
class BootstrapResult:
    """Bootstrap confidence intervals for a specific block size."""

    block_size_sessions: int
    replicates_count: int
    seed: int
    p10_delta_lower: float  # 2.5%
    p10_delta_median: float  # 50.0%
    p10_delta_upper: float  # 97.5%
    p25_delta_lower: float
    p25_delta_median: float
    p25_delta_upper: float


def run_paired_calendar_bootstrap(
    df_date_level: pd.DataFrame,
    block_size: int = BOOTSTRAP_PRIMARY_BLOCK,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = DETERMINISTIC_SEED,
) -> BootstrapResult:
    """Execute paired calendar-block bootstrap on date-level clean counts.

    Preserves full cross-section across dates within sampled blocks.
    Evaluates candidate and matched baseline on identical sampled blocks.
    """
    df_sorted = df_date_level.sort_values("as_of_date").reset_index(drop=True)
    n_dates = len(df_sorted)

    if n_dates == 0:
        return BootstrapResult(
            block_size_sessions=block_size,
            replicates_count=replicates,
            seed=seed,
            p10_delta_lower=0.0,
            p10_delta_median=0.0,
            p10_delta_upper=0.0,
            p25_delta_lower=0.0,
            p25_delta_median=0.0,
            p25_delta_upper=0.0,
        )

    # Form contiguous calendar blocks
    n_blocks = int(np.ceil(n_dates / block_size))
    blocks: list[pd.DataFrame] = []
    for b in range(n_blocks):
        start_idx = b * block_size
        end_idx = min(start_idx + block_size, n_dates)
        blocks.append(df_sorted.iloc[start_idx:end_idx])

    # Pre-extract totals per block
    # (k10_sel, c10_clean, v10_clean, k25_sel, c25_clean, v25_clean)
    block_totals = np.zeros((len(blocks), 6), dtype=float)
    for i, blk in enumerate(blocks):
        block_totals[i, 0] = blk["k10_selected"].sum()
        block_totals[i, 1] = blk["c10_clean"].sum()
        block_totals[i, 2] = blk["v10_clean"].sum()
        block_totals[i, 3] = blk["k25_selected"].sum()
        block_totals[i, 4] = blk["c25_clean"].sum()
        block_totals[i, 5] = blk["v25_clean"].sum()

    rng = np.random.default_rng(seed)

    p10_deltas = np.zeros(replicates, dtype=float)
    p25_deltas = np.zeros(replicates, dtype=float)

    for r in range(replicates):
        # Sample block indices with replacement
        sample_indices = rng.choice(len(blocks), size=len(blocks), replace=True)
        sample_sum = block_totals[sample_indices].sum(axis=0)

        k10_tot = sample_sum[0]
        c10_clean = sample_sum[1]
        v10_clean = sample_sum[2]

        k25_tot = sample_sum[3]
        c25_clean = sample_sum[4]
        v25_clean = sample_sum[5]

        # P@10 delta
        if k10_tot > 0:
            p10_cand = c10_clean / k10_tot
            p10_vam5 = v10_clean / k10_tot
            p10_deltas[r] = p10_cand - p10_vam5
        else:
            p10_deltas[r] = 0.0

        # P@25 delta
        if k25_tot > 0:
            p25_cand = c25_clean / k25_tot
            p25_vam5 = v25_clean / k25_tot
            p25_deltas[r] = p25_cand - p25_vam5
        else:
            p25_deltas[r] = 0.0

    p10_q = np.quantile(p10_deltas, [0.025, 0.50, 0.975])
    p25_q = np.quantile(p25_deltas, [0.025, 0.50, 0.975])

    return BootstrapResult(
        block_size_sessions=block_size,
        replicates_count=replicates,
        seed=seed,
        p10_delta_lower=float(p10_q[0]),
        p10_delta_median=float(p10_q[1]),
        p10_delta_upper=float(p10_q[2]),
        p25_delta_lower=float(p25_q[0]),
        p25_delta_median=float(p25_q[1]),
        p25_delta_upper=float(p25_q[2]),
    )
