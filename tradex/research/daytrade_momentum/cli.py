"""Command-line interface for the DAYTRADE-002 momentum study engine."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .artifacts import sha256_of_file, write_artifact_bundle
from .dataset import (
    acquire_dataset_partition,
)
from .freeze import (
    EvaluationFreezeRecord,
    freeze_evaluation_state,
    verify_freeze_state,
)
from .spec import load_and_verify_spec
from .study import (
    evaluate_split,
    verify_holdout_access_prerequisites,
)


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser with subcommands: verify-spec, freeze, evaluate, build-dataset."""
    parser = argparse.ArgumentParser(
        prog="python -m tradex.research.daytrade_momentum",
        description="DAYTRADE-002 Early-to-Late ETF Momentum Research CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. verify-spec
    p_verify = subparsers.add_parser("verify-spec", help="Verify locked specification SHA-256")
    p_verify.add_argument("--spec", type=Path, default=None, help="Path to specification JSON")

    # 2. freeze
    p_freeze = subparsers.add_parser("freeze", help="Freeze evaluation code state")
    p_freeze.add_argument("--spec", type=Path, default=None, help="Path to specification JSON")
    p_freeze.add_argument("--manifest", type=Path, default=None, help="Path to manifest.lock.json")
    p_freeze.add_argument("--dataset-root", type=Path, default=None, help="Path to dataset root")
    p_freeze.add_argument("--output", type=Path, required=True, help="Output directory for freeze.json")

    # 3. evaluate
    p_eval = subparsers.add_parser("evaluate", help="Evaluate a specific dataset split")
    p_eval.add_argument(
        "--split",
        required=True,
        choices=["development", "validation", "holdout"],
        help="Explicit split to evaluate (warmup is history-only and not evaluatable)",
    )
    p_eval.add_argument("--spec", type=Path, default=None, help="Path to specification JSON")
    p_eval.add_argument("--dataset-root", type=Path, default=None, help="Path to external dataset root")
    p_eval.add_argument("--freeze", type=Path, default=None, help="Path to freeze.json (required for validation)")
    p_eval.add_argument("--output", type=Path, required=True, help="Directory to write study artifacts")
    p_eval.add_argument(
        "--validation-artifact-dir",
        type=Path,
        default=None,
        help="Required when --split holdout to prove validation support",
    )

    # 4. build-dataset
    p_build = subparsers.add_parser("build-dataset", help="Dataset acquisition adapter (dry-run or authorized provider)")
    p_build.add_argument("--spec", type=Path, default=None, help="Path to specification JSON")
    p_build.add_argument("--dataset-root", type=Path, required=True, help="Path to external dataset root")
    p_build.add_argument(
        "--split",
        choices=["preholdout", "holdout"],
        default="preholdout",
        help="Dataset partition to acquire (preholdout or holdout)",
    )
    p_build.add_argument("--dry-run", action="store_true", help="Dry-run verification only (zero network calls)")
    p_build.add_argument("--execute-provider", action="store_true", help="Authorize execution against Alpaca adapter")
    p_build.add_argument(
        "--validation-artifact-dir",
        type=Path,
        default=None,
        help="Required when --split holdout to prove validation support",
    )

    return parser


def cmd_verify_spec(args: argparse.Namespace) -> int:
    """Verify locked specification hash."""
    try:
        spec = load_and_verify_spec(args.spec)
        print(f"PASS: Spec {spec.task_id} v{spec.spec_version} verified. SHA-256: {spec.sha256}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: Specification verification error: {e}", file=sys.stderr)
        return 1


def cmd_freeze(args: argparse.Namespace) -> int:
    """Freeze evaluation code state."""
    try:
        spec = load_and_verify_spec(args.spec)
        manifest_sha: str | None = None
        if args.manifest is not None:
            m_data = json.loads(args.manifest.read_text(encoding="utf-8"))
            manifest_sha = m_data.get("manifest_sha256")

        freeze = freeze_evaluation_state(
            spec_sha256=spec.sha256,
            manifest_sha256=manifest_sha,
            require_clean=True,
        )
        out_dir = Path(args.output).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        freeze_fp = out_dir / "freeze.json"
        freeze_fp.write_text(json.dumps(freeze.to_dict(), indent=2), encoding="utf-8")
        print(f"PASS: Evaluation frozen at {freeze.frozen_at}. HEAD: {freeze.evaluation_code_sha}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: Freeze error: {e}", file=sys.stderr)
        return 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate split and write artifact bundle."""
    try:
        spec = load_and_verify_spec(args.spec)
        freeze_record: EvaluationFreezeRecord | None = None
        if args.freeze is not None:
            f_data = json.loads(args.freeze.read_text(encoding="utf-8"))
            freeze_record = EvaluationFreezeRecord.from_dict(f_data)
            verify_freeze_state(freeze_record, spec=spec)

        result = evaluate_split(
            split_name=args.split,
            spec=spec,
            dataset_root=args.dataset_root,
            freeze=freeze_record,
            validation_artifact_dir=args.validation_artifact_dir,
        )

        checksums = write_artifact_bundle(
            output_dir=args.output,
            result=result,
            spec=spec,
            freeze=freeze_record,
        )
        print(f"PASS: {result.task_id} split={result.split} disposition={result.disposition} step={result.disposition_step}")
        print(f"Artifacts written to {args.output} ({len(checksums)} files).")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: Evaluation error: {e}", file=sys.stderr)
        return 1


def cmd_build_dataset(args: argparse.Namespace) -> int:
    """Build dataset partition in dry-run or authorized provider mode."""
    try:
        spec = load_and_verify_spec(args.spec)
        execute_provider = getattr(args, "execute_provider", False) and not getattr(args, "dry_run", False)

        validation_bundle_sha = None
        preholdout_manifest_sha = None
        evaluator_code_sha = None

        if args.split == "holdout":
            if not args.validation_artifact_dir:
                print("FAIL: Holdout acquisition requires --validation-artifact-dir.", file=sys.stderr)
                return 1
            verify_holdout_access_prerequisites(args.validation_artifact_dir, spec)
            val_cs = Path(args.validation_artifact_dir) / "checksums.sha256"
            validation_bundle_sha = sha256_of_file(val_cs)
            # Read preholdout manifest sha and freeze sha
            val_m = json.loads((Path(args.validation_artifact_dir) / "manifest.lock.json").read_text(encoding="utf-8"))
            preholdout_manifest_sha = val_m.get("manifest_sha256")
            val_f = json.loads((Path(args.validation_artifact_dir) / "freeze.json").read_text(encoding="utf-8"))
            evaluator_code_sha = val_f.get("evaluation_code_sha")

        manifest = acquire_dataset_partition(
            dataset_root=args.dataset_root,
            partition=args.split,
            spec=spec,
            execute_provider=execute_provider,
            validation_bundle_sha=validation_bundle_sha,
            preholdout_manifest_sha=preholdout_manifest_sha,
            evaluator_code_sha=evaluator_code_sha,
        )
        mode_str = "PROVIDER ACQUISITION" if execute_provider else "DRY-RUN (NO NETWORK CALLS)"
        print(f"PASS: Dataset partition '{args.split}' completed in {mode_str} mode.")
        print(f"Manifest SHA-256: {manifest.manifest_sha256}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: Dataset acquisition error: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "verify-spec":
        return cmd_verify_spec(args)
    elif args.command == "freeze":
        return cmd_freeze(args)
    elif args.command == "evaluate":
        return cmd_evaluate(args)
    elif args.command == "build-dataset":
        return cmd_build_dataset(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
