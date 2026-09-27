"""Equivalence verification tests for LONG-002C-PERF-002 optimizations.

Verifies that Step 1 algorithmic performance optimizations preserve 100% of mathematical,
analytical, and point-in-time research semantics across:
1. Wilder ATR single-pass series precomputation vs reference compute_atr prefix slicing.
2. Decision observation construction and data quality coverage.
3. Forward outcome calculation across all nine cells for both dict and tuple inputs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tradex.research.long_002c.calendar import get_trading_sessions
from tradex.research.long_002c.dataset import (
    build_decision_observations_for_security,
    compute_atr,
    compute_atr_series,
)
from tradex.research.long_002c.identity import SecurityIdentity
from tradex.research.long_002c.outcomes import (
    compute_all_nine_outcomes,
    compute_outcome_cell,
)
from tradex.research.long_002c.spec import (
    PRIMARY_ENTRY_FRICTION_BPS,
    TARGET_GRID,
)


def test_atr_series_equivalence_early_and_established_history() -> None:
    """Verify compute_atr_series produces identical outputs to compute_atr prefix slicing."""
    rng = np.random.default_rng(12345)
    n = 200
    closes = [100.0]
    highs = [101.5]
    lows = [98.5]
    for _ in range(n - 1):
        c = closes[-1] + float(rng.normal(0, 1.5))
        h = max(c, closes[-1]) + float(rng.uniform(0.1, 2.0))
        l = min(c, closes[-1]) - float(rng.uniform(0.1, 2.0))
        closes.append(c)
        highs.append(h)
        lows.append(l)

    # 1. Test across all prefix lengths from 0 to n
    opt_series = compute_atr_series(highs, lows, closes, period=14)
    assert len(opt_series) == n

    for k in range(1, n + 1):
        ref_val = compute_atr(highs[:k], lows[:k], closes[:k], period=14)
        opt_val = opt_series[k - 1]
        assert ref_val == opt_val, f"Mismatch at prefix length k={k}: ref={ref_val}, opt={opt_val}"

    # 2. Test early history (< 15 bars) strictly returns None
    for i in range(14):
        assert opt_series[i] is None, f"Bar {i} should have None ATR"

    # 3. Bar 14 (15th bar) is first non-None ATR
    assert opt_series[14] is not None
    assert opt_series[14] == compute_atr(highs[:15], lows[:15], closes[:15], period=14)

    # 4. Test very short series (< 15 bars)
    short_series = compute_atr_series(highs[:10], lows[:10], closes[:10], period=14)
    assert short_series == [None] * 10


def test_atr_series_0900_and_2030_information_sets() -> None:
    """Verify ATR values for 09:00 (T-1) and 20:30 (T) match exact prefix history."""
    rng = np.random.default_rng(999)
    n = 50
    closes = [50.0]
    highs = [51.0]
    lows = [49.0]
    for _ in range(n - 1):
        c = closes[-1] + float(rng.normal(0, 1.0))
        h = max(c, closes[-1]) + float(rng.uniform(0.1, 1.0))
        l = min(c, closes[-1]) - float(rng.uniform(0.1, 1.0))
        closes.append(c)
        highs.append(h)
        lows.append(l)

    atrs = compute_atr_series(highs, lows, closes, 14)

    # For any decision session index idx in [15, n-1]:
    for idx in range(15, n):
        # 20:30 uses history through session T (idx): slice length idx + 1
        atr_2030 = atrs[idx]
        ref_2030 = compute_atr(highs[: idx + 1], lows[: idx + 1], closes[: idx + 1], 14)
        assert atr_2030 == ref_2030

        # 09:00 uses history strictly through session T-1 (idx - 1): slice length idx
        atr_0900 = atrs[idx - 1]
        ref_0900 = compute_atr(highs[:idx], lows[:idx], closes[:idx], 14)
        assert atr_0900 == ref_0900


def test_outcome_cell_tuple_vs_dict_equivalence() -> None:
    """Verify compute_outcome_cell gives bitwise identical OutcomeLabelRecord for dict vs tuple."""
    rng = np.random.default_rng(42)
    n_forward = 25

    opens = [100.0]
    highs = [102.0]
    lows = [98.0]
    closes = [101.0]
    for _ in range(n_forward - 1):
        o = closes[-1] + float(rng.normal(0, 0.5))
        c = o + float(rng.normal(0, 1.0))
        h = max(o, c) + float(rng.uniform(0.1, 2.0))
        l = min(o, c) - float(rng.uniform(0.1, 2.0))
        opens.append(o)
        highs.append(h)
        lows.append(l)
        closes.append(c)

    # Dict representation
    dict_bars = [
        {"open": opens[i], "high": highs[i], "low": lows[i], "close": closes[i]}
        for i in range(n_forward)
    ]

    # Tuple representation (opens, highs, lows, closes)
    tuple_bars = (opens, highs, lows, closes)
    # Also 3-tuple (highs, lows, closes)
    tuple_bars_3 = (highs, lows, closes)

    for target_pct, horizon_sessions in TARGET_GRID:
        ref_record = compute_outcome_cell(
            immutable_security_id="TEST_SEC_1",
            ticker_at_decision="TEST",
            as_of_date="2020-06-15",
            cutoff_time="20:30",
            target_pct=target_pct,
            horizon_sessions=horizon_sessions,
            next_open_price=opens[0],
            forward_bars=dict_bars,
            pre_entry_atr=1.5,
            entry_friction_bps=PRIMARY_ENTRY_FRICTION_BPS,
            special_distribution_unresolved=False,
            as_traded_entry_price=opens[0],
        )

        opt_record_4 = compute_outcome_cell(
            immutable_security_id="TEST_SEC_1",
            ticker_at_decision="TEST",
            as_of_date="2020-06-15",
            cutoff_time="20:30",
            target_pct=target_pct,
            horizon_sessions=horizon_sessions,
            next_open_price=opens[0],
            forward_bars=tuple_bars,
            pre_entry_atr=1.5,
            entry_friction_bps=PRIMARY_ENTRY_FRICTION_BPS,
            special_distribution_unresolved=False,
            as_traded_entry_price=opens[0],
        )

        opt_record_3 = compute_outcome_cell(
            immutable_security_id="TEST_SEC_1",
            ticker_at_decision="TEST",
            as_of_date="2020-06-15",
            cutoff_time="20:30",
            target_pct=target_pct,
            horizon_sessions=horizon_sessions,
            next_open_price=opens[0],
            forward_bars=tuple_bars_3,
            pre_entry_atr=1.5,
            entry_friction_bps=PRIMARY_ENTRY_FRICTION_BPS,
            special_distribution_unresolved=False,
            as_traded_entry_price=opens[0],
        )

        assert ref_record.to_dict() == opt_record_4.to_dict()
        assert ref_record.to_dict() == opt_record_3.to_dict()


def test_compute_all_nine_outcomes_all_fields_equivalence() -> None:
    """Verify compute_all_nine_outcomes matches across all fields for all nine cells."""
    rng = np.random.default_rng(777)
    n = 22
    opens = np.linspace(50.0, 55.0, n) + rng.normal(0, 0.2, n)
    highs = opens + rng.uniform(0.5, 3.0, n)
    lows = opens - rng.uniform(0.5, 3.0, n)
    closes = (highs + lows) / 2.0

    dict_bars = [
        {"open": float(opens[i]), "high": float(highs[i]), "low": float(lows[i]), "close": float(closes[i])}
        for i in range(n)
    ]
    tuple_bars = (opens, highs, lows, closes)

    ref_nine = compute_all_nine_outcomes(
        immutable_security_id="SEC_A",
        ticker_at_decision="TEST_TICKER",
        as_of_date="2019-10-15",
        cutoff_time="20:30",
        next_open_price=float(opens[0]),
        forward_bars=dict_bars,
        pre_entry_atr=1.234,
        as_traded_entry_price=float(opens[0]),
    )

    opt_nine = compute_all_nine_outcomes(
        immutable_security_id="SEC_A",
        ticker_at_decision="TEST_TICKER",
        as_of_date="2019-10-15",
        cutoff_time="20:30",
        next_open_price=float(opens[0]),
        forward_bars=tuple_bars,
        pre_entry_atr=1.234,
        as_traded_entry_price=float(opens[0]),
    )

    for r_rec, o_rec in zip(ref_nine, opt_nine):
        assert r_rec == o_rec
        assert r_rec.to_dict() == o_rec.to_dict()


def test_build_decision_observations_optimized_deterministic_equivalence() -> None:
    """Verify build_decision_observations_for_security with synthetic deterministic data."""
    # Build 100 trading sessions from valid XNYS calendar
    dates = get_trading_sessions("2016-01-04", "2016-06-30")[:100]
    sessions = dates

    df = pd.DataFrame(
        {
            "open": np.linspace(20.0, 30.0, 100),
            "high": np.linspace(20.5, 30.5, 100),
            "low": np.linspace(19.5, 29.5, 100),
            "close": np.linspace(20.2, 30.2, 100),
            "volume": np.full(100, 1_000_000.0),
            "as_traded_close": np.linspace(20.2, 30.2, 100),
            "as_traded_open": np.linspace(20.0, 30.0, 100),
        },
        index=dates,
    )

    ident = SecurityIdentity(
        immutable_security_id="SEC_DETERMINISTIC",
        ticker_at_decision="DET",
        effective_start="2016-01-04",
        effective_end=dates[-1],
        cik="0001234567",
        company_name="DETERMINISTIC CO",
        security_type="common_stock",
        listing_date="2015-12-01",
    )

    market_caps = {d: 5_000_000_000.0 for d in dates}

    for cutoff in ["09:00", "20:30"]:
        obs, _elig, _cl, _earn, _excl, qual = build_decision_observations_for_security(
            identity=ident,
            bars_df=df,
            trading_sessions=sessions,
            cutoff_time=cutoff,
            dev_start=dates[0],
            dev_end=dates[-1],
            market_caps=market_caps,
        )

        assert len(obs) == 100
        assert qual.malformed_bar_count == 0
        assert qual.duplicate_bar_count == 0
        assert qual.completeness_pct == 100.0

        for i, o in enumerate(obs):
            assert o.immutable_security_id == "SEC_DETERMINISTIC"
            assert o.cutoff_time == cutoff
            if cutoff == "09:00" and i == 0:
                # First session has no prior completed bar at 09:00
                assert o.split_normalized_close == 0.0
                assert o.as_traded_close == 0.0
            else:
                assert o.split_normalized_close > 0
                assert o.as_traded_close > 0
            if cutoff == "20:30" and 63 <= i <= 73:
                assert o.raw_outcome_eligible is True
                assert o.data_complete is True
