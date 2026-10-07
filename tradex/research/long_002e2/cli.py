"""Official execution CLI and provenance gating for LONG-002E2."""

from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

from tradex.research.long_002e2.artifacts import (
    generate_markdown_report,
    save_diagnostic_artifacts,
)
from tradex.research.long_002e2.diagnostics import run_all_e2_diagnostics
from tradex.research.long_002e2.spec import (
    EXPECTED_SPEC_SHA256,
    REPO_ROOT,
    REPRESENTATIVE_CONFIGURATION_ID,
    TASK_ID,
    verify_e2_spec_hash,
)

PREREGISTRATION_COMMIT_SHA = "90f3b3daa8c6ac234da724e8ad1ce2ec629a1bc7"


def get_runtime_git_head() -> str:
    """Resolve runtime HEAD commit SHA."""
    res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def check_worktree_clean() -> None:
    """Assert git worktree has no uncommitted changes or untracked files."""
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    uncommitted = res.stdout.strip()
    if uncommitted:
        raise RuntimeError(
            f"DIRTY WORKTREE BREACH: Worktree contains uncommitted changes:\n{uncommitted}\n"
            "Official execution strictly requires a clean committed worktree."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Official execution entry point for LONG-002E2 logistic stability diagnostic."
    )
    parser.add_argument(
        "--execution-sha",
        type=str,
        default=None,
        help="Optional expected git commit SHA of committed code. Fails closed if mismatched.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional destination path for safe artifacts bundle.",
    )
    args = parser.parse_args(argv)

    # 1. Spec hash verification before any empirical loading
    verify_e2_spec_hash()

    # 2. Strict provenance and clean worktree checks
    check_worktree_clean()
    runtime_head = get_runtime_git_head()
    if args.execution_sha is not None and args.execution_sha != runtime_head:
        raise ValueError(
            f"EXECUTION SHA MISMATCH: provided {args.execution_sha} != runtime HEAD {runtime_head}"
        )

    # 3. Create run ID
    now_utc = datetime.datetime.now(datetime.UTC)
    run_id = f"LONG-002E2-{now_utc.strftime('%Y%m%d_%H%M%S')}"

    print(f"=== Starting Official Execution: {TASK_ID} ===")
    print(f"Run ID: {run_id}")
    print(f"Runtime HEAD: {runtime_head}")
    print(f"Preregistration Commit: {PREREGISTRATION_COMMIT_SHA}")
    print(f"Representative Configuration: {REPRESENTATIVE_CONFIGURATION_ID}")

    # 4. Run all diagnostics
    results = run_all_e2_diagnostics()

    # 5. Formulate execution metadata
    execution_metadata = {
        "task_id": TASK_ID,
        "run_id": run_id,
        "execution_timestamp_utc": now_utc.isoformat(),
        "execution_code_sha": runtime_head,
        "preregistration_commit_sha": PREREGISTRATION_COMMIT_SHA,
        "spec_sha256": EXPECTED_SPEC_SHA256,
        "representative_configuration_id": REPRESENTATIVE_CONFIGURATION_ID,
        "clean_worktree_verified": True,
        "zero_provider_calls": True,
        "quarantines_enforced": True,
        "python_version": sys.version,
    }

    # Inject run_id into diagnostic decision
    results["diagnostic_decision"]["run_id"] = run_id
    results["diagnostic_decision"]["execution_code_sha"] = runtime_head

    # 6. Save safe artifacts
    if args.output_dir is not None:
        target_artifacts_dir = args.output_dir
    else:
        target_artifacts_dir = REPO_ROOT / "docs" / "research" / "artifacts" / "LONG-002E2" / run_id

    checksums = save_diagnostic_artifacts(
        artifacts_dir=target_artifacts_dir,
        execution_metadata=execution_metadata,
        input_integrity=results["input_integrity"],
        reproduction_check=results["reproduction_check"],
        family_context=results["family_context"],
        annual_bootstrap=results["annual_bootstrap"],
        quarterly_diagnostics=results["quarterly_diagnostics"],
        spy_regime_diagnostics=results["spy_regime_diagnostics"],
        selection_set_decomposition=results["selection_set_decomposition"],
        feature_profile_drift=results["feature_profile_drift"],
        selection_concentration=results["selection_concentration"],
        probability_stability=results["probability_stability"],
        localization_metrics=results["localization_metrics"],
        diagnostic_decision=results["diagnostic_decision"],
    )

    # 7. Generate markdown report
    markdown_report = generate_markdown_report(
        run_id=run_id,
        execution_metadata=execution_metadata,
        reproduction_check=results["reproduction_check"],
        family_context=results["family_context"],
        annual_bootstrap=results["annual_bootstrap"],
        quarterly_diagnostics=results["quarterly_diagnostics"],
        spy_regime_diagnostics=results["spy_regime_diagnostics"],
        selection_set_decomposition=results["selection_set_decomposition"],
        feature_profile_drift=results["feature_profile_drift"],
        selection_concentration=results["selection_concentration"],
        probability_stability=results["probability_stability"],
        localization_metrics=results["localization_metrics"],
        diagnostic_decision=results["diagnostic_decision"],
    )
    report_path = REPO_ROOT / "docs" / "research" / "LONG-002E2-STABILITY-DIAGNOSTIC.md"
    report_path.write_text(markdown_report, encoding="utf-8")

    print(
        f"\nArtifacts successfully written to: {target_artifacts_dir} ({len(checksums)} safe JSON artifacts)"
    )
    print(f"Research report updated at: {report_path}")
    print(f"Diagnostic Disposition: {results['diagnostic_decision']['diagnostic_disposition']}")
    print(f"Recommended Next Action: {results['diagnostic_decision']['recommended_next_action']}")
    print("=== Official Execution Complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
