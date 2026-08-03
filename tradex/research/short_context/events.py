"""Point-in-time context event generation and forward-return calculation."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from tradex.market.context import is_context_eligible
from tradex.market.models import ShortContextPolicy
from tradex.research.score_validation.events import (
    _incomplete_outcome,
    _net_return,
    _split_for,
    _within_split,
)
from tradex.research.score_validation.manifest import load_manifest
from tradex.research.score_validation.models import (
    DataQualityRow,
    EventOutcome,
    ScoreValidationConfig,
)
from tradex.research.short_context.alignment import context_for_signal, load_ticker_df
from tradex.research.short_context.models import (
    ContextEventRecord,
    ShortContextSpec,
)
from tradex.signals.short_term import score as short_term_score
from tradex.signals.weights import ShortWeights


def generate_context_events(
    manifest_path: str | Path,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
) -> tuple[list[ContextEventRecord], list[DataQualityRow]]:
    """Generate context-aware events for every target ticker in the manifest."""
    manifest = load_manifest(manifest_path)
    events: list[ContextEventRecord] = []
    quality_rows: list[DataQualityRow] = []

    # Preload proxy dataframes.
    proxy_dfs: dict[str, pd.DataFrame] = {}
    for proxy in spec.proxy_tickers():
        proxy_dfs[proxy] = load_ticker_df(manifest, proxy)

    for ticker in spec.target_tickers:
        ticker_df = load_ticker_df(manifest, ticker)
        market_proxy = spec.ticker_context[ticker]["market_proxy"]
        sector_proxy = spec.ticker_context[ticker].get("sector_proxy")
        market_df = proxy_dfs[market_proxy]
        sector_df = proxy_dfs.get(sector_proxy) if sector_proxy else None

        ticker_events, quality = _generate_ticker_context_events(
            ticker,
            ticker_df,
            market_df,
            sector_df,
            market_proxy,
            sector_proxy,
            spec,
            config,
            manifest.splits,
        )
        events.extend(ticker_events)
        quality_rows.append(quality)

    return events, quality_rows


def _generate_ticker_context_events(
    ticker: str,
    ticker_df: pd.DataFrame,
    market_df: pd.DataFrame,
    sector_df: pd.DataFrame | None,
    market_proxy: str,
    sector_proxy: str | None,
    spec: ShortContextSpec,
    config: ScoreValidationConfig,
    splits: dict,
) -> tuple[list[ContextEventRecord], DataQualityRow]:
    """Generate events for a single target ticker."""
    ticker_events: list[ContextEventRecord] = []
    warnings: list[str] = []
    split_event_counts: dict[str, int] = {name: 0 for name in splits}
    complete_outcomes: dict[int, int] = {h: 0 for h in config.horizons}

    validated_rows = len(ticker_df)
    data_start = ticker_df.index[0].to_pydatetime() if not ticker_df.empty else None
    data_end = ticker_df.index[-1].to_pydatetime() if not ticker_df.empty else None

    if validated_rows < config.warmup_bars:
        warnings.append(
            f"Only {validated_rows} rows available; warmup_bars is {config.warmup_bars}"
        )

    for i in range(config.warmup_bars, len(ticker_df)):
        signal_time = ticker_df.index[i].to_pydatetime()
        split_name = _split_for(signal_time, splits)
        if split_name is None:
            continue

        score_df = ticker_df.iloc[: i + 1].copy()
        context = context_for_signal(
            as_of=signal_time,
            ticker_df=ticker_df,
            spec=spec,
            ticker=ticker,
            market_df=market_df,
            sector_df=sector_df,
        )

        score_result = short_term_score(
            score_df,
            weights=ShortWeights(),
            context=context,
            context_policy=ShortContextPolicy.OFF,
        )
        base_score = int(score_result["score"])
        baseline_qualifies = base_score >= spec.baseline_score_threshold

        market_rs_eligible, market_rs_status, _ = is_context_eligible(
            context, ShortContextPolicy.MARKET_RS
        )
        market_sector_rs_eligible, market_sector_rs_status, _ = is_context_eligible(
            context, ShortContextPolicy.MARKET_SECTOR_RS
        )

        entry_time: datetime | None = None
        raw_entry_price: float | None = None
        if i + 1 < len(ticker_df):
            candidate_entry_time = ticker_df.index[i + 1].to_pydatetime()
            if _within_split(candidate_entry_time, splits[split_name]):
                entry_time = candidate_entry_time
                raw_entry_price = float(ticker_df["open"].iloc[i + 1])

        outcomes: dict[int, EventOutcome] = {}
        for horizon in config.horizons:
            if entry_time is None or raw_entry_price is None:
                outcome = _incomplete_outcome(horizon, config)
            else:
                exit_idx = i + horizon
                if exit_idx >= len(ticker_df):
                    outcome = _incomplete_outcome(horizon, config)
                else:
                    exit_time = ticker_df.index[exit_idx].to_pydatetime()
                    if not _within_split(exit_time, splits[split_name]):
                        outcome = _incomplete_outcome(horizon, config)
                    else:
                        raw_exit_price = float(ticker_df["close"].iloc[exit_idx])
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

        event = ContextEventRecord(
            ticker=ticker,
            split=split_name,
            signal_time=signal_time,
            base_score=base_score,
            baseline_qualifies=baseline_qualifies,
            market_proxy=market_proxy,
            sector_proxy=sector_proxy,
            market_regime_bullish=context.market_regime_bullish,
            sector_regime_bullish=context.sector_regime_bullish,
            market_relative_strength_positive=context.market_relative_strength_positive,
            sector_relative_strength_positive=context.sector_relative_strength_positive,
            market_rs_eligible=market_rs_eligible,
            market_sector_rs_eligible=market_sector_rs_eligible,
            context_status=market_rs_status,
            market_rs_status=market_rs_status,
            market_sector_rs_status=market_sector_rs_status,
            entry_time=entry_time,
            raw_entry_price=raw_entry_price,
            outcomes=outcomes,
            market_context_time=context.market_context_time,
            sector_context_time=context.sector_context_time,
            market_rs_ratio=context.market_rs_ratio,
            market_rs_ema20=context.market_rs_ema20,
            market_rs_change_20_pct=context.market_rs_change_20_pct,
            sector_rs_ratio=context.sector_rs_ratio,
            sector_rs_ema20=context.sector_rs_ema20,
            sector_rs_change_20_pct=context.sector_rs_change_20_pct,
        )
        ticker_events.append(event)
        split_event_counts[split_name] += 1

    if not ticker_events:
        warnings.append("No events generated for this ticker")

    quality = DataQualityRow(
        ticker=ticker,
        data_source="manifest",
        sha256="",
        manifest_rows=validated_rows,
        validated_rows=validated_rows,
        data_start=data_start,
        data_end=data_end,
        duplicate_timestamps=0,
        missing_required_values=0,
        invalid_ohlc_rows=0,
        split_event_counts=split_event_counts,
        complete_1_bar_outcomes=complete_outcomes.get(1, 0),
        complete_3_bar_outcomes=complete_outcomes.get(3, 0),
        complete_5_bar_outcomes=complete_outcomes.get(5, 0),
        warnings=warnings,
    )
    return ticker_events, quality


def build_event_dataframe(events: list[ContextEventRecord], spec: ShortContextSpec) -> pd.DataFrame:
    """Convert ``ContextEventRecord`` objects to a flat DataFrame."""
    if not events:
        return pd.DataFrame(columns=_event_columns(spec))

    rows = [e.to_dict() for e in events]
    df = pd.DataFrame(rows)
    columns = _event_columns(spec)
    for col in columns:
        if col not in df.columns:
            df[col] = None
    return df[columns]


def _event_columns(spec: ShortContextSpec) -> list[str]:
    cols = [
        "ticker",
        "split",
        "signal_time",
        "base_score",
        "baseline_qualifies",
        "market_proxy",
        "sector_proxy",
        "market_regime_bullish",
        "sector_regime_bullish",
        "market_relative_strength_positive",
        "sector_relative_strength_positive",
        "context_status",
        "market_rs_status",
        "market_sector_rs_status",
        "market_rs_eligible",
        "market_sector_rs_eligible",
        "entry_time",
        "raw_entry_price",
        "market_context_time",
        "sector_context_time",
        "market_rs_ratio",
        "market_rs_ema20",
        "market_rs_change_20_pct",
        "sector_rs_ratio",
        "sector_rs_ema20",
        "sector_rs_change_20_pct",
    ]
    for horizon in spec.horizons:
        cols.append(f"{horizon}_bar_exit_time")
        cols.append(f"{horizon}_bar_raw_exit_price")
        cols.append(f"{horizon}_bar_gross_return_pct")
        for slippage in spec.slippage_scenarios_bps:
            cols.append(f"{horizon}_bar_net_return_pct_{_slippage_key(slippage)}bps")
        cols.append(f"{horizon}_bar_outcome_status")
    return cols


def _slippage_key(slippage_bps: float) -> str:
    s = float(slippage_bps)
    if s.is_integer():
        return f"{int(s)}"
    return repr(s)
