"""First-half-hour signal calculation, rolling 20-valid-session threshold, and event classification."""
from __future__ import annotations

import math
from datetime import time

import numpy as np

from .models import BaselineObservation, DaytradeSession, EventObservation

THRESHOLD_PERCENTILE = 80.0
THRESHOLD_QUANTILE = 0.80
THRESHOLD_METHOD = "linear"
REQUIRED_PRIOR_VALID_SESSIONS = 20


class EventCalculationError(Exception):
    """Raised when event or threshold calculation encounters an illegal state."""


def calculate_first_half_hour_return(
    current_session: DaytradeSession,
    previous_regular_session: DaytradeSession | None,
) -> float | None:
    """Calculate literature-motivated first-half-hour return for a ticker-session.

    Formula:
    first_half_hour_return(i, D) = close(i, D, 09:59 bar) / close(i, previous_regular_session, 15:59 bar) - 1

    Clarification 2:
    - previous_regular_session must be the immediately preceding regular XNYS session;
    - requires only a usable 15:59 close from the previous session (does not require full session DQ pass);
    - if the immediately preceding session is missing or lacks a usable 15:59 close, returns None.
    - signal is fully known at 10:00:00 ET.
    """
    if previous_regular_session is None:
        return None

    prev_15_59_close = previous_regular_session.get_15_59_close()
    if prev_15_59_close is None or prev_15_59_close <= 0.0 or math.isnan(prev_15_59_close):
        return None

    curr_09_59_close = current_session.get_09_59_close()
    if curr_09_59_close is None or curr_09_59_close <= 0.0 or math.isnan(curr_09_59_close):
        return None

    ret = (curr_09_59_close / prev_15_59_close) - 1.0
    return float(ret)


def compute_ticker_threshold(prior_valid_signal_returns: list[float]) -> float | None:
    """Compute empirical 80th percentile threshold over exactly previous 20 valid signal sessions.

    Clarification 2:
    - Uses exactly previous 20 valid completed signal observations for this ticker;
    - History uses abs(first_half_hour_return);
    - numpy.quantile(history, q=0.80, method='linear');
    - Current session excluded;
    - Zero returns participate in threshold history (abs(0.0) = 0.0);
    - Returns None if fewer than 20 prior valid observations are available.
    """
    if len(prior_valid_signal_returns) < REQUIRED_PRIOR_VALID_SESSIONS:
        return None

    recent_20 = prior_valid_signal_returns[-REQUIRED_PRIOR_VALID_SESSIONS:]
    abs_history = np.array([abs(r) for r in recent_20], dtype=np.float64)

    threshold = float(np.quantile(abs_history, q=THRESHOLD_QUANTILE, method=THRESHOLD_METHOD))
    return threshold


def classify_session_observation(
    session: DaytradeSession,
    signal_return: float,
    threshold: float,
    split_name: str,
) -> tuple[EventObservation | None, BaselineObservation | None]:
    """Classify an eligible session as an EventObservation, BaselineObservation, or neither.

    Eligibility requirements for forward outcomes:
    - 15:30 open bar present and positive;
    - 15:59 close bar present and positive.

    Classification rules:
    - Event: abs(signal_return) >= threshold and signal_return != 0
      - LONG if signal_return > 0
      - SHORT if signal_return < 0
    - Non-event (baseline candidate): abs(signal_return) < threshold and signal_return != 0
      - direction = 'LONG' if signal_return > 0 else 'SHORT'
    - Zero signal return: neither event nor baseline candidate (has no direction).
    """
    entry_price = session.get_15_30_open()
    exit_price = session.get_15_59_close()
    if entry_price is None or exit_price is None:
        return None, None

    bar_15_30 = session.get_bar_by_time(time(15, 30))
    bar_15_59 = session.get_bar_by_time(time(15, 59))
    if bar_15_30 is None or bar_15_59 is None:
        return None, None

    entry_time = bar_15_30.bar_start
    exit_time = bar_15_59.bar_start

    # Zero signal return has no direction
    if signal_return == 0.0:
        return None, None

    direction = "LONG" if signal_return > 0 else "SHORT"
    sign = 1.0 if direction == "LONG" else -1.0

    # Locked return formulas
    gross_return = sign * ((exit_price / entry_price) - 1.0)
    net_0bps = gross_return
    net_2bps = gross_return - 0.0004   # 2 bps per side = 4 bps round-trip
    net_5bps = gross_return - 0.0010   # 5 bps per side = 10 bps round-trip

    is_event = abs(signal_return) >= threshold

    if is_event:
        event = EventObservation(
            ticker=session.ticker,
            session_date=session.session_date,
            direction=direction,
            signal_return=signal_return,
            threshold=threshold,
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=entry_price,
            exit_price=exit_price,
            gross_return=gross_return,
            net_return_0bps=net_0bps,
            net_return_2bps=net_2bps,
            net_return_5bps=net_5bps,
            split=split_name,
        )
        return event, None
    else:
        non_event = BaselineObservation(
            ticker=session.ticker,
            session_date=session.session_date,
            direction=direction,
            signal_return=signal_return,
            threshold=threshold,
            entry_price=entry_price,
            exit_price=exit_price,
            gross_return=gross_return,
            net_return_0bps=net_0bps,
            net_return_2bps=net_2bps,
            net_return_5bps=net_5bps,
            split=split_name,
        )
        return None, non_event
