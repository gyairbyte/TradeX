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
import dataclasses
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import schedule

from tradex.alerts.models import AlertCooldownConfig, AlertDecision, AlertDispatchResult
from tradex.alerts.notifier import alert_coil, alert_confluence, alert_gap
from tradex.alerts.policy import AlertPolicy
from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import FetchPolicy, resolve_provider
from tradex.market import MARKET_TIMEZONE, is_regular_market_open, market_status
from tradex.premarket.config import GapScanConfig
from tradex.premarket.gap_scanner import scan_gaps_with_report
from tradex.screener.engine import run_with_report as screener_run_with_report
from tradex.tracker import analyzer, store
from tradex.tracker.confluence import run_confluence_screen
from tradex.tracker.outcome_tracker import run_outcome_pass

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
    "AMD", "PLTR", "MSTR", "SPY", "QQQ", "SOXL", "TQQQ",
    "SMCI", "ARM",  "AVGO", "MU",   "CRWD", "NET",
]


def _default_alert_policy() -> AlertPolicy:
    """Build the default enabled alert policy from the environment.

    The underlying store is not created until the first alert is evaluated,
    so this helper is safe to call even when no alerts fire.
    """
    return AlertPolicy(AlertCooldownConfig.from_env())


def _check_alerts(
    tickers: list[str],
    timeframe: str,
    provider: str | None = None,
    *,
    alert_policy: AlertPolicy | None = None,
    observed_at: datetime | None = None,
    settings: TradeXSettings | None = None,
) -> list[AlertDispatchResult]:
    """Check coils and confluence — fire alerts where thresholds are crossed.

    Pattern matching is experimental and quarantined from automatic alerts; it is
    not evaluated here. See `tradex.research.pattern_validation` for the research
    study.
    """
    if settings is None:
        settings = load_runtime_settings()
    if alert_policy is None:
        alert_policy = AlertPolicy(
            settings.alert_cooldown, settings=settings,
        )

    results: list[AlertDispatchResult] = []

    # Coil alerts
    coils = analyzer.detect_coils(timeframe, days=7, settings=settings)
    for _, row in coils.iterrows():
        results.append(
            alert_coil(
                ticker=row["ticker"],
                coil_strength=row["coil_strength"],
                score=row["latest_score"],
                trend=row["trend_direction"],
                timeframe=timeframe,
                policy=alert_policy,
                observed_at=observed_at,
                settings=settings,
            )
        )

    # Confluence alerts
    conf = run_confluence_screen(
        tickers, provider=provider, settings=settings,
    )
    for _, row in conf.iterrows():
        results.append(
            alert_confluence(
                ticker=row["ticker"],
                confluence_score=int(row["confluence_score"]),
                active_timeframes=row["active_timeframes"].split(", ") if row["active_timeframes"] else [],
                last_close=float(row.get("last_close") or 0),
                policy=alert_policy,
                observed_at=observed_at,
                settings=settings,
            )
        )

    return results


