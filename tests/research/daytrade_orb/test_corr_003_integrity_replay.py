"""Synthetic verification tests for DAYTRADE-003D-CORR-003.

Enforces:
1. Provider payload integrity checks (HTTP status, pagination, malformed timestamps,
   unexpected symbols, duplicate timestamps, out-of-session bars, invalid OHLCV).
2. Failed/malformed provider payloads are never counted as completed no-print observations.
3. Stage-B cannot report usable data when required integrity or 15:59 liquidation condition fails.
4. Preserves legitimate sparse-bar behavior when 15:59 liquidation bar is present.
5. Deterministic offline replay from private raw fixture reproduces screening, candidate selection,
   and Stage-B classification with zero network calls and zero credentials.
6. Missing, incomplete, or tampered replay artifacts fail closed.
7. Immutable historical specifications verified (003B, 003C, 003D, CORR-001, CORR-002, CORR-003).
8. Production strategy registry remains strictly empty.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tradex.research.daytrade_orb.corr_003_pilot import (
    CORR_002_SPEC_PATH,
    CORR_003_SPEC_PATH,
    LOCKED_003B_SPEC_PATH,
    LOCKED_003B_SPEC_SHA256,
    LOCKED_003C_RESOLUTION_PATH,
    LOCKED_003C_RESOLUTION_SHA256,
    LOCKED_003D_CORR_001_SPEC_PATH,
    LOCKED_003D_CORR_001_SPEC_SHA256,
    LOCKED_003D_CORR_002_SPEC_SHA256,
    LOCKED_003D_CORR_003_SPEC_SHA256,
    LOCKED_003D_SPEC_PATH,
    LOCKED_003D_SPEC_SHA256,
    CandidateScreeningOutcome,
    PayloadIntegrityStatus,
    PilotDisposition,
    ReplayIntegrityError,
    audit_candidate_screening,
    audit_stage_b_price_path_corr_003,
    create_and_save_manifest,
    hash_bytes,
    persist_raw_stage_artifact,
    replay_corr_003_pilot,
    validate_provider_batch_response,
    verify_upstream_spec_hashes,
)
from tradex.research.daytrade_orb.indicators import get_prior_xnys_sessions
from tradex.research.daytrade_orb.models import DailyBar, MinuteBar
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

NY_TZ = ZoneInfo("America/New_York")
REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_bar(
    symbol: str,
    session_date: date,
    minute_time: time,
    open_: float = 10.0,
    high: float = 10.5,
    low: float = 9.8,
    close: float = 10.2,
    volume: float = 1_000.0,
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


# =============================================================================
# 1. Governance, Spec Hashes & Production Registry Invariants
# =============================================================================


def test_production_strategy_registry_is_empty() -> None:
    """Production strategy registry must be strictly empty."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()


def test_upstream_spec_hashes_verify_cleanly() -> None:
    """All 6 upstream specifications must match immutable registered hashes."""
    ok, hashes, errors = verify_upstream_spec_hashes(REPO_ROOT, include_corr_003=True)
    assert ok, f"Specification verification failed: {errors}"
    assert hashes[LOCKED_003B_SPEC_PATH] == LOCKED_003B_SPEC_SHA256
    assert hashes[LOCKED_003C_RESOLUTION_PATH] == LOCKED_003C_RESOLUTION_SHA256
    assert hashes[LOCKED_003D_SPEC_PATH] == LOCKED_003D_SPEC_SHA256
    assert hashes[LOCKED_003D_CORR_001_SPEC_PATH] == LOCKED_003D_CORR_001_SPEC_SHA256
    assert hashes[CORR_002_SPEC_PATH] == LOCKED_003D_CORR_002_SPEC_SHA256
    assert hashes[CORR_003_SPEC_PATH] == LOCKED_003D_CORR_003_SPEC_SHA256


# =============================================================================
# 2. Provider Payload Integrity Verification Tests
# =============================================================================


