"""Aggregation utilities for score-validation results."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .models import AggregateRow, ScoreValidationConfig


def build_event_dataframe(events: list, config: ScoreValidationConfig) -> pd.DataFrame:
    """Convert EventRecord objects into a flat DataFrame."""
    if not events:
        return pd.DataFrame(columns=_event_columns(config))

    rows = [e.to_dict() for e in events]
    df = pd.DataFrame(rows)
    columns = _event_columns(config)
    for col in columns:
        if col not in df.columns:
            df[col] = None
    return df[columns]


def build_score_buckets(
    df: pd.DataFrame, config: ScoreValidationConfig
) -> pd.DataFrame:
    """Aggregate complete outcomes by split, horizon, cost scenario, and score bucket.

    Every configured bucket is emitted for every split/horizon/slippage combination.
    Groups with no events or fewer than ``minimum_group_events`` are marked
    ``insufficient_sample`` with null metric values.
    """
    if df.empty:
        return _empty_bucket_df()

    rows: list[AggregateRow] = []
    bucket_labels = list(config.bucket_labels())
    for split in _sorted_unique(df, "split"):
        split_df = df[df["split"] == split]
        for horizon in config.horizons:
            complete = split_df[split_df[f"{horizon}_bar_outcome_status"] == "complete"]
            for slippage in config.slippage_scenarios_bps:
                if complete.empty:
                    for bucket in bucket_labels:
                        group = {
                            "split": split,
                            "horizon_bars": horizon,
                            "slippage_bps": slippage,
                            "score_bucket": bucket,
                        }
                        rows.append(
                            AggregateRow(
                                group=group,
                                metrics=_empty_metrics(),
                                sample_status="insufficient_sample",
                            )
                        )
                    continue

                bucketed = complete.copy()
                bucketed["bucket"] = bucketed["score"].apply(config.bucket_for)
                for bucket in bucket_labels:
                    bucket_df = bucketed[bucketed["bucket"] == bucket]
                    group = {
                        "split": split,
                        "horizon_bars": horizon,
                        "slippage_bps": slippage,
                        "score_bucket": bucket,
                    }
                    metrics, sample_status = _group_metrics(
                        bucket_df, horizon, slippage, config
                    )
                    rows.append(
                        AggregateRow(
                            group=group,
                            metrics=metrics,
                            sample_status=sample_status,
                        )
                    )
    return _aggregate_rows_to_df(rows, _empty_bucket_df())


def build_thresholds(
    df: pd.DataFrame, config: ScoreValidationConfig
) -> pd.DataFrame:
    """Aggregate complete outcomes at and above each configured score threshold.

    Every configured threshold is emitted for every split/horizon/slippage.
    """
    if df.empty:
        return _empty_threshold_df()

    rows: list[AggregateRow] = []
    for split in _sorted_unique(df, "split"):
        split_df = df[df["split"] == split]
        for horizon in config.horizons:
            complete = split_df[split_df[f"{horizon}_bar_outcome_status"] == "complete"]
            all_tickers = set(complete["ticker"].unique()) if not complete.empty else set()
            for slippage in config.slippage_scenarios_bps:
                for threshold in config.score_thresholds:
                    above = complete[complete["score"] >= threshold]
                    label = "current_default" if threshold == 40 else f"threshold_{threshold}"
                    group = {
                        "split": split,
                        "horizon_bars": horizon,
                        "slippage_bps": slippage,
                        "threshold": threshold,
                        "threshold_label": label,
                    }
                    if above.empty:
                        metrics = _empty_metrics()
                        metrics["event_retention_pct"] = 0.0
                        metrics["ticker_coverage_pct"] = 0.0
                        rows.append(
                            AggregateRow(
                                group=group,
                                metrics=metrics,
                                sample_status="insufficient_sample",
                            )
                        )
                        continue

                    metrics, sample_status = _group_metrics(above, horizon, slippage, config)
                    metrics["event_retention_pct"] = (
                        len(above) / max(len(complete), 1) * 100.0
                    )
                    metrics["ticker_coverage_pct"] = (
                        len(set(above["ticker"].unique()))
                        / max(len(all_tickers), 1)
                        * 100.0
                    )
                    rows.append(AggregateRow(group=group, metrics=metrics, sample_status=sample_status))
    return _aggregate_rows_to_df(rows, _empty_threshold_df())


def build_components(
    df: pd.DataFrame, config: ScoreValidationConfig
) -> pd.DataFrame:
    """Compare outcomes when each component is present vs absent.

    Both ``present`` and ``absent`` rows are emitted for every component, even if
    one side contains no complete events.
    """
    if df.empty:
        return _empty_component_df()

    component_names = [
        "ema_structure",
        "volume_confirmation",
        "rsi_momentum",
        "macd_positive",
        "pullback_ema",
    ]
    rows: list[AggregateRow] = []
    for split in _sorted_unique(df, "split"):
        split_df = df[df["split"] == split]
        for horizon in config.horizons:
            complete = split_df[split_df[f"{horizon}_bar_outcome_status"] == "complete"]
            for slippage in config.slippage_scenarios_bps:
                for component in component_names:
                    col = f"component_{component}"
                    if col not in complete.columns:
                        continue
                    present = complete[complete[col] == True]
                    absent = complete[complete[col] == False]
                    present_metrics, present_status = _group_metrics(
                        present, horizon, slippage, config
                    )
                    absent_metrics, absent_status = _group_metrics(
                        absent, horizon, slippage, config
                    )
                    delta = _delta_metrics(present_metrics, absent_metrics)
                    for state, metrics, status in [
                        ("present", present_metrics, present_status),
                        ("absent", absent_metrics, absent_status),
                    ]:
                        group = {
                            "split": split,
                            "horizon_bars": horizon,
                            "slippage_bps": slippage,
                            "component": component,
                            "component_state": state,
                        }
                        row_metrics = {
                            **metrics,
                            "mean_return_present_minus_absent": delta["mean"],
                            "median_return_present_minus_absent": delta["median"],
                            "positive_rate_present_minus_absent": delta["positive_rate"],
                        }
                        rows.append(
                            AggregateRow(
                                group=group,
                                metrics=row_metrics,
                                sample_status=status,
                            )
                        )
    return _aggregate_rows_to_df(rows, _empty_component_df())


def build_score_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Return exact-score counts per split."""
    if df.empty:
        return _empty_distribution_df()

    rows = []
    for split in _sorted_unique(df, "split"):
        split_df = df[df["split"] == split]
        total = len(split_df)
        for score in _sorted_unique(split_df, "score"):
            score_df = split_df[split_df["score"] == score]
            rows.append(
                {
                    "split": split,
                    "exact_score": score,
                    "event_count": len(score_df),
                    "unique_tickers": len(score_df["ticker"].unique()),
                    "percentage_of_split_events": len(score_df)
                    / max(total, 1)
                    * 100.0,
                }
            )
    return pd.DataFrame(rows, columns=_empty_distribution_df().columns)


