"""Tests for strict split quarantine and cutoff isolation."""
from __future__ import annotations

import pytest

from tradex.research.long_002d2.spec import enforce_cutoff_guard, enforce_split_guard


def test_split_guard_permits_development_dates() -> None:
    """Verify that development split dates pass without exception."""
    enforce_split_guard("2016-01-01")
    enforce_split_guard("2016-12-30")
    enforce_split_guard("2018-06-15")
    enforce_split_guard("2020-11-23")
    enforce_split_guard("2020-12-31")


def test_split_guard_rejects_pre_dev_dates() -> None:
    """Verify that dates prior to 2016-01-01 are rejected."""
    with pytest.raises(ValueError, match="SPLIT QUARANTINE BREACH"):
        enforce_split_guard("2015-12-31")


def test_split_guard_rejects_validation_split() -> None:
    """Verify that validation dates (2021-2022) fail closed."""
    validation_dates = ["2021-01-01", "2021-06-01", "2022-12-31"]
    for d in validation_dates:
        with pytest.raises(ValueError, match="SPLIT QUARANTINE BREACH"):
            enforce_split_guard(d)


def test_split_guard_rejects_holdout_split() -> None:
    """Verify that holdout dates (2023-2025) fail closed."""
    holdout_dates = ["2023-01-01", "2024-03-15", "2025-12-31"]
    for d in holdout_dates:
        with pytest.raises(ValueError, match="SPLIT QUARANTINE BREACH"):
            enforce_split_guard(d)


def test_split_guard_rejects_shadow_and_future_dates() -> None:
    """Verify that shadow and live/future dates (2026+) fail closed."""
    shadow_dates = ["2026-01-01", "2026-09-28", "2027-01-01"]
    for d in shadow_dates:
        with pytest.raises(ValueError, match="SPLIT QUARANTINE BREACH"):
            enforce_split_guard(d)


def test_cutoff_guard_permits_20_30() -> None:
    """Verify that only 20:30 is permitted."""
    enforce_cutoff_guard("20:30")


def test_cutoff_guard_rejects_other_cutoffs() -> None:
    """Verify that morning cutoffs (09:00) or other times fail closed."""
    invalid_cutoffs = ["09:00", "16:00", "09:30", "20:00", "21:00"]
    for c in invalid_cutoffs:
        with pytest.raises(ValueError, match="CUTOFF GUARD BREACH"):
            enforce_cutoff_guard(c)
