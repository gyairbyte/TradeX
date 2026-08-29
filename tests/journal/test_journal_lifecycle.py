"""Deterministic lifecycle state machine and transition matrix tests for Journal."""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tradex.config import settings_from_mapping
from tradex.journal.models import (
    ConflictingExitError,
    ConflictingFillError,
    ExecutionProvenance,
    ExecutionProvenanceType,
    ExitReason,
    InvalidTransitionError,
    JournalEventType,
    JournalState,
    StrategyNotAuthorizedError,
    TradePlan,
)
from tradex.journal.service import (
    cancel_trade,
    create_planned_trade,
    expire_trade,
    get_journal_history,
    invalidate_trade,
    record_exit,
    record_fill,
)
from tradex.strategies.registry import (
    ApprovedProductionStrategy,
)
from tradex.tracker import store


@pytest.fixture
def test_env(tmp_path: Path):
    db_path = str(tmp_path / "journal_lifecycle_test.db")
    store.init(db_path)
    settings = settings_from_mapping({"TRADEX_DB_PATH": db_path})

    cand_ts = datetime(2026, 8, 20, 14, 0, tzinfo=UTC)
    with store._conn(db_path=Path(db_path)) as con:
        con.execute(
            """
            INSERT INTO candidates (candidate_id, symbol, decision_timestamp, created_at)
            VALUES ('cand-201', 'AAPL', ?, ?)
            """,
            (cand_ts.isoformat(), cand_ts.isoformat()),
        )

    return {"db_path": db_path, "settings": settings, "cand_ts": cand_ts}


def test_standard_lifecycle_planned_open_closed(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
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

    # 1. Create planned
    trade = create_planned_trade(
        candidate_id="cand-201",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=plan,
        decided_by="gary",
        plan_source="manual",
        idempotency_key="key-lifecycle-1",
        settings=test_env["settings"],
    )
    assert trade.state == JournalState.PLANNED

    # 2. Record fill -> open
    fill_time = t0 + timedelta(minutes=10)
    fill_prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=fill_time,
        observer="gary",
    )
    trade_open = record_fill(
        journal_id=trade.journal_id,
        fill_price=100.2,
        fill_timestamp=fill_time,
        fill_provenance=fill_prov,
        quantity=100.0,
        settings=test_env["settings"],
    )
    assert trade_open.state == JournalState.OPEN
    assert math.isclose(trade_open.fill_price, 100.2)

    # Idempotent fill repeat
    trade_open_repeat = record_fill(
        journal_id=trade.journal_id,
        fill_price=100.2,
        fill_timestamp=fill_time,
        fill_provenance=fill_prov,
        quantity=100.0,
        settings=test_env["settings"],
    )
    assert trade_open_repeat == trade_open

    # Conflicting fill raises ConflictingFillError
    with pytest.raises(ConflictingFillError):
        record_fill(
            journal_id=trade.journal_id,
            fill_price=105.0,  # Divergent price
            fill_timestamp=fill_time,
            fill_provenance=fill_prov,
            quantity=100.0,
            settings=test_env["settings"],
        )

    # 3. Record exit -> closed
    exit_time = t0 + timedelta(hours=2)
    exit_prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=exit_time,
        observer="gary",
    )
    trade_closed = record_exit(
        journal_id=trade.journal_id,
        exit_price=112.0,
        exit_timestamp=exit_time,
        exit_reason=ExitReason.TARGET,
        exit_provenance=exit_prov,
        costs=5.0,
        settings=test_env["settings"],
    )
    assert trade_closed.state == JournalState.CLOSED
    assert math.isclose(trade_closed.exit_price, 112.0)
    assert trade_closed.exit_reason == ExitReason.TARGET

    # Idempotent exit repeat
    trade_closed_repeat = record_exit(
        journal_id=trade.journal_id,
        exit_price=112.0,
        exit_timestamp=exit_time,
        exit_reason=ExitReason.TARGET,
        exit_provenance=exit_prov,
        costs=5.0,
        settings=test_env["settings"],
    )
    assert trade_closed_repeat == trade_closed

    # Conflicting exit raises ConflictingExitError
    with pytest.raises(ConflictingExitError):
        record_exit(
            journal_id=trade.journal_id,
            exit_price=115.0,  # Divergent price
            exit_timestamp=exit_time,
            exit_reason=ExitReason.TARGET,
            exit_provenance=exit_prov,
            costs=5.0,
            settings=test_env["settings"],
        )

    # Events timeline validation: seq 1 (created), 2 (filled), 3 (exited)
    events = get_journal_history(trade.journal_id, settings=test_env["settings"])
    assert len(events) == 3
    assert [e.seq for e in events] == [1, 2, 3]
    assert [e.event_type for e in events] == [
        JournalEventType.CREATED,
        JournalEventType.FILLED,
        JournalEventType.EXITED,
    ]


