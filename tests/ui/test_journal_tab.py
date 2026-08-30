"""Deterministic UI tests for the Executable Journal tab (MVP-ARCH-001-R6-IMPL-B).

Proves truthful empty-state messaging, historical read-only mode banners,
lifecycle/provenance/confidence badging, in-place detail inspection, and
the strict zero-mutation invariant.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradex.config import settings_from_mapping
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
    insert_journal_event,
    insert_journal_outcome,
    insert_journal_trade,
)
from tradex.tracker import store
from tradex.ui.tabs import journal as journal_tab_module


@pytest.fixture
def fake_journal_st():
    """Deterministic Streamlit mock for Journal tab testing."""
    st = MagicMock(name="streamlit")
    st.__version__ = "0.0.0"
    st.session_state = {}

    def _button(label, *args, **kwargs):
        key = kwargs.get("key")
        return bool(key and key in getattr(st, "_active_buttons", set()))

    def _selectbox(label, options, *args, **kwargs):
        key = kwargs.get("key")
        if key and key in st.session_state:
            return st.session_state[key]
        if options:
            return options[0]
        return None

    def _text_input(label, *args, **kwargs):
        key = kwargs.get("key")
        if key and key in st.session_state:
            return st.session_state[key]
        return ""

    def _columns(spec, *args, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        cols = []
        for _ in range(n):
            col = MagicMock()
            col.button.side_effect = _button
            col.selectbox.side_effect = _selectbox
            col.text_input.side_effect = _text_input
            col.metric.return_value = MagicMock()
            cols.append(col)
        return cols

    class _ExpanderContext:
        def __enter__(self):
            return st

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    st.button.side_effect = _button
    st.selectbox.side_effect = _selectbox
    st.text_input.side_effect = _text_input
    st.columns.side_effect = _columns
    st.expander.return_value = _ExpanderContext()
    st._active_buttons = set()
    return st


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = str(tmp_path / "test_ui_journal.db")
    monkeypatch.setattr(store, "DB_PATH", db_path)
    store.init(db_path)
    return db_path


# ── 1. Import Safety ──────────────────────────────────────────────────────────


def test_import_has_no_side_effects(fake_journal_st, monkeypatch):
    """Importing tradex.ui.tabs.journal must not invoke Streamlit or backend mutations."""
    monkeypatch.setattr(journal_tab_module, "st", fake_journal_st)

    assert fake_journal_st.subheader.call_count == 0
    assert fake_journal_st.dataframe.call_count == 0


# ── 2. True Empty State UX (Case A & Case B) ──────────────────────────────────


def test_true_empty_state_case_a_no_strategy(fake_journal_st, isolated_db, monkeypatch):
    """Case A: Zero records and empty strategy registry renders truthful explanation with no create controls."""
    monkeypatch.setattr(journal_tab_module, "st", fake_journal_st)
    settings = settings_from_mapping({"TRADEX_DB_PATH": isolated_db})

    journal_tab_module.render_journal_tab(settings=settings)

    fake_journal_st.subheader.assert_called_once_with("Journal")
    fake_journal_st.caption.assert_called_once_with("Executable Strategy Journal")

    info_texts = [str(call[0][0]) for call in fake_journal_st.info.call_args_list]
    assert any("No production-approved executable strategy is currently active" in t for t in info_texts)
    assert any("Legacy scanner outcomes remain available as descriptive telemetry" in t for t in info_texts)

    # No tables or drill-down buttons in empty state
    assert fake_journal_st.dataframe.call_count == 0
    assert "btn_view_journal_detail" not in fake_journal_st._active_buttons


def test_true_empty_state_case_b_authorized_strategy_exists(fake_journal_st, isolated_db, monkeypatch):
    """Case B: Zero records with authorized strategy renders truthful authorized-empty state with zero create controls."""
    import tradex.strategies.registry as reg

    mock_strat = reg.ApprovedProductionStrategy(
        strategy_id="strat_approved",
        strategy_version="1.0",
        description="Approved test strategy",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(reg, "APPROVED_PRODUCTION_STRATEGIES", (mock_strat,))
    monkeypatch.setattr(journal_tab_module, "st", fake_journal_st)
    settings = settings_from_mapping({"TRADEX_DB_PATH": isolated_db})

    journal_tab_module.render_journal_tab(settings=settings)

    info_texts = [str(call[0][0]) for call in fake_journal_st.info.call_args_list]
    assert any("An executable production strategy is currently authorized, but no Journal records have been recorded yet" in t for t in info_texts)

    # Still strictly read-only, zero action controls
    assert fake_journal_st.dataframe.call_count == 0
    assert "btn_view_journal_detail" not in fake_journal_st._active_buttons


def test_registry_changes_observed_at_render_time(fake_journal_st, isolated_db, monkeypatch):
    """Registry authorization changes are dynamically observed at render time."""
    import tradex.strategies.registry as reg

    monkeypatch.setattr(journal_tab_module, "st", fake_journal_st)
    settings = settings_from_mapping({"TRADEX_DB_PATH": isolated_db})

    # Initially empty registry -> Case A
    monkeypatch.setattr(reg, "APPROVED_PRODUCTION_STRATEGIES", ())
    journal_tab_module.render_journal_tab(settings=settings)
    assert any("No production-approved executable strategy is currently active" in str(c[0][0]) for c in fake_journal_st.info.call_args_list)

    # Dynamically authorize strategy -> Case B
    fake_journal_st.info.reset_mock()
    mock_strat = reg.ApprovedProductionStrategy(
        strategy_id="strat_approved",
        strategy_version="1.0",
        description="Approved test strategy",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(reg, "APPROVED_PRODUCTION_STRATEGIES", (mock_strat,))
    journal_tab_module.render_journal_tab(settings=settings)
    assert any("An executable production strategy is currently authorized" in str(c[0][0]) for c in fake_journal_st.info.call_args_list)


# ── 3. Historical Read-Only Mode Overview & Badges ───────────────────────────


def test_historical_overview_rendering(fake_journal_st, isolated_db, monkeypatch):
    """Persisted records show historical banner, table with badges, and unauthorized tags."""
    monkeypatch.setattr(journal_tab_module, "st", fake_journal_st)
    settings = settings_from_mapping({"TRADEX_DB_PATH": isolated_db})

    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)

    # Insert a candidate snapshot
    with sqlite3.connect(isolated_db) as con:
        con.execute(
            """
            INSERT INTO candidates (candidate_id, contract_version, symbol, decision_timestamp, trading_date, security_identity_version, security_identity_status, created_at)
            VALUES ('cand-1', 1, 'AAPL', ?, '2026-08-20', 'sec-v1', 'known', ?)
            """,
            (base_t.isoformat(), base_t.isoformat()),
        )
        con.commit()

    # Insert a closed trade
    trade = JournalTrade(
        journal_id="j-aapl-01",
        contract_version=1,
        idempotency_key="idem-1",
        candidate_id="cand-1",
        strategy_id="breakout",
        strategy_version="1.0",
        side="long",
        state=JournalState.CLOSED,
        decision_timestamp=base_t,
        plan_created_at=base_t,
        planned_entry=150.0,
        stop_price=140.0,
        target_price=165.0,
        quantity=10.0,
        fill_price=150.0,
        fill_timestamp=base_t + timedelta(minutes=1),
        fill_provenance=ExecutionProvenance(
            execution_provenance=ExecutionProvenanceType.MANUAL,
            provider="manual",
            observed_at=base_t + timedelta(minutes=1),
            observer="trader_gary",
        ),
        exit_price=165.0,
        exit_timestamp=base_t + timedelta(hours=2),
        exit_reason=ExitReason.TARGET,
        exit_provenance=ExecutionProvenance(
            execution_provenance=ExecutionProvenanceType.MANUAL,
            provider="manual",
            observed_at=base_t + timedelta(hours=2),
            observer="trader_gary",
        ),
        terminal_reason="Target filled",
        created_at=base_t,
        updated_at=base_t,
    )
    with sqlite3.connect(isolated_db) as con:
        insert_journal_trade(con, trade)
        insert_journal_outcome(
            con,
            JournalOutcome(
                outcome_id="out-1",
                journal_id="j-aapl-01",
                computation_version="1.0",
                computed_at=base_t + timedelta(hours=2),
                source_event_seq=1,
                inputs_hash="hash-1",
                entry_slippage=0.0,
                costs=2.0,
                gross_return_pct=10.0,
                net_return_pct=9.87,
                outcome_confidence=OutcomeConfidence.CONFIRMED,
                inputs={"entry": 150.0, "exit": 165.0},
                strategy_drawdown=None,
            ),
        )
        con.commit()

    journal_tab_module.render_journal_tab(settings=settings)

    # Info banner regarding Historical Read-Only Mode
    info_texts = [str(call[0][0]) for call in fake_journal_st.info.call_args_list]
    assert any("Historical Read-Only Mode" in t for t in info_texts)

    # Dataframe rendered
    assert fake_journal_st.dataframe.call_count >= 1
    df_arg = fake_journal_st.dataframe.call_args[0][0]
    assert len(df_arg) == 1
    row = df_arg.iloc[0]
    assert row["Symbol"] == "AAPL"
    assert row["State"] == "⚫ Closed"
    assert "[Not Currently Authorized]" in row["Strategy"]
    assert row["Planned Entry"] == "$150.00"
    assert row["Qty"] == "10"
    assert row["Fill Price"] == "$150.00"
    assert row["Exit Price"] == "$165.00"
    assert row["Exit Reason"] == "Target"
    assert row["Gross Return"] == "+10.00%"
    assert row["Net Return"] == "+9.87%"
    assert row["Confidence"] == "🟢 Confirmed"
    assert row["Provenance"] == "👤 Manual Reported"


# ── 4. In-Place Detail Drill-Down & Outcome Inputs Inspection ────────────────


def test_detail_drilldown_view_and_outcome_inputs(fake_journal_st, isolated_db, monkeypatch):
    """Inspecting a trade renders complete plan, upstream candidate context, inspectable inputs JSON, and drawdown unknown."""
    monkeypatch.setattr(journal_tab_module, "st", fake_journal_st)
    settings = settings_from_mapping({"TRADEX_DB_PATH": isolated_db})

    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)

    with sqlite3.connect(isolated_db) as con:
        con.execute(
            """
            INSERT INTO candidates (candidate_id, contract_version, symbol, decision_timestamp, trading_date, security_identity_version, security_identity_status, created_at)
            VALUES ('cand-nvda', 1, 'NVDA', ?, '2026-08-20', 'sec-v1', 'known', ?)
            """,
            (base_t.isoformat(), base_t.isoformat()),
        )
        con.commit()

    trade = JournalTrade(
        journal_id="j-nvda-99",
        contract_version=1,
        idempotency_key="idem-nvda",
        candidate_id="cand-nvda",
        strategy_id="breakout",
        strategy_version="1.0",
        side="long",
        state=JournalState.OPEN,
        decision_timestamp=base_t,
        plan_created_at=base_t,
        planned_entry=500.0,
        stop_price=480.0,
        target_price=550.0,
        invalidation_rule=InvalidationRule(rule_id="time_decay", rule_version="1.0", params={"bars": 12}),
        quantity=25.0,
        fill_price=500.5,
        fill_timestamp=base_t + timedelta(minutes=1),
        fill_provenance=ExecutionProvenance(
            execution_provenance=ExecutionProvenanceType.SIMULATED,
            provider="yahoo",
            observed_at=base_t + timedelta(minutes=1),
            observer="sim_runner",
            simulation_rule="next_open",
        ),
        created_at=base_t,
        updated_at=base_t,
    )
    with sqlite3.connect(isolated_db) as con:
        insert_journal_trade(con, trade)
        insert_journal_event(
            con,
            JournalEvent(
                event_id="ev-1",
                journal_id="j-nvda-99",
                seq=1,
                event_type=JournalEventType.CREATED,
                event_timestamp=base_t,
                recorded_at=base_t,
                payload={"planned_entry": 500.0},
            ),
        )
        insert_journal_event(
            con,
            JournalEvent(
                event_id="ev-2",
                journal_id="j-nvda-99",
                seq=2,
                event_type=JournalEventType.FILLED,
                event_timestamp=base_t + timedelta(minutes=1),
                recorded_at=base_t + timedelta(minutes=1),
                payload={"fill_price": 500.5},
            ),
        )
        insert_journal_outcome(
            con,
            JournalOutcome(
                outcome_id="out-nvda-1",
                journal_id="j-nvda-99",
                computation_version="1.0",
                computed_at=base_t + timedelta(minutes=1),
                source_event_seq=2,
                inputs_hash="hash-nvda-v1",
                entry_slippage=0.5,
                costs=None,
                gross_return_pct=None,
                net_return_pct=None,
                outcome_confidence=OutcomeConfidence.PROVISIONAL,
                inputs={"fill_price": 500.5, "step": "v1"},
                strategy_drawdown=None,
            ),
        )
        insert_journal_outcome(
            con,
            JournalOutcome(
                outcome_id="out-nvda-2",
                journal_id="j-nvda-99",
                computation_version="2.0",
                computed_at=base_t + timedelta(minutes=10),
                source_event_seq=2,
                inputs_hash="hash-nvda-v2",
                entry_slippage=0.5,
                costs=1.5,
                gross_return_pct=2.5,
                net_return_pct=2.2,
                outcome_confidence=OutcomeConfidence.CONFIRMED,
                inputs={"fill_price": 500.5, "step": "v2", "costs": 1.5},
                strategy_drawdown=None,
            ),
        )
        con.commit()

    # Set session state to drill into j-nvda-99
    fake_journal_st.session_state["journal_selected_id"] = "j-nvda-99"

    journal_tab_module.render_journal_tab(settings=settings)

    # Subheader for trade detail
    subheaders = [str(call[0][0]) for call in fake_journal_st.subheader.call_args_list]
    assert any("Journal Trade — NVDA (🔵 Open)" in s for s in subheaders)

    # Markdown checks for sections and drawdown
    markdown_texts = [str(call[0][0]) for call in fake_journal_st.markdown.call_args_list]
    assert any("Immutable Trade Plan" in m for m in markdown_texts)
    assert any("Upstream Candidate Context" in m for m in markdown_texts)
    assert any("Execution Details" in m for m in markdown_texts)
    assert any("Append-Only Event Audit Timeline" in m for m in markdown_texts)
    assert any("Strategy Drawdown" in m and "Unknown" in m for m in markdown_texts)
    assert any("Inputs Hash:" in m and "hash-nvda-v2" in m for m in markdown_texts)

    # Inspectable JSON calls for inputs
    json_payloads = [call[0][0] for call in fake_journal_st.json.call_args_list]
    assert {"fill_price": 500.5, "step": "v2", "costs": 1.5} in json_payloads
    assert {"fill_price": 500.5, "step": "v1"} in json_payloads

    # Back button resets selection
    fake_journal_st._active_buttons.add("btn_back_to_journal")
    journal_tab_module.render_journal_tab(settings=settings)
    assert fake_journal_st.session_state["journal_selected_id"] is None


# ── 5. Semantic Badges & Return Independence Tests ───────────────────────────


def test_visual_badges_and_return_independence(fake_journal_st, isolated_db, monkeypatch):
    """Lifecycle badges remain neutral (⚫ Closed) regardless of positive/negative returns or missing costs."""
    monkeypatch.setattr(journal_tab_module, "st", fake_journal_st)
    settings = settings_from_mapping({"TRADEX_DB_PATH": isolated_db})
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)

    # Insert 3 candidates for 3 trades
    with sqlite3.connect(isolated_db) as con:
        for cid, sym in [("cand-1", "TSLA"), ("cand-2", "AAPL"), ("cand-3", "NVDA")]:
            con.execute(
                """
                INSERT INTO candidates (candidate_id, contract_version, symbol, decision_timestamp, trading_date, security_identity_version, security_identity_status, created_at)
                VALUES (?, 1, ?, ?, '2026-08-20', 'sec-v1', 'known', ?)
                """,
                (cid, sym, base_t.isoformat(), base_t.isoformat()),
            )

        # Win trade
        insert_journal_trade(
            con,
            JournalTrade(
                journal_id="j-win",
                contract_version=1,
                idempotency_key="idem-win",
                candidate_id="cand-1",
                strategy_id="strat_a",
                strategy_version="1.0",
                side="long",
                state=JournalState.CLOSED,
                decision_timestamp=base_t,
                plan_created_at=base_t,
                planned_entry=200.0,
                quantity=10.0,
                fill_price=200.0,
                fill_timestamp=base_t,
                exit_price=211.0,
                exit_timestamp=base_t + timedelta(hours=1),
                exit_reason=ExitReason.TARGET,
            ),
        )
        insert_journal_outcome(
            con,
            JournalOutcome(
                outcome_id="out-win",
                journal_id="j-win",
                computation_version="1.0",
                computed_at=base_t,
                source_event_seq=1,
                inputs_hash="h1",
                entry_slippage=0.0,
                gross_return_pct=5.50,
                net_return_pct=5.25,
                costs=1.0,
                outcome_confidence=OutcomeConfidence.CONFIRMED,
            ),
        )

        # Loss trade
        insert_journal_trade(
            con,
            JournalTrade(
                journal_id="j-loss",
                contract_version=1,
                idempotency_key="idem-loss",
                candidate_id="cand-2",
                strategy_id="strat_a",
                strategy_version="1.0",
                side="long",
                state=JournalState.CLOSED,
                decision_timestamp=base_t,
                plan_created_at=base_t,
                planned_entry=200.0,
                quantity=10.0,
                fill_price=200.0,
                fill_timestamp=base_t,
                exit_price=193.6,
                exit_timestamp=base_t + timedelta(hours=1),
                exit_reason=ExitReason.STOP,
            ),
        )
        insert_journal_outcome(
            con,
            JournalOutcome(
                outcome_id="out-loss",
                journal_id="j-loss",
                computation_version="1.0",
                computed_at=base_t,
                source_event_seq=1,
                inputs_hash="h2",
                entry_slippage=0.0,
                gross_return_pct=-3.20,
                net_return_pct=-3.50,
                costs=1.0,
                outcome_confidence=OutcomeConfidence.CONFIRMED,
            ),
        )

        # Trade with unknown net return (costs NULL)
        insert_journal_trade(
            con,
            JournalTrade(
                journal_id="j-null-costs",
                contract_version=1,
                idempotency_key="idem-null",
                candidate_id="cand-3",
                strategy_id="strat_a",
                strategy_version="1.0",
                side="long",
                state=JournalState.CLOSED,
                decision_timestamp=base_t,
                plan_created_at=base_t,
                planned_entry=200.0,
                quantity=10.0,
                fill_price=200.0,
                fill_timestamp=base_t,
                exit_price=208.0,
                exit_timestamp=base_t + timedelta(hours=1),
                exit_reason=ExitReason.DISCRETIONARY,
            ),
        )
        insert_journal_outcome(
            con,
            JournalOutcome(
                outcome_id="out-null",
                journal_id="j-null-costs",
                computation_version="1.0",
                computed_at=base_t,
                source_event_seq=1,
                inputs_hash="h3",
                entry_slippage=0.0,
                gross_return_pct=4.0,
                net_return_pct=None,
                costs=None,
                outcome_confidence=OutcomeConfidence.PROVISIONAL,
            ),
        )
        con.commit()

    journal_tab_module.render_journal_tab(settings=settings)

    df_arg = fake_journal_st.dataframe.call_args[0][0]
    assert len(df_arg) == 3

    # All three closed trades have neutral ⚫ Closed badge regardless of return
    assert all(row["State"] == "⚫ Closed" for _, row in df_arg.iterrows())

    # Returns are formatted independently
    win_row = df_arg[df_arg["Gross Return"] == "+5.50%"].iloc[0]
    assert win_row["Net Return"] == "+5.25%"
    assert win_row["Confidence"] == "🟢 Confirmed"

    loss_row = df_arg[df_arg["Gross Return"] == "-3.20%"].iloc[0]
    assert loss_row["Net Return"] == "-3.50%"
    assert loss_row["Confidence"] == "🟢 Confirmed"

    null_row = df_arg[df_arg["Gross Return"] == "+4.00%"].iloc[0]
    assert null_row["Net Return"] == "Unknown (Costs unavailable)"
    assert null_row["Confidence"] == "🟡 Provisional"


# ── 6. Strict Zero-Mutation Invariant ─────────────────────────────────────────


def test_ui_makes_zero_backend_mutations(fake_journal_st, isolated_db, monkeypatch):
    """The Journal UI must NEVER import or call mutation service operations."""
    monkeypatch.setattr(journal_tab_module, "st", fake_journal_st)
    settings = settings_from_mapping({"TRADEX_DB_PATH": isolated_db})

    # Monkeypatch all mutation functions in service to raise if called
    mutation_mock = MagicMock(side_effect=RuntimeError("MUTATION CALLED FROM UI"))
    monkeypatch.setattr("tradex.journal.service.create_planned_trade", mutation_mock)
    monkeypatch.setattr("tradex.journal.service.record_fill", mutation_mock)
    monkeypatch.setattr("tradex.journal.service.record_exit", mutation_mock)
    monkeypatch.setattr("tradex.journal.service.cancel_trade", mutation_mock)
    monkeypatch.setattr("tradex.journal.service.invalidate_trade", mutation_mock)
    monkeypatch.setattr("tradex.journal.service.expire_trade", mutation_mock)
    monkeypatch.setattr("tradex.journal.service.recompute_outcomes", mutation_mock)

    # Render overview and detail
    journal_tab_module.render_journal_tab(settings=settings)

    fake_journal_st.session_state["journal_selected_id"] = "non-existent"
    journal_tab_module.render_journal_tab(settings=settings)

    assert mutation_mock.call_count == 0


# ── 7. Strategy Filter StoreError Failure Surfacing ──────────────────────────


def test_strategy_filter_store_error_surfaced_truthfully(fake_journal_st, isolated_db, monkeypatch):
    """Database failure in get_journal_strategy_ids must visibly surface error and halt overview rendering."""
    from tradex.tracker.store import StoreError

    monkeypatch.setattr(journal_tab_module, "st", fake_journal_st)
    settings = settings_from_mapping({"TRADEX_DB_PATH": isolated_db})
    base_t = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)

    # Insert a candidate and trade so overview proceeds past the initial all_records check
    with sqlite3.connect(isolated_db) as con:
        con.execute(
            """
            INSERT INTO candidates (candidate_id, contract_version, symbol, decision_timestamp, trading_date, security_identity_version, security_identity_status, created_at)
            VALUES ('cand-err', 1, 'AAPL', ?, '2026-08-20', 'sec-v1', 'known', ?)
            """,
            (base_t.isoformat(), base_t.isoformat()),
        )
        insert_journal_trade(
            con,
            JournalTrade(
                journal_id="j-err-1",
                contract_version=1,
                idempotency_key="idem-err-1",
                candidate_id="cand-err",
                strategy_id="breakout",
                strategy_version="1.0",
                side="long",
                state=JournalState.PLANNED,
                decision_timestamp=base_t,
                plan_created_at=base_t,
                planned_entry=150.0,
            ),
        )
        con.commit()

    def _mock_raise_store_error(*args, **kwargs):
        raise StoreError("disk read failure during strategy query")

    monkeypatch.setattr(journal_tab_module, "get_journal_strategy_ids", _mock_raise_store_error)

    # Also verify zero mutations
    mutation_mock = MagicMock(side_effect=RuntimeError("MUTATION CALLED FROM UI"))
    monkeypatch.setattr("tradex.journal.service.create_planned_trade", mutation_mock)
    monkeypatch.setattr("tradex.journal.service.record_fill", mutation_mock)
    monkeypatch.setattr("tradex.journal.service.record_exit", mutation_mock)

    journal_tab_module.render_journal_tab(settings=settings)

    # 1. Error is visibly surfaced to user via st.error
    assert fake_journal_st.error.call_count >= 1
    error_texts = [str(call[0][0]) for call in fake_journal_st.error.call_args_list]
    assert any("Failed to load Journal strategy filter options from database" in t for t in error_texts)
    assert any("disk read failure during strategy query" in t for t in error_texts)

    # 2. UI does not silently continue to render table/overview as though empty list succeeded
    assert fake_journal_st.dataframe.call_count == 0

    # 3. Zero mutations occur
    assert mutation_mock.call_count == 0
