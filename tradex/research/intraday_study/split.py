"""Locked split definitions for the INTRA-001D real-data study."""
from __future__ import annotations

from datetime import date
from typing import Literal

SplitName = Literal["development", "validation", "holdout"]

SPLIT_DATE_RANGES: dict[SplitName, tuple[date, date]] = {
    "development": (date(2025, 1, 2), date(2025, 6, 30)),
    "validation": (date(2025, 7, 1), date(2025, 9, 30)),
    "holdout": (date(2025, 10, 1), date(2025, 12, 31)),
}

SPLIT_MONTHS: dict[SplitName, list[str]] = {
    "development": ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"],
    "validation": ["2025-07", "2025-08", "2025-09"],
    "holdout": ["2025-10", "2025-11", "2025-12"],
}


def split_for_effective_month(effective_month: str) -> SplitName:
    """Return the locked split for an effective month string ``YYYY-MM``."""
    for split, months in SPLIT_MONTHS.items():
        if effective_month in months:
            return split
    raise ValueError(f"effective month {effective_month} not in locked split map")


def split_start_date(split: SplitName) -> date:
    return SPLIT_DATE_RANGES[split][0]


def split_end_date(split: SplitName) -> date:
    return SPLIT_DATE_RANGES[split][1]