def test_validate_provider_batch_success() -> None:
    """Clean provider response passes batch integrity validation."""
    meta = {
        "http_status": 200,
        "pagination_complete": True,
        "next_page_token_present": False,
        "repeated_page_token": False,
        "pagination_cycle_detected": False,
        "response_symbols": ["AAPL", "MSFT"],
        "malformed_timestamp_counts": {"AAPL": 0, "MSFT": 0},
    }
    bars = {
        "AAPL": [
            {"t": "2024-01-02T14:30:00Z", "o": 180.0, "h": 181.0, "l": 179.5, "c": 180.5, "v": 1000.0},
            {"t": "2024-01-02T14:31:00Z", "o": 180.5, "h": 182.0, "l": 180.0, "c": 181.5, "v": 2000.0},
        ],
        "MSFT": [
            {"t": "2024-01-02T14:30:00Z", "o": 370.0, "h": 372.0, "l": 369.0, "c": 371.0, "v": 1500.0},
        ],
    }
    res = validate_provider_batch_response(
        symbols_requested=["AAPL", "MSFT"],
        meta=meta,
        bars_by_symbol=bars,
        allowed_time_window=(time(9, 30), time(9, 34)),
        session_date=date(2024, 1, 2),
    )
    assert res.is_valid
    assert res.status == PayloadIntegrityStatus.VALID


def test_validate_provider_batch_http_error() -> None:
    """HTTP error status fails closed as HTTP_ERROR."""
    meta = {
        "http_status": 500,
        "pagination_complete": False,
        "safe_error_classification": "http_500",
    }
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta=meta,
        bars_by_symbol={},
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.HTTP_ERROR
    assert "500" in res.error_message


def test_validate_provider_batch_incomplete_pagination() -> None:
    """Truncated pagination or token cycle fails closed as PAGINATION_INCOMPLETE."""
    meta = {
        "http_status": 200,
        "pagination_complete": False,
        "next_page_token_present": True,
    }
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta=meta,
        bars_by_symbol={"AAPL": []},
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.PAGINATION_INCOMPLETE


def test_validate_provider_batch_unexpected_symbol() -> None:
    """Unexpected symbol in response fails closed as UNEXPECTED_SYMBOL."""
    meta = {
        "http_status": 200,
        "pagination_complete": True,
        "response_symbols": ["AAPL", "ROGUE"],
    }
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta=meta,
        bars_by_symbol={"AAPL": [], "ROGUE": []},
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.UNEXPECTED_SYMBOL
    assert "ROGUE" in res.unexpected_symbols


def test_validate_provider_batch_malformed_timestamp() -> None:
    """Malformed or non-parseable timestamp fails closed as MALFORMED_TIMESTAMP."""
    meta = {
        "http_status": 200,
        "pagination_complete": True,
        "response_symbols": ["AAPL"],
        "malformed_timestamp_counts": {"AAPL": 1},
    }
    bars = {
        "AAPL": [
            {"t": "not-a-timestamp", "o": 100.0, "h": 105.0, "l": 95.0, "c": 102.0, "v": 1000.0},
        ]
    }
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta=meta,
        bars_by_symbol=bars,
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.MALFORMED_TIMESTAMP


def test_validate_provider_batch_duplicate_timestamp() -> None:
    """Duplicate timestamps for a symbol fail closed as DUPLICATE_TIMESTAMP."""
    meta = {
        "http_status": 200,
        "pagination_complete": True,
        "response_symbols": ["AAPL"],
    }
    bars = {
        "AAPL": [
            {"t": "2024-01-02T14:30:00Z", "o": 100.0, "h": 105.0, "l": 95.0, "c": 102.0, "v": 1000.0},
            {"t": "2024-01-02T14:30:00Z", "o": 101.0, "h": 106.0, "l": 96.0, "c": 103.0, "v": 1200.0},
        ]
    }
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta=meta,
        bars_by_symbol=bars,
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.DUPLICATE_TIMESTAMP


