"""
Scheduled scan runner — polls the screener on a defined interval and
persists results to the signal history store.

This is what makes the tracker work: by running repeatedly, it builds
up the multi-day signal history that the coil detector reads.

Usage:
    # Run once manually
    python -m tradex.tracker.watcher --timeframe intraday

    # Run on a schedule (blocks, runs every N minutes)
    python -m tradex.tracker.watcher --timeframe intraday --interval 5

    # Or import and call from your own script
    from tradex.tracker.watcher import run_once, start_loop
"""
import argparse
import time
from datetime import datetime, timezone

import schedule

from tradex.screener.engine import run as screener_run
from tradex.tracker import store
from tradex.tracker.outcome_tracker import run_outcome_pass

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
    "AMD", "PLTR", "MSTR", "SPY", "QQQ", "SOXL", "TQQQ",
    "SMCI", "ARM",  "AVGO", "MU",   "CRWD", "NET",
]


def run_once(
    tickers: list[str],
    timeframe: str = "intraday",
    min_score: int = 35,
    provider: str | None = None,
) -> None:
    """Run a single scan pass and persist results."""
    store.init()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"[{now}] Scanning {len(tickers)} tickers on {timeframe}…")

    results = screener_run(tickers, timeframe=timeframe, min_score=min_score)

    if results.empty:
        print(f"[{now}] No signals above {min_score}.")
    else:
        print(f"[{now}] {len(results)} signals found:")
        print(results[["ticker", "score", "volume_ratio", "rsi"]].to_string(index=False))
        store.record_signals(results, timeframe)


def start_loop(
    tickers: list[str],
    timeframe: str = "intraday",
    interval_minutes: int = 5,
    min_score: int = 35,
    provider: str | None = None,
) -> None:
    """
    Block and run scans every interval_minutes.
    Designed to run during market hours (9:30am–4pm ET).
    """
    print(f"Starting watcher: {timeframe} every {interval_minutes}m — Ctrl+C to stop")
    run_once(tickers, timeframe, min_score, provider)

    schedule.every(interval_minutes).minutes.do(
        run_once, tickers=tickers, timeframe=timeframe,
        min_score=min_score, provider=provider,
    )
    # Run outcome pass once after market close each day (4:30pm ET ≈ 20:30 UTC)
    schedule.every().day.at("20:30").do(run_outcome_pass, verbose=True)

    try:
        while True:
            schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nWatcher stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TradeX signal watcher")
    parser.add_argument("--timeframe", default="intraday", choices=["intraday", "short", "long"])
    parser.add_argument("--interval",  type=int, default=0,
                        help="Poll interval in minutes. 0 = run once and exit.")
    parser.add_argument("--min-score", type=int, default=35)
    parser.add_argument("--provider",  default=None)
    args = parser.parse_args()

    if args.interval > 0:
        start_loop(DEFAULT_WATCHLIST, args.timeframe, args.interval, args.min_score, args.provider)
    else:
        run_once(DEFAULT_WATCHLIST, args.timeframe, args.min_score, args.provider)
