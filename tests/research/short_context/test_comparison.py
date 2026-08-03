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
                    "3_bar_outcome_status": "complete",
                })
                rows.append({
                    "ticker": ticker,
                    "split": split,
                    "base_score": 70,
                    "baseline_qualifies": True,
                    "market_rs_eligible": False,
                    "market_sector_rs_eligible": True,
                    "3_bar_net_return_pct_5bps": -1.0,
                    "3_bar_outcome_status": "complete",
                })
    return pd.DataFrame(rows)


def test_select_candidate_prefers_market_rs() -> None:
    spec = _unit_spec()
    config = ScoreValidationConfig()
    result = select_candidate(_events_df(), spec, config)
    assert result.selected_policy == "market_rs"


def test_select_candidate_ignores_holdout() -> None:
    spec = _unit_spec()
    config = ScoreValidationConfig()
    df = _events_df()
    result = select_candidate(df, spec, config)

    # The serialized policy metrics must not contain holdout.
    for split_metrics in result.policy_metrics.values():
        assert "holdout" not in split_metrics
        assert "holdout_baseline" not in split_metrics


def test_select_candidate_is_unchanged_by_holdout_prices() -> None:
    """Changing holdout returns must not alter candidate-selection output."""
    spec = _unit_spec()
    config = ScoreValidationConfig()
    df = _events_df()
    result_a = select_candidate(df, spec, config)

    df2 = df.copy()
    holdout_mask = df2["split"] == "holdout"
    df2.loc[holdout_mask, "3_bar_net_return_pct_5bps"] = 99.0
    result_b = select_candidate(df2, spec, config)

    assert result_a.to_dict() == result_b.to_dict()


def test_select_candidate_enforces_validation_minimum_and_zero_metrics() -> None:
    spec = _unit_spec()
    spec = ShortContextSpec(
        study_name="unit",
        target_tickers=("AAPL",),
        ticker_context={"AAPL": {"market_proxy": "SPY", "sector_proxy": "XLK"}},
        candidate_policies=(ShortContextPolicy.MARKET_RS,),
        default_market_proxy="SPY",
        primary_horizon_bars=3,
        primary_slippage_bps=5.0,
        horizons=(1, 3, 5),
        slippage_scenarios_bps=(0.0, 5.0, 10.0),
        commission_bps=0.0,
        minimum_validation_events=5,
        minimum_holdout_events=1,
        minimum_holdout_tickers=1,
        minimum_event_retention_pct=0.0,
        minimum_ticker_coverage_pct=0.0,
        baseline_score_threshold=40,
    )
    config = ScoreValidationConfig()

    # Exactly one validation event means the candidate is disqualified.
    rows = []
    for _ in range(1):
        rows.append({
            "ticker": "AAPL", "split": "validation", "base_score": 70,
            "baseline_qualifies": True, "market_rs_eligible": True,
            "market_sector_rs_eligible": True, "3_bar_net_return_pct_5bps": 1.0,
            "3_bar_outcome_status": "complete",
        })
    for _ in range(10):
        rows.append({
            "ticker": "AAPL", "split": "development", "base_score": 70,
            "baseline_qualifies": True, "market_rs_eligible": True,
            "market_sector_rs_eligible": True, "3_bar_net_return_pct_5bps": 1.0,
            "3_bar_outcome_status": "complete",
        })
    df = pd.DataFrame(rows)
    result = select_candidate(df, spec, config)
    assert result.selected_policy is None

    # Zero-valued metrics are valid and should not be treated as missing.
    # Candidate returns 0.0 while baseline returns -1.0, so candidate > baseline.
    rows = []
    for _ in range(5):
        rows.append({
            "ticker": "AAPL", "split": "validation", "base_score": 70,
            "baseline_qualifies": True, "market_rs_eligible": True,
            "market_sector_rs_eligible": True, "3_bar_net_return_pct_5bps": 0.0,
            "3_bar_outcome_status": "complete",
        })
        rows.append({
            "ticker": "AAPL", "split": "validation", "base_score": 70,
            "baseline_qualifies": True, "market_rs_eligible": False,
            "market_sector_rs_eligible": True, "3_bar_net_return_pct_5bps": -1.0,
            "3_bar_outcome_status": "complete",
        })
    for _ in range(10):
        rows.append({
            "ticker": "AAPL", "split": "development", "base_score": 70,
            "baseline_qualifies": True, "market_rs_eligible": True,
            "market_sector_rs_eligible": True, "3_bar_net_return_pct_5bps": 0.0,
            "3_bar_outcome_status": "complete",
        })
        rows.append({
            "ticker": "AAPL", "split": "development", "base_score": 70,
            "baseline_qualifies": True, "market_rs_eligible": False,
            "market_sector_rs_eligible": True, "3_bar_net_return_pct_5bps": -1.0,
            "3_bar_outcome_status": "complete",
        })
    df = pd.DataFrame(rows)
    result = select_candidate(df, spec, config)
    assert result.selected_policy == "market_rs"
    assert result.policy_metrics["market_rs"]["validation"].mean_net_return_pct == 0.0


