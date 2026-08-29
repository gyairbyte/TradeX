"""Read-only query and read-model projection layer for executable Journal (MVP-ARCH-001-R6-IMPL-B).

Provides deterministic, immutable read-models and SQLite queries over persisted
journal_trades, journal_events, journal_outcomes, and linked candidate snapshots.
Makes zero network or provider calls and performs zero database mutations.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tradex.journal.models import (
    ExecutionProvenance,
    ExecutionProvenanceType,
    InvalidationRule,
    JournalState,
    OutcomeConfidence,
)
from tradex.journal.store import (
    _deserialize_invalidation_rule,
    _deserialize_provenance,
    _parse_dt,
)
from tradex.market.hours import MARKET_TIMEZONE, normalize_market_datetime
from tradex.strategies.registry import has_production_strategy_capability
from tradex.tracker.store import StoreError, _conn, _resolve_db_path

if TYPE_CHECKING:
    from tradex.candidates.models import CandidateSnapshot
    from tradex.config import TradeXSettings


def _format_market_time(dt: datetime | None, *, include_date: bool = False) -> str:
    """Format a UTC datetime in America/New_York (ET)."""
    if dt is None:
        return "—"
    try:
        ny_dt = normalize_market_datetime(dt)
        if include_date:
            return ny_dt.strftime("%b %d, %Y %I:%M %p ET")
        return ny_dt.strftime("%I:%M %p ET")
    except (ValueError, TypeError):
        ny_dt = dt.astimezone(MARKET_TIMEZONE)
        if include_date:
            return ny_dt.strftime("%b %d, %Y %I:%M %p ET")
        return ny_dt.strftime("%I:%M %p ET")


def format_lifecycle_state_label(state: JournalState | str | None) -> str:
    """Map raw lifecycle state to authoritative user-facing label."""
    if state is None:
        return "Unknown"
    clean = state.value if isinstance(state, JournalState) else str(state).strip().lower()
    mapping = {
        "planned": "Planned",
        "open": "Open",
        "closed": "Closed",
        "cancelled": "Cancelled",
        "expired": "Expired",
        "invalidated": "Invalidated",
    }
    return mapping.get(clean, clean.title() if clean else "Unknown")


def format_lifecycle_state_badge(state: JournalState | str | None) -> str:
    """Map raw lifecycle state to visually distinct neutral/state badge."""
    if state is None:
        return "⚪ Unknown"
    clean = state.value if isinstance(state, JournalState) else str(state).strip().lower()
    mapping = {
        "planned": "⚪ Planned",
        "open": "🔵 Open",
        "closed": "⚫ Closed",
        "cancelled": "✖ Cancelled",
        "expired": "⏳ Expired",
        "invalidated": "🚫 Invalidated",
    }
    return mapping.get(clean, f"⚪ {clean.title()}" if clean else "⚪ Unknown")


def format_provenance_label(
    prov: ExecutionProvenance | ExecutionProvenanceType | str | None,
) -> str:
    """Map ExecutionProvenance, enum, or string to user-facing text label."""
    if prov is None:
        return "—"
    if isinstance(prov, ExecutionProvenance):
        ptype = (
            prov.execution_provenance.value
            if isinstance(prov.execution_provenance, ExecutionProvenanceType)
            else str(prov.execution_provenance).strip().lower()
        )
    elif isinstance(prov, ExecutionProvenanceType):
        ptype = prov.value
    else:
        ptype = str(prov).strip().lower()

    if ptype == "manual":
        return "Manual Reported"
    if ptype == "simulated":
        return "Simulated"
    if ptype == "broker_confirmed":
        return "Broker Confirmed"
    return ptype.replace("_", " ").title() if ptype else "—"


def format_provenance_badge(
    prov: ExecutionProvenance | ExecutionProvenanceType | str | None,
) -> str:
    """Map ExecutionProvenance, enum, or string to visually distinct badge."""
    if prov is None:
        return "—"
    label = format_provenance_label(prov)
    if label == "Manual Reported":
        return "👤 Manual Reported"
    if label == "Simulated":
        return "🧪 Simulated"
    if label == "Broker Confirmed":
        return "🏦 Broker Confirmed"
    return f"🏷️ {label}" if label != "—" else "—"


def format_confidence_label(conf: OutcomeConfidence | str | None) -> str:
    """Map OutcomeConfidence or string to user-facing text label."""
    if conf is None:
        return "—"
    clean = conf.value if isinstance(conf, OutcomeConfidence) else str(conf).strip().lower()
    if clean == "confirmed":
        return "Confirmed"
    if clean == "provisional":
        return "Provisional"
    if clean == "unknown":
        return "Unknown"
    return clean.title() if clean else "—"


def format_confidence_badge(conf: OutcomeConfidence | str | None) -> str:
    """Map OutcomeConfidence or string to visually distinct badge."""
    if conf is None:
        return "—"
    clean = conf.value if isinstance(conf, OutcomeConfidence) else str(conf).strip().lower()
    if clean == "confirmed":
        return "🟢 Confirmed"
    if clean == "provisional":
        return "🟡 Provisional"
    if clean == "unknown":
        return "⚪ Unknown"
    return f"⚪ {clean.title()}" if clean else "—"


# ── Read Models ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class JournalTradeReadModel:
    """Immutable view-model representing one journal trade row in the overview table."""

    journal_id: str
    candidate_id: str
    symbol: str
    state: str
    strategy_id: str
    strategy_version: str
    side: str
    planned_entry: float
    decision_timestamp: datetime
    plan_created_at: datetime
    is_strategy_authorized: bool
    quantity: float | None = None
    fill_price: float | None = None
    fill_timestamp: datetime | None = None
    fill_provenance: ExecutionProvenance | None = None
    stop_price: float | None = None
    target_price: float | None = None
    expiration: datetime | None = None
    invalidation_rule: InvalidationRule | None = None
    exit_price: float | None = None
    exit_timestamp: datetime | None = None
    exit_reason: str | None = None
    exit_provenance: ExecutionProvenance | None = None
    terminal_reason: str | None = None
    gross_return_pct: float | None = None
    net_return_pct: float | None = None
    outcome_confidence: str | None = None
    current_outcome_id: str | None = None
    costs: float | None = None
    entry_slippage: float | None = None

    @property
    def formatted_state(self) -> str:
        return format_lifecycle_state_label(self.state)

    @property
    def formatted_state_badge(self) -> str:
        return format_lifecycle_state_badge(self.state)

    @property
    def formatted_planned_entry(self) -> str:
        return f"${self.planned_entry:.2f}"

    @property
    def formatted_fill_price(self) -> str:
        if self.fill_price is not None:
            return f"${self.fill_price:.2f}"
        return "—"

    @property
    def formatted_quantity(self) -> str:
        if self.quantity is not None:
            if self.quantity.is_integer():
                return str(int(self.quantity))
            return f"{self.quantity:.2f}"
        return "—"

    @property
    def formatted_stop_price(self) -> str:
        if self.stop_price is not None:
            return f"${self.stop_price:.2f}"
        return "—"

    @property
    def formatted_target_price(self) -> str:
        if self.target_price is not None:
            return f"${self.target_price:.2f}"
        return "—"

    @property
    def formatted_exit_price(self) -> str:
        if self.exit_price is not None:
            return f"${self.exit_price:.2f}"
        return "—"

    @property
    def formatted_exit_reason(self) -> str:
        if self.exit_reason is not None:
            return str(self.exit_reason).replace("_", " ").title()
        return "—"

    @property
    def formatted_gross_return(self) -> str:
        if self.gross_return_pct is not None:
            return f"{self.gross_return_pct:+.2f}%"
        return "—"

    @property
    def formatted_net_return(self) -> str:
        if self.state.lower() == "closed":
            if self.net_return_pct is not None:
                return f"{self.net_return_pct:+.2f}%"
            return "Unknown (Costs unavailable)"
        return "—"

    @property
    def formatted_confidence(self) -> str:
        return format_confidence_label(self.outcome_confidence)

    @property
    def formatted_confidence_badge(self) -> str:
        return format_confidence_badge(self.outcome_confidence)

    @property
    def formatted_fill_provenance(self) -> str:
        return format_provenance_label(self.fill_provenance)

    @property
    def formatted_fill_provenance_badge(self) -> str:
        return format_provenance_badge(self.fill_provenance)

    @property
    def formatted_exit_provenance(self) -> str:
        return format_provenance_label(self.exit_provenance)

    @property
    def formatted_exit_provenance_badge(self) -> str:
        return format_provenance_badge(self.exit_provenance)

    @property
    def formatted_decision_time(self) -> str:
        return _format_market_time(self.decision_timestamp, include_date=True)

    @property
    def formatted_strategy(self) -> str:
        return f"{self.strategy_id} {self.strategy_version}"


@dataclass(frozen=True, slots=True)
class JournalEventStreamReadModel:
    """Immutable view-model representing one append-only lifecycle event."""

    event_id: str
    journal_id: str
    seq: int
    event_type: str
    event_timestamp: datetime
    recorded_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def formatted_event_type(self) -> str:
        return self.event_type.replace("_", " ").title()

    @property
    def formatted_event_timestamp(self) -> str:
        return _format_market_time(self.event_timestamp, include_date=True)

    @property
    def formatted_recorded_at(self) -> str:
        return _format_market_time(self.recorded_at, include_date=True)


@dataclass(frozen=True, slots=True)
class JournalOutcomeAuditReadModel:
    """Immutable view-model representing one versioned outcome computation record."""

    outcome_id: str
    journal_id: str
    computation_version: str
    computed_at: datetime
    source_event_seq: int
    inputs_hash: str
    entry_slippage: float | None
    costs: float | None
    gross_return_pct: float | None
    net_return_pct: float | None
    outcome_confidence: str
    inputs: dict[str, Any] = field(default_factory=dict)
    strategy_drawdown: float | None = None  # Always None in R6 v1

    @property
    def formatted_computed_at(self) -> str:
        return _format_market_time(self.computed_at, include_date=True)

    @property
    def formatted_confidence(self) -> str:
        return format_confidence_label(self.outcome_confidence)

    @property
    def formatted_confidence_badge(self) -> str:
        return format_confidence_badge(self.outcome_confidence)

    @property
    def formatted_gross_return(self) -> str:
        if self.gross_return_pct is not None:
            return f"{self.gross_return_pct:+.2f}%"
        return "—"

    @property
    def formatted_net_return(self) -> str:
        if self.net_return_pct is not None:
            return f"{self.net_return_pct:+.2f}%"
        return "Unknown (Costs unavailable)"


@dataclass(frozen=True, slots=True)
class JournalDetailReadModel:
    """Immutable view-model representing complete trade detail for drill-down inspection."""

    trade: JournalTradeReadModel
    symbol: str
    is_strategy_authorized: bool
    candidate_snapshot: CandidateSnapshot | None
    candidate_evidence_summary: dict[str, Any]
    current_outcome: JournalOutcomeAuditReadModel | None
    events: list[JournalEventStreamReadModel]
    outcomes: list[JournalOutcomeAuditReadModel]


# ── Query Functions ──────────────────────────────────────────────────────────


def list_journal_read_models(
    *,
    state: str | None = None,
    strategy_id: str | None = None,
    symbol: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db_path: Path | str | None = None,
    settings: TradeXSettings | None = None,
) -> list[JournalTradeReadModel]:
    """Query overview projections sorted deterministically by plan_created_at DESC, journal_id ASC.

    Joins journal_trades with candidates table for symbol and deterministically selects the latest
    outcome via window ranking on (computed_at DESC, outcome_id ASC).
    """
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    limit_val = max(1, limit)
    offset_val = max(0, offset)

    # SQLite window function query for deterministic current outcome selection
    sql = """
        WITH latest_outcomes AS (
            SELECT
                outcome_id,
                journal_id,
                computation_version,
                computed_at,
                source_event_seq,
                inputs_hash,
                entry_slippage,
                costs,
                gross_return_pct,
                net_return_pct,
                outcome_confidence,
                ROW_NUMBER() OVER (
                    PARTITION BY journal_id
                    ORDER BY computed_at DESC, outcome_id ASC
                ) AS rn
            FROM journal_outcomes
        )
        SELECT
            t.journal_id,
            t.contract_version,
            t.idempotency_key,
            t.candidate_id,
            t.strategy_id,
            t.strategy_version,
            t.side,
            t.state,
            t.decision_timestamp,
            t.plan_created_at,
            t.planned_entry,
            t.stop_price,
            t.target_price,
            t.expiration,
            t.invalidation_rule,
            t.quantity,
            t.fill_price,
            t.fill_timestamp,
            t.fill_provenance,
            t.exit_price,
            t.exit_timestamp,
            t.exit_reason,
            t.exit_provenance,
            t.terminal_reason,
            c.symbol AS candidate_symbol,
            o.outcome_id AS current_outcome_id,
            o.gross_return_pct,
            o.net_return_pct,
            o.outcome_confidence,
            o.costs,
            o.entry_slippage
        FROM journal_trades t
        LEFT JOIN candidates c ON c.candidate_id = t.candidate_id
        LEFT JOIN latest_outcomes o ON o.journal_id = t.journal_id AND o.rn = 1
        WHERE 1=1
    """

    params: list[Any] = []
    if state is not None and state.strip() and state.strip().lower() != "all":
        sql += " AND LOWER(t.state) = ?"
        params.append(state.strip().lower())

    if strategy_id is not None and strategy_id.strip() and strategy_id.strip().lower() != "all":
        sql += " AND t.strategy_id = ?"
        params.append(strategy_id.strip())

    if symbol is not None and symbol.strip():
        clean_sym = symbol.strip().upper()
        sql += " AND (c.symbol = ? OR c.symbol LIKE ?)"
        params.extend([clean_sym, f"{clean_sym}%"])

    sql += " ORDER BY t.plan_created_at DESC, t.journal_id ASC LIMIT ? OFFSET ?"
    params.extend([limit_val, offset_val])

    try:
        with _conn(db_path=path) as con:
            rows = con.execute(sql, params).fetchall()
            results: list[JournalTradeReadModel] = []

            for row in rows:
                dec_ts = _parse_dt(row["decision_timestamp"])
                plan_ts = _parse_dt(row["plan_created_at"])
                fill_ts = _parse_dt(row["fill_timestamp"])
                exit_ts = _parse_dt(row["exit_timestamp"])
                exp_ts = _parse_dt(row["expiration"])

                assert dec_ts is not None
                assert plan_ts is not None

                strat_id = str(row["strategy_id"])
                strat_ver = str(row["strategy_version"])
                is_authorized = has_production_strategy_capability(
                    strat_id, strat_ver, "journal_execution"
                )

                sym = str(row["candidate_symbol"] or "UNKNOWN")

                results.append(
                    JournalTradeReadModel(
                        journal_id=row["journal_id"],
                        candidate_id=row["candidate_id"],
                        symbol=sym,
                        state=row["state"],
                        strategy_id=strat_id,
                        strategy_version=strat_ver,
                        side=row["side"],
                        planned_entry=float(row["planned_entry"]),
                        decision_timestamp=dec_ts,
                        plan_created_at=plan_ts,
                        is_strategy_authorized=is_authorized,
                        quantity=(
                            float(row["quantity"]) if row["quantity"] is not None else None
                        ),
                        fill_price=(
                            float(row["fill_price"]) if row["fill_price"] is not None else None
                        ),
                        fill_timestamp=fill_ts,
                        fill_provenance=_deserialize_provenance(row["fill_provenance"]),
                        stop_price=(
                            float(row["stop_price"]) if row["stop_price"] is not None else None
                        ),
                        target_price=(
                            float(row["target_price"]) if row["target_price"] is not None else None
                        ),
                        expiration=exp_ts,
                        invalidation_rule=_deserialize_invalidation_rule(row["invalidation_rule"]),
                        exit_price=(
                            float(row["exit_price"]) if row["exit_price"] is not None else None
                        ),
                        exit_timestamp=exit_ts,
                        exit_reason=row["exit_reason"],
                        exit_provenance=_deserialize_provenance(row["exit_provenance"]),
                        terminal_reason=row["terminal_reason"],
                        gross_return_pct=(
                            float(row["gross_return_pct"])
                            if row["gross_return_pct"] is not None
                            else None
                        ),
                        net_return_pct=(
                            float(row["net_return_pct"])
                            if row["net_return_pct"] is not None
                            else None
                        ),
                        outcome_confidence=row["outcome_confidence"],
                        current_outcome_id=row["current_outcome_id"],
                        costs=float(row["costs"]) if row["costs"] is not None else None,
                        entry_slippage=(
                            float(row["entry_slippage"])
                            if row["entry_slippage"] is not None
                            else None
                        ),
                    )
                )

            return results
    except sqlite3.Error as exc:
        raise StoreError(f"Database error querying journal overview: {exc}") from exc


get_journal_overview = list_journal_read_models


def get_journal_events_timeline(
    journal_id: str,
    *,
    db_path: Path | str | None = None,
    settings: TradeXSettings | None = None,
) -> list[JournalEventStreamReadModel]:
    """Query append-only events for a trade ordered deterministically by seq ASC."""
    if not journal_id or not str(journal_id).strip():
        return []
    clean_id = str(journal_id).strip()
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)

    sql = """
        SELECT event_id, journal_id, seq, event_type, event_timestamp, recorded_at, payload_json
        FROM journal_events
        WHERE journal_id = ?
        ORDER BY seq ASC
    """
    try:
        with _conn(db_path=path) as con:
            rows = con.execute(sql, (clean_id,)).fetchall()
            events: list[JournalEventStreamReadModel] = []
            for r in rows:
                ev_ts = _parse_dt(r["event_timestamp"])
                rec_ts = _parse_dt(r["recorded_at"])
                assert ev_ts is not None
                assert rec_ts is not None

                payload: dict[str, Any] = {}
                if r["payload_json"]:
                    try:
                        payload = json.loads(r["payload_json"])
                    except Exception:  # noqa: BLE001
                        payload = {}

                events.append(
                    JournalEventStreamReadModel(
                        event_id=r["event_id"],
                        journal_id=r["journal_id"],
                        seq=int(r["seq"]),
                        event_type=r["event_type"],
                        event_timestamp=ev_ts,
                        recorded_at=rec_ts,
                        payload=payload,
                    )
                )
            return events
    except sqlite3.Error as exc:
        raise StoreError(f"Database error querying events for journal '{clean_id}': {exc}") from exc


def get_journal_outcome_history(
    journal_id: str,
    *,
    db_path: Path | str | None = None,
    settings: TradeXSettings | None = None,
) -> list[JournalOutcomeAuditReadModel]:
    """Query versioned outcomes for a trade ordered deterministically by computed_at DESC, outcome_id ASC."""
    if not journal_id or not str(journal_id).strip():
        return []
    clean_id = str(journal_id).strip()
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)

    sql = """
        SELECT
            outcome_id,
            journal_id,
            computation_version,
            computed_at,
            source_event_seq,
            inputs_hash,
            entry_slippage,
            costs,
            gross_return_pct,
            net_return_pct,
            outcome_confidence,
            inputs_json
        FROM journal_outcomes
        WHERE journal_id = ?
        ORDER BY computed_at DESC, outcome_id ASC
    """
    try:
        with _conn(db_path=path) as con:
            rows = con.execute(sql, (clean_id,)).fetchall()
            outcomes: list[JournalOutcomeAuditReadModel] = []
            for r in rows:
                comp_ts = _parse_dt(r["computed_at"])
                assert comp_ts is not None

                inputs_dict: dict[str, Any] = {}
                if r["inputs_json"]:
                    try:
                        inputs_dict = json.loads(r["inputs_json"])
                    except Exception:  # noqa: BLE001
                        inputs_dict = {}

                outcomes.append(
                    JournalOutcomeAuditReadModel(
                        outcome_id=r["outcome_id"],
                        journal_id=r["journal_id"],
                        computation_version=r["computation_version"],
                        computed_at=comp_ts,
                        source_event_seq=int(r["source_event_seq"]),
                        inputs_hash=r["inputs_hash"],
                        entry_slippage=(
                            float(r["entry_slippage"]) if r["entry_slippage"] is not None else None
                        ),
                        costs=float(r["costs"]) if r["costs"] is not None else None,
                        gross_return_pct=(
                            float(r["gross_return_pct"])
                            if r["gross_return_pct"] is not None
                            else None
                        ),
                        net_return_pct=(
                            float(r["net_return_pct"])
                            if r["net_return_pct"] is not None
                            else None
                        ),
                        outcome_confidence=r["outcome_confidence"],
                        inputs=inputs_dict,
                        strategy_drawdown=None,
                    )
                )
            return outcomes
    except sqlite3.Error as exc:
        raise StoreError(
            f"Database error querying outcome history for journal '{clean_id}': {exc}"
        ) from exc


def get_journal_detail(
    journal_id: str,
    *,
    db_path: Path | str | None = None,
    settings: TradeXSettings | None = None,
) -> JournalDetailReadModel | None:
    """Retrieve complete journal trade detail with candidate linkage, event timeline, and outcome history."""
    if not journal_id or not str(journal_id).strip():
        return None
    clean_id = str(journal_id).strip()
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)

    sql = """
        SELECT
            t.*,
            c.symbol AS candidate_symbol,
            c.decision_timestamp AS candidate_decision_timestamp,
            c.trading_date AS candidate_trading_date,
            c.security_identity_status AS candidate_sec_status,
            c.security_identity_version AS candidate_sec_version,
            c.created_at AS candidate_created_at,
            c.contract_version AS candidate_contract_version
        FROM journal_trades t
        LEFT JOIN candidates c ON c.candidate_id = t.candidate_id
        WHERE t.journal_id = ?
    """
    try:
        with _conn(db_path=path) as con:
            row = con.execute(sql, (clean_id,)).fetchone()
            if row is None:
                return None

            dec_ts = _parse_dt(row["decision_timestamp"])
            plan_ts = _parse_dt(row["plan_created_at"])
            fill_ts = _parse_dt(row["fill_timestamp"])
            exit_ts = _parse_dt(row["exit_timestamp"])
            exp_ts = _parse_dt(row["expiration"])

            assert dec_ts is not None
            assert plan_ts is not None

            strat_id = str(row["strategy_id"])
            strat_ver = str(row["strategy_version"])
            is_authorized = has_production_strategy_capability(
                strat_id, strat_ver, "journal_execution"
            )

            sym = str(row["candidate_symbol"] or "UNKNOWN")

            # Load events and outcomes
            events = get_journal_events_timeline(clean_id, db_path=path, settings=settings)
            outcomes = get_journal_outcome_history(clean_id, db_path=path, settings=settings)
            current_outcome = outcomes[0] if outcomes else None

            trade_model = JournalTradeReadModel(
                journal_id=row["journal_id"],
                candidate_id=row["candidate_id"],
                symbol=sym,
                state=row["state"],
                strategy_id=strat_id,
                strategy_version=strat_ver,
                side=row["side"],
                planned_entry=float(row["planned_entry"]),
                decision_timestamp=dec_ts,
                plan_created_at=plan_ts,
                is_strategy_authorized=is_authorized,
                quantity=float(row["quantity"]) if row["quantity"] is not None else None,
                fill_price=float(row["fill_price"]) if row["fill_price"] is not None else None,
                fill_timestamp=fill_ts,
                fill_provenance=_deserialize_provenance(row["fill_provenance"]),
                stop_price=float(row["stop_price"]) if row["stop_price"] is not None else None,
                target_price=float(row["target_price"]) if row["target_price"] is not None else None,
                expiration=exp_ts,
                invalidation_rule=_deserialize_invalidation_rule(row["invalidation_rule"]),
                exit_price=float(row["exit_price"]) if row["exit_price"] is not None else None,
                exit_timestamp=exit_ts,
                exit_reason=row["exit_reason"],
                exit_provenance=_deserialize_provenance(row["exit_provenance"]),
                terminal_reason=row["terminal_reason"],
                gross_return_pct=(
                    current_outcome.gross_return_pct if current_outcome else None
                ),
                net_return_pct=(
                    current_outcome.net_return_pct if current_outcome else None
                ),
                outcome_confidence=(
                    current_outcome.outcome_confidence if current_outcome else None
                ),
                current_outcome_id=(
                    current_outcome.outcome_id if current_outcome else None
                ),
                costs=current_outcome.costs if current_outcome else None,
                entry_slippage=current_outcome.entry_slippage if current_outcome else None,
            )

            # Construct candidate snapshot model if candidate row exists
            candidate_snap: CandidateSnapshot | None = None
            if row["candidate_id"] and row["candidate_symbol"]:
                from tradex.candidates.models import CandidateSnapshot, SecurityIdentityStatus

                c_dec_ts = _parse_dt(row["candidate_decision_timestamp"])
                c_created = _parse_dt(row["candidate_created_at"])
                assert c_dec_ts is not None
                assert c_created is not None

                raw_sec_version = row["candidate_sec_version"]
                raw_sec_status = row["candidate_sec_status"]

                sec_version = (
                    str(raw_sec_version).strip()
                    if raw_sec_version is not None and str(raw_sec_version).strip()
                    else None
                )

                if sec_version is not None:
                    if raw_sec_status:
                        try:
                            sec_status = SecurityIdentityStatus(str(raw_sec_status).lower())
                        except ValueError:
                            sec_status = SecurityIdentityStatus.KNOWN
                    else:
                        sec_status = SecurityIdentityStatus.KNOWN
                else:
                    sec_status = SecurityIdentityStatus.UNKNOWN

                candidate_snap = CandidateSnapshot(
                    candidate_id=row["candidate_id"],
                    symbol=row["candidate_symbol"],
                    decision_timestamp=c_dec_ts,
                    contract_version=int(row["candidate_contract_version"] or 1),
                    trading_date=row["candidate_trading_date"],
                    security_identity_version=sec_version,
                    security_identity_status=sec_status,
                    created_at=c_created,
                )

            # Query candidate evidence summary
            evidence_summary: dict[str, Any] = {}
            ev_rows = con.execute(
                "SELECT evidence_type, provider, metadata_json FROM candidate_evidence WHERE candidate_id = ?",
                (row["candidate_id"],),
            ).fetchall()
            for er in ev_rows:
                ev_type = str(er["evidence_type"])
                meta_json = {}
                if er["metadata_json"]:
                    try:
                        meta_json = json.loads(er["metadata_json"])
                    except Exception:  # noqa: BLE001
                        meta_json = {}
                evidence_summary[ev_type] = {
                    "provider": er["provider"],
                    "metadata": meta_json,
                }

            return JournalDetailReadModel(
                trade=trade_model,
                symbol=sym,
                is_strategy_authorized=is_authorized,
                candidate_snapshot=candidate_snap,
                candidate_evidence_summary=evidence_summary,
                current_outcome=current_outcome,
                events=events,
                outcomes=outcomes,
            )
    except sqlite3.Error as exc:
        raise StoreError(f"Database error querying journal detail '{clean_id}': {exc}") from exc


def get_journal_strategy_ids(
    *,
    db_path: Path | str | None = None,
    settings: TradeXSettings | None = None,
) -> list[str]:
    """Return distinct strategy IDs present in journal_trades, ordered alphabetically."""
    path = _resolve_db_path(settings) if db_path is None else Path(db_path)
    try:
        with _conn(db_path=path) as con:
            rows = con.execute(
                "SELECT DISTINCT strategy_id FROM journal_trades ORDER BY strategy_id ASC"
            ).fetchall()
            return [str(r["strategy_id"]) for r in rows if r["strategy_id"]]
    except sqlite3.Error as exc:
        raise StoreError(f"Database error querying journal strategy IDs: {exc}") from exc
