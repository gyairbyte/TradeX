"""Primary outcome calculations and execution friction models."""
from __future__ import annotations

PRIMARY_FRICTION_BPS_PER_SIDE = 2.0
PRIMARY_ROUND_TRIP_FRICTION = 0.0004   # 4.0 bps

SENSITIVITY_0BPS_ROUND_TRIP = 0.0000   # 0.0 bps
SENSITIVITY_5BPS_ROUND_TRIP = 0.0010   # 10.0 bps


def calculate_gross_signed_return(
    direction: str,
    entry_price: float,
    exit_price: float,
) -> float:
    """Calculate gross signed return for LONG or SHORT event.

    LONG: exit / entry - 1
    SHORT: 1 - exit / entry
    Algebraically equivalent to: sign * (exit / entry - 1)
    """
    if entry_price <= 0.0 or exit_price <= 0.0:
        raise ValueError(f"Prices must be strictly positive: entry={entry_price}, exit={exit_price}")

    if direction == "LONG":
        return (exit_price / entry_price) - 1.0
    elif direction == "SHORT":
        return 1.0 - (exit_price / entry_price)
    else:
        raise ValueError(f"Invalid direction '{direction}'; must be 'LONG' or 'SHORT'")


def apply_friction_to_gross_return(
    gross_signed_return: float,
    bps_per_side: float = 2.0,
) -> float:
    """Apply realistic execution friction to a gross signed return.

    net_return = gross_signed_return - 2 * (bps_per_side / 10000.0)
    """
    round_trip_cost = 2.0 * (bps_per_side / 10000.0)
    return gross_signed_return - round_trip_cost


def calculate_gross_win_rate(gross_signed_returns: list[float]) -> float:
    """Calculate the fraction of events with strictly positive gross signed return.

    Note: Spec requires gross win rate, not net win rate.
    Returns 0.0 if empty list.
    """
    if not gross_signed_returns:
        return 0.0
    wins = sum(1 for r in gross_signed_returns if r > 0.0)
    return float(wins) / float(len(gross_signed_returns))
