"""Deterministic unit and integration tests for read-only Journal queries (MVP-ARCH-001-R6-IMPL-B).

Validates deterministic sorting, current outcome selection with tie-breaking,
state/strategy/symbol filtering, candidate linkage, strategy authorization checks,
event stream ordering, outcome audit history ordering, zero provider calls,
and zero database mutations.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tradex.candidates import (
    CandidateDossier,
    CandidateEvidence,
    CandidateSnapshot,
    SecurityIdentityStatus,
    record_candidate_dossier,
)
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
)
from tradex.journal.queries import (
    format_confidence_label,
    format_lifecycle_state_label,
    format_provenance_label,
    get_journal_detail,
    get_journal_events_timeline,
    get_journal_outcome_history,
    get_journal_overview,
    get_journal_strategy_ids,
    list_journal_read_models,
)
from tradex.journal.store import (
    insert_journal_event,
    insert_journal_outcome,
    insert_journal_trade,
)
from tradex.strategies.registry import ApprovedProductionStrategy
from tradex.tracker import store


@pytest.fixture
def journal_query_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Create and initialize an isolated test SQLite database at schema v5."""
    db_path = str(tmp_path / "test_journal_queries.db")
    monkeypatch.setattr(store, "DB_PATH", db_path)
    store.init(db_path)
    return db_path


def _make_candidate(
    db_path: str,
    candidate_id: str,
    symbol: str,
    dt: datetime,
) -> CandidateSnapshot:
    """Helper to record a valid candidate snapshot and evidence."""
    snap = CandidateSnapshot(
        candidate_id=candidate_id,
        symbol=symbol,
        decision_timestamp=dt,
        contract_version=1,
        trading_date=dt.strftime("%Y-%m-%d"),
        security_identity_version="sec-v1",
        security_identity_status=SecurityIdentityStatus.KNOWN,
    )
    evid = CandidateEvidence(
        evidence_id=f"evid-{candidate_id}",
        candidate_id=candidate_id,
        evidence_type="screener_observation",
        source_ref_type="scan_session",
        source_ref_id="session-01",
        provider="yahoo",
        observed_at=dt,
        metadata={"legacy_heuristic_score": 75, "timeframe": "intraday"},
    )
    dossier = CandidateDossier(
        snapshot=snap,
        evaluations=(),
        evidence=(evid,),
        reasons=(),
        missing_data=(),
    )
    record_candidate_dossier(dossier, db_path=db_path)
    return snap


def _insert_trade(
    db_path: str,
    *,
    journal_id: str,
    candidate_id: str,
    strategy_id: str = "strat_a",
    strategy_version: str = "1.0",
    side: str = "long",
    state: JournalState = JournalState.PLANNED,
    decision_timestamp: datetime,
    plan_created_at: datetime,
    planned_entry: float = 100.0,
    stop_price: float | None = None,
    target_price: float | None = None,
    expiration: datetime | None = None,
    invalidation_rule: InvalidationRule | None = None,
    quantity: float | None = None,
    fill_price: float | None = None,
    fill_timestamp: datetime | None = None,
    fill_provenance: ExecutionProvenance | None = None,
    exit_price: float | None = None,
    exit_timestamp: datetime | None = None,
    exit_reason: ExitReason | str | None = None,
    exit_provenance: ExecutionProvenance | None = None,
    terminal_reason: str | None = None,
) -> JournalTrade:
    trade = JournalTrade(
        journal_id=journal_id,
        contract_version=1,
        idempotency_key=f"idem-{journal_id}",
        candidate_id=candidate_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        side=side,
        state=state,
        decision_timestamp=decision_timestamp,
        plan_created_at=plan_created_at,
        planned_entry=planned_entry,
        stop_price=stop_price,
        target_price=target_price,
        expiration=expiration,
        invalidation_rule=invalidation_rule,
        quantity=quantity,
        fill_price=fill_price,
        fill_timestamp=fill_timestamp,
        fill_provenance=fill_provenance,
        exit_price=exit_price,
        exit_timestamp=exit_timestamp,
        exit_reason=exit_reason,
        exit_provenance=exit_provenance,
        terminal_reason=terminal_reason,
        created_at=plan_created_at,
        updated_at=plan_created_at,
    )
    with sqlite3.connect(db_path) as con:
        insert_journal_trade(con, trade)
        con.commit()
    return trade


