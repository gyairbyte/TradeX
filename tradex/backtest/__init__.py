"""TradeX deterministic, point-in-time backtesting harness."""
from __future__ import annotations

from tradex.backtest.cli import main
from tradex.backtest.engine import run_backtest, run_short_term_backtest
from tradex.backtest.io import load_csv
from tradex.backtest.models import (
    BacktestConfig,
    BacktestDataError,
    BacktestError,
    BacktestResult,
    Metrics,
    SignalRecord,
    TradeRecord,
)
from tradex.backtest.validation import canonicalize_bars

__all__ = [
    "BacktestConfig",
    "BacktestDataError",
    "BacktestError",
    "BacktestResult",
    "Metrics",
    "SignalRecord",
    "TradeRecord",
    "canonicalize_bars",
    "load_csv",
    "main",
    "run_backtest",
    "run_short_term_backtest",
]
