"""Immutable, typed public models for the TradeX backtest harness."""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime
from typing import Any, Literal

import numpy as np
import pandas as pd


class BacktestError(ValueError):
    """Base exception for deterministic, point-in-time backtesting errors."""


class BacktestDataError(BacktestError):
    """Raised when OHLCV input violates canonical invariants."""


@dataclass(frozen=True)
class BacktestConfig:
    """Immutable configuration for one backtest run.

    Default values are demonstration defaults only and are not investment
    recommendations. Callers should choose values appropriate to their own
    research questions.
    """

    min_score: int = 40
    warmup_bars: int = 60
    max_holding_bars: int = 3
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    commission_bps: float = 0.0
    slippage_bps: float = 0.0
    initial_capital: float = 100_000.0
    intrabar_policy: Literal["stop_first", "target_first"] = "stop_first"

    def __post_init__(self) -> None:
        _reject_bool("min_score", self.min_score)
        if not (0 <= self.min_score <= 100):
            raise BacktestError(f"min_score must be between 0 and 100; got {self.min_score}")

        _reject_bool("warmup_bars", self.warmup_bars)
        if self.warmup_bars < 50:
            raise BacktestError(f"warmup_bars must be at least 50; got {self.warmup_bars}")

        _reject_bool("max_holding_bars", self.max_holding_bars)
        if self.max_holding_bars < 1:
            raise BacktestError(f"max_holding_bars must be at least 1; got {self.max_holding_bars}")

        _reject_float_bool("stop_loss_pct", self.stop_loss_pct)
        if not (0 < self.stop_loss_pct < 1):
            raise BacktestError(
                f"stop_loss_pct must be between 0 and 1 (exclusive); got {self.stop_loss_pct}"
            )

        _reject_float_bool("take_profit_pct", self.take_profit_pct)
        if not (0 < self.take_profit_pct < 1):
            raise BacktestError(
                f"take_profit_pct must be between 0 and 1 (exclusive); got {self.take_profit_pct}"
            )

        _reject_float_bool("commission_bps", self.commission_bps)
        if self.commission_bps < 0:
            raise BacktestError(f"commission_bps must be non-negative; got {self.commission_bps}")

        _reject_float_bool("slippage_bps", self.slippage_bps)
        if self.slippage_bps < 0:
            raise BacktestError(f"slippage_bps must be non-negative; got {self.slippage_bps}")

        _reject_float_bool("initial_capital", self.initial_capital)
        if self.initial_capital <= 0:
            raise BacktestError(f"initial_capital must be positive; got {self.initial_capital}")

        if self.intrabar_policy not in ("stop_first", "target_first"):
            raise BacktestError(
                f"intrabar_policy must be 'stop_first' or 'target_first'; got {self.intrabar_policy!r}"
            )


@dataclass(frozen=True)
class SignalRecord:
    """One point-in-time signal evaluation."""

    ticker: str
    signal_time: datetime
    score: float
    reasons: list[str]
    signal_close: float
    execution_status: Literal["executed", "skipped"]
    entry_time: datetime | None
    skip_reason: Literal["below_threshold", "overlap", "no_next_bar"] | None = None


@dataclass(frozen=True)
class TradeRecord:
    """One executed long trade."""

    ticker: str
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    score: float
    reasons: list[str]
    raw_entry_price: float
    entry_fill_price: float
    raw_exit_price: float
    exit_fill_price: float
    stop_price: float
    target_price: float
    exit_reason: Literal["gap_stop", "stop", "gap_target", "target", "time_exit"]
    bars_held: int
    gross_return_pct: float
    net_return_pct: float
    commission_bps: float
    slippage_bps: float
    quantity: float
    starting_cash: float
    ending_cash: float


@dataclass(frozen=True)
class Metrics:
    """Performance summary for a backtest run."""

    initial_capital: float
    ending_capital: float
    total_return_pct: float
    buy_and_hold_return_pct: float
    excess_return_pct: float
    total_signals: int
    qualifying_signals: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate_pct: float | None
    average_trade_return_pct: float | None
    median_trade_return_pct: float | None
    average_win_pct: float | None
    average_loss_pct: float | None
    expectancy_pct: float | None
    profit_factor: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float
    exposure_pct: float
    signals_skipped_overlap: int = 0
    signals_skipped_no_next_bar: int = 0


