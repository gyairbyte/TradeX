"""Performance metrics for a backtest result."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from tradex.backtest.models import BacktestConfig, Metrics, TradeRecord


def compute_metrics(
    equity_curve: pd.DataFrame,
    trades: list[TradeRecord],
    config: BacktestConfig,
    buy_and_hold_return_pct: float,
    *,
    total_signals: int,
    qualifying_signals: int,
    signals_skipped_overlap: int,
    signals_skipped_no_next_bar: int,
) -> Metrics:
    """Compute a stable metrics object from the equity curve and trade ledger."""
    return _compute_metrics(
        equity_curve=equity_curve,
        trades=trades,
        config=config,
        buy_and_hold_return_pct=buy_and_hold_return_pct,
        total_signals=total_signals,
        qualifying_signals=qualifying_signals,
        skipped_overlap=signals_skipped_overlap,
        skipped_no_next_bar=signals_skipped_no_next_bar,
    )


def _compute_metrics(
    equity_curve: pd.DataFrame,
    trades: list[TradeRecord],
    config: BacktestConfig,
    buy_and_hold_return_pct: float,
    total_signals: int,
    qualifying_signals: int,
    skipped_overlap: int,
    skipped_no_next_bar: int,
) -> Metrics:
    """Compute metrics with signal counts supplied by the engine."""
    initial_capital = float(config.initial_capital)
    ending_capital = float(equity_curve["equity"].iloc[-1])

    total_return_pct = (ending_capital / initial_capital - 1) * 100
    excess_return_pct = total_return_pct - buy_and_hold_return_pct

    total_trades = len(trades)
    net_returns = np.array([t.net_return_pct for t in trades])

    winning = net_returns[net_returns > 1e-9]
    losing = net_returns[net_returns < -1e-9]
    breakeven_count = total_trades - len(winning) - len(losing)

    winning_trades = len(winning)
    losing_trades = len(losing)
    breakeven_trades = breakeven_count

    if total_trades > 0:
        win_rate_pct = float((winning_trades / total_trades) * 100)
        average_trade_return_pct = float(np.mean(net_returns))
        median_trade_return_pct = float(np.median(net_returns))
        expectancy_pct = average_trade_return_pct
    else:
        win_rate_pct = None
        average_trade_return_pct = None
        median_trade_return_pct = None
        expectancy_pct = None

    average_win_pct = float(np.mean(winning)) if len(winning) else None
    average_loss_pct = float(np.mean(losing)) if len(losing) else None

    profit_factor = _profit_factor(trades)
    sharpe_ratio = _sharpe_ratio(equity_curve)
    max_drawdown_pct = float(equity_curve["drawdown_pct"].min())

    if len(equity_curve) > 0:
        exposure_pct = float((equity_curve["position_open"].sum() / len(equity_curve)) * 100)
    else:
        exposure_pct = 0.0

    return Metrics(
        initial_capital=initial_capital,
        ending_capital=ending_capital,
        total_return_pct=total_return_pct,
        buy_and_hold_return_pct=buy_and_hold_return_pct,
        excess_return_pct=excess_return_pct,
        total_signals=total_signals,
        qualifying_signals=qualifying_signals,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        breakeven_trades=breakeven_trades,
        win_rate_pct=win_rate_pct,
        average_trade_return_pct=average_trade_return_pct,
        median_trade_return_pct=median_trade_return_pct,
        average_win_pct=average_win_pct,
        average_loss_pct=average_loss_pct,
        expectancy_pct=expectancy_pct,
        profit_factor=profit_factor,
        sharpe_ratio=sharpe_ratio,
        max_drawdown_pct=max_drawdown_pct,
        exposure_pct=exposure_pct,
        signals_skipped_overlap=skipped_overlap,
        signals_skipped_no_next_bar=skipped_no_next_bar,
    )


def _profit_factor(trades: list[TradeRecord]) -> float | None:
    """Return profit factor as positive P&L / abs(negative P&L)."""
    if not trades:
        return None

    pnls = np.array([t.ending_cash - t.starting_cash for t in trades])
    positive = pnls[pnls > 0].sum()
    negative = pnls[pnls < 0].sum()

    if negative == 0:
        if positive > 0:
            return None
        return None
    if positive == 0:
        return 0.0

    pf = positive / abs(negative)
    return float(pf) if math.isfinite(pf) else None


def _sharpe_ratio(equity_curve: pd.DataFrame) -> float | None:
    """Annualized Sharpe ratio from bar-level equity-curve returns."""
    returns = equity_curve["daily_return"].dropna().to_numpy(dtype=float)
    if len(returns) < 2:
        return None

    mean = np.mean(returns)
    std = np.std(returns, ddof=1)
    if std == 0 or not math.isfinite(mean) or not math.isfinite(std):
        return None

    sharpe = math.sqrt(252) * (mean / std)
    if not math.isfinite(sharpe):
        return None
    return float(sharpe)
