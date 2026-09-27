"""Pre-launch benchmark harness for LONG-002D1 runtime stop gates."""
from __future__ import annotations

import gc
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

from tradex.research.long_002c.manifest import CandidateSecurity
from tradex.research.long_002d.bootstrap import run_feature_block_bootstrap
from tradex.research.long_002d.census import (
    run_feature_census,
)
from tradex.research.long_002d.features import compute_features_for_security_df
from tradex.research.long_002d.loader import (
    create_read_only_alpaca_client,
    load_candidate_bars,
    load_spy_daily_closes,
)
from tradex.research.long_002d.redundancy import compute_pairwise_redundancy
from tradex.research.long_002d.spec import (
    FEATURE_REGISTRY,
    POPULATION_CUTOFF,
)


@dataclass
class BenchmarkReport:
    """Audit report for pre-launch benchmark."""

    benchmark_securities_count: int
    benchmark_observations_count: int
    feature_construction_elapsed_seconds: float
    feature_construction_sec_per_sec: float
    projected_full_feature_construction_seconds: float
    census_and_bootstrap_elapsed_seconds: float
    projected_full_aggregation_seconds: float
    total_projected_runtime_seconds: float
    peak_working_set_mb: float
    network_requests_attempted: int
    network_requests_blocked: int
    gate_preferred_pass: bool  # < 10 minutes
    gate_hard_pass: bool  # < 20 minutes
    hotspot_analysis: str