def build_component_frequency(df: pd.DataFrame) -> pd.DataFrame:
    """Return component presence counts per split."""
    if df.empty:
        return _empty_frequency_df()

    component_names = [
        "ema_structure",
        "volume_confirmation",
        "rsi_momentum",
        "macd_positive",
        "pullback_ema",
    ]
    rows = []
    for split in _sorted_unique(df, "split"):
        split_df = df[df["split"] == split]
        total = len(split_df)
        for component in component_names:
            col = f"component_{component}"
            if col not in split_df.columns:
                continue
            present = (split_df[col] == True).sum()
            rows.append(
                {
                    "split": split,
                    "component": component,
                    "present_count": int(present),
                    "present_pct": present / max(total, 1) * 100.0,
                }
            )
    return pd.DataFrame(rows, columns=_empty_frequency_df().columns)


def build_ticker_summary(df: pd.DataFrame, config: ScoreValidationConfig) -> pd.DataFrame:
    """Return per-ticker, per-split, per-horizon summaries."""
    if df.empty:
        return _empty_ticker_summary_df()

    rows = []
    for split in _sorted_unique(df, "split"):
        split_df = df[df["split"] == split]
        for ticker in _sorted_unique(split_df, "ticker"):
            ticker_df = split_df[split_df["ticker"] == ticker]
            for horizon in config.horizons:
                subset = ticker_df[
                    ticker_df[f"{horizon}_bar_outcome_status"] == "complete"
                ]
                if subset.empty:
                    continue
                for slippage in config.slippage_scenarios_bps:
                    col = f"{horizon}_bar_net_return_pct_{config.slippage_key(slippage)}bps"
                    values = pd.to_numeric(subset[col], errors="coerce").dropna()
                    rows.append(
                        {
                            "split": split,
                            "ticker": ticker,
                            "horizon_bars": horizon,
                            "slippage_bps": slippage,
                            "event_count": len(subset),
                            "complete_outcomes": int(
                                (ticker_df[f"{horizon}_bar_outcome_status"] == "complete").sum()
                            ),
                            "mean_net_return_pct": float(values.mean())
                            if not values.empty
                            else None,
                            "median_net_return_pct": float(values.median())
                            if not values.empty
                            else None,
                            "positive_return_rate_pct": (values > 0).mean() * 100.0
                            if not values.empty
                            else None,
                        }
                    )
    return pd.DataFrame(rows, columns=_empty_ticker_summary_df().columns)


