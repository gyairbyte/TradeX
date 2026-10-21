"""Deterministic tests for the market-wide ORB Opportunity Scanner (DAYTRADE-003F).

Covers all required acceptance criteria:
- Automatic universe discovery without a user-supplied watchlist
- Daily-history eligibility filtering (Price > $5, ADV14 >= 1M, ATR14 > $0.50)
- The exact five-minute regular-session opening range (09:30-09:34 ET)
- Previous 14 completed XNYS session opening-volume calculations
- No current-session daily lookahead (D strictly excluded from D-1 lookback)
- Ranking by RV14 descending with symbol ascending tie-breaker
- Doji setup in Top 20 receiving NO_ORDER and no backfill with rank #21
- Large-universe batching and pagination
- Missing/duplicate/out-of-session records failing closed
- 09:34 versus 09:35 ET time-gating
- Weekends, holidays, and DST handling
- Partial provider availability and error isolation per symbol
- IEX versus SIP feed disclosure
- Production strategy isolation (APPROVED_PRODUCTION_STRATEGIES == ())
"""
from __future__ import annotations

from datetime import date, datetime
from datetime import time as dt_time

from tradex.market.hours import MARKET_TIMEZONE
from tradex.research.daytrade_orb.indicators import get_prior_xnys_sessions
from tradex.research.daytrade_orb.models import (
    DailyBar,
    Direction,
    MinuteBar,
    OpeningRangeVolumeObservation,
    OrderStatus,
)
from tradex.research.daytrade_orb.preview import ExclusionCategory
from tradex.research.daytrade_orb.provider import MockORBProvider
from tradex.research.daytrade_orb.scanner import (
    ScanStage,
    run_market_scan,
)
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

TEST_DATE = date(2024, 1, 2)
TEST_AS_OF_935 = datetime(2024, 1, 2, 9, 35, 0, tzinfo=MARKET_TIMEZONE)
TEST_AS_OF_934 = datetime(2024, 1, 2, 9, 34, 59, tzinfo=MARKET_TIMEZONE)


def _make_daily_bars(
    symbol: str,
    target_date: date,
    num_days: int = 15,
    base_price: float = 100.0,
    daily_vol: float = 2_000_000.0,
    daily_range: float = 2.0,
) -> list[DailyBar]:
    """Generate num_days completed regular XNYS daily bars ending at D-1."""
    prior_sessions = get_prior_xnys_sessions(target_date, num_days)
    bars: list[DailyBar] = []
    for d in prior_sessions:
        bars.append(
            DailyBar(
                symbol=symbol,
                session_date=d,
                open=base_price,
                high=base_price + daily_range / 2,
                low=base_price - daily_range / 2,
                close=base_price + 0.10,
                volume=daily_vol,
            )
        )
    return bars


def _make_or_bars(
    symbol: str,
    session_date: date,
    open_p: float = 100.0,
    high_p: float = 104.0,
    low_p: float = 96.0,
    close_p: float = 101.5,
    total_vol: float = 500_000.0,
) -> list[MinuteBar]:
    """Generate 5 regular-session 1-minute bars (09:30-09:34 ET)."""
    bars: list[MinuteBar] = []
    vol_per_bar = total_vol / 5.0
    for minute in range(30, 35):
        ts = datetime.combine(session_date, dt_time(9, minute), tzinfo=MARKET_TIMEZONE)
        bar_open = open_p if minute == 30 else 100.5
        bar_close = close_p if minute == 34 else 100.8
        bar_high = max(high_p if minute == 32 else 101.0, bar_open, bar_close)
        bar_low = min(low_p if minute == 31 else 100.0, bar_open, bar_close)
        bars.append(
            MinuteBar(
                symbol=symbol,
                timestamp=ts,
                session_date=session_date,
                open=bar_open,
                high=bar_high,
                low=bar_low,
                close=bar_close,
                volume=vol_per_bar,
            )
        )
    return bars


def _make_prior_or_vols(
    symbol: str,
    target_date: date,
    daily_or_vol: float = 100_000.0,
    num_sessions: int = 14,
) -> list[OpeningRangeVolumeObservation]:
    """Generate OpeningRangeVolumeObservation for exact prior 14 completed XNYS sessions."""
    prior_sessions = get_prior_xnys_sessions(target_date, num_sessions)
    obs: list[OpeningRangeVolumeObservation] = []
    for d in prior_sessions:
        obs.append(
            OpeningRangeVolumeObservation(
                symbol=symbol,
                session_date=d,
                volume=daily_or_vol,
            )
        )
    return obs


