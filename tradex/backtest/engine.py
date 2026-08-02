"""Point-in-time backtest engine."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Literal

import pandas as pd

from tradex.backtest.metrics import compute_metrics
from tradex.backtest.models import (
    BacktestConfig,
    BacktestDataError,
    BacktestResult,
    SignalRecord,
    TradeRecord,
)
from tradex.backtest.validation import canonicalize_bars, validate_score_output
from tradex.signals.short_term import score as short_term_score
from tradex.signals.weights import ShortWeights

ScoreFn = Callable[[pd.DataFrame], Mapping[str, Any]]

# Default research limitations. These are not exhaustive; they document the
# known boundaries of a CSV-driven, point-in-time backtest.
_LIMITATIONS = [
    "This harness does not eliminate survivorship bias, delisting bias, or point-in-time index membership.",
    "Corporate actions, provider adjustments, retroactive splits, and liquidity capacity are not modeled.",
    "Execution uses daily bars; real intraday order placement, slippage timing, and partial fills are not simulated.",
    "Reported metrics are research evidence, not proof of a durable edge or statistical significance.",
]


def run_backtest(
    ticker: str,
    bars: pd.DataFrame,
    score_fn: ScoreFn,
    config: BacktestConfig,
    *,
    strategy_name: str,
    data_source: str = "unknown",
    weight_snapshot: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> BacktestResult:
    """Run a deterministic, point-in-time backtest on caller-supplied OHLCV data.

    The engine evaluates ``score_fn`` using only the historical slice available at
    each signal bar, enters on the next open, and applies explicit stop/target/time
    exits. It never passes future rows to the scorer.
    """
    if config is None:
        config = BacktestConfig()

    bars = canonicalize_bars(bars)
    n = len(bars)
    if n < config.warmup_bars:
        raise BacktestDataError(
            f"Not enough bars for warmup. Need at least {config.warmup_bars}, got {n}"
        )

    evaluation_start = bars.index[config.warmup_bars - 1]
    evaluation_end = bars.index[-1]

    signals: list[SignalRecord] = []
    trades: list[TradeRecord] = []

    active_trade: dict[str, Any] | None = None
    cash = float(config.initial_capital)
    last_exit_idx = -1

    for i in range(config.warmup_bars - 1, n):
        ts = bars.index[i]

        # Realize any trade that exits on or before this bar.
        if active_trade is not None and active_trade["exit_idx"] <= i:
            cash = active_trade["exit_cash"]
            last_exit_idx = active_trade["exit_idx"]
            active_trade = None

        score_output = validate_score_output(score_fn(bars.iloc[: i + 1]))
        score_val = float(score_output["score"])
        reasons = list(score_output.get("reasons", []))
        signal_close = float(score_output.get("last_close", bars.iloc[i]["close"]))

        if score_val < config.min_score:
            signals.append(
                SignalRecord(
                    ticker=ticker,
                    signal_time=ts,
                    score=score_val,
                    reasons=reasons,
                    signal_close=signal_close,
                    execution_status="skipped",
                    entry_time=None,
                    skip_reason="below_threshold",
                )
            )
            continue

        entry_idx = i + 1

        if active_trade is not None:
            signals.append(
                SignalRecord(
                    ticker=ticker,
                    signal_time=ts,
                    score=score_val,
                    reasons=reasons,
                    signal_close=signal_close,
                    execution_status="skipped",
                    entry_time=None,
                    skip_reason="overlap",
                )
            )
            continue

        if entry_idx <= last_exit_idx:
            signals.append(
                SignalRecord(
                    ticker=ticker,
                    signal_time=ts,
                    score=score_val,
                    reasons=reasons,
                    signal_close=signal_close,
                    execution_status="skipped",
                    entry_time=None,
                    skip_reason="overlap",
                )
            )
            continue

        if entry_idx >= n:
            signals.append(
                SignalRecord(
                    ticker=ticker,
                    signal_time=ts,
                    score=score_val,
                    reasons=reasons,
                    signal_close=signal_close,
                    execution_status="skipped",
                    entry_time=None,
                    skip_reason="no_next_bar",
                )
            )
            continue

        trade = _execute_trade(
            ticker=ticker,
            bars=bars,
            signal_time=ts,
            entry_idx=entry_idx,
            score=score_val,
            reasons=reasons,
            config=config,
            starting_cash=cash,
        )

        trades.append(trade)
        signals.append(
            SignalRecord(
                ticker=ticker,
                signal_time=ts,
                score=score_val,
                reasons=reasons,
                signal_close=signal_close,
                execution_status="executed",
                entry_time=bars.index[entry_idx],
                skip_reason=None,
            )
        )

        cash = 0.0
        active_trade = {
            "entry_idx": entry_idx,
            "exit_idx": bars.index.get_loc(trade.exit_time),
            "quantity": trade.quantity,
            "exit_cash": trade.ending_cash,
        }
        last_exit_idx = active_trade["exit_idx"]

    # Any trade that exits on the final bar is already realized in the loop.
    # Ensure final cash is correct.
    if active_trade is not None:
        cash = active_trade["exit_cash"]

    equity_curve = _build_equity_curve(
        bars=bars,
        trades=trades,
        config=config,
        first_idx=config.warmup_bars - 1,
    )

    buy_and_hold = _buy_and_hold_return(bars, config)
    total_signals = len(signals)
    qualifying_signals = sum(1 for s in signals if s.score >= config.min_score)
    skipped_overlap = sum(1 for s in signals if s.skip_reason == "overlap")
    skipped_no_next_bar = sum(1 for s in signals if s.skip_reason == "no_next_bar")
    metrics = compute_metrics(
        equity_curve=equity_curve,
        trades=trades,
        config=config,
        buy_and_hold_return_pct=buy_and_hold,
        total_signals=total_signals,
        qualifying_signals=qualifying_signals,
        signals_skipped_overlap=skipped_overlap,
        signals_skipped_no_next_bar=skipped_no_next_bar,
    )

    return BacktestResult(
        ticker=ticker,
        timeframe="daily",
        strategy_name=strategy_name,
        data_source=data_source,
        data_start=bars.index[0],
        data_end=bars.index[-1],
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        config=config.__dict__,
        weight_snapshot=dict(weight_snapshot) if weight_snapshot else None,
        signal_ledger=signals,
        trade_ledger=trades,
        equity_curve=equity_curve,
        metrics=metrics,
        limitations=list(_LIMITATIONS),
        metadata=metadata or {},
    )


def run_short_term_backtest(
    ticker: str,
    bars: pd.DataFrame,
    config: BacktestConfig | None = None,
    *,
    weights: ShortWeights | None = None,
    data_source: str = "unknown",
) -> BacktestResult:
    """Run a point-in-time backtest using the production short-term scorer.

    Defaults to an explicit, fresh ``ShortWeights()`` instance so the result is
    independent of any user-specific saved weight file.
    """
    if config is None:
        config = BacktestConfig()
    if weights is None:
        weights = ShortWeights()

    def _score_fn(df: pd.DataFrame) -> dict[str, Any]:
        return short_term_score(df, weights=weights)

    return run_backtest(
        ticker=ticker,
        bars=bars,
        score_fn=_score_fn,
        config=config,
        strategy_name="short_term",
        data_source=data_source,
        weight_snapshot=_short_weights_snapshot(weights),
    )


def _execute_trade(
    ticker: str,
    bars: pd.DataFrame,
    signal_time: datetime,
    entry_idx: int,
    score: float,
    reasons: list[str],
    config: BacktestConfig,
    starting_cash: float,
) -> TradeRecord:
    """Enter at ``entry_idx`` open and simulate the configured exit."""
    raw_entry = float(bars.iloc[entry_idx]["open"])
    entry_fill = raw_entry * (1 + config.slippage_bps / 10_000)

    cash_per_share = entry_fill * (1 + config.commission_bps / 10_000)
    quantity = starting_cash / cash_per_share

    # Risk levels are anchored to the actual entry fill, not the signal bar close,
    # so opening gaps and entry slippage are reflected in the trade's risk.
    stop_price = entry_fill * (1 - config.stop_loss_pct)
    target_price = entry_fill * (1 + config.take_profit_pct)

    exit_idx, raw_exit, exit_reason = _simulate_exit(
        bars=bars,
        entry_idx=entry_idx,
        stop_price=stop_price,
        target_price=target_price,
        max_holding_bars=config.max_holding_bars,
        intrabar_policy=config.intrabar_policy,
    )

    exit_fill = raw_exit * (1 - config.slippage_bps / 10_000)
    ending_cash = quantity * exit_fill * (1 - config.commission_bps / 10_000)

    gross_return_pct = (raw_exit / raw_entry - 1) * 100
    net_return_pct = (ending_cash / starting_cash - 1) * 100

    return TradeRecord(
        ticker=ticker,
        signal_time=signal_time,
        entry_time=bars.index[entry_idx],
        exit_time=bars.index[exit_idx],
        score=score,
        reasons=reasons,
        raw_entry_price=raw_entry,
        entry_fill_price=entry_fill,
        raw_exit_price=raw_exit,
        exit_fill_price=exit_fill,
        stop_price=stop_price,
        target_price=target_price,
        exit_reason=exit_reason,
        bars_held=exit_idx - entry_idx + 1,
        gross_return_pct=gross_return_pct,
        net_return_pct=net_return_pct,
        commission_bps=config.commission_bps,
        slippage_bps=config.slippage_bps,
        quantity=quantity,
        starting_cash=starting_cash,
        ending_cash=ending_cash,
    )


def _simulate_exit(
    bars: pd.DataFrame,
    entry_idx: int,
    stop_price: float,
    target_price: float,
    max_holding_bars: int,
    intrabar_policy: Literal["stop_first", "target_first"],
) -> tuple[int, float, Literal["gap_stop", "stop", "gap_target", "target", "time_exit"]]:
    """Determine the first exit bar, raw exit price, and reason for one trade."""
    last_possible = min(entry_idx + max_holding_bars - 1, len(bars) - 1)

    for j in range(entry_idx, last_possible + 1):
        row = bars.iloc[j]
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])

        if o <= stop_price:
            return j, o, "gap_stop"
        if o >= target_price:
            return j, o, "gap_target"

        stop_touched = l <= stop_price
        target_touched = h >= target_price

        if stop_touched and target_touched:
            if intrabar_policy == "stop_first":
                return j, stop_price, "stop"
            return j, target_price, "target"
        if stop_touched:
            return j, stop_price, "stop"
        if target_touched:
            return j, target_price, "target"

        if j == last_possible:
            return j, c, "time_exit"

    # Should be unreachable because last_possible is always reached.
    return last_possible, float(bars.iloc[last_possible]["close"]), "time_exit"


def _build_equity_curve(
    bars: pd.DataFrame,
    trades: list[TradeRecord],
    config: BacktestConfig,
    first_idx: int,
) -> pd.DataFrame:
    """Produce a bar-level marked-to-market equity curve from ``first_idx`` onward.

    A bar is counted as exposed if a position is held at any point during it, so
    both the entry bar and the exit bar are included in exposure accounting. The
    ``position_ticker`` column records the active ticker (or None) for each bar.
    """
    entries: dict[datetime, TradeRecord] = {t.entry_time: t for t in trades}
    exits: dict[datetime, TradeRecord] = {t.exit_time: t for t in trades}

    cash = float(config.initial_capital)
    active_trade: TradeRecord | None = None
    rows: list[dict[str, Any]] = []

    for i in range(first_idx, len(bars)):
        ts = bars.index[i]

        if ts in entries:
            active_trade = entries[ts]
            cash = 0.0

        # Capture exposure state for this bar before any same-bar exit is applied.
        position_ticker = active_trade.ticker if active_trade is not None else None
        position_open = position_ticker is not None

        close = float(bars.iloc[i]["close"])

        # Realize the exit immediately, so the equity for this bar reflects the
        # realized cash (or a position still held through the close).
        if ts in exits:
            cash = exits[ts].ending_cash
            active_trade = None

        equity = active_trade.quantity * close if active_trade is not None else cash

        rows.append(
            {
                "timestamp": ts,
                "equity": equity,
                "cash": cash,
                "position_quantity": active_trade.quantity if active_trade is not None else 0.0,
                "position_open": position_open,
                "position_ticker": position_ticker,
                "close": close,
            }
        )

    df = pd.DataFrame(rows).set_index("timestamp")
    df.index.name = "datetime"
    df["daily_return"] = df["equity"].pct_change().fillna(0.0)
    df["running_peak"] = df["equity"].cummax()
    df["drawdown_pct"] = (df["equity"] / df["running_peak"] - 1) * 100
    return df


def _buy_and_hold_return(bars: pd.DataFrame, config: BacktestConfig) -> float:
    """Return the full-capital, same-cost buy-and-hold return for the evaluation window."""
    first_idx = config.warmup_bars - 1
    last_idx = len(bars) - 1

    raw_entry = float(bars.iloc[first_idx]["open"])
    raw_exit = float(bars.iloc[last_idx]["close"])

    entry_fill = raw_entry * (1 + config.slippage_bps / 10_000)
    exit_fill = raw_exit * (1 - config.slippage_bps / 10_000)

    cash_per_share = entry_fill * (1 + config.commission_bps / 10_000)
    quantity = config.initial_capital / cash_per_share
    ending_cash = quantity * exit_fill * (1 - config.commission_bps / 10_000)

    return (ending_cash / config.initial_capital - 1) * 100


def _short_weights_snapshot(weights: ShortWeights) -> dict[str, Any]:
    return {
        "ema_structure": weights.ema_structure,
        "volume_confirmation": weights.volume_confirmation,
        "rsi_momentum": weights.rsi_momentum,
        "macd_positive": weights.macd_positive,
        "pullback_ema": weights.pullback_ema,
    }