def _print_alert_summary(results: list[AlertDispatchResult]) -> None:
    """Print a concise count of alert outcomes plus per-suppression details."""
    evaluated = len(results)
    sent = sum(
        1
        for r in results
        if r.decision in (AlertDecision.SENT, AlertDecision.COOLDOWN_DISABLED)
    )
    suppressed = sum(
        1
        for r in results
        if r.decision
        in (AlertDecision.SUPPRESSED_COOLDOWN, AlertDecision.SUPPRESSED_IN_FLIGHT)
    )
    failed = sum(
        1
        for r in results
        if r.decision
        in (AlertDecision.DELIVERY_FAILED, AlertDecision.NO_CHANNELS_CONFIGURED)
    )
    policy_errors = sum(1 for r in results if r.decision == AlertDecision.POLICY_ERROR)
    print(
        f"[alerts] evaluated={evaluated} sent={sent} suppressed={suppressed} "
        f"failed={failed} policy_errors={policy_errors}"
    )

    for r in results:
        if r.decision == AlertDecision.SUPPRESSED_COOLDOWN:
            next_eligible = (
                r.next_eligible_at.isoformat() if r.next_eligible_at else "unknown"
            )
            print(
                f"[alerts] suppressed (cooldown): {r.key.ticker} | {r.key.alert_type} | "
                f"{r.key.timeframe}; next eligible at {next_eligible}"
            )
        elif r.decision == AlertDecision.SUPPRESSED_IN_FLIGHT:
            claim_expires = (
                r.next_eligible_at.isoformat() if r.next_eligible_at else "unknown"
            )
            print(
                f"[alerts] suppressed (in-flight): {r.key.ticker} | {r.key.alert_type} | "
                f"{r.key.timeframe}; claim expires at {claim_expires}"
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
    alert_policy: AlertPolicy | None = None,
    now: datetime | None = None,
    *,
    settings: TradeXSettings | None = None,
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

    if settings is None:
        settings = load_runtime_settings()
    if alert_policy is None:
        alert_policy = AlertPolicy(
            settings.alert_cooldown, settings=settings,
        )

    store.init(db_path=str(settings.paths.signals_db))
    requested_provider = resolve_provider(provider, settings=settings)
    fetch_policy = policy or FetchPolicy.build(
        max_retries=max_retries, fallback_order=fallback_order, settings=settings
    )
    requested_tickers = list(dict.fromkeys(str(t).upper() for t in tickers))
    print(f"[{timestamp}] Scanning {len(requested_tickers)} tickers on {timeframe} (provider={requested_provider}, "
          f"max_retries={fetch_policy.max_retries}, fallback={fetch_policy.fallback_order or 'disabled'})…")

    report = screener_run_with_report(
        requested_tickers,
        timeframe=timeframe,
        min_score=min_score,
        provider=requested_provider,
        policy=fetch_policy,
        settings=settings,
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
        alert_results = _check_alerts(
            tickers, timeframe, provider=actual_provider,
            alert_policy=alert_policy, observed_at=now, settings=settings,
        )
        _print_alert_summary(alert_results)


def _run_scheduled_outcomes(
    provider: str | None = None,
    now: datetime | None = None,
    *,
    settings: TradeXSettings | None = None,
) -> None:
    """Trading-day guard for the daily outcome-resolution job."""
    now = now or datetime.now(UTC)
    status = market_status(now)
    if not status.is_trading_day:
        ny_now = now.astimezone(MARKET_TIMEZONE)
        print(f"[{ny_now.strftime('%Y-%m-%d %H:%M %Z')}] Skipping outcome pass — {status.reason}.")
        return
    if settings is None:
        settings = load_runtime_settings()
    run_outcome_pass(verbose=True, provider=provider, settings=settings)


def _run_scheduled_premarket(
    tickers: list[str],
    provider: str | None = None,
    *,
    alert_policy: AlertPolicy | None = None,
    now: datetime | None = None,
) -> None:
    """Trading-day guard for the daily pre-market gap scan using the structured report."""
    now = now or datetime.now(UTC)
    status = market_status(now)
    if not status.is_trading_day:
        ny_now = now.astimezone(MARKET_TIMEZONE)
        print(f"[{ny_now.strftime('%Y-%m-%d %H:%M %Z')}] Skipping pre-market gap scan — {status.reason}.")
        return

    settings = load_runtime_settings()
    if alert_policy is None:
        alert_policy = AlertPolicy(
            settings.alert_cooldown, settings=settings,
        )

    config = GapScanConfig(min_abs_gap_pct=4.0)
    try:
        report = scan_gaps_with_report(
            tickers, config=config, provider=provider, as_of=now, settings=settings,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[pre-market gap] {exc}")
        return

    counts = report.counts()
    print(
        f"[pre-market gap] requested={counts['requested']}, "
        f"qualified={counts['qualified']}, filtered={counts['filtered']}, "
        f"failed={counts['failed']}, outside_window={counts['outside_window']}"
    )

    if report.provider_errors:
        categories = sorted({str(e) for e in report.provider_errors.values()})
        print(f"[pre-market gap] provider errors: {categories}")

    provider_failures = counts.get("provider_failure", 0)
    missing_data = counts.get("no_previous_close", 0) + counts.get("no_premarket_data", 0)
    if provider_failures == counts["requested"] and counts["requested"] > 0:
        print("[pre-market gap] All tickers failed — possible provider or data outage.")
    elif missing_data == counts["requested"] and counts["requested"] > 0:
        print("[pre-market gap] All tickers lack required market data (previous close or pre-market bars).")
    elif counts["qualified"] == 0:
        print("[pre-market gap] No qualifying gaps at 4% threshold.")

    gap_results: list[AlertDispatchResult] = []
    for _, row in report.results.iterrows():
        if row["tier"] in ("large", "massive"):
            gap_results.append(
                alert_gap(
                    ticker=row["ticker"],
                    gap_pct=row["gap_pct"],
                    direction=row["direction"],
                    prev_close=row["prev_close"],
                    pre_market=row["pre_market"],
                    policy=alert_policy,
                    observed_at=now,
                    settings=settings,
                )
            )
    _print_alert_summary(gap_results)


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
    alert_policy: AlertPolicy | None = None,
) -> None:
    """
    Block and run scans every interval_minutes.
    Designed to run during market hours (9:30am–4pm ET).
    """
    settings = load_runtime_settings()
    if alert_policy is None:
        alert_policy = AlertPolicy(
            settings.alert_cooldown, settings=settings,
        )

    requested_provider = resolve_provider(provider, settings=settings)
    fetch_policy = policy or FetchPolicy.build(
        max_retries=max_retries, fallback_order=fallback_order, settings=settings
    )
    print(f"Starting watcher: {timeframe} every {interval_minutes}m "
          f"(provider={requested_provider}, retries={fetch_policy.max_retries}, "
          f"fallback={fetch_policy.fallback_order or 'disabled'}, "
          f"market_hours_only={market_hours_only}) — Ctrl+C to stop")
    run_once(
        tickers, timeframe, min_score, provider,
        max_retries=max_retries, fallback_order=fallback_order, policy=policy,
        market_hours_only=market_hours_only,
        alert_policy=alert_policy,
        settings=settings,
    )

    def _scheduled_run() -> None:
        run_once(
            tickers, timeframe, min_score, requested_provider,
            max_retries=max_retries, fallback_order=fallback_order, policy=policy,
            market_hours_only=market_hours_only,
            alert_policy=alert_policy,
            now=datetime.now(UTC),
            settings=settings,
        )

    schedule.every(interval_minutes).minutes.do(_scheduled_run)
    # Daily after market close: resolve outcomes at 4:30 PM New York time.
    schedule.every().day.at("16:30", "America/New_York").do(
        _run_scheduled_outcomes, provider=requested_provider, settings=settings
    )
    # Daily pre-market: gap scan at 8:00 AM New York time.
    schedule.every().day.at("08:00", "America/New_York").do(
        _run_scheduled_premarket, tickers=tickers, provider=requested_provider, alert_policy=alert_policy
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
    parser.add_argument(
        "--alert-cooldown-minutes",
        type=int,
        default=None,
        help="Default alert cooldown in minutes (overrides ALERT_COOLDOWN_MINUTES env var).",
    )
    parser.add_argument(
        "--disable-alert-cooldown",
        action="store_true",
        help="Send every eligible alert without cooldown.",
    )
    parser.add_argument(
        "--alert-state-path",
        default=None,
        help="Path to the isolated alert cooldown SQLite database (overrides ALERT_STATE_PATH).",
    )
    args = parser.parse_args()

    settings = load_runtime_settings()
    try:
        alert_config = settings.alert_cooldown
        overrides: dict[str, Any] = {}
        if args.alert_cooldown_minutes is not None:
            overrides["default_minutes"] = args.alert_cooldown_minutes
        if args.disable_alert_cooldown:
            overrides["enabled"] = False
        if args.alert_state_path is not None:
            overrides["state_path"] = Path(args.alert_state_path)
        if overrides:
            alert_config = dataclasses.replace(alert_config, **overrides)
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    alert_policy = AlertPolicy(alert_config, settings=settings)

    if args.interval > 0:
        start_loop(
            DEFAULT_WATCHLIST, args.timeframe, args.interval, args.min_score,
            args.provider, max_retries=args.max_retries, fallback_order=args.fallback_order,
            market_hours_only=args.market_hours_only,
            alert_policy=alert_policy,
        )
    else:
        run_once(
            DEFAULT_WATCHLIST, args.timeframe, args.min_score, args.provider,
            max_retries=args.max_retries, fallback_order=args.fallback_order,
            market_hours_only=args.market_hours_only,
            alert_policy=alert_policy,
            settings=settings,
        )
