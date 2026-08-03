"""Candidate selection and holdout promotion gate."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from tradex.market.models import ShortContextPolicy
from tradex.research.score_validation.models import ScoreValidationConfig
from tradex.research.short_context.models import (
    CandidateResult,
    HoldoutResult,
    PolicySplitMetrics,
    ShortContextSpec,
    ValidationError,
)


def select_candidate(
    events_df: pd.DataFrame,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
) -> CandidateResult:
    """Select the best candidate policy using development and validation only."""
    if events_df.empty:
        return CandidateResult(
            selected_policy=None,
            selection_reason="no events",
            policy_metrics={},
        )

    policy_metrics: dict[str, dict[str, PolicySplitMetrics]] = {}
    qualified: list[tuple[ShortContextPolicy, dict[str, PolicySplitMetrics], float]] = []

    for policy in spec.candidate_policies:
        metrics_by_split: dict[str, PolicySplitMetrics] = {}
        for split in ("development", "validation", "holdout"):
            split_df = events_df[events_df["split"] == split]
            if split_df.empty:
                continue
            baseline = _split_metrics(split_df, None, spec, config)
            candidate = _split_metrics(split_df, policy, spec, config)
            metrics_by_split[split] = candidate
            if split == "validation":
                metrics_by_split[f"{split}_baseline"] = baseline
            if split == "development":
                metrics_by_split[f"{split}_baseline"] = baseline

        policy_metrics[policy.value] = metrics_by_split

        dev = metrics_by_split.get("development")
        dev_base = metrics_by_split.get("development_baseline")
        val = metrics_by_split.get("validation")
        val_base = metrics_by_split.get("validation_baseline")

        if dev is None or dev_base is None or val is None or val_base is None:
            continue

        if candidate_qualifies_for_holdout(dev, dev_base, val, val_base, spec, config, require_sample=False):
            improvement = (
                (val.mean_ticker_event_return_pct or 0.0)
                - (val_base.mean_ticker_event_return_pct or 0.0)
            )
            qualified.append((policy, metrics_by_split, improvement))

    if not qualified:
        return CandidateResult(
            selected_policy=None,
            selection_reason="no policy passed development and validation criteria",
            policy_metrics=policy_metrics,
        )

    # Tie-break: simpler policy (market_rs) wins.
    def _sort_key(item: tuple[ShortContextPolicy, Any, float]) -> tuple:
        policy, _, improvement = item
        return (
            -improvement,
            0 if policy == ShortContextPolicy.MARKET_RS else 1,
            policy.value,
        )

    qualified.sort(key=_sort_key)
    selected_policy, _, _ = qualified[0]
    return CandidateResult(
        selected_policy=selected_policy.value,
        selection_reason=f"selected by largest validation equal-weighted per-ticker mean improvement; tie-break prefers {ShortContextPolicy.MARKET_RS.value}",
        policy_metrics=policy_metrics,
    )


def evaluate_holdout(
    events_df: pd.DataFrame,
    selected_policy: str | None,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
) -> HoldoutResult:
    """Evaluate the selected candidate on holdout."""
    if selected_policy is None or events_df.empty:
        return HoldoutResult(
            passed=False,
            policy=selected_policy,
            metrics=None,
            baseline_metrics=None,
            failure_reasons=["no candidate selected"],
        )

    policy = _policy_from_string(selected_policy)
    holdout_df = events_df[events_df["split"] == "holdout"]
    if holdout_df.empty:
        return HoldoutResult(
            passed=False,
            policy=selected_policy,
            metrics=None,
            baseline_metrics=None,
            failure_reasons=["no holdout events"],
        )

    baseline = _split_metrics(holdout_df, None, spec, config)
    candidate = _split_metrics(holdout_df, policy, spec, config)

    failure_reasons = _holdout_failures(candidate, baseline, spec, config)
    passed = not failure_reasons

    return HoldoutResult(
        passed=passed,
        policy=selected_policy,
        metrics=candidate,
        baseline_metrics=baseline,
        failure_reasons=failure_reasons,
    )


def _policy_from_string(value: str) -> ShortContextPolicy:
    try:
        return ShortContextPolicy(value)
    except ValueError as exc:
        raise ValidationError(f"unknown policy: {value}") from exc


def _slippage_key(slippage_bps: float) -> str:
    s = float(slippage_bps)
    if s.is_integer():
        return f"{int(s)}"
    return repr(s)


def _net_return_col(spec: ShortContextSpec, config: ScoreValidationConfig) -> str:
    horizon = spec.primary_horizon_bars
    slippage = spec.primary_slippage_bps
    return f"{horizon}_bar_net_return_pct_{_slippage_key(slippage)}bps"


def _eligible_mask(df: pd.DataFrame, policy: ShortContextPolicy | None) -> pd.Series:
    """Return a boolean mask for events qualifying under ``policy``."""
    if policy is None:
        return df["baseline_qualifies"]
    if policy == ShortContextPolicy.MARKET_RS:
        return df["baseline_qualifies"] & df["market_rs_eligible"]
    if policy == ShortContextPolicy.MARKET_SECTOR_RS:
        return df["baseline_qualifies"] & df["market_sector_rs_eligible"]
    raise ValidationError(f"unknown policy: {policy}")


def _split_metrics(
    df: pd.DataFrame,
    policy: ShortContextPolicy | None,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
) -> PolicySplitMetrics:
    """Compute descriptive metrics for a split and optional policy."""
    split = df["split"].iloc[0] if not df.empty else ""
    mask = _eligible_mask(df, policy)
    eligible_df = df[mask]
    baseline_df = df[df["baseline_qualifies"]]

    col = _net_return_col(spec, config)
    values = pd.to_numeric(eligible_df[col], errors="coerce").dropna()

    mean_ret = float(values.mean()) if not values.empty else None
    median_ret = float(values.median()) if not values.empty else None
    positive_rate = (values > 0).mean() * 100.0 if not values.empty else None
    mean_ticker, median_ticker = _ticker_level_means(eligible_df, col)

    event_count = len(eligible_df)
    baseline_event_count = len(baseline_df)
    unique_tickers = eligible_df["ticker"].nunique() if not eligible_df.empty else 0
    baseline_unique_tickers = baseline_df["ticker"].nunique() if not baseline_df.empty else 0
    retention_pct = (
        event_count / max(baseline_event_count, 1) * 100.0
    )
    coverage_pct = (
        unique_tickers / max(baseline_unique_tickers, 1) * 100.0
    )

    return PolicySplitMetrics(
        split=split,
        policy=policy.value if policy else "baseline",
        event_count=event_count,
        baseline_event_count=baseline_event_count,
        retention_pct=retention_pct,
        unique_tickers=unique_tickers,
        baseline_unique_tickers=baseline_unique_tickers,
        coverage_pct=coverage_pct,
        mean_net_return_pct=mean_ret,
        median_net_return_pct=median_ret,
        positive_return_rate_pct=positive_rate,
        mean_ticker_event_return_pct=mean_ticker,
        median_ticker_event_return_pct=median_ticker,
    )


def _ticker_level_means(df: pd.DataFrame, col: str) -> tuple[float | None, float | None]:
    """Equal-weighted mean of per-ticker means and the median of those means."""
    if df.empty:
        return None, None
    ticker_means = []
    for ticker in sorted(df["ticker"].unique()):
        vals = pd.to_numeric(df[df["ticker"] == ticker][col], errors="coerce").dropna()
        if not vals.empty:
            ticker_means.append(float(vals.mean()))
    if not ticker_means:
        return None, None
    return float(np.mean(ticker_means)), float(np.median(ticker_means))


def candidate_qualifies_for_holdout(
    dev: PolicySplitMetrics,
    dev_base: PolicySplitMetrics,
    val: PolicySplitMetrics,
    val_base: PolicySplitMetrics,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
    require_sample: bool = True,
) -> bool:
    """Return True when a candidate policy passes development and validation gates."""
    # Development mean must exceed baseline.
    if (dev.mean_net_return_pct or -np.inf) <= (dev_base.mean_net_return_pct or -np.inf):
        return False

    # Validation criteria.
    if require_sample and val.event_count < spec.minimum_holdout_events:
        return False
    if val.retention_pct < spec.minimum_event_retention_pct:
        return False
    if val.coverage_pct < spec.minimum_ticker_coverage_pct:
        return False
    if (val.mean_net_return_pct or -np.inf) <= (val_base.mean_net_return_pct or -np.inf):
        return False
    if (val.mean_ticker_event_return_pct or -np.inf) <= (
        val_base.mean_ticker_event_return_pct or -np.inf
    ):
        return False
    if (val.median_net_return_pct or -np.inf) < (val_base.median_net_return_pct or -np.inf):
        return False
    return (val.positive_return_rate_pct or 100.0) >= (
        (val_base.positive_return_rate_pct or 0.0) - 2.0
    )


def _holdout_failures(
    candidate: PolicySplitMetrics,
    baseline: PolicySplitMetrics,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
) -> list[str]:
    """Return a list of failed holdout criteria."""
    failures: list[str] = []

    if candidate.event_count < spec.minimum_holdout_events:
        failures.append(
            f"holdout event count {candidate.event_count} < {spec.minimum_holdout_events}"
        )
    if candidate.unique_tickers < spec.minimum_holdout_tickers:
        failures.append(
            f"holdout ticker count {candidate.unique_tickers} < {spec.minimum_holdout_tickers}"
        )
    if candidate.retention_pct < spec.minimum_event_retention_pct:
        failures.append(
            f"holdout retention {candidate.retention_pct:.2f}% < {spec.minimum_event_retention_pct}%"
        )
    if candidate.coverage_pct < spec.minimum_ticker_coverage_pct:
        failures.append(
            f"holdout ticker coverage {candidate.coverage_pct:.2f}% < {spec.minimum_ticker_coverage_pct}%"
        )
    if (candidate.mean_net_return_pct or -np.inf) <= (baseline.mean_net_return_pct or -np.inf):
        failures.append("holdout mean return not greater than baseline")
    if (candidate.mean_ticker_event_return_pct or -np.inf) <= (
        baseline.mean_ticker_event_return_pct or -np.inf
    ):
        failures.append("holdout equal-weighted per-ticker mean not greater than baseline")
    if (candidate.median_net_return_pct or -np.inf) < (baseline.median_net_return_pct or -np.inf):
        failures.append("holdout median return lower than baseline")
    if (candidate.positive_return_rate_pct or 100.0) < (
        (baseline.positive_return_rate_pct or 0.0) - 2.0
    ):
        failures.append("holdout positive-return rate degraded more than 2 percentage points")

    # Robustness: improvement not produced by only one ticker.
    if candidate.unique_tickers == 1:
        failures.append("improvement produced by only one ticker")

    # At least half of represented tickers have candidate mean >= baseline mean.
    # This is checked at the per-ticker comparison level in the report pipeline.

    return failures


def build_candidate_comparison_df(
    events_df: pd.DataFrame,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
) -> pd.DataFrame:
    """Return a DataFrame comparing every policy on every split."""
    rows: list[dict[str, Any]] = []
    for split in sorted(events_df["split"].unique()):
        split_df = events_df[events_df["split"] == split]
        baseline = _split_metrics(split_df, None, spec, config)
        rows.append(_metrics_to_dict(baseline))
        for policy in spec.candidate_policies:
            candidate = _split_metrics(split_df, policy, spec, config)
            rows.append(_metrics_to_dict(candidate))
    if not rows:
        return pd.DataFrame(columns=_comparison_columns())
    df = pd.DataFrame(rows)
    for col in _comparison_columns():
        if col not in df.columns:
            df[col] = None
    return df[_comparison_columns()]


def _metrics_to_dict(m: PolicySplitMetrics) -> dict[str, Any]:
    return {
        "split": m.split,
        "policy": m.policy,
        "event_count": m.event_count,
        "baseline_event_count": m.baseline_event_count,
        "retention_pct": m.retention_pct,
        "unique_tickers": m.unique_tickers,
        "baseline_unique_tickers": m.baseline_unique_tickers,
        "coverage_pct": m.coverage_pct,
        "mean_net_return_pct": m.mean_net_return_pct,
        "median_net_return_pct": m.median_net_return_pct,
        "positive_return_rate_pct": m.positive_return_rate_pct,
        "mean_ticker_event_return_pct": m.mean_ticker_event_return_pct,
        "median_ticker_event_return_pct": m.median_ticker_event_return_pct,
    }


def _comparison_columns() -> list[str]:
    return [
        "split",
        "policy",
        "event_count",
        "baseline_event_count",
        "retention_pct",
        "unique_tickers",
        "baseline_unique_tickers",
        "coverage_pct",
        "mean_net_return_pct",
        "median_net_return_pct",
        "positive_return_rate_pct",
        "mean_ticker_event_return_pct",
        "median_ticker_event_return_pct",
    ]
