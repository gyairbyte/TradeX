"""Deterministic joint cluster bootstrap for primary net return and baseline uplift."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

import numpy as np

from .calendar import to_market_time
from .models import BaselineObservation, BootstrapCI, EventObservation

DEFAULT_BOOTSTRAP_RESAMPLES = 2000
DEFAULT_BOOTSTRAP_SEED = 20260925
DEFAULT_CONFIDENCE_LEVEL_PCT = 95.0


class BootstrapError(Exception):
    """Raised when cluster bootstrap input validation fails."""


def run_joint_cluster_bootstrap(
    events: list[EventObservation],
    non_events: list[BaselineObservation],
    all_clusters: list[tuple[str, date]],
    *,
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    confidence_level_pct: float = DEFAULT_CONFIDENCE_LEVEL_PCT,
    horizon: int = 1,
) -> tuple[BootstrapCI, BootstrapCI]:
    """Execute deterministic cluster bootstrap by ticker-session.

    Simultaneously recomputes:
    1. Primary event mean net return (2 bps/side)
    2. Event-minus-baseline uplift (2 bps/side)

    Lock rules:
    - Cluster variable: (ticker, session_date)
    - Resamples: 2,000
    - Seed: 20260925
    - Baseline must never be held fixed while resampling events
    - If any replicate cannot be computed:
      - do NOT substitute zero;
      - do NOT silently drop the replicate;
      - do NOT reduce denominator from 2,000;
      - set CI status to 'non_computable' and bounds to None;
      - expose reason in error_reason.
    """
    if not all_clusters:
        ci_fail = BootstrapCI(
            point_estimate=None,
            ci_lower=None,
            ci_upper=None,
            resamples=resamples,
            seed=seed,
            status="non_computable",
            error_reason="no_clusters_available",
        )
        return ci_fail, ci_fail

    if not events:
        ci_fail = BootstrapCI(
            point_estimate=None,
            ci_lower=None,
            ci_upper=None,
            resamples=resamples,
            seed=seed,
            status="non_computable",
            error_reason="no_eligible_events_in_sample",
        )
        return ci_fail, ci_fail

    # Group original observations by cluster (ticker, session_date)
    events_by_cluster: dict[tuple[str, date], list[EventObservation]] = defaultdict(list)
    for e in events:
        events_by_cluster[(e.ticker, e.session_date)].append(e)

    non_events_by_cluster: dict[tuple[str, date], list[BaselineObservation]] = defaultdict(list)
    for ne in non_events:
        non_events_by_cluster[(ne.ticker, ne.session_date)].append(ne)

    # Calculate point estimates on original full sample
    full_event_rets = [
        e.outcomes[horizon].net_return_2bps
        for e in events
        if horizon in e.outcomes
    ]
    full_uplifts = [
        e.uplift_1m_net
        for e in events
        if e.uplift_1m_net is not None
    ]

    if not full_event_rets or len(full_uplifts) != len(events):
        # Point estimate itself is non-computable (e.g. missing baseline for an event in full sample)
        missing_count = len(events) - len(full_uplifts)
        ci_fail = BootstrapCI(
            point_estimate=None,
            ci_lower=None,
            ci_upper=None,
            resamples=resamples,
            seed=seed,
            status="non_computable",
            error_reason=f"full_sample_baseline_non_computable_missing_{missing_count}",
        )
        return ci_fail, ci_fail

    event_point_estimate = float(np.mean(full_event_rets))
    uplift_point_estimate = float(np.mean(full_uplifts))

    cluster_list = list(all_clusters)
    n_clusters = len(cluster_list)

    rng = np.random.default_rng(seed)

    event_means: list[float] = []
    uplift_means: list[float] = []

    alpha = (100.0 - confidence_level_pct) / 200.0
    lower_q = alpha
    upper_q = 1.0 - alpha

    for r in range(resamples):
        # Resample cluster indices with replacement
        sample_indices = rng.integers(0, n_clusters, size=n_clusters)

        # Gather resampled events and non-events
        resampled_events: list[EventObservation] = []
        # Index resampled non-events by (ticker, minute_of_day)
        resampled_non_events_pool: dict[tuple[str, str], list[float]] = defaultdict(list)

        for idx in sample_indices:
            cl = cluster_list[idx]
            resampled_events.extend(events_by_cluster.get(cl, []))
            for ne in non_events_by_cluster.get(cl, []):
                outcome = ne.outcomes.get(horizon)
                if outcome is not None:
                    resampled_non_events_pool[(ne.ticker, ne.minute_of_day)].append(
                        outcome.net_return_2bps
                    )

        if not resampled_events:
            # Replicate has 0 events; non-computable
            ci_fail = BootstrapCI(
                point_estimate=None,
                ci_lower=None,
                ci_upper=None,
                resamples=resamples,
                seed=seed,
                status="non_computable",
                error_reason=f"replicate_{r}_zero_events_drawn",
            )
            return ci_fail, ci_fail

        replicate_event_rets: list[float] = []
        replicate_uplifts: list[float] = []
        replicate_failed = False
        replicate_fail_reason = ""

        for ev in resampled_events:
            ev_outcome = ev.outcomes.get(horizon)
            if ev_outcome is None:
                replicate_failed = True
                replicate_fail_reason = f"replicate_{r}_event_missing_horizon_{horizon}"
                break

            ev_net = ev_outcome.net_return_2bps
            replicate_event_rets.append(ev_net)

            local_min = to_market_time(ev.event_bar_start).strftime("%H:%M")
            pool_key = (ev.ticker, local_min)
            base_rets = resampled_non_events_pool.get(pool_key, [])

            if not base_rets:
                # Replicate cannot compute baseline uplift for this event!
                replicate_failed = True
                replicate_fail_reason = (
                    f"replicate_{r}_empty_baseline_for_{ev.ticker}_{local_min}"
                )
                break

            base_ref = sum(base_rets) / float(len(base_rets))
            replicate_uplifts.append(ev_net - base_ref)

        if replicate_failed:
            ci_fail = BootstrapCI(
                point_estimate=None,
                ci_lower=None,
                ci_upper=None,
                resamples=resamples,
                seed=seed,
                status="non_computable",
                error_reason=replicate_fail_reason,
            )
            return ci_fail, ci_fail

        event_means.append(float(np.mean(replicate_event_rets)))
        uplift_means.append(float(np.mean(replicate_uplifts)))

    # Compute two-sided percentile bounds using deterministic linear method
    event_ci_lower = float(np.quantile(event_means, q=lower_q, method="linear"))
    event_ci_upper = float(np.quantile(event_means, q=upper_q, method="linear"))

    uplift_ci_lower = float(np.quantile(uplift_means, q=lower_q, method="linear"))
    uplift_ci_upper = float(np.quantile(uplift_means, q=upper_q, method="linear"))

    event_ci = BootstrapCI(
        point_estimate=event_point_estimate,
        ci_lower=event_ci_lower,
        ci_upper=event_ci_upper,
        resamples=resamples,
        seed=seed,
        status="computable",
        error_reason=None,
    )

    uplift_ci = BootstrapCI(
        point_estimate=uplift_point_estimate,
        ci_lower=uplift_ci_lower,
        ci_upper=uplift_ci_upper,
        resamples=resamples,
        seed=seed,
        status="computable",
        error_reason=None,
    )

    return event_ci, uplift_ci
