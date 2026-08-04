"""Tests for point-in-time similarity evaluation and execution simulation."""
from __future__ import annotations

import pandas as pd
import pytest

from tradex.research.pattern_validation.fingerprints import build_development_fingerprints
from tradex.research.pattern_validation.observations import (
    build_executable_trades,
    evaluate_splits,
    point_in_time_isolation_test,
)


def test_observations_are_point_in_time_isolated(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    assert obs
    # Pick a complete observation and truncate the future; similarity must not change.
    target = next(o for o in obs if o.outcome_status == "complete")
    full_df = tiny_bars[target.ticker].copy()
    full_df.index = pd.to_datetime(full_df.index)
    split = tiny_spec.splits[target.split]
    split_df = full_df[(full_df.index >= pd.Timestamp(split.start, tz="UTC")) & (full_df.index <= pd.Timestamp(split.end, tz="UTC"))]
    decision_idx = split_df.index.get_loc(pd.Timestamp(target.decision_date, tz="UTC"))
    truncated = split_df.iloc[: decision_idx + 6]  # keep enough to compute but hide later bars
    sim_truncated = point_in_time_isolation_test(truncated, fingerprints[target.event_type], tiny_spec, decision_idx, target.event_type)
    assert sim_truncated == pytest.approx(target.similarity_score, rel=1e-6)


def test_observations_record_forward_returns(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    complete = [o for o in obs if o.outcome_status == "complete"]
    assert complete
    for o in complete:
        assert o.gross_return_pct is not None
        assert "10" in o.net_return_pct_by_slippage
        assert "0" in o.net_return_pct_by_slippage


def test_executable_trades_are_non_overlapping(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    trades = build_executable_trades(obs, tiny_spec)
    by_key = {}
    for t in trades:
        key = (t.ticker, t.split, t.event_type)
        if key in by_key:
            prev = by_key[key]
            assert t.decision_date >= prev.exit_date
        by_key[key] = t
