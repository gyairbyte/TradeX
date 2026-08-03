"""Tests for frequency-matched and unconditional baselines."""
from __future__ import annotations

from tradex.research.pattern_validation.baselines import (
    compute_baseline_returns,
    frequency_matched_controls,
    unconditional_baseline_observations,
)
from tradex.research.pattern_validation.fingerprints import build_development_fingerprints
from tradex.research.pattern_validation.observations import evaluate_splits


def test_frequency_matched_controls_are_below_threshold(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    controls = frequency_matched_controls(obs, tiny_spec)
    for c in controls:
        assert c.is_qualifying is False
        assert c.outcome_status == "complete"


def test_frequency_matched_controls_deterministic(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    controls1 = frequency_matched_controls(obs, tiny_spec)
    controls2 = frequency_matched_controls(obs, tiny_spec)
    assert [o.ticker for o in controls1] == [o.ticker for o in controls2]
    assert [o.decision_date for o in controls1] == [o.decision_date for o in controls2]


def test_unconditional_baseline_includes_all_eligible(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    base = unconditional_baseline_observations(obs, tiny_spec)
    assert len(base) >= len([o for o in obs if o.outcome_status == "complete"])


def test_baseline_returns_use_decision_slippage(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    controls = frequency_matched_controls(obs, tiny_spec)
    rets = compute_baseline_returns(controls, tiny_spec.slippage_key(tiny_spec.decision_slippage_bps))
    assert all(isinstance(r, (int, float)) for r in rets)
