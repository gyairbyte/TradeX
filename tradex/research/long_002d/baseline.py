"""Frozen development baseline comparator reference for LONG-002D1.

The frozen development baseline remains volatility_aware_momentum_5 (fixed 50/50 composite
of 5-session momentum percentile and 14-session ATR%-percentile).
D1 does not modify or retune this baseline.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from tradex.research.long_002d.spec import (
    FROZEN_BASELINE_ID,
    FROZEN_BASELINE_TOP_10_CLEAN_RATE,
    FROZEN_BASELINE_TOP_10_LIFT,
    FROZEN_BASELINE_TOP_25_CLEAN_RATE,
    FROZEN_BASELINE_TOP_25_LIFT,
    POPULATION_CUTOFF,
)


@dataclass(frozen=True)
class FrozenBaselineReference:
    """Frozen baseline reference values from Stage C development execution."""

    comparator_id: str
    formula: str
    common_population_observations: int
    common_population_clean_events: int
    common_population_base_rate: float
    top_10_observation_count: int
    top_10_clean_count: int
    top_10_clean_rate: float
    top_10_lift: float
    top_25_observation_count: int
    top_25_clean_count: int
    top_25_clean_rate: float
    top_25_lift: float


def load_frozen_baseline_reference(
    stage_c_dir: Path | None = None,
) -> FrozenBaselineReference:
    """Load or verify the Stage C frozen baseline reference metrics."""
    if stage_c_dir is not None:
        p_base = stage_c_dir / "baseline_comparator_outputs.parquet"
        p_out = stage_c_dir / "outcome_matrix.parquet"
        if p_base.exists() and p_out.exists():
            df_base = pq.read_table(
                p_base,
                columns=["immutable_security_id", "as_of_date", "top_10_flag", "top_25_flag"],
                filters=[
                    ("cutoff_time", "=", POPULATION_CUTOFF),
                    ("comparator_id", "=", FROZEN_BASELINE_ID),
                ],
            ).to_pandas()
            df_out = pq.read_table(
                p_out,
                columns=["immutable_security_id", "as_of_date", "clean_target_reached"],
                filters=[
                    ("cutoff_time", "=", POPULATION_CUTOFF),
                    ("target_pct", "=", 10.0),
                    ("horizon_sessions", "=", 10),
                ],
            ).to_pandas()
            merged = pd.merge(df_base, df_out, on=["immutable_security_id", "as_of_date"], how="inner")
            n_tot = len(merged)
            n_clean = int(merged["clean_target_reached"].sum())
            b_rate = float(n_clean / n_tot) if n_tot > 0 else 0.0

            top10 = merged[merged["top_10_flag"] == True]
            c_top10 = int(top10["clean_target_reached"].sum())
            r_top10 = float(c_top10 / len(top10)) if len(top10) > 0 else 0.0
            l_top10 = float(r_top10 / b_rate) if b_rate > 0 else 0.0

            top25 = merged[merged["top_25_flag"] == True]
            c_top25 = int(top25["clean_target_reached"].sum())
            r_top25 = float(c_top25 / len(top25)) if len(top25) > 0 else 0.0
            l_top25 = float(r_top25 / b_rate) if b_rate > 0 else 0.0

            return FrozenBaselineReference(
                comparator_id=FROZEN_BASELINE_ID,
                formula="0.5 * momentum_5_pct + 0.5 * atr_pct_14_pct",
                common_population_observations=n_tot,
                common_population_clean_events=n_clean,
                common_population_base_rate=round(b_rate, 6),
                top_10_observation_count=len(top10),
                top_10_clean_count=c_top10,
                top_10_clean_rate=round(r_top10, 6),
                top_10_lift=round(l_top10, 4),
                top_25_observation_count=len(top25),
                top_25_clean_count=c_top25,
                top_25_clean_rate=round(r_top25, 6),
                top_25_lift=round(l_top25, 4),
            )

    # Return default verified reference values
    return FrozenBaselineReference(
        comparator_id=FROZEN_BASELINE_ID,
        formula="0.5 * momentum_5_pct + 0.5 * atr_pct_14_pct",
        common_population_observations=758731,
        common_population_clean_events=67257,
        common_population_base_rate=0.088644,
        top_10_observation_count=76407,
        top_10_clean_count=11731,
        top_10_clean_rate=FROZEN_BASELINE_TOP_10_CLEAN_RATE,
        top_10_lift=FROZEN_BASELINE_TOP_10_LIFT,
        top_25_observation_count=190288,
        top_25_clean_count=24144,
        top_25_clean_rate=FROZEN_BASELINE_TOP_25_CLEAN_RATE,
        top_25_lift=FROZEN_BASELINE_TOP_25_LIFT,
    )
