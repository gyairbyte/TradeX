"""Temporal split assignment and isolation tests."""
from __future__ import annotations

from datetime import UTC, date, datetime

from tradex.research.score_validation.events import _split_for, _within_split
from tradex.research.score_validation.models import Split


def test_split_for_returns_correct_split():
    splits = {
        "development": Split(date(2020, 1, 1), date(2021, 12, 31)),
        "validation": Split(date(2022, 1, 1), date(2023, 12, 31)),
        "holdout": Split(date(2024, 1, 1), date(2024, 12, 31)),
    }
    assert _split_for(datetime(2020, 6, 1, tzinfo=UTC), splits) == "development"
    assert _split_for(datetime(2022, 6, 1, tzinfo=UTC), splits) == "validation"
    assert _split_for(datetime(2025, 6, 1, tzinfo=UTC), splits) is None


def test_within_split_inclusive_boundaries():
    split = Split(date(2020, 1, 1), date(2020, 12, 31))
    assert _within_split(datetime(2020, 1, 1, tzinfo=UTC), split)
    assert _within_split(datetime(2020, 12, 31, 23, 59, tzinfo=UTC), split)
    assert not _within_split(datetime(2021, 1, 1, tzinfo=UTC), split)
