"""CLI entry point for LONG-002D1: Core Technical & Market-Context KPI Census."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from tradex.research.long_002d.artifacts import (
    DEFAULT_EXTERNAL_DIR,
    DEFAULT_SUMMARY_BASE_DIR,
    save_committed_safe_summaries,
    save_external_parquets,
)
from tradex.research.long_002d.baseline import load_frozen_baseline_reference
from tradex.research.long_002d.benchmark import run_pre_launch_benchmark
from tradex.research.long_002d.bootstrap import run_feature_block_bootstrap
from tradex.research.long_002d.census import run_feature_census
from tradex.research.long_002d.features import compute_features_for_security_df
from tradex.research.long_002d.loader import (
    audit_stage_c_cache_provenance,
    create_read_only_alpaca_client,
    load_candidate_bars,
    load_spy_daily_closes,
    load_stage_c_primary_data,
    select_study_candidates,
)
from tradex.research.long_002d.redundancy import compute_pairwise_redundancy
from tradex.research.long_002d.spec import (
    EXPECTED_CLEAN_EVENTS,
    EXPECTED_DENOMINATOR,
    EXPECTED_SPEC_SHA256,
    FEATURE_REGISTRY,
    REPO_ROOT,
    SPEC_PATH,
    load_spec_payload,
)


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def verify_upstream_stage_c(stage_c_dir: Path, spec: dict[str, Any]) -> None:
    """Verify that Stage C external parquet digests match the preregistered spec."""
    print("[PREFLIGHT] Verifying Stage C source Parquet digests against preregistration spec...")
    upstream_ref = spec.get("upstream_stage_c_reference", {})
    expected_digests = upstream_ref.get("external_parquet_digests", {})

    all_matched = True
    for fname, exp_sha in expected_digests.items():
        fpath = stage_c_dir / fname
        if not fpath.exists():
            print(f"  ERROR: Missing Stage C file {fname} at {fpath}")
            all_matched = False
            continue
        act_sha = _compute_sha256(fpath)
        if act_sha != exp_sha:
            print(f"  FAIL: {fname} checksum mismatch! Expected {exp_sha}, got {act_sha}")
            all_matched = False
        else:
            print(f"  OK: {fname}")

    if not all_matched:
        raise ValueError("Stage C Parquet checksum verification failed! Aborting D1 execution.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tradex.research.long_002d.cli",
        description="LONG-002D1: Core Technical & Market-Context KPI Census CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. benchmark
    p_bench = subparsers.add_parser("benchmark", help="Run 25-security pre-launch runtime benchmark")
    p_bench.add_argument("--discovery-manifest", type=Path, default=REPO_ROOT / "data" / "research" / "long_002c" / "discovery_manifest.json")
    p_bench.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "data" / "cache" / "long_002c")
    p_bench.add_argument("--stage-c-dir", type=Path, default=REPO_ROOT / "data" / "research" / "long_002c")
    p_bench.add_argument("--benchmark-size", type=int, default=25)

    # 2. run
    p_run = subparsers.add_parser("run", help="Run official full D1 descriptive census")
    p_run.add_argument("--stage-c-dir", type=Path, default=REPO_ROOT / "data" / "research" / "long_002c")
    p_run.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "data" / "cache" / "long_002c")
    p_run.add_argument("--discovery-manifest", type=Path, default=REPO_ROOT / "data" / "research" / "long_002c" / "discovery_manifest.json")
    p_run.add_argument("--output-dir", type=Path, default=DEFAULT_EXTERNAL_DIR)
    p_run.add_argument("--run-id", type=str, default=None)

    # 3. verify
    p_ver = subparsers.add_parser("verify", help="Verify committed safe summary artifacts checksums")
    p_ver.add_argument("--artifacts-dir", type=Path, default=None)

    # 4. evaluate
    p_eval = subparsers.add_parser("evaluate", help="Offline inspection of generated D1 Parquet files")
    p_eval.add_argument("--data-dir", type=Path, default=DEFAULT_EXTERNAL_DIR)

    args = parser.parse_args(argv)

    if args.command == "benchmark":
        report = run_pre_launch_benchmark(
            discovery_manifest_path=args.discovery_manifest,
            cache_dir=args.cache_dir,
            stage_c_dir=args.stage_c_dir,
            benchmark_size=args.benchmark_size,
        )
        print("\n=== BENCHMARK REPORT ===")
        print(json.dumps(asdict(report), indent=2))
        return 0

    if args.command == "verify":
        target_dir = args.artifacts_dir
        if target_dir is None:
            # Pick latest run in artifacts dir
            runs = sorted(DEFAULT_SUMMARY_BASE_DIR.glob("*"))
            if not runs:
                print(f"No artifact runs found in {DEFAULT_SUMMARY_BASE_DIR}")
                return 1
            target_dir = runs[-1]

        chk_file = target_dir / "checksums.sha256"
        if not chk_file.exists():
            print(f"Checksum file not found: {chk_file}")
            return 1

        print(f"Verifying checksums for {target_dir}...")
        all_ok = True
        for line in chk_file.read_text(encoding="utf-8").strip().splitlines():
            parts = line.strip().split()
            if len(parts) == 2:
                exp_sha, fname = parts
                fpath = target_dir / fname
                if not fpath.exists():
                    print(f"MISSING: {fname}")
                    all_ok = False
                    continue
                act_sha = _compute_sha256(fpath)
                if act_sha == exp_sha:
                    print(f"OK: {fname}")
                else:
                    print(f"FAIL: {fname} expected {exp_sha} got {act_sha}")
                    all_ok = False
        return 0 if all_ok else 1

    if args.command == "evaluate":
        p_table = args.data_dir / "feature_table.parquet"
        if not p_table.exists():
            print(f"Feature table not found: {p_table}")
            return 1
        meta = pq.read_metadata(p_table)
        print(f"Feature table: {meta.num_rows} rows, {meta.num_columns} columns")
        table = pq.read_table(p_table)
        print("Schema columns:", table.schema.names)
        return 0

    if args.command == "run":
        run_id = args.run_id or datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
        print("\n=======================================================")
        print(f"STARTING OFFICIAL LONG-002D1 EXECUTION: RUN {run_id}")
        print("=======================================================")

        # Step 0: Check Preregistration Spec SHA-256
        spec_sha = _compute_sha256(SPEC_PATH)
        print(f"[PREFLIGHT] Preregistration Spec SHA-256: {spec_sha}")
        if spec_sha != EXPECTED_SPEC_SHA256:
            raise ValueError(
                f"Spec SHA-256 mismatch! Expected {EXPECTED_SPEC_SHA256}, got {spec_sha}"
            )
        spec = load_spec_payload(SPEC_PATH)

        # Step 1: Verify Stage C Source Checksums
        verify_upstream_stage_c(args.stage_c_dir, spec)

        # Step 2: Run Mandatory Pre-Launch Benchmark Gate
        bench_report = run_pre_launch_benchmark(
            discovery_manifest_path=args.discovery_manifest,
            cache_dir=args.cache_dir,
            stage_c_dir=args.stage_c_dir,
            benchmark_size=25,
        )
        print(f"[PREFLIGHT] Benchmark passed! Total projected runtime: {bench_report.total_projected_runtime_seconds/60:.2f} minutes.")

        # Step 3: Load Stage C Primary Observations and Outcomes
        print("\n[1/6] Loading Stage C 20:30 primary observations and outcomes...")
        t_load_start = time.perf_counter()
        df_obs, df_out, df_elig = load_stage_c_primary_data(args.stage_c_dir)
        print(f"  Loaded {len(df_obs)} observations and {len(df_out)} outcomes in {time.perf_counter() - t_load_start:.2f}s")

        # Step 4: Derive Study Securities and Load Candidates
        study_security_ids = sorted(df_obs["immutable_security_id"].unique())
        if len(study_security_ids) != 1271:
            raise ValueError(
                f"Expected exactly 1,271 study securities in primary observations, got {len(study_security_ids)}"
            )
        study_cands = select_study_candidates(args.discovery_manifest, study_security_ids)
        print(f"  Validated {len(study_cands)} study candidates against discovery manifest.")

        # Step 5: Initialize Provider Cache Client & Ingest SPY Bars
        print("\n[2/6] Loading SPY daily bars from provider cache (read-only)...")
        alpaca, auditing_cache, tracker = create_read_only_alpaca_client(args.cache_dir)
        spy_closes = load_spy_daily_closes(alpaca)
        print(f"  Loaded {len(spy_closes)} SPY daily closes. Cache hits: {tracker.provider_cache_hits}")

        # Step 6: Feature Construction for Study Candidates Only
        print("\n[3/6] Computing 15 features across 1,271 study candidates from provider cache...")
        t_feat_start = time.perf_counter()

        # Map candidate bars and compute features
        features_by_sec_id: dict[str, pd.DataFrame] = {}
        processed_candidates = 0

        for cand in study_cands:
            sec_id = cand.immutable_security_id
            df_bars, _, _ = load_candidate_bars(cand, alpaca)
            feat_df = compute_features_for_security_df(df_bars, spy_closes)
            features_by_sec_id[sec_id] = feat_df
            processed_candidates += 1

        if processed_candidates != 1271:
            raise RuntimeError(
                f"Expected exactly 1,271 processed study candidates, got {processed_candidates}"
            )

        t_feat_elapsed = time.perf_counter() - t_feat_start
        print(f"  Computed features for {processed_candidates} candidates in {t_feat_elapsed:.2f}s ({t_feat_elapsed/processed_candidates*1000:.1f}ms/sec)")

        # Step 6: Map Features to 758,731 Primary Observations
        print("\n[4/6] Aligning feature values with primary 20:30 observations...")
        t_align_start = time.perf_counter()

        # Build feature columns directly
        obs_sec_ids = df_obs["immutable_security_id"].to_numpy()
        obs_dates = df_obs["as_of_date"].to_numpy()
        n_obs = len(df_obs)

        feature_names = [f.feature_id for f in FEATURE_REGISTRY]
        feature_arrays: dict[str, np.ndarray] = {
            fname: np.full(n_obs, np.nan, dtype=float) for fname in feature_names
        }

        # Group observation indices by security ID
        sec_to_obs_indices: dict[str, list[int]] = {}
        for idx, s_id in enumerate(obs_sec_ids):
            sec_to_obs_indices.setdefault(s_id, []).append(idx)

        for s_id, indices in sec_to_obs_indices.items():
            if s_id not in features_by_sec_id:
                continue
            sec_feat_df = features_by_sec_id[s_id]

            # Reindex to observation dates
            obs_dates_subset = obs_dates[indices]
            sub_feats = sec_feat_df.reindex(obs_dates_subset)

            for fname in feature_names:
                feature_arrays[fname][indices] = sub_feats[fname].to_numpy(dtype=float)

        # Merge observations, outcomes, and features
        df_merged = df_obs[["immutable_security_id", "as_of_date", "cutoff_time", "ticker_at_decision"]].copy()
        df_merged["clean_target_reached"] = df_out["clean_target_reached"].to_numpy()
        df_merged["market_cap"] = df_elig["market_cap"].to_numpy()

        for fname in feature_names:
            df_merged[fname] = feature_arrays[fname]

        print(f"  Aligned {n_obs} observations across {len(feature_names)} features in {time.perf_counter() - t_align_start:.2f}s")

        # Step 7: Redundancy Analysis (Spearman Rank Correlations)
        print("\n[5/6] Running pairwise Spearman redundancy analysis...")
        t_red_start = time.perf_counter()
        corr_matrix, high_red_pairs, high_features = compute_pairwise_redundancy(
            df_merged, feature_names, threshold=0.95
        )
        print(f"  Spearman correlation computed in {time.perf_counter() - t_red_start:.2f}s. High redundancy pairs (|rho|>=0.95): {len(high_red_pairs)}")

        # Step 8: Census Decile Tables, Block Bootstrap, and Annual Stability
        print("\n[6/6] Generating decile census, 21/42-session block bootstraps, and annual stability...")
        t_census_start = time.perf_counter()

        sessions_ordered = sorted(df_merged["as_of_date"].unique())
        dates_arr = df_merged["as_of_date"].to_numpy()
        clean_arr = df_merged["clean_target_reached"].to_numpy(dtype=bool)

        census_summaries: list[dict[str, Any]] = []
        bootstrap_summaries: dict[str, Any] = {}
        detail_dfs: list[pd.DataFrame] = []
        bootstrap_detail_rows: list[dict[str, Any]] = []

        for f_def in FEATURE_REGISTRY:
            fid = f_def.feature_id
            high_flags = ["high_redundancy_candidate"] if fid in high_features else []

            # 1. Decile census & ranks
            c_summary, df_detail = run_feature_census(df_merged, f_def, high_redundancy_flags=high_flags)
            census_summaries.append(asdict(c_summary))
            detail_dfs.append(df_detail)

            # 2. Block bootstrap (21 and 42 sessions)
            valid_m = ~np.isnan(df_merged[fid].to_numpy(dtype=float))
            fav_m = df_detail[f"{fid}_top10"].to_numpy(dtype=bool)

            b_summaries, b_dist = run_feature_block_bootstrap(
                dates=dates_arr,
                valid_mask=valid_m,
                fav_mask=fav_m,
                clean_labels=clean_arr,
                sessions_ordered=sessions_ordered,
                block_sizes=(21, 42),
                num_bootstraps=1000,
                seed=20260927,
            )
            bootstrap_summaries[fid] = {
                "21_session_blocks": asdict(b_summaries[21]),
                "42_session_blocks": asdict(b_summaries[42]),
            }

            for iter_idx in range(1000):
                bootstrap_detail_rows.append({
                    "feature_id": fid,
                    "bootstrap_iteration": iter_idx,
                    "lift_21_sessions": round(float(b_dist[21][iter_idx]), 6),
                    "lift_42_sessions": round(float(b_dist[42][iter_idx]), 6),
                })

            print(
                f"  [{fid:<27}] Cov: {c_summary.coverage_pct:>5.1f}% | "
                f"Base: {c_summary.common_base_rate*100:>5.2f}% | "
                f"Fav Clean: {c_summary.favorable_decile_clean_rate*100:>5.2f}% | "
                f"Lift: {c_summary.favorable_decile_lift:>5.4f}x | "
                f"21d CI: [{b_summaries[21].ci_2_5:.2f}, {b_summaries[21].ci_97_5:.2f}] | "
                f"Stability: {c_summary.annual_stability_years_favorable}/5 yrs"
            )

        print(f"  Census & bootstrap completed in {time.perf_counter() - t_census_start:.2f}s")

        # Step 9: Assemble Full External Datasets & Save
        print("\n[SAVING ARTIFACTS] Assembling external Parquet datasets...")
        df_feature_table = pd.concat([df_merged] + detail_dfs, axis=1)

        # Build decile detail table
        decile_detail_records: list[dict[str, Any]] = []
        for cs in census_summaries:
            fid = cs["feature_id"]
            for drow in cs["decile_table"]:
                r = dict(drow)
                r["feature_id"] = fid
                decile_detail_records.append(r)
        df_decile_detail = pd.DataFrame(decile_detail_records)
        df_bootstrap_detail = pd.DataFrame(bootstrap_detail_rows)

        ext_manifest = save_external_parquets(
            df_feature_table=df_feature_table,
            df_decile_detail=df_decile_detail,
            df_bootstrap_detail=df_bootstrap_detail,
            df_redundancy_matrix=corr_matrix,
            output_dir=args.output_dir,
        )

        # Audit consumed cache payloads against Stage C provenance records
        print("\n[AUDIT] Auditing consumed provider cache payloads against Stage C Alpaca provenance...")
        audit_summary = audit_stage_c_cache_provenance(
            stage_c_dir=args.stage_c_dir,
            auditing_cache=auditing_cache,
            tracker=tracker,
        )

        if audit_summary.outbound_http_requests_executed != 0:
            raise RuntimeError(
                f"FAIL-CLOSED: {audit_summary.outbound_http_requests_executed} outbound HTTP requests were executed!"
            )
        if audit_summary.provider_cache_misses != 0:
            raise RuntimeError(
                f"FAIL-CLOSED: {audit_summary.provider_cache_misses} provider cache misses occurred!"
            )
        if audit_summary.live_request_path_attempts != 0:
            raise RuntimeError(
                f"FAIL-CLOSED: {audit_summary.live_request_path_attempts} live request path attempts occurred!"
            )
        if audit_summary.blocked_live_request_attempts != 0:
            raise RuntimeError(
                f"FAIL-CLOSED: {audit_summary.blocked_live_request_attempts} blocked live request attempts occurred!"
            )
        if audit_summary.unmatched_provenance_count != 0:
            raise RuntimeError(
                f"FAIL-CLOSED: {audit_summary.unmatched_provenance_count} unmatched provenance records!"
            )

        print(
            f"  Audit PASSED: {audit_summary.matched_provenance_count} payloads verified (100.0%). "
            f"Cache hits: {audit_summary.provider_cache_hits}, misses: {audit_summary.provider_cache_misses}, "
            f"live attempts: {audit_summary.live_request_path_attempts}, outbound HTTP: {audit_summary.outbound_http_requests_executed}."
        )

        data_quality_report = {
            "task_id": "LONG-002D1-CORE-KPI-CENSUS",
            "run_id": run_id,
            "created_at_utc": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "total_primary_observations": EXPECTED_DENOMINATOR,
            "total_clean_primary_events": EXPECTED_CLEAN_EVENTS,
            "provider_cache_consumed_payloads": audit_summary.total_payloads_consumed,
            "provider_cache_consumed_bytes": audit_summary.total_payload_bytes,
            "provider_cache_unique_keys": audit_summary.unique_cache_keys,
            "matched_stage_c_provenance_count": audit_summary.matched_provenance_count,
            "unmatched_stage_c_provenance_count": audit_summary.unmatched_provenance_count,
            "provider_cache_hits": audit_summary.provider_cache_hits,
            "provider_cache_misses": audit_summary.provider_cache_misses,
            "live_request_path_attempts": audit_summary.live_request_path_attempts,
            "outbound_http_requests_executed": audit_summary.outbound_http_requests_executed,
            "blocked_live_request_attempts": audit_summary.blocked_live_request_attempts,
            "live_network_requests_attempted": audit_summary.live_request_path_attempts,
            "live_network_requests_blocked": audit_summary.blocked_live_request_attempts,
            "allow_live_enforced": True,
            "feature_coverage_summary": [
                {
                    "feature_id": cs["feature_id"],
                    "usable_observation_count": cs["usable_observation_count"],
                    "coverage_pct": cs["coverage_pct"],
                    "distinct_securities_count": cs["distinct_securities_count"],
                }
                for cs in census_summaries
            ],
        }

        # Step 10: Save Safe Committed Summaries
        print("[SAVING ARTIFACTS] Saving committed safe summary JSONs and checksums...")
        t_total_elapsed = time.perf_counter() - t_load_start
        corr_dict = {col: corr_matrix[col].to_dict() for col in corr_matrix.columns}

        saved_dir = save_committed_safe_summaries(
            run_id=run_id,
            execution_time_seconds=t_total_elapsed,
            benchmark_report=asdict(bench_report),
            external_files_manifest=ext_manifest,
            census_summaries=census_summaries,
            bootstrap_summaries=bootstrap_summaries,
            redundancy_matrix=corr_dict,
            high_redundancy_pairs=high_red_pairs,
            data_quality_report=data_quality_report,
        )

        print("\n=======================================================")
        print(f"OFFICIAL LONG-002D1 EXECUTION COMPLETED IN {t_total_elapsed:.2f}s")
        print(f"External Parquets: {args.output_dir}")
        print(f"Committed Summaries: {saved_dir}")
        print("=======================================================\n")

        # Load frozen baseline for final comparator output
        base_ref = load_frozen_baseline_reference(args.stage_c_dir)
        print("=== FROZEN BASELINE COMPARATOR REFERENCE ===")
        print(f"Comparator: {base_ref.comparator_id}")
        print(f"Base Rate: {base_ref.common_population_base_rate*100:.4f}%")
        print(f"Top-10 Clean Rate: {base_ref.top_10_clean_rate*100:.4f}% (Lift: {base_ref.top_10_lift:.4f}x)")
        print(f"Top-25 Clean Rate: {base_ref.top_25_clean_rate*100:.4f}% (Lift: {base_ref.top_25_lift:.4f}x)\n")

        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