def test_validate_provider_batch_out_of_session_bar() -> None:
    """Bar with timestamp outside requested session or intraday window fails closed."""
    meta = {
        "http_status": 200,
        "pagination_complete": True,
        "response_symbols": ["AAPL"],
    }
    # 09:29 ET is outside 09:30-09:34 window
    bars = {
        "AAPL": [
            {"t": "2024-01-02T14:29:00Z", "o": 100.0, "h": 105.0, "l": 95.0, "c": 102.0, "v": 1000.0},
        ]
    }
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta=meta,
        bars_by_symbol=bars,
        allowed_time_window=(time(9, 30), time(9, 34)),
        session_date=date(2024, 1, 2),
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.OUT_OF_SESSION_BAR


def test_validate_provider_batch_invalid_ohlcv_bounds() -> None:
    """Inverted bounds (high < low or close outside high/low) fail closed as INVALID_OHLCV."""
    meta = {
        "http_status": 200,
        "pagination_complete": True,
        "response_symbols": ["AAPL"],
    }
    bars = {
        "AAPL": [
            # High 100 < Low 105!
            {"t": "2024-01-02T14:30:00Z", "o": 102.0, "h": 100.0, "l": 105.0, "c": 102.0, "v": 1000.0},
        ]
    }
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta=meta,
        bars_by_symbol=bars,
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.INVALID_OHLCV


# =============================================================================
# 3. Provider Failures vs Legitimate Sparse Intervals
# =============================================================================


def test_provider_failure_is_not_counted_as_zero_volume_no_print() -> None:
    """Failed provider request must be recorded as PROVIDER_DATA_FAILURE, never NO_OPENING_PRINT."""
    d = date(2024, 1, 2)
    daily_bars = [
        DailyBar("FAILSYM", date(2023, 12, i), 10.0, 11.0, 9.5, 10.5, 2_000_000.0)
        for i in range(1, 20)
    ]
    # FAILSYM failed provider request
    cur_failures = {"FAILSYM"}
    current_or_by_sym = {"FAILSYM": None}  # empty response because request failed!

    audit, outcomes, _eligible, _ors = audit_candidate_screening(
        daily_base_qualified_symbols=["FAILSYM"],
        current_or_by_symbol=current_or_by_sym,
        current_or_provider_failures=cur_failures,
        prior_or_obs_by_symbol={},
        prior_or_provider_failures=set(),
        daily_bars_by_symbol={"FAILSYM": daily_bars},
        target_session=d,
    )
    assert outcomes["FAILSYM"] == CandidateScreeningOutcome.PROVIDER_DATA_FAILURE
    assert audit.no_opening_print_count == 0
    assert audit.provider_failure_count == 1
    assert not audit.meets_screening_gate


def test_verified_completed_empty_response_is_legitimate_no_opening_print() -> None:
    """Completed provider response with zero trades is classified as NO_OPENING_PRINT_NO_SETUP."""
    d = date(2024, 1, 2)
    daily_bars = [
        DailyBar("SPARSESYM", date(2023, 12, i), 10.0, 11.0, 9.5, 10.5, 2_000_000.0)
        for i in range(1, 20)
    ]
    # SPARSESYM had a verified completed response (no provider failure), with no trades in OR
    audit, outcomes, _eligible, _ors = audit_candidate_screening(
        daily_base_qualified_symbols=["SPARSESYM"],
        current_or_by_symbol={"SPARSESYM": None},
        current_or_provider_failures=set(),
        prior_or_obs_by_symbol={},
        prior_or_provider_failures=set(),
        daily_bars_by_symbol={"SPARSESYM": daily_bars},
        target_session=d,
    )
    assert outcomes["SPARSESYM"] == CandidateScreeningOutcome.NO_OPENING_PRINT_NO_SETUP
    assert audit.no_opening_print_count == 1
    assert audit.provider_failure_count == 0
    assert audit.meets_screening_gate


# =============================================================================
# 4. Stage-B Invariants & Liquidation-Bar Coverage Tests
# =============================================================================


