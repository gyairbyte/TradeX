"""Point-in-time evaluation engine for LONG-001."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from tradex.signals import long_term
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

    protocol_sha256 = _protocol_file_sha256(spec)
    protocol_commit = _protocol_commit(spec)

    report = _generate_report(
        spec, manifest, protocol_sha256, protocol_commit,
        events_df, trades_df, aggregates, bootstrap, data_quality, summary, conclusion,
    )

    result = StudyResult(
        spec=spec,
        manifest=manifest,
        protocol_sha256=protocol_sha256,
        protocol_commit=protocol_commit,
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


def _protocol_file_sha256(spec: LongTermStudySpec) -> str:
    from pathlib import Path
    path = Path(spec.protocol_path)
    if path.exists():
        return _file_sha256(path)
    return ""


def _protocol_commit(spec: LongTermStudySpec) -> str | None:
    import subprocess
    from pathlib import Path
    path = Path(spec.protocol_path)
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", str(path)],
            cwd=Path(__file__).resolve().parents[3],
            capture_output=True,
            text=True,
            check=False,
        )
        commit = result.stdout.strip()
        return commit if commit else None
    except Exception:  # noqa: BLE001
        return None


def _load_ticker_df(entry: ManifestEntry, data_dir: Path, spec: LongTermStudySpec) -> pd.DataFrame:
    path = data_dir / entry.path
    if _file_sha256(path) != entry.sha256:
        raise StudyError(f"Hash mismatch for {entry.ticker}")
    df = pd.read_csv(path, index_col="datetime", parse_dates=True)
    df, _, _, _ = _validate_bars(df, entry.ticker)
    weekly = _aggregate_daily_to_weekly(df)
    min_bars = max(spec.warmup_weeks, spec.min_required_weekly_bars)
    if len(weekly) < min_bars:
        raise StudyError(f"{entry.ticker}: only {len(weekly)} weekly bars, need {min_bars}")
    return weekly


def _evaluate_ticker(
    entry: ManifestEntry,
    weekly: pd.DataFrame,
    spy_weekly: pd.DataFrame,
    spec: LongTermStudySpec,
) -> tuple[list[EventRecord], list[EventRecord]]:
    """Generate overlapping event-study and non-overlapping trade records for one ticker."""
    n = len(weekly)
    cohort = spec.cohort_for(entry.ticker)

    candidate_scores, reasons_list = _score_vectorized(weekly, spec)
    ma40_series, baseline_flags = _baseline_vectorized(weekly, spec)

    start_idx = max(0, spec.min_required_weekly_bars - 1)

    events: list[EventRecord] = []
    for i in range(start_idx, n):
        signal_time = weekly.index[i].to_pydatetime()
        split = spec.split_for(signal_time)
        if split in ("warmup", "out_of_range"):
            continue
        score = candidate_scores[i]
        ma40 = ma40_series.iloc[i]
        close = float(weekly["close"].iloc[i])

        if not math.isnan(score) and any(score >= t for t in spec.score_thresholds):
            group = "baseline_and_candidate" if baseline_flags[i] else "candidate_only"
            events.extend(
                _make_records(
                    entry, cohort, signal_time, split, "candidate", group, score,
                    reasons_list[i], close, ma40, weekly, spy_weekly, i, spec, "overlapping"
                )
            )
        if baseline_flags[i]:
            group = "baseline_and_candidate" if not math.isnan(score) and any(score >= t for t in spec.score_thresholds) else "baseline_only"
            events.extend(
                _make_records(
                    entry, cohort, signal_time, split, "baseline", group, None,
                    ["close > 40-week SMA"], close, ma40, weekly, spy_weekly, i, spec, "overlapping"
                )
            )

    trades: list[EventRecord] = []
    for rule in ("candidate", "baseline"):
        next_idx = start_idx
        for i in range(start_idx, n):
            if i < next_idx:
                continue
            flag = (
                (not math.isnan(candidate_scores[i]) and any(candidate_scores[i] >= t for t in spec.score_thresholds))
                if rule == "candidate" else baseline_flags[i]
            )
            if not flag:
                continue
            signal_time = weekly.index[i].to_pydatetime()
            split = spec.split_for(signal_time)
            if split in ("warmup", "out_of_range"):
                continue
            score = candidate_scores[i] if rule == "candidate" else None
            reasons = reasons_list[i] if rule == "candidate" else ["close > 40-week SMA"]
            other_flag = baseline_flags[i] if rule == "candidate" else (
                not math.isnan(candidate_scores[i]) and any(candidate_scores[i] >= t for t in spec.score_thresholds)
            )
            group = "baseline_and_candidate" if other_flag else (
                "candidate_only" if rule == "candidate" else "baseline_only"
            )
            close = float(weekly["close"].iloc[i])
            ma40 = ma40_series.iloc[i]
            recs = _make_records(
                entry, cohort, signal_time, split, rule, group, score, reasons, close,
                ma40, weekly, spy_weekly, i, spec, "non_overlapping"
            )
            trades.extend(recs)

            primary = spec.hold_weeks[0]
            primary_status = recs[0].outcomes[primary].outcome_status
            if primary_status == "cross_split_excluded":
                next_idx = i + 1
            elif primary_status == "insufficient_future_bars":
                next_idx = n
            else:
                entry_idx = i + spec.entry_delay_bars
                exit_idx = entry_idx + primary
                next_idx = exit_idx + 1

    return events, trades


def _score_vectorized(
    weekly: pd.DataFrame, spec: LongTermStudySpec
) -> tuple[np.ndarray, list[list[str]]]:
    """Compute the production-equivalent long-term score for every bar.

    The returned scores and reasons are exact matches for
    ``long_term.score(weekly.iloc[: i + 1], weights=spec.weights)`` because the
    same point-in-time indicator windows and rank logic are used.  A separate
    parity test asserts this for every bar.
    """
    ind = add_indicators(weekly.copy())
    n = len(ind)

    close = ind["close"].astype(float)
    ema50 = ind["ema_50"]
    rsi = ind["rsi"]
    macd = ind["macd"]
    macd_signal = ind["macd_signal"]
    bb_width = ind["bb_width"]
    volume_ratio = ind["volume_ratio"]

    recent_vol = volume_ratio.rolling(8, min_periods=1).mean()
    bb_pct = bb_width.expanding().rank(pct=True)

    cond_uptrend = close > ema50
    cond_rsi = (rsi >= 40) & (rsi <= 65)
    cond_vol = recent_vol >= 1.15
    cond_macd = macd > macd_signal
    cond_bb = bb_pct < 0.25

    weights = spec.weights
    signals = np.zeros(n, dtype=int)
    reasons: list[list[str]] = []

    for i in range(n):
        s = 0
        r: list[str] = []
        if cond_uptrend.iloc[i]:
            s += weights.secular_uptrend
            r.append("Price above long-term EMA50 — secular uptrend")
        if cond_rsi.iloc[i]:
            s += weights.rsi_healthy
            r.append(f"RSI healthy, not overbought ({rsi.iloc[i]:.0f})")
        if cond_vol.iloc[i]:
            s += weights.volume_accumulation
            r.append(f"8-period volume accumulation ({recent_vol.iloc[i]:.2f}x avg)")
        if cond_macd.iloc[i]:
            s += weights.macd_bullish
            r.append("MACD above signal on weekly — bullish bias")
        if cond_bb.iloc[i]:
            s += weights.bb_coil
            r.append("Tight BB on weekly — coiling for breakout")
        signals[i] = s
        reasons.append(r)

    scores = np.minimum(signals, 100)
    return scores, reasons


def _score_bar(weekly: pd.DataFrame, i: int, spec: LongTermStudySpec) -> tuple[float, list[str]]:
    """Direct production-scorer parity helper for a single bar."""
    result = long_term.score(weekly.iloc[: i + 1], weights=spec.weights)
    return float(result["score"]), list(result["reasons"])


def _baseline_vectorized(
    weekly: pd.DataFrame, spec: LongTermStudySpec
) -> tuple[pd.Series, np.ndarray]:
    """Compute the 40-week SMA and baseline eligibility at every bar."""
    close = weekly["close"].astype(float)
    ma40 = close.rolling(40, min_periods=40).mean()
    baseline_flags = (close > ma40).to_numpy().copy()
    baseline_flags[np.isnan(ma40.to_numpy())] = False
    return ma40, baseline_flags


def _ma40_value(weekly: pd.DataFrame, i: int) -> float | None:
    if i < 39:
        return None
    return float(weekly["close"].iloc[i - 39 : i + 1].mean())


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
    entry_time = (
        weekly["first_session_open_time"].iloc[entry_idx].to_pydatetime()
        if entry_idx < len(weekly) else None
    )
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

    if entry_idx >= n:
        for h in spec.hold_weeks:
            outcomes[h] = _incomplete_outcome(h, spec, "insufficient_future_bars")
        return outcomes

    entry_time_open = weekly["first_session_open_time"].iloc[entry_idx]
    entry_split = spec.split_for(entry_time_open)

    if signal_split != entry_split:
        for h in spec.hold_weeks:
            outcomes[h] = _incomplete_outcome(h, spec, "cross_split_excluded")
        return outcomes

    for h in spec.hold_weeks:
        exit_idx = entry_idx + h
        if exit_idx >= n:
            outcomes[h] = _incomplete_outcome(h, spec, "insufficient_future_bars")
            continue
        exit_time = weekly.index[exit_idx].to_pydatetime()
        exit_split = spec.split_for(exit_time)
        if signal_split != exit_split:
            outcomes[h] = _incomplete_outcome(h, spec, "cross_split_excluded")
            continue

        entry_price = float(weekly["open"].iloc[entry_idx])
        exit_price = float(weekly["close"].iloc[exit_idx])
        gross = (exit_price / entry_price - 1.0) * 100.0

        entry_week_close = weekly.index[entry_idx].to_pydatetime()
        exit_week_close = weekly.index[exit_idx].to_pydatetime()
        spy_entry, spy_exit = _spy_prices(spy_weekly, entry_week_close, exit_week_close)
        spy_gross = None
        if spy_entry is not None and spy_exit is not None and spy_entry > 0:
            spy_gross = (spy_exit / spy_entry - 1.0) * 100.0

        net_by_slippage: dict[str, float] = {}
        spy_net_by_slippage: dict[str, float | None] = {}
        for s in (*spec.slippage_scenarios_bps, spec.decision_slippage_bps):
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
    keys = {spec.slippage_key(s) for s in (*spec.slippage_scenarios_bps, spec.decision_slippage_bps)}
    return EventOutcome(
        horizon=horizon,
        exit_time=None,
        raw_exit_price=None,
        gross_return_pct=None,
        net_return_pct_by_slippage={k: None for k in keys},
        spy_return_pct=None,
        spy_net_return_pct_by_slippage={k: None for k in keys},
        outcome_status=status,  # type: ignore[arg-type]
    )


def _spy_prices(spy_weekly: pd.DataFrame, entry_week_close: datetime, exit_week_close: datetime) -> tuple[float | None, float | None]:
    """Return SPY's open for the entry week and close for the exit week."""
    entry = _spy_price(spy_weekly, entry_week_close, "open")
    exit_ = _spy_price(spy_weekly, exit_week_close, "close")
    return entry, exit_


