"""Deterministic tests for Journal persistence store primitives and deterministic read ordering."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from tradex.journal.models import (
    ExecutionProvenance,
    ExecutionProvenanceType,
    ExitReason,
    InvalidationRule,
    JournalEvent,
    JournalEventType,
    JournalOutcome,
    JournalState,
    JournalTrade,
    OutcomeConfidence,
)
from tradex.journal.store import (
    get_journal_events,
    get_journal_trade_by_candidate_strategy,
    get_journal_trade_by_id,
    get_journal_trade_by_idempotency_key,
    get_latest_event_seq,
    get_latest_journal_outcome,
    insert_journal_event,
    insert_journal_outcome,
    insert_journal_trade,
    list_journal_outcomes,
    list_journal_trades,
    update_journal_trade,
)
from tradex.tracker import store


@pytest.fixture
def journal_db(tmp_path) -> sqlite3.Connection:
    db_path = str(tmp_path / "journal_test.db")
    store.init(db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")

    # Seed candidates
    con.execute(
        """
        INSERT INTO candidates (candidate_id, symbol, decision_timestamp, created_at)
        VALUES ('cand-001', 'AAPL', '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z')
        """
    )
    con.execute(
        """
        INSERT INTO candidates (candidate_id, symbol, decision_timestamp, created_at)
        VALUES ('cand-002', 'MSFT', '2026-08-20T14:00:00Z', '2026-08-20T14:00:00Z')
        """
    )
    con.commit()
    yield con
    con.close()


def test_insert_and_get_journal_trade(journal_db) -> None:
    now = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)
    rule = InvalidationRule(rule_id="r1", rule_version="v1", params={"thresh": 50})
    trade = JournalTrade(
        journal_id="j-100",
        idempotency_key="idem-100",
        candidate_id="cand-001",
        strategy_id="strat-alpha",
        strategy_version="1.0.0",
        side="long",
        state=JournalState.PLANNED,
        decision_timestamp=now,
        plan_created_at=now,
        planned_entry=150.0,
        stop_price=140.0,
        target_price=170.0,
        expiration=now + timedelta(days=2),
        invalidation_rule=rule,
        created_at=now,
        updated_at=now,
    )

    insert_journal_trade(journal_db, trade)

    # Query by ID
    fetched = get_journal_trade_by_id(journal_db, "j-100")
    assert fetched is not None
    assert fetched.journal_id == "j-100"
    assert fetched.candidate_id == "cand-001"
    assert fetched.strategy_id == "strat-alpha"
    assert fetched.strategy_version == "1.0.0"
    assert fetched.planned_entry == 150.0
    assert fetched.stop_price == 140.0
    assert fetched.target_price == 170.0
    assert fetched.invalidation_rule == rule

    # Query by idempotency key
    fetched_idem = get_journal_trade_by_idempotency_key(journal_db, "idem-100")
    assert fetched_idem == fetched

    # Query by candidate + strategy
    fetched_cand_strat = get_journal_trade_by_candidate_strategy(
        journal_db, "cand-001", "strat-alpha", "1.0.0"
    )
    assert fetched_cand_strat == fetched


def test_update_journal_trade_to_open_and_closed(journal_db) -> None:
    now = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)
    t0 = JournalTrade(
        journal_id="j-200",
        idempotency_key="idem-200",
        candidate_id="cand-001",
        strategy_id="strat-alpha",
        strategy_version="1.0.0",
        decision_timestamp=now,
        plan_created_at=now,
        planned_entry=100.0,
        created_at=now,
        updated_at=now,
    )
    insert_journal_trade(journal_db, t0)

    # Update to OPEN
    fill_time = now + timedelta(minutes=15)
    fill_prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=fill_time,
        observer="gary",
    )
    t_open = JournalTrade(
        journal_id=t0.journal_id,
        idempotency_key=t0.idempotency_key,
        candidate_id=t0.candidate_id,
        strategy_id=t0.strategy_id,
        strategy_version=t0.strategy_version,
        decision_timestamp=t0.decision_timestamp,
        plan_created_at=t0.plan_created_at,
        planned_entry=t0.planned_entry,
        state=JournalState.OPEN,
        quantity=100.0,
        fill_price=100.5,
        fill_timestamp=fill_time,
        fill_provenance=fill_prov,
        created_at=t0.created_at,
        updated_at=fill_time,
    )
    update_journal_trade(journal_db, t_open)

    fetched_open = get_journal_trade_by_id(journal_db, "j-200")
    assert fetched_open is not None
    assert fetched_open.state == JournalState.OPEN
    assert fetched_open.quantity == 100.0
    assert fetched_open.fill_price == 100.5
    assert fetched_open.fill_provenance == fill_prov

    # Update to CLOSED
    exit_time = now + timedelta(hours=2)
    exit_prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=exit_time,
        observer="gary",
    )
    t_closed = JournalTrade(
        journal_id=t0.journal_id,
        idempotency_key=t0.idempotency_key,
        candidate_id=t0.candidate_id,
        strategy_id=t0.strategy_id,
        strategy_version=t0.strategy_version,
        decision_timestamp=t0.decision_timestamp,
        plan_created_at=t0.plan_created_at,
        planned_entry=t0.planned_entry,
        state=JournalState.CLOSED,
        quantity=100.0,
        fill_price=100.5,
        fill_timestamp=fill_time,
        fill_provenance=fill_prov,
        exit_price=110.0,
        exit_timestamp=exit_time,
        exit_reason=ExitReason.TARGET,
        exit_provenance=exit_prov,
        created_at=t0.created_at,
        updated_at=exit_time,
    )
    update_journal_trade(journal_db, t_closed)

    fetched_closed = get_journal_trade_by_id(journal_db, "j-200")
    assert fetched_closed is not None
    assert fetched_closed.state == JournalState.CLOSED
    assert fetched_closed.exit_price == 110.0
    assert fetched_closed.exit_reason == ExitReason.TARGET


def test_deterministic_trade_ordering(journal_db) -> None:
    t0 = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)

    # Insert trades with different plan_created_at timestamps and tied timestamps
    trades = [
        JournalTrade(
            journal_id="j-b",
            idempotency_key="k-b",
            candidate_id="cand-001",
            strategy_id="strat-1",
            strategy_version="1.0.0",
            decision_timestamp=t0,
            plan_created_at=t0 + timedelta(minutes=10),
            planned_entry=100.0,
            created_at=t0,
            updated_at=t0,
        ),
        JournalTrade(
            journal_id="j-a",
            idempotency_key="k-a",
            candidate_id="cand-002",
            strategy_id="strat-1",
            strategy_version="1.0.0",
            decision_timestamp=t0,
            plan_created_at=t0 + timedelta(minutes=10),  # Tied plan_created_at with j-b
            planned_entry=200.0,
            created_at=t0,
            updated_at=t0,
        ),
        JournalTrade(
            journal_id="j-c",
            idempotency_key="k-c",
            candidate_id="cand-001",
            strategy_id="strat-2",
            strategy_version="1.0.0",
            decision_timestamp=t0,
            plan_created_at=t0 + timedelta(minutes=5),  # Earlier timestamp
            planned_entry=300.0,
            created_at=t0,
            updated_at=t0,
        ),
    ]

    for t in trades:
        insert_journal_trade(journal_db, t)

    ordered = list_journal_trades(journal_db)
    # Expected ordering: plan_created_at DESC, journal_id ASC
    # j-a and j-b share t0+10m -> j-a comes before j-b; j-c has t0+5m -> last
    assert [t.journal_id for t in ordered] == ["j-a", "j-b", "j-c"]


def test_events_and_outcomes_persistence_and_ordering(journal_db) -> None:
    now = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)
    t = JournalTrade(
        journal_id="j-300",
        idempotency_key="idem-300",
        candidate_id="cand-001",
        strategy_id="strat-1",
        strategy_version="1.0.0",
        decision_timestamp=now,
        plan_created_at=now,
        planned_entry=100.0,
        created_at=now,
        updated_at=now,
    )
    insert_journal_trade(journal_db, t)

    # Insert events in sequence
    e1 = JournalEvent(
        event_id="e-1",
        journal_id="j-300",
        seq=1,
        event_type=JournalEventType.CREATED,
        event_timestamp=now,
        recorded_at=now,
        payload={"note": "created"},
    )
    e2 = JournalEvent(
        event_id="e-2",
        journal_id="j-300",
        seq=2,
        event_type=JournalEventType.FILLED,
        event_timestamp=now + timedelta(minutes=5),
        recorded_at=now + timedelta(minutes=5),
        payload={"fill_price": 100.0},
    )
    insert_journal_event(journal_db, e1)
    insert_journal_event(journal_db, e2)

    events = get_journal_events(journal_db, "j-300")
    assert len(events) == 2
    assert [e.seq for e in events] == [1, 2]
    assert get_latest_event_seq(journal_db, "j-300") == 2

    # Insert outcomes
    o1 = JournalOutcome(
        outcome_id="out-1",
        journal_id="j-300",
        computation_version="v1",
        computed_at=now + timedelta(minutes=10),
        source_event_seq=2,
        inputs_hash="hash1",
        entry_slippage=0.0,
        costs=5.0,
        gross_return_pct=5.0,
        net_return_pct=4.5,
        outcome_confidence=OutcomeConfidence.PROVISIONAL,
    )
    o2 = JournalOutcome(
        outcome_id="out-2",
        journal_id="j-300",
        computation_version="v2",
        computed_at=now + timedelta(minutes=15),  # Later computed_at
        source_event_seq=2,
        inputs_hash="hash2",
        entry_slippage=0.0,
        costs=5.0,
        gross_return_pct=5.0,
        net_return_pct=4.5,
        outcome_confidence=OutcomeConfidence.PROVISIONAL,
    )
    insert_journal_outcome(journal_db, o1)
    insert_journal_outcome(journal_db, o2)

    outcomes = list_journal_outcomes(journal_db, "j-300")
    # Ordered by computed_at DESC, outcome_id ASC -> o2 first, then o1
    assert [o.outcome_id for o in outcomes] == ["out-2", "out-1"]

    latest = get_latest_journal_outcome(journal_db, "j-300")
    assert latest is not None
    assert latest.outcome_id == "out-2"
