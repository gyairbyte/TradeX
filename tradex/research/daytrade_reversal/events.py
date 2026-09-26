"""Event detection, rolling quantile calculation, and overlap classification."""
from __future__ import annotations

from datetime import datetime, time, timedelta

import numpy as np

from .calendar import to_market_time
from .models import DaytradeBar, DaytradeSession, EventObservation

EARLIEST_EVENT_TIME = time(9, 31)
LATEST_EVENT_TIME = time(15, 54)
EVENT_QUANTILE = 0.001
REQUIRED_PRIOR_SESSIONS = 20


class EventCalculationError(Exception):
    """Raised when event or threshold calculation encounters an illegal state."""


def is_eligible_event_time(bar_start: datetime) -> bool:
    """Return True if bar_start ET is within the locked event window [09:31, 15:54]."""
    local_dt = to_market_time(bar_start)
    t = local_dt.time()
    return EARLIEST_EVENT_TIME <= t <= LATEST_EVENT_TIME


def extract_session_eligible_returns(session: DaytradeSession) -> list[float]:
    """Extract valid within-session 1-minute close-to-close returns for eligible window [09:31, 15:54].

    Strictly excludes the 09:30 opening return (which would compare 09:30 close to prior day).
    Only returns between consecutive bars within the session are included.
    """
    if not session.is_valid or len(session.bars) < 2:
        return []

    returns: list[float] = []
    # Map bar_start to bar
    bars = session.bars
    for i in range(1, len(bars)):
        curr_bar = bars[i]
        prev_bar = bars[i - 1]

        # Verify consecutive 1-minute spacing
        if (curr_bar.bar_start - prev_bar.bar_start) != timedelta(minutes=1):
            continue

        if is_eligible_event_time(curr_bar.bar_start) and prev_bar.close > 0:
            ret = (curr_bar.close - prev_bar.close) / prev_bar.close
            returns.append(ret)

    return returns


def compute_session_threshold(prior_valid_sessions: list[DaytradeSession]) -> float | None:
    """Compute empirical 0.1st percentile (quantile 0.001) using numpy linear method.

    Requires exactly 20 completed valid regular sessions.
    Returns None if fewer than 20 prior valid sessions are available.
    """
    if len(prior_valid_sessions) < REQUIRED_PRIOR_SESSIONS:
        return None

    # Use the most recent 20 valid sessions
    sessions_to_use = prior_valid_sessions[-REQUIRED_PRIOR_SESSIONS:]

    all_returns: list[float] = []
    for s in sessions_to_use:
        all_returns.extend(extract_session_eligible_returns(s))

    if not all_returns:
        return None

    # Spec requirement: numpy.quantile(..., q=0.001, method="linear")
    arr = np.array(all_returns, dtype=np.float64)
    threshold = float(np.quantile(arr, q=EVENT_QUANTILE, method="linear"))
    return threshold


def detect_events_in_session(
    session: DaytradeSession,
    threshold: float,
    split_name: str,
) -> tuple[list[EventObservation], list[tuple[DaytradeBar, float]]]:
    """Detect extreme downside 1-minute events and qualifying non-events in session.

    Returns:
        (events, non_events) where non_events are (bar, return).
    """
    if not session.is_valid or len(session.bars) < 2:
        return [], []

    events: list[EventObservation] = []
    non_events: list[tuple[DaytradeBar, float]] = []

    bars = session.bars
    for i in range(1, len(bars)):
        curr_bar = bars[i]
        prev_bar = bars[i - 1]

        if (curr_bar.bar_start - prev_bar.bar_start) != timedelta(minutes=1):
            continue

        if not is_eligible_event_time(curr_bar.bar_start):
            continue

        if prev_bar.close <= 0:
            continue

        ret = (curr_bar.close - prev_bar.close) / prev_bar.close
        event_id = f"{session.ticker}_{curr_bar.bar_start.strftime('%Y%m%d_%H%M')}"

        # Floating-point representation guard (e.g. 1e-12 tolerance)
        if ret <= threshold + 1e-12:
            # Event!
            # Maximum 5-minute forward window: [t+1 open, t+5 close]
            # Analysis window starts at t+1 open (curr_bar.bar_start + 1m)
            # Analysis window ends at t+5 close (curr_bar.bar_start + 6m)
            w_start = curr_bar.bar_start + timedelta(minutes=1)
            w_end = curr_bar.bar_start + timedelta(minutes=6)

            event_obs = EventObservation(
                event_id=event_id,
                ticker=session.ticker,
                session_date=session.session_date,
                split=split_name,
                event_bar_start=curr_bar.bar_start,
                event_available_at=curr_bar.available_at,
                event_return=ret,
                threshold=threshold,
                analysis_window_start=w_start,
                analysis_window_end=w_end,
            )
            events.append(event_obs)
        else:
            non_events.append((curr_bar, ret))

    return events, non_events


def classify_overlapping_events(events: list[EventObservation]) -> None:
    """Classify events as overlapping using the locked 5-minute analysis window [t+1 open, t+5 close].

    An event counts as overlapping if its analysis interval intersects another event's analysis interval.
    Marks is_overlapping, same_ticker_overlap, and cross_ticker_overlap in-place.
    """
    n = len(events)
    for i in range(n):
        e1 = events[i]
        if e1.analysis_window_start is None or e1.analysis_window_end is None:
            continue

        for j in range(i + 1, n):
            e2 = events[j]
            if e2.analysis_window_start is None or e2.analysis_window_end is None:
                continue

            # Interval intersection: max(start1, start2) < min(end1, end2)
            # Because intervals represent continuous holding periods:
            start_max = max(e1.analysis_window_start, e2.analysis_window_start)
            end_min = min(e1.analysis_window_end, e2.analysis_window_end)

            if start_max < end_min:
                # Intersects!
                e1.is_overlapping = True
                e2.is_overlapping = True

                if e1.ticker == e2.ticker:
                    e1.same_ticker_overlap = True
                    e2.same_ticker_overlap = True
                else:
                    e1.cross_ticker_overlap = True
                    e2.cross_ticker_overlap = True
