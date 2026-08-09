"""Command-line interface for the INTRA-001C synthetic engine."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from .engine import run_study
from .models import as_json_dict
from .spec import load_spec
from .synthetic import generate_synthetic_inputs


def _write_outputs(result, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(as_json_dict(result), indent=2, sort_keys=True)
    )
    (output_dir / "report.md").write_text(result.report_markdown)
    trades = result.trades
    if trades:
        import csv

        for strategy, trade_list in trades.items():
            rows = [as_json_dict(t) for t in trade_list]
            if rows:
                keys = rows[0].keys()
                path = output_dir / f"trades_{strategy}.csv"
                with path.open("w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=keys)
                    writer.writeheader()
                    writer.writerows(rows)


def synthetic_smoke(args: argparse.Namespace) -> int:
    """Run the deterministic synthetic workflow and write artifacts."""
    output_dir = Path(args.output).expanduser().resolve()
    spec, _ = load_spec()
    inputs = generate_synthetic_inputs(
        spec,
        seed=args.seed,
        n_stock_tickers=args.n_stock_tickers,
        n_etf_tickers=args.n_etf_tickers,
        n_sessions=args.n_sessions,
    )
    result = run_study(
        inputs,
        spec,
        synthetic=True,
        evidence_eligible=False,
        generated_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    _write_outputs(result, output_dir)
    print(f"Wrote synthetic outputs to {output_dir}")
    print(f"Disposition: {result.outcome.disposition}")
    print(f"Reason: {result.outcome.reason}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradex.research.intraday_engine",
        description="Synthetic INTRA-001C intraday research engine",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    smoke = subparsers.add_parser(
        "synthetic-smoke", help="Run a deterministic synthetic smoke test"
    )
    smoke.add_argument("--output", required=True, help="Directory to write artifacts")
    smoke.add_argument("--seed", type=int, default=20260801, help="Random seed")
    smoke.add_argument(
        "--n-stock-tickers", type=int, default=5, help="Number of synthetic stock tickers"
    )
    smoke.add_argument(
        "--n-etf-tickers", type=int, default=2, help="Number of synthetic ETF tickers"
    )
    smoke.add_argument(
        "--n-sessions", type=int, default=60, help="Number of sessions per ticker"
    )
    smoke.set_defaults(func=synthetic_smoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