def build_data_quality_df(quality_rows: list) -> pd.DataFrame:
    """Convert DataQualityRow objects into a DataFrame."""
    if not quality_rows:
        return _empty_quality_df()
    rows = [q.to_dict() for q in quality_rows]
    df = pd.DataFrame(rows)
    columns = _empty_quality_df().columns
    for col in columns:
        if col not in df.columns:
            df[col] = None
    return df[columns]


def _group_metrics(
    df: pd.DataFrame, horizon: int, slippage: float, config: ScoreValidationConfig
) -> tuple[dict[str, Any], str]:
    """Compute descriptive metrics for a group of complete events.

    Returns ``(metrics, sample_status)``.  Groups with no events or fewer than
    ``minimum_group_events`` are marked ``insufficient_sample``.
    """
    col = f"{horizon}_bar_net_return_pct_{config.slippage_key(slippage)}bps"
    values = pd.to_numeric(df[col], errors="coerce").dropna()

    sample_status = (
        "sufficient_sample" if len(df) >= config.minimum_group_events else "insufficient_sample"
    )

    if values.empty:
        return _empty_metrics(), sample_status

    mean_ticker, median_ticker = _ticker_level_aggregates(df, horizon, slippage, config)

    metrics = {
        "event_count": len(df),
        "unique_tickers": len(df["ticker"].unique()),
        "mean_net_return_pct": float(values.mean()),
        "median_net_return_pct": float(values.median()),
        "positive_return_rate_pct": (values > 0).mean() * 100.0,
        "standard_deviation_pct": float(values.std(ddof=0))
        if len(values) > 1
        else 0.0,
        "p25_net_return_pct": float(values.quantile(0.25)),
        "p75_net_return_pct": float(values.quantile(0.75)),
        "minimum_net_return_pct": float(values.min()),
        "maximum_net_return_pct": float(values.max()),
        "mean_ticker_event_return_pct": mean_ticker,
        "median_ticker_event_return_pct": median_ticker,
    }
    return metrics, sample_status


def _empty_metrics() -> dict[str, Any]:
    return {
        "event_count": 0,
        "unique_tickers": 0,
        "mean_net_return_pct": None,
        "median_net_return_pct": None,
        "positive_return_rate_pct": None,
        "standard_deviation_pct": None,
        "p25_net_return_pct": None,
        "p75_net_return_pct": None,
        "minimum_net_return_pct": None,
        "maximum_net_return_pct": None,
        "mean_ticker_event_return_pct": None,
        "median_ticker_event_return_pct": None,
    }


def _ticker_level_aggregates(
    df: pd.DataFrame, horizon: int, slippage: float, config: ScoreValidationConfig
) -> tuple[Any, Any]:
    """Compute equal-weighted ticker means and the median of those means."""
    col = f"{horizon}_bar_net_return_pct_{config.slippage_key(slippage)}bps"
    ticker_means = []
    for ticker in _sorted_unique(df, "ticker"):
        ticker_values = pd.to_numeric(df[df["ticker"] == ticker][col], errors="coerce").dropna()
        if not ticker_values.empty:
            ticker_means.append(float(ticker_values.mean()))
    if not ticker_means:
        return None, None
    return float(np.mean(ticker_means)), float(np.median(ticker_means))


def _delta_metrics(present: dict, absent: dict) -> dict[str, Any]:
    """Component deltas: present minus absent."""
    keys = ["mean_net_return_pct", "median_net_return_pct", "positive_return_rate_pct"]
    result = {"mean": None, "median": None, "positive_rate": None}
    if present.get("mean_net_return_pct") is not None and absent.get(
        "mean_net_return_pct"
    ) is not None:
        result["mean"] = present["mean_net_return_pct"] - absent["mean_net_return_pct"]
    if present.get("median_net_return_pct") is not None and absent.get(
        "median_net_return_pct"
    ) is not None:
        result["median"] = present["median_net_return_pct"] - absent["median_net_return_pct"]
    if present.get("positive_return_rate_pct") is not None and absent.get(
        "positive_return_rate_pct"
    ) is not None:
        result["positive_rate"] = (
            present["positive_return_rate_pct"] - absent["positive_return_rate_pct"]
        )
    return result


