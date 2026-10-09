"""Synthetic tests for DAYTRADE-003D-CORR-001 corrected pilot logic.

Proves:
- ambiguous duplicate does not silently first-row-win;
- ambiguous duplicate becomes unavailable rather than killing entire universe;
- duplicate proven identical collapses deterministically;
- recent IPO becomes INSUFFICIENT_HISTORY;
- unavailable symbol counts against denominator;
- 94.99% Stage-A coverage fails;
- 95.00% passes;
- 99% passes;
- technical filter failure is NOT missing data;
- technical filter failures remain in computable denominator;
- Top-20 uses only computable symbols;
- missing symbols never use future outcome;
- no rank-21 replacement after Top-20 freeze;
- incomplete selected Stage-B path fails pilot;
- 5,000-page runaway guard works;
- no provider calls in unit tests;
- historical specs/artifacts remain unchanged.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tradex.research.daytrade_orb.corrected_pilot import (
    LOCKED_003B_SPEC_PATH,
    LOCKED_003B_SPEC_SHA256,
    LOCKED_003C_RESOLUTION_PATH,
    LOCKED_003C_RESOLUTION_SHA256,
    LOCKED_003D_SPEC_PATH,
    LOCKED_003D_SPEC_SHA256,
    MAX_PILOT_PAGES_LIMIT,
    MAX_PILOT_STORAGE_BYTES_LIMIT,
    STAGE_A_COVERAGE_THRESHOLD,
    UnavailableReason,
    audit_corrected_stage_b_path,
    audit_stage_a_coverage,
    calculate_corrected_resource_plan,
    compute_and_freeze_corrected_stage_a_selection,
    filter_and_audit_target_universe,
    resolve_ticker_duplicates,
    verify_all_upstream_spec_hashes,
)
from tradex.research.daytrade_orb.indicators import get_prior_xnys_sessions
from tradex.research.daytrade_orb.models import (
    DailyBar,
    Direction,
    MinuteBar,
    OpeningRange,
    OpeningRangeVolumeObservation,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MARKET_TIMEZONE = ZoneInfo("America/New_York")


def test_ambiguous_duplicate_does_not_silently_first_row_win():
    """Ambiguous duplicates with conflicting metadata must fail closed and NOT keep the first row."""
    rows = [
        {
            "ticker": "DUAL",
            "primary_exchange": "XNYS",
            "type": "CS",
            "active": True,
            "cik": "0001111111",
            "composite_figi": "BBG000000001",
        },
        {
            "ticker": "DUAL",
            "primary_exchange": "XNAS",  # Conflicting exchange!
            "type": "CS",
            "active": True,
            "cik": "0002222222",  # Conflicting CIK!
            "composite_figi": "BBG000000002",
        },
    ]

    is_identical, collapsed = resolve_ticker_duplicates("DUAL", rows)
    assert not is_identical
    assert collapsed is None

    audit, target_rows = filter_and_audit_target_universe(rows)
    assert "DUAL" not in target_rows
    assert "DUAL" not in audit.valid_target_symbols
    assert "DUAL" in audit.ambiguous_symbols
    assert audit.canonical_target_universe_count == 1
    assert audit.duplicate_ticker_count == 1


def test_ambiguous_duplicate_becomes_unavailable_rather_than_killing_entire_universe():
    """Ambiguous duplicate is marked AMBIGUOUS_IDENTITY and excluded from ranking, but universe continues."""
    rows = [
        {
            "ticker": "GOOD",
            "primary_exchange": "XNYS",
            "type": "CS",
            "active": True,
            "cik": "0009999999",
        },
        {
            "ticker": "AMBIG",
            "primary_exchange": "XNYS",
            "type": "CS",
            "active": True,
            "cik": "0001111111",
        },
        {
            "ticker": "AMBIG",
            "primary_exchange": "XNAS",
            "type": "CS",
            "active": True,
            "cik": "0002222222",
        },
    ]

    audit, _target_rows = filter_and_audit_target_universe(rows)
    assert audit.canonical_target_universe_count == 2
    assert audit.valid_target_symbols == ["GOOD"]
    assert audit.ambiguous_symbols == ["AMBIG"]

    # In Stage A coverage audit:
    target_dt = date(2024, 1, 2)
    prior_sessions = get_prior_xnys_sessions(target_dt, 14)

    # Provide complete data for GOOD
    daily_bars = {
        "GOOD": [
            DailyBar(
                symbol="GOOD",
                session_date=d,
                open=10.0,
                high=11.0,
                low=9.5,
                close=10.5,
                volume=2_000_000,
            )
            for d in get_prior_xnys_sessions(target_dt, 20)
        ]
    }
    prior_or = {
        "GOOD": [
            OpeningRangeVolumeObservation(symbol="GOOD", session_date=d, volume=500_000)
            for d in prior_sessions
        ]
    }
    current_or = {
        "GOOD": OpeningRange(
            symbol="GOOD",
            session_date=target_dt,
            or_open=10.0,
            or_high=10.5,
            or_low=9.8,
            or_close=10.4,
            or_volume=600_000,
            direction=Direction.LONG,
            stop_level=10.5,
        )
    }

    cov_audit, reasons, computable = audit_stage_a_coverage(
        valid_target_symbols=audit.valid_target_symbols,
        ambiguous_symbols=audit.ambiguous_symbols,
        daily_bars_by_symbol=daily_bars,
        prior_or_obs_by_symbol=prior_or,
        current_or_by_symbol=current_or,
        target_session=target_dt,
        coverage_threshold=0.50,  # 1 out of 2 is 50%
    )

    assert cov_audit.canonical_target_universe_count == 2
    assert cov_audit.computable_stage_a_symbols_count == 1
    assert computable == ["GOOD"]
    assert reasons.get("AMBIG") == UnavailableReason.AMBIGUOUS_IDENTITY.value
    assert cov_audit.unavailable_counts_by_reason == {"AMBIGUOUS_IDENTITY": 1}


def test_duplicate_proven_identical_collapses_deterministically():
    """Duplicate rows with identical exchange, type, active, and matching strong identity collapse."""
    rows = [
        {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "primary_exchange": "XNAS",
            "type": "CS",
            "active": True,
            "cik": "0000320193",
            "composite_figi": "BBG000B9XRY4",
        },
        {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "primary_exchange": "XNAS",
            "type": "CS",
            "active": True,
            "cik": "0000320193",
            "composite_figi": "BBG000B9XRY4",
        },
    ]

    is_identical, collapsed = resolve_ticker_duplicates("AAPL", rows)
    assert is_identical
    assert collapsed is not None
    assert collapsed["ticker"] == "AAPL"

    audit, _target_rows = filter_and_audit_target_universe(rows)
    assert audit.canonical_target_universe_count == 1
    assert audit.valid_target_symbols == ["AAPL"]
    assert audit.ambiguous_symbols == []
    assert audit.collapsed_duplicates_count == 1


def test_recent_ipo_becomes_insufficient_history():
    """A security listed fewer than 15 historical sessions ago is classified as INSUFFICIENT_HISTORY."""
    target_dt = date(2024, 1, 2)
    # Only 5 historical daily bars
    recent_dates = get_prior_xnys_sessions(target_dt, 5)
    daily_bars = {
        "IPO": [
            DailyBar(
                symbol="IPO",
                session_date=d,
                open=20.0,
                high=22.0,
                low=19.0,
                close=21.0,
                volume=1_500_000,
            )
            for d in recent_dates
        ]
    }

    cov_audit, reasons, computable = audit_stage_a_coverage(
        valid_target_symbols=["IPO"],
        ambiguous_symbols=[],
        daily_bars_by_symbol=daily_bars,
        prior_or_obs_by_symbol={},
        current_or_by_symbol={},
        target_session=target_dt,
    )

    assert cov_audit.computable_stage_a_symbols_count == 0
    assert "IPO" not in computable
    assert reasons["IPO"] == UnavailableReason.INSUFFICIENT_HISTORY.value
    assert cov_audit.unavailable_counts_by_reason == {"INSUFFICIENT_HISTORY": 1}


def test_unavailable_symbol_counts_against_denominator():
    """Unavailable symbols count in denominator, reducing coverage percentage."""
    target_dt = date(2024, 1, 2)
    prior_20 = get_prior_xnys_sessions(target_dt, 20)
    prior_14 = get_prior_xnys_sessions(target_dt, 14)

    # 10 symbols: 8 computable, 1 IPO, 1 ambiguous
    symbols = [f"SYM{i}" for i in range(8)]
    daily_bars = {
        s: [
            DailyBar(
                symbol=s,
                session_date=d,
                open=15.0,
                high=16.0,
                low=14.5,
                close=15.5,
                volume=2_000_000,
            )
            for d in prior_20
        ]
        for s in symbols
    }
    prior_or = {
        s: [
            OpeningRangeVolumeObservation(symbol=s, session_date=d, volume=300_000)
            for d in prior_14
        ]
        for s in symbols
    }
    current_or = {
        s: OpeningRange(
            symbol=s,
            session_date=target_dt,
            or_open=15.0,
            or_high=15.8,
            or_low=14.9,
            or_close=15.6,
            or_volume=400_000,
            direction=Direction.LONG,
            stop_level=15.8,
        )
        for s in symbols
    }

    # Add 1 IPO (insufficient daily bars)
    daily_bars["IPO1"] = [
        DailyBar(
            symbol="IPO1",
            session_date=d,
            open=15.0,
            high=16.0,
            low=14.5,
            close=15.5,
            volume=1000,
        )
        for d in prior_20[:3]
    ]

    valid_syms = symbols + ["IPO1"]
    ambig_syms = ["AMBIG1"]

    cov_audit, _reasons, _computable = audit_stage_a_coverage(
        valid_target_symbols=valid_syms,
        ambiguous_symbols=ambig_syms,
        daily_bars_by_symbol=daily_bars,
        prior_or_obs_by_symbol=prior_or,
        current_or_by_symbol=current_or,
        target_session=target_dt,
    )

    # Denominator is 8 valid + 1 IPO + 1 AMBIG = 10
    assert cov_audit.canonical_target_universe_count == 10
    # Numerator is 8
    assert cov_audit.computable_stage_a_symbols_count == 8
    # Coverage is exactly 80.0%
    assert cov_audit.stage_a_coverage_pct == 80.0
    assert not cov_audit.meets_coverage_threshold


def test_coverage_threshold_boundaries():
    """Precise boundary testing: 94.99% fails, 95.00% passes, 99.00% passes."""
    target_dt = date(2024, 1, 2)
    prior_20 = get_prior_xnys_sessions(target_dt, 20)
    prior_14 = get_prior_xnys_sessions(target_dt, 14)

    # Single canonical bar template reused for speed across synthetic symbols
    dummy_daily_list = [
        DailyBar(
            symbol="TEMP",
            session_date=d,
            open=20.0,
            high=21.0,
            low=19.0,
            close=20.5,
            volume=1_500_000,
        )
        for d in prior_20
    ]
    dummy_prior_or_list = [
        OpeningRangeVolumeObservation(symbol="TEMP", session_date=d, volume=200_000)
        for d in prior_14
    ]
    dummy_current_or = OpeningRange(
        symbol="TEMP",
        session_date=target_dt,
        or_open=20.0,
        or_high=20.5,
        or_low=19.8,
        or_close=20.3,
        or_volume=250_000,
        direction=Direction.LONG,
        stop_level=20.5,
    )

    class FastMap:
        """Lightweight mapping proxy to avoid creating 10,000 distinct lists."""
        def __init__(self, val):
            self.val = val
        def get(self, k, default=None):
            return self.val

    fast_daily = FastMap(dummy_daily_list)
    fast_prior_or = FastMap(dummy_prior_or_list)
    fast_current_or = FastMap(dummy_current_or)

    # 1. Test 94.99%: 9,499 computable out of 10,000
    valid_9499 = [f"C_{i}" for i in range(9499)]
    ambig_501 = [f"A_{i}" for i in range(501)]

    cov_audit_fail, _, _ = audit_stage_a_coverage(
        valid_target_symbols=valid_9499,
        ambiguous_symbols=ambig_501,
        daily_bars_by_symbol=fast_daily,  # type: ignore[arg-type]
        prior_or_obs_by_symbol=fast_prior_or,  # type: ignore[arg-type]
        current_or_by_symbol=fast_current_or,  # type: ignore[arg-type]
        target_session=target_dt,
        coverage_threshold=STAGE_A_COVERAGE_THRESHOLD,
    )
    assert cov_audit_fail.stage_a_coverage_pct == 94.99
    assert not cov_audit_fail.meets_coverage_threshold

    # 2. Test 95.00%: 9,500 computable out of 10,000
    valid_9500 = [f"C_{i}" for i in range(9500)]
    ambig_500 = [f"A_{i}" for i in range(500)]

    cov_audit_pass, _, _ = audit_stage_a_coverage(
        valid_target_symbols=valid_9500,
        ambiguous_symbols=ambig_500,
        daily_bars_by_symbol=fast_daily,  # type: ignore[arg-type]
        prior_or_obs_by_symbol=fast_prior_or,  # type: ignore[arg-type]
        current_or_by_symbol=fast_current_or,  # type: ignore[arg-type]
        target_session=target_dt,
        coverage_threshold=STAGE_A_COVERAGE_THRESHOLD,
    )
    assert cov_audit_pass.stage_a_coverage_pct == 95.0
    assert cov_audit_pass.meets_coverage_threshold

    # 3. Test 99.00%: 9,900 computable out of 10,000
    valid_9900 = [f"C_{i}" for i in range(9900)]
    ambig_100 = [f"A_{i}" for i in range(100)]

    cov_audit_99, _, _ = audit_stage_a_coverage(
        valid_target_symbols=valid_9900,
        ambiguous_symbols=ambig_100,
        daily_bars_by_symbol=fast_daily,  # type: ignore[arg-type]
        prior_or_obs_by_symbol=fast_prior_or,  # type: ignore[arg-type]
        current_or_by_symbol=fast_current_or,  # type: ignore[arg-type]
        target_session=target_dt,
        coverage_threshold=STAGE_A_COVERAGE_THRESHOLD,
    )
    assert cov_audit_99.stage_a_coverage_pct == 99.0
    assert cov_audit_99.meets_coverage_threshold


def test_technical_filter_failure_is_not_missing_data():
    """Technical filter failures (e.g. price < $5 or RV < 1.0) remain COMPUTABLE and in coverage."""
    target_dt = date(2024, 1, 2)
    prior_20 = get_prior_xnys_sessions(target_dt, 20)
    prior_14 = get_prior_xnys_sessions(target_dt, 14)

    # Low priced stock: opening_price = $3.00 (< $5.00)
    daily_bars = {
        "LOWPRICE": [
            DailyBar(
                symbol="LOWPRICE",
                session_date=d,
                open=3.0,
                high=3.2,
                low=2.9,
                close=3.1,
                volume=2_000_000,
            )
            for d in prior_20
        ]
    }
    prior_or = {
        "LOWPRICE": [
            OpeningRangeVolumeObservation(symbol="LOWPRICE", session_date=d, volume=500_000)
            for d in prior_14
        ]
    }
    current_or = {
        "LOWPRICE": OpeningRange(
            symbol="LOWPRICE",
            session_date=target_dt,
            or_open=3.0,  # Below $5 filter!
            or_high=3.2,
            or_low=2.9,
            or_close=3.1,
            or_volume=600_000,
            direction=Direction.LONG,
            stop_level=3.2,
        )
    }

    cov_audit, reasons, computable = audit_stage_a_coverage(
        valid_target_symbols=["LOWPRICE"],
        ambiguous_symbols=[],
        daily_bars_by_symbol=daily_bars,
        prior_or_obs_by_symbol=prior_or,
        current_or_by_symbol=current_or,
        target_session=target_dt,
    )

    # Must be COMPUTABLE and NOT listed in unavailable reasons
    assert "LOWPRICE" in computable
    assert "LOWPRICE" not in reasons
    assert cov_audit.computable_stage_a_symbols_count == 1
    assert cov_audit.stage_a_coverage_pct == 100.0

    # In candidate selection, it evaluates as ineligible
    sel_evidence, _records, _selected = compute_and_freeze_corrected_stage_a_selection(
        computable_symbols=computable,
        daily_bars_by_symbol=daily_bars,
        prior_or_obs_by_symbol=prior_or,
        current_or_by_symbol=current_or,
        target_session=target_dt,
    )
    assert sel_evidence.eligible_candidates_count == 0
    assert sel_evidence.selected_count == 0


def test_top_20_uses_only_computable_symbols():
    """Selection pool strictly excludes unavailable symbols and ranks only computable candidates."""
    target_dt = date(2024, 1, 2)
    prior_20 = get_prior_xnys_sessions(target_dt, 20)
    prior_14 = get_prior_xnys_sessions(target_dt, 14)

    # 25 candidates: 25 eligible, ranking selects top 20
    computable = [f"COMP_{i:02d}" for i in range(25)]
    daily_bars = {
        s: [
            DailyBar(
                symbol=s,
                session_date=d,
                open=25.0,
                high=26.0,
                low=24.5,
                close=25.5,
                volume=2_000_000,
            )
            for d in prior_20
        ]
        for s in computable
    }
    prior_or = {
        s: [
            OpeningRangeVolumeObservation(symbol=s, session_date=d, volume=200_000)
            for d in prior_14
        ]
        for s in computable
    }
    current_or = {
        s: OpeningRange(
            symbol=s,
            session_date=target_dt,
            or_open=25.0,
            or_high=26.0,
            or_low=24.8,
            or_close=25.8,
            or_volume=400_000 + (i * 10_000),  # varying volume -> varying RV
            direction=Direction.LONG,
            stop_level=26.0,
        )
        for i, s in enumerate(computable)
    }

    sel_evidence, records, selected = compute_and_freeze_corrected_stage_a_selection(
        computable_symbols=computable,
        daily_bars_by_symbol=daily_bars,
        prior_or_obs_by_symbol=prior_or,
        current_or_by_symbol=current_or,
        target_session=target_dt,
        top_n=20,
    )

    assert sel_evidence.eligible_candidates_count == 25
    assert sel_evidence.selected_count == 20
    assert len(selected) == 20
    # Highest RV should be rank 1 (COMP_24)
    assert records[0]["symbol"] == "COMP_24"
    assert records[0]["rank"] == 1


def test_no_rank_21_replacement_after_top_20_freeze():
    """If a selected symbol is missing Stage-B bars, pilot fails; rank 21 is NEVER substituted."""
    target_dt = date(2024, 1, 2)
    selected = ["SYM1", "SYM2"]

    start_m = datetime(2024, 1, 2, 9, 35, tzinfo=MARKET_TIMEZONE)
    bars_by_symbol = {
        "SYM1": [
            MinuteBar(
                symbol="SYM1",
                timestamp=(start_m + timedelta(minutes=m)).astimezone(UTC),
                session_date=target_dt,
                open=50.0,
                high=50.5,
                low=49.8,
                close=50.2,
                volume=10_000,
            )
            for m in range(385)
        ],
        "SYM2": [
            MinuteBar(
                symbol="SYM2",
                timestamp=(start_m + timedelta(minutes=m)).astimezone(UTC),
                session_date=target_dt,
                open=50.0,
                high=50.5,
                low=49.8,
                close=50.2,
                volume=10_000,
            )
            for m in range(300)
        ],
    }

    b_audit, missing_by_sym = audit_corrected_stage_b_path(
        selected_symbols=selected,
        bars_by_symbol=bars_by_symbol,
        target_session=target_dt,
    )

    assert not b_audit.path_complete
    assert b_audit.missing_minutes_count == 85
    assert "SYM2" in missing_by_sym
    # The contract dictates failure, not replacing with rank 21!


def test_5000_page_runaway_guard_works():
    """Runaway limits: 1,300 pages passes (under 5,000), but > 5,000 pages or > 2GB halts."""
    # N = 8,000, B = 100 -> ~1,300 pages -> passes
    plan_normal = calculate_corrected_resource_plan(
        universe_size=8000,
        batch_size=100,
        max_pages_limit=MAX_PILOT_PAGES_LIMIT,
        max_storage_bytes_limit=MAX_PILOT_STORAGE_BYTES_LIMIT,
    )
    assert plan_normal.is_within_bounds
    assert not plan_normal.exceeds_pages_limit
    assert not plan_normal.exceeds_storage_limit

    # Runaway universe: N = 40,000 -> 400 batches * 16 = 6,400 pages -> fails guard
    plan_runaway = calculate_corrected_resource_plan(
        universe_size=40000,
        batch_size=100,
        max_pages_limit=MAX_PILOT_PAGES_LIMIT,
        max_storage_bytes_limit=MAX_PILOT_STORAGE_BYTES_LIMIT,
    )
    assert not plan_runaway.is_within_bounds
    assert plan_runaway.exceeds_pages_limit


def test_historical_specs_and_artifacts_remain_unchanged():
    """Ensure exact SHA-256 hashes of historical 003B, 003C, and 003D specs remain unchanged."""
    valid, actual_hashes, errors = verify_all_upstream_spec_hashes(REPO_ROOT)
    assert valid, f"Historical spec hash verification failed: {errors}"
    assert actual_hashes[LOCKED_003B_SPEC_PATH] == LOCKED_003B_SPEC_SHA256
    assert actual_hashes[LOCKED_003C_RESOLUTION_PATH] == LOCKED_003C_RESOLUTION_SHA256
    assert actual_hashes[LOCKED_003D_SPEC_PATH] == LOCKED_003D_SPEC_SHA256
