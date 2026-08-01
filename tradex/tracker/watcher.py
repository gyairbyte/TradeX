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
from tradex.tracker import store, analyzer
from tradex.tracker.outcome_tracker import run_outcome_pass
from tradex.tracker.confluence import run_confluence_screen
from tradex.patterns.matcher import run_match_screen
from tradex.alerts.notifier import alert_coil, alert_pattern_match, alert_confluence
from tradex.premarket.gap_scanner import run_gap_alerts

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
    "AMD", "PLTR", "MSTR", "SPY", "QQQ", "SOXL", "TQQQ",
    "SMCI", "ARM",  "AVGO", "MU",   "CRWD", "NET",
]


def _check_alerts(tickers: list[str], timeframe: str, provider: str | None = None) -> None:
    """Check coils, confluence, and pattern matches — fire alerts where thresholds are crossed."""
    # Coil alerts
    coils = analyzer.detect_coils(timeframe, days=7)
    for _, row in coils.iterrows():
        alert_coil(
            ticker=row["ticker"],
            coil_strength=row["coil_strength"],
            score=row["latest_score"],
            trend=row["trend_direction"],
            timeframe=timeframe,
        )

    # Confluence alerts
    conf = run_confluence_screen(tickers, provider=provider)
    for _, row in conf.iterrows():
        alert_confluence(
            ticker=row["ticker"],
            confluence_score=int(row["confluence_score"]),
            active_timeframes=row["active_timeframes"].split(", ") if row["active_timeframes"] else [],
            last_close=float(row.get("last_close") or 0),
        )

    # Pattern match alerts (only if fingerprints exist)
    for event_type in ("runup", "decline"):
        for profile in ("standard",):
            matches = run_match_screen(
                tickers, event_type=event_type, profile=profile, provider=provider
            )
            for _, row in matches.iterrows():
                alert_pattern_match(
                    ticker=row["ticker"],
                    similarity=float(row["similarity_score"]),
                    event_type=event_type,
                    profile=profile,
                    fp_events=int(row.get("fp_events", 0)),
                    interpretation=row.get("interpretation", ""),
                )


def run_once(
    tickers: list[str],
    timeframe: str = "intraday",
    min_score: int = 35,
    provider: str | None = None,
) -> None:
    """Run a single scan pass, persist results, and fire any threshold alerts."""
    store.init()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    provider_label = provider if provider else "env default"
    print(f"[{now}] Scanning {len(tickers)} tickers on {timeframe} (provider={provider_label})…")

    results = screener_run(
        tickers, timeframe=timeframe, min_score=min_score, provider=provider
    )

    if results.empty:
        print(f"[{now}] No signals above {min_score}.")
    else:
        print(f"[{now}] {len(results)} signals found:")
        print(results[["ticker", "score", "volume_ratio", "rsi"]].to_string(index=False))
        store.record_signals(results, timeframe)

    _check_alerts(tickers, timeframe, provider=provider)


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
    effective_provider = provider if provider else "env default"
    print(f"Starting watcher: {timeframe} every {interval_minutes}m (provider={effective_provider}) — Ctrl+C to stop")
    run_once(tickers, timeframe, min_score, provider)

    schedule.every(interval_minutes).minutes.do(
        run_once, tickers=tickers, timeframe=timeframe,
        min_score=min_score, provider=provider,
    )
    # Daily after market close: resolve outcomes
    schedule.every().day.at("20:30").do(run_outcome_pass, verbose=True)
    # Daily pre-market: gap scan at 8am ET (12:00 UTC)
    schedule.every().day.at("12:00").do(
        run_gap_alerts, tickers=tickers, min_gap_pct=4.0
    )

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
    parser.add_argument(
        "--provider",
        default=None,
        choices=["yahoo", "schwab", "alpaca", "ibkr"],
        help="Market data provider to use for supported OHLCV workflows. Defaults to DATA_PROVIDER env var or yahoo.",
    )
    args = parser.parse_args()

    if args.interval > 0:
        start_loop(DEFAULT_WATCHLIST, args.timeframe, args.interval, args.min_score, args.provider)
    else:
        run_once(DEFAULT_WATCHLIST, args.timeframe, args.min_score, args.provider)