def _insert_event(
    db_path: str,
    *,
    event_id: str,
    journal_id: str,
    seq: int,
    event_type: JournalEventType | str = JournalEventType.CREATED,
    event_timestamp: datetime,
    recorded_at: datetime | None = None,
    payload: dict | None = None,
) -> JournalEvent:
    rec_at = recorded_at or event_timestamp
    ev_type = (
        event_type
        if isinstance(event_type, JournalEventType)
        else JournalEventType(str(event_type).lower())
    )
    ev = JournalEvent(
        event_id=event_id,
        journal_id=journal_id,
        seq=seq,
        event_type=ev_type,
        event_timestamp=event_timestamp,
        recorded_at=rec_at,
        payload=payload or {},
    )
    with sqlite3.connect(db_path) as con:
        insert_journal_event(con, ev)
        con.commit()
    return ev


def _insert_outcome(
    db_path: str,
    *,
    outcome_id: str,
    journal_id: str,
    computation_version: str = "1.0",
    computed_at: datetime,
    source_event_seq: int = 1,
    inputs_hash: str = "hash",
    entry_slippage: float | None = 0.05,
    costs: float | None = 1.50,
    gross_return_pct: float | None = 5.0,
    net_return_pct: float | None = 4.8,
    outcome_confidence: str = "provisional",
    inputs: dict | None = None,
) -> JournalOutcome:
    out = JournalOutcome(
        outcome_id=outcome_id,
        journal_id=journal_id,
        computation_version=computation_version,
        computed_at=computed_at,
        source_event_seq=source_event_seq,
        inputs_hash=inputs_hash,
        entry_slippage=entry_slippage,
        costs=costs,
        gross_return_pct=gross_return_pct,
        net_return_pct=net_return_pct,
        outcome_confidence=outcome_confidence,
        inputs=inputs or {},
        strategy_drawdown=None,
    )
    with sqlite3.connect(db_path) as con:
        insert_journal_outcome(con, out)
        con.commit()
    return out


# ── 1. Empty Overview ─────────────────────────────────────────────────────────


def test_empty_journal_overview_returns_empty_list(journal_query_db: str):
    """When journal_trades is empty, list_journal_read_models returns an empty list."""
    results = list_journal_read_models(db_path=journal_query_db)
    assert results == []
    assert get_journal_overview(db_path=journal_query_db) == []


# ── 2. Deterministic Overview Ordering ───────────────────────────────────────


def test_overview_deterministic_ordering(journal_query_db: str):
    """Journal trades are sorted by plan_created_at DESC, journal_id ASC."""
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)
    _make_candidate(journal_query_db, "cand-1", "AAPL", base_t - timedelta(minutes=15))
    _make_candidate(journal_query_db, "cand-2", "MSFT", base_t)
    _make_candidate(journal_query_db, "cand-3", "NVDA", base_t)

    _insert_trade(
        journal_query_db,
        journal_id="j-older",
        candidate_id="cand-1",
        decision_timestamp=base_t - timedelta(minutes=15),
        plan_created_at=base_t - timedelta(minutes=10),
    )
    _insert_trade(
        journal_query_db,
        journal_id="j-new-z",
        candidate_id="cand-2",
        decision_timestamp=base_t,
        plan_created_at=base_t,
    )
    _insert_trade(
        journal_query_db,
        journal_id="j-new-a",
        candidate_id="cand-3",
        decision_timestamp=base_t,
        plan_created_at=base_t,
    )

    overview = list_journal_read_models(db_path=journal_query_db)
    assert len(overview) == 3
    # j-new-a and j-new-z have same plan_created_at; j-new-a comes first due to journal_id ASC
    assert [t.journal_id for t in overview] == ["j-new-a", "j-new-z", "j-older"]