def test_stage_b_usable_with_valid_sparse_bars_and_1559_bar() -> None:
    """Valid sparse session (e.g. 50 bars out of 385) with 15:59 liquidation bar is USABLE."""
    d = date(2024, 1, 2)
    # 49 intermediate bars + 15:59 bar = 50 actual bars, 335 sparse minutes
    start_dt = datetime(2024, 1, 2, 9, 35, tzinfo=NY_TZ)
    bars = [_make_bar("TEST", d, (start_dt + timedelta(minutes=i)).time()) for i in range(49)]
    bars.append(_make_bar("TEST", d, time(15, 59)))

    audit = audit_stage_b_price_path_corr_003(
        active_selected_symbols=["TEST"],
        stage_b_bars_by_symbol={"TEST": bars},
        stage_b_provider_failures=set(),
        expected_minutes=385,
        session_date=d,
    )
    assert audit.is_usable
    assert audit.total_actual_bars == 50
    assert audit.total_sparse_minutes == 335
    assert audit.missing_eod_bar_symbols_count == 0
    assert audit.provider_failure_count == 0
    assert audit.integrity_failure_count == 0


def test_stage_b_unusable_when_1559_liquidation_bar_missing() -> None:
    """Missing 15:59 liquidation bar strictly prevents USABLE classification."""
    d = date(2024, 1, 2)
    # 384 bars present from 09:35 to 15:58, but 15:59 missing!
    bars = [
        _make_bar("TEST", d, time(h, m))
        for h in range(9, 16)
        for m in range(60)
        if (h == 9 and m >= 35) or (10 <= h <= 14) or (h == 15 and m < 59)
    ]
    assert len(bars) == 384

    audit = audit_stage_b_price_path_corr_003(
        active_selected_symbols=["TEST"],
        stage_b_bars_by_symbol={"TEST": bars},
        stage_b_provider_failures=set(),
        expected_minutes=385,
        session_date=d,
    )
    assert not audit.is_usable
    assert audit.missing_eod_bar_symbols_count == 1
    assert "15:59" in audit.unusable_reason


def test_stage_b_unusable_when_provider_failed() -> None:
    """Provider failure on any actionable symbol prevents USABLE classification."""
    d = date(2024, 1, 2)
    audit = audit_stage_b_price_path_corr_003(
        active_selected_symbols=["FAILS"],
        stage_b_bars_by_symbol={},
        stage_b_provider_failures={"FAILS"},
        expected_minutes=385,
        session_date=d,
    )
    assert not audit.is_usable
    assert audit.provider_failure_count == 1


def test_stage_b_unusable_when_duplicate_timestamps_present() -> None:
    """Duplicate timestamp in Stage-B bars fails closed as unusable."""
    d = date(2024, 1, 2)
    b1 = _make_bar("TEST", d, time(9, 35))
    b2 = _make_bar("TEST", d, time(9, 35))  # duplicate!
    b_eod = _make_bar("TEST", d, time(15, 59))

    audit = audit_stage_b_price_path_corr_003(
        active_selected_symbols=["TEST"],
        stage_b_bars_by_symbol={"TEST": [b1, b2, b_eod]},
        stage_b_provider_failures=set(),
        expected_minutes=385,
        session_date=d,
    )
    assert not audit.is_usable
    assert audit.integrity_failure_count == 1
    assert "Duplicate" in audit.unusable_reasons[0]


def test_stage_b_unusable_when_out_of_session_bar_present() -> None:
    """Out-of-session bar (e.g. 16:00 ET) in Stage-B fails closed as unusable."""
    d = date(2024, 1, 2)
    b_early = _make_bar("TEST", d, time(9, 34))  # 09:34 is OR, not Stage-B!
    b_eod = _make_bar("TEST", d, time(15, 59))

    audit = audit_stage_b_price_path_corr_003(
        active_selected_symbols=["TEST"],
        stage_b_bars_by_symbol={"TEST": [b_early, b_eod]},
        stage_b_provider_failures=set(),
        expected_minutes=385,
        session_date=d,
    )
    assert not audit.is_usable
    assert audit.integrity_failure_count == 1
    assert "Out-of-session" in audit.unusable_reasons[0]


# =============================================================================
# 5. Complete Private Fixture & Offline Replay Verification
# =============================================================================


