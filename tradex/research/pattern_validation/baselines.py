"""Baseline generation for the pattern-similarity validation study."""
from __future__ import annotations

import random

from .models import BaselineSelection, ControlAudit, Observation, StudySpec


def _group_key(obs: Observation) -> tuple[str, str, int, str]:
    """Group by ticker, split, calendar year, event_type."""
    return (obs.ticker, obs.split, obs.decision_date.year, obs.event_type)


def frequency_matched_controls(
    observations: list[Observation],
    spec: StudySpec,
) -> BaselineSelection:
    """Select deterministic below-threshold controls matched to qualifying signals.

    For each (ticker, split, year, event_type) group, this selects the same number
    of non-qualifying complete observations as qualifying signals. If fewer
    non-qualifying observations are available than requested, the group is
    marked ``underfilled`` and all available controls are used, but the resulting
    lift for that split/event type is intentionally invalidated.
    """
    rng = random.Random(spec.random_seed)

    by_group: dict[tuple[str, str, int, str], list[Observation]] = {}
    for obs in observations:
        if obs.outcome_status != "complete":
            continue
        key = _group_key(obs)
        by_group.setdefault(key, []).append(obs)

    controls: list[Observation] = []
    audit: list[ControlAudit] = []
    underfilled_keys: list[tuple[str, str, int, str]] = []

    for key, group in sorted(by_group.items()):
        signals = [o for o in group if o.is_qualifying]
        non_signals = [o for o in group if not o.is_qualifying and o.outcome_status == "complete"]
        n = len(signals)
        requested = n
        available = len(non_signals)
        selected: list[Observation] = []
        underfilled = False
        if n == 0 or available == 0:
            continue
        if available <= n:
            selected = non_signals
            if available < n:
                underfilled = True
                underfilled_keys.append(key)
        else:
            # random.sample is deterministic given the seeded RNG order.
            selected = rng.sample(non_signals, n)
        controls.extend(selected)
        audit.append(ControlAudit(
            ticker=key[0],
            split=key[1],
            year=key[2],
            event_type=key[3],
            requested=requested,
            available=available,
            selected=len(selected),
            underfilled=underfilled,
        ))

    return BaselineSelection(
        controls=controls,
        audit=audit,
        underfilled_keys=underfilled_keys,
    )


def unconditional_baseline_observations(
    observations: list[Observation],
    spec: StudySpec,
) -> BaselineSelection:
    """All otherwise eligible (complete outcome) observations for the same ticker/split/event_type."""
    _ = spec  # spec reserved for future filtering
    return BaselineSelection(controls=[o for o in observations if o.outcome_status == "complete"])


def compute_baseline_returns(
    observations: list[Observation],
    slippage_key: str,
) -> list[float]:
    """Return list of signed net returns for the given slippage key."""
    return [o.net_return_pct_by_slippage[slippage_key] for o in observations
            if o.outcome_status == "complete" and o.net_return_pct_by_slippage.get(slippage_key) is not None]
