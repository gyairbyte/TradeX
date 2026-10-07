"""Pure deterministic technical indicator calculations for DAYTRADE-003.

Enforces point-in-time correctness: session D prices never enter ADV14 or ATR14,
and Relative Volume uses exactly the immediately preceding 14 completed XNYS sessions.
"""
from __future__ import annotations

import math
from datetime import date

from tradex.market.hours import _calendar

from .models import DailyBar, OpeningRangeVolumeObservation


def get_prior_xnys_sessions(target_session: date, count: int) -> list[date]:
    """Return the exact ``count`` completed XNYS trading session dates immediately preceding ``target_session``.

    Parameters:
        target_session: The target session date D.
        count: The number of previous trading sessions required.

    Returns:
        List of session dates sorted chronologically (D-count, ..., D-1).

    Raises:
        ValueError if target_session is not an XNYS session or count <= 0.
    """
    cal = _calendar()
    if not cal.is_session(target_session):
        raise ValueError(f"Target date {target_session} is not a valid XNYS trading session")
    if count <= 0:
        raise ValueError(f"Count must be positive, got {count}")
    prev = cal.previous_session(target_session)
    window = cal.sessions_window(prev, -count)
    return [s.date() for s in window]


def compute_adv14(
    daily_bars: list[DailyBar],
    target_session: date,
    lookback: int = 14,
) -> float | None:
    """Compute Average Daily Volume over exactly the preceding 14 completed regular XNYS sessions.

    Parameters:
        daily_bars: Historical daily bars for a symbol.
        target_session: Session date D being evaluated (strictly excluded).
        lookback: Number of completed trading sessions required (default 14).

    Returns:
        Arithmetic mean of volume over the exact 14 completed XNYS sessions immediately preceding D,
        or None if any required session date is missing, duplicated, or non-computable (fail closed).
    """
    try:
        expected_dates = get_prior_xnys_sessions(target_session, lookback)
    except ValueError:
        return None

    # Check for duplicate session dates in daily_bars
    seen_dates: set[date] = set()
    bars_by_date: dict[date, DailyBar] = {}
    for b in daily_bars:
        if b.session_date in seen_dates:
            # Duplicate daily bar date detected -> fail closed
            return None
        seen_dates.add(b.session_date)
        bars_by_date[b.session_date] = b

    # Check that each expected date is present
    window_bars: list[DailyBar] = []
    for dt in expected_dates:
        bar = bars_by_date.get(dt)
        if bar is None or bar.volume < 0:
            return None
        window_bars.append(bar)

    total_volume = sum(b.volume for b in window_bars)
    adv = float(total_volume / float(lookback))
    return adv if math.isfinite(adv) else None


