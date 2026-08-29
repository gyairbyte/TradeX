"""Deterministic tests for Journal lifecycle service, authorization, candidate linkage, idempotency, and rollback."""
from __future__ import annotations

import math
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tradex.config import settings_from_mapping
from tradex.journal.models import (
    CandidateNotFoundError,
    ExecutionProvenance,
    ExecutionProvenanceType,
    ExitReason,
    IdempotencyConflictError,
    InvalidationRule,
    InvalidTransitionError,
    JournalEventType,
    JournalState,
    StrategyNotAuthorizedError,
    TradePlan,
)
from tradex.journal.service import (
    create_planned_trade,
    get_journal_history,
    get_journal_trade,
    recompute_outcomes,
    record_exit,
    record_fill,
    validate_strategy_authorization,
)
from tradex.journal.service import (
    list_journal_outcomes_query as list_journal_outcomes,
)
from tradex.strategies.registry import (
    APPROVED_PRODUCTION_STRATEGIES,
    ApprovedProductionStrategy,
)
from tradex.tracker import store


@pytest.fixture
def test_env(tmp_path: Path):
    db_path = str(tmp_path / "journal_service_test.db")
    store.init(db_path)
    settings = settings_from_mapping({"TRADEX_DB_PATH": db_path})

    # Seed candidate snapshot
    cand_ts = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)
    with store._conn(db_path=Path(db_path)) as con:
        con.execute(
            """
            INSERT INTO candidates (candidate_id, symbol, decision_timestamp, created_at)
            VALUES ('cand-101', 'AAPL', ?, ?)
            """,
            (cand_ts.isoformat(), cand_ts.isoformat()),
        )

    return {"db_path": db_path, "settings": settings, "cand_ts": cand_ts}


def test_strategy_authorization_fails_closed_when_registry_empty(test_env) -> None:
    # Committed registry is strictly empty
    assert APPROVED_PRODUCTION_STRATEGIES == ()

    with pytest.raises(StrategyNotAuthorizedError, match="not authorized for journal_execution"):
        validate_strategy_authorization("strat-alpha", "1.0.0")

    plan = TradePlan(planned_entry=100.0)
    with pytest.raises(StrategyNotAuthorizedError, match="not authorized for journal_execution"):
        create_planned_trade(
            candidate_id="cand-101",
            strategy_id="strat-alpha",
            strategy_version="1.0.0",
            decision_timestamp=test_env["cand_ts"],
            plan_created_at=test_env["cand_ts"],
            plan=plan,
            decided_by="gary",
            plan_source="manual",
            idempotency_key="key-1",
            settings=test_env["settings"],
        )


def test_strategy_identity_syntax_validation_before_registry_check() -> None:
    # Malformed / empty / invalid regex strategy identifiers raise ValueError/TypeError
    with pytest.raises(TypeError):
        validate_strategy_authorization(123, "1.0.0")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        validate_strategy_authorization("strat-alpha ", "1.0.0")

    with pytest.raises(ValueError, match="does not match required pattern"):
        validate_strategy_authorization("INVALID_UPPERCASE", "1.0.0")

    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        validate_strategy_authorization("strat-alpha", " 1.0.0")


