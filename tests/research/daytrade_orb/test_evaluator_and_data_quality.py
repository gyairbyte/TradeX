"""End-to-end evaluator orchestration, calendar checks, and candidate pool completeness tests."""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from tradex.market.hours import _calendar
from tradex.research.daytrade_orb import (
    DailyBar,
    MinuteBar,
    OpeningRangeVolumeObservation,
    ORBEvaluator,
    UniverseMember,
)
from tradex.research.daytrade_orb.portfolio import CANONICAL_TRADE_MINUTES

NY_TZ = ZoneInfo("America/New_York")


def _setup_synthetic_session_data(
    session_date: date,
    num_symbols: int = 5,
) -> tuple[
    list[UniverseMember],
    dict[str, list[DailyBar]],
    dict[str, list[OpeningRangeVolumeObservation]],
    dict[str, list[MinuteBar]],
    dict[str, list[MinuteBar]],
]:
    cal = _calendar()
    prev = cal.previous_session(session_date)
    prior_16_dates = [s.date() for s in cal.sessions_window(prev, -16)]
    prior_14_dates = prior_16_dates[-14:]

    members: list[UniverseMember] = []
    daily_bars: dict[str, list[DailyBar]] = {}
    prior_or_vols: dict[str, list[OpeningRangeVolumeObservation]] = {}
    or_bars: dict[str, list[MinuteBar]] = {}
    trade_bars: dict[str, list[MinuteBar]] = {}

    for i in range(1, num_symbols + 1):
        sym = f"SYM{i:02d}"
        members.append(UniverseMember(sym, "NYSE", True))

        # 16 daily bars leading up to D-1
        db_list: list[DailyBar] = []
        for d in prior_16_dates:
            db_list.append(DailyBar(sym, d, 50.0, 52.0, 48.0, 50.0, 1_500_000.0))
        daily_bars[sym] = db_list

        # Prior 14 OR volumes: 25,000 each for exact preceding 14 XNYS sessions
        prior_or_vols[sym] = [
            OpeningRangeVolumeObservation(sym, d, 25_000.0)
            for d in prior_14_dates
        ]

        # 5 opening range minute bars: open 50.0, close 52.0, high 52.0, low 49.0 -> Bullish (LONG @ 52.0), volume 75,000 (RV = 3.0)
        or_list: list[MinuteBar] = []
        for m_idx, m in enumerate([30, 31, 32, 33, 34]):
            ts = datetime(session_date.year, session_date.month, session_date.day, 9, m, tzinfo=NY_TZ)
            o = 50.0 if m_idx == 0 else 51.0
            c = 52.0 if m_idx == 4 else 51.0
            or_list.append(MinuteBar(sym, ts, session_date, o, 52.0, 49.0, c, 15_000.0))
        or_bars[sym] = or_list

        # Complete trade path: 09:35..15:59
        # Triggers entry at 09:36 (high 53.0 >= 52.0, low 51.85 > stop 51.80)
        # Liquidates at 15:59 close 54.0
        tb_list: list[MinuteBar] = []
        for t in CANONICAL_TRADE_MINUTES:
            ts = datetime(session_date.year, session_date.month, session_date.day, t.hour, t.minute, tzinfo=NY_TZ)
            if t == time(9, 35):
                o, h, l, c = 51.0, 51.5, 50.8, 51.2
            elif t == time(9, 36):
                o, h, l, c = 51.85, 53.0, 51.85, 52.5
            elif t == time(15, 59):
                o, h, l, c = 53.5, 54.5, 53.0, 54.0
            else:
                o, h, l, c = 52.5, 53.0, 52.0, 52.5
            tb_list.append(MinuteBar(sym, ts, session_date, o, h, l, c, 10_000.0))
        trade_bars[sym] = tb_list

    return members, daily_bars, prior_or_vols, or_bars, trade_bars


def test_evaluator_end_to_end_session() -> None:
    """Requirement: ORBEvaluator completes synthetic session with correct ranking and execution."""
    evaluator = ORBEvaluator(initial_equity=25000.0, leverage_cap=4.0)
    d = date(2025, 6, 2)
    members, daily_b, prior_v, or_b, trade_b = _setup_synthetic_session_data(d, num_symbols=5)

    result = evaluator.evaluate_session(
        session_date=d,
        universe_members=members,
        daily_bars_by_symbol=daily_b,
        prior_or_volumes_by_symbol=prior_v,
        opening_minute_bars_by_symbol=or_b,
        trade_path_bars_by_symbol=trade_b,
        candidate_pool_complete=True,
    )

    assert result.is_valid is True
    assert result.status == "completed"
    assert result.candidate_count == 5
    assert result.qualified_candidate_count == 5
    assert result.trades_triggered_count > 0
    assert result.session_net_return_b > 0.0


