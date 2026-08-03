"""Baseline generation for the pattern-similarity validation study."""
from __future__ import annotations

import random
from datetime import date
from typing import Any

from .models import Observation, StudySpec


def _group_key(obs: Observation) -> tuple[str, str, int, str]:
    """Group by ticker, split, calendar year, event_type."""
    return (obs.ticker, obs.split, obs.decision_date.year, obs.event_type)


def frequency_matched_controls(
    observations: list[Observation],
    spec: StudySpec,
) -> list[Observation]:
    """Select deterministic below-threshold controls matched to qualifying signals."""
    rng = random.Random(spec.random_seed)

    by_group: dict[tuple[str, str, int, str], list[Observation]] = {}
    for obs in observations:
        if obs.outcome_status != "complete":
            continue
        key = _group_key(obs)
        by_group.setdefault(key, []).append(obs)

    controls: list[Observation] = []
    for key, group in by_group.items():
        signals = [o for o in group if o.is_qualifying]
        non_signals = [o for o in group if not o.is_qualifying and o.outcome_status == "complete"]
        n = len(signals)
        if n == 0 or len(non_signals) == 0:
            continue
        # Deterministic selection without replacement and without reusing signal dates.
        non_signal_dates = {o.decision_date for o in non_signals}
        if len(non_signals) <= n:
            selected = non_signals
        else:
            # random.sample is deterministic given the seeded RNG order.
            selected = rng.sample(non_signals, n)
        controls.extend(selected)
    return controls


def unconditional_baseline_observations(
    observations: list[Observation],
    spec: StudySpec,
) -> list[Observation]:
    """All otherwise eligible (complete outcome) observations for the same ticker/split/event_type."""
    return [o for o in observations if o.outcome_status == "complete"]


def compute_baseline_returns(
    observations: list[Observation],
    slippage_key: str,
) -> list[float]:
    """Return list of signed net returns for the given slippage key."""
    return [o.net_return_pct_by_slippage[slippage_key] for o in observations
            if o.outcome_status == "complete" and o.net_return_pct_by_slippage.get(slippage_key) is not None]
