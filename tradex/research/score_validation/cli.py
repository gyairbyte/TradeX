"""Command-line interface for the short-term score validation study."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .manifest import load_manifest
from .models import ScoreValidationConfig, ValidationError
from .report import run_study, write_study
from .snapshot import create_snapshot


def _comma_ints(value: str) -> tuple[int, ...]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    try:
        return tuple(int(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected comma-separated integers; got {value!r}") from exc


def _comma_floats(value: str) -> tuple[float, ...]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    try:
        return tuple(float(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected comma-separated numbers; got {value!r}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradex.research.score_validation",
        description="Point-in-time validation study for the TradeX short-term scorer.",
    )
    subparsers = parser.add_subparsers(dest="command")

    snapshot = subparsers.add_parser(
        "snapshot",
        help="Fetch daily OHLCV snapshots and build a versioned manifest.",
    )
    snapshot.add_argument("--tickers", required=True, help="Comma-separated tickers")
    snapshot.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    snapshot.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    snapshot.add_argument("--provider", default=None, help="Data provider (yahoo, schwab, ...)")
    snapshot.add_argument("--output-dir", required=True, help="Output directory")
    snapshot.add_argument("--overwrite", action="store_true", help="Overwrite existing output")
    snapshot.add_argument("--dataset-name", default="short-term-score-study")
    snapshot.add_argument("--source-description", default="offline OHLCV snapshots")
    snapshot.add_argument("--adjustment-policy", default="provider_default")

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Evaluate a manifest offline and produce a score-validation report.",
    )
    evaluate.add_argument("--manifest", required=True, help="Path to manifest.json")
    evaluate.add_argument("--output-dir", required=True, help="Output directory")
    evaluate.add_argument("--overwrite", action="store_true")
    evaluate.add_argument("--warmup-bars", type=int, default=60)
    evaluate.add_argument("--horizons", type=_comma_ints, default="1,3,5")
    evaluate.add_argument("--score-buckets", type=_comma_ints, default="0,20,40,60,80,101")
    evaluate.add_argument("--thresholds", type=_comma_ints, default="20,30,40,50,60,70,80")
    evaluate.add_argument("--slippage-bps", type=_comma_floats, default="0.0,5.0,10.0")
    evaluate.add_argument("--commission-bps", type=float, default=0.0)
    evaluate.add_argument("--minimum-group-events", type=int, default=20)

    return parser


def _handle_snapshot(args: argparse.Namespace) -> int:
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        print("error: --tickers must contain at least one ticker", file=sys.stderr)
        return 1
    try:
        manifest_path = create_snapshot(
            tickers=tickers,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
            provider=args.provider,
            output_dir=args.output_dir,
            overwrite=args.overwrite,
            dataset_name=args.dataset_name,
            source_description=args.source_description,
            adjustment_policy=args.adjustment_policy,
        )
        print(f"Snapshot written to: {manifest_path}")
        print(f"Output directory: {Path(manifest_path).parent}")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _handle_evaluate(args: argparse.Namespace) -> int:
    try:
        config = ScoreValidationConfig(
            warmup_bars=args.warmup_bars,
            horizons=args.horizons,
            score_bucket_edges=args.score_buckets,
            score_thresholds=args.thresholds,
            slippage_scenarios_bps=args.slippage_bps,
            commission_bps=args.commission_bps,
            minimum_group_events=args.minimum_group_events,
        )
        study = run_study(args.manifest, config)
        paths = write_study(study, args.output_dir, overwrite=args.overwrite)
        print(f"Study written to: {args.output_dir}")
        print(f"Events: {len(study.events)}")
        print(f"Score buckets: {len(study.score_buckets)}")
        print(f"Thresholds: {len(study.thresholds)}")
        for name, path in sorted(paths.items()):
            print(f"  {name}: {path}")
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "snapshot":
        return _handle_snapshot(args)
    if args.command == "evaluate":
        return _handle_evaluate(args)
    parser.print_help()
    return 0
