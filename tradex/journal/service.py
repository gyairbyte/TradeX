"""Executable Journal lifecycle service layer (MVP-ARCH-001-R6).

Orchestrates strategy authorization, CandidateSnapshot point-in-time linkage,
trade plan validation, single-transaction state transitions, idempotency,
append-only event logging, and deterministic outcome calculation/recomputation.
"""
from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from typing import Any

from tradex.config import TradeXSettings
from tradex.journal.models import (
    CandidateNotFoundError,
    ConflictingExitError,
    ConflictingFillError,
    ExecutionProvenance,
    ExecutionProvenanceType,
    ExitReason,
    IdempotencyConflictError,
    InvalidTransitionError,
    JournalEvent,
    JournalEventType,
    JournalNotFoundError,
    JournalOutcome,
    JournalState,
    JournalTrade,
    StrategyNotAuthorizedError,
    TradePlan,
    _normalize_aware_dt,
    _normalize_enum,
    _validate_non_blank_str,
    _validate_non_negative_finite_float,
    _validate_positive_finite_float,
)
from tradex.journal.outcomes import (
    JOURNAL_OUTCOME_COMPUTATION_VERSION,
    canonicalize_provenance_payload,
    compute_journal_outcome,
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
from tradex.strategies.registry import (
    has_production_strategy_capability,
    validate_strategy_identity,
)
from tradex.tracker.store import _resolve_db_path, _transaction


def validate_strategy_authorization(strategy_id: str, strategy_version: str) -> None:
    """Validate strategy authorization for new journal execution.

    Requirements:
    1. Validates strategy_id and strategy_version identity syntax first (raises ValueError/TypeError).
    2. Inspects APPROVED_PRODUCTION_STRATEGIES at call time for "journal_execution" capability.
    3. Raises StrategyNotAuthorizedError if the strategy does not hold "journal_execution".
    """
    validate_strategy_identity(strategy_id, strategy_version)

    if not has_production_strategy_capability(
        strategy_id, strategy_version, "journal_execution"
    ):
        raise StrategyNotAuthorizedError(
            f"Strategy '{strategy_id}' version '{strategy_version}' is not authorized "
            "for journal_execution in APPROVED_PRODUCTION_STRATEGIES"
        )


def create_planned_trade(
    *,
    candidate_id: str,
    strategy_id: str,
    strategy_version: str,
    decision_timestamp: datetime,
    plan_created_at: datetime,
    plan: TradePlan,
    decided_by: str,
    plan_source: str,
    plan_provider: str | None = None,
    idempotency_key: str,
    settings: TradeXSettings | None = None,
) -> JournalTrade:
    """Create a new planned trade record and append the initial created event in one transaction.

    Enforces:
    1. Strategy authorization gate at creation time.
    2. CandidateSnapshot existence and PIT ordering (candidate.decision_ts <= journal.decision_ts <= plan_created_at).
    3. Trade plan validation and immutability.
    4. Exact idempotency replay returns existing trade; divergent replay raises IdempotencyConflictError.
    5. Single transaction: no partial write on failure.
    """
    # 1. Strategy identity and authorization
    validate_strategy_authorization(strategy_id, strategy_version)

    # Validate strings
    cand_id = _validate_non_blank_str(candidate_id, "candidate_id")
    strat_id = _validate_non_blank_str(strategy_id, "strategy_id")
    strat_ver = _validate_non_blank_str(strategy_version, "strategy_version")
    dec_by = _validate_non_blank_str(decided_by, "decided_by")
    p_source = _validate_non_blank_str(plan_source, "plan_source")
    p_provider = (
        str(plan_provider).strip()
        if (plan_provider is not None and str(plan_provider).strip())
        else "unknown"
    )
    idem_key = _validate_non_blank_str(idempotency_key, "idempotency_key")

    # Validate timestamps
    norm_dec_ts = _normalize_aware_dt(decision_timestamp, "decision_timestamp")
    norm_plan_created = _normalize_aware_dt(plan_created_at, "plan_created_at")

    if norm_dec_ts > norm_plan_created:
        raise ValueError(
            f"decision_timestamp ({norm_dec_ts.isoformat()}) cannot be after "
            f"plan_created_at ({norm_plan_created.isoformat()})"
        )

    if not isinstance(plan, TradePlan):
        raise TypeError(f"plan must be a TradePlan instance, got {type(plan).__name__}")

    if plan.expiration is not None and plan.expiration <= norm_plan_created:
        raise ValueError(
            f"plan expiration ({plan.expiration.isoformat()}) must be strictly after "
            f"plan_created_at ({norm_plan_created.isoformat()})"
        )

    db_path = _resolve_db_path(settings)

    with _transaction(db_path=db_path) as con:
        # 2. Candidate existence & PIT check
        cand_row = con.execute(
            "SELECT decision_timestamp FROM candidates WHERE candidate_id = ?",
            (cand_id,),
        ).fetchone()
        if cand_row is None:
            raise CandidateNotFoundError(f"CandidateSnapshot '{cand_id}' does not exist in store")

        cand_dec_ts_str = cand_row[0]
        cand_dec_ts = datetime.fromisoformat(cand_dec_ts_str)
        if cand_dec_ts.tzinfo is None:
            cand_dec_ts = cand_dec_ts.replace(tzinfo=UTC)
        cand_dec_ts = cand_dec_ts.astimezone(UTC)

        if cand_dec_ts > norm_dec_ts:
            raise ValueError(
                f"Candidate decision_timestamp ({cand_dec_ts.isoformat()}) is after "
                f"journal decision_timestamp ({norm_dec_ts.isoformat()}); PIT ordering violated"
            )

        # 3. Idempotency checks
        existing_by_key = get_journal_trade_by_idempotency_key(con, idem_key)
        if existing_by_key is not None:
            # Inspect first event for provenance fields
            events = get_journal_events(con, existing_by_key.journal_id)
            created_event = next((e for e in events if e.seq == 1), None)
            ev_payload = created_event.payload if created_event else {}

            # Materiality comparison
            same_candidate = existing_by_key.candidate_id == cand_id
            same_strategy = (
                existing_by_key.strategy_id == strat_id
                and existing_by_key.strategy_version == strat_ver
            )
            same_decision_ts = existing_by_key.decision_timestamp == norm_dec_ts
            same_plan_created = existing_by_key.plan_created_at == norm_plan_created
            same_entry = math.isclose(existing_by_key.planned_entry, plan.planned_entry)
            same_stop = (
                (existing_by_key.stop_price is None and plan.stop_price is None)
                or (
                    existing_by_key.stop_price is not None
                    and plan.stop_price is not None
                    and math.isclose(existing_by_key.stop_price, plan.stop_price)
                )
            )
            same_target = (
                (existing_by_key.target_price is None and plan.target_price is None)
                or (
                    existing_by_key.target_price is not None
                    and plan.target_price is not None
                    and math.isclose(existing_by_key.target_price, plan.target_price)
                )
            )
            same_exp = existing_by_key.expiration == plan.expiration
            same_inv = existing_by_key.invalidation_rule == plan.invalidation_rule
            same_dec_by = ev_payload.get("decided_by") == dec_by
            same_p_src = ev_payload.get("plan_source") == p_source
            same_p_prov = ev_payload.get("plan_provider") == p_provider

            if (
                same_candidate
                and same_strategy
                and same_decision_ts
                and same_plan_created
                and same_entry
                and same_stop
                and same_target
                and same_exp
                and same_inv
                and same_dec_by
                and same_p_src
                and same_p_prov
            ):
                return existing_by_key

            raise IdempotencyConflictError(
                f"Idempotency key '{idem_key}' was reused with divergent material payload"
            )

        # Check unique (candidate_id, strategy_id, strategy_version) under different idempotency key
        existing_by_cand_strat = get_journal_trade_by_candidate_strategy(
            con, cand_id, strat_id, strat_ver
        )
        if existing_by_cand_strat is not None:
            raise IdempotencyConflictError(
                f"A trade decision for candidate '{cand_id}' and strategy '{strat_id}:{strat_ver}' "
                f"already exists with journal_id '{existing_by_cand_strat.journal_id}'"
            )

        # 4. Write new planned trade
        journal_id = uuid.uuid4().hex
        now_utc = datetime.now(tz=UTC)

        trade = JournalTrade(
            journal_id=journal_id,
            contract_version=1,
            idempotency_key=idem_key,
            candidate_id=cand_id,
            strategy_id=strat_id,
            strategy_version=strat_ver,
            side="long",
            state=JournalState.PLANNED,
            decision_timestamp=norm_dec_ts,
            plan_created_at=norm_plan_created,
            planned_entry=plan.planned_entry,
            stop_price=plan.stop_price,
            target_price=plan.target_price,
            expiration=plan.expiration,
            invalidation_rule=plan.invalidation_rule,
            created_at=now_utc,
            updated_at=now_utc,
        )
        insert_journal_trade(con, trade)

        # 5. Append initial created event (seq = 1)
        created_payload: dict[str, Any] = {
            "candidate_id": cand_id,
            "decided_by": dec_by,
            "decision_timestamp": norm_dec_ts.isoformat(),
            "expiration": plan.expiration.isoformat() if plan.expiration else None,
            "invalidation_rule": (
                {
                    "params": plan.invalidation_rule.params,
                    "rule_id": plan.invalidation_rule.rule_id,
                    "rule_version": plan.invalidation_rule.rule_version,
                }
                if plan.invalidation_rule
                else None
            ),
            "plan_provider": p_provider,
            "plan_source": p_source,
            "planned_entry": plan.planned_entry,
            "stop_price": plan.stop_price,
            "strategy_id": strat_id,
            "strategy_version": strat_ver,
            "target_price": plan.target_price,
        }

        created_event = JournalEvent(
            event_id=uuid.uuid4().hex,
            journal_id=journal_id,
            seq=1,
            event_type=JournalEventType.CREATED,
            event_timestamp=norm_plan_created,
            recorded_at=now_utc,
            payload=created_payload,
        )
        insert_journal_event(con, created_event)

        return trade


def record_fill(
    *,
    journal_id: str,
    fill_price: float,
    fill_timestamp: datetime,
    fill_provenance: ExecutionProvenance,
    quantity: float,
    settings: TradeXSettings | None = None,
) -> JournalTrade:
    """Record an entry execution fill transitioning a trade from planned to open.

    Enforces:
    1. planned -> open state transition.
    2. Rejection of broker_confirmed execution provenance in R6 v1 service.
    3. Fill timestamp >= plan_created_at and <= expiration (if configured).
    4. Exact replay returns existing trade; divergent replay raises ConflictingFillError.
    5. Appends filled event in the same atomic transaction.
    """
    j_id = _validate_non_blank_str(journal_id, "journal_id")
    f_price = _validate_positive_finite_float(fill_price, "fill_price")
    qty = _validate_positive_finite_float(quantity, "quantity")
    norm_fill_ts = _normalize_aware_dt(fill_timestamp, "fill_timestamp")

    if not isinstance(fill_provenance, ExecutionProvenance):
        raise TypeError(
            f"fill_provenance must be ExecutionProvenance, got {type(fill_provenance).__name__}"
        )

    # R6 v1 service rejection of broker_confirmed
    prov_type = (
        fill_provenance.execution_provenance.value
        if isinstance(fill_provenance.execution_provenance, ExecutionProvenanceType)
        else str(fill_provenance.execution_provenance).strip().lower()
    )
    if prov_type == ExecutionProvenanceType.BROKER_CONFIRMED.value:
        raise InvalidTransitionError(
            "broker_confirmed execution provenance is rejected by the service in R6 v1"
        )

    db_path = _resolve_db_path(settings)

    with _transaction(db_path=db_path) as con:
        trade = get_journal_trade_by_id(con, j_id)
        if trade is None:
            raise JournalNotFoundError(f"JournalTrade '{j_id}' not found")

        # Idempotent fill replay check
        if trade.state == JournalState.OPEN:
            same_price = trade.fill_price is not None and math.isclose(trade.fill_price, f_price)
            same_qty = trade.quantity is not None and math.isclose(trade.quantity, qty)
            same_ts = trade.fill_timestamp == norm_fill_ts
            same_prov = trade.fill_provenance == fill_provenance

            if same_price and same_qty and same_ts and same_prov:
                return trade

            raise ConflictingFillError(
                f"JournalTrade '{j_id}' is already open with a conflicting fill"
            )

        if trade.state != JournalState.PLANNED:
            raise InvalidTransitionError(
                f"Cannot record fill on trade in state '{trade.state.value}'; expected 'planned'"
            )

        if norm_fill_ts < trade.plan_created_at:
            raise ValueError(
                f"fill_timestamp ({norm_fill_ts.isoformat()}) cannot be before "
                f"plan_created_at ({trade.plan_created_at.isoformat()})"
            )

        if trade.expiration is not None and norm_fill_ts > trade.expiration:
            raise ValueError(
                f"fill_timestamp ({norm_fill_ts.isoformat()}) cannot be after "
                f"expiration ({trade.expiration.isoformat()})"
            )

        now_utc = datetime.now(tz=UTC)
        next_seq = get_latest_event_seq(con, j_id) + 1

        updated_trade = JournalTrade(
            journal_id=trade.journal_id,
            contract_version=trade.contract_version,
            idempotency_key=trade.idempotency_key,
            candidate_id=trade.candidate_id,
            strategy_id=trade.strategy_id,
            strategy_version=trade.strategy_version,
            side=trade.side,
            state=JournalState.OPEN,
            decision_timestamp=trade.decision_timestamp,
            plan_created_at=trade.plan_created_at,
            planned_entry=trade.planned_entry,
            stop_price=trade.stop_price,
            target_price=trade.target_price,
            expiration=trade.expiration,
            invalidation_rule=trade.invalidation_rule,
            quantity=qty,
            fill_price=f_price,
            fill_timestamp=norm_fill_ts,
            fill_provenance=fill_provenance,
            exit_price=None,
            exit_timestamp=None,
            exit_reason=None,
            exit_provenance=None,
            terminal_reason=None,
            created_at=trade.created_at,
            updated_at=now_utc,
        )
        update_journal_trade(con, updated_trade)

        fill_payload = {
            "fill_price": f_price,
            "fill_provenance": canonicalize_provenance_payload(fill_provenance),
            "quantity": qty,
        }
        filled_event = JournalEvent(
            event_id=uuid.uuid4().hex,
            journal_id=j_id,
            seq=next_seq,
            event_type=JournalEventType.FILLED,
            event_timestamp=norm_fill_ts,
            recorded_at=now_utc,
            payload=fill_payload,
        )
        insert_journal_event(con, filled_event)

        return updated_trade


def cancel_trade(
    *,
    journal_id: str,
    cancel_reason: str,
    cancelled_at: datetime,
    settings: TradeXSettings | None = None,
) -> JournalTrade:
    """Cancel a planned trade before entry fill."""
    j_id = _validate_non_blank_str(journal_id, "journal_id")
    reason = _validate_non_blank_str(cancel_reason, "cancel_reason")
    norm_cancelled_at = _normalize_aware_dt(cancelled_at, "cancelled_at")
    db_path = _resolve_db_path(settings)

    with _transaction(db_path=db_path) as con:
        trade = get_journal_trade_by_id(con, j_id)
        if trade is None:
            raise JournalNotFoundError(f"JournalTrade '{j_id}' not found")

        if trade.state == JournalState.CANCELLED:
            if trade.terminal_reason == reason:
                return trade
            raise InvalidTransitionError(
                f"Trade '{j_id}' is already cancelled with different reason"
            )

        if trade.state != JournalState.PLANNED:
            raise InvalidTransitionError(
                f"Cannot cancel trade in state '{trade.state.value}'; expected 'planned'"
            )

        if norm_cancelled_at < trade.plan_created_at:
            raise ValueError(
                f"cancelled_at ({norm_cancelled_at.isoformat()}) cannot be before "
                f"plan_created_at ({trade.plan_created_at.isoformat()})"
            )

        now_utc = datetime.now(tz=UTC)
        next_seq = get_latest_event_seq(con, j_id) + 1

        updated_trade = JournalTrade(
            journal_id=trade.journal_id,
            contract_version=trade.contract_version,
            idempotency_key=trade.idempotency_key,
            candidate_id=trade.candidate_id,
            strategy_id=trade.strategy_id,
            strategy_version=trade.strategy_version,
            side=trade.side,
            state=JournalState.CANCELLED,
            decision_timestamp=trade.decision_timestamp,
            plan_created_at=trade.plan_created_at,
            planned_entry=trade.planned_entry,
            stop_price=trade.stop_price,
            target_price=trade.target_price,
            expiration=trade.expiration,
            invalidation_rule=trade.invalidation_rule,
            quantity=None,
            fill_price=None,
            fill_timestamp=None,
            fill_provenance=None,
            exit_price=None,
            exit_timestamp=None,
            exit_reason=None,
            exit_provenance=None,
            terminal_reason=reason,
            created_at=trade.created_at,
            updated_at=now_utc,
        )
        update_journal_trade(con, updated_trade)

        event = JournalEvent(
            event_id=uuid.uuid4().hex,
            journal_id=j_id,
            seq=next_seq,
            event_type=JournalEventType.CANCELLED,
            event_timestamp=norm_cancelled_at,
            recorded_at=now_utc,
            payload={"cancel_reason": reason},
        )
        insert_journal_event(con, event)

        return updated_trade


def invalidate_trade(
    *,
    journal_id: str,
    invalidation_reason: str,
    invalidated_at: datetime,
    settings: TradeXSettings | None = None,
) -> JournalTrade:
    """Invalidate a planned trade setup before entry fill."""
    j_id = _validate_non_blank_str(journal_id, "journal_id")
    reason = _validate_non_blank_str(invalidation_reason, "invalidation_reason")
    norm_invalidated_at = _normalize_aware_dt(invalidated_at, "invalidated_at")
    db_path = _resolve_db_path(settings)

    with _transaction(db_path=db_path) as con:
        trade = get_journal_trade_by_id(con, j_id)
        if trade is None:
            raise JournalNotFoundError(f"JournalTrade '{j_id}' not found")

        if trade.state == JournalState.INVALIDATED:
            if trade.terminal_reason == reason:
                return trade
            raise InvalidTransitionError(
                f"Trade '{j_id}' is already invalidated with different reason"
            )

        if trade.state != JournalState.PLANNED:
            raise InvalidTransitionError(
                f"Cannot invalidate trade in state '{trade.state.value}' without an exit fill"
            )

        if norm_invalidated_at < trade.plan_created_at:
            raise ValueError(
                f"invalidated_at ({norm_invalidated_at.isoformat()}) cannot be before "
                f"plan_created_at ({trade.plan_created_at.isoformat()})"
            )

        now_utc = datetime.now(tz=UTC)
        next_seq = get_latest_event_seq(con, j_id) + 1

        updated_trade = JournalTrade(
            journal_id=trade.journal_id,
            contract_version=trade.contract_version,
            idempotency_key=trade.idempotency_key,
            candidate_id=trade.candidate_id,
            strategy_id=trade.strategy_id,
            strategy_version=trade.strategy_version,
            side=trade.side,
            state=JournalState.INVALIDATED,
            decision_timestamp=trade.decision_timestamp,
            plan_created_at=trade.plan_created_at,
            planned_entry=trade.planned_entry,
            stop_price=trade.stop_price,
            target_price=trade.target_price,
            expiration=trade.expiration,
            invalidation_rule=trade.invalidation_rule,
            quantity=None,
            fill_price=None,
            fill_timestamp=None,
            fill_provenance=None,
            exit_price=None,
            exit_timestamp=None,
            exit_reason=None,
            exit_provenance=None,
            terminal_reason=reason,
            created_at=trade.created_at,
            updated_at=now_utc,
        )
        update_journal_trade(con, updated_trade)

        event = JournalEvent(
            event_id=uuid.uuid4().hex,
            journal_id=j_id,
            seq=next_seq,
            event_type=JournalEventType.INVALIDATED,
            event_timestamp=norm_invalidated_at,
            recorded_at=now_utc,
            payload={"invalidation_reason": reason},
        )
        insert_journal_event(con, event)

        return updated_trade


def expire_trade(
    *,
    journal_id: str,
    expired_at: datetime,
    settings: TradeXSettings | None = None,
) -> JournalTrade:
    """Expire a planned trade whose expiration timestamp has passed without an entry fill."""
    j_id = _validate_non_blank_str(journal_id, "journal_id")
    norm_expired_at = _normalize_aware_dt(expired_at, "expired_at")
    db_path = _resolve_db_path(settings)

    with _transaction(db_path=db_path) as con:
        trade = get_journal_trade_by_id(con, j_id)
        if trade is None:
            raise JournalNotFoundError(f"JournalTrade '{j_id}' not found")

        if trade.state == JournalState.EXPIRED:
            return trade

        if trade.state != JournalState.PLANNED:
            raise InvalidTransitionError(
                f"Cannot expire trade in state '{trade.state.value}' without an exit fill"
            )

        if trade.expiration is None:
            raise InvalidTransitionError(
                f"Cannot expire trade '{j_id}' because it has no expiration configured"
            )

        if norm_expired_at < trade.expiration:
            raise ValueError(
                f"expired_at ({norm_expired_at.isoformat()}) must be >= "
                f"plan expiration ({trade.expiration.isoformat()})"
            )

        now_utc = datetime.now(tz=UTC)
        next_seq = get_latest_event_seq(con, j_id) + 1

        updated_trade = JournalTrade(
            journal_id=trade.journal_id,
            contract_version=trade.contract_version,
            idempotency_key=trade.idempotency_key,
            candidate_id=trade.candidate_id,
            strategy_id=trade.strategy_id,
            strategy_version=trade.strategy_version,
            side=trade.side,
            state=JournalState.EXPIRED,
            decision_timestamp=trade.decision_timestamp,
            plan_created_at=trade.plan_created_at,
            planned_entry=trade.planned_entry,
            stop_price=trade.stop_price,
            target_price=trade.target_price,
            expiration=trade.expiration,
            invalidation_rule=trade.invalidation_rule,
            quantity=None,
            fill_price=None,
            fill_timestamp=None,
            fill_provenance=None,
            exit_price=None,
            exit_timestamp=None,
            exit_reason=None,
            exit_provenance=None,
            terminal_reason="expired",
            created_at=trade.created_at,
            updated_at=now_utc,
        )
        update_journal_trade(con, updated_trade)

        event = JournalEvent(
            event_id=uuid.uuid4().hex,
            journal_id=j_id,
            seq=next_seq,
            event_type=JournalEventType.EXPIRED,
            event_timestamp=norm_expired_at,
            recorded_at=now_utc,
            payload={"expired_at": norm_expired_at.isoformat()},
        )
        insert_journal_event(con, event)

        return updated_trade


def record_exit(
    *,
    journal_id: str,
    exit_price: float,
    exit_timestamp: datetime,
    exit_reason: ExitReason | str,
    exit_provenance: ExecutionProvenance,
    costs: float | None = None,
    settings: TradeXSettings | None = None,
) -> JournalTrade:
    """Record an exit execution transitioning an open trade to closed.

    In ONE atomic transaction:
    1. Validates open state and exit parameters.
    2. Rejects broker_confirmed execution provenance in R6 v1 service.
    3. Updates journal_trades to closed.
    4. Appends exited event (persisting costs in event payload).
    5. Computes initial outcome and inserts initial journal_outcomes row.
    """
    j_id = _validate_non_blank_str(journal_id, "journal_id")
    e_price = _validate_positive_finite_float(exit_price, "exit_price")
    norm_exit_ts = _normalize_aware_dt(exit_timestamp, "exit_timestamp")
    norm_exit_reason = _normalize_enum(exit_reason, ExitReason, "exit_reason")

    if not isinstance(exit_provenance, ExecutionProvenance):
        raise TypeError(
            f"exit_provenance must be ExecutionProvenance, got {type(exit_provenance).__name__}"
        )

    # R6 v1 service rejection of broker_confirmed
    prov_type = (
        exit_provenance.execution_provenance.value
        if isinstance(exit_provenance.execution_provenance, ExecutionProvenanceType)
        else str(exit_provenance.execution_provenance).strip().lower()
    )
    if prov_type == ExecutionProvenanceType.BROKER_CONFIRMED.value:
        raise InvalidTransitionError(
            "broker_confirmed execution provenance is rejected by the service in R6 v1"
        )

    c_val: float | None = None
    if costs is not None:
        c_val = _validate_non_negative_finite_float(costs, "costs")

    db_path = _resolve_db_path(settings)

    with _transaction(db_path=db_path) as con:
        trade = get_journal_trade_by_id(con, j_id)
        if trade is None:
            raise JournalNotFoundError(f"JournalTrade '{j_id}' not found")

        # Idempotency check for closed trade
        if trade.state == JournalState.CLOSED:
            events = get_journal_events(con, j_id)
            exit_event = next((e for e in events if e.event_type == JournalEventType.EXITED), None)
            persisted_costs = exit_event.payload.get("costs") if exit_event else None

            same_price = trade.exit_price is not None and math.isclose(trade.exit_price, e_price)
            same_ts = trade.exit_timestamp == norm_exit_ts
            same_reason = trade.exit_reason == norm_exit_reason
            same_prov = trade.exit_provenance == exit_provenance
            same_costs = (
                (persisted_costs is None and c_val is None)
                or (
                    persisted_costs is not None
                    and c_val is not None
                    and math.isclose(float(persisted_costs), c_val)
                )
            )

            if same_price and same_ts and same_reason and same_prov and same_costs:
                return trade

            raise ConflictingExitError(
                f"JournalTrade '{j_id}' is already closed with conflicting exit parameters"
            )

        if trade.state != JournalState.OPEN:
            raise InvalidTransitionError(
                f"Cannot record exit on trade in state '{trade.state.value}'; expected 'open'"
            )

        assert trade.fill_timestamp is not None
        assert trade.fill_price is not None
        assert trade.quantity is not None

        if norm_exit_ts < trade.fill_timestamp:
            raise ValueError(
                f"exit_timestamp ({norm_exit_ts.isoformat()}) cannot be before "
                f"fill_timestamp ({trade.fill_timestamp.isoformat()})"
            )

        now_utc = datetime.now(tz=UTC)
        next_seq = get_latest_event_seq(con, j_id) + 1

        updated_trade = JournalTrade(
            journal_id=trade.journal_id,
            contract_version=trade.contract_version,
            idempotency_key=trade.idempotency_key,
            candidate_id=trade.candidate_id,
            strategy_id=trade.strategy_id,
            strategy_version=trade.strategy_version,
            side=trade.side,
            state=JournalState.CLOSED,
            decision_timestamp=trade.decision_timestamp,
            plan_created_at=trade.plan_created_at,
            planned_entry=trade.planned_entry,
            stop_price=trade.stop_price,
            target_price=trade.target_price,
            expiration=trade.expiration,
            invalidation_rule=trade.invalidation_rule,
            quantity=trade.quantity,
            fill_price=trade.fill_price,
            fill_timestamp=trade.fill_timestamp,
            fill_provenance=trade.fill_provenance,
            exit_price=e_price,
            exit_timestamp=norm_exit_ts,
            exit_reason=norm_exit_reason,
            exit_provenance=exit_provenance,
            terminal_reason=None,
            created_at=trade.created_at,
            updated_at=now_utc,
        )
        update_journal_trade(con, updated_trade)

        exit_payload = {
            "costs": c_val,
            "exit_price": e_price,
            "exit_provenance": canonicalize_provenance_payload(exit_provenance),
            "exit_reason": norm_exit_reason.value,
        }
        exited_event = JournalEvent(
            event_id=uuid.uuid4().hex,
            journal_id=j_id,
            seq=next_seq,
            event_type=JournalEventType.EXITED,
            event_timestamp=norm_exit_ts,
            recorded_at=now_utc,
            payload=exit_payload,
        )
        insert_journal_event(con, exited_event)

        initial_outcome = compute_journal_outcome(
            journal_id=j_id,
            planned_entry=trade.planned_entry,
            fill_price=trade.fill_price,
            quantity=trade.quantity,
            exit_price=e_price,
            fill_provenance=trade.fill_provenance,
            exit_provenance=exit_provenance,
            costs=c_val,
            source_event_seq=next_seq,
            computation_version=JOURNAL_OUTCOME_COMPUTATION_VERSION,
            outcome_id=uuid.uuid4().hex,
            computed_at=now_utc,
        )
        insert_journal_outcome(con, initial_outcome)

        return updated_trade


def recompute_outcomes(
    *,
    journal_id: str,
    computation_version: str = JOURNAL_OUTCOME_COMPUTATION_VERSION,
    settings: TradeXSettings | None = None,
) -> JournalOutcome:
    """Recompute outcomes for a closed trade from persisted lifecycle events.

    Reconstructs calculation inputs from persisted lifecycle/event data (specifically
    reconstructing costs from the exited event payload) and inserts a new versioned
    journal_outcomes row without mutating previous outcomes.
    """
    j_id = _validate_non_blank_str(journal_id, "journal_id")
    comp_ver = _validate_non_blank_str(computation_version, "computation_version")
    db_path = _resolve_db_path(settings)

    with _transaction(db_path=db_path) as con:
        trade = get_journal_trade_by_id(con, j_id)
        if trade is None:
            raise JournalNotFoundError(f"JournalTrade '{j_id}' not found")

        if trade.state != JournalState.CLOSED:
            raise InvalidTransitionError(
                f"Cannot recompute outcomes on trade in state '{trade.state.value}'; expected 'closed'"
            )

        events = get_journal_events(con, j_id)
        exit_event = next((e for e in events if e.event_type == JournalEventType.EXITED), None)
        if exit_event is None:
            raise InvalidTransitionError(
                f"Corrupt lifecycle audit trail: closed trade '{j_id}' has no 'exited' event"
            )

        persisted_costs = exit_event.payload.get("costs")
        c_val: float | None = float(persisted_costs) if persisted_costs is not None else None

        source_event_seq = get_latest_event_seq(con, j_id)
        now_utc = datetime.now(tz=UTC)

        assert trade.fill_price is not None
        assert trade.quantity is not None
        assert trade.exit_price is not None

        new_outcome = compute_journal_outcome(
            journal_id=j_id,
            planned_entry=trade.planned_entry,
            fill_price=trade.fill_price,
            quantity=trade.quantity,
            exit_price=trade.exit_price,
            fill_provenance=trade.fill_provenance,
            exit_provenance=trade.exit_provenance,
            costs=c_val,
            source_event_seq=source_event_seq,
            computation_version=comp_ver,
            outcome_id=uuid.uuid4().hex,
            computed_at=now_utc,
        )
        insert_journal_outcome(con, new_outcome)

        return new_outcome


# ── Read APIs ────────────────────────────────────────────────────────────────


def get_journal_trade(
    journal_id: str,
    *,
    settings: TradeXSettings | None = None,
) -> JournalTrade | None:
    """Retrieve a single journal trade by ID."""
    db_path = _resolve_db_path(settings)
    with _transaction(db_path=db_path) as con:
        return get_journal_trade_by_id(con, journal_id)


def list_journal_trades_query(
    *,
    state: str | None = None,
    strategy_id: str | None = None,
    candidate_id: str | None = None,
    limit: int = 100,
    settings: TradeXSettings | None = None,
) -> list[JournalTrade]:
    """Retrieve journal trades ordered by plan_created_at DESC, journal_id ASC."""
    db_path = _resolve_db_path(settings)
    with _transaction(db_path=db_path) as con:
        return list_journal_trades(
            con,
            state=state,
            strategy_id=strategy_id,
            candidate_id=candidate_id,
            limit=limit,
        )


def get_journal_history(
    journal_id: str,
    *,
    settings: TradeXSettings | None = None,
) -> list[JournalEvent]:
    """Retrieve append-only events for a trade ordered by seq ASC."""
    db_path = _resolve_db_path(settings)
    with _transaction(db_path=db_path) as con:
        return get_journal_events(con, journal_id)


def list_journal_outcomes_query(
    journal_id: str,
    *,
    limit: int = 100,
    settings: TradeXSettings | None = None,
) -> list[JournalOutcome]:
    """Retrieve versioned outcomes ordered by computed_at DESC, outcome_id ASC."""
    db_path = _resolve_db_path(settings)
    with _transaction(db_path=db_path) as con:
        return list_journal_outcomes(con, journal_id, limit=limit)


def get_latest_journal_outcome_query(
    journal_id: str,
    *,
    settings: TradeXSettings | None = None,
) -> JournalOutcome | None:
    """Retrieve the latest outcome for a trade under the deterministic ordering."""
    db_path = _resolve_db_path(settings)
    with _transaction(db_path=db_path) as con:
        return get_latest_journal_outcome(con, journal_id)
