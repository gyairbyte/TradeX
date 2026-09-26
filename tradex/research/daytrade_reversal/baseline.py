"""Matched baseline pool construction and event-minus-baseline uplift."""
from __future__ import annotations

from collections import defaultdict

from .calendar import to_market_time
from .models import BaselineObservation, EventObservation


class BaselineError(Exception):
    """Raised when an illegal baseline operation or structure occurs."""


def build_baseline_pool(
    qualifying_non_events: list[BaselineObservation],
) -> dict[tuple[str, str, str], list[BaselineObservation]]:
    """Index qualifying non-event observations by (ticker, minute_of_day, split).

    Eligible baseline observations strictly satisfy:
    - same ticker;
    - same minute-of-day (HH:MM ET);
    - same dataset split;
    - non-event (events strictly excluded);
    - regular session eligibility;
    - ticker-session passed data-quality rules;
    - complete relevant forward horizon exists.
    """
    pool: dict[tuple[str, str, str], list[BaselineObservation]] = defaultdict(list)
    for obs in qualifying_non_events:
        key = (obs.ticker, obs.minute_of_day, obs.split)
        pool[key].append(obs)
    return pool


def match_event_baselines(
    events: list[EventObservation],
    baseline_pool: dict[tuple[str, str, str], list[BaselineObservation]],
    horizon: int = 1,
    friction_bps: float = 2.0,
) -> None:
    """Compute matched baseline reference return and uplift for each event in-place.

    For each event and horizon:
    baseline_reference_return = arithmetic mean of all qualifying non-event returns
                                for the same ticker + minute-of-day + split + horizon.
    event_uplift = event_return - baseline_reference_return.

    If an event has no qualifying baseline non-events, matched_baseline and uplift
    are explicitly set to None (non-computable).
    """
    for event in events:
        event_outcome = event.outcomes.get(horizon)
        if event_outcome is None:
            event.matched_baseline_1m_net = None
            event.uplift_1m_net = None
            continue

        local_time_str = to_market_time(event.event_bar_start).strftime("%H:%M")
        key = (event.ticker, local_time_str, event.split)
        candidates = baseline_pool.get(key, [])

        # Filter candidates that have valid outcome for horizon
        valid_candidate_rets: list[float] = []
        for cand in candidates:
            cand_outcome = cand.outcomes.get(horizon)
            if cand_outcome is not None:
                if friction_bps == 2.0:
                    valid_candidate_rets.append(cand_outcome.net_return_2bps)
                elif friction_bps == 0.0:
                    valid_candidate_rets.append(cand_outcome.net_return_0bps)
                elif friction_bps == 5.0:
                    valid_candidate_rets.append(cand_outcome.net_return_5bps)
                else:
                    valid_candidate_rets.append(cand_outcome.gross_return)

        if not valid_candidate_rets:
            # Expose explicitly as non-computable; do not substitute zero or other buckets
            event.matched_baseline_1m_net = None
            event.uplift_1m_net = None
        else:
            base_ref = sum(valid_candidate_rets) / float(len(valid_candidate_rets))
            if friction_bps == 2.0:
                ev_ret = event_outcome.net_return_2bps
            elif friction_bps == 0.0:
                ev_ret = event_outcome.net_return_0bps
            elif friction_bps == 5.0:
                ev_ret = event_outcome.net_return_5bps
            else:
                ev_ret = event_outcome.gross_return

            event.matched_baseline_1m_net = base_ref
            event.uplift_1m_net = ev_ret - base_ref
