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
    selection = frequency_matched_controls(obs, tiny_spec)
    for c in selection.controls:
        assert c.is_qualifying is False
        assert c.outcome_status == "complete"


def test_frequency_matched_controls_deterministic(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    selection1 = frequency_matched_controls(obs, tiny_spec)
    selection2 = frequency_matched_controls(obs, tiny_spec)
    assert [o.ticker for o in selection1.controls] == [o.ticker for o in selection2.controls]
    assert [o.decision_date for o in selection1.controls] == [o.decision_date for o in selection2.controls]


def test_unconditional_baseline_includes_all_eligible(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    selection = unconditional_baseline_observations(obs, tiny_spec)
    assert len(selection.controls) >= len([o for o in obs if o.outcome_status == "complete"])


def test_baseline_returns_use_decision_slippage(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    selection = frequency_matched_controls(obs, tiny_spec)
    rets = compute_baseline_returns(selection.controls, tiny_spec.slippage_key(tiny_spec.decision_slippage_bps))
    assert all(isinstance(r, (int, float)) for r in rets)


def test_frequency_matched_controls_expose_audit_counts(tiny_bars, tiny_spec):
    fingerprints, _ = build_development_fingerprints(tiny_bars, tiny_spec)
    obs = evaluate_splits(tiny_bars, fingerprints, tiny_spec)
    selection = frequency_matched_controls(obs, tiny_spec)
    assert len(selection.audit) >= 0
    for audit in selection.audit:
        assert audit.selected <= audit.requested
        assert audit.selected <= audit.available
        assert audit.underfilled == (audit.requested > audit.available)


def test_frequency_matched_controls_zero_available_is_audited():
    """A group with qualifying signals and zero controls is recorded as underfilled."""
    from datetime import date

    from tradex.research.pattern_validation.models import Observation, Split, StudySpec

    signal = Observation(
        ticker="AAPL",
        split="validation",
        event_type="runup",
        decision_date=date(2021, 6, 1),
        signal_time=date(2021, 6, 1),
        similarity_score=80.0,
        series_scores={"price_pct": 80.0},
        is_qualifying=True,
        data_source="synthetic",
        signal_close=100.0,
        entry_date=date(2021, 6, 2),
        raw_entry_price=100.0,
        exit_date=date(2021, 6, 7),
        raw_exit_price=105.0,
        gross_return_pct=5.0,
        net_return_pct_by_slippage={"10": 4.9},
        outcome_status="complete",
    )
    spec = StudySpec(
        tickers=("AAPL",),
        provider="synthetic",
        start_date=date(2021, 1, 1),
        end_date=date(2021, 12, 31),
        splits={"validation": Split(date(2021, 1, 1), date(2021, 12, 31))},
        min_events=1,
        minimum_validation_signals=1,
        minimum_holdout_signals=1,
        minimum_tickers=1,
        research_test_mode=True,
    )
    selection = frequency_matched_controls([signal], spec)
    assert len(selection.audit) == 1
    audit = selection.audit[0]
    assert audit.requested == 1
    assert audit.available == 0
    assert audit.selected == 0
    assert audit.underfilled is True
    assert selection.underfilled_keys == [("AAPL", "validation", 2021, "runup")]


def test_frequency_matched_controls_underfill_marks_inconclusive():
    """When fewer non-signal observations exist than signals, the group is underfilled."""
    from datetime import date

    from tradex.research.pattern_validation.models import Observation

    # Create a group with 3 qualifying signals and only 1 non-qualifying control.
    base_obs = Observation(
        ticker="AAPL",
        split="validation",
        event_type="runup",
        decision_date=date(2021, 6, 1),
        signal_time=date(2021, 6, 1),
        similarity_score=80.0,
        series_scores={"price_pct": 80.0},
        is_qualifying=True,
        data_source="synthetic",
        signal_close=100.0,
        entry_date=date(2021, 6, 2),
        raw_entry_price=100.0,
        exit_date=date(2021, 6, 7),
        raw_exit_price=105.0,
        gross_return_pct=5.0,
        net_return_pct_by_slippage={"10": 4.9},
        outcome_status="complete",
    )
    controls = [
        Observation(
            ticker="AAPL",
            split="validation",
            event_type="runup",
            decision_date=date(2021, 6, 2 + i),
            signal_time=date(2021, 6, 2 + i),
            similarity_score=80.0,
            series_scores={"price_pct": 80.0},
            is_qualifying=True,
            data_source="synthetic",
            signal_close=100.0,
            entry_date=date(2021, 6, 3 + i),
            raw_entry_price=100.0,
            exit_date=date(2021, 6, 8 + i),
            raw_exit_price=105.0,
            gross_return_pct=5.0,
            net_return_pct_by_slippage={"10": 4.9},
            outcome_status="complete",
        )
        for i in range(3)
    ]
    non_signal = Observation(
        ticker="AAPL",
        split="validation",
        event_type="runup",
        decision_date=date(2021, 6, 10),
        signal_time=date(2021, 6, 10),
        similarity_score=30.0,
        series_scores={"price_pct": 30.0},
        is_qualifying=False,
        data_source="synthetic",
        signal_close=100.0,
        entry_date=date(2021, 6, 11),
        raw_entry_price=100.0,
        exit_date=date(2021, 6, 16),
        raw_exit_price=101.0,
        gross_return_pct=1.0,
        net_return_pct_by_slippage={"10": 0.9},
        outcome_status="complete",
    )
    from tradex.research.pattern_validation.models import Split, StudySpec
    spec = StudySpec(
        tickers=("AAPL",),
        provider="synthetic",
        start_date=date(2021, 1, 1),
        end_date=date(2021, 12, 31),
        splits={"validation": Split(date(2021, 1, 1), date(2021, 12, 31))},
        min_events=1,
        minimum_validation_signals=1,
        minimum_holdout_signals=1,
        minimum_tickers=1,
        research_test_mode=True,
    )
    selection = frequency_matched_controls([base_obs] + controls + [non_signal], spec)
    aapl_audits = [a for a in selection.audit if a.ticker == "AAPL" and a.split == "validation"]
    assert aapl_audits
    assert aapl_audits[0].requested == 4
    assert aapl_audits[0].available == 1
    assert aapl_audits[0].selected == 1
    assert aapl_audits[0].underfilled is True