def _build_synthetic_fixture(tmp_path: Path, pilot_date: str = "2024-01-02") -> Path:
    """Construct a complete, deterministic, private raw OHLCV fixture for offline replay."""
    fixture_dir = tmp_path / "private_fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, Any]] = {}

    # 1. Massive reference snapshot (2 symbols: AAA, BBB)
    ref_rows = [
        {"ticker": "AAA", "primary_exchange": "XNYS", "type": "CS", "active": True},
        {"ticker": "BBB", "primary_exchange": "XNAS", "type": "CS", "active": True},
    ]
    ref_file = f"massive_reference_{pilot_date}.json"
    ref_bytes = json.dumps(ref_rows, indent=2).encode("utf-8")
    (fixture_dir / ref_file).write_bytes(ref_bytes)
    artifacts[ref_file] = {
        "sha256": hash_bytes(ref_bytes),
        "size_bytes": len(ref_bytes),
        "description": "Massive reference snapshot",
        "record_count": len(ref_rows),
    }

    # 2. Universe file
    univ_file = f"universe_{pilot_date}.json"
    univ_bytes = json.dumps({
        "date": pilot_date,
        "canonical_target_universe_count": 2,
        "valid_symbols_count": 2,
        "ambiguous_symbols_count": 0,
        "universe_sha256": "fake_univ_hash",
        "valid_symbols": ["AAA", "BBB"],
        "ambiguous_symbols": [],
    }, indent=2).encode("utf-8")
    (fixture_dir / univ_file).write_bytes(univ_bytes)
    artifacts[univ_file] = {
        "sha256": hash_bytes(univ_bytes),
        "size_bytes": len(univ_bytes),
        "description": "Universe summary",
        "record_count": 2,
    }

    # 3. Dec 2023 Daily bars (20 trading days each, ADV14 >= 1M, ATR14 > 0.50)
    daily_dates = [s.isoformat() for s in get_prior_xnys_sessions(date(2024, 1, 2), 20)]
    daily_bars_aaa = [
        {"t": f"{d}T05:00:00Z", "o": 50.0, "h": 52.0, "l": 49.0, "c": 51.0, "v": 2_000_000.0}
        for d in daily_dates
    ]
    daily_bars_bbb = [
        {"t": f"{d}T05:00:00Z", "o": 30.0, "h": 32.0, "l": 29.0, "c": 31.0, "v": 1_500_000.0}
        for d in daily_dates
    ]
    daily_batch = [{
        "batch_index": 1,
        "symbols_requested": ["AAA", "BBB"],
        "http_status": 200,
        "pagination_complete": True,
        "page_count": 1,
        "token_hashes": ["hash1"],
        "token_sequence_sha256": "tokseq",
        "bars_by_symbol": {"AAA": daily_bars_aaa, "BBB": daily_bars_bbb},
    }]
    daily_file = "alpaca_daily_dec2023.json"
    daily_hash, daily_size = persist_raw_stage_artifact(
        fixture_dir / daily_file,
        metadata={"stage": "phase_2_broad_daily"},
        batches=daily_batch,
    )
    artifacts[daily_file] = {
        "sha256": daily_hash,
        "size_bytes": daily_size,
        "description": "Daily bars",
        "record_count": 2,
    }

    # 4. Current Opening Range (09:30-09:34 ET)
    # AAA: or_open 51.0, close 52.0 (LONG, stop 52.0), or_volume 50_000
    or_bars_aaa = [
        {"t": "2024-01-02T14:30:00Z", "o": 51.0, "h": 51.5, "l": 50.8, "c": 51.2, "v": 25000.0},
        {"t": "2024-01-02T14:34:00Z", "o": 51.2, "h": 52.0, "l": 51.0, "c": 52.0, "v": 25000.0},
    ]
    # BBB: or_open 4.0 <= 5.0 (PRICE_REJECTED)
    or_bars_bbb = [
        {"t": "2024-01-02T14:30:00Z", "o": 4.0, "h": 4.2, "l": 3.9, "c": 4.1, "v": 10000.0},
    ]
    cur_batch = [{
        "batch_index": 1,
        "symbols_requested": ["AAA", "BBB"],
        "http_status": 200,
        "pagination_complete": True,
        "page_count": 1,
        "token_hashes": ["hash1"],
        "token_sequence_sha256": "tokseq",
        "bars_by_symbol": {"AAA": or_bars_aaa, "BBB": or_bars_bbb},
    }]
    cur_file = f"alpaca_current_or_{pilot_date}.json"
    cur_hash, cur_size = persist_raw_stage_artifact(
        fixture_dir / cur_file,
        metadata={"stage": "phase_3_current_opening_range"},
        batches=cur_batch,
    )
    artifacts[cur_file] = {
        "sha256": cur_hash,
        "size_bytes": cur_size,
        "description": "Current OR bars",
        "record_count": 2,
    }

    # 5. Prior 14 Sessions Opening Range (AAA only needs RV, mean prior OR volume = 20,000 -> RV = 2.5 >= 1.0)
    # 14 prior XNYS sessions
    prior_sessions = [s.isoformat() for s in get_prior_xnys_sessions(date(2024, 1, 2), 14)]
    prior_sessions_data: dict[str, list[dict[str, Any]]] = {}
    for ps in prior_sessions:
        prior_sessions_data[ps] = [{
            "batch_index": 1,
            "symbols_requested": ["AAA"],
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 1,
            "token_hashes": ["hash1"],
            "token_sequence_sha256": "tokseq",
            "bars_by_symbol": {
                "AAA": [{"t": f"{ps}T14:30:00Z", "o": 50.0, "h": 51.0, "l": 49.5, "c": 50.5, "v": 20000.0}]
            },
        }]
    prior_file = f"alpaca_prior_or_14sessions_{pilot_date}.json"
    p_bytes = json.dumps({
        "metadata": {"stage": "phase_3_prior_14_sessions_opening_range"},
        "sessions_data": prior_sessions_data,
    }, indent=2).encode("utf-8")
    (fixture_dir / prior_file).write_bytes(p_bytes)
    artifacts[prior_file] = {
        "sha256": hash_bytes(p_bytes),
        "size_bytes": len(p_bytes),
        "description": "Prior 14 sessions OR",
        "record_count": 14,
    }

    # 6. Top-20 Selection record (AAA selected)
    sel_file = f"top_20_selection_{pilot_date}.json"
    sel_records = [{
        "rank": 1,
        "symbol": "AAA",
        "session_date": pilot_date,
        "opening_price": 51.0,
        "adv14": 2000000.0,
        "atr14": 3.0,
        "or_volume": 50000.0,
        "mean_prior_or_volume": 20000.0,
        "relative_volume": 2.5,
        "direction": "LONG",
        "stop_level": 52.0,
        "order_intent_status": "FILLED",
        "desired_shares": 100,
        "risk_per_share": 1.0,
    }]
    sel_bytes = json.dumps({
        "date": pilot_date,
        "selection_sha256": "fake_sel_sha",
        "selected_count": 1,
        "doji_count": 0,
        "eligible_candidates_count": 1,
        "records": sel_records,
    }, indent=2).encode("utf-8")
    (fixture_dir / sel_file).write_bytes(sel_bytes)
    artifacts[sel_file] = {
        "sha256": hash_bytes(sel_bytes),
        "size_bytes": len(sel_bytes),
        "description": "Top-20 selection",
        "record_count": 1,
    }

    # 7. Stage-B Minute bars for AAA (valid sparse bars with 15:59 liquidation bar)
    sb_bars_aaa = [
        {"t": "2024-01-02T14:35:00Z", "o": 52.0, "h": 53.0, "l": 51.8, "c": 52.5, "v": 10000.0},
        {"t": "2024-01-02T20:59:00Z", "o": 54.0, "h": 54.5, "l": 53.8, "c": 54.2, "v": 15000.0},  # 15:59 ET liquidation bar!
    ]
    sb_batch = [{
        "batch_index": 1,
        "symbols_requested": ["AAA"],
        "http_status": 200,
        "pagination_complete": True,
        "page_count": 1,
        "token_hashes": ["hash1"],
        "token_sequence_sha256": "tokseq",
        "bars_by_symbol": {"AAA": sb_bars_aaa},
    }]
    sb_file = f"alpaca_stage_b_{pilot_date}.json"
    sb_hash, sb_size = persist_raw_stage_artifact(
        fixture_dir / sb_file,
        metadata={"stage": "phase_5_stage_b_minute_bars"},
        batches=sb_batch,
    )
    artifacts[sb_file] = {
        "sha256": sb_hash,
        "size_bytes": sb_size,
        "description": "Stage-B minute bars",
        "record_count": 1,
    }

    # 8. Manifest
    create_and_save_manifest(fixture_dir, artifacts, pilot_date)
    return fixture_dir


