"""Tests for first-half-hour signal calculation, rolling 20-session threshold, and event classification.

Enforces Clarification 2:
- Signal denominator requires only usable 15:59 close from immediately-prior regular session.
- Threshold history requires strictly valid prior sessions with computable signal returns.
- Point-in-time integrity: altering intermediate bars (10:00 to 15:29) does not alter signal or classification.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from tradex.research.daytrade_momentum.calendar import build_regular_session_grid
from tradex.research.daytrade_momentum.events import (
    calculate_first_half_hour_return,
    classify_session_observation,
    compute_ticker_threshold,
)
from tradex.research.daytrade_momentum.synthetic import (
    build_synthetic_session_from_bars,
    generate_synthetic_session_bars,
)


def test_first_half_hour_return_formula() -> None:
    """Verify first_half_hour_return = close(09:59) / prev_close(15:59) - 1."""
    prev_d = date(2025, 1, 14)
    curr_d = date(2025, 1, 15)

    df_prev = generate_synthetic_session_bars("SPY", prev_d, exit_15_59_close=100.0)
    prev_sess = build_synthetic_session_from_bars("SPY", prev_d, df_prev)

    df_curr = generate_synthetic_session_bars("SPY", curr_d, signal_09_59_close=102.5)
    curr_sess = build_synthetic_session_from_bars("SPY", curr_d, df_curr)

    ret = calculate_first_half_hour_return(curr_sess, prev_sess)
    assert ret is not None
    assert pytest.approx(ret, rel=1e-6) == 0.025  # 102.5 / 100.0 - 1.0 = +2.5%


def test_clarification2_prior_session_usable_close_vs_invalid_session() -> None:
    """Verify that prior regular session requires only usable 15:59 close, even if marked invalid."""
    prev_d = date(2025, 1, 14)
    curr_d = date(2025, 1, 15)

    # Prior session has 25 missing bars (so it is invalid/excluded), but has a valid 15:59 close
    grid_prev = build_regular_session_grid(prev_d)
    drop_25 = [grid_prev[i].strftime("%H:%M") for i in range(25)]
    df_prev = generate_synthetic_session_bars(
        "SPY",
        prev_d,
        exit_15_59_close=100.0,
        drop_minutes=drop_25,
    )
    prev_sess = build_synthetic_session_from_bars("SPY", prev_d, df_prev)
    assert prev_sess.is_valid is False
    assert prev_sess.get_15_59_close() == 100.0

    df_curr = generate_synthetic_session_bars("SPY", curr_d, signal_09_59_close=101.0)
    curr_sess = build_synthetic_session_from_bars("SPY", curr_d, df_curr)

    # Signal return is computable because prior session has a usable 15:59 close
    ret = calculate_first_half_hour_return(curr_sess, prev_sess)
    assert ret is not None
    assert pytest.approx(ret, rel=1e-6) == 0.010

    # If prior session has no 15:59 close, signal is None
    df_no_close = generate_synthetic_session_bars("SPY", prev_d, drop_minutes=["15:59"])
    prev_sess_no_close = build_synthetic_session_from_bars("SPY", prev_d, df_no_close)
    ret_none = calculate_first_half_hour_return(curr_sess, prev_sess_no_close)
    assert ret_none is None


def test_rolling_20_valid_session_threshold() -> None:
    """Verify rolling threshold requires exactly 20 valid prior returns and uses 80th percentile linear."""
    # Fewer than 20 returns -> returns None
    short_history = [0.01] * 19
    assert compute_ticker_threshold(short_history) is None

    # Exactly 20 returns: values 0.001, 0.002, ..., 0.020
    history_20 = [0.001 * i for i in range(1, 21)]
    thresh = compute_ticker_threshold(history_20)
    assert thresh is not None

    expected = float(np.quantile([abs(r) for r in history_20], q=0.80, method="linear"))
    assert pytest.approx(thresh, rel=1e-6) == expected

    # Verify negative returns participate via absolute value
    mixed_history = [-0.001 * i if i % 2 == 0 else 0.001 * i for i in range(1, 21)]
    thresh_mixed = compute_ticker_threshold(mixed_history)
    assert pytest.approx(thresh_mixed, rel=1e-6) == expected


def test_classification_event_and_non_event() -> None:
    """Verify event vs non-event classification based on threshold comparison."""
    session_d = date(2025, 1, 15)
    df = generate_synthetic_session_bars(
        "SPY",
        session_d,
        entry_15_30_open=100.0,
        exit_15_59_close=101.0,
    )
    sess = build_synthetic_session_from_bars("SPY", session_d, df)

    threshold = 0.015

    # 1. Event LONG: signal_return = 0.020 >= 0.015
    ev_long, ne_long = classify_session_observation(sess, signal_return=0.020, threshold=threshold, split_name="development")
    assert ev_long is not None
    assert ne_long is None
    assert ev_long.direction == "LONG"
    assert ev_long.signal_return == 0.020
    assert ev_long.threshold == 0.015
    assert ev_long.gross_return == (101.0 / 100.0) - 1.0  # +1%

    # 2. Event SHORT: signal_return = -0.020 (abs >= 0.015)
    ev_short, ne_short = classify_session_observation(sess, signal_return=-0.020, threshold=threshold, split_name="development")
    assert ev_short is not None
    assert ne_short is None
    assert ev_short.direction == "SHORT"
    assert ev_short.signal_return == -0.020
    assert ev_short.gross_return == -( (101.0 / 100.0) - 1.0 )  # -1%

    # 3. Non-event LONG: signal_return = 0.008 < 0.015
    ev_ne_long, ne_ne_long = classify_session_observation(sess, signal_return=0.008, threshold=threshold, split_name="development")
    assert ev_ne_long is None
    assert ne_ne_long is not None
    assert ne_ne_long.direction == "LONG"

    # 4. Zero return: neither event nor baseline
    ev_zero, ne_zero = classify_session_observation(sess, signal_return=0.0, threshold=threshold, split_name="development")
    assert ev_zero is None
    assert ne_zero is None


def test_pit_information_integrity() -> None:
    """Verify changing intermediate bars (10:00 to 15:29) does not alter signal or classification."""
    prev_d = date(2025, 1, 14)
    curr_d = date(2025, 1, 15)

    df_prev = generate_synthetic_session_bars("SPY", prev_d, exit_15_59_close=100.0)
    prev_sess = build_synthetic_session_from_bars("SPY", prev_d, df_prev)

    # Session 1: normal intermediate bars
    df_curr_1 = generate_synthetic_session_bars(
        "SPY", curr_d,
        signal_09_59_close=102.0,
        entry_15_30_open=102.5,
        exit_15_59_close=103.0,
    )
    sess_1 = build_synthetic_session_from_bars("SPY", curr_d, df_curr_1)

    # Session 2: wildly volatile intermediate bars between 10:00 and 15:29
    df_curr_2 = df_curr_1.copy()
    # Modify a bar at 12:00
    for idx, row in df_curr_2.iterrows():
        if "12:00" in str(row["datetime"]):
            df_curr_2.at[idx, "close"] = 999.0
            df_curr_2.at[idx, "high"] = 1000.0

    sess_2 = build_synthetic_session_from_bars("SPY", curr_d, df_curr_2)

    sig_1 = calculate_first_half_hour_return(sess_1, prev_sess)
    sig_2 = calculate_first_half_hour_return(sess_2, prev_sess)
    assert sig_1 == sig_2

    ev_1, _ = classify_session_observation(sess_1, sig_1, 0.015, "development")
    ev_2, _ = classify_session_observation(sess_2, sig_2, 0.015, "development")
    assert ev_1 is not None and ev_2 is not None
    assert ev_1.gross_return == ev_2.gross_return
    assert ev_1.direction == ev_2.direction