def test_authorized_strategy_creates_planned_trade(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_strat = ApprovedProductionStrategy(
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        description="Approved long momentum strategy",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (auth_strat,),
    )

    t0 = test_env["cand_ts"]
    rule = InvalidationRule(rule_id="gap_fill", rule_version="1.0", params={"level": 95.0})
    plan = TradePlan(
        planned_entry=100.0,
        stop_price=95.0,
        target_price=115.0,
        expiration=t0 + timedelta(days=2),
        invalidation_rule=rule,
    )

    trade = create_planned_trade(
        candidate_id="cand-101",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0 + timedelta(minutes=1),
        plan=plan,
        decided_by="gary",
        plan_source="manual_entry",
        plan_provider="schwab",
        idempotency_key="idem-trade-1",
        settings=test_env["settings"],
    )

    assert trade.journal_id is not None
    assert trade.state == JournalState.PLANNED
    assert trade.candidate_id == "cand-101"
    assert trade.strategy_id == "long-momentum"
    assert trade.strategy_version == "1.0.0"
    assert trade.planned_entry == 100.0
    assert trade.stop_price == 95.0
    assert trade.target_price == 115.0

    # Verify event seq=1 was created
    events = get_journal_history(trade.journal_id, settings=test_env["settings"])
    assert len(events) == 1
    assert events[0].seq == 1
    assert events[0].event_type == JournalEventType.CREATED
    assert events[0].payload["decided_by"] == "gary"
    assert events[0].payload["plan_source"] == "manual_entry"
    assert events[0].payload["plan_provider"] == "schwab"


def test_candidate_linkage_and_pit_validation(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_strat = ApprovedProductionStrategy(
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        description="Approved",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (auth_strat,),
    )

    plan = TradePlan(planned_entry=100.0)

    # 1. Missing candidate -> CandidateNotFoundError
    with pytest.raises(CandidateNotFoundError, match="does not exist in store"):
        create_planned_trade(
            candidate_id="nonexistent-candidate",
            strategy_id="long-momentum",
            strategy_version="1.0.0",
            decision_timestamp=test_env["cand_ts"],
            plan_created_at=test_env["cand_ts"],
            plan=plan,
            decided_by="gary",
            plan_source="manual",
            idempotency_key="key-missing-cand",
            settings=test_env["settings"],
        )

    # 2. Candidate decision timestamp after journal decision timestamp -> ValueError (PIT ordering)
    with pytest.raises(ValueError, match="PIT ordering violated"):
        create_planned_trade(
            candidate_id="cand-101",
            strategy_id="long-momentum",
            strategy_version="1.0.0",
            decision_timestamp=test_env["cand_ts"] - timedelta(minutes=10),  # Before candidate
            plan_created_at=test_env["cand_ts"],
            plan=plan,
            decided_by="gary",
            plan_source="manual",
            idempotency_key="key-pit-violation",
            settings=test_env["settings"],
        )


def test_idempotency_exact_replay_and_conflict(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_strat = ApprovedProductionStrategy(
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        description="Approved",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (auth_strat,),
    )

    t0 = test_env["cand_ts"]
    plan = TradePlan(planned_entry=100.0, stop_price=95.0, target_price=115.0)

    # 1. First create call
    trade1 = create_planned_trade(
        candidate_id="cand-101",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=plan,
        decided_by="gary",
        plan_source="manual",
        plan_provider="schwab",
        idempotency_key="idem-key-abc",
        settings=test_env["settings"],
    )

    # 2. Exact replay with same key and same material payload -> returns identical trade
    trade2 = create_planned_trade(
        candidate_id="cand-101",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=plan,
        decided_by="gary",
        plan_source="manual",
        plan_provider="schwab",
        idempotency_key="idem-key-abc",
        settings=test_env["settings"],
    )
    assert trade1.journal_id == trade2.journal_id
    assert trade1 == trade2

    # 3. Divergent replay with same key -> IdempotencyConflictError
    diff_plan = TradePlan(planned_entry=105.0)
    with pytest.raises(IdempotencyConflictError, match="divergent material payload"):
        create_planned_trade(
            candidate_id="cand-101",
            strategy_id="long-momentum",
            strategy_version="1.0.0",
            decision_timestamp=t0,
            plan_created_at=t0,
            plan=diff_plan,
            decided_by="gary",
            plan_source="manual",
            plan_provider="schwab",
            idempotency_key="idem-key-abc",
            settings=test_env["settings"],
        )

    # 4. Duplicate (candidate_id, strategy_id, strategy_version) under different key -> IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError, match="already exists"):
        create_planned_trade(
            candidate_id="cand-101",
            strategy_id="long-momentum",
            strategy_version="1.0.0",
            decision_timestamp=t0,
            plan_created_at=t0,
            plan=plan,
            decided_by="gary",
            plan_source="manual",
            plan_provider="schwab",
            idempotency_key="diff-key-xyz",
            settings=test_env["settings"],
        )


def test_broker_confirmed_rejected_in_execution_mutations(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_strat = ApprovedProductionStrategy(
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        description="Approved",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (auth_strat,),
    )

    t0 = test_env["cand_ts"]
    trade = create_planned_trade(
        candidate_id="cand-101",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=TradePlan(planned_entry=100.0),
        decided_by="gary",
        plan_source="manual",
        idempotency_key="idem-key-broker-test",
        settings=test_env["settings"],
    )

    p_broker = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.BROKER_CONFIRMED,
        provider="schwab",
        observed_at=t0 + timedelta(minutes=5),
        observer="broker_gateway",
    )

    # Fill mutation rejects broker_confirmed
    with pytest.raises(InvalidTransitionError, match="broker_confirmed execution provenance is rejected"):
        record_fill(
            journal_id=trade.journal_id,
            fill_price=100.0,
            fill_timestamp=t0 + timedelta(minutes=5),
            fill_provenance=p_broker,
            quantity=100.0,
            settings=test_env["settings"],
        )


# ── Rollback & Transaction Integrity Tests (Amendment 4) ──────────────────────


def test_rollback_on_create_failure(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_strat = ApprovedProductionStrategy(
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        description="Approved",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (auth_strat,),
    )

    # Injected failure on event insert during create
    def failing_insert_event(con, event):
        raise sqlite3.OperationalError("injected event insert failure during create")

    monkeypatch.setattr("tradex.journal.service.insert_journal_event", failing_insert_event)

    t0 = test_env["cand_ts"]
    with pytest.raises(sqlite3.OperationalError, match="injected event insert failure"):
        create_planned_trade(
            candidate_id="cand-101",
            strategy_id="long-momentum",
            strategy_version="1.0.0",
            decision_timestamp=t0,
            plan_created_at=t0,
            plan=TradePlan(planned_entry=100.0),
            decided_by="gary",
            plan_source="manual",
            idempotency_key="idem-rollback-create",
            settings=test_env["settings"],
        )

    # Verify neither trade nor event was persisted
    with store._conn(db_path=Path(test_env["db_path"])) as con:
        assert con.execute("SELECT COUNT(*) FROM journal_trades").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM journal_events").fetchone()[0] == 0


def test_rollback_on_fill_failure(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_strat = ApprovedProductionStrategy(
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        description="Approved",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (auth_strat,),
    )

    t0 = test_env["cand_ts"]
    trade = create_planned_trade(
        candidate_id="cand-101",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=TradePlan(planned_entry=100.0),
        decided_by="gary",
        plan_source="manual",
        idempotency_key="idem-rollback-fill",
        settings=test_env["settings"],
    )

    # Injected failure on event insert during fill
    def failing_insert_event(con, event):
        raise sqlite3.OperationalError("injected event insert failure during fill")

    monkeypatch.setattr("tradex.journal.service.insert_journal_event", failing_insert_event)

    prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=t0 + timedelta(minutes=5),
        observer="gary",
    )

    with pytest.raises(sqlite3.OperationalError, match="injected event insert failure"):
        record_fill(
            journal_id=trade.journal_id,
            fill_price=100.0,
            fill_timestamp=t0 + timedelta(minutes=5),
            fill_provenance=prov,
            quantity=100.0,
            settings=test_env["settings"],
        )

    # Verify trade remains planned and only created event exists
    t_check = get_journal_trade(trade.journal_id, settings=test_env["settings"])
    assert t_check is not None
    assert t_check.state == JournalState.PLANNED
    assert t_check.fill_price is None

    events = get_journal_history(trade.journal_id, settings=test_env["settings"])
    assert len(events) == 1
    assert events[0].event_type == JournalEventType.CREATED


def test_rollback_on_exit_failure(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_strat = ApprovedProductionStrategy(
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        description="Approved",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (auth_strat,),
    )

    t0 = test_env["cand_ts"]
    trade = create_planned_trade(
        candidate_id="cand-101",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=TradePlan(planned_entry=100.0),
        decided_by="gary",
        plan_source="manual",
        idempotency_key="idem-rollback-exit",
        settings=test_env["settings"],
    )

    prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=t0 + timedelta(minutes=5),
        observer="gary",
    )
    record_fill(
        journal_id=trade.journal_id,
        fill_price=100.0,
        fill_timestamp=t0 + timedelta(minutes=5),
        fill_provenance=prov,
        quantity=100.0,
        settings=test_env["settings"],
    )

    # Injected failure on outcome insert during exit
    def failing_insert_outcome(con, outcome):
        raise sqlite3.OperationalError("injected outcome insert failure during exit")

    monkeypatch.setattr("tradex.journal.service.insert_journal_outcome", failing_insert_outcome)

    with pytest.raises(sqlite3.OperationalError, match="injected outcome insert failure"):
        record_exit(
            journal_id=trade.journal_id,
            exit_price=110.0,
            exit_timestamp=t0 + timedelta(hours=1),
            exit_reason=ExitReason.TARGET,
            exit_provenance=prov,
            costs=10.0,
            settings=test_env["settings"],
        )

    # Verify trade remains open, no exit event, and no outcomes row
    t_check = get_journal_trade(trade.journal_id, settings=test_env["settings"])
    assert t_check is not None
    assert t_check.state == JournalState.OPEN
    assert t_check.exit_price is None

    events = get_journal_history(trade.journal_id, settings=test_env["settings"])
    assert len(events) == 2
    assert [e.event_type for e in events] == [JournalEventType.CREATED, JournalEventType.FILLED]

    outcomes = list_journal_outcomes(trade.journal_id, settings=test_env["settings"])
    assert len(outcomes) == 0


def test_rollback_on_recompute_failure(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_strat = ApprovedProductionStrategy(
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        description="Approved",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (auth_strat,),
    )

    t0 = test_env["cand_ts"]
    trade = create_planned_trade(
        candidate_id="cand-101",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=TradePlan(planned_entry=100.0),
        decided_by="gary",
        plan_source="manual",
        idempotency_key="idem-rollback-recompute",
        settings=test_env["settings"],
    )
    prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=t0 + timedelta(minutes=5),
        observer="gary",
    )
    record_fill(
        journal_id=trade.journal_id,
        fill_price=100.0,
        fill_timestamp=t0 + timedelta(minutes=5),
        fill_provenance=prov,
        quantity=100.0,
        settings=test_env["settings"],
    )
    record_exit(
        journal_id=trade.journal_id,
        exit_price=110.0,
        exit_timestamp=t0 + timedelta(hours=1),
        exit_reason=ExitReason.TARGET,
        exit_provenance=prov,
        costs=10.0,
        settings=test_env["settings"],
    )

    outcomes_before = list_journal_outcomes(trade.journal_id, settings=test_env["settings"])
    assert len(outcomes_before) == 1

    # Injected failure on recompute insert
    def failing_insert_outcome(con, outcome):
        raise sqlite3.OperationalError("injected outcome insert failure during recompute")

    monkeypatch.setattr("tradex.journal.service.insert_journal_outcome", failing_insert_outcome)

    with pytest.raises(sqlite3.OperationalError, match="injected outcome insert failure"):
        recompute_outcomes(
            journal_id=trade.journal_id,
            computation_version="v2",
            settings=test_env["settings"],
        )

    outcomes_after = list_journal_outcomes(trade.journal_id, settings=test_env["settings"])
    assert len(outcomes_after) == 1
    assert outcomes_after[0].outcome_id == outcomes_before[0].outcome_id


# ── Persisted Cost Recomputation Test (Amendment 5) ──────────────────────────


def test_persisted_cost_recomputation(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_strat = ApprovedProductionStrategy(
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        description="Approved",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (auth_strat,),
    )

    t0 = test_env["cand_ts"]
    trade = create_planned_trade(
        candidate_id="cand-101",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=TradePlan(planned_entry=100.0),
        decided_by="gary",
        plan_source="manual",
        idempotency_key="idem-recompute-cost",
        settings=test_env["settings"],
    )
    prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=t0 + timedelta(minutes=5),
        observer="gary",
    )
    record_fill(
        journal_id=trade.journal_id,
        fill_price=100.0,
        fill_timestamp=t0 + timedelta(minutes=5),
        fill_provenance=prov,
        quantity=100.0,
        settings=test_env["settings"],
    )
    # Record exit with explicit costs = $15.0 ($0.15/share)
    record_exit(
        journal_id=trade.journal_id,
        exit_price=110.0,
        exit_timestamp=t0 + timedelta(hours=1),
        exit_reason=ExitReason.TARGET,
        exit_provenance=prov,
        costs=15.0,
        settings=test_env["settings"],
    )

    # Verify costs was persisted in the exited event payload
    events = get_journal_history(trade.journal_id, settings=test_env["settings"])
    exit_ev = next(e for e in events if e.event_type == JournalEventType.EXITED)
    assert exit_ev.payload["costs"] == 15.0

    # Delete existing outcome row directly to prove recompute reconstructs costs from the event
    with store._conn(db_path=Path(test_env["db_path"])) as con:
        con.execute("DELETE FROM journal_outcomes WHERE journal_id = ?", (trade.journal_id,))

    assert len(list_journal_outcomes(trade.journal_id, settings=test_env["settings"])) == 0

    # Recompute outcomes (without passing costs as a transient caller parameter)
    recomputed = recompute_outcomes(
        journal_id=trade.journal_id,
        computation_version="journal-outcome-recomputed-v1",
        settings=test_env["settings"],
    )

    assert recomputed.costs == 15.0
    assert recomputed.net_return_pct is not None
    # gross = 10.0%, net = (110 - 100 - 15/100)/100 * 100 = (10 - 0.15) = 9.85%
    assert math.isclose(recomputed.net_return_pct, 9.85)
    assert recomputed.computation_version == "journal-outcome-recomputed-v1"
