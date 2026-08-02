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
from datetime import UTC, datetime

import schedule

from tradex.alerts.notifier import alert_coil, alert_confluence, alert_pattern_match
from tradex.data.fetcher import FetchPolicy, resolve_provider
from tradex.market import MARKET_TIMEZONE, is_regular_market_open, market_status
from tradex.patterns.matcher import run_match_screen
from tradex.premarket.gap_scanner import run_gap_alerts
from tradex.screener.engine import run_with_report as screener_run_with_report
from tradex.tracker import analyzer, store
from tradex.tracker.confluence import run_confluence_screen
from tradex.tracker.outcome_tracker import run_outcome_pass

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
    max_retries: int | str | None = None,
    fallback_order: str | tuple[str, ...] | list[str] | None = None,
    policy: FetchPolicy | None = None,
    market_hours_only: bool = False,
    now: datetime | None = None,
) -> None:
    """Run a single scan pass, persist results, and fire any threshold alerts.

    When ``market_hours_only`` is ``True``, the scan is skipped outside the NYSE
    regular session. ``now`` is timezone-aware UTC by default and may be injected
    for deterministic tests.
    """
    now = now or datetime.now(UTC)
    ny_now = now.astimezone(MARKET_TIMEZONE)
    timestamp = ny_now.strftime("%Y-%m-%d %H:%M %Z")

    if market_hours_only and not is_regular_market_open(now):
        status = market_status(now)
        print(f"[{timestamp}] Market closed — skipping scan. Reason: {status.reason}.")
        if status.next_open:
            next_open_str = status.next_open.astimezone(MARKET_TIMEZONE).strftime("%Y-%m-%d %H:%M %Z")
            print(f"[{timestamp}] Next regular session opens at {next_open_str}.")
        return

    store.init()
    requested_provider = resolve_provider(provider)
    fetch_policy = policy or FetchPolicy.build(max_retries=max_retries, fallback_order=fallback_order)
    requested_tickers = list(dict.fromkeys(str(t).upper() for t in tickers))
    print(f"[{timestamp}] Scanning {len(requested_tickers)} tickers on {timeframe} (provider={requested_provider}, "
          f"max_retries={fetch_policy.max_retries}, fallback={fetch_policy.fallback_order or 'disabled'})…")

    report = screener_run_with_report(
        requested_tickers,
        timeframe=timeframe,
        min_score=min_score,
        provider=requested_provider,
        policy=fetch_policy,
    )

    actual_provider = report.actual_provider or report.requested_provider
    has_earnings_failures = bool(report.earnings_failures)
    has_fetch_failures = bool(report.fetch_failures)
    has_scoring_failures = bool(report.scoring_failures)

    all_fetch_eligible_failed = (
        report.total_fetch_eligible > 0
        and report.total_fetched == 0
        and has_fetch_failures
    )

    if all_fetch_eligible_failed:
        categories = sorted({type(e).__name__ for e in report.fetch_failures.values()})
        print(f"[{timestamp}] ERROR: all providers failed for {report.total_fetch_eligible} "
              f"symbol(s) that reached OHLCV fetching. "
              f"Providers attempted: {report.providers_attempted}. "
              f"Failure categories: {categories or ['unknown']}.")
    elif report.results.empty:
        if report.total_earnings_excluded == len(requested_tickers):
            print(f"[{timestamp}] No signals above {min_score}; all {report.total_earnings_excluded} tickers excluded due to earnings.")
        else:
            print(f"[{timestamp}] No signals above {min_score}.")
    else:
        results = report.results
        print(f"[{timestamp}] {len(results)} signals found (actual provider={actual_provider}, "
              f"retries={report.total_retries}, fallback={report.fallback_used}):")
        print(results[["ticker", "score", "volume_ratio", "rsi", "provider"]].to_string(index=False))

    # Persist the full scan report (observations, session, and signals).
    store.record_scan(
        report,
        timeframe=timeframe,
        min_score=min_score,
        tickers_scanned=requested_tickers,
        scan_time=now,
    )

    # Surface each non-empty stage map independently.
    if has_earnings_failures:
        categories = sorted({type(e).__name__ for e in report.earnings_failures.values()})
        print(f"[{timestamp}] Earnings lookup failures: {len(report.earnings_failures)} symbol(s). "
              f"Categories: {categories or ['unknown']}.")
    if has_fetch_failures and not all_fetch_eligible_failed:
        categories = sorted({type(e).__name__ for e in report.fetch_failures.values()})
        print(f"[{timestamp}] OHLCV fetch failures: {len(report.fetch_failures)} symbol(s). "
              f"Categories: {categories or ['unknown']}.")
    if has_scoring_failures:
        categories = sorted({type(e).__name__ for e in report.scoring_failures.values()})
        print(f"[{timestamp}] Scoring failures: {len(report.scoring_failures)} symbol(s). "
              f"Categories: {categories or ['unknown']}.")

    if report.attempt_log:
        print(f"[{timestamp}] Attempt summary (providers attempted: {report.providers_attempted}, "
              f"total attempts: {report.total_fetch_attempted}, retries: {report.total_retries}).")
        for prov in report.providers_attempted:
            entries = [a for a in report.attempt_log if a.provider == prov]
            attempted = len(entries)
            succeeded = sum(1 for e in entries if e.success)
            failed = attempted - succeeded
            retries = sum(e.retries for e in entries)
            print(f"  - {prov}: {attempted} attempted, {succeeded} succeeded, {failed} failed, {retries} retries")

    if report.total_fetched > 0:
        _check_alerts(tickers, timeframe, provider=actual_provider)


