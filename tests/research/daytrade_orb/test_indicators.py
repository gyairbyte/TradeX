"""Deterministic indicator tests with exact XNYS session lookbacks for ADV14, ATR14, and RV14."""
from __future__ import annotations

from datetime import date

import pytest

from tradex.market.hours import _calendar
from tradex.research.daytrade_orb import (
    DailyBar,
    OpeningRangeVolumeObservation,
    compute_adv14,
    compute_atr14_wilder,
    compute_relative_volume,
)
from tradex.research.daytrade_orb.indicators import get_prior_xnys_sessions


def _make_daily_bar(d: date, o: float, h: float, l: float, c: float, v: float, sym: str = "AAPL") -> DailyBar:
    return DailyBar(
        symbol=sym,
        session_date=d,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
    )


def test_xnys_calendar_helper_and_lookback() -> None:
    """Requirement: get_prior_xnys_sessions returns exact preceding XNYS sessions across holidays/weekends."""
    cal = _calendar()
    # Jan 16, 2024 is Tuesday after MLK day (Monday Jan 15 holiday)
    target_session = date(2024, 1, 16)
    assert cal.is_session(target_session)

    prior_14 = get_prior_xnys_sessions(target_session, 14)
    assert len(prior_14) == 14
    # All must be strictly before Jan 16
    assert all(d < target_session for d in prior_14)
    # The session immediately prior to Jan 16, 2024 was Friday Jan 12, 2024
    assert prior_14[-1] == date(2024, 1, 12)
    # MLK Day (Jan 15) and weekends are not in the list
    assert date(2024, 1, 15) not in prior_14
    assert date(2024, 1, 13) not in prior_14
    assert date(2024, 1, 14) not in prior_14
    # New Year's Day (Jan 1, 2024) is an exchange holiday
    assert date(2024, 1, 1) not in prior_14
    # Christmas (Dec 25, 2023) is an exchange holiday
    assert date(2023, 12, 25) not in prior_14


def test_adv14_exact_xnys_sessions_success() -> None:
    """Requirement: ADV14 computes exact mean across preceding 14 XNYS sessions; weekends/holidays ignored."""
    target_session = date(2024, 1, 16)
    prior_14_dates = get_prior_xnys_sessions(target_session, 14)

    daily_bars: list[DailyBar] = []
    expected_sum = 0.0
    for i, d in enumerate(prior_14_dates):
        vol = 1_000_000.0 + (i * 100_000.0)
        expected_sum += vol
        daily_bars.append(_make_daily_bar(d, 100.0, 105.0, 95.0, 100.0, vol))

    # Add target session D with massive anomaly volume 50,000,000
    daily_bars.append(_make_daily_bar(target_session, 100.0, 105.0, 95.0, 100.0, 50_000_000.0))

    adv = compute_adv14(daily_bars, target_session, lookback=14)
    expected_adv = expected_sum / 14.0
    assert adv is not None
    assert adv == pytest.approx(expected_adv)
    # Target session D volume does NOT enter ADV
    assert adv < 5_000_000.0


def test_adv14_missing_actual_session_fails_closed() -> None:
    """Requirement: If even one actual trading session is missing, fail closed (None)."""
    target_session = date(2024, 1, 16)
    prior_14_dates = get_prior_xnys_sessions(target_session, 14)

    # Omit one session (e.g. index 5: 2024-01-03)
    omitted_date = prior_14_dates[5]
    daily_bars = [
        _make_daily_bar(d, 100.0, 105.0, 95.0, 100.0, 1_500_000.0)
        for d in prior_14_dates
        if d != omitted_date
    ]

    adv = compute_adv14(daily_bars, target_session, lookback=14)
    assert adv is None


def test_adv14_older_extra_bar_does_not_repair_gap() -> None:
    """Requirement: An older bar (e.g. D-15) does NOT replace a missing required session."""
    target_session = date(2024, 1, 16)
    prior_14_dates = get_prior_xnys_sessions(target_session, 14)
    cal = _calendar()
    older_bar_date = cal.previous_session(prior_14_dates[0]).date()

    # Omit one session and add an older bar
    omitted_date = prior_14_dates[5]
    daily_bars = [
        _make_daily_bar(d, 100.0, 105.0, 95.0, 100.0, 1_500_000.0)
        for d in prior_14_dates
        if d != omitted_date
    ]
    daily_bars.append(_make_daily_bar(older_bar_date, 100.0, 105.0, 95.0, 100.0, 1_500_000.0))
    assert len(daily_bars) == 14  # Still 14 bars total, but wrong sessions!

    adv = compute_adv14(daily_bars, target_session, lookback=14)
    assert adv is None


def test_adv14_duplicate_session_fails_closed() -> None:
    """Requirement: Duplicate trading-session dates in daily_bars cause fail closed."""
    target_session = date(2024, 1, 16)
    prior_14_dates = get_prior_xnys_sessions(target_session, 14)

    daily_bars = [
        _make_daily_bar(d, 100.0, 105.0, 95.0, 100.0, 1_500_000.0)
        for d in prior_14_dates
    ]
    # Add duplicate for the latest prior date
    daily_bars.append(_make_daily_bar(prior_14_dates[-1], 100.0, 105.0, 95.0, 100.0, 1_500_000.0))

    adv = compute_adv14(daily_bars, target_session, lookback=14)
    assert adv is None


