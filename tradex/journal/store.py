"""SQLite persistence primitives and row mapping for executable Journal (MVP-ARCH-001-R6).

Implements neutral, deterministic reads, append-only event writes, versioned outcome writes,
and trade persistence according to the Schema v5 DDL contract.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from tradex.journal.models import (
    ExecutionProvenance,
    InvalidationRule,
    JournalEvent,
    JournalOutcome,
    JournalTrade,
)


def _serialize_invalidation_rule(rule: InvalidationRule | None) -> str | None:
    if rule is None:
        return None
    return json.dumps(
        {
            "rule_id": rule.rule_id,
            "rule_version": rule.rule_version,
            "params": rule.params,
        },
        sort_keys=True,
    )


def _deserialize_invalidation_rule(raw: str | None) -> InvalidationRule | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return InvalidationRule(
                rule_id=data["rule_id"],
                rule_version=data["rule_version"],
                params=data.get("params", {}),
            )
    except Exception:  # noqa: BLE001
        return None
    return None


def _serialize_provenance(prov: ExecutionProvenance | None) -> str | None:
    if prov is None:
        return None
    return json.dumps(
        {
            "execution_provenance": (
                prov.execution_provenance.value
                if hasattr(prov.execution_provenance, "value")
                else str(prov.execution_provenance)
            ),
            "provider": prov.provider,
            "observed_at": prov.observed_at.isoformat(),
            "observer": prov.observer,
            "simulation_rule": prov.simulation_rule,
        },
        sort_keys=True,
    )


def _deserialize_provenance(raw: str | None) -> ExecutionProvenance | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            obs_dt = datetime.fromisoformat(data["observed_at"])
            if obs_dt.tzinfo is None:
                obs_dt = obs_dt.replace(tzinfo=UTC)
            return ExecutionProvenance(
                execution_provenance=data["execution_provenance"],
                provider=data.get("provider", "unknown"),
                observed_at=obs_dt,
                observer=data.get("observer", ""),
                simulation_rule=data.get("simulation_rule"),
            )
    except Exception:  # noqa: BLE001
        return None
    return None


def _parse_dt(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _row_to_trade(row: sqlite3.Row) -> JournalTrade:
    dec_ts = _parse_dt(row["decision_timestamp"])
    plan_created = _parse_dt(row["plan_created_at"])
    created_at = _parse_dt(row["created_at"])
    updated_at = _parse_dt(row["updated_at"])
    fill_ts = _parse_dt(row["fill_timestamp"])
    exit_ts = _parse_dt(row["exit_timestamp"])
    exp = _parse_dt(row["expiration"])

    assert dec_ts is not None
    assert plan_created is not None
    assert created_at is not None
    assert updated_at is not None

    return JournalTrade(
        journal_id=row["journal_id"],
        contract_version=row["contract_version"],
        idempotency_key=row["idempotency_key"],
        candidate_id=row["candidate_id"],
        strategy_id=row["strategy_id"],
        strategy_version=row["strategy_version"],
        side=row["side"],
        state=row["state"],
        decision_timestamp=dec_ts,
        plan_created_at=plan_created,
        planned_entry=row["planned_entry"],
        stop_price=row["stop_price"],
        target_price=row["target_price"],
        expiration=exp,
        invalidation_rule=_deserialize_invalidation_rule(row["invalidation_rule"]),
        quantity=row["quantity"],
        fill_price=row["fill_price"],
        fill_timestamp=fill_ts,
        fill_provenance=_deserialize_provenance(row["fill_provenance"]),
        exit_price=row["exit_price"],
        exit_timestamp=exit_ts,
        exit_reason=row["exit_reason"],
        exit_provenance=_deserialize_provenance(row["exit_provenance"]),
        terminal_reason=row["terminal_reason"],
        created_at=created_at,
        updated_at=updated_at,
    )


def _row_to_event(row: sqlite3.Row) -> JournalEvent:
    ev_ts = _parse_dt(row["event_timestamp"])
    rec_at = _parse_dt(row["recorded_at"])
    assert ev_ts is not None
    assert rec_at is not None

    payload: dict[str, Any] = {}
    if row["payload_json"]:
        try:
            payload = json.loads(row["payload_json"])
        except Exception:  # noqa: BLE001
            payload = {}

    return JournalEvent(
        event_id=row["event_id"],
        journal_id=row["journal_id"],
        seq=row["seq"],
        event_type=row["event_type"],
        event_timestamp=ev_ts,
        recorded_at=rec_at,
        payload=payload,
    )


def _row_to_outcome(row: sqlite3.Row) -> JournalOutcome:
    comp_at = _parse_dt(row["computed_at"])
    assert comp_at is not None

    inputs: dict[str, Any] = {}
    if row["inputs_json"]:
        try:
            inputs = json.loads(row["inputs_json"])
        except Exception:  # noqa: BLE001
            inputs = {}

    return JournalOutcome(
        outcome_id=row["outcome_id"],
        journal_id=row["journal_id"],
        computation_version=row["computation_version"],
        computed_at=comp_at,
        source_event_seq=row["source_event_seq"],
        inputs_hash=row["inputs_hash"],
        entry_slippage=row["entry_slippage"],
        costs=row["costs"],
        gross_return_pct=row["gross_return_pct"],
        net_return_pct=row["net_return_pct"],
        outcome_confidence=row["outcome_confidence"],
        inputs=inputs,
        strategy_drawdown=None,
    )


# ── Persistence Primitives ───────────────────────────────────────────────────


def insert_journal_trade(con: sqlite3.Connection, trade: JournalTrade) -> None:
    """Insert a new journal_trades row."""
    con.execute(
        """
        INSERT INTO journal_trades (
            journal_id, contract_version, idempotency_key, candidate_id,
            strategy_id, strategy_version, side, state,
            decision_timestamp, plan_created_at, planned_entry, stop_price,
            target_price, expiration, invalidation_rule, quantity,
            fill_price, fill_timestamp, fill_provenance,
            exit_price, exit_timestamp, exit_reason, exit_provenance,
            terminal_reason, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?
        )
        """,
        (
            trade.journal_id,
            trade.contract_version,
            trade.idempotency_key,
            trade.candidate_id,
            trade.strategy_id,
            trade.strategy_version,
            trade.side,
            trade.state.value if hasattr(trade.state, "value") else str(trade.state),
            trade.decision_timestamp.isoformat(),
            trade.plan_created_at.isoformat(),
            trade.planned_entry,
            trade.stop_price,
            trade.target_price,
            trade.expiration.isoformat() if trade.expiration else None,
            _serialize_invalidation_rule(trade.invalidation_rule),
            trade.quantity,
            trade.fill_price,
            trade.fill_timestamp.isoformat() if trade.fill_timestamp else None,
            _serialize_provenance(trade.fill_provenance),
            trade.exit_price,
            trade.exit_timestamp.isoformat() if trade.exit_timestamp else None,
            (
                trade.exit_reason.value
                if hasattr(trade.exit_reason, "value")
                else (str(trade.exit_reason) if trade.exit_reason else None)
            ),
            _serialize_provenance(trade.exit_provenance),
            trade.terminal_reason,
            trade.created_at.isoformat(),
            trade.updated_at.isoformat(),
        ),
    )


def update_journal_trade(con: sqlite3.Connection, trade: JournalTrade) -> None:
    """Update mutable execution and state fields on an existing journal_trades row."""
    con.execute(
        """
        UPDATE journal_trades
        SET state = ?,
            quantity = ?,
            fill_price = ?,
            fill_timestamp = ?,
            fill_provenance = ?,
            exit_price = ?,
            exit_timestamp = ?,
            exit_reason = ?,
            exit_provenance = ?,
            terminal_reason = ?,
            updated_at = ?
        WHERE journal_id = ?
        """,
        (
            trade.state.value if hasattr(trade.state, "value") else str(trade.state),
            trade.quantity,
            trade.fill_price,
            trade.fill_timestamp.isoformat() if trade.fill_timestamp else None,
            _serialize_provenance(trade.fill_provenance),
            trade.exit_price,
            trade.exit_timestamp.isoformat() if trade.exit_timestamp else None,
            (
                trade.exit_reason.value
                if hasattr(trade.exit_reason, "value")
                else (str(trade.exit_reason) if trade.exit_reason else None)
            ),
            _serialize_provenance(trade.exit_provenance),
            trade.terminal_reason,
            trade.updated_at.isoformat(),
            trade.journal_id,
        ),
    )


def insert_journal_event(con: sqlite3.Connection, event: JournalEvent) -> None:
    """Append a new event to journal_events. Application code never updates/deletes events."""
    con.execute(
        """
        INSERT INTO journal_events (
            event_id, journal_id, seq, event_type, event_timestamp, recorded_at, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id,
            event.journal_id,
            event.seq,
            (
                event.event_type.value
                if hasattr(event.event_type, "value")
                else str(event.event_type)
            ),
            event.event_timestamp.isoformat(),
            event.recorded_at.isoformat(),
            json.dumps(event.payload, sort_keys=True),
        ),
    )