def _spy_price(spy_weekly: pd.DataFrame, week_close_time: datetime, price_col: str) -> float | None:
    """Find the SPY weekly bar whose final session matches ``week_close_time`` (by date)."""
    if spy_weekly.empty:
        return None
    target = week_close_time.astimezone(UTC).date()
    dates = spy_weekly.index.to_series().dt.tz_convert("UTC").apply(lambda t: t.date())
    matches = spy_weekly[dates == target]
    if matches.empty:
        return None
    value = float(matches[price_col].iloc[0])
    if math.isnan(value) or value <= 0:
        return None
    return value


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

    # Cost sensitivity (net returns at each slippage scenario).
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
    sample_status = "sufficient_sample" if len(values) >= spec.min_events_per_group else "insufficient_sample"
    row: dict[str, Any] = {
        "rule": rule,
        "split": split,
        "horizon_weeks": horizon,
        "count": len(values),
        "sample_status": sample_status,
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
    """Paired candidate-minus-baseline ticker-year cluster bootstrap."""
    source = trades if not trades.empty else events
    if source.empty:
        return pd.DataFrame()
    horizon = spec.hold_weeks[0]
    slippage = spec.decision_slippage_bps
    net_col = f"{horizon}_bar_net_return_pct_{spec.slippage_key(slippage)}bps"
    status_col = f"{horizon}_bar_outcome_status"
    if net_col not in source.columns:
        return pd.DataFrame()
    df = source[source[status_col] == "complete"].copy()
    if df.empty:
        return pd.DataFrame()
    df["year"] = pd.to_datetime(df["signal_time"]).dt.year

    rows = []
    rng = np.random.default_rng(spec.bootstrap_seed)
    for split in sorted(df["split"].unique()):
        sub = df[df["split"] == split]
        if sub.empty:
            continue
        mean, lower, upper = _bootstrap_paired_diff(sub, net_col, rng, spec.bootstrap_resamples)
        if mean is None:
            continue
        cluster_count = sub[["ticker", "year"]].drop_duplicates().shape[0]
        rows.append({
            "split": split,
            "rule_pair": "candidate_minus_baseline",
            "horizon_weeks": horizon,
            "slippage_bps": slippage,
            "count": len(sub),
            "cluster_count": cluster_count,
            "mean_diff_pct": mean,
            "ci_lower": lower,
            "ci_upper": upper,
        })
    return _clean_df(pd.DataFrame(rows))


def _bootstrap_paired_diff(
    df: pd.DataFrame,
    net_col: str,
    rng: np.random.Generator,
    n_resamples: int,
) -> tuple[float | None, float | None, float | None]:
    """Bootstrap the mean of per-(ticker,year) candidate-minus-baseline differences."""
    if df.empty:
        return None, None, None

    # Per-cluster mean for each rule; keep only clusters that contain both rules.
    grouped = df.groupby(["ticker", "year", "rule"])[net_col].mean().unstack("rule")
    if "candidate" not in grouped.columns or "baseline" not in grouped.columns:
        return None, None, None
    paired = grouped.dropna(subset=["candidate", "baseline"]).copy()
    paired["diff"] = paired["candidate"] - paired["baseline"]
    if paired.empty:
        return None, None, None

    diffs: list[float] = []
    n_clusters = len(paired)
    values = paired["diff"].to_numpy(dtype=float)
    for _ in range(n_resamples):
        idx = rng.choice(n_clusters, size=n_clusters, replace=True)
        sample = values[idx]
        diffs.append(float(sample.mean()))

    if not diffs:
        return None, None, None
    return float(np.mean(diffs)), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def _build_summary(events: pd.DataFrame, trades: pd.DataFrame, aggregates: dict[str, pd.DataFrame], bootstrap: pd.DataFrame, spec: LongTermStudySpec) -> dict[str, Any]:
    """Compute key summary statistics used by the conclusion gates."""
    source = trades if not trades.empty else events
    horizon = spec.hold_weeks[0]
    slippage = spec.decision_slippage_bps
    net_col = f"{horizon}_bar_net_return_pct_{spec.slippage_key(slippage)}bps"
    status_col = f"{horizon}_bar_outcome_status"
    summary: dict[str, Any] = {
        "total_events": len(events),
        "total_trades": len(trades),
        "ticker_count": int(source["ticker"].nunique()) if not source.empty else 0,
    }

    def _rule_stats(split_df: pd.DataFrame, rule: str) -> dict[str, Any]:
        sub = split_df[(split_df["rule"] == rule) & (split_df[status_col] == "complete")]
        vals = pd.to_numeric(sub[net_col], errors="coerce").dropna()
        cohorts = sub.groupby("cohort")["ticker"].nunique().to_dict()
        return {
            "count": len(vals),
            "ticker_count": int(sub["ticker"].nunique()),
            "stock_ticker_count": int(cohorts.get("stock", 0)),
            "etf_ticker_count": int(cohorts.get("etf", 0)),
            "mean_net_return_pct": float(vals.mean()) if len(vals) else None,
            "median_net_return_pct": float(vals.median()) if len(vals) else None,
            "std_net_return_pct": float(vals.std(ddof=0)) if len(vals) > 1 else None,
            "win_rate": float((vals > 0).mean()) if len(vals) else None,
            "q10_net_return_pct": float(vals.quantile(0.10)) if len(vals) else None,
        }

    split_stats: dict[str, dict[str, Any]] = {}
    for split in ("development", "validation", "holdout"):
        split_source = source[source["split"] == split]
        if split_source.empty:
            split_stats[split] = {"sample_present": False}
            continue
        stats: dict[str, Any] = {"sample_present": True}
        for rule in ("candidate", "baseline"):
            stats[rule] = _rule_stats(split_source, rule)

        # Per-ticker lifts by cohort.
        ticker_stats: list[dict[str, Any]] = []
        for ticker, sub in split_source.groupby("ticker"):
            cand = pd.to_numeric(
                sub[(sub["rule"] == "candidate") & (sub[status_col] == "complete")][net_col],
                errors="coerce",
            ).dropna()
            base = pd.to_numeric(
                sub[(sub["rule"] == "baseline") & (sub[status_col] == "complete")][net_col],
                errors="coerce",
            ).dropna()
            if len(cand) == 0 or len(base) == 0:
                continue
            ticker_stats.append({
                "ticker": ticker,
                "cohort": sub["cohort"].iloc[0],
                "candidate_count": len(cand),
                "baseline_count": len(base),
                "candidate_mean": float(cand.mean()),
                "baseline_mean": float(base.mean()),
                "lift": float(cand.mean() - base.mean()),
            })
        stats["per_ticker"] = ticker_stats

        def _cohort_positive_fraction(cohort: str) -> float | None:
            sampled = [
                t["lift"] for t in ticker_stats
                if t["cohort"] == cohort
                and t["candidate_count"] >= spec.min_ticker_trades_for_cohort_gate
                and t["baseline_count"] >= spec.min_ticker_trades_for_cohort_gate
            ]
            if not sampled:
                return None
            return float(np.mean([l > 0 for l in sampled]))

        stats["positive_lift_fraction_stock"] = _cohort_positive_fraction("stock")
        stats["positive_lift_fraction_etf"] = _cohort_positive_fraction("etf")

        # Pooled lift at decision slippage and at cost-sensitivity slippage.
        cand_all = pd.to_numeric(
            split_source[(split_source["rule"] == "candidate") & (split_source[status_col] == "complete")][net_col],
            errors="coerce",
        ).dropna()
        base_all = pd.to_numeric(
            split_source[(split_source["rule"] == "baseline") & (split_source[status_col] == "complete")][net_col],
            errors="coerce",
        ).dropna()
        stats["pooled_lift_pct"] = float(cand_all.mean() - base_all.mean()) if len(cand_all) and len(base_all) else None

        cost_col = f"{horizon}_bar_net_return_pct_{spec.slippage_key(spec.cost_sensitivity_slippage_bps)}bps"
        cand_cost = pd.to_numeric(
            split_source[(split_source["rule"] == "candidate") & (split_source[status_col] == "complete")][cost_col],
            errors="coerce",
        ).dropna()
        base_cost = pd.to_numeric(
            split_source[(split_source["rule"] == "baseline") & (split_source[status_col] == "complete")][cost_col],
            errors="coerce",
        ).dropna()
        stats["pooled_lift_at_cost_sensitivity_pct"] = (
            float(cand_cost.mean() - base_cost.mean()) if len(cand_cost) and len(base_cost) else None
        )

        # Downside comparison at decision slippage.
        stats["q10_lift_pct"] = (
            float(stats["candidate"].get("q10_net_return_pct", np.nan) - stats["baseline"].get("q10_net_return_pct", np.nan))
            if stats["candidate"].get("q10_net_return_pct") is not None and stats["baseline"].get("q10_net_return_pct") is not None
            else None
        )

        split_stats[split] = stats
    summary["split_stats"] = split_stats

    # Bootstrap stats per split.
    bootstrap_stats: dict[str, dict[str, Any]] = {}
    if not bootstrap.empty:
        for _idx, row in bootstrap.iterrows():
            split = row.get("split")
            if split is None:
                continue
            bootstrap_stats[split] = {
                "mean_diff_pct": row.get("mean_diff_pct"),
                "ci_lower": row.get("ci_lower"),
                "ci_upper": row.get("ci_upper"),
                "cluster_count": row.get("cluster_count"),
            }
    summary["bootstrap_stats"] = bootstrap_stats

    return _clean(summary)


def _derive_conclusion(events: pd.DataFrame, trades: pd.DataFrame, summary: dict[str, Any], spec: LongTermStudySpec) -> str:
    """Apply the predefined LONG-001 evidence gates."""
    hold = summary.get("split_stats", {}).get("holdout", {})
    if not hold.get("sample_present"):
        return "inconclusive"

    cand = hold.get("candidate", {})
    base = hold.get("baseline", {})
    cand_mean = cand.get("mean_net_return_pct")
    base_mean = base.get("mean_net_return_pct")
    lift = None if cand_mean is None or base_mean is None else cand_mean - base_mean

    bootstrap = summary.get("bootstrap_stats", {}).get("holdout", {})
    ci_upper = bootstrap.get("ci_upper")
    ci_lower = bootstrap.get("ci_lower")

    q10_lift = hold.get("q10_lift_pct")

    # Reject gates.
    if ci_upper is not None and ci_upper <= 0:
        return "reject_or_deprioritize"
    if lift is not None and lift <= -spec.reject_point_estimate_worse_bps / 100.0:
        return "reject_or_deprioritize"
    if q10_lift is not None and q10_lift < -spec.q10_reject_worse_bps / 100.0:
        if lift is None or lift <= 0:
            return "reject_or_deprioritize"

    # Sample-size precondition for support.
    if (
        cand.get("count", 0) < spec.minimum_signals
        or base.get("count", 0) < spec.minimum_signals
    ):
        return "inconclusive"
    combined_tickers = set()
    if not events.empty:
        hold_df = events[(events["split"] == "holdout") & (events["overlap_policy"] == "non_overlapping")]
        if not hold_df.empty:
            combined_tickers = set(hold_df["ticker"].unique())
    else:
        combined_tickers = set()
    stock_count = sum(1 for t in combined_tickers if spec.cohort_for(t) == "stock")
    etf_count = sum(1 for t in combined_tickers if spec.cohort_for(t) == "etf")
    if stock_count < spec.minimum_stock_tickers or etf_count < spec.minimum_etf_tickers:
        return "inconclusive"

    # Support gates.
    if lift is None or lift < spec.minimum_lift_bps / 100.0:
        return "inconclusive"
    if ci_lower is None or ci_lower <= 0:
        return "inconclusive"
    if q10_lift is None or q10_lift < -spec.q10_support_max_worse_bps / 100.0:
        return "inconclusive"
    if hold.get("pooled_lift_at_cost_sensitivity_pct") is None or hold["pooled_lift_at_cost_sensitivity_pct"] <= 0:
        return "inconclusive"
    if hold.get("positive_lift_fraction_stock") is None or hold["positive_lift_fraction_stock"] < spec.ticker_positive_fraction_stock:
        return "inconclusive"
    if hold.get("positive_lift_fraction_etf") is None or hold["positive_lift_fraction_etf"] < spec.ticker_positive_fraction_etf:
        return "inconclusive"

    # Validation-period direction must also be positive.
    val = summary.get("split_stats", {}).get("validation", {})
    if not val.get("sample_present"):
        return "inconclusive"
    val_cand = val.get("candidate", {})
    val_base = val.get("baseline", {})
    val_lift = None
    if val_cand.get("mean_net_return_pct") is not None and val_base.get("mean_net_return_pct") is not None:
        val_lift = val_cand["mean_net_return_pct"] - val_base["mean_net_return_pct"]
    if val_lift is None or val_lift <= 0:
        return "inconclusive"

    return "supports_further_research"


def _generate_report(
    spec: LongTermStudySpec,
    manifest: DatasetManifest,
    protocol_sha256: str,
    protocol_commit: str | None,
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
        "## Pre-registration authority",
        "",
        f"- Protocol source: `{spec.protocol_source}`",
        f"- Locked protocol file: `{spec.protocol_path}`",
        f"- Protocol SHA-256: `{protocol_sha256}`" if protocol_sha256 else "- Protocol SHA-256: not available",
        f"- Protocol lock commit: `{protocol_commit}`" if protocol_commit else "- Protocol lock commit: not available",
        "",
        "## Spec",
        "",
        f"- Universe: `{', '.join(spec.universe)}`",
        f"- Benchmark: `{spec.benchmark_ticker}`",
        f"- Provider: `{spec.provider}`",
        f"- Timeframe: `{spec.timeframe}`",
        f"- Adjustment policy: `{spec.adjustment_policy}`",
        f"- Date range: `{spec.start}` to `{spec.end}`",
        f"- Warm-up: `{spec.start}` to `{spec.warmup_end}`",
        f"- Development: `{spec.warmup_end}` (+1 day) to `{spec.development_end}`",
        f"- Validation: `{spec.development_end}` (+1 day) to `{spec.validation_end}`",
        f"- Holdout: `{spec.validation_end}` (+1 day) to `{spec.end}`",
        f"- Primary horizon: `{horizon}` weeks",
        f"- Score threshold: `score >= {spec.score_thresholds[0]}`",
        f"- Score buckets: `{', '.join(spec.bucket_labels())}`",
        f"- Slippage scenarios (bps per side): `{', '.join(map(str, spec.slippage_scenarios_bps))}`",
        f"- Decision slippage (bps per side): `{spec.decision_slippage_bps}`",
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
            f"  - pooled lift (pct): {_clean_cell(stats.get('pooled_lift_pct'))}, "
            f"median lift at {spec.cost_sensitivity_slippage_bps}bps per side (pct): {_clean_cell(stats.get('pooled_lift_at_cost_sensitivity_pct'))}, "
            f"q10 lift (pct): {_clean_cell(stats.get('q10_lift_pct'))}"
        )
        lines.append(
            f"  - positive lift fraction stock: {_clean_cell(stats.get('positive_lift_fraction_stock'))}, "
            f"positive lift fraction etf: {_clean_cell(stats.get('positive_lift_fraction_etf'))}"
        )

    for name, df in aggregates.items():
        lines.extend(["", f"## {name}", ""])
        lines.append(_df_to_markdown(df))

    lines.extend(["", "## Bootstrap (paired candidate-minus-baseline, ticker-year clusters)", ""])
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
