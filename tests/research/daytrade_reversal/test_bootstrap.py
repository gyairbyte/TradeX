"""Deterministic cluster bootstrap tests."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from tradex.research.daytrade_reversal.bootstrap import run_joint_cluster_bootstrap
from tradex.research.daytrade_reversal.models import (
    BaselineObservation,
    EventObservation,
    HorizonOutcome,
)


def _dummy_outcome(gross: float) -> dict[int, HorizonOutcome]:
    return {
        1: HorizonOutcome(
            horizon_minutes=1,
            entry_time=datetime(2025, 7, 1, 14, 1, tzinfo=UTC),
            exit_time=datetime(2025, 7, 1, 14, 2, tzinfo=UTC),
            entry_price=100.0,
            exit_price=100.0 * (1.0 + gross),
            gross_return=gross,
            net_return_0bps=gross,
            net_return_2bps=gross - 0.0004,
            net_return_5bps=gross - 0.0010,
        )
    }


def test_deterministic_bootstrap_seed_reproducibility() -> None:
    """Bootstrap produces identical point estimates and CIs with seed 20260925."""
    clusters = [("AAPL", date(2025, 7, i)) for i in range(1, 21)]

    events: list[EventObservation] = []
    non_events: list[BaselineObservation] = []

    for i, cl in enumerate(clusters):
        # Event in every cluster
        ev = EventObservation(
            event_id=f"AAPL_{cl[1]}_1000",
            ticker="AAPL",
            session_date=cl[1],
            split="validation",
            event_bar_start=datetime(2025, 7, i + 1, 14, 0, tzinfo=UTC),
            event_available_at=datetime(2025, 7, i + 1, 14, 1, tzinfo=UTC),
            event_return=-0.03,
            threshold=-0.02,
            outcomes=_dummy_outcome(0.0050 + i * 0.0001),
            matched_baseline_1m_net=0.0010,
            uplift_1m_net=(0.0050 + i * 0.0001 - 0.0004) - 0.0010,
        )
        events.append(ev)

        # 3 non-events per cluster at 10:00
        for j in range(3):
            ne = BaselineObservation(
                ticker="AAPL",
                session_date=cl[1],
                split="validation",
                minute_of_day="10:00",
                bar_start=datetime(2025, 7, i + 1, 14, 0, tzinfo=UTC),
                available_at=datetime(2025, 7, i + 1, 14, 1, tzinfo=UTC),
                outcomes=_dummy_outcome(0.0010),
            )
            non_events.append(ne)

    ci_event1, ci_uplift1 = run_joint_cluster_bootstrap(
        events=events,
        non_events=non_events,
        all_clusters=clusters,
        resamples=200,  # Fast test resample count
        seed=20260925,
    )

    ci_event2, ci_uplift2 = run_joint_cluster_bootstrap(
        events=events,
        non_events=non_events,
        all_clusters=clusters,
        resamples=200,
        seed=20260925,
    )

    assert ci_event1.status == "computable"
    assert ci_uplift1.status == "computable"
    assert ci_event1.ci_lower == pytest.approx(ci_event2.ci_lower)
    assert ci_event1.ci_upper == pytest.approx(ci_event2.ci_upper)
    assert ci_uplift1.ci_lower == pytest.approx(ci_uplift2.ci_lower)
    assert ci_uplift1.ci_upper == pytest.approx(ci_uplift2.ci_upper)


def test_non_computable_bootstrap_fails_closed_without_dropping_replicate() -> None:
    """When a replicate cannot compute baseline uplift, bootstrap sets status to non_computable."""
    # Cluster 1 has an event at 10:00, but NO non-events exist anywhere in the sample for 10:00!
    cl1 = ("AAPL", date(2025, 7, 1))
    ev = EventObservation(
        event_id="AAPL_20250701_1000",
        ticker="AAPL",
        session_date=cl1[1],
        split="validation",
        event_bar_start=datetime(2025, 7, 1, 14, 0, tzinfo=UTC),
        event_available_at=datetime(2025, 7, 1, 14, 1, tzinfo=UTC),
        event_return=-0.03,
        threshold=-0.02,
        outcomes=_dummy_outcome(0.0050),
        matched_baseline_1m_net=None,
        uplift_1m_net=None,
    )

    ci_event, ci_uplift = run_joint_cluster_bootstrap(
        events=[ev],
        non_events=[],
        all_clusters=[cl1],
        resamples=100,
        seed=20260925,
    )

    # Must be non_computable, with None bounds and an explicit error reason
    assert ci_event.status == "non_computable"
    assert ci_uplift.status == "non_computable"
    assert ci_event.ci_lower is None
    assert ci_event.ci_upper is None
    assert ci_uplift.ci_lower is None
    assert ci_uplift.ci_upper is None
    assert ci_event.error_reason is not None
