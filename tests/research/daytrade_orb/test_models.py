"""Tests for models and strict non-finite numeric integrity."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from tradex.research.daytrade_orb.models import (
    Candidate,
    DailyBar,
    DataIntegrityError,
    Direction,
    MinuteBar,
    OpeningRange,
    OpeningRangeVolumeObservation,
    UniverseMember,
)
from tradex.research.daytrade_orb.ranking import evaluate_candidate

NY_TZ = ZoneInfo("America/New_York")


def test_daily_bar_non_finite_rejection() -> None:
    """Requirement: DailyBar must reject NaN, +inf, and -inf on open, high, low, close, volume."""
    d = date(2025, 6, 2)
    valid_args = {
        "symbol": "TEST",
        "session_date": d,
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 1_000_000.0,
    }

    for field in ["open", "high", "low", "close", "volume"]:
        for bad_val in [float("nan"), float("inf"), float("-inf")]:
            corrupted = dict(valid_args)
            corrupted[field] = bad_val
            with pytest.raises(DataIntegrityError, match="must be a finite number"):
                DailyBar(**corrupted)


def test_daily_bar_zero_volume_valid() -> None:
    """Requirement: Zero volume is a physically possible valid finite value."""
    d = date(2025, 6, 2)
    bar = DailyBar("TEST", d, 100.0, 105.0, 95.0, 102.0, 0.0)
    assert bar.volume == 0.0


def test_minute_bar_non_finite_rejection() -> None:
    """Requirement: MinuteBar must reject NaN, +inf, and -inf on open, high, low, close, volume."""
    d = date(2025, 6, 2)
    ts = datetime(2025, 6, 2, 9, 30, tzinfo=NY_TZ)
    valid_args = {
        "symbol": "TEST",
        "timestamp": ts,
        "session_date": d,
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 10_000.0,
    }

    for field in ["open", "high", "low", "close", "volume"]:
        for bad_val in [float("nan"), float("inf"), float("-inf")]:
            corrupted = dict(valid_args)
            corrupted[field] = bad_val
            with pytest.raises(DataIntegrityError, match="must be a finite number"):
                MinuteBar(**corrupted)


def test_minute_bar_zero_volume_valid() -> None:
    """Requirement: MinuteBar zero volume is valid."""
    d = date(2025, 6, 2)
    ts = datetime(2025, 6, 2, 9, 30, tzinfo=NY_TZ)
    bar = MinuteBar("TEST", ts, d, 100.0, 105.0, 95.0, 102.0, 0.0)
    assert bar.volume == 0.0


def test_opening_range_volume_obs_non_finite_rejection() -> None:
    """Requirement: OpeningRangeVolumeObservation volume must be finite."""
    d = date(2025, 6, 2)
    for bad_val in [float("nan"), float("inf"), float("-inf")]:
        with pytest.raises(DataIntegrityError, match="must be a finite number"):
            OpeningRangeVolumeObservation("TEST", d, bad_val)

    # Zero volume is valid
    obs = OpeningRangeVolumeObservation("TEST", d, 0.0)
    assert obs.volume == 0.0


def test_opening_range_non_finite_rejection() -> None:
    """Requirement: OpeningRange must reject non-finite OHLCV and stop_level."""
    d = date(2025, 6, 2)
    valid_args = {
        "symbol": "TEST",
        "session_date": d,
        "or_open": 100.0,
        "or_high": 105.0,
        "or_low": 95.0,
        "or_close": 102.0,
        "or_volume": 50_000.0,
        "direction": Direction.LONG,
        "stop_level": 105.0,
    }

    for field in ["or_open", "or_high", "or_low", "or_close", "or_volume", "stop_level"]:
        for bad_val in [float("nan"), float("inf"), float("-inf")]:
            corrupted = dict(valid_args)
            corrupted[field] = bad_val
            with pytest.raises(DataIntegrityError, match="must be finite"):
                OpeningRange(**corrupted)


def test_candidate_non_finite_rejection() -> None:
    """Requirement: Candidate must reject non-finite numeric indicator fields."""
    d = date(2025, 6, 2)
    valid_args = {
        "symbol": "TEST",
        "session_date": d,
        "opening_price": 100.0,
        "adv14": 2_000_000.0,
        "atr14": 2.0,
        "or_volume": 50_000.0,
        "mean_prior_or_volume": 25_000.0,
        "relative_volume": 2.0,
        "price_passed": True,
        "adv_passed": True,
        "atr_passed": True,
        "rv_passed": True,
        "is_eligible": True,
    }

    for field in ["opening_price", "adv14", "atr14", "or_volume", "mean_prior_or_volume", "relative_volume"]:
        for bad_val in [float("nan"), float("inf"), float("-inf")]:
            corrupted = dict(valid_args)
            corrupted[field] = bad_val
            with pytest.raises(DataIntegrityError, match="must be finite"):
                Candidate(**corrupted)


def test_evaluate_candidate_non_finite_raises_integrity_error() -> None:
    """Requirement: Non-finite values in evaluate_candidate MUST raise DataIntegrityError, NOT technical failure."""
    d = date(2025, 6, 2)
    op = OpeningRange("TEST", d, 100.0, 105.0, 95.0, 102.0, 50_000.0, Direction.LONG, 105.0)

    for bad_val in [float("nan"), float("inf"), float("-inf")]:
        with pytest.raises(DataIntegrityError, match="must be finite"):
            evaluate_candidate("TEST", d, op, adv14=bad_val, atr14=2.0, mean_prior_or_volume=25_000.0, rv=2.0)

        with pytest.raises(DataIntegrityError, match="must be finite"):
            evaluate_candidate("TEST", d, op, adv14=2_000_000.0, atr14=bad_val, mean_prior_or_volume=25_000.0, rv=2.0)

        with pytest.raises(DataIntegrityError, match="must be finite"):
            evaluate_candidate("TEST", d, op, adv14=2_000_000.0, atr14=2.0, mean_prior_or_volume=25_000.0, rv=bad_val)


def test_universe_member_symbol_normalization() -> None:
    """Requirement: UniverseMember normalizes symbol by stripping whitespace and uppercase."""
    m = UniverseMember("  aapl  ", "NASDAQ", True)
    assert m.symbol == "AAPL"

    with pytest.raises(DataIntegrityError, match="non-empty string"):
        UniverseMember("   ", "NASDAQ", True)
