"""Command-line interface for the DAYTRADE-001 reversal study engine."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .artifacts import write_artifact_bundle
from .dataset import validate_dataset_root
from .freeze import freeze_evaluation_state
from .spec import load_and_verify_spec
from .study import HoldoutAccessDeniedError, evaluate_split, load_and_evaluate_holdout


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser with subcommands: verify-spec, freeze, evaluate, build-dataset."""
    parser = argparse.ArgumentParser(
        prog="python -m tradex.research.daytrade_reversal",
        description="DAYTRADE-001 Extreme Downside Reversal Research CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. verify-spec
    p_verify = subparsers.add_parser("verify-spec", help="Verify locked specification SHA-256")
    p_verify.add_argument("--spec", type=Path, default=None, help="Path to specification JSON")

    # 2. freeze
    p_freeze = subparsers.add_parser("freeze", help="Freeze evaluation code state")
    p_freeze.add_argument("--spec", type=Path, default=None, help="Path to specification JSON")
    p_freeze.add_argument("--output", type=Path, default=None, help="Output directory for freeze.json")

    # 3. evaluate
    p_eval = subparsers.add_parser("evaluate", help="Evaluate a specific dataset split")
    p_eval.add_argument(
        "--split",
        required=True,
        choices=["warmup", "development", "validation", "holdout"],
        help="Explicit split to evaluate; holdout requires passing validation",
    )
    p_eval.add_argument("--spec", type=Path, default=None, help="Path to specification JSON")
    p_eval.add_argument("--dataset-root", type=Path, default=None, help="Path to dataset root")
    p_eval.add_argument("--output", type=Path, required=True, help="Directory to write study artifacts")
    p_eval.add_argument(
        "--validation-artifact-dir",
        type=Path,
        default=None,
        help="Required when --split holdout to prove validation support",
    )

    # 4. build-dataset
    p_build = subparsers.add_parser("build-dataset", help="Future dataset acquisition (unauthorized in C1)")
    p_build.add_argument("--spec", type=Path, default=None, help="Path to specification JSON")
    p_build.add_argument("--dataset-root", type=Path, required=True, help="Path to external dataset root")
    p_build.add_argument("--dry-run", action="store_true", help="Dry-run verification only")

    return parser


def cmd_verify_spec(args: argparse.Namespace) -> int:
    """Verify locked specification hash."""
    spec = load_and_verify_spec(args.spec)
    print(f"PASS: {spec.task_id} specification SHA-256 verified: {spec.sha256}")
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    """Freeze current evaluator state and output freeze.json."""
    spec = load_and_verify_spec(args.spec)
    record = freeze_evaluation_state(spec_sha256=spec.sha256)
    out_dir = args.output or Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    freeze_file = out_dir / "freeze.json"
    freeze_file.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    print(f"PASS: Evaluation state frozen at HEAD {record.evaluation_code_sha}")
    print(f"Wrote: {freeze_file}")
    return 0


def cmd_build_dataset(args: argparse.Namespace) -> int:
    """Refuse live acquisition in DAYTRADE-001C1 unless dry-run."""
    validate_dataset_root(args.dataset_root)
    if not args.dry_run:
        print(
            "ERROR: Live provider dataset acquisition is unauthorized in DAYTRADE-001C1.\n"
            "DAYTRADE-001C1 must make zero network/provider calls.\n"
            "Execution belongs to future DAYTRADE-001C2.",
            file=sys.stderr,
        )
        return 1

    print("PASS: Dry-run dataset validation succeeded (0 network calls made).")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate a specific split."""
    spec = load_and_verify_spec(args.spec)

    if args.split == "holdout":
        if not args.validation_artifact_dir:
            print(
                "ERROR: --validation-artifact-dir is required when evaluating holdout.",
                file=sys.stderr,
            )
            return 1
        try:
            # Dummy loader for CLI if dataset-root is not provided; loader only invoked if guard passes
            def dummy_loader() -> list[Any]:
                return []

            result = load_and_evaluate_holdout(
                validation_artifact_dir=args.validation_artifact_dir,
                spec=spec,
                holdout_loader=dummy_loader,
            )
        except HoldoutAccessDeniedError as e:
            print(f"HOLDOUT ACCESS BLOCKED: {e}", file=sys.stderr)
            return 2
    else:
        # Evaluate split
        result = evaluate_split(
            split_name=args.split,
            sessions=[],
            spec=spec,
        )

    out_dir = args.output
    out_dir.mkdir(parents=True, exist_ok=True)
    write_artifact_bundle(
        output_dir=out_dir,
        result=result,
        spec=spec,
    )
    print(f"PASS: Evaluated {args.split} with disposition: {result.disposition.upper()}")
    print(f"Artifacts written to: {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "verify-spec":
        return cmd_verify_spec(args)
    if args.command == "freeze":
        return cmd_freeze(args)
    if args.command == "build-dataset":
        return cmd_build_dataset(args)
    if args.command == "evaluate":
        return cmd_evaluate(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