def test_atr14_wilder_exact_xnys_sessions_success() -> None:
    """Requirement: Wilder ATR14 computes across contiguous XNYS sessions ending at D-1."""
    cal = _calendar()
    target_session = date(2024, 1, 16)
    prev = cal.previous_session(target_session)
    # Require 16 continuous XNYS sessions ending at D-1 (15 TR observations)
    prior_dates = [s.date() for s in cal.sessions_window(prev, -16)]

    daily_bars: list[DailyBar] = []
    # Day 0: Baseline close = 100.0
    daily_bars.append(_make_daily_bar(prior_dates[0], 100.0, 101.0, 99.0, 100.0, 1_000_000.0))

    # Days 1 to 14: Each day has H=102, L=98, C=100 -> TR = 4.0
    for d in prior_dates[1:15]:
        daily_bars.append(_make_daily_bar(d, 100.0, 102.0, 98.0, 100.0, 1_000_000.0))

    # Day 15 (D-1): H=108, L=101, C=105 -> TR_15 = max(7, 8, 1) = 8.0
    # Subsequent ATR = ((4.0 * 13) + 8.0) / 14 = 60.0 / 14
    daily_bars.append(_make_daily_bar(prior_dates[15], 102.0, 108.0, 101.0, 105.0, 1_000_000.0))

    # Add target session D anomaly
    daily_bars.append(_make_daily_bar(target_session, 150.0, 300.0, 50.0, 200.0, 1_000_000.0))

    atr = compute_atr14_wilder(daily_bars, target_session, lookback=14)
    expected_atr = 60.0 / 14.0
    assert atr is not None
    assert atr == pytest.approx(expected_atr, rel=1e-6)
    assert atr < 10.0


def test_atr14_missing_trading_session_fails_closed() -> None:
    """Requirement: If an actual XNYS session in the history is missing, fail closed (None)."""
    cal = _calendar()
    target_session = date(2024, 1, 16)
    prev = cal.previous_session(target_session)
    prior_dates = [s.date() for s in cal.sessions_window(prev, -16)]

    # Omit session index 7
    omitted = prior_dates[7]
    daily_bars = [
        _make_daily_bar(d, 100.0, 102.0, 98.0, 100.0, 1_000_000.0)
        for d in prior_dates
        if d != omitted
    ]

    atr = compute_atr14_wilder(daily_bars, target_session, lookback=14)
    assert atr is None


def test_atr14_duplicate_session_fails_closed() -> None:
    """Requirement: Duplicate session dates in daily_bars cause ATR14 to fail closed."""
    cal = _calendar()
    target_session = date(2024, 1, 16)
    prev = cal.previous_session(target_session)
    prior_dates = [s.date() for s in cal.sessions_window(prev, -16)]

    daily_bars = [
        _make_daily_bar(d, 100.0, 102.0, 98.0, 100.0, 1_000_000.0)
        for d in prior_dates
    ]
    daily_bars.append(_make_daily_bar(prior_dates[-1], 100.0, 102.0, 98.0, 100.0, 1_000_000.0))

    atr = compute_atr14_wilder(daily_bars, target_session, lookback=14)
    assert atr is None


def test_relative_volume_dated_observations_success() -> None:
    """Requirement: RV14 computes from exactly preceding 14 completed XNYS sessions."""
    target_session = date(2024, 1, 16)
    prior_14_dates = get_prior_xnys_sessions(target_session, 14)

    obs_list = [
        OpeningRangeVolumeObservation(symbol="AAPL", session_date=d, volume=50_000.0)
        for d in prior_14_dates
    ]

    # Current OR volume = 100,000 -> RV = 100,000 / 50,000 = 2.0
    rv, mean_vol = compute_relative_volume(obs_list, 100_000.0, target_session=target_session)
    assert rv is not None
    assert mean_vol == pytest.approx(50_000.0)
    assert rv == pytest.approx(2.0)


def test_relative_volume_missing_session_fails_closed() -> None:
    """Requirement: Missing even one required XNYS session observation fails closed."""
    target_session = date(2024, 1, 16)
    prior_14_dates = get_prior_xnys_sessions(target_session, 14)

    # Omit index 3
    omitted = prior_14_dates[3]
    obs_list = [
        OpeningRangeVolumeObservation(symbol="AAPL", session_date=d, volume=50_000.0)
        for d in prior_14_dates
        if d != omitted
    ]

    rv, mean_vol = compute_relative_volume(obs_list, 100_000.0, target_session=target_session)
    assert rv is None and mean_vol is None


def test_relative_volume_older_extra_obs_does_not_repair_gap() -> None:
    """Requirement: An older observation (e.g. D-15) does not repair a missing date."""
    target_session = date(2024, 1, 16)
    prior_14_dates = get_prior_xnys_sessions(target_session, 14)
    cal = _calendar()
    older_date = cal.previous_session(prior_14_dates[0]).date()

    omitted = prior_14_dates[3]
    obs_list = [
        OpeningRangeVolumeObservation(symbol="AAPL", session_date=d, volume=50_000.0)
        for d in prior_14_dates
        if d != omitted
    ]
    obs_list.append(OpeningRangeVolumeObservation(symbol="AAPL", session_date=older_date, volume=50_000.0))
    assert len(obs_list) == 14

    rv, mean_vol = compute_relative_volume(obs_list, 100_000.0, target_session=target_session)
    assert rv is None and mean_vol is None


def test_relative_volume_duplicate_date_fails_closed() -> None:
    """Requirement: Duplicate session dates fail closed."""
    target_session = date(2024, 1, 16)
    prior_14_dates = get_prior_xnys_sessions(target_session, 14)

    obs_list = [
        OpeningRangeVolumeObservation(symbol="AAPL", session_date=d, volume=50_000.0)
        for d in prior_14_dates
    ]
    obs_list.append(OpeningRangeVolumeObservation(symbol="AAPL", session_date=prior_14_dates[0], volume=50_000.0))

    rv, mean_vol = compute_relative_volume(obs_list, 100_000.0, target_session=target_session)
    assert rv is None and mean_vol is None