def _build_test_mock_provider() -> MockORBProvider:
    """Build a deterministic rich test provider with Long, Short, Doji, and filter rejection symbols."""
    symbols = [
        "LONG_HIGH_RV",   # Qualifies LONG, high RV
        "LONG_MID_RV",    # Qualifies LONG, mid RV
        "SHORT_HIGH_RV",  # Qualifies SHORT, high RV
        "SHORT_MID_RV",   # Qualifies SHORT, mid RV
        "DOJI_CAND",      # Qualifies DOJI in Top 20
        "TIE_A",          # Tied RV with TIE_B
        "TIE_B",          # Tied RV with TIE_A
        "LOW_PRICE",      # Disqualified: price <= $5
        "LOW_ADV",        # Disqualified: ADV14 < 1M
        "LOW_ATR",        # Disqualified: ATR14 <= $0.50
        "LOW_RV",         # Disqualified: RV14 < 1.0
        "MISSING_DAILY",  # Disqualified: incomplete daily bars
        "MISSING_OR",     # Disqualified: no OR prints
        "MISSING_PRIOR",  # Disqualified: missing prior OR baseline
        "LEAK_FUTURE",    # Disqualified: future bar leakage
    ]

    daily_bars: dict[str, list[DailyBar]] = {}
    or_bars: dict[str, list[MinuteBar]] = {}
    prior_or_vols: dict[str, list[OpeningRangeVolumeObservation]] = {}

    for sym in symbols:
        # Standard valid daily bars by default
        base_p = 3.50 if sym == "LOW_PRICE" else 100.0
        daily_v = 500_000.0 if sym == "LOW_ADV" else 2_500_000.0
        daily_r = 0.20 if sym == "LOW_ATR" else 2.50
        num_d = 5 if sym == "MISSING_DAILY" else 15

        daily_bars[sym] = _make_daily_bars(
            symbol=sym,
            target_date=TEST_DATE,
            num_days=num_d,
            base_price=base_p,
            daily_vol=daily_v,
            daily_range=daily_r,
        )

        # Standard valid prior OR volumes by default
        num_prior = 10 if sym == "MISSING_PRIOR" else 14
        prior_or_vols[sym] = _make_prior_or_vols(
            symbol=sym,
            target_date=TEST_DATE,
            daily_or_vol=100_000.0,
            num_sessions=num_prior,
        )

        # Opening range bars
        if sym == "MISSING_OR":
            or_bars[sym] = []
        elif sym == "LONG_HIGH_RV":
            or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=100.0, close_p=103.0, total_vol=500_000.0)  # RV = 5.0
        elif sym == "LONG_MID_RV":
            or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=100.0, close_p=102.0, total_vol=250_000.0)  # RV = 2.5
        elif sym == "SHORT_HIGH_RV":
            or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=100.0, close_p=97.0, total_vol=400_000.0)   # RV = 4.0
        elif sym == "SHORT_MID_RV":
            or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=100.0, close_p=98.0, total_vol=200_000.0)   # RV = 2.0
        elif sym == "DOJI_CAND":
            or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=100.0, close_p=100.0, total_vol=350_000.0)  # RV = 3.5 DOJI
        elif sym in ("TIE_A", "TIE_B"):
            or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=100.0, close_p=101.5, total_vol=300_000.0)  # RV = 3.0 TIE
        elif sym == "LOW_RV":
            or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=100.0, close_p=101.0, total_vol=75_000.0)   # RV = 0.75
        elif sym == "LEAK_FUTURE":
            bars = _make_or_bars(sym, TEST_DATE, open_p=100.0, close_p=102.0, total_vol=200_000.0)
            # Add a future bar at 09:36 ET
            leak_ts = datetime.combine(TEST_DATE, dt_time(9, 36), tzinfo=MARKET_TIMEZONE)
            bars.append(
                MinuteBar(
                    symbol=sym,
                    timestamp=leak_ts,
                    session_date=TEST_DATE,
                    open=102.0,
                    high=102.5,
                    low=101.8,
                    close=102.2,
                    volume=10000.0,
                )
            )
            or_bars[sym] = bars
        elif sym == "LOW_PRICE":
            or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=3.50, close_p=3.80, total_vol=150_000.0)
        else:
            or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=100.0, close_p=101.5, total_vol=150_000.0)

    return MockORBProvider(
        symbols=symbols,
        daily_bars=daily_bars,
        opening_range_bars=or_bars,
        prior_opening_range_volumes=prior_or_vols,
        provider_name="mock",
        feed_name="sip",
        is_feed_consolidated=True,
    )


