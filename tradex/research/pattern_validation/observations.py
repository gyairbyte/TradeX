"""Point-in-time similarity evaluation and forward-return simulation."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from .fingerprints import _normalize_window
from .models import Fingerprint, Observation, StudySpec, Trade, _clean


def _series_similarity(live: list[float], fp_mean: list[float]) -> float:
    """Pearson correlation between a live series and a fingerprint mean.

    Mirrors ``tradex.patterns.matcher._series_similarity`` exactly so the
    research study uses the same calculation.
    """
    n = min(len(live), len(fp_mean))
    if n < 3:
        return 0.0
    a = np.array(live[-n:], dtype=float)
    b = np.array(fp_mean[-n:], dtype=float)
    if np.std(a) == 0 or np.std(b) == 0:
        return 0.0
    corr = float(np.corrcoef(a, b)[0, 1])
    if not np.isfinite(corr):
        return 0.0
    return round((corr + 1) / 2 * 100, 1)


def _compute_similarity(live_window: dict[str, list[float]], fingerprint: Fingerprint, spec: StudySpec) -> tuple[float, dict[str, float]]:
    """Weighted similarity and per-series scores."""
    weighted_sum = 0.0
    weight_total = 0.0
    series_scores: dict[str, float] = {}
    for key, weight in spec.series_weights.items():
        if key not in live_window or key not in fingerprint.series:
            continue
        score = _series_similarity(live_window[key], fingerprint.series[key]["mean"])
        series_scores[key] = score
        weighted_sum += score * weight
        weight_total += weight
    similarity = round(weighted_sum / weight_total, 1) if weight_total > 0 else 0.0
    return similarity, series_scores


def _net_return(gross_pct: float, entry_price: float, exit_price: float, slippage_bps: float, event_type: str) -> float:
    """Return net signed return after adverse entry/exit slippage."""
    if event_type == "runup":
        entry_fill = entry_price * (1.0 + slippage_bps / 10000.0)
        exit_fill = exit_price * (1.0 - slippage_bps / 10000.0)
        net = (exit_fill - entry_fill) / entry_fill * 100.0
    else:  # decline -> short
        entry_fill = entry_price * (1.0 - slippage_bps / 10000.0)
        exit_fill = exit_price * (1.0 + slippage_bps / 10000.0)
        net = (entry_fill - exit_fill) / entry_fill * 100.0
    return round(net, 4)


def _evaluate_decision(
    df: pd.DataFrame,
    decision_idx: int,
    fingerprint: Fingerprint,
    event_type: str,
    split_name: str,
    spec: StudySpec,
    ticker: str,
) -> Observation | None:
    """Evaluate one decision date in a point-in-time manner."""
    lookback = spec.lookback_days
    if decision_idx < lookback:
        return None
    window = df.iloc[decision_idx - lookback : decision_idx + 1]
    if len(window) != lookback + 1:
        return None
    # Decision date is the last row of the window.
    decision_row = window.iloc[-1]
    required_cols = ["open", "high", "low", "close", "volume", "rsi", "macd_diff", "bb_width"]
    if decision_row[required_cols].isna().any():
        return None
    # The lookback itself must also be fully valid.
    lookback_df = window.iloc[:-1]
    if lookback_df[required_cols].isna().any().any():
        return None

    live_window = _normalize_window(lookback_df)
    if live_window is None:
        return None

    similarity, series_scores = _compute_similarity(live_window, fingerprint, spec)
    is_qualifying = similarity >= spec.similarity_threshold

    decision_date = df.index[decision_idx].to_pydatetime().date()
    signal_time = df.index[decision_idx].tz_convert("UTC").replace(hour=21, minute=0, second=0, microsecond=0)
    if isinstance(signal_time, pd.Timestamp):
        signal_time = signal_time.to_pydatetime()

    signal_close = float(decision_row["close"])

    # Forward horizon for execution.
    entry_idx = decision_idx + 1
    exit_idx = entry_idx + spec.holding_days - 1
    if exit_idx >= len(df):
        return Observation(
            ticker=ticker,
            split=split_name,
            event_type=event_type,
            decision_date=decision_date,
            signal_time=signal_time,
            similarity_score=similarity,
            series_scores=series_scores,
            is_qualifying=is_qualifying,
            data_source=ticker,
            signal_close=signal_close,
            entry_date=None,
            raw_entry_price=None,
            exit_date=None,
            raw_exit_price=None,
            gross_return_pct=None,
            net_return_pct_by_slippage={spec.slippage_key(s): None for s in spec.slippage_scenarios_bps},
            outcome_status="insufficient_future_bars",
        )

    entry_price = float(df["open"].iloc[entry_idx])
    exit_price = float(df["close"].iloc[exit_idx])
    if event_type == "runup":
        gross = (exit_price - entry_price) / entry_price * 100.0
    else:
        gross = (entry_price - exit_price) / entry_price * 100.0
    gross = round(gross, 4)

    entry_date = df.index[entry_idx].to_pydatetime().date()
    exit_date = df.index[exit_idx].to_pydatetime().date()

    net_by_slippage = {}
    for slippage_bps in spec.slippage_scenarios_bps:
        net = _net_return(gross, entry_price, exit_price, slippage_bps, event_type)
        net_by_slippage[spec.slippage_key(slippage_bps)] = net

    return Observation(
        ticker=ticker,
        split=split_name,
        event_type=event_type,
        decision_date=decision_date,
        signal_time=signal_time,
        similarity_score=similarity,
        series_scores=series_scores,
        is_qualifying=is_qualifying,
        data_source=ticker,
        signal_close=signal_close,
        entry_date=entry_date,
        raw_entry_price=round(entry_price, 4),
        exit_date=exit_date,
        raw_exit_price=round(exit_price, 4),
        gross_return_pct=gross,
        net_return_pct_by_slippage=net_by_slippage,
        outcome_status="complete",
    )


def _split_observations_for_ticker(
    df: pd.DataFrame,
    split_name: str,
    split: Any,
    fingerprint: Fingerprint,
    event_type: str,
    spec: StudySpec,
    ticker: str,
) -> list[Observation]:
    """Compute indicators on the full ticker history and evaluate the split."""
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    from tradex.signals.indicators import add_indicators
    df = add_indicators(df)
    required_cols = ["open", "high", "low", "close", "volume", "rsi", "macd_diff", "bb_width"]
    df = df.dropna(subset=required_cols)
    if df.empty:
        return []

    split_start = pd.Timestamp(split.start, tz="UTC")
    split_end = pd.Timestamp(split.end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    split_mask = (df.index >= split_start) & (df.index <= split_end)
    split_df = df[split_mask]
    if split_df.empty:
        return []

    observations: list[Observation] = []
    for decision_idx in range(len(df)):
        decision_date = df.index[decision_idx]
        if not (split_start <= decision_date <= split_end):
            continue
        obs = _evaluate_decision(df, decision_idx, fingerprint, event_type, split_name, spec, ticker)
        if obs is not None:
            observations.append(obs)
    return observations


def evaluate_splits(
    bars: dict[str, pd.DataFrame],
    fingerprints: dict[str, Fingerprint],
    spec: StudySpec,
    splits_to_evaluate: list[str] | None = None,
) -> list[Observation]:
    """Produce point-in-time observations for each split, ticker, and event type."""
    if splits_to_evaluate is None:
        splits_to_evaluate = ["validation", "holdout"]

    all_observations: list[Observation] = []
    for split_name in splits_to_evaluate:
        split = spec.splits.get(split_name)
        if split is None:
            continue
        for event_type in spec.event_types:
            fp = fingerprints.get(event_type)
            if fp is None:
                continue
            for ticker, df in sorted(bars.items()):
                if ticker not in spec.tickers:
                    continue
                obs = _split_observations_for_ticker(df, split_name, split, fp, event_type, spec, ticker)
                all_observations.extend(obs)
    return all_observations


def build_executable_trades(observations: list[Observation], spec: StudySpec) -> list[Trade]:
    """Per-ticker executable simulation: one active trade per ticker and event type."""
    trades: list[Trade] = []
    # active_until keyed by (ticker, event_type, split) -> exit_date
    active_until: dict[tuple[str, str, str], date] = {}

    # Sort by decision_date to process chronologically.
    sorted_obs = sorted(
        [o for o in observations if o.is_qualifying and o.outcome_status == "complete"],
        key=lambda o: (o.ticker, o.split, o.event_type, o.decision_date),
    )
    for obs in sorted_obs:
        key = (obs.ticker, obs.split, obs.event_type)
        if key in active_until and obs.decision_date < active_until[key]:
            continue
        trade = Trade(
            ticker=obs.ticker,
            split=obs.split,
            event_type=obs.event_type,
            decision_date=obs.decision_date,
            entry_date=obs.entry_date,
            exit_date=obs.exit_date,
            signal_close=obs.signal_close,
            raw_entry_price=obs.raw_entry_price,
            raw_exit_price=obs.raw_exit_price,
            gross_return_pct=obs.gross_return_pct,
            net_return_pct_by_slippage=obs.net_return_pct_by_slippage,
        )
        trades.append(trade)
        active_until[key] = obs.exit_date
    return trades


def observations_to_dataframe(observations: list[Observation]) -> pd.DataFrame:
    if not observations:
        return pd.DataFrame()
    records = [o.to_dict() for o in observations]
    return pd.DataFrame(records)


def trades_to_dataframe(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    records = [t.to_dict() for t in trades]
    return pd.DataFrame(records)


def point_in_time_isolation_test(df: pd.DataFrame, fingerprint: Fingerprint, spec: StudySpec, decision_idx: int, event_type: str) -> float:
    """Return similarity for a decision index; used by tests to prove future bars cannot alter it."""
    from tradex.signals.indicators import add_indicators
    decision_ts = df.index[decision_idx]
    truncated = df.iloc[: decision_idx + 1].copy()
    truncated = add_indicators(truncated)
    required_cols = ["open", "high", "low", "close", "volume", "rsi", "macd_diff", "bb_width"]
    truncated = truncated.dropna(subset=required_cols)
    new_idx = truncated.index.get_loc(decision_ts)
    obs = _evaluate_decision(truncated, new_idx, fingerprint, event_type, "test", spec, "TEST")
    return obs.similarity_score if obs else 0.0
