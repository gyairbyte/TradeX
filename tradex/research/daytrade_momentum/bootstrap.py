"""Deterministic session-date cluster bootstrap for primary net return and baseline uplift."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

import numpy as np

from .models import BaselineObservation, BootstrapCI, EventObservation

DEFAULT_BOOTSTRAP_RESAMPLES = 2000
DEFAULT_BOOTSTRAP_SEED = 20260926
DEFAULT_CONFIDENCE_LEVEL_PCT = 95.0


class BootstrapError(Exception):
    """Raised when cluster bootstrap input validation fails."""


def run_session_date_cluster_bootstrap(
    events: list[EventObservation],
    non_events: list[BaselineObservation],
    eligible_session_dates: list[date],
    *,
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    confidence_level_pct: float = DEFAULT_CONFIDENCE_LEVEL_PCT,
    friction_bps: float = 2.0,
) -> tuple[BootstrapCI, BootstrapCI]:
    """Execute deterministic cluster bootstrap by session_date.

    Simultaneously recomputes:
    1. Primary event mean net return (2 bps/side)
    2. Event-minus-baseline uplift (2 bps/side)

    Clarification 3 rules:
    - Cluster variable: session_date (all ETF observations on a date travel together);
    - Multiplicity preserved when a date is sampled more than once;
    - Baseline recomputed inside each replicate (never held fixed);
    - Computability is evaluated independently for primary return CI and uplift CI:
      - If event mean fails in any replicate: primary_ci becomes non_computable;
      - If baseline/uplift fails in any replicate: uplift_ci becomes non_computable,
        while primary_ci remains computable;
    - If any replicate cannot be computed:
      - do NOT substitute zero;
      - do NOT silently drop the replicate;
      - do NOT reduce denominator from 2,000;
      - set status to 'non_computable' and bounds to None.
    """
    if not eligible_session_dates:
        ci_fail = BootstrapCI(
            point_estimate=None,
            ci_lower=None,
            ci_upper=None,
            resamples=resamples,
            seed=seed,
            status="non_computable",
            error_reason="no_session_dates_available",
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

    # Calculate point estimates on original full sample
    full_event_rets = [e.net_return_2bps for e in events]
    point_est_primary = float(sum(full_event_rets) / float(len(full_event_rets)))

    uplifts_with_val = [e.uplift_net_2bps for e in events if e.uplift_net_2bps is not None]
    if len(uplifts_with_val) == len(events):
        point_est_uplift: float | None = float(sum(uplifts_with_val) / float(len(uplifts_with_val)))
    else:
        # At least one event in full sample has missing baseline -> point estimate is non-computable
        point_est_uplift = None

    # Group observations by cluster (session_date)
    events_by_date: dict[date, list[EventObservation]] = defaultdict(list)
    for e in events:
        events_by_date[e.session_date].append(e)

    non_events_by_date: dict[date, list[BaselineObservation]] = defaultdict(list)
    for ne in non_events:
        non_events_by_date[ne.session_date].append(ne)

    # Sort dates for deterministic indexing
    sorted_dates = sorted(set(eligible_session_dates))
    n_dates = len(sorted_dates)

    rng = np.random.default_rng(seed)
    sampled_indices = rng.integers(0, n_dates, size=(resamples, n_dates))

    primary_replicates: list[float | None] = []
    uplift_replicates: list[float | None] = []

    for b_idx in range(resamples):
        date_indices = sampled_indices[b_idx]

        # Count date multiplicity in this replicate
        date_counts: dict[date, int] = defaultdict(int)
        for idx in date_indices:
            date_counts[sorted_dates[idx]] += 1

        # Resample events and non-events preserving multiplicity and same-date grouping
        b_events: list[EventObservation] = []
        b_non_events: list[BaselineObservation] = []

        for s_date, count in date_counts.items():
            ev_list = events_by_date.get(s_date, [])
            for _ in range(count):
                b_events.extend(ev_list)

            ne_list = non_events_by_date.get(s_date, [])
            for _ in range(count):
                b_non_events.extend(ne_list)

        # 1. Primary event mean return for replicate
        if not b_events:
            primary_replicates.append(None)
            uplift_replicates.append(None)
            continue

        b_event_rets = [e.net_return_2bps for e in b_events]
        b_mean_primary = float(sum(b_event_rets) / float(len(b_event_rets)))
        primary_replicates.append(b_mean_primary)

        # 2. Rebuild direction-matched baseline pool for replicate
        # Key: (ticker, direction) -> list of net returns
        b_baseline_pool: dict[tuple[str, str], list[float]] = defaultdict(list)
        for ne in b_non_events:
            b_baseline_pool[(ne.ticker, ne.direction)].append(ne.net_return_2bps)

        # Recompute uplift for each resampled event
        b_uplifts: list[float] = []
        replicate_uplift_computable = True

        for ev in b_events:
            cand_rets = b_baseline_pool.get((ev.ticker, ev.direction), [])
            if not cand_rets:
                # Event has no matching non-event baseline in this replicate
                replicate_uplift_computable = False
                break
            base_ref = sum(cand_rets) / float(len(cand_rets))
            b_uplifts.append(ev.net_return_2bps - base_ref)

        if not replicate_uplift_computable or not b_uplifts:
            uplift_replicates.append(None)
        else:
            b_mean_uplift = float(sum(b_uplifts) / float(len(b_uplifts)))
            uplift_replicates.append(b_mean_uplift)

    alpha = (100.0 - confidence_level_pct) / 2.0

    # Evaluate Primary Return CI (Clarification 3)
    primary_none_count = sum(1 for r in primary_replicates if r is None)
    if primary_none_count > 0:
        primary_ci = BootstrapCI(
            point_estimate=point_est_primary,
            ci_lower=None,
            ci_upper=None,
            resamples=resamples,
            seed=seed,
            status="non_computable",
            error_reason=f"replicates_with_no_events_count_{primary_none_count}",
        )
    else:
        valid_prim = [float(r) for r in primary_replicates if r is not None]
        ci_lower = float(np.percentile(valid_prim, alpha))
        ci_upper = float(np.percentile(valid_prim, 100.0 - alpha))
        primary_ci = BootstrapCI(
            point_estimate=point_est_primary,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            resamples=resamples,
            seed=seed,
            status="computable",
            error_reason=None,
        )

    # Evaluate Uplift CI (Clarification 3: independent status from primary return CI)
    uplift_none_count = sum(1 for r in uplift_replicates if r is None)
    if point_est_uplift is None:
        uplift_ci = BootstrapCI(
            point_estimate=None,
            ci_lower=None,
            ci_upper=None,
            resamples=resamples,
            seed=seed,
            status="non_computable",
            error_reason="point_estimate_non_computable_due_to_empty_baseline",
        )
    elif uplift_none_count > 0:
        uplift_ci = BootstrapCI(
            point_estimate=point_est_uplift,
            ci_lower=None,
            ci_upper=None,
            resamples=resamples,
            seed=seed,
            status="non_computable",
            error_reason=f"replicates_with_empty_baseline_count_{uplift_none_count}",
        )
    else:
        valid_upl = [float(r) for r in uplift_replicates if r is not None]
        ci_lower = float(np.percentile(valid_upl, alpha))
        ci_upper = float(np.percentile(valid_upl, 100.0 - alpha))
        uplift_ci = BootstrapCI(
            point_estimate=point_est_uplift,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            resamples=resamples,
            seed=seed,
            status="computable",
            error_reason=None,
        )

    return primary_ci, uplift_ci