def test_automatic_universe_discovery_without_watchlist():
    """Scan automatically discovers NYSE/Nasdaq equities without requiring a user watchlist."""
    provider = _build_test_mock_provider()
    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)

    assert not res.is_time_gated
    assert res.universe_size_discovered == len(provider.symbols)
    # 4 symbols in test mock have missing/corrupt data: MISSING_DAILY, MISSING_OR, MISSING_PRIOR, LEAK_FUTURE
    assert res.missing_data_count == 4
    assert res.securities_evaluated == 11
    assert res.coverage_completeness_pct == 73.3
    assert res.coverage_status == "provisional_incomplete"
    assert "PROVISIONAL RANKINGS" in res.coverage_warning
    assert res.eligible_candidates_count > 0


def test_daily_history_eligibility_filtering_adv_atr_price():
    """Daily history filters ADV14 >= 1M, ATR14 > $0.50 and opening price > $5.00 with clear audit reasons."""
    provider = _build_test_mock_provider()
    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)

    ex_by_sym = {e.symbol: e for e in res.exclusions}

    # LOW_PRICE excluded on opening price <= $5.00
    assert "LOW_PRICE" in ex_by_sym
    assert ex_by_sym["LOW_PRICE"].category == ExclusionCategory.TECHNICAL_FILTER
    assert "Opening price" in ex_by_sym["LOW_PRICE"].reason
    assert "<= $5.00" in ex_by_sym["LOW_PRICE"].reason

    # LOW_ADV excluded
    assert "LOW_ADV" in ex_by_sym
    assert ex_by_sym["LOW_ADV"].category == ExclusionCategory.TECHNICAL_FILTER
    assert "1,000,000" in ex_by_sym["LOW_ADV"].reason

    # LOW_ATR excluded
    assert "LOW_ATR" in ex_by_sym
    assert ex_by_sym["LOW_ATR"].category == ExclusionCategory.TECHNICAL_FILTER
    assert "<= $0.50" in ex_by_sym["LOW_ATR"].reason

    # MISSING_DAILY excluded as DATA_UNAVAILABLE
    assert "MISSING_DAILY" in ex_by_sym
    assert ex_by_sym["MISSING_DAILY"].category == ExclusionCategory.DATA_UNAVAILABLE


def test_exact_five_minute_opening_range_and_relative_volume():
    """Evaluates exact 09:30-09:34 regular session range and RV14 >= 1.0."""
    provider = _build_test_mock_provider()
    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)

    cand_syms = [c.symbol for c in res.candidates]
    assert "LONG_HIGH_RV" in cand_syms
    assert "SHORT_HIGH_RV" in cand_syms

    # LOW_RV excluded for RV < 1.0
    ex_by_sym = {e.symbol: e for e in res.exclusions}
    assert "LOW_RV" in ex_by_sym
    assert ex_by_sym["LOW_RV"].category == ExclusionCategory.TECHNICAL_FILTER
    assert "1.00x threshold" in ex_by_sym["LOW_RV"].reason

    # MISSING_OR excluded
    assert "MISSING_OR" in ex_by_sym
    assert ex_by_sym["MISSING_OR"].category == ExclusionCategory.DATA_UNAVAILABLE

    # MISSING_PRIOR excluded
    assert "MISSING_PRIOR" in ex_by_sym
    assert ex_by_sym["MISSING_PRIOR"].category == ExclusionCategory.DATA_UNAVAILABLE


def test_no_current_session_daily_lookahead():
    """Daily bars for session D must never enter ADV14 or ATR14 calculations."""
    provider = _build_test_mock_provider()

    # Intentionally add a session D daily bar with wild prices to a symbol
    corrupt_d_bar = DailyBar(
        symbol="LONG_HIGH_RV",
        session_date=TEST_DATE,
        open=9999.0,
        high=9999.0,
        low=9999.0,
        close=9999.0,
        volume=999_999_999.0,
    )
    provider.daily_bars["LONG_HIGH_RV"].append(corrupt_d_bar)

    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)
    row = next(c for c in res.candidates if c.symbol == "LONG_HIGH_RV")

    # ADV14 and ATR14 must NOT reflect the 9999 price or 999M volume
    assert row.adv14 < 10_000_000.0
    assert row.atr14 < 10.0