# ── 3. Filters: State, Strategy, Symbol ──────────────────────────────────────


def test_overview_filters(journal_query_db: str):
    """Filters on state, strategy_id, and symbol function accurately and case-insensitively."""
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)
    _make_candidate(journal_query_db, "cand-aapl", "AAPL", base_t)
    _make_candidate(journal_query_db, "cand-msft", "MSFT", base_t - timedelta(minutes=10))

    _insert_trade(
        journal_query_db,
        journal_id="j-aapl",
        candidate_id="cand-aapl",
        strategy_id="breakout",
        strategy_version="1.0",
        state=JournalState.PLANNED,
        decision_timestamp=base_t,
        plan_created_at=base_t,
    )
    _insert_trade(
        journal_query_db,
        journal_id="j-msft",
        candidate_id="cand-msft",
        strategy_id="mean_revert",
        strategy_version="2.0",
        state=JournalState.CLOSED,
        decision_timestamp=base_t - timedelta(minutes=10),
        plan_created_at=base_t - timedelta(minutes=5),
        planned_entry=300.0,
        quantity=10.0,
        fill_price=300.0,
        fill_timestamp=base_t - timedelta(minutes=4),
        exit_price=315.0,
        exit_timestamp=base_t,
        exit_reason=ExitReason.TARGET,
    )

    # State filter
    planned = list_journal_read_models(state="planned", db_path=journal_query_db)
    assert len(planned) == 1
    assert planned[0].journal_id == "j-aapl"

    closed = list_journal_read_models(state="CLOSED", db_path=journal_query_db)
    assert len(closed) == 1
    assert closed[0].journal_id == "j-msft"

    # Strategy filter
    strat = list_journal_read_models(strategy_id="breakout", db_path=journal_query_db)
    assert len(strat) == 1
    assert strat[0].journal_id == "j-aapl"

    # Symbol filter (exact and prefix, case-insensitive)
    sym_exact = list_journal_read_models(symbol="aapl", db_path=journal_query_db)
    assert len(sym_exact) == 1
    assert sym_exact[0].symbol == "AAPL"

    sym_prefix = list_journal_read_models(symbol="MS", db_path=journal_query_db)
    assert len(sym_prefix) == 1
    assert sym_prefix[0].symbol == "MSFT"

    sym_none = list_journal_read_models(symbol="TSLA", db_path=journal_query_db)
    assert sym_none == []


# ── 4. Limit and Offset Pagination ───────────────────────────────────────────


def test_overview_pagination(journal_query_db: str):
    """Limit and offset paginate results deterministically."""
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)
    for i in range(5):
        t_plan = base_t - timedelta(minutes=i)
        t_dec = t_plan - timedelta(minutes=1)
        _make_candidate(journal_query_db, f"cand-{i}", f"SYM{i}", t_dec)
        _insert_trade(
            journal_query_db,
            journal_id=f"j-{i}",
            candidate_id=f"cand-{i}",
            decision_timestamp=t_dec,
            plan_created_at=t_plan,
        )

    p1 = list_journal_read_models(limit=2, offset=0, db_path=journal_query_db)
    p2 = list_journal_read_models(limit=2, offset=2, db_path=journal_query_db)
    p3 = list_journal_read_models(limit=2, offset=4, db_path=journal_query_db)

    assert [t.journal_id for t in p1] == ["j-0", "j-1"]
    assert [t.journal_id for t in p2] == ["j-2", "j-3"]
    assert [t.journal_id for t in p3] == ["j-4"]


# ── 5. Current Outcome Selection & Tie-Breaking ──────────────────────────────


