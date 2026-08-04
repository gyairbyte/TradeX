"""Command-line interface for the pre-market gap scanner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.config import load_runtime_settings
from tradex.premarket.config import GapScanConfig
from tradex.premarket.gap_scanner import scan_gaps_with_report
from tradex.premarket.models import VALID_TICKER_RE


def _parse_float(value: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"must be a number; got {value!r}") from exc


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"must be an integer; got {value!r}") from exc


def _parse_optional_float(value: str) -> float | None:
    if value.lower() in ("none", "null", ""):
        return None
    return _parse_float(value)


def _parse_tickers(value: str) -> list[str]:
    parts = [p.strip().upper().lstrip("$") for p in value.split(",")]
    if not parts or any(not p for p in parts):
        raise argparse.ArgumentTypeError("tickers must be non-empty comma-separated symbols")
    for p in parts:
        if not VALID_TICKER_RE.match(p):
            raise argparse.ArgumentTypeError(f"invalid ticker symbol: {p!r}")
    return parts


def _build_config(args: argparse.Namespace) -> GapScanConfig:
    return GapScanConfig(
        min_abs_gap_pct=args.min_gap,
        min_price=args.min_price,
        min_premarket_volume=args.min_premarket_volume,
        min_premarket_dollar_volume=args.min_premarket_dollar_volume,
        min_premarket_volume_ratio=args.min_premarket_volume_ratio,
        max_data_age_minutes=args.max_data_age_minutes,
        max_spread_bps=args.max_spread_bps,
        require_spread=args.require_spread,
        require_catalyst=args.require_catalyst,
        catalyst_lookback_hours=args.catalyst_lookback_hours,
        liquidity_lookback_sessions=args.liquidity_lookback_sessions,
        allow_after_open=args.allow_after_open,
    )


def _add_scan_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("scan", help="Run a pre-market gap scan")
    parser.add_argument(
        "--tickers", required=True, type=_parse_tickers, help="Comma-separated tickers"
    )
    parser.add_argument(
        "--provider", default=None, help="OHLCV provider (default: DATA_PROVIDER/yahoo)"
    )
    parser.add_argument("--min-gap", type=_parse_float, default=2.0, help="Minimum absolute gap %%")
    parser.add_argument(
        "--min-price", type=_parse_float, default=0.0, help="Minimum pre-market price"
    )
    parser.add_argument(
        "--min-premarket-volume", type=_parse_int, default=0, help="Minimum pre-market share volume"
    )
    parser.add_argument(
        "--min-premarket-dollar-volume",
        type=_parse_float,
        default=0.0,
        help="Minimum pre-market dollar volume",
    )
    parser.add_argument(
        "--min-premarket-volume-ratio",
        type=_parse_float,
        default=0.0,
        help="Minimum pre-market/average-daily-volume ratio",
    )
    parser.add_argument(
        "--max-data-age-minutes",
        type=_parse_optional_float,
        default=None,
        help="Maximum age of latest bar in minutes",
    )
    parser.add_argument(
        "--max-spread-bps",
        type=_parse_optional_float,
        default=None,
        help="Maximum spread in basis points",
    )
    parser.add_argument(
        "--require-spread", action="store_true", help="Require spread data to be available"
    )
    parser.add_argument("--require-catalyst", action="store_true", help="Require catalyst context")
    parser.add_argument(
        "--catalyst-lookback-hours",
        type=_parse_float,
        default=24.0,
        help="Headline lookback in hours",
    )
    parser.add_argument(
        "--liquidity-lookback-sessions",
        type=_parse_int,
        default=20,
        help="Completed sessions for liquidity baseline",
    )
    parser.add_argument(
        "--allow-after-open", action="store_true", help="Allow scan after regular-session open"
    )
    parser.add_argument("--earnings-source", default=None, help="Earnings source (e.g. yahoo)")
    parser.add_argument("--headline-source", default=None, help="Headline source (e.g. yahoo)")
    parser.add_argument("--include-catalysts", action="store_true", help="Fetch catalyst context")
    parser.add_argument("--json-output", default=None, help="Path to write JSON report")
    parser.add_argument("--csv-output", default=None, help="Path to write CSV results")
    parser.set_defaults(func=_run_scan)


def _run_scan(args: argparse.Namespace) -> int:
    try:
        settings = load_runtime_settings()
        config = _build_config(args)
        report = scan_gaps_with_report(
            args.tickers,
            config=config,
            provider=args.provider,
            earnings_source=args.earnings_source,
            headline_source=args.headline_source,
            include_catalysts=args.include_catalysts,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    counts = report.counts()
    print(
        f"Requested: {counts['requested']}, Qualified: {counts['qualified']}, "
        f"Filtered: {counts['filtered']}, Failed: {counts['failed']}, "
        f"Outside window: {counts['outside_window']}"
    )

    if report.provider_errors:
        for ticker, err in report.provider_errors.items():
            print(f"[provider error] {ticker}: {err}")

    if not report.results.empty:
        print("\nQualified gaps:")
        display = report.results[
            ["ticker", "prev_close", "pre_market", "gap_pct", "direction", "tier", "note"]
        ]
        print(display.to_string(index=False))

    if args.json_output:
        Path(args.json_output).write_text(
            json.dumps(report.to_dict(), indent=2, allow_nan=False),
            encoding="utf-8",
        )
        print(f"\nJSON report written to {args.json_output}")

    if args.csv_output:
        if report.results.empty:
            pd.DataFrame(columns=report.results.columns).to_csv(args.csv_output, index=False)
        else:
            report.results.to_csv(args.csv_output, index=False)
        print(f"CSV results written to {args.csv_output}")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TradeX pre-market gap scanner")
    subparsers = parser.add_subparsers(dest="command")
    _add_scan_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)
