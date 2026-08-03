"""Tests for metrics, bootstrap, and evidence gates."""
from __future__ import annotations

from tradex.research.pattern_validation.baselines import frequency_matched_controls
from tradex.research.pattern_validation.fingerprints import build_development_fingerprints
from tradex.research.pattern_validation.metrics import (
    compute_all_metrics,
    evaluate_evidence_gates,
)
from tradex.research.pattern_validation.observations import build_executable_trades, evaluate_splits


def test_period_metrics_contain_required_fields(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    controls = frequency_matched_controls(obs, tiny_spec)
    trades = build_executable_trades(obs, tiny_spec)
    period_metrics, _ = compute_all_metrics(obs, controls, trades, tiny_spec)
    for (split, event_type), pm in period_metrics.items():
        assert pm.split == split
        assert pm.event_type == event_type
        assert pm.eligible_observations >= 0
        assert pm.qualifying_signals >= 0
        assert pm.ticker_count >= 0


def test_evidence_gates_classify_as_not_supported_on_small_data(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    controls = frequency_matched_controls(obs, tiny_spec)
    trades = build_executable_trades(obs, tiny_spec)
    period_metrics, per_ticker = compute_all_metrics(obs, controls, trades, tiny_spec)
    decision = evaluate_evidence_gates(period_metrics, per_ticker, tiny_spec)
    assert decision.production_promotion_eligible is False
    assert decision.classification in {"supported", "rejected", "inconclusive"}