def test_planned_to_cancelled_transition(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
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
        candidate_id="cand-201",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=TradePlan(planned_entry=100.0),
        decided_by="gary",
        plan_source="manual",
        idempotency_key="key-lifecycle-cancel",
        settings=test_env["settings"],
    )

    c_time = t0 + timedelta(minutes=15)
    trade_cancelled = cancel_trade(
        journal_id=trade.journal_id,
        cancel_reason="Market regime shifted",
        cancelled_at=c_time,
        settings=test_env["settings"],
    )
    assert trade_cancelled.state == JournalState.CANCELLED
    assert trade_cancelled.terminal_reason == "Market regime shifted"

    # Idempotent cancel
    repeat = cancel_trade(
        journal_id=trade.journal_id,
        cancel_reason="Market regime shifted",
        cancelled_at=c_time,
        settings=test_env["settings"],
    )
    assert repeat == trade_cancelled

    # Cannot fill cancelled trade
    prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=c_time,
        observer="gary",
    )
    with pytest.raises(InvalidTransitionError, match="Cannot record fill"):
        record_fill(
            journal_id=trade.journal_id,
            fill_price=100.0,
            fill_timestamp=c_time,
            fill_provenance=prov,
            quantity=100.0,
            settings=test_env["settings"],
        )


def test_planned_to_invalidated_transition(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
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
        candidate_id="cand-201",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=TradePlan(planned_entry=100.0),
        decided_by="gary",
        plan_source="manual",
        idempotency_key="key-lifecycle-inv",
        settings=test_env["settings"],
    )

    inv_time = t0 + timedelta(minutes=20)
    trade_inv = invalidate_trade(
        journal_id=trade.journal_id,
        invalidation_reason="Lower low on higher volume before entry trigger",
        invalidated_at=inv_time,
        settings=test_env["settings"],
    )
    assert trade_inv.state == JournalState.INVALIDATED
    assert trade_inv.terminal_reason == "Lower low on higher volume before entry trigger"

    # Idempotent repeat
    repeat = invalidate_trade(
        journal_id=trade.journal_id,
        invalidation_reason="Lower low on higher volume before entry trigger",
        invalidated_at=inv_time,
        settings=test_env["settings"],
    )
    assert repeat == trade_inv


