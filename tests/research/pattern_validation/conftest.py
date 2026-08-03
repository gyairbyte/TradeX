"""Shared fixtures for pattern-validation tests."""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import pytest

from tradex.research.pattern_validation.models import BootstrapConfig, Split, StudySpec


def make_synthetic_bars(ticker: str, start: date, end: date, seed: int = 0) -> pd.DataFrame:
    """Create a deterministic daily OHLCV series with injected run-up/decline events."""
    dates = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    price = 100.0
    opens, highs, lows, closes, volumes = [], [], [], [], []
    for i, _ in enumerate(dates):
        mod = i % 60
        if mod in {0, 1, 2, 3, 4}:
            base_change = 0.04 if ticker == "AAPL" else 0.035
        elif mod in {30, 31, 32, 33, 34}:
            base_change = -0.03
        else:
            base_change = rng.normal(0, 0.005)
        open_p = price * (1 + rng.normal(0, 0.003))
        close_p = open_p * (1 + base_change + rng.normal(0, 0.005))
        if close_p <= 0:
            close_p = 0.01
        high_p = max(open_p, close_p) * (1 + abs(rng.normal(0, 0.005)))
        low_p = min(open_p, close_p) * (1 - abs(rng.normal(0, 0.005)))
        opens.append(open_p)
        highs.append(high_p)
        lows.append(low_p)
        closes.append(close_p)
        volumes.append(int(1e6 * (1 + rng.normal(0, 0.2))))
        price = close_p
    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )
    df.index = df.index.tz_localize("UTC")
    return df


def synthetic_fetcher(ticker: str, start: date, end: date, provider: str | None = None) -> pd.DataFrame:
    return make_synthetic_bars(ticker, start, end, seed=abs(hash(ticker)) % 10000)


@pytest.fixture
def tiny_study_dates() -> dict[str, Any]:
    """A short 3-year study period for fast tests."""
    return {
        "start_date": date(2020, 1, 2),
        "end_date": date(2022, 12, 30),
        "splits": {
            "development": Split(date(2020, 1, 2), date(2020, 12, 31)),
            "validation": Split(date(2021, 1, 4), date(2021, 12, 31)),
            "holdout": Split(date(2022, 1, 3), date(2022, 12, 30)),
        },
    }


@pytest.fixture
def tiny_spec(tiny_study_dates: dict[str, Any]) -> StudySpec:
    return StudySpec(
        tickers=("AAPL", "MSFT"),
        provider="synthetic",
        start_date=tiny_study_dates["start_date"],
        end_date=tiny_study_dates["end_date"],
        splits=tiny_study_dates["splits"],
        min_events=3,
        minimum_validation_signals=1,
        minimum_holdout_signals=1,
        minimum_tickers=1,
        bootstrap=BootstrapConfig(resamples=20),
    )


@pytest.fixture
def tiny_bars(tiny_study_dates: dict[str, Any]) -> dict[str, pd.DataFrame]:
    start = tiny_study_dates["start_date"]
    end = tiny_study_dates["end_date"]
    return {
        "AAPL": make_synthetic_bars("AAPL", start, end, seed=1),
        "MSFT": make_synthetic_bars("MSFT", start, end, seed=2),
    }
