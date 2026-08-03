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
    """Select the best candidate policy using development and validation only.

    Holdout rows are intentionally ignored; if the input contains a holdout
    split, it is dropped before any metric is computed so the candidate cannot
    leak holdout information into the selection decision.
    """
    if events_df.empty:
        return CandidateResult(
            selected_policy=None,
            selection_reason="no events",
            policy_metrics={},
        )

    if (events_df["split"] == "holdout").any():
        events_df = events_df[events_df["split"].isin(["development", "validation"])].copy()

    policy_metrics: dict[str, dict[str, PolicySplitMetrics]] = {}
    qualified: list[tuple[ShortContextPolicy, dict[str, PolicySplitMetrics], float]] = []

    for policy in spec.candidate_policies:
        metrics_by_split: dict[str, PolicySplitMetrics] = {}
        for split in ("development", "validation"):
            split_df = events_df[events_df["split"] == split]
            if split_df.empty:
                continue
            baseline = _split_metrics(split_df, None, spec, config)
            candidate = _split_metrics(split_df, policy, spec, config)
            metrics_by_split[split] = candidate
            metrics_by_split[f"{split}_baseline"] = baseline

        policy_metrics[policy.value] = metrics_by_split

        dev = metrics_by_split.get("development")
        dev_base = metrics_by_split.get("development_baseline")
        val = metrics_by_split.get("validation")
        val_base = metrics_by_split.get("validation_baseline")

        if dev is None or dev_base is None or val is None or val_base is None:
            continue

        if candidate_qualifies_for_selection(dev, dev_base, val, val_base, spec, config):
            val_improvement = _nonmissing(val.mean_ticker_event_return_pct, 0.0) - _nonmissing(
                val_base.mean_ticker_event_return_pct, 0.0
            )
            qualified.append((policy, metrics_by_split, val_improvement))

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

    failure_reasons = _holdout_failures(events_df, candidate, baseline, spec, config, selected_policy)
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


def _primary_outcome_status_col(spec: ShortContextSpec) -> str:
    return f"{spec.primary_horizon_bars}_bar_outcome_status"


def _complete_primary_mask(df: pd.DataFrame, spec: ShortContextSpec) -> pd.Series:
    """Return a mask selecting rows with a complete primary-horizon outcome."""
    status_col = _primary_outcome_status_col(spec)
    if status_col not in df.columns:
        return pd.Series(True, index=df.index)
    return df[status_col] == "complete"


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
    """Compute descriptive metrics for a split and optional policy.

    Only rows with a complete primary-horizon outcome are counted. This keeps
    boundary signals with ``insufficient_future_bars`` from satisfying sample
    minimums or inflating retention/coverage denominators.
    """
    split = df["split"].iloc[0] if not df.empty else ""
    complete = _complete_primary_mask(df, spec)
    mask = _eligible_mask(df, policy) & complete
    eligible_df = df[mask]
    baseline_df = df[df["baseline_qualifies"] & complete]

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


def candidate_qualifies_for_selection(
    dev: PolicySplitMetrics,
    dev_base: PolicySplitMetrics,
    val: PolicySplitMetrics,
    val_base: PolicySplitMetrics,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
) -> bool:
    """Return True when a candidate policy passes development and validation gates."""
    # Development mean must exceed baseline.
    if not _gt(dev.mean_net_return_pct, dev_base.mean_net_return_pct):
        return False

    # Validation sample minimum.
    if val.event_count < spec.minimum_validation_events:
        return False

    if val.retention_pct < spec.minimum_event_retention_pct:
        return False
    if val.coverage_pct < spec.minimum_ticker_coverage_pct:
        return False
    if not _gt(val.mean_net_return_pct, val_base.mean_net_return_pct):
        return False
    if not _gt(val.mean_ticker_event_return_pct, val_base.mean_ticker_event_return_pct):
        return False
    if not _gt_or_equal(val.median_net_return_pct, val_base.median_net_return_pct):
        return False
    if not _gte(
        val.positive_return_rate_pct,
        _nonmissing(val_base.positive_return_rate_pct, 0.0) - 2.0,
    ):
        return False
    return True


def _nonmissing(value: float | None, default: float) -> float:
    """Return ``value`` when it is not None, otherwise ``default``."""
    return value if value is not None else default


