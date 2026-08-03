"""Command-line interface for the pattern-similarity validation study."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from tradex.patterns.miner import MINING_UNIVERSE

from .models import StudySpec, ValidationError, load_manifest, load_spec
from .report import run_study, write_study
from .snapshot import create_snapshot


def _date(s: str) -> date:
    return date.fromisoformat(s)


def _default_splits() -> dict[str, dict[str, str]]:
    return {
        "development": {"start": "2018-01-02", "end": "2021-12-31"},
        "validation": {"start": "2022-01-03", "end": "2023-12-29"},
        "holdout": {"start": "2024-01-02", "end": "2026-07-31"},
    }


def _load_splits(path_or_text: str | None) -> dict[str, dict[str, str]]:
    if path_or_text is None:
        return _default_splits()
    p = Path(path_or_text)
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(path_or_text)
    if not isinstance(data, dict):
        raise ValidationError("splits must be a JSON object mapping split name to {start, end}")
    return {name: {"start": s["start"], "end": s["end"]} for name, s in data.items()}


def _split_to_split(split_dict: dict[str, dict[str, str]]) -> dict[str, Any]:
    from .models import Split
    return {name: Split(start=date.fromisoformat(s["start"]), end=date.fromisoformat(s["end"])) for name, s in split_dict.items()}


def _parse_split_arg(text: str) -> dict[str, str]:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        raise ValidationError(f"split argument must be 'YYYY-MM-DD,YYYY-MM-DD'; got {text!r}")
    return {"start": parts[0], "end": parts[1]}


def _build_default_spec(manifest, splits: dict | None = None, research_test_mode: bool = False) -> StudySpec:
    if splits is None:
        splits = _split_to_split(_default_splits())
    return StudySpec(
        tickers=manifest.requested_tickers,
        dataset_name=manifest.dataset_name,
        provider=manifest.provider,
        start_date=manifest.request_start,
        end_date=manifest.request_end,
        splits=splits,
        research_test_mode=research_test_mode,
    )


def _resolve_snapshot_tickers(args: argparse.Namespace) -> list[str]:
    if args.universe:
        if args.universe != "current-mining-universe":
            raise ValidationError(f"--universe must be 'current-mining-universe'; got {args.universe!r}")
        if args.tickers:
            raise ValidationError("--tickers and --universe are mutually exclusive")
        return list(MINING_UNIVERSE)
    if not args.tickers:
        raise ValidationError("--tickers or --universe current-mining-universe is required")
    return [t.strip().upper() for t in args.tickers.split(",")]


def _resolve_snapshot_splits(args: argparse.Namespace) -> dict[str, Any]:
    split_args = [args.development_split, args.validation_split, args.holdout_split]
    if any(split_args):
        if not all(split_args):
            raise ValidationError("--development-split, --validation-split, and --holdout-split must all be provided together")
        return _split_to_split({
            "development": _parse_split_arg(args.development_split),
            "validation": _parse_split_arg(args.validation_split),
            "holdout": _parse_split_arg(args.holdout_split),
        })
    return _split_to_split(_load_splits(args.splits))


def _cmd_snapshot(args: argparse.Namespace) -> int:
    splits = _resolve_snapshot_splits(args)
    tickers = _resolve_snapshot_tickers(args)
    manifest_path = create_snapshot(
        tickers=tickers,
        start=args.start,
        end=args.end,
        output_dir=args.output,
        splits=splits,
        provider=args.provider,
        overwrite=args.overwrite,
        dataset_name=args.dataset_name,
    )
    print(f"Snapshot written to: {manifest_path.parent}")
    print(f"Manifest: {manifest_path}")
    return 0


def _verify_manifest_files(manifest_dir: Path, manifest) -> None:
    """Compare on-disk file hashes to the manifest. Raise on mismatch."""
    from .snapshot import _sha256_file
    for entry in manifest.entries:
        if entry.failure or not entry.path:
            continue
        path = manifest_dir / entry.path
        if not path.exists():
            raise ValidationError(f"manifest entry missing on disk: {path}")
        actual = _sha256_file(path)
        if actual != entry.sha256:
            raise ValidationError(f"checksum mismatch for {entry.ticker}: expected {entry.sha256}, got {actual}")


def _cmd_evaluate(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise ValidationError(f"manifest not found: {manifest_path}")
    manifest_dir = manifest_path.parent
    manifest = load_manifest(manifest_path)
    _verify_manifest_files(manifest_dir, manifest)

    if args.spec:
        spec = load_spec(args.spec, research_test_mode=args.research_test)
    else:
        spec = _build_default_spec(manifest, manifest.splits, research_test_mode=args.research_test)

    # Confirm deterministic fingerprint build is possible.
    if "development" not in spec.splits:
        raise ValidationError("development split is required in the study spec")

    from .snapshot import load_snapshot
    _, bars = load_snapshot(manifest_path)

    study = run_study(manifest, bars, spec)
    artifacts = write_study(study, args.output, overwrite=args.overwrite)
    print(f"Study artifacts written to: {args.output}")
    print(f"Promotion decision: {study.promotion_decision.classification}")
    print(f"Files: {', '.join(sorted(artifacts.keys()))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tradex.research.pattern_validation",
        description="Validate the pattern matcher using locked, point-in-time, reproducible research.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # snapshot
    snap = subparsers.add_parser(
        "snapshot",
        help="Build an offline daily-OHLCV snapshot for a universe. No network required if --provider is omitted and a fetch_fn is injected; default requires network.",
    )
    snap.add_argument("--tickers", default=None, help="Comma-separated ticker list (e.g. AAPL,MSFT,NVDA). Mutually exclusive with --universe.")
    snap.add_argument("--universe", default=None, help="Use the exact ordered MINING_UNIVERSE; value must be 'current-mining-universe'")
    snap.add_argument("--start", type=_date, required=True, help="Start date ISO-8601 (e.g. 2018-01-02)")
    snap.add_argument("--end", type=_date, required=True, help="End date ISO-8601 (e.g. 2026-07-31)")
    snap.add_argument("--output", required=True, help="Output snapshot directory")
    snap.add_argument("--provider", default=None, help="Data provider (e.g. schwab, yahoo). Default uses DATA_PROVIDER or yahoo.")
    snap.add_argument("--splits", default=None, help="JSON file or inline JSON mapping split name to {start, end}")
    snap.add_argument("--development-split", default=None, help="Development split as 'YYYY-MM-DD,YYYY-MM-DD'")
    snap.add_argument("--validation-split", default=None, help="Validation split as 'YYYY-MM-DD,YYYY-MM-DD'")
    snap.add_argument("--holdout-split", default=None, help="Holdout split as 'YYYY-MM-DD,YYYY-MM-DD'")
    snap.add_argument("--dataset-name", default="pattern-similarity-validation")
    snap.add_argument("--overwrite", action="store_true", help="Replace an existing snapshot directory")
    snap.set_defaults(func=_cmd_snapshot)

    # evaluate
    eval_p = subparsers.add_parser(
        "evaluate",
        help="Evaluate a snapshot offline. Requires no network, no credentials, no .env, and no fingerprints.db.",
    )
    eval_p.add_argument("--manifest", required=True, help="Path to the snapshot manifest.lock.json")
    eval_p.add_argument("--output", required=True, help="Output directory for study artifacts")
    eval_p.add_argument("--spec", default=None, help="Optional study_spec.lock.json; default spec is derived from the manifest")
    eval_p.add_argument("--research-test", action="store_true", help="Skip locked-contract validation for synthetic/test specs")
    eval_p.add_argument("--overwrite", action="store_true", help="Replace an existing output directory")
    eval_p.set_defaults(func=_cmd_evaluate)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValidationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
