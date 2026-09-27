"""Dependence-aware stationary calendar block bootstrap for LONG-002D1."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BootstrapMetricSummary:
    """Summary statistics for a bootstrap distribution."""

    mean: float
    std_err: float
    ci_2_5: float
    median: float
    ci_97_5: float


@dataclass
class FeatureBootstrapResult:
    """Complete bootstrap results for a single feature under primary and robustness block sizes."""

    feature_id: str
    favorable_decile_lift_21: dict[str, float]
    favorable_decile_lift_42: dict[str, float]
    num_bootstraps: int
    seed: int


def run_feature_block_bootstrap(
    dates: np.ndarray,
    valid_mask: np.ndarray,
    fav_mask: np.ndarray,
    clean_labels: np.ndarray,
    sessions_ordered: list[str],
    block_sizes: tuple[int, ...] = (21, 42),
    num_bootstraps: int = 1000,
    seed: int = 20260927,
) -> tuple[dict[int, BootstrapMetricSummary], dict[int, np.ndarray]]:
    """Run dependence-aware time-block bootstrap for a feature's favorable decile lift.

    Parameters:
        dates: array of as_of_date strings for all observations.
        valid_mask: boolean array indicating usable observations for the feature.
        fav_mask: boolean array indicating observations in the favorable top decile.
        clean_labels: boolean array indicating clean target reached.
        sessions_ordered: chronologically ordered list of unique trading sessions in development window.
        block_sizes: tuple of block lengths in trading sessions (e.g. 21, 42).
        num_bootstraps: number of bootstrap resamples (default 1000).
        seed: fixed random seed.

    Returns:
        (summaries_by_block_size, distributions_by_block_size)
    """
    rng = np.random.default_rng(seed)

    # Pre-map date to row indices
    date_to_indices: dict[str, list[int]] = {}
    for idx, d in enumerate(dates):
        if valid_mask[idx]:
            date_to_indices.setdefault(str(d), []).append(idx)

    summaries: dict[int, BootstrapMetricSummary] = {}
    distributions: dict[int, np.ndarray] = {}

    for block_size in block_sizes:
        # Group sessions into non-overlapping sequential blocks
        blocks: list[list[str]] = [
            sessions_ordered[i : i + block_size]
            for i in range(0, len(sessions_ordered), block_size)
        ]
        num_blocks = len(blocks)
        if num_blocks == 0:
            continue

        # Sufficient statistics per block:
        # [fav_obs, fav_clean, base_obs, base_clean]
        block_stats = np.zeros((num_blocks, 4), dtype=np.int64)
        for b_idx, block_sessions in enumerate(blocks):
            b_fav_obs = 0
            b_fav_clean = 0
            b_base_obs = 0
            b_base_clean = 0
            for s in block_sessions:
                for idx in date_to_indices.get(s, []):
                    b_base_obs += 1
                    if clean_labels[idx]:
                        b_base_clean += 1
                    if fav_mask[idx]:
                        b_fav_obs += 1
                        if clean_labels[idx]:
                            b_fav_clean += 1
            block_stats[b_idx] = [b_fav_obs, b_fav_clean, b_base_obs, b_base_clean]

        # Resample block indices with replacement
        sampled_indices = rng.integers(0, num_blocks, size=(num_bootstraps, num_blocks))
        boot_sums = block_stats[sampled_indices].sum(axis=1)

        boot_fav_obs = boot_sums[:, 0]
        boot_fav_clean = boot_sums[:, 1]
        boot_base_obs = boot_sums[:, 2]
        boot_base_clean = boot_sums[:, 3]

        # Compute lift: (fav_clean / fav_obs) / (base_clean / base_obs)
        valid_b = (boot_fav_obs > 0) & (boot_base_obs > 0) & (boot_base_clean > 0)
        fav_rates = np.where(valid_b, boot_fav_clean / np.maximum(boot_fav_obs, 1), 0.0)
        base_rates = np.where(valid_b, boot_base_clean / np.maximum(boot_base_obs, 1), 1.0)
        lifts = np.where(valid_b, fav_rates / base_rates, 0.0)

        distributions[block_size] = lifts
        summaries[block_size] = BootstrapMetricSummary(
            mean=round(float(np.mean(lifts)), 4),
            std_err=round(float(np.std(lifts)), 4),
            ci_2_5=round(float(np.percentile(lifts, 2.5)), 4),
            median=round(float(np.percentile(lifts, 50.0)), 4),
            ci_97_5=round(float(np.percentile(lifts, 97.5)), 4),
        )

    return summaries, distributions
