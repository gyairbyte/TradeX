"""Command-line interface for the DAYTRADE-001 reversal study engine."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from tradex.research.intraday_dataset.alpaca_client import DatasetAlpacaClient

from .artifacts import write_artifact_bundle
from .dataset import (
    DatasetPaginationLimitError,
    DatasetSecurityError,
    DaytradeDatasetManifest,
    acquire_dataset_partition,
    load_private_dataset,
    validate_dataset_root,
)
from .freeze import (
    EvaluationFreezeRecord,
    FreezeError,
    freeze_evaluation_state,
    verify_freeze_state,
    verify_manifest_dataset_integrity,
)
from .models import DataQualityReport, DaytradeSession
from .spec import load_and_verify_spec
from .study import (
    HoldoutAccessDeniedError,
    evaluate_split,
    load_and_evaluate_holdout,
    verify_holdout_access_prerequisites,
)


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
    p_freeze.add_argument("--manifest", type=Path, default=None, help="Path to manifest.lock.json")
    p_freeze.add_argument("--dataset-root", type=Path, default=None, help="Path to dataset root")
    p_freeze.add_argument("--output", type=Path, required=True, help="Output directory for freeze.json (must be outside repo)")

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
    p_eval.add_argument("--freeze", type=Path, default=None, help="Path to freeze.json (required for validation)")
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
    p_build.add_argument(
        "--split",
        choices=["preholdout", "holdout"],
        default="preholdout",
        help="Dataset partition to acquire (preholdout or holdout)",
    )
    p_build.add_argument("--dry-run", action="store_true", help="Dry-run verification only")
    p_build.add_argument("--execute-provider", action="store_true", help="Authorize execution against provider adapter")
    p_build.add_argument(
        "--validation-artifact-dir",
        type=Path,
        default=None,
        help="Required when --split holdout to prove validation support",
    )

    return parser


def cmd_verify_spec(args: argparse.Namespace) -> int:
    """Verify locked specification hash."""
    spec = load_and_verify_spec(args.spec)
    print(f"PASS: {spec.task_id} specification SHA-256 verified: {spec.sha256}")
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    """Freeze current evaluator state and output freeze.json."""
    spec = load_and_verify_spec(args.spec)

    out_dir = args.output
    if not out_dir:
        print("ERROR: --output directory is required for freeze.", file=sys.stderr)
        return 1

    try:
        validate_dataset_root(out_dir)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    manifest_path: Path | None = None
    if args.manifest:
        manifest_path = Path(args.manifest)
    elif args.dataset_root:
        p_pre = Path(args.dataset_root) / "preholdout" / "manifest.lock.json"
        p_direct = Path(args.dataset_root) / "manifest.lock.json"
        if p_pre.is_file():
            manifest_path = p_pre
        elif p_direct.is_file():
            manifest_path = p_direct

    if not manifest_path or not manifest_path.is_file():
        print(
            "ERROR: Freeze must be dataset-bound. Provide --manifest or --dataset-root pointing to valid manifest.lock.json.",
            file=sys.stderr,
        )
        return 1

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = DaytradeDatasetManifest.from_dict(manifest_data)
        manifest.validate_against_spec(spec)
        verify_manifest_dataset_integrity(manifest_data, manifest_path.parent)
    except (DatasetSecurityError, FreezeError, json.JSONDecodeError, OSError, ValueError) as e:
        print(f"ERROR: Failed to validate manifest against spec: {e}", file=sys.stderr)
        return 1

    try:
        record = freeze_evaluation_state(
            spec_sha256=spec.sha256,
            manifest_sha256=manifest.manifest_sha256,
            require_clean=True,
        )
    except FreezeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    freeze_file = out_dir / "freeze.json"
    freeze_file.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    print(f"PASS: Evaluation state frozen at HEAD {record.evaluation_code_sha}")
    print(f"Wrote: {freeze_file}")
    return 0


def cmd_build_dataset(args: argparse.Namespace) -> int:
    """Acquire private dataset partition using locked Alpaca client parameters."""
    validate_dataset_root(args.dataset_root)
    spec = load_and_verify_spec(args.spec)

    evaluator_code_sha: str | None = None
    if args.split == "holdout":
        if not args.validation_artifact_dir:
            print("ERROR: --validation-artifact-dir is required when acquiring holdout.", file=sys.stderr)
            return 1
        try:
            verify_holdout_access_prerequisites(args.validation_artifact_dir, spec)
        except HoldoutAccessDeniedError as e:
            print(f"HOLDOUT ACCESS BLOCKED: {e}", file=sys.stderr)
            return 2

        # Verify preholdout manifest lineage
        pre_file = Path(args.dataset_root) / "preholdout" / "manifest.lock.json"
        if not pre_file.is_file():
            print(f"ERROR: Preholdout manifest not found at {pre_file}", file=sys.stderr)
            return 1
        val_freeze_file = Path(args.validation_artifact_dir) / "freeze.json"
        if val_freeze_file.is_file():
            v_freeze = json.loads(val_freeze_file.read_text(encoding="utf-8"))
            evaluator_code_sha = v_freeze.get("evaluation_code_sha")

    if not args.execute_provider and not args.dry_run:
        print(
            "ERROR: Live provider dataset acquisition requires --execute-provider flag.\n"
            "DAYTRADE-001C1 must make zero network/provider calls.\n"
            "Execution belongs to future DAYTRADE-001C2.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print("PASS: Dry-run dataset validation succeeded (0 network calls made).")
        return 0

    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    if not api_key or not secret_key:
        print("ERROR: ALPACA_API_KEY and ALPACA_SECRET_KEY must be configured.", file=sys.stderr)
        return 1

    try:
        client = DatasetAlpacaClient(api_key=api_key, secret_key=secret_key, max_retries=1)
        _, summary = acquire_dataset_partition(
            spec=spec,
            dataset_root=args.dataset_root,
            partition=args.split,
            client=client,
            validation_bundle_dir=args.validation_artifact_dir if args.split == "holdout" else None,
            evaluator_code_sha=evaluator_code_sha,
        )
    except (DatasetSecurityError, DatasetPaginationLimitError, OSError, ValueError) as e:
        print(f"ERROR: Dataset acquisition failed: {e}", file=sys.stderr)
        return 1

    print(f"PASS: Acquired partition {args.split} for {summary['total_symbols']} symbols.")
    print(f"Requests: {summary['total_requests']}, Pages: {summary['total_pages']}, Retries: {summary['total_retries']}")
    print(f"Manifest written to: {summary['manifest_path']} (SHA: {summary['manifest_sha256']})")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate a specific split."""
    spec = load_and_verify_spec(args.spec)

    freeze_record: EvaluationFreezeRecord | None = None
    if args.freeze:
        if not args.freeze.is_file():
            print(f"ERROR: Freeze file not found: {args.freeze}", file=sys.stderr)
            return 1
        try:
            freeze_data = json.loads(args.freeze.read_text(encoding="utf-8"))
            freeze_record = EvaluationFreezeRecord.from_dict(freeze_data)
            verify_freeze_state(freeze_record, require_clean=True, require_manifest=True)
        except (FreezeError, OSError, ValueError, json.JSONDecodeError) as e:
            print(f"ERROR: Freeze verification failed: {e}", file=sys.stderr)
            return 1

    if args.split == "validation":
        if not freeze_record:
            print("ERROR: --freeze is required when evaluating validation split.", file=sys.stderr)
            return 1
        if freeze_record.spec_sha256 != spec.sha256:
            print(
                f"ERROR: Freeze spec SHA mismatch: expected {spec.sha256}, got {freeze_record.spec_sha256}",
                file=sys.stderr,
            )
            return 1

    sessions: list[DaytradeSession] = []
    dq_reports: list[DataQualityReport] | None = None
    manifest_data: dict[str, Any] | None = None
    manifest_sha256: str | None = None

    if args.split == "holdout":
        if not args.validation_artifact_dir:
            print(
                "ERROR: --validation-artifact-dir is required when evaluating holdout.",
                file=sys.stderr,
            )
            return 1
        if not args.dataset_root:
            print("ERROR: --dataset-root is required when evaluating holdout.", file=sys.stderr)
            return 1

        def holdout_loader() -> tuple[list[DaytradeSession], list[DataQualityReport], str | None]:
            nonlocal manifest_data, manifest_sha256
            m_file = Path(args.dataset_root) / "holdout" / "manifest.lock.json"
            if m_file.is_file():
                manifest_data = json.loads(m_file.read_text(encoding="utf-8"))
                manifest_sha256 = manifest_data.get("manifest_sha256")
            s, q = load_private_dataset(
                dataset_root=args.dataset_root,
                split_name="holdout",
                spec=spec,
                validation_artifact_dir=args.validation_artifact_dir,
            )
            return s, q, manifest_sha256

        try:
            result = load_and_evaluate_holdout(
                validation_artifact_dir=args.validation_artifact_dir,
                spec=spec,
                holdout_loader=holdout_loader,
            )
        except HoldoutAccessDeniedError as e:
            print(f"HOLDOUT ACCESS BLOCKED: {e}", file=sys.stderr)
            return 2
        except (DatasetSecurityError, OSError, ValueError) as e:
            print(f"ERROR: Failed to load holdout dataset: {e}", file=sys.stderr)
            return 1

        val_freeze_file = Path(args.validation_artifact_dir) / "freeze.json"
        if val_freeze_file.is_file() and not freeze_record:
            try:
                freeze_data = json.loads(val_freeze_file.read_text(encoding="utf-8"))
                freeze_record = EvaluationFreezeRecord.from_dict(freeze_data)
            except (FreezeError, OSError, ValueError, json.JSONDecodeError):
                freeze_record = None
    else:
        if args.dataset_root:
            try:
                validate_dataset_root(args.dataset_root)
                sessions, dq_reports = load_private_dataset(
                    dataset_root=args.dataset_root,
                    split_name=args.split,
                    spec=spec,
                )
                m_file = Path(args.dataset_root) / "preholdout" / "manifest.lock.json"
                if m_file.is_file():
                    manifest_data = json.loads(m_file.read_text(encoding="utf-8"))
                    manifest_sha256 = manifest_data.get("manifest_sha256")
            except (DatasetSecurityError, json.JSONDecodeError, OSError, ValueError) as e:
                print(f"ERROR: Failed to load dataset from {args.dataset_root}: {e}", file=sys.stderr)
                return 1

        if (
            args.split == "validation"
            and freeze_record
            and manifest_sha256
            and freeze_record.manifest_sha256 != manifest_sha256
        ):
            print(
                f"ERROR: Freeze manifest SHA '{freeze_record.manifest_sha256}' mismatch with dataset manifest '{manifest_sha256}'",
                file=sys.stderr,
            )
            return 1

        result = evaluate_split(
            split_name=args.split,
            sessions=sessions,
            spec=spec,
            data_quality_reports=dq_reports,
            freeze_record=freeze_record,
            manifest_sha256=manifest_sha256,
        )

    out_dir = args.output
    out_dir.mkdir(parents=True, exist_ok=True)
    write_artifact_bundle(
        output_dir=out_dir,
        result=result,
        spec=spec,
        freeze_record=freeze_record,
        manifest_data=manifest_data,
        data_quality_reports=dq_reports,
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
