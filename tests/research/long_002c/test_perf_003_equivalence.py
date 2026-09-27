"""Equivalence and regression tests for LONG-002C-PERF-003 baseline optimizations.

Verifies bitwise/numerical equivalence between:
1. compute_simple_momentum_series and iterative compute_simple_momentum
2. compute_legacy_tradex_scores_series and iterative compute_legacy_tradex_score
3. evaluate_baselines_for_date with precomputed scalar features vs dynamic slicing
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradex.research.long_002c.baselines import (
    compute_legacy_tradex_score,
    compute_legacy_tradex_scores_series,
    compute_simple_momentum,
    compute_simple_momentum_series,
    evaluate_baselines_for_date,
)
from tradex.signals.weights import LongWeights


def _generate_synthetic_bars(n: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-01", periods=n, freq="B")
    log_returns = rng.normal(0.0005, 0.02, size=n)
    close = 100.0 * np.exp(np.cumsum(log_returns))
    high = close * (1.0 + np.abs(rng.normal(0, 0.01, size=n)))
    low = close * (1.0 - np.abs(rng.normal(0, 0.01, size=n)))
    open_ = (high + low) / 2.0
    volume = rng.integers(100_000, 5_000_000, size=n).astype(float)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates.strftime("%Y-%m-%d"),
    )


def test_simple_momentum_series_equivalence():
    """Verify compute_simple_momentum_series matches compute_simple_momentum for all prefixes."""
    closes = [10.0, 12.0, 11.0, 15.0, 0.0, -1.0, float("nan"), 14.0, 18.0, 20.0, 25.0, 22.0]
    n = len(closes)

    for lb in [1, 2, 3, 5, 10, 20]:
        series_res = compute_simple_momentum_series(closes, lb)
        assert len(series_res) == n

        for i in range(n):
            sub = closes[: i + 1]
            expected = compute_simple_momentum(sub, lb)
            actual = series_res[i]
            if expected is None:
                assert actual is None, f"Expected None at index {i} (lb={lb}), got {actual}"
            else:
                assert actual is not None, f"Expected {expected} at index {i} (lb={lb}), got None"
                assert abs(expected - actual) < 1e-12, f"Mismatch at index {i} (lb={lb}): {expected} vs {actual}"


def test_legacy_tradex_scores_series_short_history():
    """Verify histories with < 30 bars return all None."""
    df_short = _generate_synthetic_bars(25, seed=1)
    scores = compute_legacy_tradex_scores_series(df_short)
    assert len(scores) == 25
    assert all(s is None for s in scores)

    df_empty = pd.DataFrame()
    assert compute_legacy_tradex_scores_series(df_empty) == []


def test_legacy_tradex_scores_series_full_equivalence():
    """Verify compute_legacy_tradex_scores_series exactly matches compute_legacy_tradex_score for all prefixes."""
    df = _generate_synthetic_bars(150, seed=123)
    n = len(df)
    weights = LongWeights()

    series_scores = compute_legacy_tradex_scores_series(df, weights=weights)
    assert len(series_scores) == n

    for i in range(n):
        sub = df.iloc[: i + 1]
        if len(sub) < 30:
            assert series_scores[i] is None, f"Expected None for prefix length {len(sub)}"
        else:
            expected = compute_legacy_tradex_score(sub, weights=weights)
            actual = series_scores[i]
            assert actual is not None, f"Expected float at index {i}, got None"
            assert actual == pytest.approx(expected, abs=1e-9), f"Score mismatch at index {i}: expected {expected}, got {actual}"


def test_legacy_tradex_scores_series_custom_weights():
    """Verify custom weights are correctly applied in series scorer."""
    df = _generate_synthetic_bars(60, seed=456)
    custom_weights = LongWeights(
        secular_uptrend=30,
        rsi_healthy=10,
        volume_accumulation=20,
        macd_bullish=20,
        bb_coil=20,
    )
    series_scores = compute_legacy_tradex_scores_series(df, weights=custom_weights)
    for i in range(30, 60):
        sub = df.iloc[: i + 1]
        expected = compute_legacy_tradex_score(sub, weights=custom_weights)
        assert series_scores[i] == pytest.approx(expected, abs=1e-9)


def test_evaluate_baselines_for_date_precomputed_equivalence():
    """Verify evaluate_baselines_for_date produces identical records with precomputed features."""
    sec_ids = ["SEC_A", "SEC_B", "SEC_C", "SEC_D"]
    dfs = {sid: _generate_synthetic_bars(80, seed=i) for i, sid in enumerate(sec_ids)}
    spy_df = _generate_synthetic_bars(80, seed=999)

    as_of_date = dfs["SEC_A"].index[50]
    cutoff_time = "20:30"
    lookbacks = [5, 10, 20, 60]

    # Mode 1: Dynamic DataFrame slicing (legacy)
    legacy_data = {}
    for i, sid in enumerate(sec_ids):
        sub = dfs[sid].iloc[:51]
        raw_elig = (i != 3)  # SEC_D is ineligible
        legacy_data[sid] = {
            "ticker": sid,
            "history_df": sub,
            "atr_14": 1.5 + i,
            "sector": None,
            "universe_eligible": True,
            "raw_outcome_eligible": raw_elig,
        }

    spy_sub = spy_df.iloc[:51]
    legacy_outputs = evaluate_baselines_for_date(
        as_of_date=as_of_date,
        cutoff_time=cutoff_time,
        securities_data=legacy_data,
        spy_history_df=spy_sub,
    )

    # Mode 2: Precomputed features
    spy_mom_series = {
        lb: compute_simple_momentum_series(spy_df["close"].to_numpy(dtype=float), lb)
        for lb in lookbacks
    }
    curr_spy_mom = {lb: spy_mom_series[lb][50] for lb in lookbacks}

    precomputed_data = {}
    for i, sid in enumerate(sec_ids):
        raw_elig = (i != 3)
        if not raw_elig:
            continue
        close_arr = dfs[sid]["close"].to_numpy(dtype=float)
        legacy_series = compute_legacy_tradex_scores_series(dfs[sid])
        mom_series = {lb: compute_simple_momentum_series(close_arr, lb) for lb in lookbacks}
        atr_val = 1.5 + i
        last_close = close_arr[50]
        atr_pct = atr_val / last_close if last_close > 0 else None

        precomputed_data[sid] = {
            "ticker": sid,
            "has_history": True,
            "history_df": None,
            "atr_14": atr_val,
            "sector": None,
            "universe_eligible": True,
            "raw_outcome_eligible": True,
            "precomputed_legacy_score": legacy_series[50],
            "precomputed_momentum": {lb: mom_series[lb][50] for lb in lookbacks},
            "precomputed_atr_pct": atr_pct,
        }

    fast_outputs = evaluate_baselines_for_date(
        as_of_date=as_of_date,
        cutoff_time=cutoff_time,
        securities_data=precomputed_data,
        spy_momentum=curr_spy_mom,
    )

    # Assert exact match of all output records
    assert len(legacy_outputs) == len(fast_outputs)
    assert len(fast_outputs) > 0

    for leg, fst in zip(legacy_outputs, fast_outputs):
        assert leg.immutable_security_id == fst.immutable_security_id
        assert leg.as_of_date == fst.as_of_date
        assert leg.cutoff_time == fst.cutoff_time
        assert leg.comparator_id == fst.comparator_id
        assert leg.ticker_at_decision == fst.ticker_at_decision
        assert leg.comparator_family == fst.comparator_family
        assert leg.raw_score_or_return == pytest.approx(fst.raw_score_or_return, abs=1e-6)
        assert leg.cross_sectional_rank == fst.cross_sectional_rank
        assert leg.cross_sectional_percentile == pytest.approx(fst.cross_sectional_percentile, abs=1e-2)
        assert leg.top_10_flag == fst.top_10_flag
        assert leg.top_25_flag == fst.top_25_flag
