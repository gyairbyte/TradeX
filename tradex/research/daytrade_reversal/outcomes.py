"""Forward outcome and execution friction calculations."""
from __future__ import annotations

from datetime import datetime, timedelta

from .models import DaytradeBar, HorizonOutcome

LOCKED_HORIZONS = (1, 2, 5)

# Friction constants
ROUND_TRIP_0BPS = 0.0
ROUND_TRIP_2BPS = 0.0004  # 2 bps per side = 4 bps round trip
ROUND_TRIP_5BPS = 0.0010  # 5 bps per side = 10 bps round trip


class OutcomeCalculationError(Exception):
    """Raised when an invalid outcome calculation or boundary violation occurs."""


def calculate_horizon_outcomes_for_bar(
    bar: DaytradeBar,
    session_bars: list[DaytradeBar],
    split_end_dt: datetime | None = None,
) -> dict[int, HorizonOutcome]:
    """Compute 1m, 2m, and 5m forward outcomes for a signal bar (event or non-event).

    Point-in-time rules:
    - Entry occurs strictly at open[t+1].
    - Fills at close[t] or during bar t are strictly prohibited.
    - 1m exit is at close[t+1].
    - 2m exit is at close[t+2].
    - 5m exit is at close[t+5].
    - Outcomes must not cross 16:00 session close or split boundary.
    """
    outcomes: dict[int, HorizonOutcome] = {}

    # Map bar_start to DaytradeBar
    bar_map = {b.bar_start: b for b in session_bars}

    # Entry bar t+1 starts at bar.bar_start + 1 minute
    entry_bar_start = bar.bar_start + timedelta(minutes=1)
    entry_bar = bar_map.get(entry_bar_start)

    if entry_bar is None or entry_bar.open <= 0:
        # Incomplete forward data or non-positive open
        return outcomes

    entry_price = entry_bar.open

    for h in LOCKED_HORIZONS:
        # Exit bar t+h starts at bar.bar_start + h minutes
        exit_bar_start = bar.bar_start + timedelta(minutes=h)
        exit_bar = bar_map.get(exit_bar_start)

        if exit_bar is None:
            # Missing or crosses session close
            continue

        # Check split boundary if provided
        if split_end_dt is not None:
            exit_bar_end = exit_bar.available_at
            if exit_bar_end > split_end_dt:
                # Forward horizon crosses split boundary; prohibited
                continue

        exit_price = exit_bar.close
        gross_return = (exit_price - entry_price) / entry_price

        net_0bps = gross_return - ROUND_TRIP_0BPS
        net_2bps = gross_return - ROUND_TRIP_2BPS
        net_5bps = gross_return - ROUND_TRIP_5BPS

        outcomes[h] = HorizonOutcome(
            horizon_minutes=h,
            entry_time=entry_bar.bar_start,
            exit_time=exit_bar.available_at,
            entry_price=entry_price,
            exit_price=exit_price,
            gross_return=gross_return,
            net_return_0bps=net_0bps,
            net_return_2bps=net_2bps,
            net_return_5bps=net_5bps,
        )

    return outcomes
