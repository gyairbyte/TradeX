"""Tests for session-date cluster bootstrap and metric-specific non-computability.

Enforces Clarification 3:
- Clustered by session_date: all ETF events/baselines on a session date travel together.
- Multiplicity preserved when a date is selected multiple times.
- Baseline recomputed inside each bootstrap replicate.
- Metric-specific non-computability:
  - primary_net_return_ci and uplift_ci evaluated independently;
  - uplift_ci can be non_computable (e.g. empty baseline bucket in a replicate) while primary_net_return_ci remains computable.
"""
from __future__ import annotations

from datetime import date

from tradex.research.daytrade_momentum.bootstrap import run_session_date_cluster_bootstrap
from tradex.research.daytrade_momentum.models import BaselineObservation, EventObservation


def test_cluster_bootstrap_travel_together_and_computable() -> None:
    """Verify cluster bootstrap when all replicates have computable events and baselines."""
    d1 = date(2025, 1, 15)
    d2 = date(2025, 1, 16)
    d3 = date(2025, 1, 17)

    # 3 dates, each has 1 event and 1 baseline for SPY LONG
    events = [
        EventObservation(
            ticker="SPY", session_date=d1, direction="LONG", signal_return=0.02,
            threshold=0.015, entry_time=d1, exit_time=d1, entry_price=100.0, exit_price=101.5,
            gross_return=0.015, net_return_0bps=0.015, net_return_2bps=0.0146, net_return_5bps=0.014,
            split="validation",
        ),
        EventObservation(
            ticker="SPY", session_date=d2, direction="LONG", signal_return=0.02,
            threshold=0.015, entry_time=d2, exit_time=d2, entry_price=100.0, exit_price=101.8,
            gross_return=0.018, net_return_0bps=0.018, net_return_2bps=0.0176, net_return_5bps=0.017,
            split="validation",
        ),
        EventObservation(
            ticker="SPY", session_date=d3, direction="LONG", signal_return=0.02,
            threshold=0.015, entry_time=d3, exit_time=d3, entry_price=100.0, exit_price=101.2,
            gross_return=0.012, net_return_0bps=0.012, net_return_2bps=0.0116, net_return_5bps=0.011,
            split="validation",
        ),
    ]

    non_events = [
        BaselineObservation(
            ticker="SPY", session_date=d1, direction="LONG", signal_return=0.005,
            threshold=0.015, entry_price=100.0, exit_price=100.5,
            gross_return=0.005, net_return_0bps=0.005, net_return_2bps=0.0046, net_return_5bps=0.004,
            split="validation",
        ),
        BaselineObservation(
            ticker="SPY", session_date=d2, direction="LONG", signal_return=0.005,
            threshold=0.015, entry_price=100.0, exit_price=100.4,
            gross_return=0.004, net_return_0bps=0.004, net_return_2bps=0.0036, net_return_5bps=0.003,
            split="validation",
        ),
        BaselineObservation(
            ticker="SPY", session_date=d3, direction="LONG", signal_return=0.005,
            threshold=0.015, entry_price=100.0, exit_price=100.6,
            gross_return=0.006, net_return_0bps=0.006, net_return_2bps=0.0056, net_return_5bps=0.005,
            split="validation",
        ),
    ]

    from tradex.research.daytrade_momentum.baseline import (
        build_baseline_pool,
        match_event_baselines,
    )
    pool = build_baseline_pool(non_events)
    match_event_baselines(events, pool)

    primary_ci, uplift_ci = run_session_date_cluster_bootstrap(
        events=events,
        non_events=non_events,
        eligible_session_dates=[d1, d2, d3],
        resamples=100,  # Fast test
        seed=20260926,
    )

    assert primary_ci.status == "computable"
    assert primary_ci.ci_lower is not None
    assert primary_ci.ci_upper is not None
    assert primary_ci.ci_lower <= primary_ci.point_estimate <= primary_ci.ci_upper

    assert uplift_ci.status == "computable"
    assert uplift_ci.ci_lower is not None
    assert uplift_ci.ci_upper is not None
    assert uplift_ci.ci_lower <= uplift_ci.point_estimate <= uplift_ci.ci_upper


def test_clarification3_metric_specific_non_computability() -> None:
    """Verify Clarification 3: primary CI can be computable while uplift CI is non_computable."""
    from tradex.research.daytrade_momentum.baseline import (
        build_baseline_pool,
        match_event_baselines,
    )
    d1 = date(2025, 1, 15)
    d2 = date(2025, 1, 16)

    # Date 1 has an event for SPY LONG
    ev1 = EventObservation(
        ticker="SPY", session_date=d1, direction="LONG", signal_return=0.02,
        threshold=0.015, entry_time=d1, exit_time=d1, entry_price=100.0, exit_price=101.5,
        gross_return=0.015, net_return_0bps=0.015, net_return_2bps=0.0146, net_return_5bps=0.014,
        split="validation",
    )
    # Date 2 has an event for SPY LONG
    ev2 = EventObservation(
        ticker="SPY", session_date=d2, direction="LONG", signal_return=0.02,
        threshold=0.015, entry_time=d2, exit_time=d2, entry_price=100.0, exit_price=101.8,
        gross_return=0.018, net_return_0bps=0.018, net_return_2bps=0.0176, net_return_5bps=0.017,
        split="validation",
    )

    # ONLY Date 1 has a baseline non-event for SPY LONG; Date 2 has NO non-events!
    # Whenever bootstrap samples only date 2 (e.g. resample draws [d2, d2]),
    # there are events (so primary return is computable), but zero baseline observations!
    # Hence uplift in that replicate is non-computable.
    ne1 = BaselineObservation(
        ticker="SPY", session_date=d1, direction="LONG", signal_return=0.005,
        threshold=0.015, entry_price=100.0, exit_price=100.5,
        gross_return=0.005, net_return_0bps=0.005, net_return_2bps=0.0046, net_return_5bps=0.004,
        split="validation",
    )

    # Match initial baselines (both ev1 and ev2 match to ne1 in full sample)
    pool = build_baseline_pool([ne1])
    match_event_baselines([ev1, ev2], pool)

    primary_ci, uplift_ci = run_session_date_cluster_bootstrap(
        events=[ev1, ev2],
        non_events=[ne1],
        eligible_session_dates=[d1, d2],
        resamples=100,
        seed=20260926,
    )

    # Primary CI is computable because every resample of [d1, d2] contains events
    assert primary_ci.status == "computable"
    assert primary_ci.ci_lower is not None

    # Uplift CI MUST be non_computable because some replicates draw only [d2, d2] where baseline is empty!
    assert uplift_ci.status == "non_computable"
    assert uplift_ci.ci_lower is None
    assert uplift_ci.ci_upper is None
    assert uplift_ci.error_reason is not None
