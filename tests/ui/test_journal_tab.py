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


# ── 2. True Empty State UX ───────────────────────────────────────────────────


def test_true_empty_state_rendering(fake_journal_st, isolated_db, monkeypatch):
    """Zero records and empty strategy registry renders truthful explanation with no create controls."""
    monkeypatch.setattr(journal_tab_module, "st", fake_journal_st)
    settings = settings_from_mapping({"TRADEX_DB_PATH": isolated_db})

    journal_tab_module.render_journal_tab(settings=settings)

    fake_journal_st.subheader.assert_called_once_with("Journal")
    fake_journal_st.caption.assert_called_once_with("Executable Strategy Journal")

    info_texts = [str(call[0][0]) for call in fake_journal_st.info.call_args_list]
    assert any("No production-approved executable strategy" in t for t in info_texts)
    assert any("Legacy scanner outcomes remain available as descriptive telemetry" in t for t in info_texts)

    # No tables or drill-down buttons in empty state
    assert fake_journal_st.dataframe.call_count == 0
    assert "btn_view_journal_detail" not in fake_journal_st._active_buttons


# ── 3. Historical Read-Only Mode Overview ────────────────────────────────────


def test_historical_overview_rendering(fake_journal_st, isolated_db, monkeypatch):
    """Persisted records with empty strategy registry show historical banner, table, and unauthorized tags."""
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
                inputs={},
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
    assert row["State"] == "Closed"
    assert "[Not Currently Authorized]" in row["Strategy"]
    assert row["Planned Entry"] == "$150.00"
    assert row["Qty"] == "10"
    assert row["Fill Price"] == "$150.00"
    assert row["Exit Price"] == "$165.00"
    assert row["Exit Reason"] == "Target"
    assert row["Gross Return"] == "+10.00%"
    assert row["Net Return"] == "+9.87%"
    assert row["Confidence"] == "Confirmed"
    assert row["Provenance"] == "Manual Reported"


# ── 4. In-Place Detail Drill-Down UX ─────────────────────────────────────────


def test_detail_drilldown_view(fake_journal_st, isolated_db, monkeypatch):
    """Inspecting a trade renders complete plan, upstream candidate context, events, outcomes, and drawdown unknown."""
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
                inputs_hash="hash-nvda",
                entry_slippage=0.5,
                costs=None,
                gross_return_pct=None,
                net_return_pct=None,
                outcome_confidence=OutcomeConfidence.PROVISIONAL,
                inputs={},
                strategy_drawdown=None,
            ),
        )
        con.commit()

    # Set session state to drill into j-nvda-99
    fake_journal_st.session_state["journal_selected_id"] = "j-nvda-99"

    journal_tab_module.render_journal_tab(settings=settings)

    # Subheader for trade detail
    subheaders = [str(call[0][0]) for call in fake_journal_st.subheader.call_args_list]
    assert any("Journal Trade — NVDA (Open)" in s for s in subheaders)

    # Markdown checks for sections
    markdown_texts = [str(call[0][0]) for call in fake_journal_st.markdown.call_args_list]
    assert any("Immutable Trade Plan" in m for m in markdown_texts)
    assert any("Upstream Candidate Context" in m for m in markdown_texts)
    assert any("Execution Details" in m for m in markdown_texts)
    assert any("Append-Only Event Audit Timeline" in m for m in markdown_texts)
    assert any("Strategy Drawdown" in m and "Unknown" in m for m in markdown_texts)

    # Back button resets selection
    fake_journal_st._active_buttons.add("btn_back_to_journal")
    journal_tab_module.render_journal_tab(settings=settings)
    assert fake_journal_st.session_state["journal_selected_id"] is None


# ── 5. Strict Zero-Mutation Invariant ─────────────────────────────────────────


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