@dataclass(frozen=True)
class BacktestResult:
    """Complete deterministic result for one backtest run."""

    ticker: str
    timeframe: str
    strategy_name: str
    data_source: str
    data_start: datetime
    data_end: datetime
    evaluation_start: datetime
    evaluation_end: datetime
    config: dict[str, Any]
    weight_snapshot: dict[str, Any] | None
    signal_ledger: list[SignalRecord]
    trade_ledger: list[TradeRecord]
    equity_curve: pd.DataFrame
    metrics: Metrics
    warnings: list[str] = None
    limitations: list[str] = None
    metadata: Mapping[str, Any] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "warnings",
            list(self.warnings) if self.warnings is not None else [],
        )
        object.__setattr__(
            self,
            "limitations",
            list(self.limitations) if self.limitations is not None else [],
        )

    def to_signals_df(self) -> pd.DataFrame:
        """Return the signal ledger as a DataFrame."""
        rows = [_signal_to_dict(s) for s in self.signal_ledger]
        return pd.DataFrame(rows)

    def to_trades_df(self) -> pd.DataFrame:
        """Return the trade ledger as a DataFrame."""
        rows = [_trade_to_dict(t) for t in self.trade_ledger]
        return pd.DataFrame(rows)

    def to_equity_df(self) -> pd.DataFrame:
        """Return a defensive copy of the equity curve."""
        return self.equity_curve.copy()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result to a JSON-safe dictionary.

        NaN and infinity values are converted to ``None`` so the dictionary is
        safe for JSON serialization.
        """
        return {
            "ticker": self.ticker,
            "timeframe": self.timeframe,
            "strategy_name": self.strategy_name,
            "data_source": self.data_source,
            "data_start": _iso(self.data_start),
            "data_end": _iso(self.data_end),
            "evaluation_start": _iso(self.evaluation_start),
            "evaluation_end": _iso(self.evaluation_end),
            "config": _clean(self.config),
            "weight_snapshot": _clean(self.weight_snapshot),
            "signal_ledger": [_clean(_signal_to_dict(s)) for s in self.signal_ledger],
            "trade_ledger": [_clean(_trade_to_dict(t)) for t in self.trade_ledger],
            "equity_curve": _df_records(self.equity_curve),
            "metrics": _clean(_metrics_to_dict(self.metrics)),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "metadata": _clean(dict(self.metadata)) if self.metadata else None,
        }

    def to_json(self, indent: int | None = None) -> str:
        """Serialize the result to a JSON string with no NaN or infinity."""
        return json.dumps(self.to_dict(), indent=indent, default=_json_default)


def _reject_bool(name: str, value: Any) -> None:
    if isinstance(value, bool):
        raise BacktestError(f"{name} must be an integer, not a boolean; got {value}")


def _reject_float_bool(name: str, value: Any) -> None:
    if isinstance(value, bool):
        raise BacktestError(f"{name} must be a number, not a boolean; got {value}")


def _signal_to_dict(s: SignalRecord) -> dict[str, Any]:
    return {
        "ticker": s.ticker,
        "signal_time": _iso(s.signal_time),
        "score": s.score,
        "reasons": list(s.reasons),
        "signal_close": s.signal_close,
        "execution_status": s.execution_status,
        "entry_time": _iso(s.entry_time) if s.entry_time else None,
        "skip_reason": s.skip_reason,
    }


def _trade_to_dict(t: TradeRecord) -> dict[str, Any]:
    return {
        "ticker": t.ticker,
        "signal_time": _iso(t.signal_time),
        "entry_time": _iso(t.entry_time),
        "exit_time": _iso(t.exit_time),
        "score": t.score,
        "reasons": list(t.reasons),
        "raw_entry_price": t.raw_entry_price,
        "entry_fill_price": t.entry_fill_price,
        "raw_exit_price": t.raw_exit_price,
        "exit_fill_price": t.exit_fill_price,
        "stop_price": t.stop_price,
        "target_price": t.target_price,
        "exit_reason": t.exit_reason,
        "bars_held": t.bars_held,
        "gross_return_pct": t.gross_return_pct,
        "net_return_pct": t.net_return_pct,
        "commission_bps": t.commission_bps,
        "slippage_bps": t.slippage_bps,
        "quantity": t.quantity,
        "starting_cash": t.starting_cash,
        "ending_cash": t.ending_cash,
    }


def _metrics_to_dict(m: Metrics) -> dict[str, Any]:
    return {field.name: getattr(m, field.name) for field in fields(m)}


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _clean(value: Any) -> Any:
    """Recursively convert numpy/pandas scalars and replace NaN/inf with None."""
    if isinstance(value, (np.floating, float)):
        f = float(value)
        if math.isfinite(f):
            return f
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, pd.DataFrame):
        return _df_records(value)
    return value


def _df_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to JSON-safe record dictionaries, preserving the index as ``timestamp``."""
    records = df.reset_index().rename(columns={"datetime": "timestamp"}).to_dict("records")
    return [_clean(r) for r in records]


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return _clean(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