def test_deterministic_offline_replay_succeeds(tmp_path: Path) -> None:
    """Complete private raw fixture deterministically reproduces screening and Stage-B usability."""
    fixture_dir = _build_synthetic_fixture(tmp_path)

    res = replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")
    assert res.target_audit.canonical_target_universe_count == 2
    assert res.daily_audit.daily_computable_count == 2
    assert res.daily_audit.daily_base_qualified_count == 2
    assert res.screening_audit.eligible_candidate_count == 1  # AAA eligible, BBB price rejected
    assert res.selection_evidence.selected_count == 1
    assert res.selection_records[0]["symbol"] == "AAA"
    assert res.stage_b_audit.is_usable
    assert res.stage_b_audit.total_actual_bars == 2
    assert res.stage_b_audit.missing_eod_bar_symbols_count == 0
    assert res.disposition == PilotDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD


def test_tampered_replay_artifact_fails_closed(tmp_path: Path) -> None:
    """Tampering with an artifact file byte causes manifest verification to fail closed."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    stage_b_file = fixture_dir / "alpaca_stage_b_2024-01-02.json"

    # Modify one byte in the file
    content = stage_b_file.read_text(encoding="utf-8")
    stage_b_file.write_text(content.replace("52.5", "99.9"), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="Replay manifest verification failed closed"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_missing_replay_artifact_fails_closed(tmp_path: Path) -> None:
    """Deleting an artifact file causes replay to fail closed."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    (fixture_dir / "alpaca_daily_dec2023.json").unlink()

    with pytest.raises(ReplayIntegrityError, match="Missing artifact file"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_missing_manifest_fails_closed(tmp_path: Path) -> None:
    """Missing manifest fails closed immediately."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    (fixture_dir / "manifest_2024-01-02.json").unlink()

    with pytest.raises(ReplayIntegrityError, match="Missing manifest file"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_tampered_manifest_checksum_fails_closed(tmp_path: Path) -> None:
    """Altering checksum in manifest causes verification mismatch to fail closed."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    manifest_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["alpaca_daily_dec2023.json"]["sha256"] = "badhash0000000000000000000000000000000000000000000000000000000000"
    manifest_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="SHA-256 checksum mismatch"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_corrupt_provider_batch_in_artifact_fails_closed(tmp_path: Path) -> None:
    """Artifact containing corrupt provider payload fails closed under replay."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    stage_b_file = fixture_dir / "alpaca_stage_b_2024-01-02.json"
    sb_payload = json.loads(stage_b_file.read_text(encoding="utf-8"))
    # Invalidate HTTP status
    sb_payload["batches"][0]["http_status"] = 500
    sb_bytes = json.dumps(sb_payload, indent=2).encode("utf-8")
    stage_b_file.write_bytes(sb_bytes)

    # Re-sign manifest to test payload validation failure rather than manifest mismatch
    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["alpaca_stage_b_2024-01-02.json"]["sha256"] = hash_bytes(sb_bytes)
    m_data["artifacts"]["alpaca_stage_b_2024-01-02.json"]["size_bytes"] = len(sb_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    # Replay must catch provider failure in Stage-B and report BLOCKED_STAGE_B_PRICE_PATH
    res = replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")
    assert not res.stage_b_audit.is_usable
    assert res.stage_b_audit.provider_failure_count == 1
    assert res.disposition == PilotDisposition.BLOCKED_STAGE_B_PRICE_PATH
