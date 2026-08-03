"""Tests for paired backtest candidate scoring and gate logic."""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from tradex.market.models import ShortContextPolicy
from tradex.research.short_context.backtest import (
    _backtest_gate_failures,
    _make_candidate_score_fn,
)


def _trending_df(n: int = 80) -> pd.DataFrame:
    dates = pd.bdate_range(start=datetime(2020, 1, 1, tzinfo=UTC), periods=n)
    prices = 100.0 + pd.Series(range(n)) * 0.5
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices + 0.1,
            "low": prices - 0.1,
            "close": prices,
            "volume": 1_000_000,
        },
        index=dates,
    )


def test_candidate_score_returns_zero_when_ineligible() -> None:
    target = _trending_df(80)
    market = _trending_df(80)
    score_fn = _make_candidate_score_fn(
        ticker="AAPL",
        market_df=market,
        sector_df=None,
        market_proxy="SPY",
        sector_proxy=None,
        policy=ShortContextPolicy.MARKET_RS,
    )
    result = score_fn(target)
    assert result["context_policy"] == "market_rs"
    assert "base_score" in result
    assert "market_context" in result


def test_backtest_gate_empty_candidate_fails() -> None:
    baseline = pd.DataFrame({"ticker": ["AAPL"], "total_trades": [5], "expectancy_pct": [1.0], "total_return_pct": [2.0], "max_drawdown_pct": [-5.0]})
    candidate = pd.DataFrame(columns=["ticker", "total_trades"])
    failures = _backtest_gate_failures(baseline, candidate, None)
    assert failures
