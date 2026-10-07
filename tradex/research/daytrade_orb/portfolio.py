"""Multi-position portfolio execution simulation, 4x leverage ceiling, and capacity recycling."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from .execution import (
    build_trade_record,
    check_protective_stop_hit,
    check_same_bar_stop_collision,
    check_stop_entry_trigger,
)
from .models import (
    Direction,
    ExitReason,
    MinuteBar,
    OrderStatus,
    RankedCandidate,
    SessionResult,
    Trade,
)

MARKET_TIMEZONE = ZoneInfo("America/New_York")
EOD_MINUTE_TIME = time(15, 59)

# Canonical regular-session post-OR trade minutes: 09:35 through 15:59 ET (385 minutes)
CANONICAL_TRADE_MINUTES: tuple[time, ...] = tuple(
    time(h, m)
    for h in range(9, 16)
    for m in range(60)
    if (h == 9 and m >= 35) or (10 <= h <= 15)
)


@dataclass
class _ActivePosition:
    symbol: str
    direction: Direction
    entry_timestamp: datetime
    raw_entry_price: float
    shares: int
    protective_stop_price: float
    atr14: float


def simulate_session_portfolio(
    session_date: date,
    ranked_candidates: list[RankedCandidate],
    minute_bars_by_symbol: dict[str, list[MinuteBar]],
    session_start_equity: float = 25000.0,
    leverage_cap: float = 4.0,
    stop_loss_atr_mult: float = 0.10,
    candidate_count: int | None = None,
    qualified_candidate_count: int | None = None,
) -> SessionResult:
    """Simulate multi-position execution across discrete 1-minute regular-session bars.

    Key Invariants:
    1. Canonical minute iteration: iterates exact XNYS minute sequence (09:35 to 15:59 ET).
    2. State-aware data requirement: active pending orders and open positions require bars.
       Completed/dead states (stopped out, EOD liquidated, capacity rejected, doji) do not
       require irrelevant future bars.
    3. Bar integrity: rejects duplicate timestamps, date mismatches, symbol mismatches, or malformed bars.
    4. Portfolio gross leverage ceiling: gross_open_notional <= 4.0 * session_start_equity.
    5. Sizing: actual_shares = min(desired_shares, floor(available_gross_capacity / raw_entry_price)).
    6. Same-timestamp priority: higher Relative Volume rank first, ticker ascending tie-break.
    7. Capacity recycling: capacity released when position closes becomes available for later
       timestamps. For positions opened and stopped within the same minute, capacity is released
       beginning with the next minute (no same-minute intrabar recycling).
    8. EOD liquidation: all open positions liquidated at 15:59 bar close.
    """
    total_candidates = candidate_count if candidate_count is not None else len(ranked_candidates)
    qualified_candidates_count = (
        qualified_candidate_count
        if qualified_candidate_count is not None
        else len([rc for rc in ranked_candidates if rc.candidate.is_eligible])
    )

    # Index minute bars by (symbol, local_time) and strictly validate bar integrity
    bars_by_symbol_time: dict[str, dict[time, MinuteBar]] = {}

    for sym, bars in minute_bars_by_symbol.items():
        time_map: dict[time, MinuteBar] = {}
        for b in bars:
            if b.symbol != sym:
                return SessionResult(
                    session_date=session_date,
                    is_valid=False,
                    status="non_computable",
                    error_reason=f"Bar symbol mismatch for {sym}: bar has symbol {b.symbol}",
                    candidate_count=total_candidates,
                    qualified_candidate_count=qualified_candidates_count,
                    top_20_count=total_candidates,
                    orders_placed_count=0,
                    trades_triggered_count=0,
                    capacity_rejected_count=0,
                    trades=(),
                    session_start_equity=session_start_equity,
                    session_end_equity_a=session_start_equity,
                    session_end_equity_b=session_start_equity,
                    session_end_equity_c=session_start_equity,
                    session_net_pnl_a=0.0,
                    session_net_pnl_b=0.0,
                    session_net_pnl_c=0.0,
                    session_net_return_a=0.0,
                    session_net_return_b=0.0,
                    session_net_return_c=0.0,
                    max_gross_exposure=0.0,
                    max_leverage_used=0.0,
                    same_bar_ambiguity_count=0,
                )
            if b.session_date != session_date:
                return SessionResult(
                    session_date=session_date,
                    is_valid=False,
                    status="non_computable",
                    error_reason=f"Bar session_date mismatch for {sym}: expected {session_date}, got {b.session_date}",
                    candidate_count=total_candidates,
                    qualified_candidate_count=qualified_candidates_count,
                    top_20_count=total_candidates,
                    orders_placed_count=0,
                    trades_triggered_count=0,
                    capacity_rejected_count=0,
                    trades=(),
                    session_start_equity=session_start_equity,
                    session_end_equity_a=session_start_equity,
                    session_end_equity_b=session_start_equity,
                    session_end_equity_c=session_start_equity,
                    session_net_pnl_a=0.0,
                    session_net_pnl_b=0.0,
                    session_net_pnl_c=0.0,
                    session_net_return_a=0.0,
                    session_net_return_b=0.0,
                    session_net_return_c=0.0,
                    max_gross_exposure=0.0,
                    max_leverage_used=0.0,
                    same_bar_ambiguity_count=0,
                )
            ny_dt = b.timestamp.astimezone(MARKET_TIMEZONE)
            if ny_dt.date() != session_date:
                return SessionResult(
                    session_date=session_date,
                    is_valid=False,
                    status="non_computable",
                    error_reason=f"Bar timestamp NY date mismatch for {sym}: expected {session_date}, got {ny_dt.date()}",
                    candidate_count=total_candidates,
                    qualified_candidate_count=qualified_candidates_count,
                    top_20_count=total_candidates,
                    orders_placed_count=0,
                    trades_triggered_count=0,
                    capacity_rejected_count=0,
                    trades=(),
                    session_start_equity=session_start_equity,
                    session_end_equity_a=session_start_equity,
                    session_end_equity_b=session_start_equity,
                    session_end_equity_c=session_start_equity,
                    session_net_pnl_a=0.0,
                    session_net_pnl_b=0.0,
                    session_net_pnl_c=0.0,
                    session_net_return_a=0.0,
                    session_net_return_b=0.0,
                    session_net_return_c=0.0,
                    max_gross_exposure=0.0,
                    max_leverage_used=0.0,
                    same_bar_ambiguity_count=0,
                )
            lt = ny_dt.time()
            if time(9, 35) <= lt <= EOD_MINUTE_TIME:
                if lt in time_map:
                    # Duplicate minute bar detected -> fail closed!
                    return SessionResult(
                        session_date=session_date,
                        is_valid=False,
                        status="non_computable",
                        error_reason=f"Duplicate minute bar timestamp {lt.strftime('%H:%M')} for symbol {sym}",
                        candidate_count=total_candidates,
                        qualified_candidate_count=qualified_candidates_count,
                        top_20_count=total_candidates,
                        orders_placed_count=0,
                        trades_triggered_count=0,
                        capacity_rejected_count=0,
                        trades=(),
                        session_start_equity=session_start_equity,
                        session_end_equity_a=session_start_equity,
                        session_end_equity_b=session_start_equity,
                        session_end_equity_c=session_start_equity,
                        session_net_pnl_a=0.0,
                        session_net_pnl_b=0.0,
                        session_net_pnl_c=0.0,
                        session_net_return_a=0.0,
                        session_net_return_b=0.0,
                        session_net_return_c=0.0,
                        max_gross_exposure=0.0,
                        max_leverage_used=0.0,
                        same_bar_ambiguity_count=0,
                    )
                time_map[lt] = b
        bars_by_symbol_time[sym] = time_map

    # Active tracking
    active_positions: dict[str, _ActivePosition] = {}
    completed_trades: list[Trade] = []

    # Pending orders: qualifying candidates with ORDER_NOT_TRIGGERED
    pending_orders: dict[str, RankedCandidate] = {
        rc.candidate.symbol: rc
        for rc in ranked_candidates
        if rc.order_intent.status == OrderStatus.ORDER_NOT_TRIGGERED
    }

    capacity_rejected_count = len(
        [rc for rc in ranked_candidates if rc.order_intent.status == OrderStatus.CAPACITY_REJECTED]
    )
    orders_placed_count = len(
        [rc for rc in ranked_candidates if rc.order_intent.status != OrderStatus.NO_ORDER_DOJI]
    )

    max_gross_exposure = 0.0
    gross_capacity_limit = leverage_cap * session_start_equity

    # Iterate through the canonical XNYS minute sequence (09:35 through 15:59 ET)
    for curr_time in CANONICAL_TRADE_MINUTES:
        is_eod_bar = curr_time == EOD_MINUTE_TIME

        # Verify bar presence for all symbols with active orders or open positions
        # 1. Active positions require a bar at curr_time
        for sym in active_positions:
            bar = bars_by_symbol_time.get(sym, {}).get(curr_time)
            if bar is None:
                return SessionResult(
                    session_date=session_date,
                    is_valid=False,
                    status="non_computable",
                    error_reason=f"Missing trade-path bar for open position {sym} at {curr_time.strftime('%H:%M')}",
                    candidate_count=total_candidates,
                    qualified_candidate_count=qualified_candidates_count,
                    top_20_count=total_candidates,
                    orders_placed_count=orders_placed_count,
                    trades_triggered_count=len(completed_trades),
                    capacity_rejected_count=capacity_rejected_count,
                    trades=(),
                    session_start_equity=session_start_equity,
                    session_end_equity_a=session_start_equity,
                    session_end_equity_b=session_start_equity,
                    session_end_equity_c=session_start_equity,
                    session_net_pnl_a=0.0,
                    session_net_pnl_b=0.0,
                    session_net_pnl_c=0.0,
                    session_net_return_a=0.0,
                    session_net_return_b=0.0,
                    session_net_return_c=0.0,
                    max_gross_exposure=max_gross_exposure,
                    max_leverage_used=max_gross_exposure / session_start_equity if session_start_equity > 0 else 0.0,
                    same_bar_ambiguity_count=0,
                )

        # 2. Pending orders require a bar at curr_time
        for sym in pending_orders:
            bar = bars_by_symbol_time.get(sym, {}).get(curr_time)
            if bar is None:
                return SessionResult(
                    session_date=session_date,
                    is_valid=False,
                    status="non_computable",
                    error_reason=f"Missing trade-path bar for pending order {sym} at {curr_time.strftime('%H:%M')}",
                    candidate_count=total_candidates,
                    qualified_candidate_count=qualified_candidates_count,
                    top_20_count=total_candidates,
                    orders_placed_count=orders_placed_count,
                    trades_triggered_count=len(completed_trades),
                    capacity_rejected_count=capacity_rejected_count,
                    trades=(),
                    session_start_equity=session_start_equity,
                    session_end_equity_a=session_start_equity,
                    session_end_equity_b=session_start_equity,
                    session_end_equity_c=session_start_equity,
                    session_net_pnl_a=0.0,
                    session_net_pnl_b=0.0,
                    session_net_pnl_c=0.0,
                    session_net_return_a=0.0,
                    session_net_return_b=0.0,
                    session_net_return_c=0.0,
                    max_gross_exposure=max_gross_exposure,
                    max_leverage_used=max_gross_exposure / session_start_equity if session_start_equity > 0 else 0.0,
                    same_bar_ambiguity_count=0,
                )

        # Baseline open notional entering this minute
        baseline_open_notional = sum(
            float(p.shares) * p.raw_entry_price for p in active_positions.values()
        )
        committed_notional_this_minute = 0.0

        # Step 1: Check existing open positions for protective stop exits
        # Positions that close in this minute will NOT free capacity for entries in this minute
        positions_to_close: list[str] = []
        for sym, pos in list(active_positions.items()):
            bar = bars_by_symbol_time[sym][curr_time]

            hit_stop, raw_exit = check_protective_stop_hit(
                bar=bar,
                direction=pos.direction,
                protective_stop=pos.protective_stop_price,
            )
            if hit_stop:
                trade = build_trade_record(
                    symbol=sym,
                    direction=pos.direction,
                    session_date=session_date,
                    entry_timestamp=pos.entry_timestamp,
                    raw_entry_price=pos.raw_entry_price,
                    exit_timestamp=bar.timestamp,
                    raw_exit_price=raw_exit,
                    shares=pos.shares,
                    protective_stop_price=pos.protective_stop_price,
                    exit_reason=ExitReason.STOP_LOSS,
                    same_bar_ambiguity=False,
                    atr14=pos.atr14,
                    stop_mult=stop_loss_atr_mult,
                )
                completed_trades.append(trade)
                positions_to_close.append(sym)
            elif is_eod_bar:
                # EOD liquidation at 15:59 bar close
                trade = build_trade_record(
                    symbol=sym,
                    direction=pos.direction,
                    session_date=session_date,
                    entry_timestamp=pos.entry_timestamp,
                    raw_entry_price=pos.raw_entry_price,
                    exit_timestamp=bar.timestamp,
                    raw_exit_price=bar.close,
                    shares=pos.shares,
                    protective_stop_price=pos.protective_stop_price,
                    exit_reason=ExitReason.END_OF_DAY,
                    same_bar_ambiguity=False,
                    atr14=pos.atr14,
                    stop_mult=stop_loss_atr_mult,
                )
                completed_trades.append(trade)
                positions_to_close.append(sym)

        # Step 2: Check pending orders that trigger in this minute
        triggered_this_minute: list[tuple[RankedCandidate, MinuteBar, float]] = []
        for sym, rc in list(pending_orders.items()):
            bar = bars_by_symbol_time[sym][curr_time]

            stop_level = rc.order_intent.stop_level
            if stop_level is None:
                continue

            is_trig, raw_entry = check_stop_entry_trigger(
                bar=bar,
                direction=rc.order_intent.direction,
                stop_level=stop_level,
            )
            if is_trig:
                triggered_this_minute.append((rc, bar, raw_entry))

        # Sort multiple triggers in the same minute:
        # 1. higher Relative Volume rank first (lower rank integer)
        # 2. ticker alphabetical ascending tie-break
        triggered_this_minute.sort(key=lambda item: (item[0].rank, item[0].candidate.symbol))

        # Step 3: Size and fill triggered orders against available portfolio capacity
        for rc, bar, raw_entry in triggered_this_minute:
            sym = rc.candidate.symbol
            # Order triggered -> no longer pending regardless of fill vs capacity reject
            pending_orders.pop(sym, None)

            # Available gross capacity based on baseline open notional entering minute + committed this minute
            current_minute_exposure = baseline_open_notional + committed_notional_this_minute
            available_capacity = max(0.0, gross_capacity_limit - current_minute_exposure)

            # Max shares allowed by remaining capacity
            max_capacity_shares = math.floor(available_capacity / raw_entry) if raw_entry > 0 else 0
            actual_shares = min(rc.order_intent.desired_shares, max_capacity_shares)

            if actual_shares <= 0:
                # Capacity rejected: record and move to next trigger
                capacity_rejected_count += 1
                continue

            order_notional = float(actual_shares) * raw_entry
            committed_notional_this_minute += order_notional

            # Check conservative same-bar collision
            hit_same_bar, protective_stop, same_bar_exit = check_same_bar_stop_collision(
                bar=bar,
                direction=rc.order_intent.direction,
                raw_entry_price=raw_entry,
                atr14=rc.candidate.atr14,
                stop_mult=stop_loss_atr_mult,
            )

            if hit_same_bar:
                # Same-bar stopped out: position is closed immediately
                # Crucial capacity rule: capacity is NOT recycled within this same minute!
                trade = build_trade_record(
                    symbol=sym,
                    direction=rc.order_intent.direction,
                    session_date=session_date,
                    entry_timestamp=bar.timestamp,
                    raw_entry_price=raw_entry,
                    exit_timestamp=bar.timestamp,
                    raw_exit_price=same_bar_exit,
                    shares=actual_shares,
                    protective_stop_price=protective_stop,
                    exit_reason=ExitReason.STOP_LOSS,
                    same_bar_ambiguity=True,
                    atr14=rc.candidate.atr14,
                    stop_mult=stop_loss_atr_mult,
                )
                completed_trades.append(trade)
            elif is_eod_bar:
                # Triggered on 15:59 bar and not stopped: liquidated at 15:59 bar close
                protective_stop = (
                    raw_entry - (stop_loss_atr_mult * rc.candidate.atr14)
                    if rc.order_intent.direction == Direction.LONG
                    else raw_entry + (stop_loss_atr_mult * rc.candidate.atr14)
                )
                trade = build_trade_record(
                    symbol=sym,
                    direction=rc.order_intent.direction,
                    session_date=session_date,
                    entry_timestamp=bar.timestamp,
                    raw_entry_price=raw_entry,
                    exit_timestamp=bar.timestamp,
                    raw_exit_price=bar.close,
                    shares=actual_shares,
                    protective_stop_price=protective_stop,
                    exit_reason=ExitReason.END_OF_DAY,
                    same_bar_ambiguity=False,
                    atr14=rc.candidate.atr14,
                    stop_mult=stop_loss_atr_mult,
                )
                completed_trades.append(trade)
            else:
                # Position remains open into future minutes
                protective_stop = (
                    raw_entry - (stop_loss_atr_mult * rc.candidate.atr14)
                    if rc.order_intent.direction == Direction.LONG
                    else raw_entry + (stop_loss_atr_mult * rc.candidate.atr14)
                )
                active_positions[sym] = _ActivePosition(
                    symbol=sym,
                    direction=rc.order_intent.direction,
                    entry_timestamp=bar.timestamp,
                    raw_entry_price=raw_entry,
                    shares=actual_shares,
                    protective_stop_price=protective_stop,
                    atr14=rc.candidate.atr14,
                )

        # Update peak gross exposure observed
        minute_total_exposure = baseline_open_notional + committed_notional_this_minute
        max_gross_exposure = max(max_gross_exposure, minute_total_exposure)

        # Remove positions that closed during this minute (releases capacity for NEXT minute)
        for sym in positions_to_close:
            active_positions.pop(sym, None)

    # Calculate session totals
    net_pnl_a = sum(t.net_pnl_a for t in completed_trades)
    net_pnl_b = sum(t.net_pnl_b for t in completed_trades)
    net_pnl_c = sum(t.net_pnl_c for t in completed_trades)

    ret_a = float(net_pnl_a / session_start_equity) if session_start_equity > 0 else 0.0
    ret_b = float(net_pnl_b / session_start_equity) if session_start_equity > 0 else 0.0
    ret_c = float(net_pnl_c / session_start_equity) if session_start_equity > 0 else 0.0

    max_lev = float(max_gross_exposure / session_start_equity) if session_start_equity > 0 else 0.0
    same_bar_count = sum(1 for t in completed_trades if t.same_bar_ambiguity)

    return SessionResult(
        session_date=session_date,
        is_valid=True,
        status="completed",
        error_reason=None,
        candidate_count=total_candidates,
        qualified_candidate_count=qualified_candidates_count,
        top_20_count=total_candidates,
        orders_placed_count=orders_placed_count,
        trades_triggered_count=len(completed_trades),
        capacity_rejected_count=capacity_rejected_count,
        trades=tuple(completed_trades),
        session_start_equity=session_start_equity,
        session_end_equity_a=session_start_equity + net_pnl_a,
        session_end_equity_b=session_start_equity + net_pnl_b,
        session_end_equity_c=session_start_equity + net_pnl_c,
        session_net_pnl_a=net_pnl_a,
        session_net_pnl_b=net_pnl_b,
        session_net_pnl_c=net_pnl_c,
        session_net_return_a=ret_a,
        session_net_return_b=ret_b,
        session_net_return_c=ret_c,
        max_gross_exposure=max_gross_exposure,
        max_leverage_used=max_lev,
        same_bar_ambiguity_count=same_bar_count,
    )
