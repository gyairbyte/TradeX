"""Tests for direction-matched baseline pool construction and event uplift."""
from __future__ import annotations

from datetime import date

import pytest

from tradex.research.daytrade_momentum.baseline import (
    build_baseline_pool,
    match_event_baselines,
)
from tradex.research.daytrade_momentum.models import BaselineObservation, EventObservation


def test_baseline_pool_indexing_isolation() -> None:
    """Verify baseline observations are partitioned strictly by (ticker, split, direction)."""
    d1 = date(2025, 1, 15)
    d2 = date(2025, 1, 16)

    obs1 = BaselineObservation(
        ticker="SPY", session_date=d1, direction="LONG", signal_return=0.005,
        threshold=0.015, entry_price=100.0, exit_price=101.0,
        gross_return=0.01, net_return_0bps=0.01, net_return_2bps=0.0096, net_return_5bps=0.009,
        split="development",
    )
    obs2 = BaselineObservation(
        ticker="SPY", session_date=d2, direction="SHORT", signal_return=-0.005,
        threshold=0.015, entry_price=100.0, exit_price=99.0,
        gross_return=0.01, net_return_0bps=0.01, net_return_2bps=0.0096, net_return_5bps=0.009,
        split="development",
    )
    obs3 = BaselineObservation(
        ticker="QQQ", session_date=d1, direction="LONG", signal_return=0.005,
        threshold=0.015, entry_price=200.0, exit_price=202.0,
        gross_return=0.01, net_return_0bps=0.01, net_return_2bps=0.0096, net_return_5bps=0.009,
        split="development",
    )
    obs4 = BaselineObservation(
        ticker="SPY", session_date=d1, direction="LONG", signal_return=0.005,
        threshold=0.015, entry_price=100.0, exit_price=101.0,
        gross_return=0.01, net_return_0bps=0.01, net_return_2bps=0.0096, net_return_5bps=0.009,
        split="validation",  # different split
    )

    pool = build_baseline_pool([obs1, obs2, obs3, obs4])

    assert len(pool[("SPY", "development", "LONG")]) == 1
    assert len(pool[("SPY", "development", "SHORT")]) == 1
    assert len(pool[("QQQ", "development", "LONG")]) == 1
    assert len(pool[("SPY", "validation", "LONG")]) == 1

    # Cross-split or cross-direction queries do not cross-contaminate
    assert len(pool.get(("SPY", "validation", "SHORT"), [])) == 0


def test_match_event_baselines_and_uplift() -> None:
    """Verify matched baseline mean return and event uplift calculation."""
    d = date(2025, 1, 15)

    ev = EventObservation(
        ticker="SPY", session_date=d, direction="LONG", signal_return=0.02,
        threshold=0.015, entry_time=d, exit_time=d, entry_price=100.0, exit_price=102.0,
        gross_return=0.02, net_return_0bps=0.02, net_return_2bps=0.0196, net_return_5bps=0.019,
        split="development",
    )

    # 2 baseline observations for SPY development LONG: net returns 0.0050 and 0.0070 (mean = 0.0060)
    ne1 = BaselineObservation(
        ticker="SPY", session_date=d, direction="LONG", signal_return=0.005,
        threshold=0.015, entry_price=100.0, exit_price=100.5,
        gross_return=0.0054, net_return_0bps=0.0054, net_return_2bps=0.0050, net_return_5bps=0.0044,
        split="development",
    )
    ne2 = BaselineObservation(
        ticker="SPY", session_date=d, direction="LONG", signal_return=0.007,
        threshold=0.015, entry_price=100.0, exit_price=100.7,
        gross_return=0.0074, net_return_0bps=0.0074, net_return_2bps=0.0070, net_return_5bps=0.0064,
        split="development",
    )

    pool = build_baseline_pool([ne1, ne2])
    match_event_baselines([ev], pool, friction_bps=2.0)

    assert ev.matched_baseline_net_2bps is not None
    assert pytest.approx(ev.matched_baseline_net_2bps) == 0.0060
    assert ev.uplift_net_2bps is not None
    # 0.0196 - 0.0060 = 0.0136
    assert pytest.approx(ev.uplift_net_2bps) == 0.0136


def test_empty_baseline_bucket_non_computable() -> None:
    """Verify empty baseline bucket sets matched baseline and uplift to None without substituting zero."""
    d = date(2025, 1, 15)
    ev = EventObservation(
        ticker="DIA", session_date=d, direction="SHORT", signal_return=-0.02,
        threshold=0.015, entry_time=d, exit_time=d, entry_price=100.0, exit_price=98.0,
        gross_return=0.02, net_return_0bps=0.02, net_return_2bps=0.0196, net_return_5bps=0.019,
        split="development",
    )

    # Empty pool
    pool: dict = {}
    match_event_baselines([ev], pool, friction_bps=2.0)

    assert ev.matched_baseline_net_2bps is None
    assert ev.uplift_net_2bps is None
