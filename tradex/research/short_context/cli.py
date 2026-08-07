"""Command-line interface for the short-term market-context research study."""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date
from pathlib import Path

from tradex.research.score_validation.cleaning import (
    load_ingestion_policy,
    verify_snapshot_sidecars,
)
from tradex.research.score_validation.models import ScoreValidationConfig
from tradex.research.score_validation.snapshot import create_snapshot
from tradex.research.short_context.report import run_study
from tradex.research.short_context.spec import load_spec


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date {value!r}: {exc}") from exc


def _parse_split(value: str) -> tuple[str, str]:
    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Split must be 'start,end'; got {value!r}")
    return (parts[0].strip(), parts[1].strip())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tradex.research.short_context",
        description="Research tools for short-term market-context studies.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snap = subparsers.add_parser(
        "snapshot",
        help="Fetch and lock a manifest containing targets and required proxies.",
    )
    snap.add_argument("--context-spec", required=True, help="Path to context-study spec JSON")
    snap.add_argument("--ingestion-spec", default=None, help="Path to locked ingestion-policy JSON")
    snap.add_argument("--targets", default=None, help="Comma-separated targets (default: from spec)")
    snap.add_argument("--start", required=True, type=_parse_date, help="Start date (YYYY-MM-DD)")
    snap.add_argument("--end", required=True, type=_parse_date, help="End date (YYYY-MM-DD)")
    snap.add_argument("--provider", default=None, help="OHLCV provider (default: env/DATA_PROVIDER or yahoo)")
    snap.add_argument("--development-split", required=True, type=_parse_split)
    snap.add_argument("--validation-split", required=True, type=_parse_split)
    snap.add_argument("--holdout-split", required=True, type=_parse_split)
    snap.add_argument("--output-dir", required=True, help="Directory to write manifest and CSVs")
    snap.add_argument("--overwrite", action="store_true")
    snap.add_argument("--dataset-name", default="short-term-market-context", help="Manifest dataset name")

    eval_ = subparsers.add_parser(
        "evaluate",
        help="Evaluate a context study from an existing manifest and spec.",
    )
    eval_.add_argument("--manifest", required=True, help="Path to manifest.json")
    eval_.add_argument("--context-spec", required=True, help="Path to context-study spec JSON")
    eval_.add_argument("--ingestion-spec", default=None, help="Path to locked ingestion-policy JSON (required for v2 snapshots)")
    eval_.add_argument("--output-dir", required=True, help="Directory for study outputs")
    eval_.add_argument("--overwrite", action="store_true")
    eval_.add_argument("--warmup-bars", type=int, default=60)
    eval_.add_argument("--horizons", default="1,3,5", help="Comma-separated horizon bars")
    eval_.add_argument("--slippage-bps", default="0.0,5.0,10.0", help="Comma-separated slippage scenarios")
    eval_.add_argument("--commission-bps", type=float, default=0.0)

    return parser


def _comma_ints(value: str) -> tuple[int, ...]:
    if any(p == "" for p in value.split(",")):
        raise argparse.ArgumentTypeError(f"Expected nonempty comma-separated integers; got {value!r}")
    parts = [p.strip() for p in value.split(",")]
    try:
        return tuple(int(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected comma-separated integers; got {value!r}") from exc


def _comma_floats(value: str) -> tuple[float, ...]:
    if any(p == "" for p in value.split(",")):
        raise argparse.ArgumentTypeError(f"Expected nonempty comma-separated floats; got {value!r}")
    parts = [p.strip() for p in value.split(",")]
    try:
        return tuple(float(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected comma-separated floats; got {value!r}") from exc


def _handle_snapshot(args: argparse.Namespace) -> int:
    spec, spec_bytes = load_spec(args.context_spec)
    context_spec_sha256 = hashlib.sha256(spec_bytes).hexdigest()
    if args.targets:
        raw = {t.strip().upper() for t in args.targets.split(",") if t.strip()}
        if not raw:
            print("error: --targets contains no valid symbols", file=sys.stderr)
            return 1
        if raw != set(spec.target_tickers):
            print("error: --targets must match the context-spec target_tickers", file=sys.stderr)
            return 1

    # Ensure all required proxies are included in the snapshot.
    all_tickers = list(spec.all_tickers())

    splits = {
        "development": args.development_split,
        "validation": args.validation_split,
        "holdout": args.holdout_split,
    }
    kwargs: dict = {
        "tickers": all_tickers,
        "start": args.start,
        "end": args.end,
        "output_dir": args.output_dir,
        "splits": splits,
        "provider": args.provider,
        "overwrite": args.overwrite,
        "dataset_name": args.dataset_name,
        "context_spec_sha256": context_spec_sha256,
    }
    if args.ingestion_spec:
        kwargs["ingestion_spec"] = args.ingestion_spec
        # Validate the policy file now; create_snapshot recomputes its hash.
        load_ingestion_policy(args.ingestion_spec)
        kwargs["context_spec_sha256"] = context_spec_sha256
    create_snapshot(**kwargs)
    return 0


def _handle_evaluate(args: argparse.Namespace) -> int:
    horizons = _comma_ints(args.horizons)
    slippage = _comma_floats(args.slippage_bps)
    config = ScoreValidationConfig(
        warmup_bars=args.warmup_bars,
        horizons=horizons,
        slippage_scenarios_bps=slippage,
        commission_bps=args.commission_bps,
    )
    kwargs: dict = {
        "manifest_path": args.manifest,
        "spec_path": args.context_spec,
        "output_dir": args.output_dir,
        "config": config,
        "overwrite": args.overwrite,
    }
    if args.ingestion_spec:
        _, spec_bytes = load_ingestion_policy(args.ingestion_spec)
        expected_ingestion_sha = hashlib.sha256(spec_bytes).hexdigest()
        snapshot_dir = Path(args.manifest).expanduser().resolve().parent
        verify_snapshot_sidecars(snapshot_dir, expected_ingestion_sha)
        kwargs["ingestion_spec"] = args.ingestion_spec
    run_study(**kwargs)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "snapshot":
        return _handle_snapshot(args)
    if args.command == "evaluate":
        return _handle_evaluate(args)
    parser.print_help()
    return 1
