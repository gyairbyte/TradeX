"""Tests for exact mathematical formulas, adverse barriers, clean risk caps, and same-bar ambiguity in outcomes."""
from __future__ import annotations

from tradex.research.long_002c.outcomes import (
    compute_all_nine_outcomes,
    compute_outcome_cell,
)


def test_outcome_formulas_basic_win() -> None:
    """Verify clean target attainment on smooth upward move without adverse excursion."""
    # Next open = 100.0, 10 bps friction -> entry = 100.10
    # +10% target = 110.11
    # ATR = 2.0 -> adverse barrier pct = max(0.05, 1.5 * 2.0 / 100.10) = max(0.05, 0.02997) = 0.05 (5%)
    # clean risk cap = min(10% / 2, 0.05) = 0.05 (5%)
    forward_bars = [
        {"open": 100.0, "high": 102.0, "low": 99.5, "close": 101.5},
        {"open": 101.5, "high": 105.0, "low": 101.0, "close": 104.5},
        {"open": 104.5, "high": 111.0, "low": 104.0, "close": 110.5},  # Target hit on bar 3
        {"open": 110.5, "high": 112.0, "low": 109.0, "close": 111.0},
        {"open": 111.0, "high": 113.0, "low": 110.0, "close": 112.5},
    ]

    res = compute_outcome_cell(
        immutable_security_id="TEST_SEC",
        ticker_at_decision="TEST",
        as_of_date="2016-01-04",
        cutoff_time="20:30",
        target_pct=10.0,
        horizon_sessions=5,
        next_open_price=100.0,
        forward_bars=forward_bars,
        pre_entry_atr=2.0,
        entry_friction_bps=10.0,
    )

    assert res.reference_entry_price == 100.10
    assert res.target_price == 110.11
    assert res.adverse_barrier_pct == 0.05
    assert res.clean_risk_cap_pct == 0.05
    assert res.time_to_target == 3
    assert res.clean_target_reached is True
    assert res.path_sequence_ambiguous is False
    assert res.near_miss is False
    assert res.partial_move is False
    assert res.sustained_target is True


def test_same_bar_ambiguity_disqualifies_clean_target() -> None:
    """If target bar touches both target price and adverse barrier, clean target is False."""
    # Entry = 100.0 (0 bps friction for simple math)
    # Target = 110.0, Adverse barrier = 95.0
    # Bar 1 touches high=111.0 and low=94.0 -> same-bar ambiguity!
    forward_bars = [
        {"open": 100.0, "high": 111.0, "low": 94.0, "close": 108.0},
        {"open": 108.0, "high": 112.0, "low": 107.0, "close": 111.0},
        {"open": 111.0, "high": 112.0, "low": 110.0, "close": 111.5},
        {"open": 111.5, "high": 113.0, "low": 111.0, "close": 112.0},
        {"open": 112.0, "high": 113.0, "low": 111.5, "close": 112.5},
    ]

    res = compute_outcome_cell(
        immutable_security_id="TEST_SEC",
        ticker_at_decision="TEST",
        as_of_date="2016-01-04",
        cutoff_time="20:30",
        target_pct=10.0,
        horizon_sessions=5,
        next_open_price=100.0,
        forward_bars=forward_bars,
        pre_entry_atr=2.0,
        entry_friction_bps=0.0,
    )

    # Gross target was touched
    assert res.target_progress_ratio >= 1.0
    # But same-bar ambiguity disqualifies clean target
    assert res.path_sequence_ambiguous is True
    assert res.clean_target_reached is False


def test_near_miss_and_partial_move() -> None:
    """Verify near-miss (0.8..1.0) and partial-move (0.5..0.8) classifications."""
    # Entry = 100.0, Target = 110.0 (+10%)
    # Max high = 108.5 -> MFE = 8.5% -> target_progress_ratio = 0.85 -> Near miss
    bars_near = [
        {"open": 100.0, "high": 108.5, "low": 99.0, "close": 107.0},
        {"open": 107.0, "high": 108.0, "low": 105.0, "close": 106.0},
        {"open": 106.0, "high": 107.0, "low": 105.0, "close": 106.5},
        {"open": 106.5, "high": 107.0, "low": 105.0, "close": 106.0},
        {"open": 106.0, "high": 107.0, "low": 105.0, "close": 106.0},
    ]

    res_near = compute_outcome_cell(
        immutable_security_id="TEST_SEC",
        ticker_at_decision="TEST",
        as_of_date="2016-01-04",
        cutoff_time="20:30",
        target_pct=10.0,
        horizon_sessions=5,
        next_open_price=100.0,
        forward_bars=bars_near,
        pre_entry_atr=2.0,
        entry_friction_bps=0.0,
    )
    assert res_near.near_miss is True
    assert res_near.partial_move is False
    assert res_near.clean_target_reached is False

    # Max high = 106.0 -> MFE = 6.0% -> target_progress_ratio = 0.60 -> Partial move
    bars_partial = [
        {"open": 100.0, "high": 106.0, "low": 99.0, "close": 105.0},
        {"open": 105.0, "high": 105.5, "low": 104.0, "close": 104.5},
        {"open": 104.5, "high": 105.0, "low": 104.0, "close": 104.5},
        {"open": 104.5, "high": 105.0, "low": 104.0, "close": 104.5},
        {"open": 104.5, "high": 105.0, "low": 104.0, "close": 104.5},
    ]
    res_partial = compute_outcome_cell(
        immutable_security_id="TEST_SEC",
        ticker_at_decision="TEST",
        as_of_date="2016-01-04",
        cutoff_time="20:30",
        target_pct=10.0,
        horizon_sessions=5,
        next_open_price=100.0,
        forward_bars=bars_partial,
        pre_entry_atr=2.0,
        entry_friction_bps=0.0,
    )
    assert res_partial.near_miss is False
    assert res_partial.partial_move is True


def test_compute_all_nine_outcomes() -> None:
    """Verify calculation produces exactly 9 records."""
    # 21 bars
    bars_21 = [{"open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0}] * 21
    outcomes = compute_all_nine_outcomes(
        immutable_security_id="TEST_SEC",
        ticker_at_decision="TEST",
        as_of_date="2016-01-04",
        cutoff_time="20:30",
        next_open_price=100.0,
        forward_bars=bars_21,
        pre_entry_atr=2.0,
    )
    assert len(outcomes) == 9
    targets = {o.target_pct for o in outcomes}
    horizons = {o.horizon_sessions for o in outcomes}
    assert targets == {10.0, 20.0, 30.0}
    assert horizons == {5, 10, 21}