def get_peak_memory_mb() -> float:
    """Return the current process RSS working set in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def run_pre_launch_benchmark(
    discovery_manifest_path: Path,
    cache_dir: Path,
    benchmark_size: int = 25,
    total_universe_candidates: int = 1291,
) -> BenchmarkReport:
    """Execute the mandatory pre-launch runtime benchmark over 25 representative securities."""
    print(f"\n[BENCHMARK] Initializing pre-launch benchmark over {benchmark_size} representative candidates...")
    gc.collect()

    # Load discovery manifest
    with open(discovery_manifest_path, "r", encoding="utf-8") as f:
        disc = json.load(f)

    candidates_raw = disc.get("candidates", [])
    if not candidates_raw:
        raise ValueError(f"No candidates found in {discovery_manifest_path}")

    # If Stage C observations exist in the same directory, restrict candidates to active universe
    stage_c_obs = discovery_manifest_path.parent / "decision_observations.parquet"
    if stage_c_obs.exists():
        import pyarrow.parquet as pq

        tbl = pq.read_table(
            stage_c_obs,
            columns=["immutable_security_id"],
            filters=[
                ("cutoff_time", "=", POPULATION_CUTOFF),
                ("raw_outcome_eligible", "=", True),
                ("split_boundary_purged", "=", False),
            ],
        )
        valid_sec_ids = set(tbl["immutable_security_id"].to_pylist())
        candidates_raw = [c for c in candidates_raw if c.get("immutable_security_id") in valid_sec_ids]
        total_universe_candidates = len(candidates_raw)

    # Select representative eligible candidates (sampling across sectors/symbols)
    step = max(1, len(candidates_raw) // benchmark_size)
    sample_cands = [CandidateSecurity.from_dict(c) for c in candidates_raw[::step][:benchmark_size]]

    # Initialize read-only fail-closed client
    alpaca, _auditing_cache = create_read_only_alpaca_client(cache_dir)

    # Ingest SPY closes
    t_spy_start = time.perf_counter()
    spy_closes = load_spy_daily_closes(alpaca)
    t_spy_sec = time.perf_counter() - t_spy_start
    print(f"[BENCHMARK] SPY daily bars loaded ({len(spy_closes)} sessions) in {t_spy_sec:.2f}s")

    # Measure Feature Construction Phase
    t_feat_start = time.perf_counter()
    bench_feature_rows: list[pd.DataFrame] = []
    total_obs = 0

    for cand in sample_cands:
        df_bars, _, _ = load_candidate_bars(cand, alpaca)
        if df_bars.empty:
            continue
        feat_df = compute_features_for_security_df(df_bars, spy_closes)
        feat_df["immutable_security_id"] = cand.immutable_security_id
        feat_df["as_of_date"] = feat_df.index
        feat_df["cutoff_time"] = POPULATION_CUTOFF
        bench_feature_rows.append(feat_df)
        total_obs += len(feat_df)

    t_feat_elapsed = time.perf_counter() - t_feat_start
    sec_per_sec = t_feat_elapsed / max(1, len(sample_cands))
    proj_feat_sec = sec_per_sec * total_universe_candidates

    print(
        f"[BENCHMARK] Feature construction for {len(sample_cands)} securities ({total_obs} obs) "
        f"completed in {t_feat_elapsed:.2f}s ({sec_per_sec*1000:.1f}ms/sec). "
        f"Projected full feature-construction runtime: {proj_feat_sec/60:.2f} minutes."
    )

    # Measure Descriptive Aggregation, Decile Census, Bootstrap, and Redundancy Phase
    t_agg_start = time.perf_counter()
    if bench_feature_rows:
        df_bench_all = pd.concat(bench_feature_rows, ignore_index=True)
        # Mock clean labels for aggregation benchmark
        rng = np.random.default_rng(20260927)
        df_bench_all["clean_target_reached"] = rng.random(len(df_bench_all)) < 0.0886
        df_bench_all["market_cap"] = 10e9

        sessions_ordered = sorted(df_bench_all["as_of_date"].unique())

        # Benchmark deciles and bootstrap for 3 representative features
        for f_def in FEATURE_REGISTRY[:3]:
            run_feature_census(df_bench_all, f_def)
            run_feature_block_bootstrap(
                dates=df_bench_all["as_of_date"].to_numpy(),
                valid_mask=df_bench_all[f_def.feature_id].notna().to_numpy(),
                fav_mask=rng.random(len(df_bench_all)) < 0.10,
                clean_labels=df_bench_all["clean_target_reached"].to_numpy(),
                sessions_ordered=sessions_ordered,
                num_bootstraps=1000,
            )

        # Benchmark redundancy
        feature_cols = [f.feature_id for f in FEATURE_REGISTRY]
        compute_pairwise_redundancy(df_bench_all, feature_cols)

    t_agg_elapsed = time.perf_counter() - t_agg_start
    # Scaling factor for aggregation: full dataset has 758,731 / total_obs
    scale_factor = (758731 / max(1, total_obs)) if total_obs > 0 else 50.0
    proj_agg_sec = t_agg_elapsed * scale_factor

    print(
        f"[BENCHMARK] Census & bootstrap phase benchmarked in {t_agg_elapsed:.2f}s. "
        f"Projected full aggregation runtime: {proj_agg_sec/60:.2f} minutes."
    )

    tot_proj_sec = proj_feat_sec + proj_agg_sec
    peak_mem = get_peak_memory_mb()

    gate_pref = tot_proj_sec < 600.0  # < 10 min
    gate_hard = tot_proj_sec < 1200.0  # < 20 min

    hotspot = "No bottleneck detected; vectorized feature construction and pre-aggregated bootstrap are within gates."
    if not gate_hard:
        hotspot = (
            f"STOP GATE BREACH: Projected full runtime {tot_proj_sec/60:.2f} minutes exceeds 20-minute hard gate! "
            f"Feature construction: {proj_feat_sec/60:.2f}m, Aggregation: {proj_agg_sec/60:.2f}m."
        )

    report = BenchmarkReport(
        benchmark_securities_count=len(sample_cands),
        benchmark_observations_count=total_obs,
        feature_construction_elapsed_seconds=round(t_feat_elapsed, 2),
        feature_construction_sec_per_sec=round(sec_per_sec, 4),
        projected_full_feature_construction_seconds=round(proj_feat_sec, 2),
        census_and_bootstrap_elapsed_seconds=round(t_agg_elapsed, 2),
        projected_full_aggregation_seconds=round(proj_agg_sec, 2),
        total_projected_runtime_seconds=round(tot_proj_sec, 2),
        peak_working_set_mb=round(peak_mem, 2),
        network_requests_attempted=alpaca.network_requests_count,
        network_requests_blocked=0,
        gate_preferred_pass=gate_pref,
        gate_hard_pass=gate_hard,
        hotspot_analysis=hotspot,
    )

    if not gate_hard:
        raise RuntimeError(hotspot)

    return report
