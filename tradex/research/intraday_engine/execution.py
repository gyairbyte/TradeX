"""Trade execution: next-bar entry, fixed stop, 1.5R target, deterministic exits."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from .calendar import MARKET_TIMEZONE, bar_available_at
from .models import Bar, CostScenario, Session, Signal, Trade
from .spec import IntradaySpec


def _find_next_bar(session: Session, bar_start: datetime) -> Bar | None:
    """Return the expected bar immediately following ``bar_start``, or ``None``."""
    sorted_grid = sorted(session.grid)
    try:
        idx = sorted_grid.index(bar_start)
    except ValueError:
        return None
    if idx + 1 >= len(sorted_grid):
        return None
    next_start = sorted_grid[idx + 1]
    return session.bars.get(next_start)


def _time_exit_bar_start(session: Session, spec: IntradaySpec) -> datetime | None:
    """Return the bar_start whose completion is the 3:45 PM time exit."""
    for g in sorted(session.grid):
        avail = bar_available_at(g)
        et = avail.astimezone(MARKET_TIMEZONE)
        if et.time() == spec.time_exit_time:
            return g
    return None


def _fallback_close(session: Session, before: datetime) -> tuple[float, datetime, str] | None:
    """Last valid regular-session close strictly before ``before``."""
    best: Bar | None = None
    for g in sorted(session.grid):
        if g >= before:
            break
        bar = session.bars.get(g)
        if bar is not None and bar.is_valid:
            best = bar
    if best is None:
        return None
    return best.close, bar_available_at(best.bar_start), "missing_time_exit_bar_fallback"


def _exit_on_bar(bar: Bar, stop: float, target: float) -> tuple[float, str, bool] | None:
    """Apply locked exit priority for one completed bar. Returns raw exit, type, ambiguity."""
    # Gap through stop at open.
    if bar.open <= stop:
        return bar.open, "gap_stop", False
    # Gap through target at open.
    if bar.open >= target:
        return bar.open, "gap_target", False

    stop_touched = bar.low <= stop
    target_touched = bar.high >= target
    ambiguity = stop_touched and target_touched

    if stop_touched:
        return stop, "stop", ambiguity
    if target_touched:
        return target, "target", ambiguity
    return None


def attempt_trade(
    ticker: str,
    ticker_meta: Any,  # TickerMeta, but Any to avoid import cycle typing
    session: Session,
    signal_bar: Bar,
    stop_price: float,
    opening_drive_qualified: bool | None,
    score: float | None,
    costs: CostScenario,
    spec: IntradaySpec,
    strategy: str,
) -> Signal:
    """Attempt entry on the bar after ``signal_bar`` and simulate the exit."""
    from .models import Signal, TickerMeta

    if not isinstance(ticker_meta, TickerMeta):
        raise TypeError("ticker_meta must be a TickerMeta instance")

    signal_time = bar_available_at(signal_bar.bar_start)

    next_bar = _find_next_bar(session, signal_bar.bar_start)
    if next_bar is None or not next_bar.is_valid:
        return Signal(
            ticker=ticker,
            session_date=session.session_date,
            strategy=strategy,
            signal_bar_start=signal_bar.bar_start,
            signal_time=signal_time,
            opening_drive_qualified=opening_drive_qualified,
            score=score,
            stop_price=stop_price,
            target_price=None,
            entry_open=None,
            entry_fill=None,
            risk_per_share=None,
            status="rejected_no_next_bar",
            reason="next_expected_bar_missing_or_invalid",
        )

    entry_open = next_bar.open
    entry_fill = costs.entry_fill(entry_open)

    if entry_open <= stop_price:
        return Signal(
            ticker=ticker,
            session_date=session.session_date,
            strategy=strategy,
            signal_bar_start=signal_bar.bar_start,
            signal_time=signal_time,
            opening_drive_qualified=opening_drive_qualified,
            score=score,
            stop_price=stop_price,
            target_price=None,
            entry_open=entry_open,
            entry_fill=None,
            risk_per_share=None,
            status="rejected_entry_at_or_below_stop",
            reason="next_bar_open_at_or_below_stop",
        )

    risk_per_share = entry_fill - stop_price
    if risk_per_share <= 0 or not math.isfinite(risk_per_share):
        return Signal(
            ticker=ticker,
            session_date=session.session_date,
            strategy=strategy,
            signal_bar_start=signal_bar.bar_start,
            signal_time=signal_time,
            opening_drive_qualified=opening_drive_qualified,
            score=score,
            stop_price=stop_price,
            target_price=None,
            entry_open=entry_open,
            entry_fill=entry_fill,
            risk_per_share=None,
            status="rejected_nonpositive_risk",
            reason="nonpositive_or_nonfinite_risk_per_share",
        )

    target_price = entry_fill + spec.target_multiple * risk_per_share
    entry_time = next_bar.bar_start

    # Simulate exit from entry bar through the rest of the session.
    sorted_grid = sorted(session.grid)
    entry_idx = sorted_grid.index(next_bar.bar_start)
    exit_time: datetime | None = None
    exit_bar_start: datetime | None = None
    raw_exit_price: float | None = None
    exit_type: str | None = None
    same_bar_ambiguity = False
    fallback_reason: str | None = None

    time_exit_start = _time_exit_bar_start(session, spec)

    for i in range(entry_idx, len(sorted_grid)):
        bar_start = sorted_grid[i]
        bar = session.bars.get(bar_start)
        if bar is None or not bar.is_valid:
            continue

        if i == entry_idx:
            # We entered at the open; evaluate the completed entry bar.
            result = _exit_on_bar(bar, stop_price, target_price)
            if result is not None:
                raw_exit_price, exit_type, ambiguity = result
                exit_time = bar_available_at(bar.bar_start)
                exit_bar_start = bar.bar_start
                same_bar_ambiguity = ambiguity
                break

            # If the entry bar is the time-exit bar, exit at close.
            if bar_start == time_exit_start:
                raw_exit_price = bar.close
                exit_type = "time"
                exit_time = bar_available_at(bar.bar_start)
                exit_bar_start = bar.bar_start
                break
            continue

        # Subsequent bars.
        if bar_start == time_exit_start:
            # Time exit priority: intrabar stop/target first, then close.
            result = _exit_on_bar(bar, stop_price, target_price)
            if result is not None:
                raw_exit_price, exit_type, ambiguity = result
                exit_time = bar_available_at(bar.bar_start)
                exit_bar_start = bar.bar_start
                same_bar_ambiguity = ambiguity
                break
            raw_exit_price = bar.close
            exit_type = "time"
            exit_time = bar_available_at(bar.bar_start)
            exit_bar_start = bar.bar_start
            break

        result = _exit_on_bar(bar, stop_price, target_price)
        if result is not None:
            raw_exit_price, exit_type, ambiguity = result
            exit_time = bar_available_at(bar.bar_start)
            exit_bar_start = bar.bar_start
            same_bar_ambiguity = ambiguity
            break

    if raw_exit_price is None:
        # Expected time-exit bar is missing; use fallback close.
        fallback = _fallback_close(session, session.closes_at)
        if fallback is None:
            return Signal(
                ticker=ticker,
                session_date=session.session_date,
                strategy=strategy,
                signal_bar_start=signal_bar.bar_start,
                signal_time=signal_time,
                opening_drive_qualified=opening_drive_qualified,
                score=score,
                stop_price=stop_price,
                target_price=target_price,
                entry_open=entry_open,
                entry_fill=entry_fill,
                risk_per_share=risk_per_share,
                status="rejected_no_time_exit_fallback",
                reason="no_valid_regular_session_close_before_close",
            )
        raw_exit_price, exit_time, fallback_reason = fallback
        exit_type = "time_fallback"

    exit_fill = costs.exit_fill(raw_exit_price)
    profit = exit_fill - entry_fill
    net_r = profit / risk_per_share

    trade = Trade(
        ticker=ticker,
        session_date=session.session_date,
        strategy=strategy,
        signal_time=signal_time,
        signal_bar_start=signal_bar.bar_start,
        entry_time=entry_time,
        entry_bar_start=next_bar.bar_start,
        entry_open=entry_open,
        entry_fill=entry_fill,
        stop_price=stop_price,
        target_price=target_price,
        risk_per_share=risk_per_share,
        exit_time=exit_time,
        exit_bar_start=exit_bar_start,
        raw_exit_price=raw_exit_price,
        exit_fill=exit_fill,
        profit=profit,
        net_r=net_r,
        exit_type=exit_type,
        same_bar_ambiguity=same_bar_ambiguity,
        fallback_reason=fallback_reason,
    )

    return Signal(
        ticker=ticker,
        session_date=session.session_date,
        strategy=strategy,
        signal_bar_start=signal_bar.bar_start,
        signal_time=signal_time,
        opening_drive_qualified=opening_drive_qualified,
        score=score,
        stop_price=stop_price,
        target_price=target_price,
        entry_open=entry_open,
        entry_fill=entry_fill,
        risk_per_share=risk_per_share,
        status="executed",
        trade=trade,
    )
