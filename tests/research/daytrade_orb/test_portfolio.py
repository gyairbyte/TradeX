"""Portfolio simulation, multi-position capacity, 4x leverage ceiling, and state-aware path tests."""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from tradex.research.daytrade_orb import (
    Candidate,
    Direction,
    ExitReason,
    MinuteBar,
    OpeningRange,
    OrderIntent,
    OrderStatus,
    RankedCandidate,
    simulate_session_portfolio,
    size_order_intent,
)
from tradex.research.daytrade_orb.portfolio import CANONICAL_TRADE_MINUTES

NY_TZ = ZoneInfo("America/New_York")


def _bar(sym: str, d: date, m: int, o: float, h: float, l: float, c: float, hour: int = 9) -> MinuteBar:
    return MinuteBar(
        symbol=sym,
        timestamp=datetime(d.year, d.month, d.day, hour, m, tzinfo=NY_TZ),
        session_date=d,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=10_000.0,
    )


def _make_minute_path(
    sym: str,
    d: date,
    base_price: float,
    overrides: dict[time, tuple[float, float, float, float]] | None = None,
) -> list[MinuteBar]:
    """Construct complete regular session path (09:35..15:59) with optional OHLC overrides."""
    overrides = overrides or {}
    bars: list[MinuteBar] = []
    for t in CANONICAL_TRADE_MINUTES:
        if t in overrides:
            o, h, l, c = overrides[t]
        else:
            o, h, l, c = base_price, base_price + 0.1, base_price - 0.1, base_price
        ts = datetime(d.year, d.month, d.day, t.hour, t.minute, tzinfo=NY_TZ)
        bars.append(
            MinuteBar(
                symbol=sym,
                timestamp=ts,
                session_date=d,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=10_000.0,
            )
        )
    return bars


