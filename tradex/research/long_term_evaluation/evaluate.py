"""Point-in-time evaluation engine for LONG-001."""
from __future__ import annotations

import bisect
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from tradex.signals.indicators import add_indicators

from .models import (
    DataQualityRow,
    DatasetManifest,
    EventOutcome,
    EventRecord,
    LongTermStudySpec,
    ManifestEntry,
    StudyError,
    StudyResult,
    _aggregate_daily_to_weekly,
    _clean,
    _clean_cell,
    _clean_df,
    _df_to_markdown,
    _file_sha256,
    _validate_bars,
)


def evaluate_study(
    manifest: DatasetManifest,
    spec: LongTermStudySpec,
    data_dir: Path,
    output_dir: Path | None = None,
) -> StudyResult:
    """Run the point-in-time LONG-001 evaluation described by ``spec`` on ``manifest``."""
    data_dir = Path(data_dir)
    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    if not manifest.verify_data_files(data_dir):
        raise StudyError("Manifest data-file verification failed (missing or corrupt files)")
    if not manifest.verify_metadata(spec):
        raise StudyError("Manifest metadata does not match the locked study spec")

    weekly_bars: dict[str, pd.DataFrame] = {}
    spy_weekly: pd.DataFrame | None = None
    quality_rows: list[DataQualityRow] = []

    candidate_tickers = set(spec.universe)
    for entry in manifest.entries:
        if entry.failure:
            quality_rows.append(_quality_for_failure(entry))
            continue
        try:
            df = _load_ticker_df(entry, data_dir, spec)
            if entry.ticker == spec.benchmark_ticker:
                spy_weekly = df
            else:
                weekly_bars[entry.ticker] = df
            quality_rows.append(_compute_quality(entry, df, spec))
        except Exception as exc:  # noqa: BLE001
            quality_rows.append(_quality_for_failure(entry, [str(exc)]))

    if spy_weekly is None or spy_weekly.empty:
        raise StudyError(f"Benchmark {spec.benchmark_ticker} data is missing or empty")

    events: list[EventRecord] = []
    trades: list[EventRecord] = []
    for entry in manifest.entries:
        if entry.ticker not in candidate_tickers or entry.failure:
            continue
        weekly = weekly_bars.get(entry.ticker)
        if weekly is None or weekly.empty:
            continue
        ticker_events, ticker_trades = _evaluate_ticker(entry, weekly, spy_weekly, spec)
        events.extend(ticker_events)
        trades.extend(ticker_trades)

    if not events:
        raise StudyError("No events generated. Check warmup, splits, or dataset coverage.")

    events_df = _sort_columns(pd.DataFrame([e.to_dict() for e in events]))
    trades_df = _sort_columns(pd.DataFrame([t.to_dict() for t in trades])) if trades else pd.DataFrame()
    data_quality = _clean_df(pd.DataFrame([r.to_dict() for r in quality_rows]))

    weight_snapshot = {
        "secular_uptrend": spec.weights.secular_uptrend,
        "rsi_healthy": spec.weights.rsi_healthy,
        "volume_accumulation": spec.weights.volume_accumulation,
        "macd_bullish": spec.weights.macd_bullish,
        "bb_coil": spec.weights.bb_coil,
    }

    aggregates = _build_aggregates(events_df, trades_df, spec)
    bootstrap = _build_bootstrap(events_df, trades_df, spec)
    summary = _build_summary(events_df, trades_df, aggregates, bootstrap, spec)
    conclusion = _derive_conclusion(events_df, trades_df, summary, spec)
    report = _generate_report(spec, manifest, events_df, trades_df, aggregates, bootstrap, data_quality, summary, conclusion)

    result = StudyResult(
        spec=spec,
        manifest=manifest,
        weight_snapshot=weight_snapshot,
        events=events_df,
        trades=trades_df,
        summary=summary,
        aggregates=aggregates,
        bootstrap=bootstrap,
        data_quality=data_quality,
        report_markdown=report,
        conclusion=conclusion,
        production_promotion_eligible=False,
    )

    if output_dir is not None:
        (output_dir / "result.json").write_text(result.to_json(indent=2), encoding="utf-8")
        (output_dir / "report.md").write_text(report, encoding="utf-8")
        for name, df in [
            ("events.csv", events_df),
            ("trades.csv", trades_df),
            ("bootstrap.csv", bootstrap),
            ("data_quality.csv", data_quality),
        ]:
            df.to_csv(output_dir / name, index=False)
        for name, df in aggregates.items():
            df.to_csv(output_dir / f"{name}.csv", index=False)

    return result


def _load_ticker_df(entry: ManifestEntry, data_dir: Path, spec: LongTermStudySpec) -> pd.DataFrame:
    path = data_dir / entry.path
    if _file_sha256(path) != entry.sha256:
        raise StudyError(f"Hash mismatch for {entry.ticker}")
    df = pd.read_csv(path, index_col="datetime", parse_dates=True)
    df, _, _, _ = _validate_bars(df, entry.ticker)
    weekly = _aggregate_daily_to_weekly(df)
    if len(weekly) < spec.warmup_weeks:
        raise StudyError(f"{entry.ticker}: only {len(weekly)} weekly bars, need {spec.warmup_weeks}")
    return weekly


