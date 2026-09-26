"""Matched baseline pool and uplift calculation tests."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from tradex.research.daytrade_reversal.baseline import build_baseline_pool, match_event_baselines
from tradex.research.daytrade_reversal.models import (
    BaselineObservation,
    EventObservation,
    HorizonOutcome,
)


def _make_dummy_outcome(gross: float) -> dict[int, HorizonOutcome]:
    return {
        1: HorizonOutcome(
            horizon_minutes=1,
            entry_time=datetime(2025, 1, 2, 14, 31, tzinfo=UTC),
            exit_time=datetime(2025, 1, 2, 14, 32, tzinfo=UTC),
            entry_price=100.0,
            exit_price=100.0 * (1.0 + gross),
            gross_return=gross,
            net_return_0bps=gross,
            net_return_2bps=gross - 0.0004,
            net_return_5bps=gross - 0.0010,
        )
    }


def test_matched_baseline_uses_arithmetic_mean_and_computes_uplift() -> None:
    """Event is matched against qualifying non-events with same ticker, minute-of-day, split."""
    # 2 baseline observations for AAPL at 10:00 in validation split
    # Return 1: gross = 0.0010, net_2bps = 0.0006
    # Return 2: gross = 0.0020, net_2bps = 0.0016
    # Expected baseline reference return = (0.0006 + 0.0016) / 2 = 0.0011
    b1 = BaselineObservation(
        ticker="AAPL",
        session_date=date(2025, 7, 2),
        split="validation",
        minute_of_day="10:00",
        bar_start=datetime(2025, 7, 2, 14, 0, tzinfo=UTC),
        available_at=datetime(2025, 7, 2, 14, 1, tzinfo=UTC),
        outcomes=_make_dummy_outcome(0.0010),
    )
    b2 = BaselineObservation(
        ticker="AAPL",
        session_date=date(2025, 7, 3),
        split="validation",
        minute_of_day="10:00",
        bar_start=datetime(2025, 7, 3, 14, 0, tzinfo=UTC),
        available_at=datetime(2025, 7, 3, 14, 1, tzinfo=UTC),
        outcomes=_make_dummy_outcome(0.0020),
    )

    # Event for AAPL at 10:00 with gross = 0.0050, net_2bps = 0.0046
    ev = EventObservation(
        event_id="AAPL_20250701_1000",
        ticker="AAPL",
        session_date=date(2025, 7, 1),
        split="validation",
        event_bar_start=datetime(2025, 7, 1, 14, 0, tzinfo=UTC),
        event_available_at=datetime(2025, 7, 1, 14, 1, tzinfo=UTC),
        event_return=-0.03,
        threshold=-0.02,
        outcomes=_make_dummy_outcome(0.0050),
    )

    pool = build_baseline_pool([b1, b2])
    match_event_baselines([ev], pool, horizon=1, friction_bps=2.0)

    assert ev.matched_baseline_1m_net == pytest.approx(0.0011)
    # Uplift = event_net - baseline_net = 0.0046 - 0.0011 = 0.0035
    assert ev.uplift_1m_net == pytest.approx(0.0046 - 0.0011)


def test_missing_baseline_sets_explicit_none_non_computable() -> None:
    """If no qualifying baseline observations exist for the event's bucket, values are set to None."""
    ev = EventObservation(
        event_id="MSFT_20250701_1000",
        ticker="MSFT",
        session_date=date(2025, 7, 1),
        split="validation",
        event_bar_start=datetime(2025, 7, 1, 14, 0, tzinfo=UTC),
        event_available_at=datetime(2025, 7, 1, 14, 1, tzinfo=UTC),
        event_return=-0.03,
        threshold=-0.02,
        outcomes=_make_dummy_outcome(0.0050),
    )

    empty_pool = build_baseline_pool([])
    match_event_baselines([ev], empty_pool, horizon=1, friction_bps=2.0)

    # Must be explicitly None (not 0.0!)
    assert ev.matched_baseline_1m_net is None
    assert ev.uplift_1m_net is None


def test_baseline_pool_excludes_events() -> None:
    """Event observations cannot enter the baseline pool."""
    # Pool only accepts BaselineObservation objects, not EventObservation
    b = BaselineObservation(
        ticker="AAPL",
        session_date=date(2025, 7, 2),
        split="validation",
        minute_of_day="10:00",
        bar_start=datetime(2025, 7, 2, 14, 0, tzinfo=UTC),
        available_at=datetime(2025, 7, 2, 14, 1, tzinfo=UTC),
        outcomes=_make_dummy_outcome(0.0010),
    )
    pool = build_baseline_pool([b])
    key = ("AAPL", "10:00", "validation")
    assert len(pool[key]) == 1
    assert isinstance(pool[key][0], BaselineObservation)
