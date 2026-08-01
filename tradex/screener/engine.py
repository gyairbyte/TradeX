"""
Runs all three signal scorers across a watchlist and returns ranked results.
"""
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from tradex.data.fetcher import (
    FetchAttempt,
    FetchPolicy,
    ProviderDataUnavailableError,
    ProviderError,
    ProviderResponseError,
    fetch_multi_report,
    resolve_provider,
)
from tradex.earnings import days_until_earnings
from tradex.signals import intraday, long_term, short_term

SIGNAL_MAP = {
    "intraday": (intraday.score, "intraday"),
    "short":    (short_term.score, "short"),
    "long":     (long_term.score, "long"),
}

# Concurrent workers for the per-ticker scan loop. Schwab handles this fine;
# yfinance is more rate-limit-prone so we keep it moderate.
DEFAULT_WORKERS = 12


@dataclass
class ScanReport:
    """Structured result of a screener run, including provenance and failures."""

    results: pd.DataFrame
    requested_provider: str
    actual_provider: str | None
    fallback_used: bool
    providers_attempted: tuple[str, ...]
    failures: dict[str, ProviderError]
    total_requested: int
    total_fetch_attempted: int
    total_fetched: int
    total_scored: int
    total_signals: int
    total_below_threshold: int
    total_insufficient_data: int
    total_earnings_excluded: int
    earnings_failures: dict[str, ProviderError] = field(default_factory=dict)
    fetch_failures: dict[str, ProviderError] = field(default_factory=dict)
    scoring_failures: dict[str, ProviderError] = field(default_factory=dict)
    total_fetch_eligible: int = 0
    total_retries: int = 0
    attempt_log: list[FetchAttempt] = field(default_factory=list)


def run_with_report(
    tickers: list[str],
    timeframe: str = "intraday",
    min_score: int = 40,
    exclude_earnings_within: int | None = None,
    max_workers: int = DEFAULT_WORKERS,
    progress: Callable[[int, int], None] | None = None,
    status: Callable[[str], None] | None = None,
    provider: str | None = None,
    earnings_source: str | None = None,
    policy: FetchPolicy | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> ScanReport:
    """Run the screener and return a structured report.

    The report distinguishes valid zero-signal scans, earnings-source failures,
    OHLCV provider failures, and scoring failures; tracks the actual provider used
    (including fallback); and preserves accurate provenance on every result row.
    """
    if timeframe not in SIGNAL_MAP:
        raise ValueError(f"timeframe must be one of {list(SIGNAL_MAP)}")

    scorer, tf_key = SIGNAL_MAP[timeframe]
    requested_provider = resolve_provider(provider)
    effective_policy = policy or FetchPolicy.build()

    total_earnings_excluded = 0
    eligible_tickers: list[str] = []
    earnings_failures: dict[str, ProviderError] = {}
    days_map: dict[str, int | None] = {}

    for ticker in tickers:
        try:
            days_to_er = days_until_earnings(ticker, source=earnings_source)
            days_map[ticker] = days_to_er
        except Exception:  # noqa: BLE001
            earnings_failures[ticker] = ProviderDataUnavailableError(
                f"Earnings lookup failed for {ticker}"
            )
            continue

        if (
            exclude_earnings_within is not None
            and days_to_er is not None
            and 0 <= days_to_er <= exclude_earnings_within
        ):
            total_earnings_excluded += 1
            continue

        eligible_tickers.append(ticker)

    fetch_report = fetch_multi_report(
        eligible_tickers,
        tf_key,
        provider=requested_provider,
        policy=effective_policy,
        sleeper=sleeper,
        progress=progress,
        status=status,
        max_workers=max_workers,
    )

    actual_provider = fetch_report.actual_provider
    fallback_used = fetch_report.fallback_used
    providers_attempted = fetch_report.providers_attempted
    total_fetch_attempted = fetch_report.total_fetch_attempted
    total_fetched = fetch_report.total_fetched

    rows: list[dict] = []
    total_scored = 0
    total_below_threshold = 0
    total_insufficient_data = 0
    fetch_failures: dict[str, ProviderError] = {}
    scoring_failures: dict[str, ProviderError] = {}

    for ticker, df in fetch_report.data.items():
        if len(df) < 30:
            total_insufficient_data += 1
            fetch_failures[ticker] = ProviderDataUnavailableError(
                f"Insufficient OHLCV data for {ticker} ({timeframe})"
            )
            continue

        try:
            result = scorer(df)
        except Exception:  # noqa: BLE001
            scoring_failures[ticker] = ProviderResponseError(
                f"Scoring failed for {ticker} ({timeframe})"
            )
            continue

        total_scored += 1
        if result["score"] < min_score:
            total_below_threshold += 1
            continue

        rows.append({
            "ticker": ticker,
            "score": result["score"],
            "last_close": result["last_close"],
            "volume_ratio": round(result["volume_ratio"], 2),
            "rsi": round(result["rsi"], 1),
            "days_until_earnings": days_map.get(ticker),
            "reasons": " | ".join(result["reasons"]),
            "provider": actual_provider or requested_provider,
        })

    # Carry forward any fetch failures reported by the batch fetcher.
    fetch_failures.update(fetch_report.failures)
    failures = {**fetch_failures, **scoring_failures}

    if not rows:
        results = pd.DataFrame(columns=[
            "ticker", "score", "last_close", "volume_ratio", "rsi",
            "days_until_earnings", "reasons", "provider",
        ])
    else:
        results = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)

    return ScanReport(
        results=results,
        requested_provider=requested_provider,
        actual_provider=actual_provider,
        fallback_used=fallback_used,
        providers_attempted=providers_attempted,
        failures=failures,
        total_requested=len(tickers),
        total_fetch_eligible=len(eligible_tickers),
        total_fetch_attempted=total_fetch_attempted,
        total_retries=fetch_report.retries,
        total_fetched=total_fetched,
        total_scored=total_scored,
        total_signals=len(rows),
        total_below_threshold=total_below_threshold,
        total_insufficient_data=total_insufficient_data,
        total_earnings_excluded=total_earnings_excluded,
        earnings_failures=earnings_failures,
        fetch_failures=fetch_failures,
        scoring_failures=scoring_failures,
        attempt_log=fetch_report.attempt_log,
    )


def run(
    tickers: list[str],
    timeframe: str = "intraday",
    min_score: int = 40,
    exclude_earnings_within: int | None = None,
    max_workers: int = DEFAULT_WORKERS,
    progress: Callable[[int, int], None] | None = None,
    provider: str | None = None,
    earnings_source: str | None = None,
    policy: FetchPolicy | None = None,
) -> pd.DataFrame:
    """Compatibility wrapper that returns the signal DataFrame from ``run_with_report``."""
    report = run_with_report(
        tickers,
        timeframe=timeframe,
        min_score=min_score,
        exclude_earnings_within=exclude_earnings_within,
        max_workers=max_workers,
        progress=progress,
        provider=provider,
        earnings_source=earnings_source,
        policy=policy,
    )
    return report.results
