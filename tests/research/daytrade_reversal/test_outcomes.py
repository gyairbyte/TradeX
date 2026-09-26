"""Forward outcome and execution friction calculation tests."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from tradex.research.daytrade_reversal.calendar import build_regular_session_grid
from tradex.research.daytrade_reversal.outcomes import (
    ROUND_TRIP_0BPS,
    calculate_horizon_outcomes_for_bar,
)
from tradex.research.daytrade_reversal.quality import audit_ticker_session
from tradex.research.daytrade_reversal.synthetic import generate_synthetic_session_bars


def test_next_bar_open_entry_and_horizons() -> None:
    """Entry strictly uses open[t+1]; exits use close[t+1], close[t+2], close[t+5]."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)
    raw_df = generate_synthetic_session_bars("AAPL", session_d)
    session, _ = audit_ticker_session("AAPL", session_d, raw_df, grid)

    # Pick bar at 10:00 (index 30)
    bar_t = session.bars[30]
    bar_t1 = session.bars[31]
    bar_t2 = session.bars[32]
    bar_t5 = session.bars[35]

    outcomes = calculate_horizon_outcomes_for_bar(bar_t, session.bars)

    assert 1 in outcomes
    assert 2 in outcomes
    assert 5 in outcomes

    # 1m outcome
    o1 = outcomes[1]
    assert o1.entry_time == bar_t1.bar_start
    assert o1.entry_price == bar_t1.open
    assert o1.exit_price == bar_t1.close
    expected_gross_1m = (bar_t1.close - bar_t1.open) / bar_t1.open
    assert o1.gross_return == pytest.approx(expected_gross_1m)

    # 2m outcome
    o2 = outcomes[2]
    assert o2.entry_price == bar_t1.open
    assert o2.exit_price == bar_t2.close
    expected_gross_2m = (bar_t2.close - bar_t1.open) / bar_t1.open
    assert o2.gross_return == pytest.approx(expected_gross_2m)

    # 5m outcome
    o5 = outcomes[5]
    assert o5.entry_price == bar_t1.open
    assert o5.exit_price == bar_t5.close
    expected_gross_5m = (bar_t5.close - bar_t1.open) / bar_t1.open
    assert o5.gross_return == pytest.approx(expected_gross_5m)


def test_execution_friction_deduction() -> None:
    """Net return deducts exact round-trip friction (0 bps, 4 bps, 10 bps)."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)
    raw_df = generate_synthetic_session_bars("AAPL", session_d)
    session, _ = audit_ticker_session("AAPL", session_d, raw_df, grid)

    bar_t = session.bars[10]
    outcomes = calculate_horizon_outcomes_for_bar(bar_t, session.bars)
    o1 = outcomes[1]

    # Gross
    assert o1.net_return_0bps == pytest.approx(o1.gross_return - ROUND_TRIP_0BPS)
    # Primary (2 bps per side = 4 bps round-trip = 0.0004)
    assert o1.net_return_2bps == pytest.approx(o1.gross_return - 0.0004)
    # Stressed (5 bps per side = 10 bps round-trip = 0.0010)
    assert o1.net_return_5bps == pytest.approx(o1.gross_return - 0.0010)


def test_session_close_boundary_truncation() -> None:
    """Outcomes near session close that cross 16:00 are not created."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)
    raw_df = generate_synthetic_session_bars("AAPL", session_d)
    session, _ = audit_ticker_session("AAPL", session_d, raw_df, grid)

    # 15:58 bar (index 388) -> t+1 is 15:59; 2m and 5m cross session close
    bar_late = session.bars[388]
    outcomes = calculate_horizon_outcomes_for_bar(bar_late, session.bars)
    assert 1 in outcomes
    assert 2 not in outcomes
    assert 5 not in outcomes


def test_split_boundary_truncation() -> None:
    """Outcomes crossing split boundary timestamp are truncated."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)
    raw_df = generate_synthetic_session_bars("AAPL", session_d)
    session, _ = audit_ticker_session("AAPL", session_d, raw_df, grid)

    bar_t = session.bars[30]
    # Set split_end_dt to available_at of t+1 (only 1m completes within split)
    split_end = bar_t.bar_start + timedelta(minutes=2)  # allows t+1 exit, but not t+2
    outcomes = calculate_horizon_outcomes_for_bar(bar_t, session.bars, split_end_dt=split_end)
    assert 1 in outcomes
    assert 2 not in outcomes
    assert 5 not in outcomes
