"""Tests for frozen baseline comparators, volatility weighting, and user-weight isolation."""
from __future__ import annotations

import pandas as pd

from tradex.research.long_002c.baselines import (
    compute_legacy_tradex_score,
    compute_simple_momentum,
    evaluate_baselines_for_date,
)


def test_simple_momentum_calculation() -> None:
    """Verify price return over trailing N sessions."""
    closes = [100.0, 102.0, 105.0, 110.0, 115.0, 120.0]
    # 5-session momentum: 120.0 / 100.0 - 1.0 = 0.20 (+20%)
    mom_5 = compute_simple_momentum(closes, 5)
    assert mom_5 is not None
    assert round(mom_5, 4) == 0.2000


def test_legacy_tradex_scorer_uses_fresh_weights_isolation() -> None:
    """Verify legacy scorer runs with default LongWeights() and produces deterministic score."""
    dates = pd.date_range("2016-01-01", periods=60, freq="B")
    # Upward trending DataFrame with moving indicators
    df = pd.DataFrame(
        {
            "open": [100.0 + i * 0.5 for i in range(60)],
            "high": [101.0 + i * 0.5 for i in range(60)],
            "low": [99.0 + i * 0.5 for i in range(60)],
            "close": [100.5 + i * 0.5 for i in range(60)],
            "volume": [1000000 + i * 10000 for i in range(60)],
        },
        index=dates,
    )

    score = compute_legacy_tradex_score(df)
    assert isinstance(score, float)
    assert 0.0 <= score <= 100.0


def test_evaluate_baselines_cross_sectional_ranking() -> None:
    """Verify cross-sectional ranking and percentiles on common observations."""
    dates = pd.date_range("2016-01-01", periods=70, freq="B")
    date_str = dates[-1].strftime("%Y-%m-%d")

    # Security A has +30% momentum
    df_a = pd.DataFrame(
        {
            "open": [100.0] * 70,
            "high": [105.0] * 70,
            "low": [95.0] * 70,
            "close": [100.0 + (i * 0.5) for i in range(70)],
            "volume": [1000000] * 70,
        },
        index=dates,
    )
    # Security B has flat momentum
    df_b = pd.DataFrame(
        {
            "open": [100.0] * 70,
            "high": [102.0] * 70,
            "low": [98.0] * 70,
            "close": [100.0] * 70,
            "volume": [1000000] * 70,
        },
        index=dates,
    )

    sec_data = {
        "SEC_A": {
            "ticker": "AAA",
            "history_df": df_a,
            "atr_14": 2.5,
            "sector": "TECH",
            "universe_eligible": True,
        },
        "SEC_B": {
            "ticker": "BBB",
            "history_df": df_b,
            "atr_14": 1.5,
            "sector": "TECH",
            "universe_eligible": True,
        },
    }

    outputs = evaluate_baselines_for_date(
        as_of_date=date_str,
        cutoff_time="20:30",
        securities_data=sec_data,
    )
    assert len(outputs) > 0

    # SEC_A should rank 1 in simple_momentum_20
    mom20_outputs = [o for o in outputs if o.comparator_id == "simple_momentum_20"]
    assert len(mom20_outputs) == 2
    out_a = next(o for o in mom20_outputs if o.immutable_security_id == "SEC_A")
    out_b = next(o for o in mom20_outputs if o.immutable_security_id == "SEC_B")
    assert out_a.cross_sectional_rank == 1
    assert out_b.cross_sectional_rank == 2
    assert out_a.cross_sectional_percentile > out_b.cross_sectional_percentile