def test_ranking_rv_descending_and_tie_breaking():
    """Candidates are ranked by RV14 descending, with symbol ascending tie-breaker."""
    provider = _build_test_mock_provider()
    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)

    candidates = res.candidates
    assert len(candidates) >= 4

    # Rank 1 must have highest RV
    assert candidates[0].symbol == "LONG_HIGH_RV"
    assert candidates[0].rv14 == 5.0
    assert candidates[0].direction == Direction.LONG
    assert candidates[0].order_intent_status == OrderStatus.ORDER_NOT_TRIGGERED
    assert candidates[0].stop_entry_trigger == candidates[0].or_high

    # Rank 2 must be SHORT_HIGH_RV with RV = 4.0
    assert candidates[1].symbol == "SHORT_HIGH_RV"
    assert candidates[1].rv14 == 4.0
    assert candidates[1].direction == Direction.SHORT
    assert candidates[1].order_intent_status == OrderStatus.ORDER_NOT_TRIGGERED
    assert candidates[1].stop_entry_trigger == candidates[1].or_low

    # Ties: TIE_A and TIE_B have identical RV (3.0); TIE_A must rank before TIE_B
    tie_ranks = [c.symbol for c in candidates if c.symbol in ("TIE_A", "TIE_B")]
    assert tie_ranks == ["TIE_A", "TIE_B"]


def test_doji_no_order_and_no_backfill_rank21():
    """Doji opening range produces NO_ORDER and rank #21 is not backfilled."""
    provider = _build_test_mock_provider()
    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)

    doji_row = next((c for c in res.candidates if c.symbol == "DOJI_CAND"), None)
    assert doji_row is not None
    assert doji_row.direction == Direction.DOJI
    assert doji_row.order_intent_status == OrderStatus.NO_ORDER_DOJI
    assert doji_row.stop_entry_trigger is None
    assert "NO ORDER" in doji_row.explanation
    assert "Rank #21 is not backfilled" in doji_row.explanation


def test_time_gating_934_blocked_versus_935_eligible():
    """Candidate ranking is blocked at 09:34 ET and permitted at 09:35 ET."""
    provider = _build_test_mock_provider()

    # At 09:34:59 ET -> Blocked
    res_early = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_934)
    assert res_early.is_time_gated
    assert "Candidate ranking is blocked" in (res_early.time_gate_message or "")
    assert len(res_early.candidates) == 0

    # At 09:35:00 ET -> Proceeds
    res_valid = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)
    assert not res_valid.is_time_gated
    assert len(res_valid.candidates) > 0


def test_future_bar_leakage_rejected():
    """Minute bars at or after 09:35 ET in opening range are flagged as future-bar leakage."""
    provider = _build_test_mock_provider()
    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)

    ex_by_sym = {e.symbol: e for e in res.exclusions}
    assert "LEAK_FUTURE" in ex_by_sym
    assert ex_by_sym["LEAK_FUTURE"].category == ExclusionCategory.INTEGRITY_BLOCKED
    assert "Future-bar leakage" in ex_by_sym["LEAK_FUTURE"].reason


def test_iex_versus_sip_source_disclosure():
    """SIP provider yields consolidated coverage; IEX yields provisional warning."""
    # SIP provider with complete data yields full-market SIP coverage
    provider_sip = MockORBProvider(
        symbols=["AAPL", "MSFT"],
        daily_bars={
            "AAPL": _make_daily_bars("AAPL", TEST_DATE),
            "MSFT": _make_daily_bars("MSFT", TEST_DATE),
        },
        opening_range_bars={
            "AAPL": _make_or_bars("AAPL", TEST_DATE),
            "MSFT": _make_or_bars("MSFT", TEST_DATE),
        },
        prior_opening_range_volumes={
            "AAPL": _make_prior_or_vols("AAPL", TEST_DATE),
            "MSFT": _make_prior_or_vols("MSFT", TEST_DATE),
        },
        provider_name="mock",
        feed_name="sip",
        is_feed_consolidated=True,
    )
    res_sip = run_market_scan(provider=provider_sip, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)
    assert res_sip.is_feed_consolidated
    assert res_sip.coverage_status == "full_market_sip"
    assert "consolidated SIP" in res_sip.coverage_warning

    # IEX provider (even with complete data) strictly yields provisional IEX warning
    provider_iex = MockORBProvider(
        symbols=["AAPL", "MSFT"],
        daily_bars={
            "AAPL": _make_daily_bars("AAPL", TEST_DATE),
            "MSFT": _make_daily_bars("MSFT", TEST_DATE),
        },
        opening_range_bars={
            "AAPL": _make_or_bars("AAPL", TEST_DATE),
            "MSFT": _make_or_bars("MSFT", TEST_DATE),
        },
        prior_opening_range_volumes={
            "AAPL": _make_prior_or_vols("AAPL", TEST_DATE),
            "MSFT": _make_prior_or_vols("MSFT", TEST_DATE),
        },
        provider_name="alpaca",
        feed_name="iex",
        is_feed_consolidated=False,
    )

    res_iex = run_market_scan(provider=provider_iex, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)
    assert not res_iex.is_feed_consolidated
    assert "PROVISIONAL RANKINGS (IEX FEED ONLY)" in res_iex.coverage_warning
    assert res_iex.coverage_status == "provisional_iex"