def test_overview_current_outcome_window_ranking(journal_query_db: str):
    """Current outcome selection uses computed_at DESC, outcome_id ASC."""
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)
    _make_candidate(journal_query_db, "cand-1", "AAPL", base_t)

    _insert_trade(
        journal_query_db,
        journal_id="j-1",
        candidate_id="cand-1",
        state=JournalState.CLOSED,
        decision_timestamp=base_t,
        plan_created_at=base_t,
        planned_entry=150.0,
        quantity=10.0,
        fill_price=150.0,
        fill_timestamp=base_t + timedelta(minutes=5),
        exit_price=160.0,
        exit_timestamp=base_t + timedelta(hours=1),
        exit_reason=ExitReason.TARGET,
    )

    # Insert older outcome
    _insert_outcome(
        journal_query_db,
        outcome_id="out-old",
        journal_id="j-1",
        computed_at=base_t + timedelta(hours=1),
        gross_return_pct=5.0,
        net_return_pct=4.8,
        outcome_confidence="provisional",
    )

    # Insert newer outcome A
    _insert_outcome(
        journal_query_db,
        outcome_id="out-new-z",
        journal_id="j-1",
        computation_version="1.0",
        computed_at=base_t + timedelta(hours=2),
        gross_return_pct=10.0,
        net_return_pct=9.5,
        outcome_confidence="confirmed",
    )

    # Insert newer outcome B with identical timestamp but different computation_version (tie-break by outcome_id ASC: out-new-a < out-new-z)
    _insert_outcome(
        journal_query_db,
        outcome_id="out-new-a",
        journal_id="j-1",
        computation_version="2.0",
        computed_at=base_t + timedelta(hours=2),
        gross_return_pct=10.5,
        net_return_pct=10.0,
        outcome_confidence="confirmed",
    )

    overview = list_journal_read_models(db_path=journal_query_db)
    assert len(overview) == 1
    t = overview[0]
    assert t.current_outcome_id == "out-new-a"
    assert t.gross_return_pct == 10.5
    assert t.net_return_pct == 10.0
    assert t.outcome_confidence == "confirmed"


# ── 6. Historical Deauthorized Strategy & Active Strategy ────────────────────


def test_strategy_authorization_status(journal_query_db: str, monkeypatch: pytest.MonkeyPatch):
    """Historical trade with deauthorized strategy has is_strategy_authorized=False; active is True."""
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)
    _make_candidate(journal_query_db, "cand-1", "AAPL", base_t)

    _insert_trade(
        journal_query_db,
        journal_id="j-alpha",
        candidate_id="cand-1",
        strategy_id="strat_alpha",
        strategy_version="1.0",
        decision_timestamp=base_t,
        plan_created_at=base_t,
    )

    # By default, APPROVED_PRODUCTION_STRATEGIES is empty ()
    trades = list_journal_read_models(db_path=journal_query_db)
    assert len(trades) == 1
    assert trades[0].is_strategy_authorized is False

    # Simulate authorizing strat_alpha v1.0 with journal_execution capability
    auth_strat = ApprovedProductionStrategy(
        strategy_id="strat_alpha",
        strategy_version="1.0",
        description="Test Strategy Alpha",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (auth_strat,),
    )

    trades_after = list_journal_read_models(db_path=journal_query_db)
    assert trades_after[0].is_strategy_authorized is True

    # If version differs, it must remain False
    auth_strat_v2 = ApprovedProductionStrategy(
        strategy_id="strat_alpha",
        strategy_version="2.0",
        description="Test Strategy Alpha v2",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (auth_strat_v2,),
    )
    trades_v2 = list_journal_read_models(db_path=journal_query_db)
    assert trades_v2[0].is_strategy_authorized is False


# ── 7. Events Timeline Ordering ──────────────────────────────────────────────


def test_events_timeline_ordering(journal_query_db: str):
    """Events timeline returns all lifecycle events ordered by seq ASC."""
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)

    # Insert out of order
    _insert_event(
        journal_query_db,
        event_id="ev-3",
        journal_id="j-trade",
        seq=3,
        event_type="exited",
        event_timestamp=base_t + timedelta(hours=2),
        payload={"exit_price": 160.0},
    )
    _insert_event(
        journal_query_db,
        event_id="ev-1",
        journal_id="j-trade",
        seq=1,
        event_type="created",
        event_timestamp=base_t,
        payload={"planned_entry": 150.0},
    )
    _insert_event(
        journal_query_db,
        event_id="ev-2",
        journal_id="j-trade",
        seq=2,
        event_type="filled",
        event_timestamp=base_t + timedelta(hours=1),
        payload={"fill_price": 150.5},
    )

    events = get_journal_events_timeline("j-trade", db_path=journal_query_db)
    assert len(events) == 3
    assert [e.seq for e in events] == [1, 2, 3]
    assert [e.event_type for e in events] == ["created", "filled", "exited"]
    assert events[0].payload == {"planned_entry": 150.0}


