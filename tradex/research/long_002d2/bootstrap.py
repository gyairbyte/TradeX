"""Paired fixed/non-overlapping calendar-block bootstrap for LONG-002D2."""
from __future__ import annotations

import numpy as np

from tradex.research.long_002d2.models import BootstrapDistributionSummary


def run_paired_calendar_block_bootstrap(
    unique_dates: list[str],
    date_results: dict[str, dict],
    block_sizes: tuple[int, ...] = (21, 42),
    replicates: int = 1000,
    seed: int = 20260928,
) -> tuple[dict[int, BootstrapDistributionSummary], dict[int, np.ndarray]]:
    """Execute paired fixed/non-overlapping calendar-block bootstrap on date cross-sections.

    Parameters:
        unique_dates: chronologically ordered list of evaluation dates.
        date_results: mapping of date -> {"k_date": int, "cand_clean": int, "vam5_clean": int}.
        block_sizes: tuple of block sizes in sessions (default 21, 42).
        replicates: number of bootstrap replicates (default 1000).
        seed: fixed random seed (default 20260928).

    Returns:
        (summaries_by_block_size, deltas_by_block_size)
    """
    summaries: dict[int, BootstrapDistributionSummary] = {}
    distributions: dict[int, np.ndarray] = {}

    for block_size in block_sizes:
        rng = np.random.default_rng(seed)

        # Partition dates into contiguous non-overlapping calendar blocks
        blocks: list[list[str]] = [
            unique_dates[i : i + block_size]
            for i in range(0, len(unique_dates), block_size)
        ]
        num_blocks = len(blocks)
        if num_blocks == 0:
            continue

        # Sufficient statistics per block: [selected_count, cand_clean, vam5_clean]
        block_stats = np.zeros((num_blocks, 3), dtype=np.int64)
        for b_idx, block_dates in enumerate(blocks):
            b_sel = 0
            b_cand_c = 0
            b_vam5_c = 0
            for d in block_dates:
                res = date_results.get(d)
                if res is not None:
                    b_sel += res["k_date"]
                    b_cand_c += res["cand_clean"]
                    b_vam5_c += res["vam5_clean"]
            block_stats[b_idx] = [b_sel, b_cand_c, b_vam5_c]

        # Resample block indices with replacement: shape (replicates, num_blocks)
        sampled_indices = rng.integers(0, num_blocks, size=(replicates, num_blocks))

        # Sum statistics across sampled blocks for each replicate
        # boot_sums shape: (replicates, 3)
        boot_sums = block_stats[sampled_indices].sum(axis=1)

        boot_sel = boot_sums[:, 0]
        boot_cand_c = boot_sums[:, 1]
        boot_vam5_c = boot_sums[:, 2]

        valid_rep = boot_sel > 0
        cand_prec = np.where(valid_rep, boot_cand_c / np.maximum(boot_sel, 1), 0.0)
        vam5_prec = np.where(valid_rep, boot_vam5_c / np.maximum(boot_sel, 1), 0.0)
        deltas = np.where(valid_rep, cand_prec - vam5_prec, 0.0)

        distributions[block_size] = deltas
        summaries[block_size] = BootstrapDistributionSummary(
            block_size_sessions=block_size,
            replicates=replicates,
            seed=seed,
            mean_delta=round(float(np.mean(deltas)), 6),
            median_delta=round(float(np.percentile(deltas, 50.0)), 6),
            std_err=round(float(np.std(deltas)), 6),
            ci_2_5=round(float(np.percentile(deltas, 2.5)), 6),
            ci_97_5=round(float(np.percentile(deltas, 97.5)), 6),
        )

    return summaries, distributions