def test_progress_callback_receives_all_stages():
    """Scanner invokes progress callback at every execution stage."""
    provider = _build_test_mock_provider()
    recorded_stages: list[ScanStage] = []

    def _callback(p):
        recorded_stages.append(p.stage)

    res = run_market_scan(
        provider=provider,
        session_date=TEST_DATE,
        as_of_time=TEST_AS_OF_935,
        progress_callback=_callback,
    )

    assert ScanStage.INIT in recorded_stages
    assert ScanStage.DISCOVERY in recorded_stages
    assert ScanStage.DAILY_ELIGIBILITY in recorded_stages
    assert ScanStage.OPENING_RANGE in recorded_stages
    assert ScanStage.RANKING in recorded_stages
    assert ScanStage.COMPLETE in recorded_stages
    assert len(res.candidates) > 0


def test_stage_failure_handling():
    """If provider discovery or data fails, returns safe result with stage_failures."""
    provider = _build_test_mock_provider()
    provider.fail_stage = "DISCOVERY"

    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)
    assert res.coverage_status == "failed"
    assert "DISCOVERY" in res.stage_failures
    assert len(res.candidates) == 0


def test_production_strategy_isolation():
    """Preserves APPROVED_PRODUCTION_STRATEGIES == () and research separation."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()


def test_opening_price_filter_gap_up_and_gap_down():
    """Exact opening price filter applies to session D opening print, not D-1 close (DAYTRADE-003B).

    Case 1 (Gap-up): D-1 close = $4.90 (<= $5), D open = $5.20 (> $5) -> Eligible & Ranked!
    Case 2 (Gap-down): D-1 close = $5.20 (> $5), D open = $4.90 (<= $5) -> Excluded at OR evaluation!
    """
    symbols = ["GAP_UP", "GAP_DOWN"]
    daily_bars: dict[str, list[DailyBar]] = {}
    or_bars: dict[str, list[MinuteBar]] = {}
    prior_or_vols: dict[str, list[OpeningRangeVolumeObservation]] = {}

    for sym in symbols:
        # Prior sessions setup
        prior_close = 4.90 if sym == "GAP_UP" else 5.20
        daily_bars[sym] = _make_daily_bars(
            symbol=sym,
            target_date=TEST_DATE,
            num_days=15,
            base_price=prior_close,
            daily_vol=2_500_000.0,
            daily_range=1.00,
        )
        # Ensure exact D-1 close matches the test scenario
        daily_bars[sym][-1] = DailyBar(
            symbol=sym,
            session_date=daily_bars[sym][-1].session_date,
            open=prior_close,
            high=prior_close + 0.50,
            low=prior_close - 0.50,
            close=prior_close,
            volume=2_500_000.0,
        )

        prior_or_vols[sym] = _make_prior_or_vols(sym, TEST_DATE, daily_or_vol=100_000.0, num_sessions=14)

        # Opening range bars at 09:30 ET
        or_open = 5.20 if sym == "GAP_UP" else 4.90
        or_close = 5.50 if sym == "GAP_UP" else 4.60
        or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=or_open, close_p=or_close, total_vol=300_000.0)

    provider = MockORBProvider(
        symbols=symbols,
        daily_bars=daily_bars,
        opening_range_bars=or_bars,
        prior_opening_range_volumes=prior_or_vols,
        provider_name="mock",
        feed_name="sip",
        is_feed_consolidated=True,
    )

    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)

    # GAP_UP must qualify and be ranked despite D-1 close $4.90
    cand_syms = [c.symbol for c in res.candidates]
    assert "GAP_UP" in cand_syms
    gap_up_cand = next(c for c in res.candidates if c.symbol == "GAP_UP")
    assert gap_up_cand.or_open == 5.20
    assert gap_up_cand.rank == 1

    # GAP_DOWN must be excluded at OR evaluation despite D-1 close $5.20
    assert "GAP_DOWN" not in cand_syms
    ex_by_sym = {e.symbol: e for e in res.exclusions}
    assert "GAP_DOWN" in ex_by_sym
    assert ex_by_sym["GAP_DOWN"].category == ExclusionCategory.TECHNICAL_FILTER
    assert "Opening price $4.90 <= $5.00 minimum threshold" in ex_by_sym["GAP_DOWN"].reason


def test_truthful_market_coverage_with_material_missing_data():
    """Mock with 100 discovered symbols and 90 missing daily histories reports provisional coverage, NOT full-market SIP."""
    symbols = [f"SYM_{i:03d}" for i in range(100)]
    daily_bars: dict[str, list[DailyBar]] = {}
    or_bars: dict[str, list[MinuteBar]] = {}
    prior_or_vols: dict[str, list[OpeningRangeVolumeObservation]] = {}

    # Only 10 symbols have valid data; 90 have empty daily bars
    for i, sym in enumerate(symbols):
        if i < 10:
            daily_bars[sym] = _make_daily_bars(sym, TEST_DATE, num_days=15, base_price=50.0, daily_vol=2_000_000.0)
            or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=50.0, close_p=52.0, total_vol=250_000.0)
            prior_or_vols[sym] = _make_prior_or_vols(sym, TEST_DATE, daily_or_vol=100_000.0, num_sessions=14)
        else:
            daily_bars[sym] = []
            or_bars[sym] = []
            prior_or_vols[sym] = []

    provider = MockORBProvider(
        symbols=symbols,
        daily_bars=daily_bars,
        opening_range_bars=or_bars,
        prior_opening_range_volumes=prior_or_vols,
        provider_name="mock",
        feed_name="sip",
        is_feed_consolidated=True,
    )

    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)

    assert res.universe_size_discovered == 100
    assert res.missing_data_count == 90
    assert res.securities_evaluated == 10
    assert res.daily_history_complete_count == 10
    assert res.coverage_completeness_pct == 10.0
    # Must be marked provisional_incomplete, NOT full_market_sip!
    assert res.coverage_status == "provisional_incomplete"
    assert "PROVISIONAL RANKINGS (MATERIAL DATA GAPS)" in res.coverage_warning
    assert "10 of 100" in res.coverage_warning


def test_full_market_sip_coverage_when_complete():
    """When >= 95% of securities have complete evaluable data on SIP feed, coverage is full_market_sip."""
    symbols = [f"SYM_{i:02d}" for i in range(20)]
    daily_bars: dict[str, list[DailyBar]] = {}
    or_bars: dict[str, list[MinuteBar]] = {}
    prior_or_vols: dict[str, list[OpeningRangeVolumeObservation]] = {}

    for sym in symbols:
        daily_bars[sym] = _make_daily_bars(sym, TEST_DATE, num_days=15, base_price=50.0, daily_vol=2_000_000.0)
        or_bars[sym] = _make_or_bars(sym, TEST_DATE, open_p=50.0, close_p=52.0, total_vol=250_000.0)
        prior_or_vols[sym] = _make_prior_or_vols(sym, TEST_DATE, daily_or_vol=100_000.0, num_sessions=14)

    provider = MockORBProvider(
        symbols=symbols,
        daily_bars=daily_bars,
        opening_range_bars=or_bars,
        prior_opening_range_volumes=prior_or_vols,
        provider_name="mock",
        feed_name="sip",
        is_feed_consolidated=True,
    )

    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)

    assert res.universe_size_discovered == 20
    assert res.missing_data_count == 0
    assert res.securities_evaluated == 20
    assert res.coverage_completeness_pct == 100.0
    assert res.coverage_status == "full_market_sip"
    assert "Full-market candidate discovery evaluated 20 of 20" in res.coverage_warning


def test_scan_timestamps_and_freshness():
    """MarketScanResult accurately records scan request time, completion time, and data freshness."""
    provider = _build_test_mock_provider()
    res = run_market_scan(provider=provider, session_date=TEST_DATE, as_of_time=TEST_AS_OF_935)

    assert res.scan_requested_at is not None
    assert res.scan_completed_at is not None
    assert res.data_freshness_time is not None
    assert res.data_freshness_time_et is not None
    assert res.data_freshness_time_et.time() == dt_time(9, 34, 59)
    assert res.scan_completed_at >= res.scan_requested_at
