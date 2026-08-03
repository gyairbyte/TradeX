"""Tests for candidate selection and holdout promotion gates."""
from __future__ import annotations

import pandas as pd

from tradex.market.models import ShortContextPolicy
from tradex.research.score_validation.models import ScoreValidationConfig
from tradex.research.short_context.comparison import (
    build_candidate_comparison_df,
    evaluate_holdout,
    select_candidate,
)
from tradex.research.short_context.models import ShortContextSpec


def _unit_spec() -> ShortContextSpec:
    return ShortContextSpec(
        study_name="unit",
        target_tickers=("AAPL", "MSFT"),
        ticker_context={
            "AAPL": {"market_proxy": "SPY", "sector_proxy": "XLK"},
            "MSFT": {"market_proxy": "SPY", "sector_proxy": "XLK"},
        },
        candidate_policies=(ShortContextPolicy.MARKET_RS, ShortContextPolicy.MARKET_SECTOR_RS),
        default_market_proxy="SPY",
        primary_horizon_bars=3,
        primary_slippage_bps=5.0,
        horizons=(1, 3, 5),
        slippage_scenarios_bps=(0.0, 5.0, 10.0),
        commission_bps=0.0,
        minimum_holdout_events=1,
        minimum_holdout_tickers=1,
        minimum_event_retention_pct=0.0,
        minimum_ticker_coverage_pct=0.0,
        baseline_score_threshold=40,
    )


def _events_df() -> pd.DataFrame:
    """A small hand-built event DataFrame with two tickers and three splits."""
    rows = []
    for split in ["development", "validation", "holdout"]:
        for ticker in ["AAPL", "MSFT"]:
            for _ in range(10):
                rows.append({
                    "ticker": ticker,
                    "split": split,
                    "base_score": 70,
                    "baseline_qualifies": True,
                    "market_rs_eligible": True,
                    "market_sector_rs_eligible": True,
                    "3_bar_net_return_pct_5bps": 1.0,
                })
                rows.append({
                    "ticker": ticker,
                    "split": split,
                    "base_score": 70,
                    "baseline_qualifies": True,
                    "market_rs_eligible": False,
                    "market_sector_rs_eligible": True,
                    "3_bar_net_return_pct_5bps": -1.0,
                })
    return pd.DataFrame(rows)


def test_select_candidate_prefers_market_rs() -> None:
    spec = _unit_spec()
    config = ScoreValidationConfig()
    result = select_candidate(_events_df(), spec, config)
    assert result.selected_policy == "market_rs"


def test_evaluate_holdout_passes_with_perfect_candidate() -> None:
    spec = _unit_spec()
    config = ScoreValidationConfig()
    holdout = evaluate_holdout(_events_df(), "market_rs", spec, config)
    assert holdout.passed is True


def test_build_candidate_comparison_has_expected_columns() -> None:
    spec = _unit_spec()
    config = ScoreValidationConfig()
    df = build_candidate_comparison_df(_events_df(), spec, config)
    assert not df.empty
    assert "policy" in df.columns
    assert "mean_net_return_pct" in df.columns
