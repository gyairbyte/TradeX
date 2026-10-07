"""Opening range qualification, candidate filtering, and Top-20 ranking tests."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from tradex.research.daytrade_orb import (
    Candidate,
    Direction,
    MinuteBar,
    OpeningRange,
    OrderStatus,
    evaluate_candidate,
    evaluate_opening_range,
    rank_and_select_top_20,
)

NY_TZ = ZoneInfo("America/New_York")


def _make_or_bars(
    symbol: str,
    session_date: date,
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    vol: float,
) -> list[MinuteBar]:
    # 5 bars: 09:30 to 09:34
    bars: list[MinuteBar] = []
    minute_v = vol / 5.0
    for i, m in enumerate([30, 31, 32, 33, 34]):
        ts = datetime(session_date.year, session_date.month, session_date.day, 9, m, tzinfo=NY_TZ)
        # Bar 0 has open_p, bar 4 has close_p
        bar_o = open_p if i == 0 else (open_p + close_p) / 2.0
        bar_c = close_p if i == 4 else (open_p + close_p) / 2.0
        bars.append(
            MinuteBar(
                symbol=symbol,
                timestamp=ts,
                session_date=session_date,
                open=bar_o,
                high=high_p,
                low=low_p,
                close=bar_c,
                volume=minute_v,
            )
        )
    return bars


def test_opening_range_bullish_bearish_doji() -> None:
    """Requirement: Bullish is LONG at OR_high, Bearish is SHORT at OR_low, Doji has NO stop level."""
    d = date(2025, 6, 2)

    # Bullish: Open 100, High 105, Low 99, Close 104
    bull_bars = _make_or_bars("BULL", d, 100.0, 105.0, 99.0, 104.0, 50_000.0)
    or_bull = evaluate_opening_range(bull_bars)
    assert or_bull is not None
    assert or_bull.direction == Direction.LONG
    assert or_bull.stop_level == 105.0
    assert or_bull.or_open == 100.0
    assert or_bull.or_close == 104.0
    assert or_bull.or_high == 105.0
    assert or_bull.or_low == 99.0

    # Bearish: Open 100, High 101, Low 95, Close 96
    bear_bars = _make_or_bars("BEAR", d, 100.0, 101.0, 95.0, 96.0, 50_000.0)
    or_bear = evaluate_opening_range(bear_bars)
    assert or_bear is not None
    assert or_bear.direction == Direction.SHORT
    assert or_bear.stop_level == 95.0

    # Doji: Open 100, High 103, Low 97, Close 100
    doji_bars = _make_or_bars("DOJI", d, 100.0, 103.0, 97.0, 100.0, 50_000.0)
    or_doji = evaluate_opening_range(doji_bars)
    assert or_doji is not None
    assert or_doji.direction == Direction.DOJI
    assert or_doji.stop_level is None


def test_opening_range_missing_or_duplicate_bars_fail_closed() -> None:
    """Requirement: All 5 bars (09:30-09:34) required; missing or duplicate fails closed."""
    d = date(2025, 6, 2)
    valid_bars = _make_or_bars("TEST", d, 100.0, 105.0, 95.0, 102.0, 50_000.0)

    # Missing 1 bar (only 4 bars)
    assert evaluate_opening_range(valid_bars[:4]) is None

    # Duplicate 09:30 bar
    dup_bars = [valid_bars[0]] + valid_bars
    assert evaluate_opening_range(dup_bars) is None


def test_opening_range_symbol_or_date_mismatch_fails_closed() -> None:
    """Requirement: All 5 bars must have the identical symbol and session date."""
    d = date(2025, 6, 2)
    valid_bars = _make_or_bars("TEST", d, 100.0, 105.0, 95.0, 102.0, 50_000.0)

    # Symbol mismatch on bar 2
    corrupt_sym = list(valid_bars)
    corrupt_sym[2] = MinuteBar(
        symbol="OTHER",
        timestamp=valid_bars[2].timestamp,
        session_date=d,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=10_000.0,
    )
    assert evaluate_opening_range(corrupt_sym) is None

    # Date mismatch on bar 3
    corrupt_date = list(valid_bars)
    d_other = date(2025, 6, 3)
    ts_other = datetime(2025, 6, 3, 9, 33, tzinfo=NY_TZ)
    corrupt_date[3] = MinuteBar(
        symbol="TEST",
        timestamp=ts_other,
        session_date=d_other,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=10_000.0,
    )
    assert evaluate_opening_range(corrupt_date) is None


def test_candidate_eligibility_filter_thresholds() -> None:
    """Requirement: Strict filters: price > 5.0, ADV14 >= 1M, ATR14 > 0.50, RV14 >= 1.0."""
    d = date(2025, 6, 2)
    or_obj = OpeningRange("T", d, 10.0, 11.0, 9.0, 10.5, 50_000.0, Direction.LONG, 11.0)

    # 1. Price filter: 5.0 fails, 5.01 passes
    or_5 = OpeningRange("T", d, 5.0, 6.0, 4.0, 5.5, 50_000.0, Direction.LONG, 6.0)
    cand_5 = evaluate_candidate("T", d, or_5, adv14=1_500_000.0, atr14=1.0, mean_prior_or_volume=25_000.0, rv=2.0)
    assert not cand_5.price_passed
    assert not cand_5.is_eligible

    or_501 = OpeningRange("T", d, 5.01, 6.0, 4.0, 5.5, 50_000.0, Direction.LONG, 6.0)
    cand_501 = evaluate_candidate("T", d, or_501, adv14=1_500_000.0, atr14=1.0, mean_prior_or_volume=25_000.0, rv=2.0)
    assert cand_501.price_passed
    assert cand_501.is_eligible

    # 2. ADV filter: 999,999 fails, 1,000,000 passes
    cand_adv_fail = evaluate_candidate("T", d, or_obj, adv14=999_999.0, atr14=1.0, mean_prior_or_volume=25_000.0, rv=2.0)
    assert not cand_adv_fail.adv_passed
    assert not cand_adv_fail.is_eligible

    cand_adv_pass = evaluate_candidate("T", d, or_obj, adv14=1_000_000.0, atr14=1.0, mean_prior_or_volume=25_000.0, rv=2.0)
    assert cand_adv_pass.adv_passed
    assert cand_adv_pass.is_eligible

    # 3. ATR filter: 0.50 fails, 0.51 passes
    cand_atr_fail = evaluate_candidate("T", d, or_obj, adv14=1_500_000.0, atr14=0.50, mean_prior_or_volume=25_000.0, rv=2.0)
    assert not cand_atr_fail.atr_passed
    assert not cand_atr_fail.is_eligible

    cand_atr_pass = evaluate_candidate("T", d, or_obj, adv14=1_500_000.0, atr14=0.51, mean_prior_or_volume=25_000.0, rv=2.0)
    assert cand_atr_pass.atr_passed
    assert cand_atr_pass.is_eligible

    # 4. RV filter: 0.99 fails, 1.0 passes
    cand_rv_fail = evaluate_candidate("T", d, or_obj, adv14=1_500_000.0, atr14=1.0, mean_prior_or_volume=50_000.0, rv=0.99)
    assert not cand_rv_fail.rv_passed
    assert not cand_rv_fail.is_eligible

    cand_rv_pass = evaluate_candidate("T", d, or_obj, adv14=1_500_000.0, atr14=1.0, mean_prior_or_volume=50_000.0, rv=1.0)
    assert cand_rv_pass.rv_passed
    assert cand_rv_pass.is_eligible


def test_top_20_selection_rv_ties_and_no_doji_backfill() -> None:
    """Requirement: Top 20 ranks by RV desc with ticker tie-break; Doji produces NO_ORDER with NO backfill."""
    d = date(2025, 6, 2)
    candidates: list[Candidate] = []
    opening_ranges: dict[str, OpeningRange] = {}

    # Create 25 eligible candidates with varying RVs
    for i in range(1, 26):
        sym = f"SYM{i:02d}"
        is_doji = (i == 5)  # Make rank 5 candidate a Doji
        op_dir = Direction.DOJI if is_doji else Direction.LONG
        op_c = 100.0 if is_doji else 105.0
        op_stop = None if is_doji else 105.0

        op = OpeningRange(sym, d, 100.0, 105.0, 95.0, op_c, 50_000.0, op_dir, op_stop)
        opening_ranges[sym] = op

        # RV decreases from 26.0 down to 2.0
        rv_val = float(30 - i)
        cand = evaluate_candidate(sym, d, op, adv14=2_000_000.0, atr14=2.0, mean_prior_or_volume=25_000.0, rv=rv_val)
        candidates.append(cand)

    ranked = rank_and_select_top_20(candidates, opening_ranges, session_start_equity=25000.0, top_n=20)

    # Exactly 20 selected
    assert len(ranked) == 20
    selected_symbols = [rc.candidate.symbol for rc in ranked]

    # SYM01..SYM20 are in Top 20, SYM21..SYM25 are excluded
    assert "SYM01" in selected_symbols
    assert "SYM20" in selected_symbols
    assert "SYM21" not in selected_symbols

    # Crucial Doji check: SYM05 is in Top 20, produces NO_ORDER_DOJI, and is NOT replaced by SYM21
    rc_doji = next(rc for rc in ranked if rc.candidate.symbol == "SYM05")
    assert rc_doji.order_intent.status == OrderStatus.NO_ORDER_DOJI
    assert rc_doji.order_intent.desired_shares == 0
    assert "SYM21" not in selected_symbols


def test_deterministic_rv_tie_breaker() -> None:
    """Requirement: RV tie breaks deterministically by ticker ascending."""
    d = date(2025, 6, 2)
    candidates: list[Candidate] = []
    opening_ranges: dict[str, OpeningRange] = {}

    for sym in ["MSFT", "AAPL", "GOOG"]:
        op = OpeningRange(sym, d, 50.0, 52.0, 48.0, 51.0, 100_000.0, Direction.LONG, 52.0)
        opening_ranges[sym] = op
        cand = evaluate_candidate(sym, d, op, adv14=2_000_000.0, atr14=1.0, mean_prior_or_volume=50_000.0, rv=2.0)
        candidates.append(cand)

    ranked = rank_and_select_top_20(candidates, opening_ranges, session_start_equity=25000.0, top_n=20)
    ordered_symbols = [rc.candidate.symbol for rc in ranked]
    assert ordered_symbols == ["AAPL", "GOOG", "MSFT"]
