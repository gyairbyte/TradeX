"""Synthetic verification tests for DAYTRADE-003D-CORR-002 sparse-bar methodology.

Zero network calls, deterministic, credential-free.
"""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from tradex.market.hours import _calendar
from tradex.research.daytrade_orb.corr_002_pilot import (
    CANDIDATE_SCREENING_GATE_THRESHOLD,
    CORR_002_SPEC_PATH,
    LOCKED_003D_CORR_002_SPEC_SHA256,
    CandidateScreeningOutcome,
    audit_broad_daily_availability,
    audit_candidate_screening,
    audit_stage_b_price_path,
    determine_pilot_disposition,
    freeze_top_20_selection,
    verify_upstream_spec_hashes,
)
from tradex.research.daytrade_orb.indicators import (
    compute_relative_volume,
    get_prior_xnys_sessions,
)
from tradex.research.daytrade_orb.models import (
    DailyBar,
    DataIntegrityError,
    Direction,
    MinuteBar,
    OpeningRange,
    OpeningRangeVolumeObservation,
)
from tradex.research.daytrade_orb.portfolio import simulate_session_portfolio
from tradex.research.daytrade_orb.ranking import (
    evaluate_candidate,
    evaluate_opening_range,
    rank_and_select_top_20,
)
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

NY_TZ = ZoneInfo("America/New_York")


