"""Point-in-time event generation and forward-return calculation."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

import pandas as pd

from tradex.backtest.validation import canonicalize_bars
from tradex.signals.short_term import score as short_term_score
from tradex.signals.weights import ShortWeights

from .manifest import _load_and_canonicalize
from .models import DataQualityRow, EventOutcome, EventRecord, ScoreValidationConfig, ValidationError


def generate_events(
    manifest,
    config: ScoreValidationConfig,
) -> tuple[list[EventRecord], list[DataQualityRow]]:
    """Generate all eligible point-in-time events from a validated manifest."""
    events: list[EventRecord] = []
    quality_rows: list[DataQualityRow] = []

    for entry in manifest.entries:
        csv_path = _resolve_csv_path(manifest, entry)
        ticker_events, quality = _generate_ticker_events(entry, csv_path, config, manifest.splits)
        events.extend(ticker_events)
        quality_rows.append(quality)

    return events, quality_rows


def _resolve_csv_path(manifest, entry) -> Any:
    # manifest path is relative to manifest directory
    import json
    from pathlib import Path

    # Re-derive from the manifest object: we don't store the base dir, so
    # callers must provide a manifest loaded from a path. We use a small
    # sentinel attribute set by the loader.
    base_dir = getattr(manifest, "_base_dir", None)
    if base_dir is None:
        raise ValidationError("Manifest was not loaded from a path; cannot resolve CSV files")
    return Path(base_dir) / entry.path


def _generate_ticker_events(
    entry, csv_path, config: ScoreValidationConfig, splits: dict
) -> tuple[list[EventRecord], DataQualityRow]:
    """Generate events for a single ticker and a data-quality summary."""
    ticker_events: list[EventRecord] = []
    warnings: list[str] = []
    duplicate_timestamps = 0
    missing_required_values = 0
    invalid_ohlc_rows = 0
    split_event_counts: dict[str, int] = {name: 0 for name in splits}
    complete_outcomes: dict[int, int] = {h: 0 for h in config.horizons}

    try:
        df = _load_and_canonicalize(csv_path)
    except Exception as exc:
        raise ValidationError(f"Failed to load/validate {entry.ticker}: {exc}") from exc

    validated_rows = len(df)
    data_start = df.index[0].to_pydatetime() if not df.empty else None
    data_end = df.index[-1].to_pydatetime() if not df.empty else None

    # We already canonicalized, but track quality signals from raw CSV before canonicalization.
    raw_df = pd.read_csv(csv_path, parse_dates=["datetime"], index_col="datetime")
    duplicate_timestamps = int(raw_df.index.duplicated().sum())
    for col in ["open", "high", "low", "close", "volume"]:
        if col in raw_df.columns:
            missing_required_values += int(raw_df[col].isna().sum())

    if df.empty:
        warnings.append("CSV contains no valid rows after canonicalization")

    if validated_rows < config.warmup_bars:
        warnings.append(
            f"Only {validated_rows} rows available; warmup_bars is {config.warmup_bars}"
        )

    for i in range(config.warmup_bars, len(df)):
        signal_time = df.index[i].to_pydatetime()
        split_name = _split_for(signal_time, splits)
        if split_name is None:
            continue

        # Point-in-time slice: only bars up to and including the signal bar.
        score_df = df.iloc[: i + 1].copy()
        score_result = short_term_score(score_df, weights=ShortWeights())

        signal_close = float(score_result["last_close"])
        score = float(score_result["score"])
        reasons = list(score_result.get("reasons", []))
        components = dict(score_result.get("components", {}))
        component_points = {
            k: int(v) for k, v in score_result.get("component_points", {}).items()
        }

        entry_time: datetime | None = None
        raw_entry_price: float | None = None
        entry_in_split = False
        if i + 1 < len(df):
            entry_time = df.index[i + 1].to_pydatetime()
            raw_entry_price = float(df["open"].iloc[i + 1])
            entry_in_split = _within_split(entry_time, splits[split_name])

        if entry_time is None or not entry_in_split:
            # The next bar either does not exist or belongs to a later split.
            # Do not expose its time/price and mark all horizons incomplete.
            entry_time = None
            raw_entry_price = None

        outcomes: dict[int, EventOutcome] = {}
        for horizon in config.horizons:
            if entry_time is None or raw_entry_price is None:
                outcome = _incomplete_outcome(horizon, config)
            else:
                exit_idx = i + horizon
                if exit_idx >= len(df):
                    outcome = _incomplete_outcome(horizon, config)
                else:
                    exit_time = df.index[exit_idx].to_pydatetime()
                    if not _within_split(exit_time, splits[split_name]):
                        outcome = _incomplete_outcome(horizon, config)
                    else:
                        raw_exit_price = float(df["close"].iloc[exit_idx])
                        gross = raw_exit_price / raw_entry_price - 1.0
                        net_by_slippage = {
                            config.slippage_key(s): _net_return(
                                raw_entry_price, raw_exit_price, s, config.commission_bps
                            )
                            for s in config.slippage_scenarios_bps
                        }
                        outcome = EventOutcome(
                            horizon=horizon,
                            exit_time=exit_time,
                            raw_exit_price=raw_exit_price,
                            gross_return_pct=gross * 100.0,
                            net_return_pct_by_slippage=net_by_slippage,
                            outcome_status="complete",
                        )
                        complete_outcomes[horizon] += 1

            outcomes[horizon] = outcome

        event = EventRecord(
            ticker=entry.ticker,
            split=split_name,
            signal_time=signal_time,
            score=score,
            reasons=reasons,
            components=components,
            component_points=component_points,
            signal_close=signal_close,
            entry_time=entry_time,
            raw_entry_price=raw_entry_price,
            data_source=entry.data_source,
            outcomes=outcomes,
        )
        ticker_events.append(event)
        split_event_counts[split_name] += 1

    if not ticker_events:
        warnings.append("No events generated for this ticker")

    quality = DataQualityRow(
        ticker=entry.ticker,
        data_source=entry.data_source,
        sha256=entry.sha256,
        manifest_rows=entry.rows,
        validated_rows=validated_rows,
        data_start=data_start,
        data_end=data_end,
        duplicate_timestamps=duplicate_timestamps,
        missing_required_values=missing_required_values,
        invalid_ohlc_rows=invalid_ohlc_rows,
        split_event_counts=split_event_counts,
        complete_1_bar_outcomes=complete_outcomes.get(1, 0),
        complete_3_bar_outcomes=complete_outcomes.get(3, 0),
        complete_5_bar_outcomes=complete_outcomes.get(5, 0),
        warnings=warnings,
    )
    return ticker_events, quality


def _incomplete_outcome(horizon: int, config: ScoreValidationConfig) -> EventOutcome:
    """Return an incomplete outcome with no net-return values."""
    return EventOutcome(
        horizon=horizon,
        exit_time=None,
        raw_exit_price=None,
        gross_return_pct=None,
        net_return_pct_by_slippage={
            config.slippage_key(s): None for s in config.slippage_scenarios_bps
        },
        outcome_status="insufficient_future_bars",
    )


def _split_for(signal_time: datetime, splits: dict) -> str | None:
    """Return the split name that contains ``signal_time``, or None."""
    for name in ["development", "validation", "holdout"]:
        sp = splits[name]
        start_dt = datetime.combine(sp.start, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(sp.end, time.max, tzinfo=timezone.utc)
        if start_dt <= signal_time <= end_dt:
            return name
    return None


def _within_split(exit_time: datetime, split) -> bool:
    """Check whether ``exit_time`` falls within the inclusive split boundaries."""
    start_dt = datetime.combine(split.start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(split.end, time.max, tzinfo=timezone.utc)
    return start_dt <= exit_time <= end_dt


def _net_return(
    raw_entry: float, raw_exit: float, slippage_bps: float, commission_bps: float
) -> float:
    """Return net return percentage after slippage and commission per side."""
    entry_fill = raw_entry * (1.0 + slippage_bps / 10_000.0)
    exit_fill = raw_exit * (1.0 - slippage_bps / 10_000.0)
    net = (
        exit_fill * (1.0 - commission_bps / 10_000.0)
    ) / (entry_fill * (1.0 + commission_bps / 10_000.0)) - 1.0
    return net * 100.0
