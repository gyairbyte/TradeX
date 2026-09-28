"""Descriptive census and cross-sectional decile analysis for LONG-002D1."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from tradex.research.long_002d.spec import (
    FeatureDefinition,
)


@dataclass
class DecileRow:
    """Statistics for a single decile bin of a feature."""

    decile: int  # 1 (least favorable) to 10 (most favorable)
    observation_count: int
    clean_event_count: int
    clean_rate: float
    lift_vs_base_rate: float
    raw_min: float | None
    raw_max: float | None
    raw_mean: float | None
    raw_median: float | None
    date_count: int | None = None  # populated for date-level features like spy_return_20


@dataclass
class AnnualStabilityRow:
    """Annual breakdown for a feature."""

    year: int
    usable_observations: int
    common_base_rate: float
    favorable_decile_observations: int
    favorable_decile_clean_events: int
    favorable_decile_clean_rate: float
    favorable_decile_lift: float
    top_quartile_clean_rate: float
    top_quartile_lift: float


@dataclass
class CohortBreakdownRow:
    """Cohort breakdown for a feature."""

    cohort_name: str
    usable_observations: int
    clean_event_count: int
    base_rate: float
    favorable_decile_clean_rate: float
    favorable_decile_lift: float


@dataclass
class FeatureCensusSummary:
    """Complete descriptive census summary for a single feature."""

    feature_id: str
    role: str
    hypothesized_direction: str
    status: str
    mechanical_flags: list[str]
    usable_observation_count: int
    coverage_pct: float
    distinct_securities_count: int
    common_base_rate: float
    favorable_decile_clean_count: int
    favorable_decile_observation_count: int
    favorable_decile_clean_rate: float
    favorable_decile_lift: float
    top_quartile_clean_count: int
    top_quartile_observation_count: int
    top_quartile_clean_rate: float
    top_quartile_lift: float
    annual_stability_years_favorable: int  # e.g. 5 out of 5
    annual_breakdowns: list[dict[str, Any]]
    decile_table: list[dict[str, Any]]
    cohort_breakdowns: list[dict[str, Any]]
    diagnostic_notes: list[str]


def compute_cross_sectional_ranks_for_feature(
    df_merged: pd.DataFrame,
    feature_def: FeatureDefinition,
    spy_unique_dates: list[str] | None = None,
    spy_date_values: dict[str, float] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute cross-sectional ranks, percentiles, deciles, and favorable flags.

    Returns:
        (percentiles, deciles, top_10_flags, top_25_flags) as NumPy arrays of length len(df_merged).
        Entries for NaN feature values will be NaN / False.
    """
    n = len(df_merged)
    percentiles = np.full(n, np.nan, dtype=float)
    deciles = np.full(n, np.nan, dtype=float)
    top_10_flags = np.zeros(n, dtype=bool)
    top_25_flags = np.zeros(n, dtype=bool)

    feat_vals = df_merged[feature_def.feature_id].to_numpy(dtype=float)
    sec_ids = df_merged["immutable_security_id"].to_numpy()
    dates = df_merged["as_of_date"].to_numpy()

    if feature_def.diagnostic_type == "market_regime_date_level":
        # spy_return_20: date-level ranking over unique development dates
        if spy_date_values is None:
            # Derive unique dates and values from data
            valid_date_vals: dict[str, float] = {}
            for d, val in zip(dates, feat_vals):
                if not np.isnan(val) and d not in valid_date_vals:
                    valid_date_vals[d] = float(val)
        else:
            valid_date_vals = {d: v for d, v in spy_date_values.items() if not np.isnan(v)}

        sorted_dates = sorted(
            valid_date_vals.items(),
            key=lambda item: (-item[1], item[0]),  # descending by SPY return, date ASC
        )
        n_dates = len(sorted_dates)
        if n_dates == 0:
            return percentiles, deciles, top_10_flags, top_25_flags

        date_pct_map: dict[str, float] = {}
        date_dec_map: dict[str, int] = {}
        for rank_idx, (d, _) in enumerate(sorted_dates):
            pct = 100.0 * (n_dates - rank_idx) / n_dates
            # Decile: 10 for top 10% (rank_idx < 0.1 * n_dates), down to 1
            dec = min(10, max(1, 10 - int(np.floor(rank_idx * 10.0 / n_dates))))
            date_pct_map[d] = pct
            date_dec_map[d] = dec

        for i in range(n):
            d = dates[i]
            if d in date_pct_map:
                pct = date_pct_map[d]
                dec = date_dec_map[d]
                percentiles[i] = pct
                deciles[i] = dec
                top_10_flags[i] = pct >= 90.0
                top_25_flags[i] = pct >= 75.0

        return percentiles, deciles, top_10_flags, top_25_flags

    # Stock-level cross-sectional ranking per as_of_date
    is_higher = feature_def.hypothesized_direction != "LOWER"

    # Group row indices by date
    date_to_indices: dict[str, list[int]] = {}
    for idx, d in enumerate(dates):
        if not np.isnan(feat_vals[idx]):
            date_to_indices.setdefault(d, []).append(idx)

    for d, row_indices in date_to_indices.items():
        n_valid = len(row_indices)
        if n_valid == 0:
            continue

        # Sort indices:
        # For HIGHER: descending by value, sec_id ASC tie-break
        # For LOWER: ascending by value, sec_id ASC tie-break
        if is_higher:
            row_indices.sort(key=lambda idx: (-feat_vals[idx], sec_ids[idx]))
        else:
            row_indices.sort(key=lambda idx: (feat_vals[idx], sec_ids[idx]))

        for rank_idx, idx in enumerate(row_indices):
            pct = 100.0 * (n_valid - rank_idx) / n_valid
            # Decile: 10 for favorable (rank_idx < 0.1 * n_valid), down to 1
            dec = min(10, max(1, 10 - int(np.floor(rank_idx * 10.0 / n_valid))))
            percentiles[idx] = pct
            deciles[idx] = dec
            top_10_flags[idx] = pct >= 90.0
            top_25_flags[idx] = pct >= 75.0

    return percentiles, deciles, top_10_flags, top_25_flags


