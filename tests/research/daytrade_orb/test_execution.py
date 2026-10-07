"""Execution mechanics, stop triggers, same-bar ambiguity, and transaction cost tests."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from tradex.research.daytrade_orb import (
    Direction,
    ExitReason,
    MinuteBar,
    build_trade_record,
    check_protective_stop_hit,
    check_same_bar_stop_collision,
    check_stop_entry_trigger,
)

NY_TZ = ZoneInfo("America/New_York")


def _bar(o: float, h: float, l: float, c: float, minute: int = 40) -> MinuteBar:
    return MinuteBar(
        symbol="XYZ",
        timestamp=datetime(2025, 6, 2, 9, minute, tzinfo=NY_TZ),
        session_date=date(2025, 6, 2),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=10_000.0,
    )


def test_long_stop_entry_trigger_rules() -> None:
    """Requirement: 3-step long trigger: open >= P (fill at open); high >= P (fill at P); else no fill."""
    stop_p = 100.0

    # Step 3: No fill (high < P)
    bar_no_fill = _bar(98.0, 99.5, 97.0, 99.0)
    hit, fill_p = check_stop_entry_trigger(bar_no_fill, Direction.LONG, stop_p)
    assert not hit and fill_p == 0.0

    # Step 2: Intrabar fill at P (open < P <= high)
    bar_intrabar = _bar(99.0, 101.0, 98.5, 100.5)
    hit, fill_p = check_stop_entry_trigger(bar_intrabar, Direction.LONG, stop_p)
    assert hit and fill_p == 100.0

    # Step 1: Gap-through fill at open (open >= P)
    bar_gap = _bar(102.5, 103.0, 101.5, 102.0)
    hit, fill_p = check_stop_entry_trigger(bar_gap, Direction.LONG, stop_p)
    assert hit and fill_p == 102.5


def test_short_stop_entry_trigger_rules() -> None:
    """Requirement: 3-step short trigger: open <= P (fill at open); low <= P (fill at P); else no fill."""
    stop_p = 50.0

    # Step 3: No fill (low > P)
    bar_no_fill = _bar(52.0, 52.5, 50.5, 51.0)
    hit, fill_p = check_stop_entry_trigger(bar_no_fill, Direction.SHORT, stop_p)
    assert not hit and fill_p == 0.0

    # Step 2: Intrabar fill at P (open > P >= low)
    bar_intrabar = _bar(51.0, 51.5, 49.0, 49.5)
    hit, fill_p = check_stop_entry_trigger(bar_intrabar, Direction.SHORT, stop_p)
    assert hit and fill_p == 50.0

    # Step 1: Gap-through fill at open (open <= P)
    bar_gap = _bar(48.5, 49.0, 47.5, 48.0)
    hit, fill_p = check_stop_entry_trigger(bar_gap, Direction.SHORT, stop_p)
    assert hit and fill_p == 48.5


def test_protective_stop_hit_and_gap_through() -> None:
    """Requirement: Protective stop exits at stop level or adverse open on gap-through."""
    # Long protective stop at 98.0
    stop_p = 98.0
    # No hit
    hit, _ = check_protective_stop_hit(_bar(99.0, 100.0, 98.5, 99.5), Direction.LONG, stop_p)
    assert not hit

    # Exact intrabar hit at stop level
    hit, exit_p = check_protective_stop_hit(_bar(99.0, 99.5, 97.5, 98.0), Direction.LONG, stop_p)
    assert hit and exit_p == 98.0

    # Gap-through exit at worse open
    hit, exit_p = check_protective_stop_hit(_bar(96.5, 97.0, 96.0, 96.8), Direction.LONG, stop_p)
    assert hit and exit_p == 96.5

    # Short protective stop at 52.0
    short_stop = 52.0
    # No hit
    hit, _ = check_protective_stop_hit(_bar(51.0, 51.5, 50.0, 50.5), Direction.SHORT, short_stop)
    assert not hit

    # Exact intrabar hit
    hit, exit_p = check_protective_stop_hit(_bar(51.0, 52.5, 50.5, 52.0), Direction.SHORT, short_stop)
    assert hit and exit_p == 52.0

    # Gap-through exit at worse open
    hit, exit_p = check_protective_stop_hit(_bar(53.5, 54.0, 53.0, 53.8), Direction.SHORT, short_stop)
    assert hit and exit_p == 53.5


def test_same_bar_entry_and_stop_conservative_collision() -> None:
    """Requirement: AMB-07 conservative convention: assume entry triggered and stop touched in same bar."""
    atr14 = 2.0  # Stop offset = 0.20
    # Long entry at 100.0 -> Protective stop = 99.80
    # Open 99.85 < 100.0 <= High 101.0 (triggers intrabar at 100.0); Low 99.5 <= 99.80 (hits stop in same bar)
    bar_long = _bar(99.85, 101.0, 99.5, 100.2)
    hit, stop_p, exit_p = check_same_bar_stop_collision(bar_long, Direction.LONG, 100.0, atr14)
    assert hit
    assert stop_p == pytest.approx(99.80)
    assert exit_p == pytest.approx(99.80)

    # Short entry at 50.0 -> Protective stop = 50.20
    # Open 50.15 > 50.0 >= Low 49.0 (triggers intrabar at 50.0); High 50.5 >= 50.20 (hits stop in same bar)
    bar_short = _bar(50.15, 50.5, 49.0, 49.5)
    hit_s, stop_p_s, exit_p_s = check_same_bar_stop_collision(bar_short, Direction.SHORT, 50.0, atr14)
    assert hit_s
    assert stop_p_s == pytest.approx(50.20)
    assert exit_p_s == pytest.approx(50.20)


def test_transaction_costs_and_slippage_scenarios() -> None:
    """Requirement: Commission $0.0035 both sides, Slippage 0 / 2 / 5 bps, strategy path unchanged."""
    d = date(2025, 6, 2)
    entry_ts = datetime(2025, 6, 2, 9, 36, tzinfo=NY_TZ)
    exit_ts = datetime(2025, 6, 2, 10, 15, tzinfo=NY_TZ)

    trade = build_trade_record(
        symbol="AAPL",
        direction=Direction.LONG,
        session_date=d,
        entry_timestamp=entry_ts,
        raw_entry_price=100.0,
        exit_timestamp=exit_ts,
        raw_exit_price=102.0,
        shares=1000,
        protective_stop_price=99.80,
        exit_reason=ExitReason.STOP_LOSS,
        same_bar_ambiguity=False,
        atr14=2.0,
        stop_mult=0.10,
    )

    # Gross PnL: 1000 * (102.0 - 100.0) = 2000.0
    assert trade.gross_pnl == pytest.approx(2000.0)

    # Commissions: 1000 * 0.0035 = 3.50 entry, 3.50 exit -> total 7.00
    assert trade.entry_commission == pytest.approx(3.50)
    assert trade.exit_commission == pytest.approx(3.50)
    assert trade.total_commission == pytest.approx(7.00)

    # Scenario A (0 bps): 2000 - 7 = 1993.00
    assert trade.net_pnl_a == pytest.approx(1993.00)

    # Scenario B (2 bps): entry_slip = 100,000 * 0.0002 = 20.0; exit_slip = 102,000 * 0.0002 = 20.40
    # Net B = 2000 - 7 - 20 - 20.40 = 1952.60
    assert trade.entry_slippage_cost_b == pytest.approx(20.00)
    assert trade.exit_slippage_cost_b == pytest.approx(20.40)
    assert trade.net_pnl_b == pytest.approx(1952.60)

    # Scenario C (5 bps): entry_slip = 100,000 * 0.0005 = 50.0; exit_slip = 102,000 * 0.0005 = 51.0
    # Net C = 2000 - 7 - 50 - 51 = 1892.00
    assert trade.entry_slippage_cost_c == pytest.approx(50.00)
    assert trade.exit_slippage_cost_c == pytest.approx(51.00)
    assert trade.net_pnl_c == pytest.approx(1892.00)

    # R-multiple: 2000.0 / (1000 * 0.20) = 10.0 R
    assert trade.r_multiple == pytest.approx(10.0)
