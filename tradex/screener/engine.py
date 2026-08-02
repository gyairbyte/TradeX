"""
Runs all three signal scorers across a watchlist and returns ranked results.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

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


class ObservationStatus(str, Enum):
    """Stable status for a single screener observation."""

    SIGNAL = "signal"
    BELOW_THRESHOLD = "below_threshold"
    EARNINGS_EXCLUDED = "earnings_excluded"
    EARNINGS_FAILURE = "earnings_failure"
    FETCH_FAILURE = "fetch_failure"
    INSUFFICIENT_DATA = "insufficient_data"
    SCORING_FAILURE = "scoring_failure"


OBSERVATION_COLUMNS = [
    "ticker",
    "status",
    "score",
    "last_close",
    "volume_ratio",
    "rsi",
    "days_until_earnings",
    "reasons",
    "provider",
    "error_category",
    "error_message",
]

SUCCESSFUL_STATUSES = {
    ObservationStatus.SIGNAL,
    ObservationStatus.BELOW_THRESHOLD,
    ObservationStatus.EARNINGS_EXCLUDED,
}

FAILURE_STATUSES = {
    ObservationStatus.EARNINGS_FAILURE,
    ObservationStatus.FETCH_FAILURE,
    ObservationStatus.INSUFFICIENT_DATA,
    ObservationStatus.SCORING_FAILURE,
}


def _safe_str(value) -> str | None:
    """Return a safe string or None for nullable values."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _clean_numeric(value):
    """Return a Python scalar or None, converting NaN/NA to None."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and pd.isna(value):
        return None
    return value


def _normalize_ticker(ticker: str) -> str:
    return str(ticker).strip().upper()


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
    observations: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=OBSERVATION_COLUMNS))
    min_score: int = 0

    def validate(self, expected_tickers: list[str] | None = None) -> None:
        """Validate that observations are internally consistent and complete."""
        obs = self.observations
        if len(obs) != self.total_requested:
            raise ValueError(
                f"Observation count mismatch: {len(obs)} rows for total_requested={self.total_requested}"
            )

        if expected_tickers is not None:
            normalized_expected = list(dict.fromkeys(_normalize_ticker(t) for t in expected_tickers))
            if len(obs) != len(normalized_expected):
                raise ValueError(
                    f"Observation count mismatch: {len(obs)} rows for {len(normalized_expected)} unique tickers"
                )
            obs_tickers = set(obs["ticker"].tolist()) if not obs.empty else set()
            if obs_tickers != set(normalized_expected):
                raise ValueError("Observation tickers do not match requested tickers")

        if not obs.empty:
            if obs["ticker"].duplicated().any():
                raise ValueError("Duplicate ticker observations")
            unknown = set(obs["status"].unique()) - set(ObservationStatus)
            if unknown:
                raise ValueError(f"Unknown observation statuses: {sorted(unknown)}")

            signal_obs = obs[obs["status"] == ObservationStatus.SIGNAL]
            for col in ("score", "last_close", "volume_ratio", "rsi", "reasons", "provider"):
                missing = signal_obs[col].isna().any()
                if missing:
                    raise ValueError(f"Signal observation missing required column '{col}'")

            # Successful observations must share the actual provider (earnings-excluded rows have no provider).
            scored = obs[obs["status"].isin(SUCCESSFUL_STATUSES)]
            scored_providers = set(scored["provider"].dropna().unique())
            if len(scored_providers) > 1:
                raise ValueError(f"Mixed providers in successful observations: {sorted(scored_providers)}")

            if self.actual_provider is not None:
                for provider in scored_providers:
                    if provider != self.actual_provider:
                        raise ValueError(
                            f"Observation provider {provider!r} does not match report.actual_provider {self.actual_provider!r}"
                        )
            else:
                if scored_providers:
                    raise ValueError(
                        "report.actual_provider is None but scored observations have provider set"
                    )

            # results must mirror the signal observations exactly.
            if not self.results.empty:
                result_tickers = set(self.results["ticker"].tolist())
                if result_tickers != set(signal_obs["ticker"].tolist()):
                    raise ValueError("results DataFrame does not match signal observations")


def _build_observation_row(
    ticker: str,
    status: ObservationStatus,
    *,
    score: int | None = None,
    last_close: float | None = None,
    volume_ratio: float | None = None,
    rsi: float | None = None,
    days_until_earnings: int | None = None,
    reasons: str | None = None,
    provider: str | None = None,
    error: ProviderError | None = None,
) -> dict:
    """Create a single normalized observation row."""
    return {
        "ticker": _normalize_ticker(ticker),
        "status": status.value,
        "score": _clean_numeric(score),
        "last_close": _clean_numeric(last_close),
        "volume_ratio": _clean_numeric(volume_ratio),
        "rsi": _clean_numeric(rsi),
        "days_until_earnings": _clean_numeric(days_until_earnings),
        "reasons": _safe_str(reasons),
        "provider": _safe_str(provider),
        "error_category": type(error).__name__ if error is not None else None,
        "error_message": _safe_str(str(error)) if error is not None else None,
    }


def _format_reasons(result: dict) -> str:
    reasons = result.get("reasons") or []
    if isinstance(reasons, str):
        return reasons
    if isinstance(reasons, (list, tuple)):
        return " | ".join(str(r) for r in reasons)
    return str(reasons)


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
    (including fallback); and preserves accurate provenance on every observation.
    """
    if timeframe not in SIGNAL_MAP:
        raise ValueError(f"timeframe must be one of {list(SIGNAL_MAP)}")

    scorer, tf_key = SIGNAL_MAP[timeframe]
    requested_provider = resolve_provider(provider)
    effective_policy = policy or FetchPolicy.build()

    unique_tickers = list(dict.fromkeys(_normalize_ticker(t) for t in tickers))

    total_earnings_excluded = 0
    eligible_tickers: list[str] = []
    earnings_failures: dict[str, ProviderError] = {}
    days_map: dict[str, int | None] = {}
    observations: list[dict] = []

    for ticker in unique_tickers:
        try:
            days_to_er = days_until_earnings(ticker, source=earnings_source)
            days_map[ticker] = days_to_er
        except Exception:  # noqa: BLE001
            err = ProviderDataUnavailableError(f"Earnings lookup failed for {ticker}")
            earnings_failures[ticker] = err
            observations.append(_build_observation_row(ticker, ObservationStatus.EARNINGS_FAILURE, error=err))
            continue

        if (
            exclude_earnings_within is not None
            and days_to_er is not None
            and 0 <= days_to_er <= exclude_earnings_within
        ):
            total_earnings_excluded += 1
            observations.append(
                _build_observation_row(
                    ticker,
                    ObservationStatus.EARNINGS_EXCLUDED,
                    days_until_earnings=days_to_er,
                )
            )
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

    for ticker in eligible_tickers:
        df = fetch_report.data.get(ticker)

        if df is None:
            err = fetch_report.failures.get(ticker) or ProviderDataUnavailableError(
                f"No usable OHLCV data for {ticker} ({timeframe})"
            )
            fetch_failures[ticker] = err
            observations.append(
                _build_observation_row(ticker, ObservationStatus.FETCH_FAILURE, error=err)
            )
            continue

        if len(df) < 30:
            total_insufficient_data += 1
            err = ProviderDataUnavailableError(f"Insufficient OHLCV data for {ticker} ({timeframe})")
            fetch_failures[ticker] = err
            observations.append(
                _build_observation_row(
                    ticker,
                    ObservationStatus.INSUFFICIENT_DATA,
                    provider=actual_provider or requested_provider,
                    error=err,
                )
            )
            continue

        try:
            result = scorer(df)
        except Exception:  # noqa: BLE001
            err = ProviderResponseError(f"Scoring failed for {ticker} ({timeframe})")
            scoring_failures[ticker] = err
            observations.append(
                _build_observation_row(
                    ticker,
                    ObservationStatus.SCORING_FAILURE,
                    provider=actual_provider or requested_provider,
                    error=err,
                )
            )
            continue

        total_scored += 1
        reasons = _format_reasons(result)
        obs_provider = actual_provider or requested_provider

        if result["score"] < min_score:
            total_below_threshold += 1
            observations.append(
                _build_observation_row(
                    ticker,
                    ObservationStatus.BELOW_THRESHOLD,
                    score=result["score"],
                    last_close=result["last_close"],
                    volume_ratio=result["volume_ratio"],
                    rsi=result["rsi"],
                    days_until_earnings=days_map.get(ticker),
                    reasons=reasons,
                    provider=obs_provider,
                )
            )
            continue

        rows.append({
            "ticker": ticker,
            "score": result["score"],
            "last_close": result["last_close"],
            "volume_ratio": round(result["volume_ratio"], 2),
            "rsi": round(result["rsi"], 1),
            "days_until_earnings": days_map.get(ticker),
            "reasons": reasons,
            "provider": obs_provider,
        })

        observations.append(
            _build_observation_row(
                ticker,
                ObservationStatus.SIGNAL,
                score=result["score"],
                last_close=result["last_close"],
                volume_ratio=result["volume_ratio"],
                rsi=result["rsi"],
                days_until_earnings=days_map.get(ticker),
                reasons=reasons,
                provider=obs_provider,
            )
        )

    # Carry forward any fetch failures reported by the batch fetcher that were
    # not already captured (e.g. tickers that never reached the per-ticker loop).
    fetch_failures.update(
        {t: e for t, e in fetch_report.failures.items() if t not in fetch_failures}
    )
    failures = {**fetch_failures, **scoring_failures}

    if not rows:
        results = pd.DataFrame(columns=[
            "ticker", "score", "last_close", "volume_ratio", "rsi",
            "days_until_earnings", "reasons", "provider",
        ])
    else:
        results = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)

    observations_df = pd.DataFrame(observations, columns=OBSERVATION_COLUMNS)
    report = ScanReport(
        results=results,
        requested_provider=requested_provider,
        actual_provider=actual_provider,
        fallback_used=fallback_used,
        providers_attempted=providers_attempted,
        failures=failures,
        total_requested=len(unique_tickers),
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
        observations=observations_df,
        min_score=min_score,
    )
    report.validate(expected_tickers=unique_tickers)
    return report


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
