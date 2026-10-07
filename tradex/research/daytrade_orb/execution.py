"""Discrete 1-minute execution simulation, stop mechanics, and transaction costs."""
from __future__ import annotations

from datetime import datetime

from .models import Direction, ExitReason, MinuteBar, Trade


def check_stop_entry_trigger(
    bar: MinuteBar,
    direction: Direction,
    stop_level: float,
) -> tuple[bool, float]:
    """Evaluate 3-step conditional stop-entry trigger rule on a 1-minute bar.

    Long stop at P:
        Step 1: If bar.open >= P -> fill at bar.open
        Step 2: Else if bar.high >= P -> fill at P
        Step 3: Else -> no fill

    Short stop at P:
        Step 1: If bar.open <= P -> fill at bar.open
        Step 2: Else if bar.low <= P -> fill at P
        Step 3: Else -> no fill

    Returns:
        (is_triggered, raw_entry_price)
    """
    if direction == Direction.LONG:
        if bar.open >= stop_level:
            return True, bar.open
        elif bar.high >= stop_level:
            return True, stop_level
        else:
            return False, 0.0

    elif direction == Direction.SHORT:
        if bar.open <= stop_level:
            return True, bar.open
        elif bar.low <= stop_level:
            return True, stop_level
        else:
            return False, 0.0

    return False, 0.0


def check_protective_stop_hit(
    bar: MinuteBar,
    direction: Direction,
    protective_stop: float,
) -> tuple[bool, float]:
    """Evaluate protective stop trigger on a subsequent 1-minute bar.

    Long protective stop at S:
        If bar.open <= S -> exit at bar.open (adverse gap-through)
        Else if bar.low <= S -> exit at S
        Else -> position remains open

    Short protective stop at S:
        If bar.open >= S -> exit at bar.open (adverse gap-through)
        Else if bar.high >= S -> exit at S
        Else -> position remains open

    Returns:
        (is_hit, raw_exit_price)
    """
    if direction == Direction.LONG:
        if bar.open <= protective_stop:
            return True, bar.open
        elif bar.low <= protective_stop:
            return True, protective_stop
        else:
            return False, 0.0

    elif direction == Direction.SHORT:
        if bar.open >= protective_stop:
            return True, bar.open
        elif bar.high >= protective_stop:
            return True, protective_stop
        else:
            return False, 0.0

    return False, 0.0


def check_same_bar_stop_collision(
    bar: MinuteBar,
    direction: Direction,
    raw_entry_price: float,
    atr14: float,
    stop_mult: float = 0.10,
) -> tuple[bool, float, float]:
    """Evaluate whether protective stop was touched in the same 1-minute bar as entry.

    Conservative rule (AMB-07):
        If entry triggered and the bar range permits touching the stop,
        assume worst-case: entry occurred and stop was triggered in the same bar.

    Returns:
        (same_bar_hit, protective_stop_price, raw_exit_price)
    """
    if direction == Direction.LONG:
        protective_stop = raw_entry_price - (stop_mult * atr14)
        if bar.low <= protective_stop:
            # Stopped out in same bar
            exit_price = min(bar.open, protective_stop)
            return True, protective_stop, exit_price
        return False, protective_stop, 0.0

    elif direction == Direction.SHORT:
        protective_stop = raw_entry_price + (stop_mult * atr14)
        if bar.high >= protective_stop:
            # Stopped out in same bar
            exit_price = max(bar.open, protective_stop)
            return True, protective_stop, exit_price
        return False, protective_stop, 0.0

    return False, 0.0, 0.0


def build_trade_record(
    symbol: str,
    direction: Direction,
    session_date: datetime.date,
    entry_timestamp: datetime,
    raw_entry_price: float,
    exit_timestamp: datetime,
    raw_exit_price: float,
    shares: int,
    protective_stop_price: float,
    exit_reason: ExitReason,
    same_bar_ambiguity: bool,
    atr14: float,
    stop_mult: float = 0.10,
) -> Trade:
    """Construct an immutable Trade record calculating PnL across cost scenarios A, B, and C.

    Commission: $0.0035/share per executed side (entry and exit).
    Slippage scenarios:
        A: 0.0 bps per side
        B: 2.0 bps per side (primary TradeX hurdle)
        C: 5.0 bps per side (stress test)
    """
    # Gross price PnL
    if direction == Direction.LONG:
        gross_pnl = float(shares) * (raw_exit_price - raw_entry_price)
    else:
        gross_pnl = float(shares) * (raw_entry_price - raw_exit_price)

    # Commissions
    entry_comm = float(shares) * 0.0035
    exit_comm = float(shares) * 0.0035
    total_comm = entry_comm + exit_comm

    entry_notional = abs(float(shares) * raw_entry_price)
    exit_notional = abs(float(shares) * raw_exit_price)

    # Scenario A (0 bps)
    entry_slip_a = 0.0
    exit_slip_a = 0.0
    net_pnl_a = gross_pnl - total_comm

    # Scenario B (2 bps = 0.0002)
    entry_slip_b = entry_notional * 0.0002
    exit_slip_b = exit_notional * 0.0002
    net_pnl_b = gross_pnl - total_comm - entry_slip_b - exit_slip_b

    # Scenario C (5 bps = 0.0005)
    entry_slip_c = entry_notional * 0.0005
    exit_slip_c = exit_notional * 0.0005
    net_pnl_c = gross_pnl - total_comm - entry_slip_c - exit_slip_c

    # R-multiple based on 0.10 * ATR14 dollar risk
    dollar_risk = float(shares) * (stop_mult * atr14)
    r_mult = float(gross_pnl / dollar_risk) if dollar_risk > 0 else 0.0

    return Trade(
        symbol=symbol,
        direction=direction,
        session_date=session_date,
        entry_timestamp=entry_timestamp,
        raw_entry_price=raw_entry_price,
        exit_timestamp=exit_timestamp,
        raw_exit_price=raw_exit_price,
        shares=shares,
        protective_stop_price=protective_stop_price,
        exit_reason=exit_reason,
        same_bar_ambiguity=same_bar_ambiguity,
        gross_pnl=gross_pnl,
        entry_commission=entry_comm,
        exit_commission=exit_comm,
        total_commission=total_comm,
        entry_slippage_cost_a=entry_slip_a,
        exit_slippage_cost_a=exit_slip_a,
        net_pnl_a=net_pnl_a,
        entry_slippage_cost_b=entry_slip_b,
        exit_slippage_cost_b=exit_slip_b,
        net_pnl_b=net_pnl_b,
        entry_slippage_cost_c=entry_slip_c,
        exit_slippage_cost_c=exit_slip_c,
        net_pnl_c=net_pnl_c,
        r_multiple=r_mult,
    )
