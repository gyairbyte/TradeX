"""Shared fixtures and helpers for backtest tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradex.backtest.models import BacktestConfig


def make_bars(
    n: int,
    *,
    start: str = "2020-01-01",
    close: np.ndarray | None = None,
    open_offset: float = 0.0,
    high_offset: float = 1.0,
    low_offset: float = -1.0,
    volume: float = 1e6,
    tz: str = "UTC",
) -> pd.DataFrame:
    """Build a deterministic OHLCV DataFrame from a close array."""
    if close is None:
        close = np.linspace(100, 100 + n * 0.5, n)
    opens = close + open_offset
    highs = close + high_offset
    lows = close + low_offset
    idx = pd.date_range(start, periods=n, freq="D", tz=tz)
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": close,
            "volume": np.ones(n) * volume,
        },
        index=idx,
    )


@pytest.fixture
def empty_score_fn():
    """A scorer that never qualifies."""

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 0, "reasons": [], "last_close": float(df["close"].iloc[-1])}

    return _fn


@pytest.fixture
def perfect_score_fn():
    """A scorer that always qualifies."""

    def _fn(df: pd.DataFrame) -> dict[str, object]:
        return {"score": 100, "reasons": ["perfect"], "last_close": float(df["close"].iloc[-1])}

    return _fn


@pytest.fixture
def default_config():
    return BacktestConfig()


@pytest.fixture
def short_term_qualifying_bars() -> pd.DataFrame:
    """Deterministic daily bars that make the production short-term scorer fire."""
    n = 120
    t = np.arange(n)
    close = 100 + 0.2 * t + 0.5 * np.sin(t / 3)
    close[-10:] += np.linspace(0, 1.5, 10)
    vol = np.ones(n) * 1e6
    vol[-5:] = 3e6
    return pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": vol,
        },
        index=pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC"),
    )