def _evaluate_ticker(
    entry: ManifestEntry,
    weekly: pd.DataFrame,
    spy_weekly: pd.DataFrame,
    spec: LongTermStudySpec,
) -> tuple[list[EventRecord], list[EventRecord]]:
    """Generate overlapping event-study and non-overlapping trade records for one ticker."""
    indicators = _compute_indicators(weekly)
    bb_width_pct = _bb_width_percentile(indicators["bb_width"])
    n = len(weekly)
    cohort = spec.cohort_for(entry.ticker)

    # Precompute candidate scores and baseline flags for every bar.
    candidate_scores = np.full(n, np.nan)
    baseline_flags = np.full(n, False)
    reasons_list: list[list[str]] = [[] for _ in range(n)]
    ma40_values = np.full(n, np.nan)

    for i in range(n):
        score, reasons, ma40 = _score_bar(weekly, indicators, bb_width_pct, i, spec)
        candidate_scores[i] = score
        reasons_list[i] = reasons
        ma40_values[i] = ma40
        if not math.isnan(score) and any(score >= t for t in spec.score_thresholds):
            baseline_flags[i] = False  # set below
        if ma40 is not None and weekly["close"].iloc[i] > ma40:
            baseline_flags[i] = True
        else:
            baseline_flags[i] = False

    # Recompute candidate flags after scores known.
    candidate_flags = np.array([
        not math.isnan(candidate_scores[i]) and any(candidate_scores[i] >= t for t in spec.score_thresholds)
        for i in range(n)
    ])

    events: list[EventRecord] = []
    # Overlapping event study: every bar with a signal.
    for i in range(spec.warmup_weeks, n):
        signal_time = weekly.index[i].to_pydatetime()
        split = spec.split_for(signal_time)
        if split in ("warmup", "out_of_range"):
            continue
        score = candidate_scores[i]
        ma40 = ma40_values[i]
        close = float(weekly["close"].iloc[i])
        if candidate_flags[i]:
            group = "baseline_and_candidate" if baseline_flags[i] else "candidate_only"
            events.extend(
                _make_records(
                    entry, cohort, signal_time, split, "candidate", group, score,
                    reasons_list[i], close, ma40, weekly, spy_weekly, i, spec, "overlapping"
                )
            )
        if baseline_flags[i]:
            group = "baseline_and_candidate" if candidate_flags[i] else "baseline_only"
            events.extend(
                _make_records(
                    entry, cohort, signal_time, split, "baseline", group, None,
                    ["close > 40-week SMA"], close, ma40, weekly, spy_weekly, i, spec, "overlapping"
                )
            )

    # Non-overlapping per-ticker trade policy for each rule.
    trades: list[EventRecord] = []
    for rule in ("candidate", "baseline"):
        next_idx = spec.warmup_weeks
        for i in range(spec.warmup_weeks, n):
            if i < next_idx:
                continue
            flag = candidate_flags[i] if rule == "candidate" else baseline_flags[i]
            if not flag:
                continue
            signal_time = weekly.index[i].to_pydatetime()
            split = spec.split_for(signal_time)
            if split in ("warmup", "out_of_range"):
                continue
            score = candidate_scores[i] if rule == "candidate" else None
            reasons = reasons_list[i] if rule == "candidate" else ["close > 40-week SMA"]
            other_flag = baseline_flags[i] if rule == "candidate" else candidate_flags[i]
            group = "baseline_and_candidate" if other_flag else (
                "candidate_only" if rule == "candidate" else "baseline_only"
            )
            close = float(weekly["close"].iloc[i])
            ma40 = ma40_values[i]
            recs = _make_records(
                entry, cohort, signal_time, split, rule, group, score, reasons, close,
                ma40, weekly, spy_weekly, i, spec, "non_overlapping"
            )
            trades.extend(recs)
            # Advance by primary horizon (first hold week).
            primary = spec.hold_weeks[0]
            exit_idx = i + spec.entry_delay_bars + primary
            if exit_idx < n:
                next_idx = exit_idx + 1
            else:
                next_idx = n

    return events, trades


def _make_records(
    entry: ManifestEntry,
    cohort: str,
    signal_time: datetime,
    split: str,
    rule: str,
    group: str,
    score: float | None,
    reasons: list[str],
    close: float,
    ma40: float | None,
    weekly: pd.DataFrame,
    spy_weekly: pd.DataFrame,
    i: int,
    spec: LongTermStudySpec,
    overlap_policy: str,
) -> list[EventRecord]:
    outcomes = _event_outcomes(weekly, spy_weekly, i, signal_time, split, spec)
    entry_idx = i + spec.entry_delay_bars
    entry_time = weekly.index[entry_idx].to_pydatetime() if entry_idx < len(weekly) else None
    entry_price = float(weekly["open"].iloc[entry_idx]) if entry_idx < len(weekly) else None
    return [
        EventRecord(
            ticker=entry.ticker,
            split=split,
            rule=rule,
            group=group,
            overlap_policy=overlap_policy,
            cohort=cohort,
            signal_time=signal_time,
            score=score,
            reasons=reasons,
            signal_close=close,
            ma40=ma40,
            entry_time=entry_time,
            raw_entry_price=entry_price,
            data_source=entry.data_source,
            outcomes=outcomes,
        )
    ]