# ── 8. Outcome History Ordering ──────────────────────────────────────────────


def test_outcome_history_ordering(journal_query_db: str):
    """Outcome history returns all computations ordered by computed_at DESC, outcome_id ASC."""
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)

    _insert_outcome(
        journal_query_db,
        outcome_id="out-1",
        journal_id="j-trade",
        computed_at=base_t + timedelta(hours=1),
        gross_return_pct=2.0,
        net_return_pct=1.8,
        outcome_confidence="provisional",
        inputs={"version": 1},
    )
    _insert_outcome(
        journal_query_db,
        outcome_id="out-2",
        journal_id="j-trade",
        computed_at=base_t + timedelta(hours=3),
        gross_return_pct=5.0,
        net_return_pct=4.8,
        outcome_confidence="confirmed",
        inputs={"version": 2},
    )

    outcomes = get_journal_outcome_history("j-trade", db_path=journal_query_db)
    assert len(outcomes) == 2
    assert [o.outcome_id for o in outcomes] == ["out-2", "out-1"]
    assert outcomes[0].strategy_drawdown is None
    assert outcomes[1].strategy_drawdown is None


# ── 9. Detail Drill-Down Query ───────────────────────────────────────────────


def test_get_journal_detail_with_candidate_linkage(journal_query_db: str):
    """get_journal_detail builds full read model with linked candidate snapshot and evidence."""
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)
    _make_candidate(journal_query_db, "cand-1", "NVDA", base_t)

    _insert_trade(
        journal_query_db,
        journal_id="j-nvda",
        candidate_id="cand-1",
        strategy_id="gap_fill",
        strategy_version="1.0",
        state=JournalState.CLOSED,
        decision_timestamp=base_t,
        plan_created_at=base_t,
        planned_entry=500.0,
        quantity=50.0,
        fill_price=500.2,
        fill_timestamp=base_t + timedelta(minutes=1),
        fill_provenance=ExecutionProvenance(
            execution_provenance=ExecutionProvenanceType.SIMULATED,
            provider="yahoo",
            observed_at=base_t + timedelta(minutes=1),
            observer="sim_engine",
            simulation_rule="next_open",
        ),
        stop_price=490.0,
        target_price=520.0,
        exit_price=520.0,
        exit_timestamp=base_t + timedelta(hours=2),
        exit_reason=ExitReason.TARGET,
        exit_provenance=ExecutionProvenance(
            execution_provenance=ExecutionProvenanceType.SIMULATED,
            provider="yahoo",
            observed_at=base_t + timedelta(hours=2),
            observer="sim_engine",
            simulation_rule="touch",
        ),
        terminal_reason="Target reached",
    )

    _insert_event(
        journal_query_db,
        event_id="ev-1",
        journal_id="j-nvda",
        seq=1,
        event_type="created",
        event_timestamp=base_t,
    )
    _insert_outcome(
        journal_query_db,
        outcome_id="out-1",
        journal_id="j-nvda",
        computed_at=base_t + timedelta(hours=2),
        gross_return_pct=3.96,
        net_return_pct=3.82,
        costs=3.50,
        entry_slippage=0.20,
    )

    detail = get_journal_detail("j-nvda", db_path=journal_query_db)
    assert detail is not None
    assert detail.symbol == "NVDA"
    assert detail.trade.journal_id == "j-nvda"
    assert detail.trade.state == "closed"
    assert detail.candidate_snapshot is not None
    assert detail.candidate_snapshot.symbol == "NVDA"
    assert "screener_observation" in detail.candidate_evidence_summary
    assert detail.current_outcome is not None
    assert detail.current_outcome.outcome_id == "out-1"
    assert len(detail.events) == 1
    assert len(detail.outcomes) == 1

    # Non-existent journal ID returns None
    assert get_journal_detail("non-existent", db_path=journal_query_db) is None


