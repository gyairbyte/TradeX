"""Command-line interface and orchestrator for LONG-002E1 Round-1 candidate search."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from tradex.research.long_002e1.artifacts import (
    build_and_write_artifacts,
    generate_markdown_results_report,
)
from tradex.research.long_002e1.bootstrap import run_paired_calendar_bootstrap
from tradex.research.long_002e1.configs import build_round1_registry
from tradex.research.long_002e1.evaluation import (
    assign_round1_status,
    evaluate_configuration_predictions,
)
from tradex.research.long_002e1.gbdt import fit_and_predict_gbdt
from tradex.research.long_002e1.loader import (
    load_primary_dataset,
    verify_input_digests,
)
from tradex.research.long_002e1.probabilistic import fit_and_predict_logistic
from tradex.research.long_002e1.rank_model import evaluate_rank_model
from tradex.research.long_002e1.spec import (
    BASE_GIT_SHA,
    CORR_TASK_ID,
    EXPECTED_CORR_SPEC_SHA256,
    PREREGISTRATION_COMMIT_SHA,
    PREREGISTRATION_SPEC_SHA256,
    SUPERSEDED_RUN_ID,
    TASK_ID,
    verify_spec_integrity,
)
from tradex.research.long_002e1.splits import (
    build_fold_definitions,
    split_fold_data,
)


def get_git_head_sha(repo_root: Path) -> str:
    """Retrieve current commit SHA from git."""
    res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def check_git_clean(repo_root: Path) -> bool:
    """Check if git working tree is clean."""
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return len(res.stdout.strip()) == 0


def run_official_round1_search(
    run_id: str | None = None,
    execution_sha: str | None = None,
    repo_root: Path | None = None,
    round_num: int = 1,
) -> dict[str, Any]:
    """Execute the preregistered Round-1 candidate-system search.

    Rejects Round 2 or any other round numbers.
    Enforces specification integrity before data loading.
    Enforces clean git status (fail-closed, no dirty bypass).
    Enforces runtime HEAD equality with execution_sha if provided.
    Evaluates exactly 36 configurations across 3 families over common 2018-2020.
    Writes safe artifacts and external parquets.
    """
    if round_num != 1:
        raise ValueError(
            f"Round {round_num} is not authorized under assignment "
            "LONG-002E1-ROUND1-CANDIDATE-SEARCH-001. Requires separate assignment."
        )

    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[3]

    # 1. Upfront specification integrity verification
    verify_spec_integrity()

    # 2. Fail-closed git working tree check
    if not check_git_clean(repo_root):
        raise RuntimeError(
            "Working tree is dirty. Execution requires a clean working tree."
        )

    # 3. Resolve runtime git HEAD
    runtime_head_sha = get_git_head_sha(repo_root)
    if not runtime_head_sha:
        raise RuntimeError("Failed to resolve runtime git HEAD commit SHA.")

    if execution_sha is not None and execution_sha != runtime_head_sha:
        raise ValueError(
            f"EXECUTION SHA MISMATCH: Supplied execution SHA {execution_sha} "
            f"does not match runtime HEAD {runtime_head_sha}."
        )
    execution_code_sha = runtime_head_sha

    if run_id is None:
        timestamp_str = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
        run_id = f"LONG-002E1-{timestamp_str}"

    print("=== LONG-002E1 Official Round-1 Candidate Search (CORR-001) ===")
    print(f"Run ID: {run_id}")
    print(f"Execution Code SHA: {execution_code_sha}")
    print(f"Base Git SHA: {BASE_GIT_SHA}")
    print(f"Preregistration Spec SHA-256: {PREREGISTRATION_SPEC_SHA256}")
    print(f"Correction Spec SHA-256: {EXPECTED_CORR_SPEC_SHA256}")
    print(f"Supersedes Run ID: {SUPERSEDED_RUN_ID}")

    # 1. Load primary dataset and verify input digests
    print("\n[1/5] Loading primary datasets and verifying digests...")
    input_digests = verify_input_digests()
    df_feat, df_base = load_primary_dataset()
    print(f"Loaded {len(df_feat):,} observations across {df_feat['as_of_date'].nunique()} sessions.")
    print(f"Clean events count: {int(df_feat['clean_target_reached'].sum()):,} ({df_feat['clean_target_reached'].mean():.4%})")

    input_integrity = {
        "file_digests": input_digests,
        "total_population_rows": len(df_feat),
        "clean_events_count": int(df_feat["clean_target_reached"].sum()),
        "clean_base_rate": float(df_feat["clean_target_reached"].mean()),
        "verification_status": "verified_against_spec",
    }

    # 2. Setup outputs directories
    artifacts_dir = repo_root / "docs" / "research" / "artifacts" / "LONG-002E1" / run_id
    external_data_dir = repo_root / "data" / "research" / "long_002e1" / run_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    external_data_dir.mkdir(parents=True, exist_ok=True)

    # 3. Build fold definitions and pre-split data
    print("\n[2/5] Constructing expanding folds and pre-splitting data...")
    folds = build_fold_definitions(purge_sessions_count=26)
    fold_splits: dict[int, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for f in folds:
        tr, ev = split_fold_data(df_feat, f)
        fold_splits[f.fold_id] = (tr, ev)
        print(f"Fold {f.fold_id}: Train {len(tr):,} rows | Eval ({f.eval_year}) {len(ev):,} rows")

    # Full evaluation population across common 2018-2020
    df_eval_all = pd.concat([fold_splits[f.fold_id][1] for f in folds], ignore_index=True)
    eval_row_count = len(df_eval_all)
    eval_sessions_count = len(df_eval_all["as_of_date"].unique())
    print(f"Total OOF evaluation observations (2018-2020): {eval_row_count:,} across {eval_sessions_count} sessions.")

    # 4. Build configuration registry
    configs = build_round1_registry()
    print(f"\n[3/5] Initializing registry with {len(configs)} configurations across 3 families...")

    eval_summaries = {}
    bootstrap_results_21 = {}
    bootstrap_results_42 = {}
    config_statuses = {}
    execution_failures = {}
    external_manifest_files = []

    # 5. Evaluate each configuration
    print("\n[4/5] Executing candidate evaluations...")
    for idx, c in enumerate(configs, start=1):
        cid = c.config_id
        fam = c.family
        slot = c.budget_slot
        print(f"  [{slot}/36] Evaluating {cid} ({fam}, subset={c.feature_subset_id})...", end=" ", flush=True)

        try:
            # Generate fold predictions
            fold_preds: list[pd.Series] = []

            for f in folds:
                tr, ev = fold_splits[f.fold_id]
                if fam == "cross_sectional_rank_score":
                    p = evaluate_rank_model(ev, c)
                elif fam == "regularized_probabilistic":
                    p = fit_and_predict_logistic(tr, ev, c)
                elif fam == "shallow_strongly_regularized_gbdt":
                    p = fit_and_predict_gbdt(tr, ev, c)
                else:
                    raise ValueError(f"Unknown family: {fam}")

                if p is None:
                    # Training set empty or failed: fill with NaN
                    p = pd.Series(np.nan, index=ev.index, name="candidate_score")
                fold_preds.append(p)

            # Concatenate predictions across all evaluation folds
            all_scores = pd.concat(fold_preds, ignore_index=True)

            score_col_name = "candidate_score" if fam == "cross_sectional_rank_score" else "candidate_probability"
            df_pred = pd.DataFrame(
                {
                    "immutable_security_id": df_eval_all["immutable_security_id"].values,
                    "as_of_date": df_eval_all["as_of_date"].values,
                    "cutoff_time": df_eval_all["cutoff_time"].values,
                    "ticker_at_decision": df_eval_all["ticker_at_decision"].values,
                    "clean_target_reached": df_eval_all["clean_target_reached"].values,
                    score_col_name: all_scores.values,
                    "realized_clean_tier": df_eval_all["realized_clean_tier"].values,
                    "adverse_excursion": df_eval_all["adverse_excursion"].values,
                    "time_to_target": df_eval_all["time_to_target"].values,
                }
            )

            # Write external gitignored row-level predictions parquet
            parquet_filename = f"predictions_{fam}_{cid}.parquet"
            parquet_path = external_data_dir / parquet_filename
            table = pa.Table.from_pandas(df_pred)
            pq.write_table(table, parquet_path, compression="snappy")

            # Compute parquet SHA-256
            parquet_sha = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
            external_manifest_files.append(
                {
                    "filename": parquet_filename,
                    "relative_path": str(parquet_path.relative_to(repo_root)).replace("\\", "/"),
                    "row_count": len(df_pred),
                    "sha256": parquet_sha,
                    "family": fam,
                    "configuration_id": cid,
                }
            )

            # Evaluate candidate against matched VAM5
            summary = evaluate_configuration_predictions(
                df_predictions=df_pred,
                df_vam5=df_base,
                config_id=cid,
                family=fam,
                subset_id=c.feature_subset_id,
                score_column=score_col_name,
            )

            # Paired calendar bootstrap (21-session primary and 42-session robustness)
            bs21 = run_paired_calendar_bootstrap(summary.date_level_data, block_size=21, replicates=1000, seed=20261005)
            bs42 = run_paired_calendar_bootstrap(summary.date_level_data, block_size=42, replicates=1000, seed=20261005)

            # Disposition status
            status = assign_round1_status(summary, (bs21.p10_delta_lower, bs21.p10_delta_median, bs21.p10_delta_upper))

            eval_summaries[cid] = summary
            bootstrap_results_21[cid] = bs21
            bootstrap_results_42[cid] = bs42
            config_statuses[cid] = status

            print(f"Status: {status} | P@10: {summary.top10.precision:.2%} (delta: {summary.top10.precision_delta_vs_vam5:+.2%}) | BS 95%: [{bs21.p10_delta_lower:+.2%}, {bs21.p10_delta_upper:+.2%}]")

        except Exception as e:  # noqa: BLE001
            print(f"FAILED: {e}")
            execution_failures[cid] = str(e)
            config_statuses[cid] = "invalid_configuration"

    # Assemble execution metadata
    executed_at = datetime.datetime.now(datetime.UTC).isoformat()
    metadata = {
        "task_id": TASK_ID,
        "correction_task_id": CORR_TASK_ID,
        "correction_spec_sha": EXPECTED_CORR_SPEC_SHA256,
        "attempt_number": 2,
        "consumes_new_material_slot": False,
        "superseded_run_id": SUPERSEDED_RUN_ID,
        "superseded_reason": (
            "Fold-1 design asymmetry left fitted families unpredicted in 2017 "
            "due to post-purge 2016 training set having zero rows; models evaluated on "
            "non-common periods (2017-2020 vs 2018-2020) and non-common baselines; "
            "outcome matrix positional merge; unverified execution provenance; mislabeled calibration status."
        ),
        "run_id": run_id,
        "base_git_sha": BASE_GIT_SHA,
        "preregistration_commit_sha": PREREGISTRATION_COMMIT_SHA,
        "preregistration_spec_sha": PREREGISTRATION_SPEC_SHA256,
        "execution_code_sha": execution_code_sha,
        "executed_at": executed_at,
        "python_environment": sys.version,
        "system_info": platform.platform(),
        "total_configurations_budgeted": 36,
        "total_configurations_attempted": 36,
        "total_configurations_completed": len(eval_summaries),
        "common_evaluation_period": "2018-01-01 to 2020-12-31",
        "evaluation_sessions_count": eval_sessions_count,
        "round2_authorized": False,
        "requires_separate_assignment": True,
    }

    external_manifest = {
        "run_id": run_id,
        "storage_directory": str(external_data_dir.relative_to(repo_root)).replace("\\", "/"),
        "total_files": len(external_manifest_files),
        "files": external_manifest_files,
    }

    # 6. Build and write safe committed artifacts
    print("\n[5/5] Writing safe artifacts and compiling Markdown report...")
    checksums = build_and_write_artifacts(
        run_id=run_id,
        output_dir=artifacts_dir,
        metadata=metadata,
        input_integrity=input_integrity,
        configs=configs,
        eval_summaries=eval_summaries,
        bootstrap_results_21=bootstrap_results_21,
        bootstrap_results_42=bootstrap_results_42,
        config_statuses=config_statuses,
        external_manifest=external_manifest,
        execution_failures=execution_failures,
    )

    # Load written artifacts to generate Markdown report
    with (artifacts_dir / "baseline_summary.json").open("r", encoding="utf-8") as f:
        base_summary = json.load(f)
    with (artifacts_dir / "round1_summary.json").open("r", encoding="utf-8") as f:
        round1_summary = json.load(f)
    with (artifacts_dir / "family_summary.json").open("r", encoding="utf-8") as f:
        family_summary = json.load(f)
    with (artifacts_dir / "round2_readiness.json").open("r", encoding="utf-8") as f:
        readiness = json.load(f)

    report_md = generate_markdown_results_report(
        run_id=run_id,
        metadata=metadata,
        base_summary=base_summary,
        round1_summary=round1_summary,
        family_summary=family_summary,
        readiness=readiness,
        checksums=checksums,
    )

    report_path = repo_root / "docs" / "research" / "LONG-002E1-ROUND1-RESULTS.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write(report_md)

    print("\nExecution complete!")
    print(f"Artifacts written to: {artifacts_dir}")
    print(f"Report written to: {report_path}")
    print(f"Overall Disposition: {readiness['overall_status']}")
    print(f"Eligible Configurations for Round 2: {readiness['eligible_configuration_ids']}")

    return {
        "run_id": run_id,
        "metadata": metadata,
        "artifacts_dir": artifacts_dir,
        "report_path": report_path,
        "checksums": checksums,
        "readiness": readiness,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="LONG-002E1: Round-1 Candidate-System Search Orchestrator"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run the official Round-1 candidate search")
    run_parser.add_argument("--run-id", type=str, default=None, help="Custom run identifier")
    run_parser.add_argument("--execution-sha", type=str, default=None, help="Execution code Git SHA override")
    run_parser.add_argument("--repo-root", type=Path, default=None, help="Repository root path")
    run_parser.add_argument("--round", type=str, default="1", help="Round number (only round 1 authorized)")

    # Optional root-level arguments for convenience
    parser.add_argument("--round", type=str, default=None, help="Round number")

    args = parser.parse_args(argv)

    # Check for round 2 authorization
    round_arg = getattr(args, "round", None)
    if round_arg is not None and str(round_arg).strip() not in ("1", "None"):
        print(
            "Round 2 is not authorized under assignment LONG-002E1-ROUND1-CANDIDATE-SEARCH-001. "
            "Requires separate assignment.",
            file=sys.stderr,
        )
        return 1

    if args.command == "run" or args.command is None:
        try:
            round_val = int(getattr(args, "round", 1) or 1)
            run_official_round1_search(
                run_id=getattr(args, "run_id", None),
                execution_sha=getattr(args, "execution_sha", None),
                repo_root=getattr(args, "repo_root", None),
                round_num=round_val,
            )
            return 0
        except Exception as e:  # noqa: BLE001
            print(f"Error during execution: {e}", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