def test_planned_to_expired_transition(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
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
    exp_dt = t0 + timedelta(hours=4)
    trade = create_planned_trade(
        candidate_id="cand-201",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=TradePlan(planned_entry=100.0, expiration=exp_dt),
        decided_by="gary",
        plan_source="manual",
        idempotency_key="key-lifecycle-exp",
        settings=test_env["settings"],
    )

    # Expire before expiration threshold raises ValueError
    with pytest.raises(ValueError, match="must be >= plan expiration"):
        expire_trade(
            journal_id=trade.journal_id,
            expired_at=exp_dt - timedelta(minutes=5),
            settings=test_env["settings"],
        )

    # Expire at or after expiration timestamp
    trade_exp = expire_trade(
        journal_id=trade.journal_id,
        expired_at=exp_dt + timedelta(minutes=1),
        settings=test_env["settings"],
    )
    assert trade_exp.state == JournalState.EXPIRED

    # Idempotent repeat
    repeat = expire_trade(
        journal_id=trade.journal_id,
        expired_at=exp_dt + timedelta(minutes=1),
        settings=test_env["settings"],
    )
    assert repeat == trade_exp


def test_prohibited_transitions_rejected(test_env, monkeypatch: pytest.MonkeyPatch) -> None:
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
        candidate_id="cand-201",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=TradePlan(planned_entry=100.0),
        decided_by="gary",
        plan_source="manual",
        idempotency_key="key-lifecycle-prohibited",
        settings=test_env["settings"],
    )

    prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=t0 + timedelta(minutes=5),
        observer="gary",
    )

    # 1. Exit before fill (planned -> closed) raises InvalidTransitionError
    with pytest.raises(InvalidTransitionError, match="expected 'open'"):
        record_exit(
            journal_id=trade.journal_id,
            exit_price=110.0,
            exit_timestamp=t0 + timedelta(minutes=10),
            exit_reason=ExitReason.TARGET,
            exit_provenance=prov,
            settings=test_env["settings"],
        )

    # Fill the trade
    record_fill(
        journal_id=trade.journal_id,
        fill_price=100.0,
        fill_timestamp=t0 + timedelta(minutes=5),
        fill_provenance=prov,
        quantity=100.0,
        settings=test_env["settings"],
    )

    # 2. Open -> cancelled without exit fill raises InvalidTransitionError
    with pytest.raises(InvalidTransitionError, match="expected 'planned'"):
        cancel_trade(
            journal_id=trade.journal_id,
            cancel_reason="cancel after open",
            cancelled_at=t0 + timedelta(minutes=15),
            settings=test_env["settings"],
        )

    # 3. Open -> invalidated without exit fill raises InvalidTransitionError
    with pytest.raises(InvalidTransitionError, match="without an exit fill"):
        invalidate_trade(
            journal_id=trade.journal_id,
            invalidation_reason="invalidate after open",
            invalidated_at=t0 + timedelta(minutes=15),
            settings=test_env["settings"],
        )

    # 4. Open -> expired without exit fill raises InvalidTransitionError
    with pytest.raises(InvalidTransitionError, match="without an exit fill"):
        expire_trade(
            journal_id=trade.journal_id,
            expired_at=t0 + timedelta(days=1),
            settings=test_env["settings"],
        )

    # Close the trade
    record_exit(
        journal_id=trade.journal_id,
        exit_price=110.0,
        exit_timestamp=t0 + timedelta(hours=1),
        exit_reason=ExitReason.TARGET,
        exit_provenance=prov,
        settings=test_env["settings"],
    )

    # 5. Transitions out of terminal closed state raise InvalidTransitionError
    with pytest.raises(InvalidTransitionError):
        record_fill(
            journal_id=trade.journal_id,
            fill_price=100.0,
            fill_timestamp=t0 + timedelta(hours=2),
            fill_provenance=prov,
            quantity=100.0,
            settings=test_env["settings"],
        )


def test_strategy_deauthorization_allows_existing_trade_lifecycle_continuation(
    test_env, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        candidate_id="cand-201",
        strategy_id="long-momentum",
        strategy_version="1.0.0",
        decision_timestamp=t0,
        plan_created_at=t0,
        plan=TradePlan(planned_entry=100.0),
        decided_by="gary",
        plan_source="manual",
        idempotency_key="key-lifecycle-deauth",
        settings=test_env["settings"],
    )

    # Strategy is now DE-AUTHORIZED / RETIRED
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (),
    )

    # 1. New trade creation is rejected
    with pytest.raises(StrategyNotAuthorizedError):
        create_planned_trade(
            candidate_id="cand-201",
            strategy_id="long-momentum",
            strategy_version="1.0.0",
            decision_timestamp=t0,
            plan_created_at=t0,
            plan=TradePlan(planned_entry=100.0),
            decided_by="gary",
            plan_source="manual",
            idempotency_key="key-new-after-deauth",
            settings=test_env["settings"],
        )

    # 2. Existing planned trade can still be filled and closed
    prov = ExecutionProvenance(
        execution_provenance=ExecutionProvenanceType.MANUAL,
        provider="schwab",
        observed_at=t0 + timedelta(minutes=5),
        observer="gary",
    )
    trade_open = record_fill(
        journal_id=trade.journal_id,
        fill_price=100.0,
        fill_timestamp=t0 + timedelta(minutes=5),
        fill_provenance=prov,
        quantity=100.0,
        settings=test_env["settings"],
    )
    assert trade_open.state == JournalState.OPEN

    trade_closed = record_exit(
        journal_id=trade.journal_id,
        exit_price=110.0,
        exit_timestamp=t0 + timedelta(hours=1),
        exit_reason=ExitReason.TARGET,
        exit_provenance=prov,
        costs=5.0,
        settings=test_env["settings"],
    )
    assert trade_closed.state == JournalState.CLOSED
