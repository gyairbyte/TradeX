"""Deterministic tests for Journal domain models, immutability, and validation."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tradex.journal.models import (
    ExecutionProvenance,
    ExecutionProvenanceType,
    InvalidationRule,
    JournalEvent,
    JournalEventType,
    JournalOutcome,
    JournalState,
    JournalTrade,
    OutcomeConfidence,
    TradePlan,
)


def test_trade_plan_validation_and_immutability() -> None:
    now = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)
    rule = InvalidationRule(rule_id="r1", rule_version="v1", params={"bar_count": 5})

    plan = TradePlan(
        planned_entry=150.0,
        stop_price=145.0,
        target_price=165.0,
        expiration=now + timedelta(days=3),
        invalidation_rule=rule,
    )

    assert plan.planned_entry == 150.0
    assert plan.stop_price == 145.0
    assert plan.target_price == 165.0
    assert plan.invalidation_rule == rule

    # Immutability
    with pytest.raises(FrozenInstanceError):
        plan.planned_entry = 155.0  # type: ignore[misc]

    # Rejection of non-positive or non-finite numbers
    with pytest.raises(ValueError, match="strictly positive"):
        TradePlan(planned_entry=0.0)

    with pytest.raises(ValueError, match="strictly positive"):
        TradePlan(planned_entry=-10.0)

    with pytest.raises(ValueError, match="finite"):
        TradePlan(planned_entry=float("nan"))

    with pytest.raises(ValueError, match="finite"):
        TradePlan(planned_entry=float("inf"))

    # Rejection of invalid stop/target relations
    with pytest.raises(ValueError, match="strictly less than planned_entry"):
        TradePlan(planned_entry=100.0, stop_price=105.0)

    with pytest.raises(ValueError, match="strictly less than planned_entry"):
        TradePlan(planned_entry=100.0, stop_price=100.0)

    with pytest.raises(ValueError, match="strictly greater than planned_entry"):
        TradePlan(planned_entry=100.0, target_price=95.0)

    with pytest.raises(ValueError, match="strictly greater than planned_entry"):
        TradePlan(planned_entry=100.0, target_price=100.0)

    # Naive expiration datetime rejected
    with pytest.raises(ValueError, match="timezone-aware"):
        TradePlan(planned_entry=100.0, expiration=datetime(2026, 8, 20, 14, 0))  # noqa: DTZ001


def test_invalidation_rule_validation_and_immutability() -> None:
    rule = InvalidationRule(rule_id="gap_fill", rule_version="1.0", params={"level": 200.5})
    assert rule.rule_id == "gap_fill"
    assert rule.rule_version == "1.0"
    assert rule.params == {"level": 200.5}

    with pytest.raises(FrozenInstanceError):
        rule.rule_id = "new_rule"  # type: ignore[misc]

    with pytest.raises(ValueError, match="rule_id"):
        InvalidationRule(rule_id="", rule_version="1.0")

    with pytest.raises(ValueError, match="rule_version"):
        InvalidationRule(rule_id="r1", rule_version="  ")

    # Non-serializable NaN/Infinity in params rejected
    with pytest.raises(ValueError, match="without NaN/Infinity"):
        InvalidationRule(rule_id="r1", rule_version="1.0", params={"bad": float("nan")})


def test_execution_provenance_validation() -> None:
    now = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)

    # Manual provenance
    p_manual = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=now,
        observer="gary",
    )
    assert p_manual.execution_provenance == ExecutionProvenanceType.MANUAL
    assert p_manual.provider == "schwab"
    assert p_manual.observer == "gary"
    assert p_manual.simulation_rule is None

    # Missing provider normalized to "unknown"
    p_unknown_prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="",
        observed_at=now,
        observer="gary",
    )
    assert p_unknown_prov.provider == "unknown"

    # Simulated requires simulation_rule
    with pytest.raises(ValueError, match="simulation_rule"):
        ExecutionProvenance(
            execution_provenance=ExecutionProvenanceType.SIMULATED,
            provider="schwab",
            observed_at=now,
            observer="system",
            simulation_rule=None,
        )

    p_sim = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.SIMULATED,
        provider="schwab",
        observed_at=now,
        observer="system",
        simulation_rule="next_bar_open",
    )
    assert p_sim.simulation_rule == "next_bar_open"

    # Naive timestamp rejected
    with pytest.raises(ValueError, match="timezone-aware"):
        ExecutionProvenance(
            execution_provenance=ExecutionProvenanceType.MANUAL,
            provider="schwab",
            observed_at=datetime(2026, 8, 20, 14, 0),  # noqa: DTZ001
            observer="gary",
        )

    # Non-UTC aware datetime normalized to UTC
    ny_tz = ZoneInfo("America/New_York")
    ny_dt = datetime(2026, 8, 20, 10, 30, tzinfo=ny_tz)
    p_ny = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=ny_dt,
        observer="gary",
    )
    assert p_ny.observed_at.tzinfo == UTC
    assert p_ny.observed_at.hour == 14
    assert p_ny.observed_at.minute == 30


def test_journal_trade_model_validation() -> None:
    now = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)
    t = JournalTrade(
        journal_id="j-1",
        idempotency_key="idem-1",
        candidate_id="cand-1",
        strategy_id="strat-1",
        strategy_version="v1",
        decision_timestamp=now,
        plan_created_at=now,
        planned_entry=100.0,
        stop_price=95.0,
        target_price=110.0,
        created_at=now,
        updated_at=now,
    )
    assert t.state == JournalState.PLANNED
    assert t.plan.planned_entry == 100.0
    assert t.plan.stop_price == 95.0
    assert t.plan.target_price == 110.0

    # Decision timestamp cannot be after plan_created_at
    with pytest.raises(ValueError, match="cannot be after plan_created_at"):
        JournalTrade(
            journal_id="j-2",
            idempotency_key="idem-2",
            candidate_id="cand-1",
            strategy_id="strat-1",
            strategy_version="v1",
            decision_timestamp=now + timedelta(minutes=5),
            plan_created_at=now,
            planned_entry=100.0,
            created_at=now,
            updated_at=now,
        )

    # Open state requires fill_price, fill_timestamp, quantity
    with pytest.raises(ValueError, match="State 'open' requires"):
        JournalTrade(
            journal_id="j-3",
            idempotency_key="idem-3",
            candidate_id="cand-1",
            strategy_id="strat-1",
            strategy_version="v1",
            state=JournalState.OPEN,
            decision_timestamp=now,
            plan_created_at=now,
            planned_entry=100.0,
            created_at=now,
            updated_at=now,
        )


def test_journal_event_validation_and_immutability() -> None:
    now = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)
    event = JournalEvent(
        event_id="e-1",
        journal_id="j-1",
        seq=1,
        event_type=JournalEventType.CREATED,
        event_timestamp=now,
        recorded_at=now,
        payload={"note": "trade created"},
    )
    assert event.seq == 1
    assert event.event_type == JournalEventType.CREATED
    assert event.payload == {"note": "trade created"}

    with pytest.raises(FrozenInstanceError):
        event.seq = 2  # type: ignore[misc]

    with pytest.raises(ValueError, match="positive integer"):
        JournalEvent(
            event_id="e-2",
            journal_id="j-1",
            seq=0,
            event_type=JournalEventType.CREATED,
            event_timestamp=now,
        )


def test_journal_outcome_model_validation() -> None:
    now = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
    outcome = JournalOutcome(
        outcome_id="out-1",
        journal_id="j-1",
        computation_version="journal-outcome-v1",
        computed_at=now,
        source_event_seq=3,
        inputs_hash="abc123hash",
        entry_slippage=0.5,
        costs=5.0,
        gross_return_pct=10.0,
        net_return_pct=9.5,
        outcome_confidence=OutcomeConfidence.PROVISIONAL,
        inputs={"entry": 100.0},
    )
    assert outcome.outcome_id == "out-1"
    assert outcome.strategy_drawdown is None

    # strategy_drawdown must be None in R6 v1
    with pytest.raises(ValueError, match="strategy_drawdown is not supported in R6 v1"):
        JournalOutcome(
            outcome_id="out-2",
            journal_id="j-1",
            computation_version="journal-outcome-v1",
            computed_at=now,
            source_event_seq=3,
            inputs_hash="abc123hash",
            entry_slippage=0.5,
            costs=5.0,
            gross_return_pct=10.0,
            net_return_pct=9.5,
            outcome_confidence=OutcomeConfidence.PROVISIONAL,
            strategy_drawdown=0.05,
        )