def _make_bar(
    symbol: str,
    session_date: date,
    minute_time: time,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> MinuteBar:
    dt = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        minute_time.hour,
        minute_time.minute,
        tzinfo=NY_TZ,
    )
    return MinuteBar(
        symbol=symbol,
        timestamp=dt,
        session_date=session_date,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


# -----------------------------------------------------------------------------
# 1. Opening Range Aggregation Tests (Scope B)
# -----------------------------------------------------------------------------


def test_sparse_opening_range_single_bar() -> None:
    """Requirement: One valid bar in the 09:30-09:34 window generates a valid opening range."""
    d = date(2024, 1, 2)
    bar = _make_bar("TEST", d, time(9, 32), 10.0, 12.0, 9.5, 11.5, 15_000.0)

    op = evaluate_opening_range([bar], require_five_bars=False)
    assert op is not None
    assert op.symbol == "TEST"
    assert op.session_date == d
    assert op.or_open == 10.0
    assert op.or_high == 12.0
    assert op.or_low == 9.5
    assert op.or_close == 11.5
    assert op.or_volume == 15_000.0
    assert op.direction == Direction.LONG
    assert op.stop_level == 12.0


def test_sparse_opening_range_three_noncontiguous_bars() -> None:
    """Requirement: Three noncontiguous valid bars (09:30, 09:32, 09:34) generate correct OHLCV."""
    d = date(2024, 1, 2)
    b0 = _make_bar("TEST", d, time(9, 30), 50.0, 52.0, 49.0, 51.0, 10_000.0)
    b1 = _make_bar("TEST", d, time(9, 32), 51.0, 55.0, 50.5, 53.0, 20_000.0)
    b2 = _make_bar("TEST", d, time(9, 34), 53.0, 54.0, 48.0, 48.5, 15_000.0)

    op = evaluate_opening_range([b2, b0, b1], require_five_bars=False)
    assert op is not None
    assert op.or_open == 50.0  # first chronological bar (09:30)
    assert op.or_high == 55.0  # max high across bars
    assert op.or_low == 48.0   # min low across bars
    assert op.or_close == 48.5 # last chronological bar (09:34)
    assert op.or_volume == 45_000.0  # sum of volumes
    assert op.direction == Direction.SHORT
    assert op.stop_level == 48.0


def test_sparse_opening_range_five_bars_preserves_existing() -> None:
    """Requirement: Five bars preserve existing outputs exactly."""
    d = date(2024, 1, 2)
    bars = [
        _make_bar("TEST", d, time(9, 30), 100.0, 102.0, 99.0, 101.0, 5_000.0),
        _make_bar("TEST", d, time(9, 31), 101.0, 103.0, 100.5, 102.0, 6_000.0),
        _make_bar("TEST", d, time(9, 32), 102.0, 105.0, 101.0, 104.0, 8_000.0),
        _make_bar("TEST", d, time(9, 33), 104.0, 104.5, 102.5, 103.0, 4_000.0),
        _make_bar("TEST", d, time(9, 34), 103.0, 103.5, 98.0, 100.0, 7_000.0),
    ]

    op = evaluate_opening_range(bars, require_five_bars=False)
    assert op is not None
    assert op.or_open == 100.0
    assert op.or_high == 105.0
    assert op.or_low == 98.0
    assert op.or_close == 100.0
    assert op.or_volume == 30_000.0
    assert op.direction == Direction.DOJI
    assert op.stop_level is None


def test_sparse_opening_range_zero_bars_no_opening_print() -> None:
    """Requirement: No valid opening bars returns None (NO_OPENING_PRINT_NO_SETUP)."""
    assert evaluate_opening_range([], require_five_bars=False) is None


def test_sparse_opening_range_invalid_and_corrupt_bars_fail_closed() -> None:
    """Requirement: Duplicate minutes, non-finite values, invalid bounds, date/symbol mismatch fail closed."""
    d = date(2024, 1, 2)
    b0 = _make_bar("TEST", d, time(9, 30), 10.0, 12.0, 9.0, 11.0, 5_000.0)

    # 1. Duplicate minute
    dup = [b0, b0]
    assert evaluate_opening_range(dup) is None

    # 2. Inverted bounds (high < low) raises DataIntegrityError at bar construction
    with pytest.raises(DataIntegrityError):
        _make_bar("TEST", d, time(9, 31), 10.0, 8.0, 12.0, 9.0, 5_000.0)

    # 3. Non-finite values raises DataIntegrityError at bar construction
    with pytest.raises(DataIntegrityError):
        _make_bar("TEST", d, time(9, 31), float("nan"), 12.0, 9.0, 11.0, 5_000.0)

    # 4. Symbol mismatch fails closed
    other_sym = _make_bar("OTHER", d, time(9, 31), 10.0, 12.0, 9.0, 11.0, 5_000.0)
    assert evaluate_opening_range([b0, other_sym]) is None

    # 5. Date mismatch fails closed
    other_date = _make_bar("TEST", date(2024, 1, 3), time(9, 31), 10.0, 12.0, 9.0, 11.0, 5_000.0)
    assert evaluate_opening_range([b0, other_date]) is None


# -----------------------------------------------------------------------------
# 2. Prior Opening Range Volume Semantics (Scope A)
# -----------------------------------------------------------------------------


def test_prior_or_volume_zero_and_partial_sessions() -> None:
    """Requirement: Partial valid bars sum volume; zero-bar prior session produces dated observation with volume 0."""
    target_d = date(2024, 1, 16)
    prior_14 = get_prior_xnys_sessions(target_d, 14)

    obs_list = []
    for i, sess_d in enumerate(prior_14):
        # Even sessions have 10,000 vol, odd sessions have 0 vol
        vol = 10_000.0 if i % 2 == 0 else 0.0
        obs_list.append(OpeningRangeVolumeObservation(symbol="TEST", session_date=sess_d, volume=vol))

    rv, mean_vol = compute_relative_volume(obs_list, current_or_volume=20_000.0, target_session=target_d)
    assert rv is not None
    assert mean_vol == pytest.approx(5_000.0)
    assert rv == pytest.approx(4.0)


def test_prior_or_volume_all_zero_denominator_unrankable() -> None:
    """Requirement: All-zero prior RV denominator cannot generate infinite or fabricated RV; returns (None, 0.0)."""
    target_d = date(2024, 1, 16)
    prior_14 = get_prior_xnys_sessions(target_d, 14)

    all_zero_obs = [
        OpeningRangeVolumeObservation(symbol="TEST", session_date=sess_d, volume=0.0)
        for sess_d in prior_14
    ]

    rv, mean_vol = compute_relative_volume(all_zero_obs, current_or_volume=5_000.0, target_session=target_d)
    assert rv is None
    assert mean_vol == 0.0


def test_prior_or_volume_missing_session_fails_closed() -> None:
    """Requirement: Missing even one required prior session fails closed; older sessions do not silently replace."""
    target_d = date(2024, 1, 16)
    prior_14 = get_prior_xnys_sessions(target_d, 14)

    # Omit session 5
    incomplete = [
        OpeningRangeVolumeObservation(symbol="TEST", session_date=sess_d, volume=5_000.0)
        for i, sess_d in enumerate(prior_14)
        if i != 5
    ]
    rv, mean_vol = compute_relative_volume(incomplete, current_or_volume=10_000.0, target_session=target_d)
    assert rv is None and mean_vol is None

    # Adding D-15 older session does NOT repair the gap
    cal = _calendar()
    older_d = cal.previous_session(prior_14[0]).date()
    incomplete.append(OpeningRangeVolumeObservation(symbol="TEST", session_date=older_d, volume=5_000.0))
    rv2, mean_vol2 = compute_relative_volume(incomplete, current_or_volume=10_000.0, target_session=target_d)
    assert rv2 is None and mean_vol2 is None


# -----------------------------------------------------------------------------
# 3. Inexpensive Screening Sequence & Gate (Scope D & E)
# -----------------------------------------------------------------------------


def test_cheap_screening_ordering_and_candidate_gate() -> None:
    """Requirement: Daily ADV/ATR screening precedes unnecessary OR-history requests; 95% gate audited."""
    target_d = date(2024, 1, 16)
    cal = _calendar()
    prior_dates = [s.date() for s in cal.sessions_window(cal.previous_session(target_d), -15)]

    # SYM_PASS: ADV=1.5M, ATR=1.00 -> passes daily base
    daily_pass = [
        DailyBar("SYM_PASS", dt, 100.0, 101.0, 99.0, 100.0, 1_500_000.0)
        for dt in prior_dates
    ]
    # SYM_LOW_VOL: ADV=200k -> fails daily base
    daily_low_vol = [
        DailyBar("SYM_LOW_VOL", dt, 100.0, 101.0, 99.0, 100.0, 200_000.0)
        for dt in prior_dates
    ]
    # SYM_LOW_ATR: ATR=0.20 -> fails daily base
    daily_low_atr = [
        DailyBar("SYM_LOW_ATR", dt, 100.0, 100.2, 99.9, 100.0, 1_500_000.0)
        for dt in prior_dates
    ]

    daily_bars_map = {
        "SYM_PASS": daily_pass,
        "SYM_LOW_VOL": daily_low_vol,
        "SYM_LOW_ATR": daily_low_atr,
    }

    # Audit broad daily
    audit_daily, _comp_daily, dq_syms = audit_broad_daily_availability(
        valid_target_symbols=["SYM_PASS", "SYM_LOW_VOL", "SYM_LOW_ATR"],
        ambiguous_symbols=[],
        daily_bars_by_symbol=daily_bars_map,
        target_session=target_d,
        lookback=14,
        adv_min=1_000_000.0,
        atr_min=0.50,
    )
    assert audit_daily.canonical_target_universe_count == 3
    assert audit_daily.daily_computable_count == 3
    assert audit_daily.daily_base_qualified_count == 1
    assert dq_syms == ["SYM_PASS"]

    # Now screen SYM_PASS: price > 5.0, RV >= 1.0
    or_pass = OpeningRange("SYM_PASS", target_d, 10.0, 11.0, 9.5, 10.5, 20_000.0, Direction.LONG, 11.0)
    prior_obs = [
        OpeningRangeVolumeObservation("SYM_PASS", dt, 10_000.0)
        for dt in prior_dates[1:]  # 14 prior sessions
    ]

    screening_audit, outcomes, _eligible, _ = audit_candidate_screening(
        daily_base_qualified_symbols=dq_syms,
        current_or_by_symbol={"SYM_PASS": or_pass},
        current_or_provider_failures=set(),
        prior_or_obs_by_symbol={"SYM_PASS": prior_obs},
        prior_or_provider_failures=set(),
        daily_bars_by_symbol=daily_bars_map,
        target_session=target_d,
        price_min=5.0,
        adv_min=1_000_000.0,
        atr_min=0.50,
        rv_min=1.0,
        gate_threshold=CANDIDATE_SCREENING_GATE_THRESHOLD,
    )
    assert screening_audit.daily_base_qualified_count == 1
    assert screening_audit.validly_determined_count == 1
    assert screening_audit.screening_completeness_pct == 100.0
    assert screening_audit.meets_screening_gate is True
    assert screening_audit.eligible_candidate_count == 1
    assert outcomes["SYM_PASS"] == CandidateScreeningOutcome.ELIGIBLE


def test_candidate_screening_resolved_no_setup_and_gate_failure() -> None:
    """Requirement: NO_OPENING_PRINT is a valid resolved outcome; provider errors count against gate."""
    target_d = date(2024, 1, 16)
    dq_syms = ["SYM1", "SYM2"]  # 2 daily-qualified symbols

    # SYM1 has NO_OPENING_PRINT (None) -> resolved outcome!
    # SYM2 suffered a provider error
    screening_audit, outcomes, _eligible, _ = audit_candidate_screening(
        daily_base_qualified_symbols=dq_syms,
        current_or_by_symbol={"SYM1": None},
        current_or_provider_failures={"SYM2"},
        prior_or_obs_by_symbol={},
        prior_or_provider_failures=set(),
        daily_bars_by_symbol={},
        target_session=target_d,
        gate_threshold=0.95,
    )
    assert outcomes["SYM1"] == CandidateScreeningOutcome.NO_OPENING_PRINT_NO_SETUP
    assert outcomes["SYM2"] == CandidateScreeningOutcome.PROVIDER_DATA_FAILURE
    assert screening_audit.validly_determined_count == 1
    assert screening_audit.provider_failure_count == 1
    # Completeness = 1 / 2 = 50.0% < 95.0% -> gate fails!
    assert screening_audit.screening_completeness_pct == 50.0
    assert screening_audit.meets_screening_gate is False


# -----------------------------------------------------------------------------
# 4. Stage-B Sparse Minute Compatibility Tests (Scope F)
# -----------------------------------------------------------------------------


def test_stage_b_sparse_pending_order_does_not_invent_fill() -> None:
    """Requirement: Verified sparse minutes do not invent order fills; pending orders remain pending."""
    d = date(2025, 6, 2)
    op = OpeningRange("PEND", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand = evaluate_candidate("PEND", d, op, adv14=2_000_000.0, atr14=2.0, mean_prior_or_volume=25_000.0, rv=2.0)
    ranked = rank_and_select_top_20([cand], {"PEND": op}, session_start_equity=25000.0)

    # Provide only 3 bars during the day, none reaching 100.0 stop level
    bars = [
        _make_bar("PEND", d, time(9, 35), 90.0, 95.0, 89.0, 92.0, 1_000.0),
        _make_bar("PEND", d, time(11, 0), 92.0, 96.0, 91.0, 93.0, 1_000.0),
        _make_bar("PEND", d, time(15, 59), 93.0, 95.0, 92.0, 94.0, 1_000.0),
    ]

    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"PEND": bars},
        session_start_equity=25000.0,
        allow_verified_sparse_bars=True,
    )
    assert result.is_valid is True
    assert result.status == "completed"
    # Order never triggered: 0 trades executed
    assert len(result.trades) == 0


