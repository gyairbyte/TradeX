"""Command-line execution runner for LONG-002D2."""
from __future__ import annotations

import argparse
import datetime
import subprocess
import time
from pathlib import Path

from tradex.research.long_002d2.artifacts import write_d2_artifacts
from tradex.research.long_002d2.bootstrap import run_paired_calendar_block_bootstrap
from tradex.research.long_002d2.diagnostics import (
    compute_spy_date_regimes,
    evaluate_regime_diagnostics,
)
from tradex.research.long_002d2.loader import load_and_verify_datasets
from tradex.research.long_002d2.models import CandidateEvaluationResult
from tradex.research.long_002d2.rerank import run_coverage_matched_reranking
from tradex.research.long_002d2.spec import (
    BOOTSTRAP_PRIMARY_BLOCK_SIZE,
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_ROBUSTNESS_BLOCK_SIZE,
    BOOTSTRAP_SEED,
    PRIMARY_CANDIDATE_SPEC,
    REPO_ROOT,
    SECONDARY_CHALLENGER_SPEC,
    evaluate_relative_volume_status,
    verify_spec_integrity,
)


def get_git_commit_sha() -> str:
    """Retrieve current HEAD commit SHA."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    """Execute official LONG-002D2 incremental reranking study."""
    parser = argparse.ArgumentParser(
        description="LONG-002D2: Incremental Ranking Value of Relative Volume Beyond Frozen VAM5"
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional unique run ID (default: current UTC timestamp YYYY-MM-DD-HHMMSS)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Target directory for committed summary artifacts",
    )
    parser.add_argument(
        "--prereg-commit-sha",
        type=str,
        default="494caa8df3e60bae15e5015ad98a42a13eb109f3",
        help="Exact preregistration commit SHA",
    )
    parser.add_argument(
        "--execution-code-sha",
        type=str,
        default=None,
        help="Optional explicit execution commit SHA (default: runtime git rev-parse HEAD)",
    )

    args = parser.parse_args(argv)

    # Verify execution code provenance early to prevent spoofing
    git_sha = get_git_commit_sha()
    if not git_sha or git_sha == "unknown":
        raise RuntimeError("Cannot record official execution metadata: git commit SHA is unknown")

    if args.execution_code_sha and args.execution_code_sha != git_sha:
        raise ValueError(
            f"EXECUTION CODE SHA MISMATCH: supplied --execution-code-sha '{args.execution_code_sha}' "
            f"does not match runtime git HEAD '{git_sha}'"
        )

    exec_sha = git_sha

    start_wall = time.time()
    start_iso = datetime.datetime.now(datetime.UTC).isoformat()
    run_id = args.run_id or datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d-%H%M%S")

    if args.output_dir is not None:
        out_dir = args.output_dir
    else:
        out_dir = REPO_ROOT / "docs" / "research" / "artifacts" / "LONG-002D2" / run_id

    print("=" * 70)
    print("LONG-002D2: INCREMENTAL RERANKING EXPERIMENT")
    print(f"Run ID: {run_id}")
    print(f"Output Directory: {out_dir}")
    print("=" * 70)

    # 1. Verify spec integrity
    print("\n[1/6] Verifying preregistered specification integrity...")
    spec_sha = verify_spec_integrity()
    print(f"  Spec SHA-256: {spec_sha} (VERIFIED)")

    # 2. Load and verify datasets
    print("\n[2/6] Loading datasets and verifying input hashes...")
    df_merged, audit = load_and_verify_datasets()
    print(f"  Joined Common Observations: {len(df_merged):,}")
    print(f"  D1 Feature Table SHA: {audit.feature_table_sha256} (MATCH)")
    print(f"  Stage C Baseline SHA: {audit.baseline_sha256} (MATCH)")

    # 3. SPY regime mapping
    print("\n[3/6] Mapping date-level SPY return regimes...")
    spy_regime_map = compute_spy_date_regimes(df_merged)
    print(f"  Total Regime-Mapped Dates: {len(spy_regime_map)}")

    # 4. Primary candidate: relative_volume_20
    print("\n[4/6] Evaluating PRIMARY CANDIDATE: relative_volume_20...")
    p_overall, p_annual, p_date_res = run_coverage_matched_reranking(
        df_merged,
        PRIMARY_CANDIDATE_SPEC,
    )
    p_dates_sorted = sorted(p_date_res.keys())

    print("  Running paired calendar-block bootstrap (21 and 42 sessions, 1000 reps)...")
    p_boot_summaries, _ = run_paired_calendar_block_bootstrap(
        unique_dates=p_dates_sorted,
        date_results=p_date_res,
        block_sizes=(BOOTSTRAP_PRIMARY_BLOCK_SIZE, BOOTSTRAP_ROBUSTNESS_BLOCK_SIZE),
        replicates=BOOTSTRAP_REPLICATES,
        seed=BOOTSTRAP_SEED,
    )
    p_boot21 = p_boot_summaries[BOOTSTRAP_PRIMARY_BLOCK_SIZE]
    p_boot42 = p_boot_summaries[BOOTSTRAP_ROBUSTNESS_BLOCK_SIZE]

    p_regimes = evaluate_regime_diagnostics(p_date_res, spy_regime_map)

    # Determine primary status
    primary_status = evaluate_relative_volume_status(
        pooled_precision_delta=p_overall["absolute_precision_delta"],
        ci_2_5_block_21=p_boot21.ci_2_5,
        ci_97_5_block_21=p_boot21.ci_97_5,
        median_block_42=p_boot42.median_delta,
        annual_positive_delta_years=p_overall["positive_annual_years_count"],
        all_integrity_gates_passed=audit.gates_passed,
    )

    primary_result = CandidateEvaluationResult(
        feature_id=PRIMARY_CANDIDATE_SPEC.feature_id,
        role=PRIMARY_CANDIDATE_SPEC.role,
        status=primary_status,
        common_observations=p_overall["common_observations"],
        coverage_within_top_25=p_overall["coverage_within_top_25"],
        evaluation_dates_count=p_overall["evaluation_dates_count"],
        total_selected_count=p_overall["total_selected_count"],
        candidate_clean_count=p_overall["candidate_clean_count"],
        candidate_precision=p_overall["candidate_precision"],
        matched_vam5_clean_count=p_overall["matched_vam5_clean_count"],
        matched_vam5_precision=p_overall["matched_vam5_precision"],
        absolute_precision_delta=p_overall["absolute_precision_delta"],
        precision_ratio=p_overall["precision_ratio"],
        incremental_clean_events=p_overall["incremental_clean_events"],
        selection_overlap_count=p_overall["selection_overlap_count"],
        selection_overlap_rate=p_overall["selection_overlap_rate"],
        annual_breakdowns=p_annual,
        positive_annual_years_count=p_overall["positive_annual_years_count"],
        bootstrap_21=p_boot21,
        bootstrap_42=p_boot42,
        regime_breakdowns=p_regimes,
    )

    print(f"  Primary Candidate Status: {primary_status.upper()}")
    print(f"  Candidate Precision: {p_overall['candidate_precision']:.4%} ({p_overall['candidate_clean_count']:,}/{p_overall['total_selected_count']:,})")
    print(f"  Matched VAM5 Precision: {p_overall['matched_vam5_precision']:.4%} ({p_overall['matched_vam5_clean_count']:,}/{p_overall['total_selected_count']:,})")
    print(f"  Absolute Delta: {p_overall['absolute_precision_delta']:+.4%} ({p_overall['absolute_precision_delta']*100:+.2f} pp)")
    print(f"  21-Session 95% CI: [{p_boot21.ci_2_5:+.4f}, {p_boot21.ci_97_5:+.4f}]")
    print(f"  42-Session Median: {p_boot42.median_delta:+.4f}")
    print(f"  Annual Stability: {p_overall['positive_annual_years_count']}/5 years positive delta")

    # 5. Secondary challenger: sma20_slope_5
    print("\n[5/6] Evaluating SECONDARY CHALLENGER: sma20_slope_5...")
    c_overall, c_annual, c_date_res = run_coverage_matched_reranking(
        df_merged,
        SECONDARY_CHALLENGER_SPEC,
    )
    c_dates_sorted = sorted(c_date_res.keys())

    c_boot_summaries, _ = run_paired_calendar_block_bootstrap(
        unique_dates=c_dates_sorted,
        date_results=c_date_res,
        block_sizes=(BOOTSTRAP_PRIMARY_BLOCK_SIZE, BOOTSTRAP_ROBUSTNESS_BLOCK_SIZE),
        replicates=BOOTSTRAP_REPLICATES,
        seed=BOOTSTRAP_SEED,
    )
    c_boot21 = c_boot_summaries[BOOTSTRAP_PRIMARY_BLOCK_SIZE]
    c_boot42 = c_boot_summaries[BOOTSTRAP_ROBUSTNESS_BLOCK_SIZE]

    c_regimes = evaluate_regime_diagnostics(c_date_res, spy_regime_map)

    challenger_result = CandidateEvaluationResult(
        feature_id=SECONDARY_CHALLENGER_SPEC.feature_id,
        role=SECONDARY_CHALLENGER_SPEC.role,
        status="descriptive_challenger",
        common_observations=c_overall["common_observations"],
        coverage_within_top_25=c_overall["coverage_within_top_25"],
        evaluation_dates_count=c_overall["evaluation_dates_count"],
        total_selected_count=c_overall["total_selected_count"],
        candidate_clean_count=c_overall["candidate_clean_count"],
        candidate_precision=c_overall["candidate_precision"],
        matched_vam5_clean_count=c_overall["matched_vam5_clean_count"],
        matched_vam5_precision=c_overall["matched_vam5_precision"],
        absolute_precision_delta=c_overall["absolute_precision_delta"],
        precision_ratio=c_overall["precision_ratio"],
        incremental_clean_events=c_overall["incremental_clean_events"],
        selection_overlap_count=c_overall["selection_overlap_count"],
        selection_overlap_rate=c_overall["selection_overlap_rate"],
        annual_breakdowns=c_annual,
        positive_annual_years_count=c_overall["positive_annual_years_count"],
        bootstrap_21=c_boot21,
        bootstrap_42=c_boot42,
        regime_breakdowns=c_regimes,
    )

    print(f"  Challenger Precision: {c_overall['candidate_precision']:.4%} ({c_overall['candidate_clean_count']:,}/{c_overall['total_selected_count']:,})")
    print(f"  Matched VAM5 Precision: {c_overall['matched_vam5_precision']:.4%} ({c_overall['matched_vam5_clean_count']:,}/{c_overall['total_selected_count']:,})")
    print(f"  Absolute Delta: {c_overall['absolute_precision_delta']:+.4%} ({c_overall['absolute_precision_delta']*100:+.2f} pp)")
    print(f"  21-Session 95% CI: [{c_boot21.ci_2_5:+.4f}, {c_boot21.ci_97_5:+.4f}]")
    print(f"  42-Session Median: {c_boot42.median_delta:+.4f}")
    print(f"  Annual Stability: {c_overall['positive_annual_years_count']}/5 years positive delta")

    # 6. Write artifacts
    end_wall = time.time()
    end_iso = datetime.datetime.now(datetime.UTC).isoformat()
    duration_s = round(end_wall - start_wall, 2)

    timing = {
        "start_iso": start_iso,
        "end_iso": end_iso,
        "duration_seconds": duration_s,
    }

    print("\n[6/6] Writing committed summary artifacts...")
    print(f"  Execution Code SHA: {exec_sha}")
    checksums = write_d2_artifacts(
        run_id=run_id,
        output_dir=out_dir,
        preregistration_commit_sha=args.prereg_commit_sha,
        execution_code_sha=exec_sha,
        audit=audit,
        primary_result=primary_result,
        challenger_result=challenger_result,
        execution_timing=timing,
    )
    for fname, sha in sorted(checksums.items()):
        print(f"  {fname}: {sha}")

    print("\n" + "=" * 70)
    print(f"LONG-002D2 EXECUTION COMPLETED IN {duration_s:.1f}s")
    print(f"Primary Status: {primary_status.upper()}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