def compute_atr14_wilder(
    daily_bars: list[DailyBar],
    target_session: date,
    lookback: int = 14,
) -> float | None:
    """Compute Welles Wilder 14-session Average True Range available through session D-1.

    Session D is strictly excluded from its own ATR calculation.
    True Range formula:
        TR_t = max(high_t - low_t, abs(high_t - close_{t-1}), abs(low_t - close_{t-1}))

    Contiguity Requirement:
        Requires a contiguous sequence of completed XNYS trading sessions ending at D-1.
        Minimum required sessions: lookback + 1 (i.e. 15 daily bars to produce 14 True Ranges).
        Duplicate session dates or missing XNYS session dates within the sequence fail closed.

    Smoothing convention:
        Initial ATR14: arithmetic mean of the first 14 True Range observations (requires 15 daily bars).
        Subsequent ATR_t: ((ATR_{t-1} * 13) + TR_t) / 14

    Returns:
        Wilder ATR14 through session D-1, or None if insufficient history, gaps, or duplicates exist.
    """
    cal = _calendar()
    try:
        if not cal.is_session(target_session):
            return None
        expected_prev = cal.previous_session(target_session).date()
    except (ValueError, KeyError, IndexError):
        return None

    prior_bars = [b for b in daily_bars if b.session_date < target_session]
    if len(prior_bars) < lookback + 1:
        return None

    # Check for duplicate session dates
    seen_dates: set[date] = set()
    for b in prior_bars:
        if b.session_date in seen_dates:
            return None
        seen_dates.add(b.session_date)

    # Sort prior bars chronologically
    sorted_prior = sorted(prior_bars, key=lambda b: b.session_date)

    # The most recent prior bar must be exactly D-1 (expected_prev)
    if sorted_prior[-1].session_date != expected_prev:
        return None

    # Verify that the entire sequence of prior bars is a contiguous XNYS session window
    k = len(sorted_prior)
    try:
        expected_window = [s.date() for s in cal.sessions_window(expected_prev, -k)]
    except (ValueError, KeyError, IndexError):
        return None

    actual_dates = [b.session_date for b in sorted_prior]
    if actual_dates != expected_window:
        # Gaps or missing XNYS sessions detected in history -> fail closed
        return None

    # Compute True Range series starting from the second available bar
    true_ranges: list[float] = []
    for i in range(1, len(sorted_prior)):
        curr = sorted_prior[i]
        prev = sorted_prior[i - 1]
        tr = max(
            curr.high - curr.low,
            abs(curr.high - prev.close),
            abs(curr.low - prev.close),
        )
        true_ranges.append(tr)

    if len(true_ranges) < lookback:
        return None

    # Initial Wilder ATR is arithmetic mean of first 14 TR observations
    atr = sum(true_ranges[:lookback]) / float(lookback)

    # Subsequent Wilder smoothing
    for tr in true_ranges[lookback:]:
        atr = ((atr * float(lookback - 1)) + tr) / float(lookback)

    atr_val = float(atr)
    return atr_val if math.isfinite(atr_val) else None


def compute_relative_volume(
    prior_observations: list[OpeningRangeVolumeObservation],
    current_or_volume: float,
    target_session: date,
    lookback: int = 14,
) -> tuple[float | None, float | None]:
    """Compute Relative Volume (RV) during the opening range.

    Formula:
        RV(D, j) = OpeningRangeVolume(D, j) / mean(OpeningRangeVolume(D-1, j), ..., OpeningRangeVolume(D-14, j))

    Source fidelity rule (CORR-003C-RV-LOOKBACK):
        Uses exactly the immediately preceding 14 completed regular XNYS trading sessions.
        Does NOT condition on passing price/ADV/ATR filters.
        If any of the 14 required observations is missing, duplicated, or non-positive, fails closed.

    Returns:
        (relative_volume, mean_prior_or_volume) or (None, None) on missing/invalid input.
    """
    try:
        expected_dates = get_prior_xnys_sessions(target_session, lookback)
    except ValueError:
        return None, None

    if (
        isinstance(current_or_volume, bool)
        or not isinstance(current_or_volume, (int, float))
        or not math.isfinite(current_or_volume)
        or current_or_volume < 0
    ):
        return None, None

    # Index observations by session_date with duplicate check
    obs_by_date: dict[date, OpeningRangeVolumeObservation] = {}
    seen_dates: set[date] = set()
    for obs in prior_observations:
        if obs.session_date in seen_dates:
            # Duplicate observation date -> fail closed
            return None, None
        seen_dates.add(obs.session_date)
        obs_by_date[obs.session_date] = obs

    # Ensure all exact expected dates are present and have non-negative volume
    prior_volumes: list[float] = []
    for dt in expected_dates:
        obs = obs_by_date.get(dt)
        if obs is None or obs.volume < 0 or not math.isfinite(obs.volume):
            return None, None
        prior_volumes.append(obs.volume)

    mean_prior = sum(prior_volumes) / float(lookback)
    if not math.isfinite(mean_prior) or mean_prior <= 0:
        return None, None

    rv = float(current_or_volume / mean_prior)
    if not math.isfinite(rv):
        return None, None
    return rv, float(mean_prior)