def _compute_indicators(weekly: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators to the weekly bars."""
    return add_indicators(weekly.copy())


def _bb_width_percentile(bb_width: pd.Series) -> pd.Series:
    """Point-in-time percentile rank of bb_width using an expanding window."""
    sorted_list: list[float] = []
    pct = np.full(len(bb_width), np.nan)
    for i, value in enumerate(bb_width):
        if math.isnan(value):
            sorted_list.append(value)
            continue
        lo = bisect.bisect_left(sorted_list, value)
        hi = bisect.bisect_right(sorted_list, value)
        # Average 1-indexed rank among i+1 elements.
        rank = (lo + hi + 2) / 2.0
        pct[i] = rank / (i + 1)
        bisect.insort(sorted_list, value)
    return pd.Series(pct, index=bb_width.index)


def _score_bar(
    weekly: pd.DataFrame,
    indicators: pd.DataFrame,
    bb_width_pct: pd.Series,
    i: int,
    spec: LongTermStudySpec,
) -> tuple[float, list[str], float | None]:
    """Point-in-time long-term score using only bars up to and including i."""
    if i + 1 < spec.warmup_weeks:
        return float("nan"), [], None
    weights = spec.weights
    close = float(weekly["close"].iloc[i])
    row = indicators.iloc[i]
    ema50 = float(row["ema_50"])
    rsi = float(row["rsi"])
    macd = float(row["macd"])
    macd_signal = float(row["macd_signal"])
    bb_pct = float(bb_width_pct.iloc[i])
    volume_ratio = indicators["volume_ratio"]
    recent_vol = float(volume_ratio.iloc[max(0, i - 7) : i + 1].mean())
    ma40 = _ma40(weekly["close"], i)

    signals: list[int] = []
    reasons: list[str] = []

    if not math.isnan(ema50) and close > ema50:
        signals.append(weights.secular_uptrend)
        reasons.append("Price above long-term EMA50 — secular uptrend")

    if not math.isnan(rsi) and 40 <= rsi <= 65:
        signals.append(weights.rsi_healthy)
        reasons.append(f"RSI healthy, not overbought ({rsi:.0f})")

    if not math.isnan(recent_vol) and recent_vol >= 1.15:
        signals.append(weights.volume_accumulation)
        reasons.append(f"8-period volume accumulation ({recent_vol:.2f}x avg)")

    if not math.isnan(macd) and not math.isnan(macd_signal) and macd > macd_signal:
        signals.append(weights.macd_bullish)
        reasons.append("MACD above signal on weekly — bullish bias")

    if not math.isnan(bb_pct) and bb_pct < 0.25:
        signals.append(weights.bb_coil)
        reasons.append("Tight BB on weekly — coiling for breakout")

    score = float(min(sum(signals), 100)) if signals else 0.0
    return score, reasons, ma40


def _ma40(series: pd.Series, i: int) -> float | None:
    if i < 39:
        return None
    return float(series.iloc[i - 39 : i + 1].mean())


def _event_outcomes(
    weekly: pd.DataFrame,
    spy_weekly: pd.DataFrame,
    i: int,
    signal_time: datetime,
    signal_split: str,
    spec: LongTermStudySpec,
) -> dict[int, EventOutcome]:
    n = len(weekly)
    entry_idx = i + spec.entry_delay_bars
    outcomes: dict[int, EventOutcome] = {}
    for h in spec.hold_weeks:
        if entry_idx >= n:
            outcomes[h] = _incomplete_outcome(h, spec, "insufficient_future_bars")
            continue
        entry_time = weekly.index[entry_idx].to_pydatetime()
        entry_split = spec.split_for(entry_time)
        exit_idx = entry_idx + h
        if exit_idx >= n:
            outcomes[h] = _incomplete_outcome(h, spec, "insufficient_future_bars")
            continue
        exit_time = weekly.index[exit_idx].to_pydatetime()
        exit_split = spec.split_for(exit_time)
        if signal_split != entry_split or signal_split != exit_split:
            outcomes[h] = _incomplete_outcome(h, spec, "cross_split_excluded")
            continue
        entry_price = float(weekly["open"].iloc[entry_idx])
        exit_price = float(weekly["close"].iloc[exit_idx])
        gross = (exit_price / entry_price - 1.0) * 100.0

        spy_entry, spy_exit = _spy_prices(spy_weekly, entry_time, exit_time)
        spy_gross = None
        if spy_entry is not None and spy_exit is not None and spy_entry > 0:
            spy_gross = (spy_exit / spy_entry - 1.0) * 100.0

        net_by_slippage: dict[str, float] = {}
        spy_net_by_slippage: dict[str, float | None] = {}
        for s in spec.slippage_scenarios_bps:
            net = _net_return(entry_price, exit_price, s, spec.commission_bps)
            net_by_slippage[spec.slippage_key(s)] = net
            spy_net = None
            if spy_entry is not None and spy_exit is not None and spy_entry > 0:
                spy_net = _net_return(spy_entry, spy_exit, s, spec.commission_bps)
            spy_net_by_slippage[spec.slippage_key(s)] = spy_net

        outcomes[h] = EventOutcome(
            horizon=h,
            exit_time=exit_time,
            raw_exit_price=exit_price,
            gross_return_pct=gross,
            net_return_pct_by_slippage=net_by_slippage,
            spy_return_pct=spy_gross,
            spy_net_return_pct_by_slippage=spy_net_by_slippage,
            outcome_status="complete",
        )
    return outcomes


def _incomplete_outcome(
    horizon: int, spec: LongTermStudySpec, status: str
) -> EventOutcome:
    return EventOutcome(
        horizon=horizon,
        exit_time=None,
        raw_exit_price=None,
        gross_return_pct=None,
        net_return_pct_by_slippage={spec.slippage_key(s): None for s in spec.slippage_scenarios_bps},
        spy_return_pct=None,
        spy_net_return_pct_by_slippage={spec.slippage_key(s): None for s in spec.slippage_scenarios_bps},
        outcome_status=status,  # type: ignore[arg-type]
    )


def _spy_prices(spy_weekly: pd.DataFrame, entry_time: datetime, exit_time: datetime) -> tuple[float | None, float | None]:
    """Return SPY open/close for the same weekly bar as the event, if available."""
    try:
        entry_row = spy_weekly.loc[entry_time]
        exit_row = spy_weekly.loc[exit_time]
    except KeyError:
        return None, None
    entry = float(entry_row["open"])
    exit_ = float(exit_row["close"])
    if math.isnan(entry) or math.isnan(exit_) or entry <= 0 or exit_ <= 0:
        return None, None
    return entry, exit_


def _net_return(entry: float, exit: float, slippage_bps: float, commission_bps: float) -> float:
    entry_fill = entry * (1.0 + slippage_bps / 10_000.0)
    exit_fill = exit * (1.0 - slippage_bps / 10_000.0)
    net = (exit_fill * (1.0 - commission_bps / 10_000.0)) / (
        entry_fill * (1.0 + commission_bps / 10_000.0)
    ) - 1.0
    return net * 100.0


def _compute_quality(entry: ManifestEntry, weekly: pd.DataFrame, spec: LongTermStudySpec) -> DataQualityRow:
    complete: dict[str, int] = {}
    split_counts: dict[str, int] = defaultdict(int)
    for ts in weekly.index:
        split = spec.split_for(ts.to_pydatetime())
        split_counts[split] += 1
    return DataQualityRow(
        ticker=entry.ticker,
        data_source=entry.data_source,
        sha256=entry.sha256,
        manifest_rows=entry.rows,
        validated_rows=len(weekly),
        data_start=weekly.index[0].to_pydatetime() if len(weekly) else None,
        data_end=weekly.index[-1].to_pydatetime() if len(weekly) else None,
        duplicate_timestamps=entry.quality.get("duplicate_timestamps", 0),
        missing_required_values=entry.quality.get("missing_required_values", 0),
        invalid_ohlc_rows=entry.quality.get("invalid_ohlc_rows", 0),
        split_event_counts=dict(split_counts),
        complete_outcomes=complete,
        warnings=list(entry.warnings),
    )


def _quality_for_failure(entry: ManifestEntry, warnings: list[str] | None = None) -> DataQualityRow:
    return DataQualityRow(
        ticker=entry.ticker,
        data_source=entry.data_source,
        sha256=entry.sha256,
        manifest_rows=0,
        validated_rows=0,
        data_start=None,
        data_end=None,
        duplicate_timestamps=0,
        missing_required_values=0,
        invalid_ohlc_rows=0,
        split_event_counts={},
        complete_outcomes={},
        warnings=warnings or [entry.failure or "unknown failure"],
    )


def _build_aggregates(events: pd.DataFrame, trades: pd.DataFrame, spec: LongTermStudySpec) -> dict[str, pd.DataFrame]:
    aggregates: dict[str, pd.DataFrame] = {}
    if events.empty:
        return aggregates

    # Threshold / rule comparison by split and horizon.
    rows: list[dict[str, Any]] = []
    for horizon in spec.hold_weeks:
        gross_col = f"{horizon}_bar_gross_return_pct"
        for rule in events["rule"].unique():
            for split in events["split"].unique():
                sub = events[(events["rule"] == rule) & (events["split"] == split)]
                if sub.empty:
                    continue
                values = pd.to_numeric(sub[gross_col], errors="coerce").dropna()
                row = _return_row(rule, split, horizon, values, spec, sub)
                rows.append(row)
    aggregates["thresholds"] = _clean_df(pd.DataFrame(rows)) if rows else pd.DataFrame()

    # Cohort analysis.
    rows = []
    for horizon in spec.hold_weeks:
        gross_col = f"{horizon}_bar_gross_return_pct"
        for split in events["split"].unique():
            for cohort in events["cohort"].unique():
                for rule in events["rule"].unique():
                    sub = events[
                        (events["split"] == split)
                        & (events["cohort"] == cohort)
                        & (events["rule"] == rule)
                    ]
                    if sub.empty:
                        continue
                    values = pd.to_numeric(sub[gross_col], errors="coerce").dropna()
                    row = _return_row(rule, split, horizon, values, spec, sub)
                    row["cohort"] = cohort
                    rows.append(row)
    aggregates["cohorts"] = _clean_df(pd.DataFrame(rows)) if rows else pd.DataFrame()

    # Group analysis (candidate_only / baseline_only / baseline_and_candidate).
    rows = []
    for horizon in spec.hold_weeks:
        gross_col = f"{horizon}_bar_gross_return_pct"
        for split in events["split"].unique():
            for group in events["group"].unique():
                for rule in events["rule"].unique():
                    sub = events[
                        (events["split"] == split)
                        & (events["group"] == group)
                        & (events["rule"] == rule)
                    ]
                    if sub.empty:
                        continue
                    values = pd.to_numeric(sub[gross_col], errors="coerce").dropna()
                    row = _return_row(rule, split, horizon, values, spec, sub)
                    row["group"] = group
                    rows.append(row)
    aggregates["groups"] = _clean_df(pd.DataFrame(rows)) if rows else pd.DataFrame()

    # Score buckets.
    rows = []
    score_rows = events[events["rule"] == "candidate"].copy()
    if not score_rows.empty:
        score_rows["score_bucket"] = score_rows["score"].apply(spec.bucket_for)
        for horizon in spec.hold_weeks:
            gross_col = f"{horizon}_bar_gross_return_pct"
            for split in score_rows["split"].unique():
                for bucket in spec.bucket_labels():
                    sub = score_rows[
                        (score_rows["split"] == split) & (score_rows["score_bucket"] == bucket)
                    ]
                    if sub.empty:
                        continue
                    values = pd.to_numeric(sub[gross_col], errors="coerce").dropna()
                    row = _return_row("candidate", split, horizon, values, spec, sub)
                    row["score_bucket"] = bucket
                    rows.append(row)
    aggregates["score_buckets"] = _clean_df(pd.DataFrame(rows)) if rows else pd.DataFrame()

    # Ticker summary (non-overlapping trades preferred for per-ticker attribution).
    source = trades if not trades.empty else events
    rows = []
    for horizon in spec.hold_weeks:
        gross_col = f"{horizon}_bar_gross_return_pct"
        for (ticker, rule, split), sub in source.groupby(["ticker", "rule", "split"]):
            values = pd.to_numeric(sub[gross_col], errors="coerce").dropna()
            if values.empty:
                continue
            row = _return_row(rule, split, horizon, values, spec, sub)
            row["ticker"] = ticker
            row["cohort"] = sub["cohort"].iloc[0]
            rows.append(row)
    aggregates["ticker_summary"] = _clean_df(pd.DataFrame(rows)) if rows else pd.DataFrame()

    # Downside / percentiles.
    rows = []
    for horizon in spec.hold_weeks:
        gross_col = f"{horizon}_bar_gross_return_pct"
        for rule in source["rule"].unique():
            for split in source["split"].unique():
                sub = source[(source["rule"] == rule) & (source["split"] == split)]
                values = pd.to_numeric(sub[gross_col], errors="coerce").dropna()
                if len(values) == 0:
                    continue
                row = {
                    "rule": rule,
                    "split": split,
                    "horizon_weeks": horizon,
                    "count": len(values),
                    "q10": float(values.quantile(0.10)),
                    "q25": float(values.quantile(0.25)),
                    "median": float(values.median()),
                    "q75": float(values.quantile(0.75)),
                    "q90": float(values.quantile(0.90)),
                    "max_drawdown_pct": float((values.cumsum() - values.cumsum().cummax()).min()),
                }
                rows.append(row)
    aggregates["downside"] = _clean_df(pd.DataFrame(rows)) if rows else pd.DataFrame()

    # Cost sensitivity (net returns at decision slippage).
    rows = []
    source = trades if not trades.empty else events
    for horizon in spec.hold_weeks:
        for slippage in spec.slippage_scenarios_bps:
            net_col = f"{horizon}_bar_net_return_pct_{spec.slippage_key(slippage)}bps"
            for rule in source["rule"].unique():
                for split in source["split"].unique():
                    sub = source[(source["rule"] == rule) & (source["split"] == split)]
                    if net_col not in sub.columns:
                        continue
                    values = pd.to_numeric(sub[net_col], errors="coerce").dropna()
                    if len(values) == 0:
                        continue
                    rows.append({
                        "rule": rule,
                        "split": split,
                        "horizon_weeks": horizon,
                        "slippage_bps": slippage,
                        "count": len(values),
                        "mean_net_return_pct": float(values.mean()),
                        "median_net_return_pct": float(values.median()),
                        "std_net_return_pct": float(values.std(ddof=0)) if len(values) > 1 else None,
                        "win_rate": float((values > 0).mean()),
                    })
    aggregates["cost_sensitivity"] = _clean_df(pd.DataFrame(rows)) if rows else pd.DataFrame()

    # Exposure / frequency (non-overlapping trades).
    rows = []
    if not trades.empty:
        for (ticker, rule, split), sub in trades.groupby(["ticker", "rule", "split"]):
            # Weeks in market is sum of completed primary-horizon weeks.
            primary = spec.hold_weeks[0]
            complete = sub[sub[f"{primary}_bar_outcome_status"] == "complete"]
            weeks_in_market = len(complete) * primary
            rows.append({
                "ticker": ticker,
                "rule": rule,
                "split": split,
                "trade_count": len(sub),
                "complete_count": len(complete),
                "weeks_in_market": weeks_in_market,
            })
    aggregates["exposure"] = _clean_df(pd.DataFrame(rows)) if rows else pd.DataFrame()

    return aggregates


def _return_row(rule: str, split: str, horizon: int, values: pd.Series, spec: LongTermStudySpec, sub: pd.DataFrame) -> dict[str, Any]:
    row: dict[str, Any] = {
        "rule": rule,
        "split": split,
        "horizon_weeks": horizon,
        "count": len(values),
        "mean_gross_return_pct": float(values.mean()) if len(values) else None,
        "median_gross_return_pct": float(values.median()) if len(values) else None,
        "std_gross_return_pct": float(values.std(ddof=0)) if len(values) > 1 else None,
        "win_rate": float((values > 0).mean()) if len(values) else None,
    }
    for slippage in spec.slippage_scenarios_bps:
        net_col = f"{horizon}_bar_net_return_pct_{spec.slippage_key(slippage)}bps"
        if net_col in sub.columns:
            net = pd.to_numeric(sub[net_col], errors="coerce").dropna()
            row[f"mean_net_return_pct_{spec.slippage_key(slippage)}bps"] = float(net.mean()) if len(net) else None
            row[f"win_rate_net_{spec.slippage_key(slippage)}bps"] = float((net > 0).mean()) if len(net) else None
        spy_col = f"{horizon}_bar_spy_return_pct"
        if spy_col in sub.columns:
            spy = pd.to_numeric(sub[spy_col], errors="coerce").dropna()
            row["mean_spy_return_pct"] = float(spy.mean()) if len(spy) else None
    return row


def _build_bootstrap(events: pd.DataFrame, trades: pd.DataFrame, spec: LongTermStudySpec) -> pd.DataFrame:
    """Ticker-year cluster bootstrap for net returns at the decision slippage."""
    source = trades if not trades.empty else events
    if source.empty:
        return pd.DataFrame()
    rng = np.random.default_rng(spec.bootstrap_seed)
    horizon = spec.hold_weeks[0]
    slippage = spec.decision_slippage_bps
    net_col = f"{horizon}_bar_net_return_pct_{spec.slippage_key(slippage)}bps"
    if net_col not in source.columns:
        return pd.DataFrame()

    # Build cluster labels: (ticker, year).
    source = source.copy()
    source["year"] = pd.to_datetime(source["signal_time"]).dt.year
    source = source[source[f"{horizon}_bar_outcome_status"] == "complete"]
    if source.empty:
        return pd.DataFrame()

    rows = []
    for split in source["split"].unique():
        for rule in source["rule"].unique():
            for group in source["group"].unique():
                sub = source[
                    (source["split"] == split)
                    & (source["rule"] == rule)
                    & (source["group"] == group)
                ]
                if sub.empty:
                    continue
                mean, lower, upper = _bootstrap_cluster_mean(
                    sub, net_col, rng, spec.bootstrap_resamples
                )
                rows.append({
                    "split": split,
                    "rule": rule,
                    "group": group,
                    "overlap_policy": sub["overlap_policy"].iloc[0],
                    "horizon_weeks": horizon,
                    "slippage_bps": slippage,
                    "count": len(sub),
                    "cluster_count": sub[["ticker", "year"]].drop_duplicates().shape[0],
                    "mean_net_return_pct": mean,
                    "ci_lower": lower,
                    "ci_upper": upper,
                })
            # Overall rule-level bootstrap (group='all').
            rule_df = source[(source["split"] == split) & (source["rule"] == rule)]
            if not rule_df.empty:
                mean, lower, upper = _bootstrap_cluster_mean(
                    rule_df, net_col, rng, spec.bootstrap_resamples
                )
                rows.append({
                    "split": split,
                    "rule": rule,
                    "group": "all",
                    "overlap_policy": rule_df["overlap_policy"].iloc[0],
                    "horizon_weeks": horizon,
                    "slippage_bps": slippage,
                    "count": len(rule_df),
                    "cluster_count": rule_df[["ticker", "year"]].drop_duplicates().shape[0],
                    "mean_net_return_pct": mean,
                    "ci_lower": lower,
                    "ci_upper": upper,
                })
    return _clean_df(pd.DataFrame(rows))


def _bootstrap_cluster_mean(
    df: pd.DataFrame,
    value_col: str,
    rng: np.random.Generator,
    n_resamples: int,
) -> tuple[float | None, float | None, float | None]:
    """Bootstrap mean by (ticker, year) clusters."""
    if df.empty:
        return None, None, None
    df = df.copy()
    df["year"] = pd.to_datetime(df["signal_time"]).dt.year
    clusters = df[["ticker", "year"]].drop_duplicates().reset_index(drop=True)
    if clusters.empty:
        return None, None, None
    n_clusters = len(clusters)
    means: list[float] = []
    for _ in range(n_resamples):
        sampled_idx = rng.choice(n_clusters, size=n_clusters, replace=True)
        selected = clusters.iloc[sampled_idx]
        selected = selected.set_index(["ticker", "year"])
        # Build mask using a merge.
        merged = df.merge(selected.reset_index(), on=["ticker", "year"], how="inner")
        values = pd.to_numeric(merged[value_col], errors="coerce").dropna()
        if len(values) == 0:
            continue
        means.append(float(values.mean()))
    if not means:
        return None, None, None
    return float(np.mean(means)), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _build_summary(events: pd.DataFrame, trades: pd.DataFrame, aggregates: dict[str, pd.DataFrame], bootstrap: pd.DataFrame, spec: LongTermStudySpec) -> dict[str, Any]:
    """Compute key summary statistics used by the conclusion gates."""
    source = trades if not trades.empty else events
    horizon = spec.hold_weeks[0]
    slippage = spec.decision_slippage_bps
    net_col = f"{horizon}_bar_net_return_pct_{spec.slippage_key(slippage)}bps"
    summary: dict[str, Any] = {
        "total_events": len(events),
        "total_trades": len(trades),
        "ticker_count": int(source["ticker"].nunique()) if not source.empty else 0,
    }

    split_stats: dict[str, dict[str, Any]] = {}
    for split in ("development", "validation", "holdout"):
        split_source = source[source["split"] == split]
        if split_source.empty:
            split_stats[split] = {"sample_present": False}
            continue
        stats: dict[str, Any] = {"sample_present": True}
        for rule in ("candidate", "baseline"):
            rule_sub = split_source[split_source["rule"] == rule]
            values = pd.to_numeric(rule_sub[net_col], errors="coerce").dropna() if net_col in rule_sub.columns else pd.Series(dtype=float)
            stats[rule] = {
                "count": len(values),
                "mean_net_return_pct": float(values.mean()) if len(values) else None,
                "median_net_return_pct": float(values.median()) if len(values) else None,
                "win_rate": float((values > 0).mean()) if len(values) else None,
                "ticker_count": int(rule_sub["ticker"].nunique()),
                "max_ticker_concentration": float(
                    rule_sub["ticker"].value_counts(normalize=True).max()
                ) if not rule_sub.empty else None,
            }
        # Per-ticker lifts.
        candidate_tickers = split_source[split_source["rule"] == "candidate"].groupby("ticker")[net_col].mean()
        baseline_tickers = split_source[split_source["rule"] == "baseline"].groupby("ticker")[net_col].mean()
        all_tickers = candidate_tickers.index.union(baseline_tickers.index)
        lifts = []
        for t in all_tickers:
            c = candidate_tickers.get(t)
            b = baseline_tickers.get(t)
            if pd.notna(c) and pd.notna(b):
                lifts.append(float(c - b))
        stats["median_ticker_lift_bps"] = float(np.median(lifts)) * 100.0 if lifts else None
        stats["positive_lift_fraction"] = float(np.mean([l > 0 for l in lifts])) if lifts else None
        stats["mean_lift_bps"] = float(np.mean(lifts)) * 100.0 if lifts else None
        split_stats[split] = stats
    summary["split_stats"] = split_stats

    # Holdout halves.
    holdout = source[source["split"] == "holdout"]
    if not holdout.empty and "signal_time" in holdout.columns:
        holdout = holdout.copy()
        holdout["signal_time"] = pd.to_datetime(holdout["signal_time"])
        mid = holdout["signal_time"].median()
        first = holdout[holdout["signal_time"] <= mid]
        second = holdout[holdout["signal_time"] > mid]
        for half, label in ((first, "first_half"), (second, "second_half")):
            rule_sub = half[half["rule"] == "candidate"]
            values = pd.to_numeric(rule_sub[net_col], errors="coerce").dropna() if net_col in rule_sub.columns else pd.Series(dtype=float)
            summary[f"holdout_candidate_{label}_mean_net_return_pct"] = float(values.mean()) if len(values) else None

    # Bootstrap stats for conclusion gates (group='all' for rule-level CI).
    bootstrap_stats: dict[str, dict[str, Any]] = {}
    if not bootstrap.empty:
        for _idx, row in bootstrap.iterrows():
            if row.get("group") != "all":
                continue
            split = row.get("split")
            rule = row.get("rule")
            if split is None or rule is None:
                continue
            bootstrap_stats.setdefault(split, {})[rule] = {
                "mean_net_return_pct": row.get("mean_net_return_pct"),
                "ci_lower": row.get("ci_lower"),
                "ci_upper": row.get("ci_upper"),
                "cluster_count": row.get("cluster_count"),
            }
    summary["bootstrap_stats"] = bootstrap_stats

    return _clean(summary)


def _derive_conclusion(events: pd.DataFrame, trades: pd.DataFrame, summary: dict[str, Any], spec: LongTermStudySpec) -> str:
    """Apply the predefined LONG-001 evidence gates."""
    splits = ("validation", "holdout")

    # Sample-size / concentration gates.
    sample_ok = True
    for split in splits:
        stats = summary.get("split_stats", {}).get(split, {})
        if not stats.get("sample_present"):
            sample_ok = False
            continue
        for rule in ("candidate", "baseline"):
            rule_stats = stats.get(rule, {})
            if rule_stats.get("count", 0) < spec.minimum_signals:
                sample_ok = False
            if rule_stats.get("ticker_count", 0) < spec.minimum_tickers:
                sample_ok = False
            if rule_stats.get("max_ticker_concentration", 0.0) and rule_stats["max_ticker_concentration"] > spec.max_ticker_concentration:
                sample_ok = False

    if not sample_ok:
        return "inconclusive"

    # Return and lift gates.
    all_pass = True
    for split in splits:
        stats = summary["split_stats"][split]
        c = stats.get("candidate", {})
        b = stats.get("baseline", {})
        c_mean = c.get("mean_net_return_pct")
        b_mean = b.get("mean_net_return_pct")
        if c_mean is None or b_mean is None:
            all_pass = False
            continue
        if not (c_mean > 0 and b_mean is not None):
            all_pass = False
        lift_bps = (c_mean - b_mean) * 100.0
        if lift_bps < spec.minimum_lift_bps:
            all_pass = False
        median_lift = stats.get("median_ticker_lift_bps")
        if median_lift is None or median_lift <= 0:
            all_pass = False
        pos_frac = stats.get("positive_lift_fraction")
        if pos_frac is None or pos_frac < spec.ticker_positive_fraction:
            all_pass = False

    # Holdout halves.
    first = summary.get("holdout_candidate_first_half_mean_net_return_pct")
    second = summary.get("holdout_candidate_second_half_mean_net_return_pct")
    if first is None or second is None or first <= 0 or second <= 0:
        all_pass = False

    # Bootstrap lower CI gates.
    bootstrap_stats = summary.get("bootstrap_stats", {})
    for split in splits:
        sub = bootstrap_stats.get(split, {})
        c_lower = sub.get("candidate", {}).get("ci_lower")
        if c_lower is None or c_lower <= 0:
            all_pass = False

    if all_pass:
        return "supported"
    return "rejected"


def _generate_report(
    spec: LongTermStudySpec,
    manifest: DatasetManifest,
    events: pd.DataFrame,
    trades: pd.DataFrame,
    aggregates: dict[str, pd.DataFrame],
    bootstrap: pd.DataFrame,
    data_quality: pd.DataFrame,
    summary: dict[str, Any],
    conclusion: str,
) -> str:
    horizon = spec.hold_weeks[0]
    lines = [
        "# LONG-001: Long-Term Scorer Evaluation Report",
        "",
        "## Study objective",
        "",
        "Compare the current production `long_term.score` (threshold 40) with a simple `close > 40-week simple moving average` baseline on weekly OHLCV bars. This is a research-only evaluation; it does **not** change production scoring.",
        "",
        "## Spec",
        "",
        f"- Universe: `{', '.join(spec.universe)}`",
        f"- Benchmark: `{spec.benchmark_ticker}`",
        f"- Provider: `{spec.provider}`",
        f"- Timeframe: `{spec.timeframe}`",
        f"- Date range: `{spec.start}` to `{spec.end}`",
        f"- Warm-up: `{spec.start}` to `{spec.warmup_end}`",
        f"- Development: `{spec.warmup_end}` (+1 day) to `{spec.development_end}`",
        f"- Validation: `{spec.development_end}` (+1 day) to `{spec.validation_end}`",
        f"- Holdout: `{spec.validation_end}` (+1 day) to `{spec.end}`",
        f"- Primary horizon: `{horizon}` weeks",
        f"- Score threshold: `score >= {spec.score_thresholds[0]}`",
        f"- Slippage scenarios (bps): `{', '.join(map(str, spec.slippage_scenarios_bps))}`",
        f"- Decision slippage (bps): `{spec.decision_slippage_bps}`",
        f"- Commission (bps): `{spec.commission_bps}`",
        f"- Spec SHA-256: `{spec.sha256}`",
        f"- Manifest SHA-256: `{manifest.sha256}`",
        "",
        "## Weight snapshot",
        "",
        "The study used a fresh `LongWeights()` default instance, not any saved user configuration.",
        "",
        "| Component | Weight |",
        "|---|---|",
    ]
    for k, v in spec.weights.__dict__.items():
        lines.append(f"| {k} | {v} |")

    lines.extend(["", "## Data quality", ""])
    lines.append(_df_to_markdown(data_quality))

    lines.extend(["", "## Events and trades", ""])
    lines.append(f"Total overlapping events: `{len(events)}`")
    lines.append(f"Total non-overlapping trades: `{len(trades)}`")
    if "rule" in events.columns:
        lines.append("Events by rule:")
        lines.append(_df_to_markdown(events["rule"].value_counts().reset_index()))

    lines.extend(["", "## Split summary", ""])
    for split, stats in summary.get("split_stats", {}).items():
        if not stats.get("sample_present"):
            lines.append(f"- **{split}**: no sample")
            continue
        lines.append(f"- **{split}**:")
        for rule in ("candidate", "baseline"):
            rs = stats.get(rule, {})
            lines.append(
                f"  - {rule}: count={_clean_cell(rs.get('count'))}, mean_net={_clean_cell(rs.get('mean_net_return_pct'))}, "
                f"win_rate={_clean_cell(rs.get('win_rate'))}, tickers={_clean_cell(rs.get('ticker_count'))}"
            )
        lines.append(
            f"  - mean lift (bps): {_clean_cell(stats.get('mean_lift_bps'))}, "
            f"median ticker lift (bps): {_clean_cell(stats.get('median_ticker_lift_bps'))}, "
            f"positive lift fraction: {_clean_cell(stats.get('positive_lift_fraction'))}"
        )

    for name, df in aggregates.items():
        lines.extend(["", f"## {name}", ""])
        lines.append(_df_to_markdown(df))

    lines.extend(["", "## Bootstrap (5,000 ticker-year cluster resamples)", ""])
    lines.append(_df_to_markdown(bootstrap))

    lines.extend(["", "## Conclusion", ""])
    lines.append(f"**{conclusion}**")
    lines.append("")
    lines.append(
        "This conclusion is based on the locked protocol, point-in-time scoring, "
        "cross-split exclusion, and non-overlapping per-ticker trade simulation. "
        "It does not authorize a production change."
    )

    lines.extend(["", "## Limitations", ""])
    for lim in _LIMITATIONS:
        lines.append(f"- {lim}")
    return "\n".join(lines)


_LIMITATIONS = [
    "Events are weekly observations and may overlap within and across tickers in the event-study output.",
    "The non-overlapping trade policy uses the primary 13-week horizon for spacing and ignores capital allocation.",
    "Execution assumes fills at the next weekly open and exit at the weekly close; real intraday slippage and partial fills are not modeled.",
    "The study does not model stops, targets, position sizing, capital allocation, or capacity.",
    "Survivorship bias, delisting bias, and point-in-time index membership are not eliminated.",
    "Corporate actions and dividend reinvestment use the provider's default adjustment policy (auto_adjust=True).",
    "Reported metrics are research evidence, not proof of a durable edge or statistical significance.",
    "A positive result here would still require a separate Gary-approved production promotion PR.",
]


def _sort_columns(df: pd.DataFrame) -> pd.DataFrame:
    first = ["ticker", "split", "rule", "group", "overlap_policy", "cohort", "signal_time", "score"]
    first = [c for c in first if c in df.columns]
    rest = sorted(c for c in df.columns if c not in first)
    return df[first + rest]