def test_stage_b_sparse_open_position_does_not_invent_stop_fill() -> None:
    """Requirement: Open position during sparse minutes remains open; does not invent stop fills."""
    d = date(2025, 6, 2)
    op = OpeningRange("OPEN", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand_obj = evaluate_candidate("OPEN", d, op, adv14=2_000_000.0, atr14=2.0, mean_prior_or_volume=25_000.0, rv=2.0)
    ranked = rank_and_select_top_20([cand_obj], {"OPEN": op}, session_start_equity=25000.0)

    # 09:35 triggers entry at 100.0 (high=101.0, low=99.85 -> protective stop at 100.0 - 0.20 = 99.80)
    # Then middle minutes are sparse (omitted)
    # 15:59 EOD bar is present and liquidates at close=100.5
    bars = [
        _make_bar("OPEN", d, time(9, 35), 99.9, 101.0, 99.85, 100.5, 5_000.0),
        _make_bar("OPEN", d, time(12, 0), 100.4, 100.8, 100.2, 100.6, 2_000.0),
        _make_bar("OPEN", d, time(15, 59), 100.5, 100.7, 100.3, 100.5, 3_000.0),
    ]

    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"OPEN": bars},
        session_start_equity=25000.0,
        allow_verified_sparse_bars=True,
    )
    assert result.is_valid is True
    assert result.status == "completed"
    assert len(result.trades) == 1
    assert result.trades[0].raw_entry_price == 100.0
    assert result.trades[0].raw_exit_price == 100.5
    assert result.trades[0].exit_reason.value == "END_OF_DAY"