def _run_scheduled_outcomes(
    provider: str | None = None,
    now: datetime | None = None,
) -> None:
    """Trading-day guard for the daily outcome-resolution job."""
    now = now or datetime.now(UTC)
    status = market_status(now)
    if not status.is_trading_day:
        ny_now = now.astimezone(MARKET_TIMEZONE)
        print(f"[{ny_now.strftime('%Y-%m-%d %H:%M %Z')}] Skipping outcome pass — {status.reason}.")
        return
    run_outcome_pass(verbose=True, provider=provider)


def _run_scheduled_premarket(
    tickers: list[str],
    provider: str | None = None,
    now: datetime | None = None,
) -> None:
    """Trading-day guard for the daily pre-market gap scan."""
    now = now or datetime.now(UTC)
    status = market_status(now)
    if not status.is_trading_day:
        ny_now = now.astimezone(MARKET_TIMEZONE)
        print(f"[{ny_now.strftime('%Y-%m-%d %H:%M %Z')}] Skipping pre-market gap scan — {status.reason}.")
        return
    run_gap_alerts(tickers, min_gap_pct=4.0, provider=provider, as_of=now)


def start_loop(
    tickers: list[str],
    timeframe: str = "intraday",
    interval_minutes: int = 5,
    min_score: int = 35,
    provider: str | None = None,
    max_retries: int | str | None = None,
    fallback_order: str | tuple[str, ...] | list[str] | None = None,
    policy: FetchPolicy | None = None,
    market_hours_only: bool = False,
) -> None:
    """
    Block and run scans every interval_minutes.
    Designed to run during market hours (9:30am–4pm ET).
    """
    requested_provider = resolve_provider(provider)
    fetch_policy = policy or FetchPolicy.build(max_retries=max_retries, fallback_order=fallback_order)
    print(f"Starting watcher: {timeframe} every {interval_minutes}m "
          f"(provider={requested_provider}, retries={fetch_policy.max_retries}, "
          f"fallback={fetch_policy.fallback_order or 'disabled'}, "
          f"market_hours_only={market_hours_only}) — Ctrl+C to stop")
    run_once(
        tickers, timeframe, min_score, provider,
        max_retries=max_retries, fallback_order=fallback_order, policy=policy,
        market_hours_only=market_hours_only,
    )

    def _scheduled_run() -> None:
        run_once(
            tickers, timeframe, min_score, requested_provider,
            max_retries=max_retries, fallback_order=fallback_order, policy=policy,
            market_hours_only=market_hours_only,
            now=datetime.now(UTC),
        )

    schedule.every(interval_minutes).minutes.do(_scheduled_run)
    # Daily after market close: resolve outcomes at 4:30 PM New York time.
    schedule.every().day.at("16:30", "America/New_York").do(
        _run_scheduled_outcomes, provider=requested_provider
    )
    # Daily pre-market: gap scan at 8:00 AM New York time.
    schedule.every().day.at("08:00", "America/New_York").do(
        _run_scheduled_premarket, tickers=tickers, provider=provider
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
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="Max extra retries per ticker (overrides OHLCV_MAX_RETRIES env var).",
    )
    parser.add_argument(
        "--fallback-order",
        default=None,
        help="Comma-separated OHLCV fallback provider order (overrides OHLCV_FALLBACK_ORDER env var).",
    )
    parser.add_argument(
        "--market-hours-only",
        action="store_true",
        help="Only run interval scans while the NYSE regular session is open.",
    )
    args = parser.parse_args()

    if args.interval > 0:
        start_loop(
            DEFAULT_WATCHLIST, args.timeframe, args.interval, args.min_score,
            args.provider, max_retries=args.max_retries, fallback_order=args.fallback_order,
            market_hours_only=args.market_hours_only,
        )
    else:
        run_once(
            DEFAULT_WATCHLIST, args.timeframe, args.min_score, args.provider,
            max_retries=args.max_retries, fallback_order=args.fallback_order,
            market_hours_only=args.market_hours_only,
        )
