"""Command-line interface for the TradeX backtest harness."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from tradex.backtest.engine import run_short_term_backtest
from tradex.backtest.io import load_csv
from tradex.backtest.models import BacktestConfig, BacktestError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tradex.backtest",
        description="Run a deterministic, point-in-time backtest for one ticker.",
    )

    parser.add_argument("--csv", type=str, help="Path to an offline CSV OHLCV file")
    parser.add_argument("--ticker", type=str, help="Ticker symbol for the backtest output")
    parser.add_argument("--start", type=str, help="Provider start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="Provider end date (YYYY-MM-DD)")
    parser.add_argument("--provider", type=str, help="OHLCV provider (e.g. yahoo, schwab)")
    parser.add_argument("--timezone", type=str, help="Timezone for naive CSV datetimes")

    parser.add_argument("--min-score", type=int, default=40, help="Minimum qualifying score")
    parser.add_argument("--warmup-bars", type=int, default=60, help="Bars to warm up before scoring")
    parser.add_argument("--holding-bars", type=int, default=3, help="Maximum holding period in bars")
    parser.add_argument("--stop-loss-pct", type=float, default=5.0, help="Stop loss percent (e.g. 5)")
    parser.add_argument("--take-profit-pct", type=float, default=10.0, help="Take profit percent (e.g. 10)")
    parser.add_argument("--commission-bps", type=float, default=0.0, help="Commission in basis points")
    parser.add_argument("--slippage-bps", type=float, default=0.0, help="Slippage in basis points")

    parser.add_argument("--json-output", type=str, help="Write JSON result to PATH")
    parser.add_argument("--trades-output", type=str, help="Write trade CSV to PATH")
    parser.add_argument("--equity-output", type=str, help="Write equity curve CSV to PATH")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the backtest CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        config = BacktestConfig(
            min_score=args.min_score,
            warmup_bars=args.warmup_bars,
            max_holding_bars=args.holding_bars,
            stop_loss_pct=args.stop_loss_pct / 100.0,
            take_profit_pct=args.take_profit_pct / 100.0,
            commission_bps=args.commission_bps,
            slippage_bps=args.slippage_bps,
            initial_capital=100_000.0,
            intrabar_policy="stop_first",
        )
    except BacktestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not args.ticker:
        print("Error: --ticker is required to identify the security being backtested", file=sys.stderr)
        return 1

    if args.csv and (args.start or args.end):
        print("Error: --start and --end are only used with provider mode, not --csv", file=sys.stderr)
        return 1

    if args.csv:
        try:
            bars = load_csv(args.csv, timezone=args.timezone)
        except BacktestError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        data_source = f"csv:{Path(args.csv).name}"
    else:
        if not args.start or not args.end:
            print("Error: --start and --end are required with --ticker", file=sys.stderr)
            return 1
        try:
            resolved_provider = _resolve_provider(args.provider)
            bars = _fetch_provider_bars(args.ticker, args.start, args.end, resolved_provider)
        except BacktestError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        data_source = resolved_provider

    ticker = args.ticker

    try:
        result = run_short_term_backtest(ticker, bars, config=config, data_source=data_source)
    except BacktestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        Path(args.json_output).write_text(result.to_json(indent=2))
    if args.trades_output:
        result.to_trades_df().to_csv(args.trades_output, index=False)
    if args.equity_output:
        result.to_equity_df().to_csv(args.equity_output)

    _print_summary(result)
    return 0


def _resolve_provider(provider: str | None) -> str:
    """Resolve a provider name through the canonical OHLCV resolver."""
    from tradex.data.fetcher import resolve_provider

    try:
        return resolve_provider(provider)
    except Exception as exc:  # noqa: BLE001
        raise BacktestError(f"Failed to resolve provider: {exc}") from None


def _fetch_provider_bars(ticker: str, start: str, end: str, provider: str):
    """Fetch daily bars through the existing date-ranged history abstraction."""
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError as exc:
        raise BacktestError(f"Invalid date format: {exc}") from None

    try:
        from tradex.data.history import fetch_daily_history
    except Exception as exc:  # noqa: BLE001
        raise BacktestError(f"Failed to import provider history: {exc}") from None

    try:
        return fetch_daily_history(ticker, start_date, end_date, provider=provider)
    except Exception as exc:  # noqa: BLE001
        raise BacktestError(f"Failed to fetch history: {exc}") from None


def _print_summary(result) -> None:
    m = result.metrics
    print(f"Ticker:        {result.ticker}")
    print(f"Strategy:      {result.strategy_name}")
    print(f"Data source:   {result.data_source}")
    print(f"Date range:    {result.evaluation_start.date()} to {result.evaluation_end.date()}")
    print(f"Configuration: {result.config}")
    print(f"Weight snapshot: {result.weight_snapshot}")
    print(f"Signals:       {m.total_signals} generated, {m.qualifying_signals} qualifying")
    print(f"Trades:        {m.total_trades} executed")
    print(f"Win rate:      {m.win_rate_pct:.1f}%" if m.win_rate_pct is not None else "Win rate:      N/A")
    print(f"Expectancy:    {m.expectancy_pct:.2f}%" if m.expectancy_pct is not None else "Expectancy:    N/A")
    print(f"Total return:  {m.total_return_pct:.2f}%")
    print(f"Benchmark:     {m.buy_and_hold_return_pct:.2f}%")
    print(f"Excess return: {m.excess_return_pct:.2f}%")
    print(f"Sharpe:        {m.sharpe_ratio:.2f}" if m.sharpe_ratio is not None else "Sharpe:        N/A")
    print(f"Max drawdown:  {m.max_drawdown_pct:.2f}%")
    print(f"Ending capital: ${m.ending_capital:,.2f}")
    print()
    print("Limitations:")
    for limitation in result.limitations:
        print(f"  - {limitation}")