def insert_journal_outcome(con: sqlite3.Connection, outcome: JournalOutcome) -> None:
    """Insert a versioned outcome row into journal_outcomes."""
    con.execute(
        """
        INSERT INTO journal_outcomes (
            outcome_id, journal_id, computation_version, computed_at,
            source_event_seq, inputs_hash, entry_slippage, costs,
            gross_return_pct, net_return_pct, outcome_confidence, inputs_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            outcome.outcome_id,
            outcome.journal_id,
            outcome.computation_version,
            outcome.computed_at.isoformat(),
            outcome.source_event_seq,
            outcome.inputs_hash,
            outcome.entry_slippage,
            outcome.costs,
            outcome.gross_return_pct,
            outcome.net_return_pct,
            (
                outcome.outcome_confidence.value
                if hasattr(outcome.outcome_confidence, "value")
                else str(outcome.outcome_confidence)
            ),
            json.dumps(outcome.inputs, sort_keys=True),
        ),
    )


# ── Query Functions ──────────────────────────────────────────────────────────


def get_journal_trade_by_id(con: sqlite3.Connection, journal_id: str) -> JournalTrade | None:
    """Query a single journal trade by journal_id."""
    row = con.execute(
        "SELECT * FROM journal_trades WHERE journal_id = ?", (journal_id,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_trade(row)


def get_journal_trade_by_idempotency_key(
    con: sqlite3.Connection, idempotency_key: str
) -> JournalTrade | None:
    """Query a journal trade by unique idempotency_key."""
    row = con.execute(
        "SELECT * FROM journal_trades WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_trade(row)


def get_journal_trade_by_candidate_strategy(
    con: sqlite3.Connection,
    candidate_id: str,
    strategy_id: str,
    strategy_version: str,
) -> JournalTrade | None:
    """Query a journal trade by candidate_id and strategy identity."""
    row = con.execute(
        """
        SELECT * FROM journal_trades
        WHERE candidate_id = ? AND strategy_id = ? AND strategy_version = ?
        """,
        (candidate_id, strategy_id, strategy_version),
    ).fetchone()
    if row is None:
        return None
    return _row_to_trade(row)


def list_journal_trades(
    con: sqlite3.Connection,
    *,
    state: str | None = None,
    strategy_id: str | None = None,
    candidate_id: str | None = None,
    limit: int = 100,
) -> list[JournalTrade]:
    """Query journal trades ordered deterministically by plan_created_at DESC, journal_id ASC."""
    query = "SELECT * FROM journal_trades WHERE 1=1"
    params: list[Any] = []

    if state is not None:
        query += " AND state = ?"
        params.append(state.strip().lower())
    if strategy_id is not None:
        query += " AND strategy_id = ?"
        params.append(strategy_id.strip())
    if candidate_id is not None:
        query += " AND candidate_id = ?"
        params.append(candidate_id.strip())

    query += " ORDER BY plan_created_at DESC, journal_id ASC LIMIT ?"
    params.append(max(1, limit))

    rows = con.execute(query, params).fetchall()
    return [_row_to_trade(r) for r in rows]


def get_journal_events(con: sqlite3.Connection, journal_id: str) -> list[JournalEvent]:
    """Query append-only events for a trade ordered deterministically by seq ASC."""
    rows = con.execute(
        "SELECT * FROM journal_events WHERE journal_id = ? ORDER BY seq ASC", (journal_id,)
    ).fetchall()
    return [_row_to_event(r) for r in rows]


def get_latest_event_seq(con: sqlite3.Connection, journal_id: str) -> int:
    """Return the highest seq number present for journal_id, or 0 if none exist."""
    row = con.execute(
        "SELECT MAX(seq) FROM journal_events WHERE journal_id = ?", (journal_id,)
    ).fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def list_journal_outcomes(
    con: sqlite3.Connection, journal_id: str, limit: int = 100
) -> list[JournalOutcome]:
    """Query versioned outcomes for a trade ordered deterministically by computed_at DESC, outcome_id ASC."""
    rows = con.execute(
        """
        SELECT * FROM journal_outcomes
        WHERE journal_id = ?
        ORDER BY computed_at DESC, outcome_id ASC
        LIMIT ?
        """,
        (journal_id, max(1, limit)),
    ).fetchall()
    return [_row_to_outcome(r) for r in rows]


def get_latest_journal_outcome(
    con: sqlite3.Connection, journal_id: str
) -> JournalOutcome | None:
    """Return the latest outcome under the deterministic ordering (computed_at DESC, outcome_id ASC)."""
    outcomes = list_journal_outcomes(con, journal_id, limit=1)
    if not outcomes:
        return None
    return outcomes[0]