def run_feature_census(
    df_merged: pd.DataFrame,
    feature_def: FeatureDefinition,
    high_redundancy_flags: list[str] | None = None,
) -> tuple[FeatureCensusSummary, pd.DataFrame]:
    """Execute the full descriptive census for a single feature.

    Returns:
        (FeatureCensusSummary, df_feature_detail)
    """
    fid = feature_def.feature_id
    vals = df_merged[fid].to_numpy(dtype=float)
    clean_labels = df_merged["clean_target_reached"].to_numpy(dtype=bool)
    dates = df_merged["as_of_date"].to_numpy()
    sec_ids = df_merged["immutable_security_id"].to_numpy()
    mcap = df_merged["market_cap"].to_numpy(dtype=float) if "market_cap" in df_merged.columns else None

    # Cross-sectional ranks
    percentiles, deciles, top10_flags, top25_flags = compute_cross_sectional_ranks_for_feature(
        df_merged, feature_def
    )

    valid_mask = ~np.isnan(vals)
    usable_count = int(np.sum(valid_mask))
    coverage_pct = round(100.0 * usable_count / len(df_merged), 2)
    distinct_sec_count = len(np.unique(sec_ids[valid_mask]))

    common_clean_count = int(np.sum(clean_labels[valid_mask]))
    common_base_rate = float(common_clean_count / usable_count) if usable_count > 0 else 0.0

    # Favorable decile metrics (Decile 10)
    fav_mask = valid_mask & top10_flags
    fav_obs_count = int(np.sum(fav_mask))
    fav_clean_count = int(np.sum(clean_labels[fav_mask]))
    fav_clean_rate = float(fav_clean_count / fav_obs_count) if fav_obs_count > 0 else 0.0
    fav_lift = float(fav_clean_rate / common_base_rate) if common_base_rate > 0 else 0.0

    # Top quartile metrics (Top 25%)
    q_mask = valid_mask & top25_flags
    q_obs_count = int(np.sum(q_mask))
    q_clean_count = int(np.sum(clean_labels[q_mask]))
    q_clean_rate = float(q_clean_count / q_obs_count) if q_obs_count > 0 else 0.0
    q_lift = float(q_clean_rate / common_base_rate) if common_base_rate > 0 else 0.0

    # Full decile table (Deciles 1 to 10)
    decile_rows: list[dict[str, Any]] = []
    for d_num in range(1, 11):
        d_mask = valid_mask & (deciles == d_num)
        d_obs = int(np.sum(d_mask))
        d_clean = int(np.sum(clean_labels[d_mask]))
        d_rate = float(d_clean / d_obs) if d_obs > 0 else 0.0
        d_lift = float(d_rate / common_base_rate) if common_base_rate > 0 else 0.0

        if d_obs > 0:
            d_raws = vals[d_mask]
            d_min = float(np.min(d_raws))
            d_max = float(np.max(d_raws))
            d_mean = float(np.mean(d_raws))
            d_median = float(np.median(d_raws))
            d_dates = len(np.unique(dates[d_mask]))
        else:
            d_min = d_max = d_mean = d_median = d_dates = None

        row = DecileRow(
            decile=d_num,
            observation_count=d_obs,
            clean_event_count=d_clean,
            clean_rate=round(d_rate, 6),
            lift_vs_base_rate=round(d_lift, 4),
            raw_min=round(d_min, 6) if d_min is not None else None,
            raw_max=round(d_max, 6) if d_max is not None else None,
            raw_mean=round(d_mean, 6) if d_mean is not None else None,
            raw_median=round(d_median, 6) if d_median is not None else None,
            date_count=d_dates,
        )
        decile_rows.append(asdict(row))

    # Annual breakdowns (2016-2020)
    years = [2016, 2017, 2018, 2019, 2020]
    annual_rows: list[dict[str, Any]] = []
    years_favorable_count = 0

    for yr in years:
        yr_prefix = str(yr)
        yr_mask = valid_mask & np.char.startswith(dates.astype(str), yr_prefix)
        yr_obs = int(np.sum(yr_mask))
        yr_clean = int(np.sum(clean_labels[yr_mask]))
        yr_base = float(yr_clean / yr_obs) if yr_obs > 0 else 0.0

        yr_fav_mask = yr_mask & top10_flags
        yr_fav_obs = int(np.sum(yr_fav_mask))
        yr_fav_clean = int(np.sum(clean_labels[yr_fav_mask]))
        yr_fav_rate = float(yr_fav_clean / yr_fav_obs) if yr_fav_obs > 0 else 0.0
        yr_fav_lift = float(yr_fav_rate / yr_base) if yr_base > 0 else 0.0

        yr_q_mask = yr_mask & top25_flags
        yr_q_obs = int(np.sum(yr_q_mask))
        yr_q_clean = int(np.sum(clean_labels[yr_q_mask]))
        yr_q_rate = float(yr_q_clean / yr_q_obs) if yr_q_obs > 0 else 0.0
        yr_q_lift = float(yr_q_rate / yr_base) if yr_base > 0 else 0.0

        if yr_fav_lift > 1.0:
            years_favorable_count += 1

        arow = AnnualStabilityRow(
            year=yr,
            usable_observations=yr_obs,
            common_base_rate=round(yr_base, 6),
            favorable_decile_observations=yr_fav_obs,
            favorable_decile_clean_events=yr_fav_clean,
            favorable_decile_clean_rate=round(yr_fav_rate, 6),
            favorable_decile_lift=round(yr_fav_lift, 4),
            top_quartile_clean_rate=round(yr_q_rate, 6),
            top_quartile_lift=round(yr_q_lift, 4),
        )
        annual_rows.append(asdict(arow))

    # Market Cap Cohorts ($3B-<5B, $5B-<20B, $20B-<200B, $200B+)
    cohort_rows: list[dict[str, Any]] = []
    if mcap is not None:
        cohort_definitions = [
            ("3B-<5B", 3e9, 5e9),
            ("5B-<20B", 5e9, 20e9),
            ("20B-<200B", 20e9, 200e9),
            ("200B+", 200e9, np.inf),
        ]
        for c_name, c_low, c_high in cohort_definitions:
            c_mask = valid_mask & (mcap >= c_low) & (mcap < c_high)
            c_obs = int(np.sum(c_mask))
            c_clean = int(np.sum(clean_labels[c_mask]))
            c_base = float(c_clean / c_obs) if c_obs > 0 else 0.0

            c_fav_mask = c_mask & top10_flags
            c_fav_obs = int(np.sum(c_fav_mask))
            c_fav_clean = int(np.sum(clean_labels[c_fav_mask]))
            c_fav_rate = float(c_fav_clean / c_fav_obs) if c_fav_obs > 0 else 0.0
            c_fav_lift = float(c_fav_rate / c_base) if c_base > 0 else 0.0

            crow = CohortBreakdownRow(
                cohort_name=c_name,
                usable_observations=c_obs,
                clean_event_count=c_clean,
                base_rate=round(c_base, 6),
                favorable_decile_clean_rate=round(c_fav_rate, 6),
                favorable_decile_lift=round(c_fav_lift, 4),
            )
            cohort_rows.append(asdict(crow))

    # Status and Mechanical Flags
    mech_flags = list(high_redundancy_flags or [])
    if coverage_pct < 95.0:
        mech_flags.append("coverage_limited")

    status = feature_def.status
    diagnostic_notes: list[str] = []
    if feature_def.feature_id == "stock_minus_spy_20":
        diagnostic_notes.append(
            "Reference diagnostic: within same-date cross-sections, order is strictly identical to return_20."
        )
    if feature_def.feature_id == "spy_return_20":
        diagnostic_notes.append(
            "Market-regime date diagnostic: deciles reflect unique market dates, not cross-sectional stock ranking."
        )

    summary = FeatureCensusSummary(
        feature_id=fid,
        role=feature_def.role,
        hypothesized_direction=feature_def.hypothesized_direction,
        status=status,
        mechanical_flags=mech_flags,
        usable_observation_count=usable_count,
        coverage_pct=coverage_pct,
        distinct_securities_count=distinct_sec_count,
        common_base_rate=round(common_base_rate, 6),
        favorable_decile_clean_count=fav_clean_count,
        favorable_decile_observation_count=fav_obs_count,
        favorable_decile_clean_rate=round(fav_clean_rate, 6),
        favorable_decile_lift=round(fav_lift, 4),
        top_quartile_clean_count=q_clean_count,
        top_quartile_observation_count=q_obs_count,
        top_quartile_clean_rate=round(q_clean_rate, 6),
        top_quartile_lift=round(q_lift, 4),
        annual_stability_years_favorable=years_favorable_count,
        annual_breakdowns=annual_rows,
        decile_table=decile_rows,
        cohort_breakdowns=cohort_rows,
        diagnostic_notes=diagnostic_notes,
    )

    df_detail = pd.DataFrame(
        {
            f"{fid}_percentile": percentiles,
            f"{fid}_decile": deciles,
            f"{fid}_top10": top10_flags,
            f"{fid}_top25": top25_flags,
        }
    )

    return summary, df_detail