def test_stage_b_missing_1559_bar_fails_closed_for_open_position() -> None:
    """Requirement: Open position missing 15:59 liquidation bar fails closed as non_computable."""
    d = date(2025, 6, 2)
    op = OpeningRange("OPEN", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand_obj = evaluate_candidate("OPEN", d, op, adv14=2_000_000.0, atr14=2.0, mean_prior_or_volume=25_000.0, rv=2.0)
    ranked = rank_and_select_top_20([cand_obj], {"OPEN": op}, session_start_equity=25000.0)

    # 09:35 triggers, but NO 15:59 bar exists!
    bars = [
        _make_bar("OPEN", d, time(9, 35), 99.9, 101.0, 99.85, 100.5, 5_000.0),
        _make_bar("OPEN", d, time(12, 0), 100.4, 100.8, 100.2, 100.6, 2_000.0),
    ]

    result = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"OPEN": bars},
        session_start_equity=25000.0,
        allow_verified_sparse_bars=True,
    )
    assert result.is_valid is False
    assert result.status == "non_computable"
    assert "Missing trade-path bar for open position OPEN at 15:59" in (result.error_reason or "")


def test_stage_b_fully_populated_preserves_outputs_identically() -> None:
    """Requirement: Fully populated 385-minute path produces identical output under allow_verified_sparse_bars=False and True."""
    d = date(2025, 6, 2)
    op = OpeningRange("SYM", d, 100.0, 100.0, 98.0, 100.0, 50_000.0, Direction.LONG, 100.0)
    cand_obj = evaluate_candidate("SYM", d, op, adv14=2_000_000.0, atr14=2.0, mean_prior_or_volume=25_000.0, rv=2.0)
    ranked = rank_and_select_top_20([cand_obj], {"SYM": op}, session_start_equity=25000.0)

    # Generate full 385 minutes
    bars = []
    for h in range(9, 16):
        for m in range(60):
            if (h == 9 and m >= 35) or (10 <= h <= 15):
                t = time(h, m)
                bars.append(_make_bar("SYM", d, t, 100.0, 100.5, 99.8, 100.2, 1_000.0))

    res_legacy = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"SYM": bars},
        session_start_equity=25000.0,
        allow_verified_sparse_bars=False,
    )
    res_sparse = simulate_session_portfolio(
        session_date=d,
        ranked_candidates=ranked,
        minute_bars_by_symbol={"SYM": bars},
        session_start_equity=25000.0,
        allow_verified_sparse_bars=True,
    )

    assert res_legacy.is_valid == res_sparse.is_valid
    assert res_legacy.session_net_pnl_a == res_sparse.session_net_pnl_a
    assert len(res_legacy.trades) == len(res_sparse.trades)


