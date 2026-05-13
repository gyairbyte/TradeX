"""Earnings-awareness module — flag/filter stocks with earnings within N days."""
from tradex.earnings.calendar import (
    get_next_earnings,
    days_until_earnings,
    is_within_earnings_window,
    annotate,
)

__all__ = [
    "get_next_earnings",
    "days_until_earnings",
    "is_within_earnings_window",
    "annotate",
]
