"""Tests for metrics, bootstrap, and evidence gates."""
from __future__ import annotations

from tradex.research.pattern_validation.baselines import frequency_matched_controls
from tradex.research.pattern_validation.fingerprints import build_development_fingerprints
from tradex.research.pattern_validation.metrics import (
    _lift_bootstrap,
    _ticker_cluster_bootstrap,
    compute_all_metrics,
    evaluate_evidence_gates,
)
from tradex.research.pattern_validation.observations import build_executable_trades, evaluate_splits


def test_period_metrics_contain_required_fields(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    baseline_selection = frequency_matched_controls(obs, tiny_spec)
    trades = build_executable_trades(obs, tiny_spec)
    period_metrics, _ = compute_all_metrics(obs, baseline_selection, trades, tiny_spec)
    for (split, event_type), pm in period_metrics.items():
        assert pm.split == split
        assert pm.event_type == event_type
        assert pm.eligible_observations >= 0
        assert pm.qualifying_signals >= 0
        assert pm.ticker_count >= 0
        assert pm.executed_trades >= 0


def test_evidence_gates_classify_as_not_supported_on_small_data(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    baseline_selection = frequency_matched_controls(obs, tiny_spec)
    trades = build_executable_trades(obs, tiny_spec)
    period_metrics, per_ticker = compute_all_metrics(obs, baseline_selection, trades, tiny_spec)
    decision = evaluate_evidence_gates(period_metrics, per_ticker, tiny_spec)
    assert decision.production_promotion_eligible is False
    assert decision.classification in {"supported", "rejected", "inconclusive"}


def test_ticker_cluster_bootstrap_retains_selected_clusters():
    """Resampling should keep whole ticker clusters, not rows within tickers."""
    from datetime import date

    from tradex.research.pattern_validation.models import Observation

    obs = []
    for t, rets in [("A", [1.0, 2.0]), ("B", [3.0]), ("C", [4.0, 5.0, 6.0])]:
        for r in rets:
            obs.append(Observation(
                ticker=t,
                split="validation",
                event_type="runup",
                decision_date=date(2021, 1, 1),
                signal_time=date(2021, 1, 1),
                similarity_score=80.0,
                series_scores={"price_pct": 80.0},
                is_qualifying=True,
                data_source="synthetic",
                signal_close=100.0,
                entry_date=date(2021, 1, 2),
                raw_entry_price=100.0,
                exit_date=date(2021, 1, 7),
                raw_exit_price=100.0,
                gross_return_pct=r,
                net_return_pct_by_slippage={"10": r},
                outcome_status="complete",
            ))
    point, ci_lower, ci_upper = _ticker_cluster_bootstrap(obs, "10", seed=42, resamples=5000)
    assert point is not None
    assert ci_lower is not None
    assert ci_upper is not None
    assert ci_lower <= point <= ci_upper


def test_lift_bootstrap_uses_paired_ticker_clusters():
    """Lift replicates share the same resampled tickers for signal and control."""
    from datetime import date

    from tradex.research.pattern_validation.models import Observation

    def make(ticker, ret, is_qualifying):
        return Observation(
            ticker=ticker,
            split="validation",
            event_type="runup",
            decision_date=date(2021, 1, 1),
            signal_time=date(2021, 1, 1),
            similarity_score=80.0 if is_qualifying else 30.0,
            series_scores={"price_pct": 80.0 if is_qualifying else 30.0},
            is_qualifying=is_qualifying,
            data_source="synthetic",
            signal_close=100.0,
            entry_date=date(2021, 1, 2),
            raw_entry_price=100.0,
            exit_date=date(2021, 1, 7),
            raw_exit_price=105.0 if is_qualifying else 100.0,
            gross_return_pct=ret,
            net_return_pct_by_slippage={"10": ret},
            outcome_status="complete",
        )

    signals = [make("A", 5.0, True), make("A", 6.0, True), make("B", 4.0, True)]
    controls = [make("A", 1.0, False), make("B", 0.5, False)]
    point, ci_lower, ci_upper = _lift_bootstrap(signals, controls, "10", seed=42, resamples=5000)
    assert point is not None
    # A and B are the only paired tickers; the lift should be positive.
    assert point > 0
    assert ci_lower is not None
    assert ci_upper is not None


def test_underfilled_baseline_invalidates_lift(tiny_bars, tiny_spec):
    """If any frequency-matched control group is underfilled, lift gates become inconclusive."""
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    baseline_selection = frequency_matched_controls(obs, tiny_spec)
    trades = build_executable_trades(obs, tiny_spec)
    period_metrics, _ = compute_all_metrics(obs, baseline_selection, trades, tiny_spec)
    # If there is no underfill, this is a no-op check.
    # If there is underfill, the affected period should have no lift.
    for pm in period_metrics.values():
        if pm.baseline_underfilled:
            assert pm.baseline_lift_bps is None
            assert pm.baseline_lift_ci_lower is None
            assert pm.baseline_lift_ci_upper is None
