"""
Runs all three signal scorers across a watchlist and returns ranked results.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from tradex.config import TradeXSettings, load_runtime_settings
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
    "short": (short_term.score, "short"),
    "long": (long_term.score, "long"),
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
    "strategy_id",
    "strategy_version",
    "primary_setup",
    "matched_setups",
    "state",
    "component_scores",
    "trigger",
    "invalidation",
    "atr_pct",
    "return_5",
    "return_20",
    "return_60",
    "qualified",
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
    observations: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=OBSERVATION_COLUMNS)
    )
    min_score: int = 0

    def validate(self, expected_tickers: list[str] | None = None) -> None:
        """Validate that observations, results, and report counters are consistent."""
        obs = self.observations
        if len(obs) != self.total_requested:
            raise ValueError(
                f"Observation count mismatch: {len(obs)} rows for total_requested={self.total_requested}"
            )

        if expected_tickers is not None:
            normalized_expected = list(
                dict.fromkeys(_normalize_ticker(t) for t in expected_tickers)
            )
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
                raise ValueError(
                    f"Mixed providers in successful observations: {sorted(scored_providers)}"
                )

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

            # Report counters must match the observation statuses that produce them.
            signal_count = int((obs["status"] == ObservationStatus.SIGNAL.value).sum())
            below_count = int((obs["status"] == ObservationStatus.BELOW_THRESHOLD.value).sum())
            expected_counters = {
                "total_signals": signal_count,
                "total_below_threshold": below_count,
                "total_earnings_excluded": int(
                    (obs["status"] == ObservationStatus.EARNINGS_EXCLUDED.value).sum()
                ),
                "total_insufficient_data": int(
                    (obs["status"] == ObservationStatus.INSUFFICIENT_DATA.value).sum()
                ),
            }
            for field, expected in expected_counters.items():
                actual = getattr(self, field)
                if actual != expected:
                    raise ValueError(
                        f"Report counter '{field}' is {actual} but observations imply {expected}"
                    )
            expected_total_scored = signal_count + below_count
            if self.total_scored != expected_total_scored:
                raise ValueError(
                    f"Report counter 'total_scored' is {self.total_scored} but observations imply {expected_total_scored}"
                )

            # Results must mirror the signal observations bidirectionally and row-completely.
            if len(self.results) != len(signal_obs):
                raise ValueError(
                    f"results DataFrame has {len(self.results)} rows but {len(signal_obs)} signal observations"
                )
            result_by_ticker = self.results.set_index("ticker")
            signal_by_ticker = signal_obs.set_index("ticker")
            result_tickers = set(result_by_ticker.index)
            signal_tickers = set(signal_by_ticker.index)
            if result_tickers != signal_tickers:
                raise ValueError(
                    f"results tickers {sorted(result_tickers)} do not match signal observation tickers {sorted(signal_tickers)}"
                )

            compare_cols = (
                "score",
                "last_close",
                "volume_ratio",
                "rsi",
                "days_until_earnings",
                "reasons",
                "provider",
            )
            for ticker in result_tickers:
                result_row = result_by_ticker.loc[ticker]
                signal_row = signal_by_ticker.loc[ticker]
                for col in compare_cols:
                    a = result_row[col]
                    b = signal_row[col]
                    a_missing = pd.isna(a)
                    b_missing = pd.isna(b)
                    if a_missing != b_missing:
                        raise ValueError(
                            f"Signal/results mismatch for {ticker} column '{col}': missing {a_missing} vs {b_missing}"
                        )
                    if not a_missing and a != b:
                        raise ValueError(
                            f"Signal/results mismatch for {ticker} column '{col}': {a!r} vs {b!r}"
                        )


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
    strategy_id: str | None = None,
    strategy_version: str | None = None,
    primary_setup: str | None = None,
    matched_setups: list[str] | None = None,
    state: str | None = None,
    component_scores: dict | None = None,
    trigger: str | None = None,
    invalidation: str | None = None,
    atr_pct: float | None = None,
    return_5: float | None = None,
    return_20: float | None = None,
    return_60: float | None = None,
    qualified: bool | None = None,
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
        "strategy_id": _safe_str(strategy_id),
        "strategy_version": _safe_str(strategy_version),
        "primary_setup": _safe_str(primary_setup),
        "matched_setups": matched_setups if matched_setups is not None else None,
        "state": _safe_str(state),
        "component_scores": component_scores,
        "trigger": _safe_str(trigger),
        "invalidation": _safe_str(invalidation),
        "atr_pct": _clean_numeric(atr_pct),
        "return_5": _clean_numeric(return_5),
        "return_20": _clean_numeric(return_20),
        "return_60": _clean_numeric(return_60),
        "qualified": qualified,
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
    *,
    settings: TradeXSettings | None = None,
) -> ScanReport:
    """Run the screener and return a structured report.

    The report distinguishes valid zero-signal scans, earnings-source failures,
    OHLCV provider failures, and scoring failures; tracks the actual provider used
    (including fallback); and preserves accurate provenance on every observation.
    """
    if settings is None:
        settings = load_runtime_settings()
    if timeframe not in SIGNAL_MAP:
        raise ValueError(f"timeframe must be one of {list(SIGNAL_MAP)}")

    scorer, tf_key = SIGNAL_MAP[timeframe]
    requested_provider = resolve_provider(provider, settings=settings)
    effective_policy = policy or FetchPolicy.build(settings=settings)

    unique_tickers = list(dict.fromkeys(_normalize_ticker(t) for t in tickers))

    total_earnings_excluded = 0
    eligible_tickers: list[str] = []
    earnings_failures: dict[str, ProviderError] = {}
    earnings_err_map: dict[str, ProviderError] = {}
    days_map: dict[str, int | None] = {}
    observations: list[dict] = []
    filter_enabled = exclude_earnings_within is not None and exclude_earnings_within > 0

    for ticker in unique_tickers:
        days_to_er = None
        earnings_err = None
        try:
            days_to_er = days_until_earnings(ticker, source=earnings_source, settings=settings)
        except ProviderError as exc:
            earnings_err = exc
        except Exception as exc:  # noqa: BLE001
            earnings_err = ProviderDataUnavailableError(f"Earnings lookup failed for {ticker}")

        if earnings_err is not None:
            earnings_failures[ticker] = earnings_err
            earnings_err_map[ticker] = earnings_err
            days_map[ticker] = None
        else:
            days_map[ticker] = days_to_er

        if filter_enabled:
            if earnings_err is not None or days_to_er is None:
                err = earnings_err or ProviderDataUnavailableError(
                    f"Earnings date unknown for {ticker}; cannot evaluate exclusion window"
                )
                earnings_failures[ticker] = err
                observations.append(
                    _build_observation_row(ticker, ObservationStatus.EARNINGS_FAILURE, error=err)
                )
                continue
            if 0 <= days_to_er <= exclude_earnings_within:
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
        settings=settings,
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

        min_bars = 220 if timeframe == "long" else 30
        if len(df) < min_bars:
            total_insufficient_data += 1
            err = ProviderDataUnavailableError(
                f"Insufficient OHLCV data for {ticker} ({timeframe}): {len(df)} bars < {min_bars} required"
            )
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

        if timeframe == "long" and result.get("insufficient_data", False):
            total_insufficient_data += 1
            err = ProviderDataUnavailableError(
                f"Insufficient or non-finite indicator inputs for {ticker} ({timeframe})"
            )
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

        total_scored += 1
        reasons = _format_reasons(result)
        obs_provider = actual_provider or requested_provider
        obs_earnings_err = earnings_err_map.get(ticker)

        # Canonicalize the scored row once so both `results` and the signal
        # observation share identical values and pass validation.
        canonical = {
            "ticker": ticker,
            "score": int(result["score"]),
            "last_close": round(float(result["last_close"]), 4),
            "volume_ratio": round(float(result["volume_ratio"]), 2),
            "rsi": round(float(result["rsi"]), 1),
            "days_until_earnings": days_map.get(ticker),
            "reasons": reasons,
            "provider": obs_provider,
            "strategy_id": result.get("strategy_id"),
            "strategy_version": result.get("strategy_version"),
            "primary_setup": result.get("primary_setup"),
            "matched_setups": result.get("matched_setups"),
            "state": result.get("state"),
            "component_scores": result.get("component_scores"),
            "trigger": result.get("trigger"),
            "invalidation": result.get("invalidation"),
            "atr_pct": round(float(result["atr_pct"]), 4) if result.get("atr_pct") is not None else None,
            "return_5": round(float(result["return_5"]), 4) if result.get("return_5") is not None else None,
            "return_20": round(float(result["return_20"]), 4) if result.get("return_20") is not None else None,
            "return_60": round(float(result["return_60"]), 4) if result.get("return_60") is not None else None,
            "qualified": result.get("qualified"),
        }

        if timeframe == "long":
            effective_min = max(60, min_score)
            is_signal = (
                bool(result.get("qualified", False))
                and (result.get("state") is not None)
                and (result.get("score", 0) >= effective_min)
            )
        else:
            is_signal = result["score"] >= min_score

        if not is_signal:
            total_below_threshold += 1
            observations.append(
                _build_observation_row(
                    ticker,
                    ObservationStatus.BELOW_THRESHOLD,
                    score=canonical["score"],
                    last_close=canonical["last_close"],
                    volume_ratio=canonical["volume_ratio"],
                    rsi=canonical["rsi"],
                    days_until_earnings=canonical["days_until_earnings"],
                    reasons=canonical["reasons"],
                    provider=canonical["provider"],
                    strategy_id=canonical["strategy_id"],
                    strategy_version=canonical["strategy_version"],
                    primary_setup=canonical["primary_setup"],
                    matched_setups=canonical["matched_setups"],
                    state=canonical["state"],
                    component_scores=canonical["component_scores"],
                    trigger=canonical["trigger"],
                    invalidation=canonical["invalidation"],
                    atr_pct=canonical["atr_pct"],
                    return_5=canonical["return_5"],
                    return_20=canonical["return_20"],
                    return_60=canonical["return_60"],
                    qualified=canonical["qualified"],
                    error=obs_earnings_err,
                )
            )
            continue

        rows.append(canonical)

        observations.append(
            _build_observation_row(
                ticker,
                ObservationStatus.SIGNAL,
                score=canonical["score"],
                last_close=canonical["last_close"],
                volume_ratio=canonical["volume_ratio"],
                rsi=canonical["rsi"],
                days_until_earnings=canonical["days_until_earnings"],
                reasons=canonical["reasons"],
                provider=canonical["provider"],
                strategy_id=canonical["strategy_id"],
                strategy_version=canonical["strategy_version"],
                primary_setup=canonical["primary_setup"],
                matched_setups=canonical["matched_setups"],
                state=canonical["state"],
                component_scores=canonical["component_scores"],
                trigger=canonical["trigger"],
                invalidation=canonical["invalidation"],
                atr_pct=canonical["atr_pct"],
                return_5=canonical["return_5"],
                return_20=canonical["return_20"],
                return_60=canonical["return_60"],
                qualified=canonical["qualified"],
                error=obs_earnings_err,
            )
        )

    # Carry forward any fetch failures reported by the batch fetcher that were
    # not already captured (e.g. tickers that never reached the per-ticker loop).
    fetch_failures.update(
        {t: e for t, e in fetch_report.failures.items() if t not in fetch_failures}
    )
    failures = {**fetch_failures, **scoring_failures}

    if not rows:
        base_cols = [
            "ticker",
            "score",
            "last_close",
            "volume_ratio",
            "rsi",
            "days_until_earnings",
            "reasons",
            "provider",
        ]
        if timeframe == "long":
            base_cols.extend(
                [
                    "strategy_id",
                    "strategy_version",
                    "primary_setup",
                    "matched_setups",
                    "state",
                    "component_scores",
                    "trigger",
                    "invalidation",
                    "atr_pct",
                    "return_5",
                    "return_20",
                    "return_60",
                    "qualified",
                ]
            )
        results = pd.DataFrame(columns=base_cols)
    else:
        if timeframe == "long":
            STATE_RANK = {"ENTER NOW": 0, "ARMED": 1, "QUALIFIED WAITLIST": 2}
            df_res = pd.DataFrame(rows)
            df_res["_state_rank"] = df_res["state"].map(lambda s: STATE_RANK.get(s, 99))
            results = (
                df_res.sort_values(
                    by=["_state_rank", "score", "ticker"],
                    ascending=[True, False, True],
                )
                .drop(columns=["_state_rank"])
                .reset_index(drop=True)
            )
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
    *,
    settings: TradeXSettings | None = None,
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
        settings=settings,
    )
    return report.results


LONG_FOCUS_CAPS: dict[str, int] = {
    "ENTER NOW": 7,
    "ARMED": 12,
    "QUALIFIED WAITLIST": 12,
}
MAX_LONG_FOCUS_DISPLAY: int = 31


def build_long_focus_list(results: pd.DataFrame) -> pd.DataFrame:
    """Return a display-capped focus list of long opportunities (7 / 12 / 12, max 31).

    Caps:
      ENTER NOW: at most 7
      ARMED: at most 12
      QUALIFIED WAITLIST: at most 12
      Total combined: at most 31

    Accepts the full ranked long result set.
    Does NOT modify or truncate telemetry in the underlying ScanReport.
    """
    if results.empty:
        return results.copy()

    parts: list[pd.DataFrame] = []
    for state_name, cap in LONG_FOCUS_CAPS.items():
        if "state" in results.columns:
            subset = results[results["state"] == state_name]
            if not subset.empty:
                parts.append(subset.iloc[:cap])

    if not parts:
        return results.iloc[:MAX_LONG_FOCUS_DISPLAY].copy()

    focus_df = pd.concat(parts, ignore_index=True)
    if len(focus_df) > MAX_LONG_FOCUS_DISPLAY:
        focus_df = focus_df.iloc[:MAX_LONG_FOCUS_DISPLAY]
    return focus_df.reset_index(drop=True)
