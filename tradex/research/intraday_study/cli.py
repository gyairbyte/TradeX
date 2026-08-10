"""Deterministic CLI for the INTRA-001D locked real-data study."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tradex.research.intraday_engine.models import as_json_dict
from tradex.research.intraday_engine.spec import IntradaySpec, load_spec

from .artifacts import (
    sha256_of_file,
    write_artifact_bundle,
    write_run_artifact_manifest_and_checksums,
)
from .freeze import (
    FreezeError,
    freeze_evaluation_code,
    freeze_record_to_dict,
    verify_frozen_evaluation_code,
)
from .manifest import (
    SymbolMonth,
    load_dataset_plan,
    verify_dataset_bundle,
    verify_dataset_integrity,
    verify_dataset_plan_file,
)
from .split import SplitName
from .study import run_split


class StudyCLIError(Exception):
    """User-facing error from the CLI."""


def _safe_json_dump(data: Any, path: Path) -> None:
    """Write JSON with no NaN/Infinity and stable key ordering."""
    path.write_text(
        json.dumps(
            data,
            indent=2,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_spec_path() -> Path:
    return _repo_root() / "docs/research/specs/INTRA-001-v1.json"


def _default_dataset_plan_path(dataset_root: Path) -> Path:
    return dataset_root / "dataset_plan.lock.json"


def _parse_generated_at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _dataset_id_from_root(dataset_root: Path) -> str:
    state_path = dataset_root / "dataset_state.json"
    if state_path.is_file():
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data.get("dataset_id", "INTRA-001B-DATASET-V1")
    return "INTRA-001B-DATASET-V1"


def _manifest_records_for_symbol_months(symbol_months: list[SymbolMonth]) -> list[dict[str, Any]]:
    """Convert SymbolMonth objects into the dict form expected by verify_dataset_integrity."""
    return [
        {
            "manifest_id": sm.manifest_id,
            "symbol": sm.symbol,
            "effective_month": sm.effective_month,
            "relative_path": sm.relative_path,
            "sha256": sm.sha256,
            "file_size_bytes": sm.file_size_bytes,
        }
        for sm in symbol_months
    ]


def _hash_verify_split(
    dataset_root: Path,
    symbol_months: list[SymbolMonth],
) -> int:
    """Hash-verify all symbol-month files for a split and return the count verified."""
    records = _manifest_records_for_symbol_months(symbol_months)
    verify_dataset_integrity(dataset_root, records)
    return len(records)


def _holdout_status_path(output_dir: Path) -> Path:
    return output_dir / "holdout_status.json"


def _read_holdout_status(output_dir: Path) -> dict[str, Any] | None:
    p = _holdout_status_path(output_dir)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _write_holdout_status(
    output_dir: Path,
    *,
    status: str,
    access_count: int,
    parse_count: int,
    reason: str,
    files_hash_verified_count: int,
) -> None:
    data = {
        "schema_version": "1.0",
        "status": status,
        "access_count": access_count,
        "parse_count": parse_count,
        "reason": reason,
        "files_hash_verified_count": files_hash_verified_count,
    }
    p = _holdout_status_path(output_dir)
    p.write_text(
        json.dumps(data, indent=2, allow_nan=False, sort_keys=True),
        encoding="utf-8",
    )


def _write_split_artifacts(
    result: Any,
    split: SplitName,
    output_dir: Path,
    spec: IntradaySpec,
    *,
    dataset_id: str,
    freeze_record: Any | None,
    manifest_lock_path: Path,
    universe_manifest_path: Path,
    data_quality_path: Path,
    spec_path: Path,
    holdout_status: str,
    production_promotion_eligible: bool,
    monthly_rejection_summary: dict[str, dict[str, Any]] | None,
    runtime_seconds: float | None = None,
) -> dict[str, Any]:
    """Run the artifact writer for one split and return a split summary."""
    split_dir = output_dir / split
    write_artifact_bundle(
        result,
        split_dir,
        split=split,
        dataset_id=dataset_id,
        spec=spec,
        freeze_record=freeze_record,
        manifest_lock_path=manifest_lock_path,
        universe_manifest_path=universe_manifest_path,
        data_quality_path=data_quality_path,
        spec_path=spec_path,
        holdout_status=holdout_status,
        production_promotion_eligible=production_promotion_eligible,
        monthly_rejection_summary=monthly_rejection_summary,
        runtime_seconds=runtime_seconds,
    )
    return {
        "split": split,
        "disposition": result.outcome.disposition if result.outcome else None,
        "reason": result.outcome.reason if result.outcome else None,
        "evidence_eligible": result.evidence_eligible,
        "path": split,
    }


def _cmd_run(args: argparse.Namespace) -> int:
    start_time = time.perf_counter()
    dataset_root = Path(args.dataset_root).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    if args.manifest_lock:
        manifest_lock_path = Path(args.manifest_lock).expanduser().resolve()
    else:
        json_lock = dataset_root / "manifest.lock.json"
        csv_lock = dataset_root / "ohlcv" / "ohlcv_manifest.csv"
        manifest_lock_path = json_lock if json_lock.is_file() else csv_lock
    spec_path = Path(args.spec).expanduser().resolve()

    spec, _ = load_spec(spec_path)
    generated_at = _parse_generated_at(args.generated_at)

    universe_manifest_path = dataset_root / "universe" / "universe_manifest.csv"
    data_quality_path = dataset_root / "ohlcv" / "data_quality.csv"
    dataset_plan_path = _default_dataset_plan_path(dataset_root)
    repo_root = _repo_root()

    # Phase 0: verify dataset plan hash against the committed locked plan.
    committed_plan_path = repo_root / "docs/research/specs/INTRA-001B-dataset-v1.json"
    if not committed_plan_path.is_file():
        raise StudyCLIError("committed INTRA-001B-dataset-v1.json not found")
    expected_plan_sha = sha256_of_file(committed_plan_path)
    verify_dataset_plan_file(dataset_plan_path, expected_sha256=expected_plan_sha)
    dataset_plan = load_dataset_plan(dataset_plan_path)
    amendment_sha = dataset_plan.get("data_sufficiency_amendment", {}).get("sha256")
    dataset_plan_sha = sha256_of_file(dataset_plan_path)

    # Phase 1: verify the entire locked dataset bundle (set equality, identity,
    # path containment, split labels, provider contract flags) and file hashes.
    verified = verify_dataset_bundle(dataset_root, expected_count=args.expected_symbol_months)
    verify_dataset_integrity(
        dataset_root,
        _manifest_records_for_symbol_months(verified.symbol_months),
    )

    # Holdout files are hash-verified before validation, regardless of whether
    # validation later permits parsing them.
    holdout_symbol_months = verified.by_split.get("holdout", [])
    holdout_files_hash_verified_count = _hash_verify_split(
        dataset_root, holdout_symbol_months
    )

    dataset_id = _dataset_id_from_root(dataset_root)

    # Phase 2: development diagnostics (not evidence-eligible).
    dev_start = time.perf_counter()
    dev_symbol_months = verified.by_split.get("development", [])
    dev_result, _, dev_monthly = run_split(
        dataset_root,
        "development",
        spec,
        generated_at,
        symbol_months=dev_symbol_months,
        evidence_eligible=False,
    )
    dev_result.evidence_eligible = False
    dev_runtime = time.perf_counter() - dev_start
    dev_summary = _write_split_artifacts(
        dev_result,
        "development",
        output_dir,
        spec,
        dataset_id=dataset_id,
        freeze_record=None,
        manifest_lock_path=manifest_lock_path,
        universe_manifest_path=universe_manifest_path,
        data_quality_path=data_quality_path,
        spec_path=spec_path,
        holdout_status="not_yet_determined",
        production_promotion_eligible=False,
        monthly_rejection_summary=dev_monthly,
        runtime_seconds=dev_runtime,
    )

    # Phase 3: freeze evaluation code.  A dirty tracked worktree aborts validation
    # and holdout because the frozen-code guarantee cannot be made.
    freeze_start = time.perf_counter()
    freeze_record = freeze_evaluation_code(
        repo_root,
        spec.sha256,
        amendment_sha256=amendment_sha,
        dataset_plan_sha256=dataset_plan_sha,
    )
    if not freeze_record.repository_clean:
        raise StudyCLIError(
            "evaluation-code worktree is not clean; validation and holdout aborted"
        )
    verify_frozen_evaluation_code(repo_root, freeze_record)
    freeze_runtime = time.perf_counter() - freeze_start

    # Phase 4: validation.
    val_start = time.perf_counter()
    val_symbol_months = verified.by_split.get("validation", [])
    val_result, _, val_monthly = run_split(
        dataset_root,
        "validation",
        spec,
        generated_at,
        symbol_months=val_symbol_months,
        evidence_eligible=True,
    )
    val_result.evidence_eligible = (
        val_result.outcome is not None and val_result.outcome.disposition == "supported"
    )
    val_runtime = time.perf_counter() - val_start

    # Phase 5: holdout firewall.
    holdout_result = None
    holdout_monthly = None
    holdout_access_count = 0
    holdout_parse_count = 0
    holdout_disposition = None

    if val_result.outcome is None or val_result.outcome.disposition != "supported":
        holdout_status = (
            f"not_run_validation_{val_result.outcome.disposition if val_result.outcome else 'none'}"
        )
        _write_holdout_status(
            output_dir,
            status="not_run",
            access_count=0,
            parse_count=0,
            reason=holdout_status,
            files_hash_verified_count=holdout_files_hash_verified_count,
        )
    else:
        existing = _read_holdout_status(output_dir)
        if existing and existing.get("status") == "completed":
            raise StudyCLIError("holdout already completed in this output directory; cannot rerun")
        holdout_start = time.perf_counter()
        verify_frozen_evaluation_code(repo_root, freeze_record)
        holdout_symbol_months = verified.by_split.get("holdout", [])
        holdout_result, _, holdout_monthly = run_split(
            dataset_root,
            "holdout",
            spec,
            generated_at,
            symbol_months=holdout_symbol_months,
            evidence_eligible=True,
        )
        holdout_result.evidence_eligible = (
            holdout_result.outcome is not None
            and holdout_result.outcome.disposition == "supported"
        )
        holdout_disposition = holdout_result.outcome.disposition if holdout_result.outcome else None
        holdout_access_count = 1
        holdout_parse_count = 1
        holdout_runtime = time.perf_counter() - holdout_start
        holdout_status = f"completed_disposition_{holdout_disposition}"
        _write_holdout_status(
            output_dir,
            status="completed",
            access_count=holdout_access_count,
            parse_count=holdout_parse_count,
            reason=holdout_status,
            files_hash_verified_count=holdout_files_hash_verified_count,
        )

    production_promotion_eligible = (
        val_result.outcome is not None
        and val_result.outcome.disposition == "supported"
        and holdout_result is not None
        and holdout_result.outcome is not None
        and holdout_result.outcome.disposition == "supported"
        and freeze_record.repository_clean
    )

    final_disposition = (
        holdout_result.outcome.disposition
        if holdout_result and holdout_result.outcome
        else (val_result.outcome.disposition if val_result.outcome else None)
    )

    # Validation report is written only after the holdout decision is final so it
    # can accurately lead with holdout status and production eligibility.
    val_summary = _write_split_artifacts(
        val_result,
        "validation",
        output_dir,
        spec,
        dataset_id=dataset_id,
        freeze_record=freeze_record,
        manifest_lock_path=manifest_lock_path,
        universe_manifest_path=universe_manifest_path,
        data_quality_path=data_quality_path,
        spec_path=spec_path,
        holdout_status=holdout_status,
        production_promotion_eligible=production_promotion_eligible,
        monthly_rejection_summary=val_monthly,
        runtime_seconds=val_runtime,
    )

    holdout_summary: dict[str, Any] = {
        "split": "holdout",
        "disposition": holdout_disposition,
        "reason": holdout_status,
        "evidence_eligible": (
            holdout_result.evidence_eligible if holdout_result else False
        ),
        "path": "holdout" if holdout_result else None,
        "access_count": holdout_access_count,
        "parse_count": holdout_parse_count,
    }

    if holdout_result is not None:
        _write_split_artifacts(
            holdout_result,
            "holdout",
            output_dir,
            spec,
            dataset_id=dataset_id,
            freeze_record=freeze_record,
            manifest_lock_path=manifest_lock_path,
            universe_manifest_path=universe_manifest_path,
            data_quality_path=data_quality_path,
            spec_path=spec_path,
            holdout_status=holdout_status,
            production_promotion_eligible=production_promotion_eligible,
            monthly_rejection_summary=holdout_monthly,
            runtime_seconds=holdout_runtime,
        )

    total_runtime = time.perf_counter() - start_time
    summary = {
        "study_id": "INTRA-001D",
        "generated_at": generated_at.isoformat(),
        "spec_sha256": spec.sha256,
        "dataset_id": dataset_id,
        "dataset_plan_sha256": dataset_plan_sha,
        "manifest_lock_sha256": verified.manifest_sha256,
        "freeze": freeze_record_to_dict(freeze_record),
        "freeze_verification_seconds": freeze_runtime,
        "holdout": {
            "status": holdout_status,
            "access_count": holdout_access_count,
            "parse_count": holdout_parse_count,
            "files_hash_verified_count": holdout_files_hash_verified_count,
        },
        "splits": [dev_summary, val_summary, holdout_summary],
        "final_disposition": final_disposition,
        "production_promotion_eligible": production_promotion_eligible,
        "no_provider_calls": True,
        "runtime_seconds": total_runtime,
    }
    _safe_json_dump(summary, output_dir / "study_summary.json")
    print(json.dumps(as_json_dict(summary), indent=2, allow_nan=False))

    write_run_artifact_manifest_and_checksums(output_dir)
    return 0


def _cmd_freeze(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    spec_path = Path(args.spec).expanduser().resolve()
    spec, _ = load_spec(spec_path)
    record = freeze_evaluation_code(repo_root, spec.sha256)
    out = Path(args.output).expanduser().resolve() if args.output else repo_root / ".intra001d_freeze.json"
    _safe_json_dump(freeze_record_to_dict(record), out)
    print(json.dumps(freeze_record_to_dict(record), indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tradex.research.intraday_study",
        description="Run the locked INTRA-001D real-data intraday study.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run the full dev/val/holdout pipeline.")
    run_parser.add_argument("--dataset-root", required=True, help="Root of INTRA-001B-DATASET-V1.")
    run_parser.add_argument("--output", required=True, help="Output directory for safe artifacts.")
    run_parser.add_argument(
        "--manifest-lock",
        default=None,
        help="Path to manifest.lock.json or ohlcv_manifest.csv. Defaults to dataset_root/manifest.lock.json if present, otherwise dataset_root/ohlcv/ohlcv_manifest.csv.",
    )
    run_parser.add_argument(
        "--spec",
        default=str(_default_spec_path()),
        help="Path to INTRA-001-v1.json.",
    )
    run_parser.add_argument(
        "--generated-at",
        required=True,
        help="Fixed UTC timestamp in ISO 8601 format (e.g., 2026-08-01T00:00:00+00:00).",
    )
    run_parser.add_argument(
        "--expected-symbol-months",
        type=int,
        default=756,
        help="Expected number of symbol-months in the verified dataset bundle.",
    )

    freeze_parser = sub.add_parser("freeze", help="Record evaluation-code freeze only.")
    freeze_parser.add_argument("--spec", default=str(_default_spec_path()))
    freeze_parser.add_argument("--output", help="Path to write freeze record JSON.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "freeze":
            return _cmd_freeze(args)
    except (StudyCLIError, FreezeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