# ── 10. Distinct Strategy IDs ────────────────────────────────────────────────


def test_get_journal_strategy_ids(journal_query_db: str):
    """get_journal_strategy_ids returns distinct sorted strategy IDs."""
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)
    _make_candidate(journal_query_db, "c1", "AAPL", base_t)

    _insert_trade(
        journal_query_db,
        journal_id="j-1",
        candidate_id="c1",
        strategy_id="strat_z",
        strategy_version="1.0",
        decision_timestamp=base_t,
        plan_created_at=base_t,
    )
    _insert_trade(
        journal_query_db,
        journal_id="j-2",
        candidate_id="c1",
        strategy_id="strat_a",
        strategy_version="1.0",
        decision_timestamp=base_t,
        plan_created_at=base_t,
    )
    _insert_trade(
        journal_query_db,
        journal_id="j-3",
        candidate_id="c1",
        strategy_id="strat_z",
        strategy_version="2.0",
        decision_timestamp=base_t,
        plan_created_at=base_t,
    )

    ids = get_journal_strategy_ids(db_path=journal_query_db)
    assert ids == ["strat_a", "strat_z"]


# ── 11. Read-Only Invariant: Zero Writes / Side-Effects ────────────────────────


def test_query_layer_performs_zero_writes(journal_query_db: str):
    """Querying overview, detail, events, and outcomes does not modify database tables or row counts."""
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)
    _make_candidate(journal_query_db, "c1", "AAPL", base_t)
    _insert_trade(
        journal_query_db,
        journal_id="j-1",
        candidate_id="c1",
        strategy_id="strat_a",
        strategy_version="1.0",
        decision_timestamp=base_t,
        plan_created_at=base_t,
    )

    def _get_counts():
        con = sqlite3.connect(journal_query_db)
        trades_ct = con.execute("SELECT count(*) FROM journal_trades").fetchone()[0]
        events_ct = con.execute("SELECT count(*) FROM journal_events").fetchone()[0]
        outcomes_ct = con.execute("SELECT count(*) FROM journal_outcomes").fetchone()[0]
        con.close()
        return trades_ct, events_ct, outcomes_ct

    c_before = _get_counts()

    # Execute all read queries
    list_journal_read_models(db_path=journal_query_db)
    get_journal_detail("j-1", db_path=journal_query_db)
    get_journal_events_timeline("j-1", db_path=journal_query_db)
    get_journal_outcome_history("j-1", db_path=journal_query_db)
    get_journal_strategy_ids(db_path=journal_query_db)

    c_after = _get_counts()
    assert c_before == c_after == (1, 0, 0)


# ── 12. Formatting Helper Tests ───────────────────────────────────────────────


def test_formatting_helpers():
    """Format helpers return canonical, human-readable labels for badges and telemetry."""
    assert format_lifecycle_state_label("planned") == "Planned"
    assert format_lifecycle_state_label("open") == "Open"
    assert format_lifecycle_state_label("closed") == "Closed"
    assert format_lifecycle_state_label("cancelled") == "Cancelled"
    assert format_lifecycle_state_label("expired") == "Expired"
    assert format_lifecycle_state_label("invalidated") == "Invalidated"
    assert format_lifecycle_state_label(None) == "Unknown"

    assert format_provenance_label("manual") == "Manual Reported"
    assert format_provenance_label("simulated") == "Simulated"
    assert format_provenance_label("broker_confirmed") == "Broker Confirmed"
    assert format_provenance_label(None) == "—"

    assert format_confidence_label("confirmed") == "Confirmed"
    assert format_confidence_label("provisional") == "Provisional"
    assert format_confidence_label("unknown") == "Unknown"
    assert format_confidence_label(None) == "—"
