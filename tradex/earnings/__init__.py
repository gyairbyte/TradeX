"""Earnings-awareness module — flag/filter stocks with earnings within N days."""
from tradex.earnings.calendar import (
    EarningsDataUnavailableError,
    annotate,
    days_until_earnings,
    get_next_earnings,
    is_within_earnings_window,
)

__all__ = [
    "EarningsDataUnavailableError",
    "annotate",
    "days_until_earnings",
    "get_next_earnings",
    "is_within_earnings_window",
]