def test_evaluate_holdout_passes_with_perfect_candidate() -> None:
    spec = _unit_spec()
    config = ScoreValidationConfig()
    holdout = evaluate_holdout(_events_df(), "market_rs", spec, config)
    assert holdout.passed is True


def test_evaluate_holdout_fails_when_half_tickers_do_not_improve() -> None:
    """The holdout gate must include a robustness check on per-ticker means."""
    rows = []
    for split in ["development", "validation", "holdout"]:
        for ticker in ["AAPL", "MSFT", "XLK"]:
            if ticker == "AAPL":
                events = [(True, 100.0), (True, 100.0), (True, 100.0)]
            else:
                # Two candidate-eligible events, one ineligible baseline-only event
                # makes the baseline mean higher than the candidate mean.
                events = [(True, -1.0), (True, -1.0), (False, 0.0)]
            for eligible, value in events:
                rows.append({
                    "ticker": ticker,
                    "split": split,
                    "base_score": 70,
                    "baseline_qualifies": True,
                    "market_rs_eligible": eligible,
                    "market_sector_rs_eligible": True,
                    "3_bar_net_return_pct_5bps": value,
                    "3_bar_outcome_status": "complete",
                })
    spec = ShortContextSpec(
        study_name="unit",
        target_tickers=("AAPL", "MSFT", "XLK"),
        ticker_context={
            "AAPL": {"market_proxy": "SPY", "sector_proxy": "XLK"},
            "MSFT": {"market_proxy": "SPY", "sector_proxy": "XLK"},
            "XLK": {"market_proxy": "SPY", "sector_proxy": "XLY"},
        },
        candidate_policies=(ShortContextPolicy.MARKET_RS,),
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
    config = ScoreValidationConfig()
    df = pd.DataFrame(rows)
    result = evaluate_holdout(df, "market_rs", spec, config)
    assert result.passed is False
    assert any("fewer than half" in reason for reason in result.failure_reasons)


def test_incomplete_primary_outcomes_not_counted() -> None:
    """Incomplete primary-horizon rows must not satisfy sample minimums or denominators."""
    spec = _unit_spec()
    spec = ShortContextSpec(
        study_name="unit",
        target_tickers=("AAPL",),
        ticker_context={"AAPL": {"market_proxy": "SPY", "sector_proxy": "XLK"}},
        candidate_policies=(ShortContextPolicy.MARKET_RS,),
        default_market_proxy="SPY",
        primary_horizon_bars=3,
        primary_slippage_bps=5.0,
        horizons=(1, 3, 5),
        slippage_scenarios_bps=(0.0, 5.0, 10.0),
        commission_bps=0.0,
        minimum_validation_events=100,
        minimum_holdout_events=100,
        minimum_holdout_tickers=1,
        minimum_event_retention_pct=0.0,
        minimum_ticker_coverage_pct=0.0,
        baseline_score_threshold=40,
    )
    config = ScoreValidationConfig()
    rows = []
    for _ in range(99):
        rows.append({
            "ticker": "AAPL", "split": "validation", "base_score": 70,
            "baseline_qualifies": True, "market_rs_eligible": True,
            "market_sector_rs_eligible": True, "3_bar_net_return_pct_5bps": None,
            "3_bar_outcome_status": "insufficient_future_bars",
        })
    rows.append({
        "ticker": "AAPL", "split": "validation", "base_score": 70,
        "baseline_qualifies": True, "market_rs_eligible": True,
        "market_sector_rs_eligible": True, "3_bar_net_return_pct_5bps": 1.0,
        "3_bar_outcome_status": "complete",
    })
    # Baseline has many more complete events but only the validation split is checked for selection.
    for _ in range(200):
        rows.append({
            "ticker": "AAPL", "split": "development", "base_score": 70,
            "baseline_qualifies": True, "market_rs_eligible": True,
            "market_sector_rs_eligible": True, "3_bar_net_return_pct_5bps": 1.0,
            "3_bar_outcome_status": "complete",
        })
    df = pd.DataFrame(rows)
    result = select_candidate(df, spec, config)
    assert result.selected_policy is None
    val_metrics = result.policy_metrics["market_rs"]["validation"]
    assert val_metrics.event_count == 1
    assert val_metrics.baseline_event_count == 1
    assert val_metrics.retention_pct == 100.0
    assert val_metrics.coverage_pct == 100.0


def test_build_candidate_comparison_has_expected_columns() -> None:
    spec = _unit_spec()
    config = ScoreValidationConfig()
    df = build_candidate_comparison_df(_events_df(), spec, config)
    assert not df.empty
    assert "policy" in df.columns
    assert "mean_net_return_pct" in df.columns
