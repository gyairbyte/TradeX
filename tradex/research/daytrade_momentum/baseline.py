"""Direction-matched baseline pool construction and event-minus-baseline uplift."""
from __future__ import annotations

from collections import defaultdict

from .models import BaselineObservation, EventObservation


class BaselineError(Exception):
    """Raised when an illegal baseline operation or structure occurs."""


def build_baseline_pool(
    qualifying_non_events: list[BaselineObservation],
) -> dict[tuple[str, str, str], list[BaselineObservation]]:
    """Index qualifying non-event observations by (ticker, split, direction).

    Locked eligibility requirements:
    - same ticker;
    - same dataset split (prior-split observations are strictly excluded);
    - same first-half-hour direction ('LONG' or 'SHORT');
    - is_non_event (abs(first_half_hour_return) < threshold and != 0);
    - valid regular session with complete required timestamps (15:30 open, 15:59 close);
    - same execution interval (15:30 open -> 15:59 close) and friction.
    """
    pool: dict[tuple[str, str, str], list[BaselineObservation]] = defaultdict(list)
    for obs in qualifying_non_events:
        key = (obs.ticker, obs.split, obs.direction)
        pool[key].append(obs)
    return pool


def match_event_baselines(
    events: list[EventObservation],
    baseline_pool: dict[tuple[str, str, str], list[BaselineObservation]],
    friction_bps: float = 2.0,
) -> None:
    """Compute matched baseline reference return and uplift for each event in-place.

    Formula:
    baseline_reference_return = arithmetic mean of qualifying non-event net returns
                                for the same ticker + split + direction.
    uplift = event_net_return - baseline_reference_return.

    If an event has no qualifying baseline observations in its bucket:
    matched_baseline and uplift are set to None (non-computable).
    Never substitute zero or draw from other buckets/splits.
    """
    for event in events:
        key = (event.ticker, event.split, event.direction)
        candidates = baseline_pool.get(key, [])

        if not candidates:
            event.matched_baseline_net_2bps = None
            event.uplift_net_2bps = None
            continue

        if friction_bps == 2.0:
            cand_rets = [c.net_return_2bps for c in candidates]
            ev_ret = event.net_return_2bps
        elif friction_bps == 0.0:
            cand_rets = [c.net_return_0bps for c in candidates]
            ev_ret = event.net_return_0bps
        elif friction_bps == 5.0:
            cand_rets = [c.net_return_5bps for c in candidates]
            ev_ret = event.net_return_5bps
        else:
            cand_rets = [c.gross_return for c in candidates]
            ev_ret = event.gross_return

        base_ref = float(sum(cand_rets) / float(len(cand_rets)))
        event.matched_baseline_net_2bps = base_ref
        event.uplift_net_2bps = ev_ret - base_ref