def _gt(a: float | None, b: float | None) -> bool:
    """Strict greater-than that treats ``None`` as missing (False)."""
    return a is not None and b is not None and a > b


def _gt_or_equal(a: float | None, b: float | None) -> bool:
    """Greater-than-or-equal that treats ``None`` as missing (False)."""
    return a is not None and b is not None and a >= b


def _gte(a: float | None, b: float | None) -> bool:
    """Greater-than-or-equal that treats ``None`` as missing (False)."""
    return a is not None and b is not None and a >= b


def _holdout_failures(
    events_df: pd.DataFrame,
    candidate: PolicySplitMetrics,
    baseline: PolicySplitMetrics,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
    selected_policy: str,
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
    if not _gt(candidate.mean_net_return_pct, baseline.mean_net_return_pct):
        failures.append("holdout mean return not greater than baseline")
    if not _gt(
        candidate.mean_ticker_event_return_pct, baseline.mean_ticker_event_return_pct
    ):
        failures.append("holdout equal-weighted per-ticker mean not greater than baseline")
    if not _gt_or_equal(candidate.median_net_return_pct, baseline.median_net_return_pct):
        failures.append("holdout median return lower than baseline")
    if not _gte(
        candidate.positive_return_rate_pct,
        _nonmissing(baseline.positive_return_rate_pct, 0.0) - 2.0,
    ):
        failures.append("holdout positive-return rate degraded more than 2 percentage points")

    # Robustness: improvement not produced by only one ticker.
    if candidate.unique_tickers == 1:
        failures.append("improvement produced by only one ticker")

    # At least half of represented tickers have candidate mean >= baseline mean.
    ticker_comparison = _build_ticker_comparison(events_df, spec, config, selected_policy)
    if not ticker_comparison.empty:
        improved = ticker_comparison["candidate_improved"]
        represented = improved.notna().sum()
        if represented > 0 and improved.sum() < represented / 2:
            failures.append(
                f"fewer than half of represented holdout tickers improved ({int(improved.sum())}/{represented})"
            )

    return failures


def _build_ticker_comparison(
    events_df: pd.DataFrame,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
    selected_policy: str | None,
) -> pd.DataFrame:
    """Return per-ticker holdout event-study comparison for selected candidate."""
    if events_df.empty or selected_policy is None:
        return _empty_ticker_comparison_df()

    holdout_df = events_df[events_df["split"] == "holdout"]
    if holdout_df.empty:
        return _empty_ticker_comparison_df()

    complete = _complete_primary_mask(holdout_df, spec)
    holdout_df = holdout_df[complete]
    if holdout_df.empty:
        return _empty_ticker_comparison_df()

    policy = _policy_from_string(selected_policy)
    col = _net_return_col(spec, config)
    rows: list[dict[str, Any]] = []
    for ticker in sorted(holdout_df["ticker"].unique()):
        ticker_df = holdout_df[holdout_df["ticker"] == ticker]
        baseline_df = ticker_df[ticker_df["baseline_qualifies"]]
        candidate_df = ticker_df[_eligible_mask(ticker_df, policy)]

        baseline_vals = pd.to_numeric(baseline_df[col], errors="coerce").dropna()
        candidate_vals = pd.to_numeric(candidate_df[col], errors="coerce").dropna()

        baseline_mean = float(baseline_vals.mean()) if not baseline_vals.empty else None
        candidate_mean = float(candidate_vals.mean()) if not candidate_vals.empty else None
        improved = (
            candidate_mean is not None
            and baseline_mean is not None
            and candidate_mean >= baseline_mean
        )

        rows.append({
            "ticker": ticker,
            "baseline_event_count": len(baseline_df),
            "candidate_event_count": len(candidate_df),
            "baseline_mean_net_return_pct": baseline_mean,
            "candidate_mean_net_return_pct": candidate_mean,
            "candidate_improved": improved,
        })

    if not rows:
        return _empty_ticker_comparison_df()
    df = pd.DataFrame(rows)
    for col_name in _empty_ticker_comparison_df().columns:
        if col_name not in df.columns:
            df[col_name] = None
    return df[_empty_ticker_comparison_df().columns]


def _empty_ticker_comparison_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "ticker", "baseline_event_count", "candidate_event_count",
        "baseline_mean_net_return_pct", "candidate_mean_net_return_pct", "candidate_improved",
    ])


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