# -----------------------------------------------------------------------------
# 5. Governance & Invariants
# -----------------------------------------------------------------------------


def test_production_strategy_registry_strictly_empty() -> None:
    """Requirement: APPROVED_PRODUCTION_STRATEGIES is strictly empty."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()


def test_all_four_upstream_spec_hashes(tmp_path: pytest.TempPathFactory) -> None:
    """Requirement: All four prior specifications (003B, 003C, 003D, CORR-001) match locked SHA-256."""
    from pathlib import Path
    repo_root = Path(".")
    ok, actual_hashes, errors = verify_upstream_spec_hashes(repo_root)
    assert ok is True, f"Spec hash mismatches: {errors}"
    assert len(actual_hashes) == 4


def test_corr_002_spec_hash() -> None:
    """Requirement: DAYTRADE-003D-CORR-002 specification matches locked SHA-256."""
    import hashlib
    from pathlib import Path
    p = Path(CORR_002_SPEC_PATH)
    assert p.exists(), f"Spec missing: {CORR_002_SPEC_PATH}"
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    assert actual == LOCKED_003D_CORR_002_SPEC_SHA256


def test_end_to_end_synthetic_acquisition_and_screening_fixture() -> None:
    """Representative synthetic end-to-end fixture exercising all CORR-002 phases with zero network calls."""
    target_d = date(2024, 1, 2)
    cal = _calendar()
    prev = cal.previous_session(target_d)
    prior_daily_dates = [s.date() for s in cal.sessions_window(prev, -15)]
    prior_14_dates = [s.date() for s in cal.sessions_window(prev, -14)]

    # 1. Target Universe: 8 canonical symbols
    # - SYM_DUAL_PASS_LONG: ADV=2M, ATR=1.50, Open=100, High=105, Low=99, Close=104 (LONG), RV=2.5 -> ELIGIBLE
    # - SYM_DUAL_PASS_SHORT: ADV=3M, ATR=2.00, Open=50, High=51, Low=45, Close=46 (SHORT), RV=1.8 -> ELIGIBLE
    # - SYM_LOW_ADV: ADV=500k, ATR=1.00 -> filtered at daily step
    # - SYM_LOW_ATR: ADV=2M, ATR=0.30 -> filtered at daily step
    # - SYM_NO_PRINT: ADV=2M, ATR=1.00, 0 bars in 09:30-09:34 -> NO_OPENING_PRINT_NO_SETUP
    # - SYM_CHEAP_PRICE: ADV=2M, ATR=1.00, Open=4.50 -> PRICE_REJECTED
    # - SYM_ZERO_RV: ADV=2M, ATR=1.00, Open=20.0, 14 prior OR sessions 0 volume -> UNRANKABLE_ZERO_RV_BASELINE
    # - SYM_LOW_RV: ADV=2M, ATR=1.00, Open=25.0, RV=0.50 -> RV_REJECTED

    canonical_syms = [
        "SYM_DUAL_PASS_LONG",
        "SYM_DUAL_PASS_SHORT",
        "SYM_LOW_ADV",
        "SYM_LOW_ATR",
        "SYM_NO_PRINT",
        "SYM_CHEAP_PRICE",
        "SYM_ZERO_RV",
        "SYM_LOW_RV",
    ]

    daily_bars_map: dict[str, list[DailyBar]] = {}
    for sym in canonical_syms:
        adv = 500_000.0 if sym == "SYM_LOW_ADV" else 2_000_000.0
        atr_tr = 0.15 if sym == "SYM_LOW_ATR" else 1.50
        bars = [
            DailyBar(sym, dt, 100.0, 100.0 + atr_tr, 100.0 - atr_tr, 100.0, adv)
            for dt in prior_daily_dates
        ]
        daily_bars_map[sym] = bars

    # Step 2: Broad daily audit
    daily_audit, _, dq_syms = audit_broad_daily_availability(
        valid_target_symbols=canonical_syms,
        ambiguous_symbols=[],
        daily_bars_by_symbol=daily_bars_map,
        target_session=target_d,
        lookback=14,
        adv_min=1_000_000.0,
        atr_min=0.50,
    )
    assert daily_audit.canonical_target_universe_count == 8
    assert daily_audit.daily_computable_count == 8
    # 6 pass daily thresholds (SYM_LOW_ADV and SYM_LOW_ATR filtered out)
    assert daily_audit.daily_base_qualified_count == 6
    assert set(dq_syms) == {
        "SYM_DUAL_PASS_LONG",
        "SYM_DUAL_PASS_SHORT",
        "SYM_NO_PRINT",
        "SYM_CHEAP_PRICE",
        "SYM_ZERO_RV",
        "SYM_LOW_RV",
    }

    # Step 3: Current opening ranges (sparse aggregation)
    current_or_map: dict[str, OpeningRange | None] = {}
    # SYM_NO_PRINT: 0 bars -> None
    current_or_map["SYM_NO_PRINT"] = None

    # SYM_CHEAP_PRICE: Open=4.50
    current_or_map["SYM_CHEAP_PRICE"] = OpeningRange("SYM_CHEAP_PRICE", target_d, 4.50, 4.80, 4.40, 4.70, 50_000.0, Direction.LONG, 4.80)

    # SYM_ZERO_RV: Open=20.0
    current_or_map["SYM_ZERO_RV"] = OpeningRange("SYM_ZERO_RV", target_d, 20.0, 21.0, 19.5, 20.5, 10_000.0, Direction.LONG, 21.0)

    # SYM_LOW_RV: Open=25.0
    current_or_map["SYM_LOW_RV"] = OpeningRange("SYM_LOW_RV", target_d, 25.0, 26.0, 24.5, 25.5, 5_000.0, Direction.LONG, 26.0)

    # SYM_DUAL_PASS_LONG: Open=100.0, High=105.0, Low=99.0, Close=104.0 (LONG)
    current_or_map["SYM_DUAL_PASS_LONG"] = OpeningRange("SYM_DUAL_PASS_LONG", target_d, 100.0, 105.0, 99.0, 104.0, 50_000.0, Direction.LONG, 105.0)

    # SYM_DUAL_PASS_SHORT: Open=50.0, High=51.0, Low=45.0, Close=46.0 (SHORT)
    current_or_map["SYM_DUAL_PASS_SHORT"] = OpeningRange("SYM_DUAL_PASS_SHORT", target_d, 50.0, 51.0, 45.0, 46.0, 90_000.0, Direction.SHORT, 45.0)

    # Step 4: Prior OR observations
    prior_obs_map: dict[str, list[OpeningRangeVolumeObservation]] = {}
    # SYM_ZERO_RV: all 14 sessions have 0 volume
    prior_obs_map["SYM_ZERO_RV"] = [
        OpeningRangeVolumeObservation("SYM_ZERO_RV", dt, 0.0) for dt in prior_14_dates
    ]
    # SYM_LOW_RV: prior mean = 10,000, current = 5,000 -> RV = 0.50
    prior_obs_map["SYM_LOW_RV"] = [
        OpeningRangeVolumeObservation("SYM_LOW_RV", dt, 10_000.0) for dt in prior_14_dates
    ]
    # SYM_DUAL_PASS_LONG: prior mean = 20,000, current = 50,000 -> RV = 2.50
    prior_obs_map["SYM_DUAL_PASS_LONG"] = [
        OpeningRangeVolumeObservation("SYM_DUAL_PASS_LONG", dt, 20_000.0) for dt in prior_14_dates
    ]
    # SYM_DUAL_PASS_SHORT: prior mean = 50,000, current = 90,000 -> RV = 1.80
    prior_obs_map["SYM_DUAL_PASS_SHORT"] = [
        OpeningRangeVolumeObservation("SYM_DUAL_PASS_SHORT", dt, 50_000.0) for dt in prior_14_dates
    ]

    # Audit candidate screening
    screening_audit, outcomes, eligible, surviving_or = audit_candidate_screening(
        daily_base_qualified_symbols=dq_syms,
        current_or_by_symbol=current_or_map,
        current_or_provider_failures=set(),
        prior_or_obs_by_symbol=prior_obs_map,
        prior_or_provider_failures=set(),
        daily_bars_by_symbol=daily_bars_map,
        target_session=target_d,
        price_min=5.0,
        adv_min=1_000_000.0,
        atr_min=0.50,
        rv_min=1.0,
        gate_threshold=0.95,
    )

    assert screening_audit.daily_base_qualified_count == 6
    assert screening_audit.validly_determined_count == 6
    assert screening_audit.screening_completeness_pct == 100.0
    assert screening_audit.meets_screening_gate is True
    assert screening_audit.no_opening_print_count == 1
    assert screening_audit.zero_rv_baseline_count == 1
    assert screening_audit.provider_failure_count == 0
    assert screening_audit.eligible_candidate_count == 2
    assert outcomes["SYM_NO_PRINT"] == CandidateScreeningOutcome.NO_OPENING_PRINT_NO_SETUP
    assert outcomes["SYM_CHEAP_PRICE"] == CandidateScreeningOutcome.PRICE_REJECTED
    assert outcomes["SYM_ZERO_RV"] == CandidateScreeningOutcome.UNRANKABLE_ZERO_RV_BASELINE
    assert outcomes["SYM_LOW_RV"] == CandidateScreeningOutcome.RV_REJECTED
    assert outcomes["SYM_DUAL_PASS_LONG"] == CandidateScreeningOutcome.ELIGIBLE
    assert outcomes["SYM_DUAL_PASS_SHORT"] == CandidateScreeningOutcome.ELIGIBLE

    # Step 5: Rank and select Top 20
    ranked = rank_and_select_top_20(
        candidates=eligible,
        opening_ranges=surviving_or,
        session_start_equity=25000.0,
        top_n=20,
    )
    evidence, records, _selected_syms = freeze_top_20_selection(ranked)
    assert evidence.selected_count == 2
    # RV=2.50 first, RV=1.80 second
    assert records[0]["symbol"] == "SYM_DUAL_PASS_LONG"
    assert records[0]["relative_volume"] == 2.50
    assert records[0]["direction"] == "LONG"
    assert records[1]["symbol"] == "SYM_DUAL_PASS_SHORT"
    assert records[1]["relative_volume"] == 1.80
    assert records[1]["direction"] == "SHORT"
    assert len(evidence.selection_sha256) == 64

    # Step 6: Stage-B price path audit
    b_long_bars = [
        _make_bar("SYM_DUAL_PASS_LONG", target_d, time(9, 35), 104.0, 106.0, 103.5, 105.5, 5_000.0),
        _make_bar("SYM_DUAL_PASS_LONG", target_d, time(15, 59), 105.0, 107.0, 104.8, 106.2, 8_000.0),
    ]
    b_short_bars = [
        _make_bar("SYM_DUAL_PASS_SHORT", target_d, time(9, 35), 46.0, 47.0, 44.5, 45.0, 10_000.0),
        _make_bar("SYM_DUAL_PASS_SHORT", target_d, time(15, 59), 45.0, 45.5, 44.0, 44.5, 12_000.0),
    ]
    stage_b_map = {
        "SYM_DUAL_PASS_LONG": b_long_bars,
        "SYM_DUAL_PASS_SHORT": b_short_bars,
    }

    stage_b_audit = audit_stage_b_price_path(
        active_selected_symbols=["SYM_DUAL_PASS_LONG", "SYM_DUAL_PASS_SHORT"],
        stage_b_bars_by_symbol=stage_b_map,
        stage_b_provider_failures=set(),
        expected_minutes=385,
    )
    assert stage_b_audit.selected_actionable_symbols_count == 2
    assert stage_b_audit.total_expected_minutes == 770
    assert stage_b_audit.total_actual_bars == 4
    assert stage_b_audit.total_sparse_minutes == 766
    assert stage_b_audit.missing_eod_bar_symbols_count == 0
    assert stage_b_audit.is_usable is True

    # Step 7: Final disposition
    disp, blockers = determine_pilot_disposition(
        reference_success=True,
        provider_access_success=True,
        provider_data_integrity_success=True,
        candidate_screening_gate_passed=screening_audit.meets_screening_gate,
        eligible_candidate_count=len(eligible),
        stage_b_path_usable=stage_b_audit.is_usable,
    )
    assert disp.value == "FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD"
    assert blockers == []

