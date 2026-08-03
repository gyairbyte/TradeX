"""Paired executable backtests for baseline and selected candidate policies."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from tradex.backtest.engine import run_backtest
from tradex.backtest.models import BacktestConfig, BacktestDataError
from tradex.market.context import compute_short_term_context
from tradex.market.models import ShortContextPolicy
from tradex.research.score_validation.manifest import load_manifest
from tradex.research.score_validation.models import ScoreValidationConfig, Split
from tradex.research.short_context.alignment import load_ticker_df
from tradex.research.short_context.models import (
    PairedBacktestResult,
    ShortContextSpec,
    ValidationError,
)
from tradex.signals.short_term import score as short_term_score
from tradex.signals.weights import ShortWeights


def run_paired_backtests(
    manifest_path: str | Any,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
    selected_policy: str | None,
) -> PairedBacktestResult:
    """Run paired baseline/candidate backtests for every holdout target ticker.

    Only bars within the manifest's holdout split are used for signal evaluation,
    entries, exits, and metrics. Earlier bars are retained only as indicator
    warmup.
    """
    manifest = load_manifest(manifest_path)
    holdout_tickers = [t for t in spec.target_tickers]

    baseline_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []

    # Preload proxy data.
    proxy_dfs: dict[str, pd.DataFrame] = {}
    for proxy in spec.proxy_tickers():
        proxy_dfs[proxy] = load_ticker_df(manifest, proxy)

    holdout = manifest.splits["holdout"]
    min_warmup = max(config.warmup_bars, 50)

    for ticker in holdout_tickers:
        ticker_df = load_ticker_df(manifest, ticker)
        entry = next(e for e in manifest.entries if e.ticker == ticker)
        bars, warmup = _holdout_window_bars(ticker_df, holdout, min_warmup=min_warmup)
        backtest_config = BacktestConfig(
            min_score=spec.baseline_score_threshold,
            warmup_bars=warmup,
            max_holding_bars=spec.primary_horizon_bars,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            commission_bps=spec.commission_bps,
            slippage_bps=spec.primary_slippage_bps,
            initial_capital=100_000.0,
            intrabar_policy="stop_first",
        )

        ctx = spec.ticker_context[ticker]
        market_proxy = ctx["market_proxy"]
        sector_proxy = ctx.get("sector_proxy")
        market_df = proxy_dfs[market_proxy]
        sector_df = proxy_dfs.get(sector_proxy) if sector_proxy else None

        baseline_fn = _make_baseline_score_fn()
        baseline_result = run_backtest(
            ticker=ticker,
            bars=bars,
            score_fn=baseline_fn,
            config=backtest_config,
            strategy_name="short_term_baseline",
            data_source=entry.data_source,
            weight_snapshot=_short_weights_snapshot(),
        )
        baseline_rows.append(_backtest_metrics_to_dict(ticker, baseline_result))

        if selected_policy is not None:
            policy = _policy_from_string(selected_policy)
            candidate_fn = _make_candidate_score_fn(
                ticker=ticker,
                market_df=market_df,
                sector_df=sector_df,
                market_proxy=market_proxy,
                sector_proxy=sector_proxy,
                policy=policy,
            )
            candidate_result = run_backtest(
                ticker=ticker,
                bars=bars,
                score_fn=candidate_fn,
                config=backtest_config,
                strategy_name=f"short_term_{policy.value}",
                data_source=entry.data_source,
                weight_snapshot=_short_weights_snapshot(),
            )
            candidate_rows.append(_backtest_metrics_to_dict(ticker, candidate_result))

    baseline_df = pd.DataFrame(baseline_rows, columns=_BACKTEST_METRICS_COLS)
    candidate_df = pd.DataFrame(candidate_rows, columns=_BACKTEST_METRICS_COLS)

    failure_reasons = _backtest_gate_failures(baseline_df, candidate_df, spec)
    passed = not failure_reasons and selected_policy is not None

    return PairedBacktestResult(
        passed=passed,
        baseline_metrics=baseline_df,
        candidate_metrics=candidate_df,
        failure_reasons=failure_reasons,
    )


def _make_baseline_score_fn() -> Callable[[pd.DataFrame], dict[str, Any]]:
    """Return the production short-term scorer with a fresh default weight snapshot."""

    def _score_fn(df: pd.DataFrame) -> dict[str, Any]:
        return short_term_score(df, weights=ShortWeights())

    return _score_fn


def _make_candidate_score_fn(
    ticker: str,
    market_df: pd.DataFrame,
    sector_df: pd.DataFrame | None,
    market_proxy: str,
    sector_proxy: str | None,
    policy: ShortContextPolicy,
) -> Callable[[pd.DataFrame], dict[str, Any]]:
    """Return a point-in-time candidate score function.

    The returned score is the original base score when the context is eligible,
    and zero (below the default threshold) when it is not. This preserves the
    base score and context metadata in the signal record without rewriting the
    public scorer.
    """

    def _score_fn(df: pd.DataFrame) -> dict[str, Any]:
        as_of = df.index[-1].to_pydatetime()
        context = compute_short_term_context(
            as_of=as_of,
            ticker_df=df,
            market_proxy=market_proxy,
            market_df=market_df,
            sector_proxy=sector_proxy,
            sector_df=sector_df,
        )
        result = short_term_score(
            df,
            weights=ShortWeights(),
            context=context,
            context_policy=policy,
        )
        if not result["context_eligible"]:
            result = dict(result)
            result["score"] = 0
        return result

    return _score_fn


def _policy_from_string(value: str) -> ShortContextPolicy:
    try:
        return ShortContextPolicy(value)
    except ValueError as exc:
        raise ValidationError(f"unknown policy: {value}") from exc


def _holdout_window_bars(
    ticker_df: pd.DataFrame,
    holdout: Split,
    *,
    min_warmup: int,
) -> tuple[pd.DataFrame, int]:
    """Return bars trimmed to the holdout window plus indicator warmup.

    The returned DataFrame ends at the last bar on or before ``holdout.end``.
    Only ``min_warmup`` bars before the first holdout bar are retained as
    indicator warmup, so development/validation price changes far from the
    holdout boundary cannot alter holdout backtest metrics.
    """
    if ticker_df.empty or ticker_df.index.tz is None:
        raise BacktestDataError("Bars must be non-empty and timezone-aware")

    dates = ticker_df.index.tz_convert("UTC").date
    mask = (dates >= holdout.start) & (dates <= holdout.end)
    holdout_indices = mask.nonzero()[0]
    if holdout_indices.size == 0:
        raise BacktestDataError(f"No bars within holdout window {holdout.start} to {holdout.end}")

    end_idx = int(holdout_indices[-1])
    start_idx = int(holdout_indices[0])
    if start_idx + 1 < min_warmup:
        raise BacktestDataError(
            f"Holdout window starts at index {start_idx} but {min_warmup} warmup bars are required"
        )

    slice_start = max(0, start_idx - min_warmup + 1)
    warmup = start_idx - slice_start + 1
    bars = ticker_df.iloc[slice_start : end_idx + 1]
    if len(bars) < warmup:
        raise BacktestDataError("Trimmed holdout window is shorter than required warmup")

    return bars, warmup


def _short_weights_snapshot() -> dict[str, Any]:
    return {k: int(v) for k, v in ShortWeights().__dict__.items()}


_BACKTEST_METRICS_COLS = [
    "ticker",
    "data_source",
    "total_trades",
    "expectancy_pct",
    "total_return_pct",
    "profit_factor",
    "max_drawdown_pct",
    "sharpe_ratio",
]


def _backtest_metrics_to_dict(ticker: str, result) -> dict[str, Any]:
    m = result.metrics
    return {
        "ticker": ticker,
        "data_source": result.data_source,
        "total_trades": m.total_trades,
        "expectancy_pct": m.expectancy_pct,
        "total_return_pct": m.total_return_pct,
        "profit_factor": m.profit_factor,
        "max_drawdown_pct": m.max_drawdown_pct,
        "sharpe_ratio": m.sharpe_ratio,
    }


def _backtest_gate_failures(
    baseline_df: pd.DataFrame,
    candidate_df: pd.DataFrame,
    spec: ShortContextSpec,
) -> list[str]:
    """Evaluate the executable-backtest promotion gate."""
    failures: list[str] = []

    if candidate_df.empty:
        failures.append("no candidate backtest results")
        return failures

    if baseline_df.empty:
        failures.append("no baseline backtest results")
        return failures

    # Compare only tickers that produced a candidate trade.
    compared = pd.merge(
        baseline_df,
        candidate_df,
        on="ticker",
        suffixes=("_baseline", "_candidate"),
        how="inner",
    )
    if compared.empty:
        failures.append("no overlapping tickers between baseline and candidate")
        return failures

    eligible = compared[compared["total_trades_candidate"] > 0]
    if eligible.empty:
        failures.append("candidate trade count is zero")
        return failures

    if len(eligible) == 1:
        failures.append("improvement produced by only one ticker")

    # Median candidate expectancy across eligible tickers exceeds baseline.
    if (
        eligible["expectancy_pct_candidate"].median()
        <= eligible["expectancy_pct_baseline"].median()
    ):
        failures.append("median candidate expectancy not greater than baseline")

    # Equal-weighted mean candidate expectancy exceeds baseline.
    if (
        eligible["expectancy_pct_candidate"].mean()
        <= eligible["expectancy_pct_baseline"].mean()
    ):
        failures.append("mean candidate expectancy not greater than baseline")

    # Median total return not lower than baseline.
    if (
        eligible["total_return_pct_candidate"].median()
        < eligible["total_return_pct_baseline"].median()
    ):
        failures.append("median candidate total return lower than baseline")

    # Median max drawdown not worse by more than two percentage points.
    median_dd_candidate = eligible["max_drawdown_pct_candidate"].median()
    median_dd_baseline = eligible["max_drawdown_pct_baseline"].median()
    if median_dd_candidate < median_dd_baseline - 2.0:
        failures.append("candidate max drawdown worse by more than 2 percentage points")

    return failures