def _aggregate_rows_to_df(rows: list[AggregateRow], empty: pd.DataFrame) -> pd.DataFrame:
    if not rows:
        return empty
    records = [r.to_dict() for r in rows]
    df = pd.DataFrame(records)
    for col in empty.columns:
        if col not in df.columns:
            df[col] = None
    return df[empty.columns]


def _sorted_unique(df: pd.DataFrame, col: str) -> list:
    if col not in df.columns:
        return []
    values = df[col].dropna().unique()
    try:
        return sorted(values)
    except TypeError:
        return sorted(values, key=str)


def _event_columns(config: ScoreValidationConfig) -> list[str]:
    cols = [
        "ticker",
        "split",
        "signal_time",
        "score",
        "reasons",
        "components",
        "component_points",
        "signal_close",
        "entry_time",
        "raw_entry_price",
        "data_source",
    ]
    for c in ["ema_structure", "volume_confirmation", "rsi_momentum", "macd_positive", "pullback_ema"]:
        cols.append(f"component_{c}")
    for horizon in config.horizons:
        cols.append(f"{horizon}_bar_exit_time")
        cols.append(f"{horizon}_bar_raw_exit_price")
        cols.append(f"{horizon}_bar_gross_return_pct")
        for slippage in config.slippage_scenarios_bps:
            cols.append(f"{horizon}_bar_net_return_pct_{config.slippage_key(slippage)}bps")
        cols.append(f"{horizon}_bar_outcome_status")
    return cols


def _empty_bucket_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "split",
            "horizon_bars",
            "slippage_bps",
            "score_bucket",
            "event_count",
            "unique_tickers",
            "mean_net_return_pct",
            "median_net_return_pct",
            "positive_return_rate_pct",
            "standard_deviation_pct",
            "p25_net_return_pct",
            "p75_net_return_pct",
            "minimum_net_return_pct",
            "maximum_net_return_pct",
            "mean_ticker_event_return_pct",
            "median_ticker_event_return_pct",
            "sample_status",
        ]
    )


def _empty_threshold_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "split",
            "horizon_bars",
            "slippage_bps",
            "threshold",
            "threshold_label",
            "event_count",
            "unique_tickers",
            "mean_net_return_pct",
            "median_net_return_pct",
            "positive_return_rate_pct",
            "standard_deviation_pct",
            "p25_net_return_pct",
            "p75_net_return_pct",
            "minimum_net_return_pct",
            "maximum_net_return_pct",
            "mean_ticker_event_return_pct",
            "median_ticker_event_return_pct",
            "event_retention_pct",
            "ticker_coverage_pct",
            "sample_status",
        ]
    )


def _empty_component_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "split",
            "horizon_bars",
            "slippage_bps",
            "component",
            "component_state",
            "event_count",
            "unique_tickers",
            "mean_net_return_pct",
            "median_net_return_pct",
            "positive_return_rate_pct",
            "standard_deviation_pct",
            "p25_net_return_pct",
            "p75_net_return_pct",
            "minimum_net_return_pct",
            "maximum_net_return_pct",
            "mean_ticker_event_return_pct",
            "median_ticker_event_return_pct",
            "mean_return_present_minus_absent",
            "median_return_present_minus_absent",
            "positive_rate_present_minus_absent",
            "sample_status",
        ]
    )


def _empty_distribution_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "split",
            "exact_score",
            "event_count",
            "unique_tickers",
            "percentage_of_split_events",
        ]
    )


def _empty_frequency_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "split",
            "component",
            "present_count",
            "present_pct",
        ]
    )


def _empty_ticker_summary_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "split",
            "ticker",
            "horizon_bars",
            "slippage_bps",
            "event_count",
            "complete_outcomes",
            "mean_net_return_pct",
            "median_net_return_pct",
            "positive_return_rate_pct",
        ]
    )


def _empty_quality_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ticker",
            "data_source",
            "sha256",
            "manifest_rows",
            "validated_rows",
            "data_start",
            "data_end",
            "duplicate_timestamps",
            "missing_required_values",
            "invalid_ohlc_rows",
            "split_event_counts",
            "complete_1_bar_outcomes",
            "complete_3_bar_outcomes",
            "complete_5_bar_outcomes",
            "warnings",
        ]
    )
