"""Command-line interface for LONG-001 snapshot and evaluation."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from .evaluate import evaluate_study
from .models import LONG_TERM_UNIVERSE, LongTermStudySpec, LongWeights, load_manifest
from .snapshot import snapshot_dataset


def _date(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


def _spec_from_dict(raw: dict[str, Any]) -> LongTermStudySpec:
    """Build a ``LongTermStudySpec`` from a machine-readable protocol dict."""
    raw = dict(raw)
    for key in ("start", "end", "warmup_end", "development_end", "validation_end"):
        if key in raw and isinstance(raw[key], str):
            raw[key] = date.fromisoformat(raw[key])
    for key in ("hold_weeks", "score_thresholds", "score_bucket_edges", "slippage_scenarios_bps", "universe"):
        if key in raw and isinstance(raw[key], list):
            raw[key] = tuple(raw[key])
    if "weights" in raw and isinstance(raw["weights"], dict):
        raw["weights"] = LongWeights(**raw["weights"])
    return LongTermStudySpec(**raw)


def _make_spec(args: argparse.Namespace) -> LongTermStudySpec:
    if args.protocol:
        raw = json.loads(Path(args.protocol).read_text(encoding="utf-8"))
        return _spec_from_dict(raw)

    universe = tuple(t.strip().upper() for t in args.universe.split(",") if t.strip()) if args.universe else LONG_TERM_UNIVERSE
    slippage_scenarios = tuple(float(s) for s in args.slippage_scenarios.split(",") if s.strip())
    hold_weeks = tuple(int(h) for h in args.hold_weeks.split(",") if h.strip())
    return LongTermStudySpec(
        provider=args.provider,
        universe=universe,
        benchmark_ticker=args.benchmark_ticker.upper(),
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        warmup_end=date.fromisoformat(args.warmup_end),
        development_end=date.fromisoformat(args.development_end),
        validation_end=date.fromisoformat(args.validation_end),
        warmup_weeks=args.warmup_weeks,
        min_required_weekly_bars=args.min_required_weekly_bars,
        hold_weeks=hold_weeks,
        decision_slippage_bps=args.decision_slippage_bps,
        slippage_scenarios_bps=slippage_scenarios,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LONG-001 long-term scorer evaluation")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="Fetch daily bars and build a locked manifest.")
    snap.add_argument("--protocol", type=Path, help="Path to locked protocol JSON (overrides other spec args)")
    snap.add_argument("--universe", required=False, help="Comma-separated candidate tickers")
    snap.add_argument("--benchmark-ticker", default="SPY")
    snap.add_argument("--start", default="2007-01-01")
    snap.add_argument("--end", default="2025-12-19")
    snap.add_argument("--warmup-end", default="2009-12-31")
    snap.add_argument("--development-end", default="2016-12-31")
    snap.add_argument("--validation-end", default="2020-12-31")
    snap.add_argument("--warmup-weeks", type=int, default=60)
    snap.add_argument("--min-required-weekly-bars", type=int, default=60)
    snap.add_argument("--hold-weeks", default="13,26")
    snap.add_argument("--slippage-scenarios", default="0,10,25")
    snap.add_argument("--decision-slippage-bps", type=float, default=5.0)
    snap.add_argument("--output", required=True, type=Path)
    snap.add_argument("--provider", default="yahoo")

    evalp = sub.add_parser("evaluate", help="Evaluate the long-term scorer on a locked manifest.")
    evalp.add_argument("--protocol", type=Path, help="Path to locked protocol JSON (overrides other spec args)")
    evalp.add_argument("--manifest", required=True, type=Path)
    evalp.add_argument("--output", required=True, type=Path)
    evalp.add_argument("--universe", required=False)
    evalp.add_argument("--benchmark-ticker", default="SPY")
    evalp.add_argument("--start", default="2007-01-01")
    evalp.add_argument("--end", default="2025-12-19")
    evalp.add_argument("--warmup-end", default="2009-12-31")
    evalp.add_argument("--development-end", default="2016-12-31")
    evalp.add_argument("--validation-end", default="2020-12-31")
    evalp.add_argument("--warmup-weeks", type=int, default=60)
    evalp.add_argument("--min-required-weekly-bars", type=int, default=60)
    evalp.add_argument("--hold-weeks", default="13,26")
    evalp.add_argument("--slippage-scenarios", default="0,10,25")
    evalp.add_argument("--decision-slippage-bps", type=float, default=5.0)
    evalp.add_argument("--provider", default="yahoo")

    args = parser.parse_args(argv)

    if args.command == "snapshot":
        spec = _make_spec(args)
        manifest = snapshot_dataset(spec, args.output)
        print(f"Manifest written to {args.output / 'manifest.json'}")
        print(f"Tickers: {len([e for e in manifest.entries if not e.failure])}; rows: {sum(e.rows for e in manifest.entries)}")
        return 0

    if args.command == "evaluate":
        manifest = load_manifest(args.manifest)
        spec = _make_spec(args)
        if not manifest.verify_metadata(spec):
            print("Manifest metadata does not match the provided spec", file=sys.stderr)
            return 1
        result = evaluate_study(manifest, spec, data_dir=args.manifest.parent, output_dir=args.output)
        print(f"Conclusion: {result.conclusion}")
        print(f"Report written to {args.output / 'report.md'}")
        return 0

    return 0


if __name__ == "__main__":
    main()