def test_position_sizing_risk_vs_leverage_clipping() -> None:
    """Requirement: Sizing = min(risk_shares, leverage_shares) with floor to integer."""
    d = date(2025, 6, 2)

    # Case 1: Risk limited
    op1 = OpeningRange("SYM1", d, 50.0, 50.0, 48.0, 50.0, 50_000.0, Direction.LONG, 50.0)
    cand1 = Candidate("SYM1", d, 50.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent1 = size_order_intent(cand1, op1, session_start_equity=25000.0)
    assert intent1.desired_shares == 1250
    assert intent1.status == OrderStatus.ORDER_NOT_TRIGGERED

    # Case 2: Leverage limited
    op2 = OpeningRange("SYM2", d, 100.0, 100.0, 95.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand2 = Candidate("SYM2", d, 100.0, 2_000_000.0, 0.51, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent2 = size_order_intent(cand2, op2, session_start_equity=25000.0)
    assert intent2.desired_shares == 1000


def test_portfolio_4x_leverage_ceiling_and_capacity_rejection() -> None:
    """Requirement: Gross open notional <= 4x equity; orders exceeding capacity clip or reject."""
    d = date(2025, 6, 2)
    ranked: list[RankedCandidate] = []
    bars_by_sym: dict[str, list[MinuteBar]] = {}

    for i, sym in enumerate(["SYM1", "SYM2", "SYM3"], start=1):
        op = OpeningRange(sym, d, 60.0, 60.0, 58.0, 60.0, 50_000.0, Direction.LONG, 60.0)
        cand = Candidate(sym, d, 60.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
        intent = OrderIntent(
            symbol=sym,
            session_date=d,
            direction=Direction.LONG,
            stop_level=60.0,
            atr14=2.0,
            protective_stop_offset=0.20,
            desired_shares=1000,
            risk_per_share=0.20,
            status=OrderStatus.ORDER_NOT_TRIGGERED,
        )
        ranked.append(RankedCandidate(rank=i, candidate=cand, opening_range=op, order_intent=intent))

        # Build full session path:
        # At 09:35, quiet (does not trigger: high = 59.5 < 60.0)
        # At 09:36, triggers (high = 61.0 >= 60.0)
        # At 15:59, closes at 62.0
        overrides = {
            time(9, 35): (59.0, 59.5, 58.5, 59.0),
            time(9, 36): (59.0, 61.0, 59.0, 60.5),
            time(15, 59): (61.0, 62.5, 60.8, 62.0),
        }
        bars_by_sym[sym] = _make_minute_path(sym, d, base_price=60.5, overrides=overrides)

    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol=bars_by_sym,
        session_start_equity=25000.0,
        leverage_cap=4.0,
    )

    assert result.trades_triggered_count == 2
    assert result.capacity_rejected_count == 1

    trades_by_sym = {t.symbol: t for t in result.trades}
    assert trades_by_sym["SYM1"].shares == 1000
    assert trades_by_sym["SYM2"].shares == 666
    assert "SYM3" not in trades_by_sym

    assert result.max_gross_exposure <= 100000.0
    assert result.max_gross_exposure == pytest.approx(60000.0 + (666 * 60.0))
    assert result.max_leverage_used <= 4.0


def test_capacity_released_for_later_timestamps() -> None:
    """Requirement: When an open position closes, its capacity becomes available for later minutes."""
    d = date(2025, 6, 2)
    op1 = OpeningRange("SYM1", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand1 = Candidate("SYM1", d, 100.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent1 = OrderIntent("SYM1", d, Direction.LONG, 100.0, 2.0, 0.20, 1000, 0.20, OrderStatus.ORDER_NOT_TRIGGERED)

    op2 = OpeningRange("SYM2", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand2 = Candidate("SYM2", d, 100.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent2 = OrderIntent("SYM2", d, Direction.LONG, 100.0, 2.0, 0.20, 1000, 0.20, OrderStatus.ORDER_NOT_TRIGGERED)

    ranked = [
        RankedCandidate(1, cand1, op1, intent1),
        RankedCandidate(2, cand2, op2, intent2),
    ]

    # SYM1 triggers at 09:36, stops out at 09:40
    overrides1 = {
        time(9, 35): (99.0, 99.5, 98.5, 99.0),
        time(9, 36): (99.0, 101.0, 99.0, 100.5),  # Triggers at 100.0 (100% capacity)
        time(9, 37): (100.0, 100.5, 99.9, 100.2),
        time(9, 38): (100.0, 100.5, 99.9, 100.2),
        time(9, 39): (100.0, 100.5, 99.9, 100.2),
        time(9, 40): (100.0, 100.5, 99.7, 99.75), # Stops out (low <= 99.80)
    }
    bars1 = _make_minute_path("SYM1", d, base_price=100.0, overrides=overrides1)

    # SYM2 is quiet until 09:45, then triggers at 09:45
    overrides2 = {
        time(9, 35): (95.0, 96.0, 94.0, 95.0),
        time(9, 36): (95.0, 96.0, 94.0, 95.0),
        time(9, 45): (99.0, 101.0, 99.0, 100.5),  # Triggers using freed capacity!
        time(15, 59): (100.0, 101.0, 99.5, 100.5),
    }
    bars2 = _make_minute_path("SYM2", d, base_price=95.0, overrides=overrides2)

    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"SYM1": bars1, "SYM2": bars2},
        session_start_equity=25000.0,
        leverage_cap=4.0,
    )

    assert result.trades_triggered_count == 2
    assert result.capacity_rejected_count == 0


def test_no_same_minute_capacity_recycling_on_stop() -> None:
    """Requirement: Position opened and stopped in same minute does NOT release capacity in that same minute."""
    d = date(2025, 6, 2)
    op1 = OpeningRange("SYM1", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand1 = Candidate("SYM1", d, 100.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent1 = OrderIntent("SYM1", d, Direction.LONG, 100.0, 2.0, 0.20, 1000, 0.20, OrderStatus.ORDER_NOT_TRIGGERED)

    op2 = OpeningRange("SYM2", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand2 = Candidate("SYM2", d, 100.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent2 = OrderIntent("SYM2", d, Direction.LONG, 100.0, 2.0, 0.20, 1000, 0.20, OrderStatus.ORDER_NOT_TRIGGERED)

    ranked = [
        RankedCandidate(1, cand1, op1, intent1),
        RankedCandidate(2, cand2, op2, intent2),
    ]

    # SYM1 triggers and stops same-bar at 09:35
    overrides1 = {
        time(9, 35): (99.85, 101.0, 99.5, 99.9),
    }
    bars1 = _make_minute_path("SYM1", d, base_price=100.0, overrides=overrides1)

    # SYM2 also triggers at 09:35
    overrides2 = {
        time(9, 35): (99.0, 101.0, 98.5, 100.5),
    }
    bars2 = _make_minute_path("SYM2", d, base_price=100.0, overrides=overrides2)

    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"SYM1": bars1, "SYM2": bars2},
        session_start_equity=25000.0,
        leverage_cap=4.0,
    )

    assert result.trades_triggered_count == 1
    assert result.capacity_rejected_count == 1
    assert result.same_bar_ambiguity_count == 1
    assert result.trades[0].symbol == "SYM1"


def test_missing_middle_minute_for_pending_order_fails_closed() -> None:
    """Requirement: Untriggered order with missing middle minute fails closed as non_computable."""
    d = date(2025, 6, 2)
    op = OpeningRange("PEND", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand = Candidate("PEND", d, 100.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent = OrderIntent("PEND", d, Direction.LONG, 100.0, 2.0, 0.20, 1000, 0.20, OrderStatus.ORDER_NOT_TRIGGERED)
    ranked = [RankedCandidate(1, cand, op, intent)]

    # Make full path but omit minute 10:00
    bars = [b for b in _make_minute_path("PEND", d, base_price=90.0) if b.timestamp.time() != time(10, 0)]
    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"PEND": bars},
        session_start_equity=25000.0,
    )

    assert result.is_valid is False
    assert result.status == "non_computable"
    assert "Missing trade-path bar for pending order PEND at 10:00" in (result.error_reason or "")


def test_missing_middle_minute_for_open_position_fails_closed() -> None:
    """Requirement: Open position with missing middle minute fails closed as non_computable."""
    d = date(2025, 6, 2)
    op = OpeningRange("OPEN", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand = Candidate("OPEN", d, 100.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent = OrderIntent("OPEN", d, Direction.LONG, 100.0, 2.0, 0.20, 1000, 0.20, OrderStatus.ORDER_NOT_TRIGGERED)
    ranked = [RankedCandidate(1, cand, op, intent)]

    # Triggers at 09:35, remains open until 15:59, but omit minute 11:30
    overrides = {time(9, 35): (99.9, 101.0, 99.85, 100.5)}
    bars = [
        b for b in _make_minute_path("OPEN", d, base_price=100.5, overrides=overrides)
        if b.timestamp.time() != time(11, 30)
    ]

    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"OPEN": bars},
        session_start_equity=25000.0,
    )

    assert result.is_valid is False
    assert result.status == "non_computable"
    assert "Missing trade-path bar for open position OPEN at 11:30" in (result.error_reason or "")


def test_missing_1559_bar_for_open_position_fails_closed() -> None:
    """Requirement: Open position missing final 15:59 bar fails closed."""
    d = date(2025, 6, 2)
    op = OpeningRange("OPEN", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand = Candidate("OPEN", d, 100.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent = OrderIntent("OPEN", d, Direction.LONG, 100.0, 2.0, 0.20, 1000, 0.20, OrderStatus.ORDER_NOT_TRIGGERED)
    ranked = [RankedCandidate(1, cand, op, intent)]

    overrides = {time(9, 35): (99.9, 101.0, 99.85, 100.5)}
    # Omit 15:59 bar
    bars = [
        b for b in _make_minute_path("OPEN", d, base_price=100.5, overrides=overrides)
        if b.timestamp.time() != time(15, 59)
    ]

    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"OPEN": bars},
        session_start_equity=25000.0,
    )

    assert result.is_valid is False
    assert result.status == "non_computable"
    assert "Missing trade-path bar for open position OPEN at 15:59" in (result.error_reason or "")


def test_bars_after_stopped_position_not_required() -> None:
    """Requirement: Once a position is stopped out, future path bars are irrelevant and NOT required."""
    d = date(2025, 6, 2)
    op = OpeningRange("STOP", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand = Candidate("STOP", d, 100.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent = OrderIntent("STOP", d, Direction.LONG, 100.0, 2.0, 0.20, 1000, 0.20, OrderStatus.ORDER_NOT_TRIGGERED)
    ranked = [RankedCandidate(1, cand, op, intent)]

    # Provide only bars up to 09:37:
    # 09:35 triggers
    # 09:36 stops out
    # 09:37 onwards: COMPLETELY MISSING
    bars = [
        _bar("STOP", d, 35, 99.0, 101.0, 99.0, 100.5), # Triggers at 100.0
        _bar("STOP", d, 36, 100.0, 100.5, 99.7, 99.75), # Stops out (low <= 99.80)
    ]

    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"STOP": bars},
        session_start_equity=25000.0,
    )

    # Must succeed! The trade completed and subsequent bars are not demanded.
    assert result.is_valid is True
    assert result.trades_triggered_count == 1
    assert result.trades[0].exit_reason == ExitReason.STOP_LOSS


def test_doji_requires_no_trade_path_bars() -> None:
    """Requirement: Doji candidate produces NO_ORDER_DOJI and requires zero subsequent path bars."""
    d = date(2025, 6, 2)
    op = OpeningRange("DOJI", d, 100.0, 105.0, 95.0, 100.0, 50_000.0, Direction.DOJI, None)
    cand = Candidate("DOJI", d, 100.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent = OrderIntent("DOJI", d, Direction.DOJI, None, 2.0, 0.0, 0, 0.0, OrderStatus.NO_ORDER_DOJI)
    ranked = [RankedCandidate(1, cand, op, intent)]

    # Zero trade path bars supplied for DOJI
    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"DOJI": []},
        session_start_equity=25000.0,
    )

    assert result.is_valid is True
    assert result.trades_triggered_count == 0


def test_duplicate_trade_path_minute_fails_closed() -> None:
    """Requirement: Duplicate trade path minute bar timestamp fails closed."""
    d = date(2025, 6, 2)
    op = OpeningRange("DUP", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand = Candidate("DUP", d, 100.0, 2_000_000.0, 2.0, 50_000.0, 25_000.0, 2.0, True, True, True, True, True)
    intent = OrderIntent("DUP", d, Direction.LONG, 100.0, 2.0, 0.20, 1000, 0.20, OrderStatus.ORDER_NOT_TRIGGERED)
    ranked = [RankedCandidate(1, cand, op, intent)]

    bars = _make_minute_path("DUP", d, base_price=90.0)
    # Add duplicate bar for 09:35
    bars.append(bars[0])

    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"DUP": bars},
        session_start_equity=25000.0,
    )

    assert result.is_valid is False
    assert result.status == "non_computable"
    assert "Duplicate minute bar timestamp" in (result.error_reason or "")