def test_evaluator_candidate_pool_missing_daily_history_fails_closed() -> None:
    """Requirement: Missing daily history for any active PIT universe member causes fail closed."""
    evaluator = ORBEvaluator()
    d = date(2025, 6, 2)
    members, daily_b, prior_v, or_b, trade_b = _setup_synthetic_session_data(d, num_symbols=3)

    # Empty daily bars for active member SYM02
    daily_b["SYM02"] = []

    result = evaluator.evaluate_session(d, members, daily_b, prior_v, or_b, trade_b)
    assert result.is_valid is False
    assert result.status == "non_computable"
    assert "missing daily bars" in result.error_reason.lower()


def test_evaluator_candidate_pool_missing_rv_history_fails_closed() -> None:
    """Requirement: Missing prior OR volume history for active member causes fail closed."""
    evaluator = ORBEvaluator()
    d = date(2025, 6, 2)
    members, daily_b, prior_v, or_b, trade_b = _setup_synthetic_session_data(d, num_symbols=3)

    # Missing prior volume for SYM03
    prior_v["SYM03"] = []

    result = evaluator.evaluate_session(d, members, daily_b, prior_v, or_b, trade_b)
    assert result.is_valid is False
    assert result.status == "non_computable"
    assert "missing prior or volume" in result.error_reason.lower()


def test_evaluator_candidate_pool_missing_or_minutes_fails_closed() -> None:
    """Requirement: Missing opening-range minute bar for active member causes fail closed."""
    evaluator = ORBEvaluator()
    d = date(2025, 6, 2)
    members, daily_b, prior_v, or_b, trade_b = _setup_synthetic_session_data(d, num_symbols=3)

    # SYM01 only has 4 bars (missing 09:34)
    or_b["SYM01"] = or_b["SYM01"][:4]

    result = evaluator.evaluate_session(d, members, daily_b, prior_v, or_b, trade_b)
    assert result.is_valid is False
    assert result.status == "non_computable"
    assert "malformed or missing opening range" in result.error_reason.lower()


def test_evaluator_candidate_pool_technical_failure_remains_normal_ineligible() -> None:
    """Requirement: Genuine technical filter failure remains normal non-qualification, NOT an error."""
    evaluator = ORBEvaluator()
    d = date(2025, 6, 2)
    members, daily_b, prior_v, or_b, trade_b = _setup_synthetic_session_data(d, num_symbols=3)

    # Modify SYM01 opening price to $4.00 (below $5 filter)
    # All Stage-A data is completely present!
    new_or = []
    for b in or_b["SYM01"]:
        new_or.append(MinuteBar(b.symbol, b.timestamp, b.session_date, 4.0, 4.5, 3.8, 4.2, b.volume))
    or_b["SYM01"] = new_or

    result = evaluator.evaluate_session(d, members, daily_b, prior_v, or_b, trade_b)
    # Session completes validly!
    assert result.is_valid is True
    assert result.candidate_count == 3
    # Only SYM02 and SYM03 qualified
    assert result.qualified_candidate_count == 2


def test_session_calendar_early_close_excluded() -> None:
    """Requirement: Exchange early-close session returns EXCLUDED_EARLY_CLOSE."""
    evaluator = ORBEvaluator()
    # Black Friday 2024 is an early close session (closes at 13:00 ET)
    d_early = date(2024, 11, 29)
    members, daily_b, prior_v, or_b, trade_b = _setup_synthetic_session_data(d_early, num_symbols=2)

    result = evaluator.evaluate_session(d_early, members, daily_b, prior_v, or_b, trade_b)
    assert result.is_valid is False
    assert result.status == "EXCLUDED_EARLY_CLOSE"
    assert "early-close" in result.error_reason.lower()


def test_session_calendar_non_session_date_rejected() -> None:
    """Requirement: Non-trading session date (e.g. Saturday or holiday) fails closed."""
    evaluator = ORBEvaluator()
    # Saturday June 7, 2025 is not a trading day
    d_sat = date(2025, 6, 7)

    result = evaluator.evaluate_session(
        d_sat,
        universe_members=[],
        daily_bars_by_symbol={},
        prior_or_volumes_by_symbol={},
        opening_minute_bars_by_symbol={},
        trade_path_bars_by_symbol={},
    )
    assert result.is_valid is False
    assert result.status == "non_computable"
    assert "not a valid xnys trading session" in result.error_reason.lower()
