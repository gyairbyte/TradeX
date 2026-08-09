"""Deterministic CLI for the INTRA-001D locked real-data study."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tradex.research.intraday_engine.spec import IntradaySpec, load_spec

from .artifacts import write_artifact_bundle
from .freeze import FreezeError, freeze_evaluation_code, freeze_record_to_dict
from .manifest import (
    SymbolMonth,
    get_symbol_months_for_split,
    load_data_quality,
    load_dataset_plan,
    load_manifest_lock,
    verify_dataset_integrity,
)
from .split import SplitName
from .study import run_split


class StudyCLIError(Exception):
    """User-facing error from the CLI."""


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


def _verify_split_symbol_months(
    dataset_root: Path,
    manifest_lock_path: Path,
    split: SplitName,
) -> list[SymbolMonth]:
    """Verify file integrity for the symbol-months in a split."""
    manifest_records = load_manifest_lock(manifest_lock_path)
    # Filter to the requested split using the data_quality split column.
    dq_path = dataset_root / "ohlcv" / "data_quality.csv"
    dq_df = load_data_quality(dq_path)
    split_ids = {
        (row["symbol"], row["effective_month"])
        for _, row in dq_df[dq_df["split"] == split].iterrows()
    }
    records = [
        rec
        for rec in manifest_records
        if (rec.get("symbol"), rec.get("effective_month")) in split_ids
    ]
    verify_dataset_integrity(dataset_root, records)
    return get_symbol_months_for_split(dq_df, split)


def _run_split_and_write(
    dataset_root: Path,
    split: SplitName,
    output_dir: Path,
    spec: IntradaySpec,
    generated_at: datetime,
    freeze_record: Any | None,
    evidence_eligible: bool,
    manifest_lock_path: Path,
    universe_manifest_path: Path,
    data_quality_path: Path,
    spec_path: Path,
) -> dict[str, Any]:
    """Run one split and write its safe artifact bundle."""
    symbol_months = _verify_split_symbol_months(dataset_root, manifest_lock_path, split)
    result, _ = run_split(
        dataset_root,
        split,
        spec,
        generated_at,
        evidence_eligible=evidence_eligible,
        symbol_months=symbol_months,
    )

    # Evidence eligibility is tied to outcome and split.
    if split == "development":
        result.evidence_eligible = False
    elif result.outcome is not None:
        result.evidence_eligible = result.outcome.disposition == "supported"
    else:
        result.evidence_eligible = False

    split_dir = output_dir / split
    write_artifact_bundle(
        result,
        split_dir,
        split=split,
        dataset_id=_dataset_id_from_root(dataset_root),
        freeze_record=freeze_record,
        manifest_lock_path=manifest_lock_path,
        universe_manifest_path=universe_manifest_path,
        data_quality_path=data_quality_path,
        spec_path=spec_path,
    )
    return {
        "split": split,
        "disposition": result.outcome.disposition if result.outcome else None,
        "reason": result.outcome.reason if result.outcome else None,
        "evidence_eligible": result.evidence_eligible,
        "path": str(split_dir),
    }


def _cmd_run(args: argparse.Namespace) -> int:
    dataset_root = Path(args.dataset_root).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    manifest_lock_path = Path(args.manifest_lock).expanduser().resolve()
    spec_path = Path(args.spec).expanduser().resolve()

    spec, _ = load_spec(spec_path)
    generated_at = _parse_generated_at(args.generated_at)

    universe_manifest_path = dataset_root / "universe" / "universe_manifest.csv"
    data_quality_path = dataset_root / "ohlcv" / "data_quality.csv"
    dataset_plan_path = _default_dataset_plan_path(dataset_root)

    dataset_plan = load_dataset_plan(dataset_plan_path)
    amendment_sha = dataset_plan.get("data_sufficiency_amendment", {}).get("sha256")
    dataset_plan_sha = None
    if dataset_plan_path.is_file():
        import hashlib

        dataset_plan_sha = hashlib.sha256(dataset_plan_path.read_bytes()).hexdigest()

    repo_root = _repo_root()

    # Phase 2: development diagnostics.
    dev_result = _run_split_and_write(
        dataset_root,
        "development",
        output_dir,
        spec,
        generated_at,
        freeze_record=None,
        evidence_eligible=False,
        manifest_lock_path=manifest_lock_path,
        universe_manifest_path=universe_manifest_path,
        data_quality_path=data_quality_path,
        spec_path=spec_path,
    )

    # Phase 3: freeze evaluation code before validation.
    freeze_record = freeze_evaluation_code(
        repo_root,
        spec.sha256,
        amendment_sha256=amendment_sha,
        dataset_plan_sha256=dataset_plan_sha,
    )
    if not freeze_record.repository_clean:
        print(
            "warning: worktree is not clean at evaluation freeze; "
            "validation/holdout results cannot be evidence-eligible.",
            file=sys.stderr,
        )

    # Phase 4: validation.
    val_result = _run_split_and_write(
        dataset_root,
        "validation",
        output_dir,
        spec,
        generated_at,
        freeze_record=freeze_record,
        evidence_eligible=True,
        manifest_lock_path=manifest_lock_path,
        universe_manifest_path=universe_manifest_path,
        data_quality_path=data_quality_path,
        spec_path=spec_path,
    )

    # Phase 5: holdout firewall.
    if val_result["disposition"] != "supported":
        holdout_result = {
            "split": "holdout",
            "disposition": None,
            "reason": f"not_run_validation_{val_result['disposition']}",
            "path": None,
        }
    else:
        holdout_result = _run_split_and_write(
            dataset_root,
            "holdout",
            output_dir,
            spec,
            generated_at,
            freeze_record=freeze_record,
            evidence_eligible=True,
            manifest_lock_path=manifest_lock_path,
            universe_manifest_path=universe_manifest_path,
            data_quality_path=data_quality_path,
            spec_path=spec_path,
        )

    production_promotion_eligible = (
        val_result["disposition"] == "supported"
        and holdout_result.get("disposition") == "supported"
        and freeze_record.repository_clean
        and freeze_record.amendment_sha256 is not None
    )

    summary = {
        "study_id": "INTRA-001D",
        "generated_at": generated_at.isoformat(),
        "spec_sha256": spec.sha256,
        "dataset_id": _dataset_id_from_root(dataset_root),
        "manifest_lock_sha256": None,
        "freeze": freeze_record_to_dict(freeze_record),
        "splits": [dev_result, val_result, holdout_result],
        "final_disposition": holdout_result.get("disposition") or val_result["disposition"],
        "production_promotion_eligible": production_promotion_eligible,
        "no_provider_calls": True,
    }
    if manifest_lock_path.is_file():
        import hashlib

        summary["manifest_lock_sha256"] = hashlib.sha256(
            manifest_lock_path.read_bytes()
        ).hexdigest()

    (output_dir / "study_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


def _cmd_freeze(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    spec_path = Path(args.spec).expanduser().resolve()
    spec, _ = load_spec(spec_path)
    record = freeze_evaluation_code(repo_root, spec.sha256)
    out = Path(args.output).expanduser().resolve() if args.output else repo_root / ".intra001d_freeze.json"
    out.write_text(json.dumps(freeze_record_to_dict(record), indent=2), encoding="utf-8")
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
        default=str(_repo_root() / "docs/research/artifacts/INTRA-001B-DATASET-V1/2026-08-09-014844/manifest.lock.json"),
        help="Path to manifest.lock.json.",
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
