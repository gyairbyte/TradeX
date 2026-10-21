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

import concurrent.futures
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import requests

from tradex.research.daytrade_orb.corr_003_pilot import (
    CORR_002_SPEC_PATH,
    CORR_003_ENV_SPEC_PATH,
    CORR_003_SPEC_PATH,
    LOCKED_003B_SPEC_PATH,
    LOCKED_003B_SPEC_SHA256,
    LOCKED_003C_RESOLUTION_PATH,
    LOCKED_003C_RESOLUTION_SHA256,
    LOCKED_003D_CORR_001_SPEC_PATH,
    LOCKED_003D_CORR_001_SPEC_SHA256,
    LOCKED_003D_CORR_002_SPEC_SHA256,
    LOCKED_003D_CORR_003_ENV_SPEC_SHA256,
    LOCKED_003D_CORR_003_SPEC_SHA256,
    LOCKED_003D_SPEC_PATH,
    LOCKED_003D_SPEC_SHA256,
    PILOT_DATE,
    TASK_ID,
    CandidateScreeningOutcome,
    PayloadIntegrityStatus,
    PilotDisposition,
    ReplayIntegrityError,
    acquire_atomic_pilot_run_lock,
    audit_broad_daily_availability,
    audit_candidate_screening,
    audit_stage_b_price_path_corr_003,
    check_one_shot_pilot_guard,
    check_pilot_authorization,
    check_pre_live_code_freeze,
    check_resource_limits,
    check_runtime_environment_freeze,
    create_and_save_manifest,
    filter_and_audit_target_universe,
    freeze_top_20_selection,
    hash_bytes,
    is_allowed_post_freeze_drift,
    persist_raw_stage_artifact,
    rank_and_select_top_20,
    replay_corr_003_pilot,
    validate_batch_size,
    validate_provider_batch_response,
    validate_run_lock_marker,
    verify_replay_manifest,
    verify_upstream_spec_hashes,
)
from tradex.research.daytrade_orb.indicators import get_prior_xnys_sessions
from tradex.research.daytrade_orb.models import (
    DailyBar,
    MinuteBar,
    OpeningRangeVolumeObservation,
)
from tradex.research.daytrade_orb.ranking import evaluate_opening_range
from tradex.research.intraday_dataset.alpaca_client import (
    DatasetAlpacaClient,
    _token_hash,
    _token_sequence_hash,
)
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
    assert hashes[CORR_003_ENV_SPEC_PATH] == LOCKED_003D_CORR_003_ENV_SPEC_SHA256


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

    target_audit, _ = filter_and_audit_target_universe(ref_rows)

    # 2. Universe file
    univ_file = f"universe_{pilot_date}.json"
    univ_bytes = json.dumps({
        "date": pilot_date,
        "canonical_target_universe_count": target_audit.canonical_target_universe_count,
        "valid_symbols_count": len(target_audit.valid_target_symbols),
        "ambiguous_symbols_count": len(target_audit.ambiguous_symbols),
        "universe_sha256": target_audit.universe_sha256,
        "valid_symbols": target_audit.valid_target_symbols,
        "ambiguous_symbols": target_audit.ambiguous_symbols,
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
    tok_hashes = [_token_hash(None), _token_hash(None)]
    tok_seq = _token_sequence_hash(tok_hashes)

    daily_raw_pages = [{
        "http_status": 200,
        "page_token": None,
        "body": {
            "bars": {"AAA": daily_bars_aaa, "BBB": daily_bars_bbb},
            "next_page_token": None,
        },
    }]
    daily_batch = [{
        "batch_index": 1,
        "symbols_requested": ["AAA", "BBB"],
        "request_params": {
            "symbols": "AAA,BBB",
            "timeframe": "1Day",
            "feed": "sip",
            "adjustment": "raw",
            "asof": pilot_date,
            "start": "2023-12-01T00:00:00Z",
            "end": "2023-12-29T23:59:00Z",
        },
        "http_status": 200,
        "pagination_complete": True,
        "page_count": 1,
        "token_hashes": tok_hashes,
        "token_sequence_sha256": tok_seq,
        "meta": {
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 1,
            "safe_error_classification": "none",
            "repeated_page_token": False,
            "pagination_cycle_detected": False,
            "terminal_next_page_token_present": False,
            "unconsumed_page_token_present": False,
            "response_symbols": ["AAA", "BBB"],
            "malformed_timestamp_counts": {"AAA": 0, "BBB": 0},
            "token_hashes": tok_hashes,
            "token_sequence_sha256": tok_seq,
            "raw_pages": daily_raw_pages,
        },
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
    cur_raw_pages = [{
        "http_status": 200,
        "page_token": None,
        "body": {
            "bars": {"AAA": or_bars_aaa, "BBB": or_bars_bbb},
            "next_page_token": None,
        },
    }]
    cur_batch = [{
        "batch_index": 1,
        "symbols_requested": ["AAA", "BBB"],
        "request_params": {
            "symbols": "AAA,BBB",
            "timeframe": "1Min",
            "feed": "sip",
            "adjustment": "raw",
            "asof": pilot_date,
            "start": "2024-01-02T14:30:00Z",
            "end": "2024-01-02T14:34:59Z",
        },
        "http_status": 200,
        "pagination_complete": True,
        "page_count": 1,
        "token_hashes": tok_hashes,
        "token_sequence_sha256": tok_seq,
        "meta": {
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 1,
            "safe_error_classification": "none",
            "repeated_page_token": False,
            "pagination_cycle_detected": False,
            "terminal_next_page_token_present": False,
            "unconsumed_page_token_present": False,
            "response_symbols": ["AAA", "BBB"],
            "malformed_timestamp_counts": {"AAA": 0, "BBB": 0},
            "token_hashes": tok_hashes,
            "token_sequence_sha256": tok_seq,
            "raw_pages": cur_raw_pages,
        },
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
    prior_sessions = [s.isoformat() for s in get_prior_xnys_sessions(date(2024, 1, 2), 14)]
    prior_sessions_data: dict[str, list[dict[str, Any]]] = {}
    for ps in prior_sessions:
        p_raw_pages = [{
            "http_status": 200,
            "page_token": None,
            "body": {
                "bars": {"AAA": [{"t": f"{ps}T14:30:00Z", "o": 50.0, "h": 51.0, "l": 49.5, "c": 50.5, "v": 20000.0}]},
                "next_page_token": None,
            },
        }]
        prior_sessions_data[ps] = [{
            "batch_index": 1,
            "symbols_requested": ["AAA"],
            "request_params": {
                "symbols": "AAA",
                "timeframe": "1Min",
                "feed": "sip",
                "adjustment": "raw",
                "asof": pilot_date,
                "start": f"{ps}T14:30:00Z",
                "end": f"{ps}T14:34:59Z",
            },
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 1,
            "token_hashes": tok_hashes,
            "token_sequence_sha256": tok_seq,
            "meta": {
                "http_status": 200,
                "pagination_complete": True,
                "page_count": 1,
                "safe_error_classification": "none",
                "repeated_page_token": False,
                "pagination_cycle_detected": False,
                "terminal_next_page_token_present": False,
                "unconsumed_page_token_present": False,
                "response_symbols": ["AAA"],
                "malformed_timestamp_counts": {"AAA": 0},
                "token_hashes": tok_hashes,
                "token_sequence_sha256": tok_seq,
                "raw_pages": p_raw_pages,
            },
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

    # 6. Top-20 Selection record (deterministic recomputation parity)
    d_obj = {
        sym: sorted([
            DailyBar(
                symbol=sym,
                session_date=datetime.fromisoformat(b["t"]).date(),
                open=b["o"],
                high=b["h"],
                low=b["l"],
                close=b["c"],
                volume=b["v"],
            )
            for b in (daily_bars_aaa if sym == "AAA" else daily_bars_bbb)
        ], key=lambda x: x.session_date)
        for sym in ["AAA", "BBB"]
    }
    _d_audit, _comp, d_qual = audit_broad_daily_availability(target_audit.valid_target_symbols, [], d_obj, date(2024, 1, 2))
    cur_ors = {
        "AAA": evaluate_opening_range([
            MinuteBar("AAA", datetime.fromisoformat(b["t"]), date(2024, 1, 2), b["o"], b["h"], b["l"], b["c"], b["v"])
            for b in or_bars_aaa
        ], require_five_bars=False),
        "BBB": evaluate_opening_range([
            MinuteBar("BBB", datetime.fromisoformat(b["t"]), date(2024, 1, 2), b["o"], b["h"], b["l"], b["c"], b["v"])
            for b in or_bars_bbb
        ], require_five_bars=False),
    }
    prior_obs = {
        "AAA": [
            OpeningRangeVolumeObservation("AAA", date.fromisoformat(ps), 20000.0)
            for ps in prior_sessions
        ]
    }
    _s_audit, _outcomes, elig, surv_ors = audit_candidate_screening(
        d_qual, cur_ors, set(), prior_obs, set(), d_obj, date(2024, 1, 2)
    )
    ranked = rank_and_select_top_20(elig, surv_ors, 25000.0, 20)
    sel_ev, sel_records, _ = freeze_top_20_selection(ranked)

    sel_file = f"top_20_selection_{pilot_date}.json"
    sel_bytes = json.dumps({
        "date": pilot_date,
        "selection_sha256": sel_ev.selection_sha256,
        "selected_count": sel_ev.selected_count,
        "doji_count": sel_ev.doji_count,
        "eligible_candidates_count": sel_ev.eligible_candidates_count,
        "records": sel_records,
    }, indent=2).encode("utf-8")
    (fixture_dir / sel_file).write_bytes(sel_bytes)
    artifacts[sel_file] = {
        "sha256": hash_bytes(sel_bytes),
        "size_bytes": len(sel_bytes),
        "description": "Top-20 selection",
        "record_count": len(sel_records),
    }

    # 7. Stage-B Minute bars for AAA (valid sparse bars with 15:59 liquidation bar)
    sb_bars_aaa = [
        {"t": "2024-01-02T14:35:00Z", "o": 52.0, "h": 53.0, "l": 51.8, "c": 52.5, "v": 10000.0},
        {"t": "2024-01-02T20:59:00Z", "o": 54.0, "h": 54.5, "l": 53.8, "c": 54.2, "v": 15000.0},  # 15:59 ET liquidation bar!
    ]
    sb_raw_pages = [{
        "http_status": 200,
        "page_token": None,
        "body": {
            "bars": {"AAA": sb_bars_aaa},
            "next_page_token": None,
        },
    }]
    sb_batch = [{
        "batch_index": 1,
        "symbols_requested": ["AAA"],
        "request_params": {
            "symbols": "AAA",
            "timeframe": "1Min",
            "feed": "sip",
            "adjustment": "raw",
            "asof": pilot_date,
            "start": "2024-01-02T14:35:00Z",
            "end": "2024-01-02T20:59:59Z",
        },
        "http_status": 200,
        "pagination_complete": True,
        "page_count": 1,
        "token_hashes": tok_hashes,
        "token_sequence_sha256": tok_seq,
        "meta": {
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 1,
            "safe_error_classification": "none",
            "repeated_page_token": False,
            "pagination_cycle_detected": False,
            "terminal_next_page_token_present": False,
            "unconsumed_page_token_present": False,
            "response_symbols": ["AAA"],
            "malformed_timestamp_counts": {"AAA": 0},
            "token_hashes": tok_hashes,
            "token_sequence_sha256": tok_seq,
            "raw_pages": sb_raw_pages,
        },
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
    m_data["artifacts"]["alpaca_daily_dec2023.json"]["sha256"] = "0" * 64
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

    # Replay must catch provider failure in Stage-B and report BLOCKED_PROVIDER_DATA_INTEGRITY
    res = replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")
    assert not res.stage_b_audit.is_usable
    assert res.stage_b_audit.provider_failure_count == 1
    assert res.disposition == PilotDisposition.BLOCKED_PROVIDER_DATA_INTEGRITY


def _make_resp(status_code: int, data: dict[str, Any]) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = json.dumps(data).encode("utf-8")
    return resp


def test_client_two_page_pagination_success() -> None:
    calls = 0

    def fake_request(url: str, params: dict[str, Any], headers: dict[str, str], timeout: int):
        nonlocal calls
        calls += 1
        if calls == 1:
            data = {
                "bars": {
                    "AAA": [{"t": "2024-01-02T14:30:00Z", "o": 50.0, "h": 51.0, "l": 49.5, "c": 50.5, "v": 1000.0}]
                },
                "next_page_token": "token_page_2",
            }
        else:
            data = {
                "bars": {
                    "AAA": [{"t": "2024-01-02T14:31:00Z", "o": 50.5, "h": 51.2, "l": 50.2, "c": 51.0, "v": 1500.0}]
                },
                "next_page_token": None,
            }
        return _make_resp(200, data)

    client = DatasetAlpacaClient(
        api_key="fake",
        secret_key="fake",
        request_func=fake_request,
        request_delay_seconds=0.0,
        max_retries=1,
    )
    start_utc = datetime(2024, 1, 2, 14, 30, tzinfo=ZoneInfo("UTC"))
    end_utc = datetime(2024, 1, 2, 14, 34, tzinfo=ZoneInfo("UTC"))
    dfs, meta = client.get_bars(
        symbols=["AAA"],
        start_utc=start_utc,
        end_utc=end_utc,
        feed="sip",
        adjustment="split",
        timeframe="1Min",
        include_raw_pages=True,
    )
    assert calls == 2
    assert meta["http_pages"] == 2
    assert meta["page_count"] == 2
    assert meta["pagination_complete"] is True
    assert meta["terminal_next_page_token"] is None
    assert meta["terminal_next_page_token_present"] is False
    assert meta["unconsumed_page_token_present"] is False
    assert meta["repeated_page_token"] is False
    assert meta["pagination_cycle_detected"] is False
    assert meta["safe_error_classification"] == "none"
    assert "AAA" in dfs
    assert len(dfs["AAA"]) == 2


def test_client_incomplete_pagination_when_max_pages_reached() -> None:
    calls = 0

    def fake_request(url: str, params: dict[str, Any], headers: dict[str, str], timeout: int):
        nonlocal calls
        calls += 1
        data = {
            "bars": {
                "AAA": [{"t": f"2024-01-02T14:3{calls}:00Z", "o": 50.0, "h": 51.0, "l": 49.5, "c": 50.5, "v": 1000.0}]
            },
            "next_page_token": f"token_page_{calls + 1}",
        }
        return _make_resp(200, data)

    client = DatasetAlpacaClient(
        api_key="fake",
        secret_key="fake",
        request_func=fake_request,
        request_delay_seconds=0.0,
        max_retries=1,
    )
    start_utc = datetime(2024, 1, 2, 14, 30, tzinfo=ZoneInfo("UTC"))
    end_utc = datetime(2024, 1, 2, 14, 34, tzinfo=ZoneInfo("UTC"))
    _dfs, meta = client.get_bars(
        symbols=["AAA"],
        start_utc=start_utc,
        end_utc=end_utc,
        feed="sip",
        adjustment="split",
        timeframe="1Min",
        max_pages=2,
    )
    assert calls == 2
    assert meta["http_pages"] == 2
    assert meta["pagination_complete"] is False
    assert meta["terminal_next_page_token"] == "token_page_3"
    assert meta["terminal_next_page_token_present"] is True
    assert meta["unconsumed_page_token_present"] is True
    assert meta["safe_error_classification"] == "max_pages_exceeded"


def test_client_pagination_cycle_detected() -> None:
    calls = 0

    def fake_request(url: str, params: dict[str, Any], headers: dict[str, str], timeout: int):
        nonlocal calls
        calls += 1
        data = {
            "bars": {
                "AAA": [{"t": f"2024-01-02T14:3{calls}:00Z", "o": 50.0, "h": 51.0, "l": 49.5, "c": 50.5, "v": 1000.0}]
            },
            "next_page_token": "token_cycle",
        }
        return _make_resp(200, data)

    client = DatasetAlpacaClient(
        api_key="fake",
        secret_key="fake",
        request_func=fake_request,
        request_delay_seconds=0.0,
        max_retries=1,
    )
    start_utc = datetime(2024, 1, 2, 14, 30, tzinfo=ZoneInfo("UTC"))
    end_utc = datetime(2024, 1, 2, 14, 34, tzinfo=ZoneInfo("UTC"))
    _dfs, meta = client.get_bars(
        symbols=["AAA"],
        start_utc=start_utc,
        end_utc=end_utc,
        feed="sip",
        adjustment="split",
        timeframe="1Min",
    )
    assert calls == 2
    assert meta["pagination_cycle_detected"] is True
    assert meta["repeated_page_token"] is True
    assert meta["pagination_complete"] is False
    assert meta["safe_error_classification"] == "pagination_cycle"


def test_daily_batch_failure_propagates_to_blocked_disposition(tmp_path: Path) -> None:
    fixture_dir = _build_synthetic_fixture(tmp_path)
    daily_file = fixture_dir / "alpaca_daily_dec2023.json"
    daily_payload = json.loads(daily_file.read_text(encoding="utf-8"))
    daily_payload["batches"][0]["http_status"] = 500
    daily_payload["batches"][0]["meta"]["http_status"] = 500
    daily_payload["batches"][0]["meta"]["safe_error_classification"] = "server_error"
    daily_bytes = json.dumps(daily_payload, indent=2).encode("utf-8")
    daily_file.write_bytes(daily_bytes)

    # Recomputed selection has 0 candidates due to daily failure; synchronize top_20_selection
    sel_file = fixture_dir / "top_20_selection_2024-01-02.json"
    sel_data = {
        "date": "2024-01-02",
        "selection_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        "selected_count": 0,
        "doji_count": 0,
        "eligible_candidates_count": 0,
        "records": [],
    }
    sel_bytes = json.dumps(sel_data, indent=2).encode("utf-8")
    sel_file.write_bytes(sel_bytes)

    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["alpaca_daily_dec2023.json"]["sha256"] = hash_bytes(daily_bytes)
    m_data["artifacts"]["alpaca_daily_dec2023.json"]["size_bytes"] = len(daily_bytes)
    m_data["artifacts"]["top_20_selection_2024-01-02.json"]["sha256"] = hash_bytes(sel_bytes)
    m_data["artifacts"]["top_20_selection_2024-01-02.json"]["size_bytes"] = len(sel_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    res = replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")
    assert not res.provider_data_integrity_success
    assert len(res.daily_provider_failures) > 0
    assert res.disposition == PilotDisposition.BLOCKED_PROVIDER_DATA_INTEGRITY


def test_unexpected_provider_response_symbol_in_raw_pages_fails_closed() -> None:
    meta = {
        "http_status": 200,
        "pagination_complete": True,
        "response_symbols": ["AAA"],
        "raw_pages": [
            {
                "body": {
                    "bars": {
                        "AAA": [],
                        "HACK_UNEXPECTED": [],
                    }
                }
            }
        ],
    }
    bars_by_symbol = {"AAA": []}
    res = validate_provider_batch_response(
        symbols_requested=["AAA"],
        meta=meta,
        bars_by_symbol=bars_by_symbol,
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.UNEXPECTED_SYMBOL
    assert "HACK_UNEXPECTED" in res.unexpected_symbols


def test_missing_mandatory_provenance_fails_closed() -> None:
    # 1. Missing entirely
    res1 = validate_provider_batch_response(
        symbols_requested=["AAA"],
        meta={},
        bars_by_symbol={"AAA": []},
    )
    assert not res1.is_valid
    assert res1.status == PayloadIntegrityStatus.PAGINATION_INCOMPLETE
    assert "Missing mandatory provenance" in res1.error_message

    # 2. None values
    res2 = validate_provider_batch_response(
        symbols_requested=["AAA"],
        meta={"http_status": None, "pagination_complete": True},
        bars_by_symbol={"AAA": []},
    )
    assert not res2.is_valid
    assert res2.status == PayloadIntegrityStatus.PAGINATION_INCOMPLETE


def test_contradictory_request_params_fails_closed(tmp_path: Path) -> None:
    fixture_dir = _build_synthetic_fixture(tmp_path)
    cur_file = fixture_dir / "alpaca_current_or_2024-01-02.json"
    cur_payload = json.loads(cur_file.read_text(encoding="utf-8"))
    cur_payload["batches"][0]["request_params"] = {"symbols": ["AAA", "CONTRADICTION"], "timeframe": "1Min"}
    cur_bytes = json.dumps(cur_payload, indent=2).encode("utf-8")
    cur_file.write_bytes(cur_bytes)

    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["sha256"] = hash_bytes(cur_bytes)
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["size_bytes"] = len(cur_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="Contradictory request parameters"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_manifest_unlisted_extra_file_fails_closed(tmp_path: Path) -> None:
    fixture_dir = _build_synthetic_fixture(tmp_path)
    (fixture_dir / "unlisted_extra_file.json").write_text("{}", encoding="utf-8")

    ok, _, errors = verify_replay_manifest(fixture_dir, "2024-01-02")
    assert not ok
    assert any("Unlisted extra file detected" in e for e in errors)

    with pytest.raises(ReplayIntegrityError, match="Replay manifest verification failed closed"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_manifest_omitted_required_file_entry_fails_closed(tmp_path: Path) -> None:
    fixture_dir = _build_synthetic_fixture(tmp_path)
    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    del m_data["artifacts"]["universe_2024-01-02.json"]
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    ok, _, errors = verify_replay_manifest(fixture_dir, "2024-01-02")
    assert not ok
    assert any("Required artifact 'universe_2024-01-02.json' is missing from manifest" in e for e in errors)

    with pytest.raises(ReplayIntegrityError, match="Replay manifest verification failed closed"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_manifest_invalid_size_or_hash_fails_closed(tmp_path: Path) -> None:
    fixture_dir = _build_synthetic_fixture(tmp_path)
    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))

    # Test non-positive size_bytes
    m_data["artifacts"]["universe_2024-01-02.json"]["size_bytes"] = 0
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")
    ok, _, errors = verify_replay_manifest(fixture_dir, "2024-01-02")
    assert not ok
    assert any("missing mandatory positive 'size_bytes'" in e for e in errors)

    # Test invalid SHA-256 length
    m_data["artifacts"]["universe_2024-01-02.json"]["size_bytes"] = 100
    m_data["artifacts"]["universe_2024-01-02.json"]["sha256"] = "short_hash"
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")
    ok, _, errors = verify_replay_manifest(fixture_dir, "2024-01-02")
    assert not ok
    assert any("missing mandatory valid 64-character 'sha256'" in e for e in errors)


def test_omitted_prior_session_fails_closed(tmp_path: Path) -> None:
    fixture_dir = _build_synthetic_fixture(tmp_path)
    prior_file = fixture_dir / "alpaca_prior_or_14sessions_2024-01-02.json"
    p_data = json.loads(prior_file.read_text(encoding="utf-8"))
    sessions_keys = list(p_data["sessions_data"].keys())
    del p_data["sessions_data"][sessions_keys[0]]
    p_bytes = json.dumps(p_data, indent=2).encode("utf-8")
    prior_file.write_bytes(p_bytes)

    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["alpaca_prior_or_14sessions_2024-01-02.json"]["sha256"] = hash_bytes(p_bytes)
    m_data["artifacts"]["alpaca_prior_or_14sessions_2024-01-02.json"]["size_bytes"] = len(p_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="Prior OR artifact missing expected sessions"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_omitted_daily_batch_symbol_coverage_fails_closed(tmp_path: Path) -> None:
    fixture_dir = _build_synthetic_fixture(tmp_path)
    daily_file = fixture_dir / "alpaca_daily_dec2023.json"
    daily_data = json.loads(daily_file.read_text(encoding="utf-8"))
    daily_data["batches"][0]["symbols_requested"] = ["AAA"]
    daily_data["batches"][0]["request_params"]["symbols"] = ["AAA"]
    del daily_data["batches"][0]["bars_by_symbol"]["BBB"]
    d_bytes = json.dumps(daily_data, indent=2).encode("utf-8")
    daily_file.write_bytes(d_bytes)

    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["alpaca_daily_dec2023.json"]["sha256"] = hash_bytes(d_bytes)
    m_data["artifacts"]["alpaca_daily_dec2023.json"]["size_bytes"] = len(d_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="Daily batches missing coverage for canonical target symbols"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_tampered_top_20_selection_fails_closed(tmp_path: Path) -> None:
    fixture_dir = _build_synthetic_fixture(tmp_path)
    sel_file = fixture_dir / "top_20_selection_2024-01-02.json"
    sel_data = json.loads(sel_file.read_text(encoding="utf-8"))
    sel_data["selection_sha256"] = "1" * 64
    s_bytes = json.dumps(sel_data, indent=2).encode("utf-8")
    sel_file.write_bytes(s_bytes)

    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["top_20_selection_2024-01-02.json"]["sha256"] = hash_bytes(s_bytes)
    m_data["artifacts"]["top_20_selection_2024-01-02.json"]["size_bytes"] = len(s_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="Top-20 selection hash mismatch"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_tampered_universe_classification_fails_closed(tmp_path: Path) -> None:
    fixture_dir = _build_synthetic_fixture(tmp_path)
    univ_file = fixture_dir / "universe_2024-01-02.json"
    univ_data = json.loads(univ_file.read_text(encoding="utf-8"))
    univ_data["canonical_target_universe_count"] = 999
    u_bytes = json.dumps(univ_data, indent=2).encode("utf-8")
    univ_file.write_bytes(u_bytes)

    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["universe_2024-01-02.json"]["sha256"] = hash_bytes(u_bytes)
    m_data["artifacts"]["universe_2024-01-02.json"]["size_bytes"] = len(u_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="Universe count mismatch"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_stage_b_missing_1559_bar_reports_blocked_stage_b_price_path(tmp_path: Path) -> None:
    fixture_dir = _build_synthetic_fixture(tmp_path)
    sb_file = fixture_dir / "alpaca_stage_b_2024-01-02.json"
    sb_data = json.loads(sb_file.read_text(encoding="utf-8"))
    sb_data["batches"][0]["bars_by_symbol"]["AAA"] = [
        {"t": "2024-01-02T14:35:00Z", "o": 52.0, "h": 53.0, "l": 51.8, "c": 52.5, "v": 10000.0}
    ]
    sb_data["batches"][0]["meta"]["raw_pages"][0]["body"]["bars"]["AAA"] = [
        {"t": "2024-01-02T14:35:00Z", "o": 52.0, "h": 53.0, "l": 51.8, "c": 52.5, "v": 10000.0}
    ]
    sb_bytes = json.dumps(sb_data, indent=2).encode("utf-8")
    sb_file.write_bytes(sb_bytes)

    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["alpaca_stage_b_2024-01-02.json"]["sha256"] = hash_bytes(sb_bytes)
    m_data["artifacts"]["alpaca_stage_b_2024-01-02.json"]["size_bytes"] = len(sb_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    res = replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")
    assert not res.stage_b_audit.is_usable
    assert res.stage_b_audit.missing_eod_bar_symbols_count == 1
    assert res.disposition == PilotDisposition.BLOCKED_STAGE_B_PRICE_PATH


def test_validate_batch_size_guard() -> None:
    validate_batch_size(1)
    validate_batch_size(50)
    validate_batch_size(100)
    with pytest.raises(ValueError, match="Invalid batch size"):
        validate_batch_size(0)
    with pytest.raises(ValueError, match="Invalid batch size"):
        validate_batch_size(101)
    with pytest.raises(ValueError, match="Invalid batch size"):
        validate_batch_size(-10)


def test_one_shot_pilot_guard(tmp_path: Path) -> None:
    check_one_shot_pilot_guard(tmp_path, "2024-01-02")
    (tmp_path / "manifest_2024-01-02.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="One-shot pilot guard triggered"):
        check_one_shot_pilot_guard(tmp_path, "2024-01-02")


def test_resource_limits_guard() -> None:
    check_resource_limits(100, 1024)
    with pytest.raises(RuntimeError, match="Resource ceiling exceeded"):
        check_resource_limits(5001, 1024)
    with pytest.raises(RuntimeError, match="Storage ceiling exceeded"):
        check_resource_limits(100, 3 * 1024**3)


def test_pre_live_code_freeze_guard() -> None:
    with pytest.raises(RuntimeError, match="Pre-live freeze verification failed"):
        check_pre_live_code_freeze(REPO_ROOT, "0" * 40)


def test_pilot_authorization_guard(tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="Gary Yang has not granted live pilot authorization"):
        check_pilot_authorization(tmp_path, "fake_sha", authorized_by_gary=False)

    with pytest.raises(PermissionError, match="Missing Gary Yang authorization file"):
        check_pilot_authorization(tmp_path, "fake_sha", authorized_by_gary=True)

    auth_dir = tmp_path / "docs" / "research" / "authorizations"
    auth_dir.mkdir(parents=True)
    auth_file = auth_dir / "DAYTRADE-003D-CORR-003-AUTHORIZATION.json"
    auth_file.write_text(json.dumps({"authorized_by": "Not Gary"}), encoding="utf-8")

    with pytest.raises(PermissionError, match="Authorization record is not authorized by Gary Yang"):
        check_pilot_authorization(tmp_path, "fake_sha", authorized_by_gary=True)


# =============================================================================
# BLOCKER 1 REGRESSION TESTS: Two-Commit Freeze and Gary Yang Authorization
# =============================================================================


def test_two_commit_freeze_and_authorization_workflow(tmp_path: Path) -> None:
    """Demonstrate satisfiable two-commit workflow: freeze commit F, then authorization commit A."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)

    # Commit F: frozen code/specs
    (tmp_path / "tradex").mkdir(parents=True)
    (tmp_path / "tradex" / "foo.py").write_text("# audited code\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Freeze F"], cwd=tmp_path, check=True, capture_output=True)
    freeze_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    # Verify freeze guard passes on commit F itself
    check_pre_live_code_freeze(tmp_path, freeze_sha)

    # Commit A: Gary authorization record referencing F
    auth_dir = tmp_path / "docs" / "research" / "authorizations"
    auth_dir.mkdir(parents=True)
    auth_file = auth_dir / "DAYTRADE-003D-CORR-003-AUTHORIZATION.json"
    auth_file.write_text(
        json.dumps({
            "authorized_by": "Gary Yang",
            "task_id": TASK_ID,
            "pilot_date": PILOT_DATE,
            "frozen_implementation_sha": freeze_sha,
            "run_scope": "ONE_SHOT_PILOT_JAN_2_2024",
        }, indent=2),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Authorization A"], cwd=tmp_path, check=True, capture_output=True)
    auth_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    assert auth_sha != freeze_sha

    # Verify freeze guard passes on commit A referencing freeze SHA F
    check_pre_live_code_freeze(tmp_path, freeze_sha)
    # Verify pilot authorization guard passes on commit A
    check_pilot_authorization(tmp_path, freeze_sha, authorized_by_gary=True, pilot_date=PILOT_DATE)


def test_two_commit_freeze_code_drift_between_f_and_a_fails_closed(tmp_path: Path) -> None:
    """Fail closed if forbidden research code, spec, or test drift occurs between freeze F and authorization A."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "tradex").mkdir(parents=True)
    (tmp_path / "tradex" / "foo.py").write_text("# audited code\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Freeze F"], cwd=tmp_path, check=True, capture_output=True)
    freeze_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    # Commit A modifies tradex/foo.py (code drift!)
    (tmp_path / "tradex" / "foo.py").write_text("# code modification\n", encoding="utf-8")
    auth_dir = tmp_path / "docs" / "research" / "authorizations"
    auth_dir.mkdir(parents=True)
    auth_file = auth_dir / "DAYTRADE-003D-CORR-003-AUTHORIZATION.json"
    auth_file.write_text(
        json.dumps({
            "authorized_by": "Gary Yang",
            "task_id": TASK_ID,
            "pilot_date": PILOT_DATE,
            "frozen_implementation_sha": freeze_sha,
            "run_scope": "ONE_SHOT_PILOT_JAN_2_2024",
        }),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Authorization with drift"], cwd=tmp_path, check=True, capture_output=True)

    with pytest.raises(RuntimeError, match="forbidden code/spec/test drift between freeze"):
        check_pre_live_code_freeze(tmp_path, freeze_sha)


def test_two_commit_freeze_non_ancestor_fails_closed(tmp_path: Path) -> None:
    """Fail closed if current HEAD does not have the expected freeze commit as ancestor."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "tradex").mkdir(parents=True)
    (tmp_path / "tradex" / "foo.py").write_text("# code\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True, capture_output=True)
    sha1 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    # Create orphan branch
    subprocess.run(["git", "checkout", "--orphan", "orphan_branch"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "tradex" / "bar.py").write_text("# bar\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Orphan commit"], cwd=tmp_path, check=True, capture_output=True)

    with pytest.raises(RuntimeError, match="is not an ancestor of current HEAD"):
        check_pre_live_code_freeze(tmp_path, sha1)


def test_two_commit_freeze_dirty_worktree_fails_closed(tmp_path: Path) -> None:
    """Fail closed if working tree is dirty during freeze verification."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "tradex").mkdir(parents=True)
    (tmp_path / "tradex" / "foo.py").write_text("# code\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True, capture_output=True)
    sha1 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    (tmp_path / "dirty.txt").write_text("untracked\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="working tree is dirty"):
        check_pre_live_code_freeze(tmp_path, sha1)


def test_authorization_invalid_scope_and_fields_fail_closed(tmp_path: Path) -> None:
    """Fail closed if authorization record contains invalid run scope, task_id, or pilot date."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "tradex").mkdir(parents=True)
    (tmp_path / "tradex" / "foo.py").write_text("# code\n", encoding="utf-8")
    auth_dir = tmp_path / "docs" / "research" / "authorizations"
    auth_dir.mkdir(parents=True)
    auth_file = auth_dir / "DAYTRADE-003D-CORR-003-AUTHORIZATION.json"

    # 1. Invalid run scope
    auth_file.write_text(
        json.dumps({
            "authorized_by": "Gary Yang",
            "task_id": TASK_ID,
            "pilot_date": PILOT_DATE,
            "frozen_implementation_sha": "fake_sha",
            "run_scope": "FULL_2024_PILOT",
        }),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="Authorization record run_scope mismatch"):
        check_pilot_authorization(tmp_path, "fake_sha", authorized_by_gary=True)

    # 2. Invalid task_id
    auth_file.write_text(
        json.dumps({
            "authorized_by": "Gary Yang",
            "task_id": "WRONG-TASK",
            "pilot_date": PILOT_DATE,
            "frozen_implementation_sha": "fake_sha",
            "run_scope": "ONE_SHOT_PILOT_JAN_2_2024",
        }),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="Authorization record task_id mismatch"):
        check_pilot_authorization(tmp_path, "fake_sha", authorized_by_gary=True)

    # 3. Invalid pilot_date
    auth_file.write_text(
        json.dumps({
            "authorized_by": "Gary Yang",
            "task_id": TASK_ID,
            "pilot_date": "2024-01-03",
            "frozen_implementation_sha": "fake_sha",
            "run_scope": "ONE_SHOT_PILOT_JAN_2_2024",
        }),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="Authorization record pilot_date mismatch"):
        check_pilot_authorization(tmp_path, "fake_sha", authorized_by_gary=True)

    # 4. Untracked file in git repository
    auth_file.write_text(
        json.dumps({
            "authorized_by": "Gary Yang",
            "task_id": TASK_ID,
            "pilot_date": PILOT_DATE,
            "frozen_implementation_sha": "fake_sha",
            "run_scope": "ONE_SHOT_PILOT_JAN_2_2024",
        }),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="Authorization file is modified or untracked"):
        check_pilot_authorization(tmp_path, "fake_sha", authorized_by_gary=True)


# =============================================================================
# BLOCKER 2 REGRESSION TESTS: Raw Provider Payload Integrity & Parity
# =============================================================================


def test_alpaca_client_rejects_missing_bars_key() -> None:
    """DatasetAlpacaClient marks malformed payload when response dictionary lacks 'bars'."""
    def fake_request(*args: Any, **kwargs: Any) -> requests.Response:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({"data": []}).encode("utf-8")
        return resp

    client = DatasetAlpacaClient(api_key="k", secret_key="s", request_func=fake_request)
    _dfs, meta = client.get_bars(
        ["AAPL"],
        datetime(2024, 1, 2, 9, 30, tzinfo=ZoneInfo("UTC")),
        datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("UTC")),
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
    )
    assert meta["safe_error_classification"] == "malformed_page_payload"
    assert meta["pagination_complete"] is False


def test_alpaca_client_rejects_null_bars_symbol_entry() -> None:
    """DatasetAlpacaClient marks malformed payload when a symbol's bars entry is null."""
    def fake_request(*args: Any, **kwargs: Any) -> requests.Response:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({"bars": {"AAPL": None}}).encode("utf-8")
        return resp

    client = DatasetAlpacaClient(api_key="k", secret_key="s", request_func=fake_request)
    _dfs, meta = client.get_bars(
        ["AAPL"],
        datetime(2024, 1, 2, 9, 30, tzinfo=ZoneInfo("UTC")),
        datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("UTC")),
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
    )
    assert meta["safe_error_classification"] == "malformed_page_payload"
    assert meta["pagination_complete"] is False


def test_alpaca_client_rejects_non_list_bars_symbol_entry() -> None:
    """DatasetAlpacaClient marks malformed payload when a symbol's bars entry is a non-list string/int."""
    def fake_request(*args: Any, **kwargs: Any) -> requests.Response:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({"bars": {"AAPL": "corrupted_string"}}).encode("utf-8")
        return resp

    client = DatasetAlpacaClient(api_key="k", secret_key="s", request_func=fake_request)
    _dfs, meta = client.get_bars(
        ["AAPL"],
        datetime(2024, 1, 2, 9, 30, tzinfo=ZoneInfo("UTC")),
        datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("UTC")),
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
    )
    assert meta["safe_error_classification"] == "malformed_page_payload"
    assert meta["pagination_complete"] is False


def test_alpaca_client_rejects_non_dict_bar_object_in_list() -> None:
    """DatasetAlpacaClient marks malformed payload when a bar object inside the list is not a dictionary."""
    def fake_request(*args: Any, **kwargs: Any) -> requests.Response:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({"bars": {"AAPL": ["not_a_dict_bar"]}}).encode("utf-8")
        return resp

    client = DatasetAlpacaClient(api_key="k", secret_key="s", request_func=fake_request)
    _dfs, meta = client.get_bars(
        ["AAPL"],
        datetime(2024, 1, 2, 9, 30, tzinfo=ZoneInfo("UTC")),
        datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("UTC")),
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
    )
    assert meta["safe_error_classification"] == "malformed_page_payload"
    assert meta["pagination_complete"] is False


def test_alpaca_client_accepts_legitimate_empty_completed_response() -> None:
    """DatasetAlpacaClient treats legitimately empty symbol bar lists as completed pagination with safe_error='none'."""
    def fake_request(*args: Any, **kwargs: Any) -> requests.Response:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({"bars": {"AAPL": []}, "next_page_token": None}).encode("utf-8")
        return resp

    client = DatasetAlpacaClient(api_key="k", secret_key="s", request_func=fake_request)
    dfs, meta = client.get_bars(
        ["AAPL"],
        datetime(2024, 1, 2, 9, 30, tzinfo=ZoneInfo("UTC")),
        datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("UTC")),
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
    )
    assert meta["safe_error_classification"] == "none"
    assert meta["pagination_complete"] is True
    assert "AAPL" in dfs
    assert dfs["AAPL"].empty


def test_validator_rejects_malformed_raw_page_schema() -> None:
    """validate_provider_batch_response fails closed when raw page body violates schema."""
    batch_check_missing_bars = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        bars_by_symbol={"AAPL": []},
        meta={
            "http_status": 200,
            "pagination_complete": True,
            "raw_pages": [{"page_index": 0, "status_code": 200, "body": {"other": 123}}],
        },
    )
    assert not batch_check_missing_bars.is_valid
    assert batch_check_missing_bars.status == PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD

    batch_check_null_bars = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        bars_by_symbol={"AAPL": []},
        meta={
            "http_status": 200,
            "pagination_complete": True,
            "raw_pages": [{"page_index": 0, "status_code": 200, "body": {"bars": {"AAPL": None}}}],
        },
    )
    assert not batch_check_null_bars.is_valid
    assert batch_check_null_bars.status == PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD


def test_validator_rejects_raw_pages_to_aggregate_disagreement() -> None:
    """validate_provider_batch_response fails closed if raw pages bars do not match aggregated bars_by_symbol."""
    bar1 = {"t": "2024-01-02T14:30:00Z", "o": 10.0, "h": 11.0, "l": 9.0, "c": 10.5, "v": 1000.0}
    bar2 = {"t": "2024-01-02T14:31:00Z", "o": 10.5, "h": 11.2, "l": 10.1, "c": 11.0, "v": 2000.0}
    batch_check = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        bars_by_symbol={"AAPL": [bar1]},
        meta={
            "http_status": 200,
            "pagination_complete": True,
            "raw_pages": [{"page_index": 0, "status_code": 200, "body": {"bars": {"AAPL": [bar1, bar2]}}}],
        },
    )
    assert not batch_check.is_valid
    assert batch_check.status == PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD


# =============================================================================
# BLOCKER 3 REGRESSION TESTS: Actual Request Provenance & PIT Parameters
# =============================================================================


def test_replay_rejects_string_valued_rogue_symbol_parameter(tmp_path: Path) -> None:
    """Replay rejects realistic comma-separated string-valued symbol parameter containing rogue symbols."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    or_file = fixture_dir / "alpaca_current_or_2024-01-02.json"
    or_data = json.loads(or_file.read_text(encoding="utf-8"))
    or_data["batches"][0]["request_params"]["symbols"] = "AAA,ROGUE"
    or_bytes = json.dumps(or_data, indent=2).encode("utf-8")
    or_file.write_bytes(or_bytes)

    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["sha256"] = hash_bytes(or_bytes)
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["size_bytes"] = len(or_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="Contradictory request parameters: request_params symbols"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_replay_rejects_bad_feed_and_timeframe(tmp_path: Path) -> None:
    """Replay rejects contradictory feed or timeframe request parameters."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    or_file = fixture_dir / "alpaca_current_or_2024-01-02.json"
    or_data = json.loads(or_file.read_text(encoding="utf-8"))

    # Contradictory feed
    or_data["batches"][0]["request_params"]["feed"] = "iex"
    or_bytes = json.dumps(or_data, indent=2).encode("utf-8")
    or_file.write_bytes(or_bytes)
    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["sha256"] = hash_bytes(or_bytes)
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["size_bytes"] = len(or_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="Contradictory request feed: expected 'sip', got 'iex'"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")

    # Contradictory timeframe
    or_data["batches"][0]["request_params"]["feed"] = "sip"
    or_data["batches"][0]["request_params"]["timeframe"] = "5Min"
    or_bytes = json.dumps(or_data, indent=2).encode("utf-8")
    or_file.write_bytes(or_bytes)
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["sha256"] = hash_bytes(or_bytes)
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["size_bytes"] = len(or_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="Contradictory request timeframe: expected '1Min', got '5Min'"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_replay_rejects_bad_asof_and_pit_window(tmp_path: Path) -> None:
    """Replay rejects contradictory asof date or PIT query window."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    or_file = fixture_dir / "alpaca_current_or_2024-01-02.json"
    or_data = json.loads(or_file.read_text(encoding="utf-8"))

    or_data["batches"][0]["request_params"]["asof"] = "2024-01-03"
    or_bytes = json.dumps(or_data, indent=2).encode("utf-8")
    or_file.write_bytes(or_bytes)
    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["sha256"] = hash_bytes(or_bytes)
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["size_bytes"] = len(or_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="Contradictory request asof: expected '2024-01-02', got '2024-01-03'"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_replay_rejects_token_sequence_mismatch(tmp_path: Path) -> None:
    """Replay fails closed if token_sequence_sha256 does not match recomputed token sequence hash."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    or_file = fixture_dir / "alpaca_current_or_2024-01-02.json"
    or_data = json.loads(or_file.read_text(encoding="utf-8"))

    or_data["batches"][0]["meta"]["token_sequence_sha256"] = "9" * 64
    or_bytes = json.dumps(or_data, indent=2).encode("utf-8")
    or_file.write_bytes(or_bytes)
    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["sha256"] = hash_bytes(or_bytes)
    m_data["artifacts"]["alpaca_current_or_2024-01-02.json"]["size_bytes"] = len(or_bytes)
    m_path.write_text(json.dumps(m_data, indent=2), encoding="utf-8")

    with pytest.raises(ReplayIntegrityError, match="Token sequence hash mismatch"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_mocked_acquisition_to_replay_integration(tmp_path: Path) -> None:
    """End-to-end integration proving acquisition via DatasetAlpacaClient feeds replay successfully."""
    pilot_date = "2024-01-02"
    artifacts: dict[str, Any] = {}

    # 1. Massive reference snapshot (2 symbols: AAA, BBB)
    ref_rows = [
        {"ticker": "AAA", "primary_exchange": "XNYS", "type": "CS", "active": True},
        {"ticker": "BBB", "primary_exchange": "XNAS", "type": "CS", "active": True},
    ]
    ref_file = f"massive_reference_{pilot_date}.json"
    ref_bytes = json.dumps(ref_rows, indent=2).encode("utf-8")
    (tmp_path / ref_file).write_bytes(ref_bytes)
    artifacts[ref_file] = {
        "sha256": hash_bytes(ref_bytes),
        "size_bytes": len(ref_bytes),
        "description": "Massive reference snapshot",
        "record_count": len(ref_rows),
    }

    target_audit, _ = filter_and_audit_target_universe(ref_rows)
    univ_file = f"universe_{pilot_date}.json"
    univ_bytes = json.dumps({
        "date": pilot_date,
        "canonical_target_universe_count": target_audit.canonical_target_universe_count,
        "valid_symbols_count": len(target_audit.valid_target_symbols),
        "ambiguous_symbols_count": len(target_audit.ambiguous_symbols),
        "universe_sha256": target_audit.universe_sha256,
        "valid_symbols": target_audit.valid_target_symbols,
        "ambiguous_symbols": target_audit.ambiguous_symbols,
    }, indent=2).encode("utf-8")
    (tmp_path / univ_file).write_bytes(univ_bytes)
    artifacts[univ_file] = {
        "sha256": hash_bytes(univ_bytes),
        "size_bytes": len(univ_bytes),
        "description": "Universe summary",
        "record_count": 2,
    }

    daily_dates = [s.isoformat() for s in get_prior_xnys_sessions(date(2024, 1, 2), 20)]
    daily_bars_aaa = [
        {"t": f"{d}T05:00:00Z", "o": 50.0, "h": 52.0, "l": 49.0, "c": 51.0, "v": 2_000_000.0}
        for d in daily_dates
    ]
    daily_bars_bbb = [
        {"t": f"{d}T05:00:00Z", "o": 30.0, "h": 32.0, "l": 29.0, "c": 31.0, "v": 1_500_000.0}
        for d in daily_dates
    ]
    or_bars_aaa = [
        {"t": "2024-01-02T14:30:00Z", "o": 51.0, "h": 51.5, "l": 50.8, "c": 51.2, "v": 25000.0},
        {"t": "2024-01-02T14:34:00Z", "o": 51.2, "h": 52.0, "l": 51.0, "c": 52.0, "v": 25000.0},
    ]
    or_bars_bbb = [
        {"t": "2024-01-02T14:30:00Z", "o": 4.0, "h": 4.2, "l": 3.9, "c": 4.1, "v": 10000.0},
    ]
    prior_sessions = get_prior_xnys_sessions(date(2024, 1, 2), 14)
    prior_bars_by_date = {
        s.isoformat(): [
            {"t": f"{s.isoformat()}T14:30:00Z", "o": 50.0, "h": 50.5, "l": 49.8, "c": 50.2, "v": 30000.0}
        ]
        for s in prior_sessions
    }
    sb_bars_aaa = [
        {"t": "2024-01-02T14:35:00Z", "o": 52.0, "h": 53.0, "l": 51.8, "c": 52.5, "v": 10000.0},
        {"t": "2024-01-02T20:59:00Z", "o": 52.8, "h": 53.0, "l": 52.5, "c": 52.9, "v": 15000.0},
    ]

    def mock_request(url: str, params: dict[str, Any] | None = None, **kwargs: Any) -> requests.Response:
        resp = requests.Response()
        resp.status_code = 200
        p = params or {}
        tf = p.get("timeframe")
        start = str(p.get("start", ""))
        if tf == "1Day":
            body = {"bars": {"AAA": daily_bars_aaa, "BBB": daily_bars_bbb}, "next_page_token": None}
        elif tf == "1Min" and ("09:35" in start or "14:35" in start):
            body = {"bars": {"AAA": sb_bars_aaa}, "next_page_token": None}
        elif tf == "1Min" and "2024-01-02" in start:
            body = {"bars": {"AAA": or_bars_aaa, "BBB": or_bars_bbb}, "next_page_token": None}
        else:
            s_date = start[:10]
            p_bars = prior_bars_by_date.get(s_date, [])
            body = {"bars": {"AAA": p_bars, "BBB": []}, "next_page_token": None}
        resp._content = json.dumps(body).encode("utf-8")
        return resp

    client = DatasetAlpacaClient(api_key="mock_k", secret_key="mock_s", request_func=mock_request)

    # 1. Phase 2 acquisition
    _dfs, d_meta = client.get_bars(
        ["AAA", "BBB"],
        datetime(2023, 12, 1, 0, 0, tzinfo=ZoneInfo("UTC")),
        datetime(2023, 12, 29, 23, 59, tzinfo=ZoneInfo("UTC")),
        feed="sip",
        timeframe="1Day",
        adjustment="raw",
        asof=pilot_date,
        include_raw_bars=True,
        include_raw_pages=True,
    )
    daily_file = "alpaca_daily_dec2023.json"
    daily_hash, daily_size = persist_raw_stage_artifact(
        tmp_path / daily_file,
        metadata={"stage": "phase_2_broad_daily"},
        batches=[{
            "batch_index": 1,
            "symbols_requested": ["AAA", "BBB"],
            "request_params": d_meta.get("request_params", {}),
            "http_status": d_meta.get("http_status", 200),
            "pagination_complete": d_meta.get("pagination_complete", True),
            "page_count": d_meta.get("page_count", 1),
            "token_hashes": d_meta.get("token_hashes", []),
            "token_sequence_sha256": d_meta.get("token_sequence_sha256", ""),
            "meta": d_meta,
            "bars_by_symbol": d_meta.get("raw_bars_by_symbol", {}),
        }],
    )
    artifacts[daily_file] = {
        "sha256": daily_hash,
        "size_bytes": daily_size,
        "description": "Daily bars",
        "record_count": 2,
    }

    # 2. Phase 3 current OR acquisition
    cur_start = datetime(2024, 1, 2, 9, 30, tzinfo=NY_TZ).astimezone(ZoneInfo("UTC"))
    cur_end = datetime(2024, 1, 2, 9, 34, 59, tzinfo=NY_TZ).astimezone(ZoneInfo("UTC"))
    _dfs, cur_meta = client.get_bars(
        ["AAA", "BBB"],
        cur_start,
        cur_end,
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
        asof=pilot_date,
        include_raw_bars=True,
        include_raw_pages=True,
    )
    cur_file = f"alpaca_current_or_{pilot_date}.json"
    cur_hash, cur_size = persist_raw_stage_artifact(
        tmp_path / cur_file,
        metadata={"stage": "phase_3_current_opening_range"},
        batches=[{
            "batch_index": 1,
            "symbols_requested": ["AAA", "BBB"],
            "request_params": cur_meta.get("request_params", {}),
            "http_status": cur_meta.get("http_status", 200),
            "pagination_complete": cur_meta.get("pagination_complete", True),
            "page_count": cur_meta.get("page_count", 1),
            "token_hashes": cur_meta.get("token_hashes", []),
            "token_sequence_sha256": cur_meta.get("token_sequence_sha256", ""),
            "meta": cur_meta,
            "bars_by_symbol": cur_meta.get("raw_bars_by_symbol", {}),
        }],
    )
    artifacts[cur_file] = {
        "sha256": cur_hash,
        "size_bytes": cur_size,
        "description": "Current OR bars",
        "record_count": 2,
    }

    # 3. Phase 3 prior 14 sessions acquisition
    prior_sessions_data: dict[str, list[dict[str, Any]]] = {}
    for s_idx, sess in enumerate(prior_sessions, start=1):
        s_date = sess.isoformat()
        s_start = datetime(sess.year, sess.month, sess.day, 9, 30, tzinfo=NY_TZ).astimezone(ZoneInfo("UTC"))
        s_end = datetime(sess.year, sess.month, sess.day, 9, 34, 59, tzinfo=NY_TZ).astimezone(ZoneInfo("UTC"))
        _dfs, p_meta = client.get_bars(
            ["AAA", "BBB"],
            s_start,
            s_end,
            feed="sip",
            timeframe="1Min",
            adjustment="raw",
            asof=pilot_date,
            include_raw_bars=True,
            include_raw_pages=True,
        )
        prior_sessions_data[s_date] = [{
            "session_index": s_idx,
            "session_date": s_date,
            "batch_index": 1,
            "symbols_requested": ["AAA", "BBB"],
            "request_params": p_meta.get("request_params", {}),
            "http_status": p_meta.get("http_status", 200),
            "pagination_complete": p_meta.get("pagination_complete", True),
            "page_count": p_meta.get("page_count", 1),
            "token_hashes": p_meta.get("token_hashes", []),
            "token_sequence_sha256": p_meta.get("token_sequence_sha256", ""),
            "meta": p_meta,
            "bars_by_symbol": p_meta.get("raw_bars_by_symbol", {}),
        }]
    prior_file = f"alpaca_prior_or_14sessions_{pilot_date}.json"
    prior_bytes = json.dumps({
        "metadata": {"stage": "phase_3_prior_14_sessions_opening_range"},
        "sessions_data": prior_sessions_data,
    }, indent=2).encode("utf-8")
    (tmp_path / prior_file).write_bytes(prior_bytes)
    artifacts[prior_file] = {
        "sha256": hash_bytes(prior_bytes),
        "size_bytes": len(prior_bytes),
        "description": "Prior 14 sessions OR bars",
        "record_count": len(prior_sessions_data),
    }

    # 4. Top-20 selection
    d_obj = {
        sym: sorted([
            DailyBar(
                symbol=sym,
                session_date=datetime.fromisoformat(b["t"]).date(),
                open=b["o"],
                high=b["h"],
                low=b["l"],
                close=b["c"],
                volume=b["v"],
            )
            for b in (daily_bars_aaa if sym == "AAA" else daily_bars_bbb)
        ], key=lambda x: x.session_date)
        for sym in ["AAA", "BBB"]
    }
    _d_audit, _comp, d_qual = audit_broad_daily_availability(target_audit.valid_target_symbols, [], d_obj, date(2024, 1, 2))
    cur_ors = {
        "AAA": evaluate_opening_range([
            MinuteBar("AAA", datetime.fromisoformat(b["t"]), date(2024, 1, 2), b["o"], b["h"], b["l"], b["c"], b["v"])
            for b in or_bars_aaa
        ], require_five_bars=False),
        "BBB": evaluate_opening_range([
            MinuteBar("BBB", datetime.fromisoformat(b["t"]), date(2024, 1, 2), b["o"], b["h"], b["l"], b["c"], b["v"])
            for b in or_bars_bbb
        ], require_five_bars=False),
    }
    prior_obs = {
        "AAA": [
            OpeningRangeVolumeObservation("AAA", date.fromisoformat(ps), 30000.0)
            for ps in [s.isoformat() for s in prior_sessions]
        ]
    }
    _s_audit, _outcomes, elig, surv_ors = audit_candidate_screening(
        d_qual, cur_ors, set(), prior_obs, set(), d_obj, date(2024, 1, 2)
    )
    ranked = rank_and_select_top_20(elig, surv_ors, 25000.0, 20)
    sel_ev, sel_records, _ = freeze_top_20_selection(ranked)

    sel_file = f"top_20_selection_{pilot_date}.json"
    sel_bytes = json.dumps({
        "date": pilot_date,
        "selection_sha256": sel_ev.selection_sha256,
        "selected_count": sel_ev.selected_count,
        "doji_count": sel_ev.doji_count,
        "eligible_candidates_count": sel_ev.eligible_candidates_count,
        "records": sel_records,
    }, indent=2).encode("utf-8")
    (tmp_path / sel_file).write_bytes(sel_bytes)
    artifacts[sel_file] = {
        "sha256": hash_bytes(sel_bytes),
        "size_bytes": len(sel_bytes),
        "description": "Top-20 selection",
        "record_count": len(sel_records),
    }

    # 5. Phase 5 Stage B acquisition
    sb_start = datetime(2024, 1, 2, 9, 35, tzinfo=NY_TZ).astimezone(ZoneInfo("UTC"))
    sb_end = datetime(2024, 1, 2, 15, 59, 59, tzinfo=NY_TZ).astimezone(ZoneInfo("UTC"))
    _dfs, sb_meta = client.get_bars(
        ["AAA"],
        sb_start,
        sb_end,
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
        asof=pilot_date,
        include_raw_bars=True,
        include_raw_pages=True,
    )
    sb_file = f"alpaca_stage_b_{pilot_date}.json"
    sb_hash, sb_size = persist_raw_stage_artifact(
        tmp_path / sb_file,
        metadata={"stage": "phase_5_stage_b_price_path"},
        batches=[{
            "batch_index": 1,
            "symbols_requested": ["AAA"],
            "request_params": sb_meta.get("request_params", {}),
            "http_status": sb_meta.get("http_status", 200),
            "pagination_complete": sb_meta.get("pagination_complete", True),
            "page_count": sb_meta.get("page_count", 1),
            "token_hashes": sb_meta.get("token_hashes", []),
            "token_sequence_sha256": sb_meta.get("token_sequence_sha256", ""),
            "meta": sb_meta,
            "bars_by_symbol": sb_meta.get("raw_bars_by_symbol", {}),
        }],
    )
    artifacts[sb_file] = {
        "sha256": sb_hash,
        "size_bytes": sb_size,
        "description": "Stage-B bars",
        "record_count": 1,
    }

    # Manifest
    create_and_save_manifest(
        output_dir=tmp_path,
        artifacts_info=artifacts,
        pilot_date=pilot_date,
    )

    # Replay
    res = replay_corr_003_pilot(input_dir=tmp_path, repo_root=REPO_ROOT, pilot_date=pilot_date)
    assert res.disposition == PilotDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD
    assert res.stage_b_audit.is_usable is True


# =============================================================================
# BLOCKER 4 REGRESSION TESTS: Prospective Resource Ceilings & One-Shot Guard
# =============================================================================


def test_one_shot_guard_rejects_interrupted_run_with_lock_marker(tmp_path: Path) -> None:
    """One-shot guard rejects execution if a durable lock marker from a prior or interrupted run exists."""
    lock_file = tmp_path / ".pilot_run_lock_2024-01-02.json"
    lock_file.write_text(json.dumps({"started_at": "2026-10-12T12:00:00Z"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="run lock marker exists"):
        check_one_shot_pilot_guard(tmp_path, "2024-01-02")


def test_one_shot_guard_rejects_partial_artifacts_without_manifest(tmp_path: Path) -> None:
    """One-shot guard rejects execution if partial artifacts exist in output directory without a manifest."""
    partial_file = tmp_path / "alpaca_daily_dec2023.json"
    partial_file.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="found 1 existing artifacts"):
        check_one_shot_pilot_guard(tmp_path, "2024-01-02")


def test_one_shot_guard_allows_clean_directory(tmp_path: Path) -> None:
    """One-shot guard permits execution in a completely clean directory."""
    check_one_shot_pilot_guard(tmp_path, "2024-01-02")


def test_prospective_resource_limit_checks() -> None:
    """Strict resource ceiling checks prospectively enforce 5,000 pages and 2 GiB storage."""
    # Under limit passes
    check_resource_limits(5000, 2 * 1024**3)
    # Exceeding page ceiling raises
    with pytest.raises(RuntimeError, match="Resource ceiling exceeded"):
        check_resource_limits(5001, 1024)
    # Exceeding storage ceiling raises
    with pytest.raises(RuntimeError, match="Storage ceiling exceeded"):
        check_resource_limits(100, (2 * 1024**3) + 1)


def test_prospective_budget_exhaustion_in_client() -> None:
    """DatasetAlpacaClient respects max_pages and stops before requesting beyond the prospective limit."""
    call_count = 0

    def fake_request(*args: Any, **kwargs: Any) -> requests.Response:
        nonlocal call_count
        call_count += 1
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({
            "bars": {"AAPL": [{"t": "2024-01-02T14:30:00Z", "o": 10.0, "h": 10.5, "l": 9.8, "c": 10.2, "v": 1000.0}]},
            "next_page_token": "token_page_2",
        }).encode("utf-8")
        return resp

    client = DatasetAlpacaClient(api_key="k", secret_key="s", request_func=fake_request)
    _dfs, meta = client.get_bars(
        ["AAPL"],
        datetime(2024, 1, 2, 9, 30, tzinfo=ZoneInfo("UTC")),
        datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("UTC")),
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
        max_pages=1,
    )
    assert call_count == 1
    assert meta["safe_error_classification"] == "max_pages_exceeded"
    assert meta["terminal_next_page_token"] == "token_page_2"
    assert meta["pagination_complete"] is False


# =============================================================================
# BLOCKER 1 & 2 REGRESSION TESTS: Durable Run Lock in Replay & Atomic One-Shot Guard
# =============================================================================


def test_manifest_verifies_durable_run_lock_marker(tmp_path: Path) -> None:
    """Replay manifest verification accepts and validates a durable run lock marker listed in the manifest."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    lock_marker = fixture_dir / ".pilot_run_lock_2024-01-02.json"
    lock_payload = {
        "task_id": TASK_ID,
        "pilot_date": "2024-01-02",
        "pre_live_commit_sha": "a" * 40,
        "status": "IN_PROGRESS",
        "initiated_at_utc": "2024-01-02T14:00:00Z",
    }
    lock_bytes = json.dumps(lock_payload, indent=2).encode("utf-8")
    lock_marker.write_bytes(lock_bytes)

    # Add lock marker to manifest
    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"][lock_marker.name] = {
        "sha256": hash_bytes(lock_bytes),
        "size_bytes": len(lock_bytes),
        "description": "Durable pilot run lock marker",
        "record_count": 1,
    }
    m_path.write_bytes(json.dumps(m_data, indent=2).encode("utf-8"))

    ok, _, errors = verify_replay_manifest(fixture_dir, "2024-01-02")
    assert ok, f"Expected manifest verification to pass, got errors: {errors}"
    assert len(errors) == 0


def test_manifest_rejects_unlisted_run_lock_marker(tmp_path: Path) -> None:
    """An unlisted run lock marker on disk fails closed as an unlisted extra file in replay."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    lock_marker = fixture_dir / ".pilot_run_lock_2024-01-02.json"
    lock_marker.write_text(json.dumps({"status": "IN_PROGRESS"}), encoding="utf-8")

    ok, _, errors = verify_replay_manifest(fixture_dir, "2024-01-02")
    assert not ok
    assert any("Unlisted extra file detected in replay directory: .pilot_run_lock_2024-01-02.json" in e for e in errors)


def test_manifest_rejects_corrupted_run_lock_marker(tmp_path: Path) -> None:
    """A listed run lock marker with corrupted metadata fails closed during manifest verification."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    lock_marker = fixture_dir / ".pilot_run_lock_2024-01-02.json"
    corrupt_payload = {
        "task_id": "WRONG_TASK",
        "pilot_date": "2024-01-02",
        "pre_live_commit_sha": "bad_sha",
        "status": "INVALID_STATUS",
        "initiated_at_utc": "",
    }
    lock_bytes = json.dumps(corrupt_payload, indent=2).encode("utf-8")
    lock_marker.write_bytes(lock_bytes)

    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"][lock_marker.name] = {
        "sha256": hash_bytes(lock_bytes),
        "size_bytes": len(lock_bytes),
        "description": "Durable pilot run lock marker",
        "record_count": 1,
    }
    m_path.write_bytes(json.dumps(m_data, indent=2).encode("utf-8"))

    ok, _, errors = verify_replay_manifest(fixture_dir, "2024-01-02")
    assert not ok
    assert any("Run lock task_id mismatch" in e for e in errors)


def test_acquire_atomic_pilot_run_lock_concurrent_race(tmp_path: Path) -> None:
    """Atomic one-shot lock acquisition prevents race condition: exactly 1 process succeeds."""
    output_dir = tmp_path / "race_test"
    pilot_date = "2024-01-02"
    pre_live_sha = "1" * 40

    def try_acquire(worker_id: int) -> tuple[bool, str]:
        try:
            acquire_atomic_pilot_run_lock(output_dir, pilot_date, pre_live_sha)
            return (True, f"worker_{worker_id}")
        except RuntimeError as exc:
            return (False, str(exc))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(try_acquire, i) for i in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    successes = [r for r in results if r[0]]
    failures = [r for r in results if not r[0]]

    assert len(successes) == 1, f"Expected exactly 1 acquisition success, got {len(successes)}"
    assert len(failures) == 9, f"Expected exactly 9 collision failures, got {len(failures)}"
    for _, err_msg in failures:
        assert "already exists" in err_msg or "run lock marker exists" in err_msg

    # Verify lock file on disk is valid and uncorrupted
    lock_file = output_dir / f".pilot_run_lock_{pilot_date}.json"
    assert lock_file.exists()
    lock_data = json.loads(lock_file.read_text(encoding="utf-8"))
    assert lock_data["task_id"] == TASK_ID
    assert lock_data["status"] == "IN_PROGRESS"


def test_full_producer_layout_to_replay_integration(tmp_path: Path) -> None:
    """Simulated actual producer storage layout with atomic lock and manifest successfully feeds offline replay."""
    pilot_date = "2024-01-02"
    output_dir = tmp_path / "producer_output"
    output_dir.mkdir(parents=True)

    # 1. Producer acquires atomic run lock
    acquire_atomic_pilot_run_lock(output_dir, pilot_date, "b" * 40)

    # 2. Build artifacts in producer layout
    artifacts: dict[str, Any] = {}

    # Lock marker added to manifest
    lock_marker = output_dir / f".pilot_run_lock_{pilot_date}.json"
    lock_bytes = lock_marker.read_bytes()
    artifacts[lock_marker.name] = {
        "sha256": hash_bytes(lock_bytes),
        "size_bytes": len(lock_bytes),
        "description": "Durable atomic pilot run lock marker",
        "record_count": 1,
    }

    ref_rows = [
        {"ticker": "AAA", "primary_exchange": "XNYS", "type": "CS", "active": True},
        {"ticker": "BBB", "primary_exchange": "XNAS", "type": "CS", "active": True},
    ]
    ref_file = f"massive_reference_{pilot_date}.json"
    ref_bytes = json.dumps(ref_rows, indent=2).encode("utf-8")
    (output_dir / ref_file).write_bytes(ref_bytes)
    artifacts[ref_file] = {
        "sha256": hash_bytes(ref_bytes),
        "size_bytes": len(ref_bytes),
        "description": "Massive reference snapshot",
        "record_count": len(ref_rows),
    }

    target_audit, _ = filter_and_audit_target_universe(ref_rows)
    univ_file = f"universe_{pilot_date}.json"
    univ_bytes = json.dumps({
        "date": pilot_date,
        "canonical_target_universe_count": target_audit.canonical_target_universe_count,
        "valid_symbols_count": len(target_audit.valid_target_symbols),
        "ambiguous_symbols_count": len(target_audit.ambiguous_symbols),
        "universe_sha256": target_audit.universe_sha256,
        "valid_symbols": target_audit.valid_target_symbols,
        "ambiguous_symbols": target_audit.ambiguous_symbols,
    }, indent=2).encode("utf-8")
    (output_dir / univ_file).write_bytes(univ_bytes)
    artifacts[univ_file] = {
        "sha256": hash_bytes(univ_bytes),
        "size_bytes": len(univ_bytes),
        "description": "Universe summary",
        "record_count": 2,
    }

    daily_dates = [s.isoformat() for s in get_prior_xnys_sessions(date(2024, 1, 2), 20)]
    daily_bars_aaa = [
        {"t": f"{d}T05:00:00Z", "o": 50.0, "h": 52.0, "l": 49.0, "c": 51.0, "v": 2_000_000.0}
        for d in daily_dates
    ]
    daily_bars_bbb = [
        {"t": f"{d}T05:00:00Z", "o": 30.0, "h": 32.0, "l": 29.0, "c": 31.0, "v": 1_500_000.0}
        for d in daily_dates
    ]
    or_bars_aaa = [
        {"t": "2024-01-02T14:30:00Z", "o": 51.0, "h": 51.5, "l": 50.8, "c": 51.2, "v": 25000.0},
        {"t": "2024-01-02T14:34:00Z", "o": 51.2, "h": 52.0, "l": 51.0, "c": 52.0, "v": 25000.0},
    ]
    or_bars_bbb = [
        {"t": "2024-01-02T14:30:00Z", "o": 4.0, "h": 4.2, "l": 3.9, "c": 4.1, "v": 10000.0},
    ]
    prior_sessions = get_prior_xnys_sessions(date(2024, 1, 2), 14)
    prior_bars_by_date = {
        s.isoformat(): [
            {"t": f"{s.isoformat()}T14:30:00Z", "o": 50.0, "h": 50.5, "l": 49.8, "c": 50.2, "v": 30000.0}
        ]
        for s in prior_sessions
    }
    sb_bars_aaa = [
        {"t": "2024-01-02T14:35:00Z", "o": 52.0, "h": 53.0, "l": 51.8, "c": 52.5, "v": 10000.0},
        {"t": "2024-01-02T20:59:00Z", "o": 52.8, "h": 53.0, "l": 52.5, "c": 52.9, "v": 15000.0},
    ]

    def mock_request(url: str, params: dict[str, Any] | None = None, **kwargs: Any) -> requests.Response:
        resp = requests.Response()
        resp.status_code = 200
        p = params or {}
        tf = p.get("timeframe")
        start = str(p.get("start", ""))
        if tf == "1Day":
            body = {"bars": {"AAA": daily_bars_aaa, "BBB": daily_bars_bbb}, "next_page_token": None}
        elif tf == "1Min" and ("09:35" in start or "14:35" in start):
            body = {"bars": {"AAA": sb_bars_aaa}, "next_page_token": None}
        elif tf == "1Min" and "2024-01-02" in start:
            body = {"bars": {"AAA": or_bars_aaa, "BBB": or_bars_bbb}, "next_page_token": None}
        else:
            s_date = start[:10]
            p_bars = prior_bars_by_date.get(s_date, [])
            body = {"bars": {"AAA": p_bars, "BBB": []}, "next_page_token": None}
        resp._content = json.dumps(body).encode("utf-8")
        return resp

    client = DatasetAlpacaClient(api_key="mock_k", secret_key="mock_s", request_func=mock_request)

    # Phase 2
    _dfs, d_meta = client.get_bars(
        ["AAA", "BBB"],
        datetime(2023, 12, 1, 0, 0, tzinfo=ZoneInfo("UTC")),
        datetime(2023, 12, 29, 23, 59, tzinfo=ZoneInfo("UTC")),
        feed="sip",
        timeframe="1Day",
        adjustment="raw",
        asof=pilot_date,
        include_raw_bars=True,
        include_raw_pages=True,
    )
    daily_file = "alpaca_daily_dec2023.json"
    daily_hash, daily_size = persist_raw_stage_artifact(
        output_dir / daily_file,
        metadata={"stage": "phase_2_broad_daily"},
        batches=[{
            "batch_index": 1,
            "symbols_requested": ["AAA", "BBB"],
            "request_params": d_meta.get("request_params", {}),
            "http_status": d_meta.get("http_status", 200),
            "pagination_complete": d_meta.get("pagination_complete", True),
            "page_count": d_meta.get("page_count", 1),
            "token_hashes": d_meta.get("token_hashes", []),
            "token_sequence_sha256": d_meta.get("token_sequence_sha256", ""),
            "meta": d_meta,
            "bars_by_symbol": d_meta.get("raw_bars_by_symbol", {}),
        }],
    )
    artifacts[daily_file] = {
        "sha256": daily_hash,
        "size_bytes": daily_size,
        "description": "Daily bars",
        "record_count": 2,
    }

    # Phase 3 Current OR
    cur_start = datetime(2024, 1, 2, 9, 30, tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
    cur_end = datetime(2024, 1, 2, 9, 34, 59, tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
    _dfs, cur_meta = client.get_bars(
        ["AAA", "BBB"],
        cur_start,
        cur_end,
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
        asof=pilot_date,
        include_raw_bars=True,
        include_raw_pages=True,
    )
    cur_file = f"alpaca_current_or_{pilot_date}.json"
    cur_hash, cur_size = persist_raw_stage_artifact(
        output_dir / cur_file,
        metadata={"stage": "phase_3_current_opening_range"},
        batches=[{
            "batch_index": 1,
            "symbols_requested": ["AAA", "BBB"],
            "request_params": cur_meta.get("request_params", {}),
            "http_status": cur_meta.get("http_status", 200),
            "pagination_complete": cur_meta.get("pagination_complete", True),
            "page_count": cur_meta.get("page_count", 1),
            "token_hashes": cur_meta.get("token_hashes", []),
            "token_sequence_sha256": cur_meta.get("token_sequence_sha256", ""),
            "meta": cur_meta,
            "bars_by_symbol": cur_meta.get("raw_bars_by_symbol", {}),
        }],
    )
    artifacts[cur_file] = {
        "sha256": cur_hash,
        "size_bytes": cur_size,
        "description": "Current OR bars",
        "record_count": 2,
    }

    # Phase 3 Prior 14 Sessions
    prior_sessions_data: dict[str, list[dict[str, Any]]] = {}
    for s_idx, sess in enumerate(prior_sessions, start=1):
        s_date = sess.isoformat()
        s_start = datetime(sess.year, sess.month, sess.day, 9, 30, tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
        s_end = datetime(sess.year, sess.month, sess.day, 9, 34, 59, tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
        _dfs, p_meta = client.get_bars(
            ["AAA", "BBB"],
            s_start,
            s_end,
            feed="sip",
            timeframe="1Min",
            adjustment="raw",
            asof=pilot_date,
            include_raw_bars=True,
            include_raw_pages=True,
        )
        prior_sessions_data[s_date] = [{
            "session_index": s_idx,
            "session_date": s_date,
            "batch_index": 1,
            "symbols_requested": ["AAA", "BBB"],
            "request_params": p_meta.get("request_params", {}),
            "http_status": p_meta.get("http_status", 200),
            "pagination_complete": p_meta.get("pagination_complete", True),
            "page_count": p_meta.get("page_count", 1),
            "token_hashes": p_meta.get("token_hashes", []),
            "token_sequence_sha256": p_meta.get("token_sequence_sha256", ""),
            "meta": p_meta,
            "bars_by_symbol": p_meta.get("raw_bars_by_symbol", {}),
        }]
    prior_file = f"alpaca_prior_or_14sessions_{pilot_date}.json"
    prior_bytes = json.dumps({
        "metadata": {"stage": "phase_3_prior_14_sessions_opening_range"},
        "sessions_data": prior_sessions_data,
    }, indent=2).encode("utf-8")
    (output_dir / prior_file).write_bytes(prior_bytes)
    artifacts[prior_file] = {
        "sha256": hash_bytes(prior_bytes),
        "size_bytes": len(prior_bytes),
        "description": "Prior 14 sessions OR bars",
        "record_count": len(prior_sessions_data),
    }

    # Phase 4 Selection
    d_obj = {
        sym: sorted([
            DailyBar(
                symbol=sym,
                session_date=datetime.fromisoformat(b["t"]).date(),
                open=b["o"],
                high=b["h"],
                low=b["l"],
                close=b["c"],
                volume=b["v"],
            )
            for b in (daily_bars_aaa if sym == "AAA" else daily_bars_bbb)
        ], key=lambda x: x.session_date)
        for sym in ["AAA", "BBB"]
    }
    _d_audit, _comp, d_qual = audit_broad_daily_availability(target_audit.valid_target_symbols, [], d_obj, date(2024, 1, 2))
    cur_ors = {
        "AAA": evaluate_opening_range([
            MinuteBar("AAA", datetime.fromisoformat(b["t"]), date(2024, 1, 2), b["o"], b["h"], b["l"], b["c"], b["v"])
            for b in or_bars_aaa
        ], require_five_bars=False),
        "BBB": evaluate_opening_range([
            MinuteBar("BBB", datetime.fromisoformat(b["t"]), date(2024, 1, 2), b["o"], b["h"], b["l"], b["c"], b["v"])
            for b in or_bars_bbb
        ], require_five_bars=False),
    }
    prior_obs = {
        "AAA": [
            OpeningRangeVolumeObservation("AAA", date.fromisoformat(ps), 30000.0)
            for ps in [s.isoformat() for s in prior_sessions]
        ]
    }
    _s_audit, _outcomes, elig, surv_ors = audit_candidate_screening(
        d_qual, cur_ors, set(), prior_obs, set(), d_obj, date(2024, 1, 2)
    )
    ranked = rank_and_select_top_20(elig, surv_ors, 25000.0, 20)
    sel_ev, sel_records, _ = freeze_top_20_selection(ranked)
    sel_file = f"top_20_selection_{pilot_date}.json"
    sel_bytes = json.dumps({
        "date": pilot_date,
        "selection_sha256": sel_ev.selection_sha256,
        "selected_count": sel_ev.selected_count,
        "doji_count": sel_ev.doji_count,
        "eligible_candidates_count": sel_ev.eligible_candidates_count,
        "records": sel_records,
    }, indent=2).encode("utf-8")
    (output_dir / sel_file).write_bytes(sel_bytes)
    artifacts[sel_file] = {
        "sha256": hash_bytes(sel_bytes),
        "size_bytes": len(sel_bytes),
        "description": "Top-20 selection",
        "record_count": len(sel_records),
    }

    # Phase 5 Stage B
    sb_start = datetime(2024, 1, 2, 9, 35, tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
    sb_end = datetime(2024, 1, 2, 15, 59, 59, tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
    _dfs, sb_meta = client.get_bars(
        ["AAA"],
        sb_start,
        sb_end,
        feed="sip",
        timeframe="1Min",
        adjustment="raw",
        asof=pilot_date,
        include_raw_bars=True,
        include_raw_pages=True,
    )
    sb_file = f"alpaca_stage_b_{pilot_date}.json"
    sb_hash, sb_size = persist_raw_stage_artifact(
        output_dir / sb_file,
        metadata={"stage": "phase_5_stage_b_price_path"},
        batches=[{
            "batch_index": 1,
            "symbols_requested": ["AAA"],
            "request_params": sb_meta.get("request_params", {}),
            "http_status": sb_meta.get("http_status", 200),
            "pagination_complete": sb_meta.get("pagination_complete", True),
            "page_count": sb_meta.get("page_count", 1),
            "token_hashes": sb_meta.get("token_hashes", []),
            "token_sequence_sha256": sb_meta.get("token_sequence_sha256", ""),
            "meta": sb_meta,
            "bars_by_symbol": sb_meta.get("raw_bars_by_symbol", {}),
        }],
    )
    artifacts[sb_file] = {
        "sha256": sb_hash,
        "size_bytes": sb_size,
        "description": "Stage-B bars",
        "record_count": 1,
    }

    # Save manifest with lock marker included
    create_and_save_manifest(output_dir, artifacts, pilot_date)

    # 3. Deterministic replay must succeed without "Unlisted extra file" for the lock marker!
    res = replay_corr_003_pilot(input_dir=output_dir, repo_root=REPO_ROOT, pilot_date=pilot_date)
    assert res.disposition == PilotDisposition.FEASIBLE_FOR_2024_DEVELOPMENT_DATASET_BUILD
    assert res.stage_b_audit.is_usable is True


# =============================================================================
# BLOCKER 3 REGRESSION TESTS: Post-Freeze Allowlist vs Denylist
# =============================================================================


def test_pre_live_code_freeze_rejects_pyproject_toml_drift(tmp_path: Path) -> None:
    """Post-freeze allowlist strictly rejects modification to pyproject.toml between F and A."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Freeze F"], cwd=tmp_path, check=True, capture_output=True)
    freeze_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    # Modify pyproject.toml in commit A
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.1"\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Modify pyproject"], cwd=tmp_path, check=True, capture_output=True)

    with pytest.raises(RuntimeError, match=r"forbidden code/spec/test drift between freeze.*pyproject\.toml"):
        check_pre_live_code_freeze(tmp_path, freeze_sha)


def test_pre_live_code_freeze_rejects_uv_lock_drift(tmp_path: Path) -> None:
    """Post-freeze allowlist strictly rejects modification to uv.lock between F and A."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Freeze F"], cwd=tmp_path, check=True, capture_output=True)
    freeze_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    # Modify uv.lock in commit A
    (tmp_path / "uv.lock").write_text("version = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Modify uv.lock"], cwd=tmp_path, check=True, capture_output=True)

    with pytest.raises(RuntimeError, match=r"forbidden code/spec/test drift between freeze.*uv\.lock"):
        check_pre_live_code_freeze(tmp_path, freeze_sha)


def test_pre_live_code_freeze_rejects_workflow_or_config_drift(tmp_path: Path) -> None:
    """Post-freeze allowlist strictly rejects changes to workflows or runtime config between F and A."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Freeze F"], cwd=tmp_path, check=True, capture_output=True)
    freeze_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    (wf_dir / "ci.yml").write_text("name: Modified CI\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Modify workflow"], cwd=tmp_path, check=True, capture_output=True)

    with pytest.raises(RuntimeError, match=r"forbidden code/spec/test drift between freeze.*\.github"):
        check_pre_live_code_freeze(tmp_path, freeze_sha)


def test_pre_live_code_freeze_allows_gary_authorization_and_documentation(tmp_path: Path) -> None:
    """Post-freeze allowlist permits Gary authorization record and non-executable documentation between F and A."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "README.md").write_text("# TradeX\n", encoding="utf-8")
    docs_dir = tmp_path / "docs" / "research"
    docs_dir.mkdir(parents=True)
    (docs_dir / "DAYTRADE-003D-CORR-003.md").write_text("# Report\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Freeze F"], cwd=tmp_path, check=True, capture_output=True)
    freeze_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    # Commit A: add Gary Yang authorization and update docs
    auth_dir = docs_dir / "authorizations"
    auth_dir.mkdir(parents=True)
    (auth_dir / "DAYTRADE-003D-CORR-003-AUTHORIZATION.json").write_text("{}", encoding="utf-8")
    (docs_dir / "DAYTRADE-003D-CORR-003.md").write_text("# Updated Report\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Authorization and doc update"], cwd=tmp_path, check=True, capture_output=True)

    # Must pass without error
    check_pre_live_code_freeze(tmp_path, freeze_sha)


# =============================================================================
# BLOCKER 4 REGRESSION TESTS: Raw Page Evidence Presence and Coherence
# =============================================================================


def test_validate_provider_batch_rejects_empty_raw_pages_for_200_complete() -> None:
    """HTTP 200 completed provider response with empty raw_pages=[] fails closed."""
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta={
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 0,
            "raw_pages": [],
        },
        bars_by_symbol={"AAPL": []},
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD
    assert "empty raw_pages list" in res.error_message


def test_validate_provider_batch_rejects_page_count_mismatch() -> None:
    """validate_provider_batch_response fails closed when raw_pages count does not match page_count."""
    raw_pages = [{
        "http_status": 200,
        "page_token": None,
        "body": {"bars": {"AAPL": []}, "next_page_token": None},
    }]
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta={
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 2,  # mismatch: claims 2, has 1
            "raw_pages": raw_pages,
        },
        bars_by_symbol={"AAPL": []},
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.TRUNCATED_OR_MALFORMED_PAYLOAD
    assert "does not match metadata page_count" in res.error_message


def test_validate_provider_batch_rejects_raw_page_http_error() -> None:
    """validate_provider_batch_response fails closed when an individual raw page reports non-200 HTTP status."""
    raw_pages = [{
        "http_status": 500,
        "page_token": None,
        "body": {"bars": {"AAPL": []}, "next_page_token": None},
    }]
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta={
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 1,
            "raw_pages": raw_pages,
        },
        bars_by_symbol={"AAPL": []},
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.HTTP_ERROR
    assert "raw_pages[0] http_status 500 != 200" in res.error_message


def test_validate_provider_batch_rejects_unconsumed_terminal_token() -> None:
    """validate_provider_batch_response fails closed when terminal raw page has unconsumed next_page_token."""
    raw_pages = [{
        "http_status": 200,
        "page_token": None,
        "body": {"bars": {"AAPL": []}, "next_page_token": "unconsumed_token_abc"},
    }]
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta={
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 1,
            "raw_pages": raw_pages,
        },
        bars_by_symbol={"AAPL": []},
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.PAGINATION_INCOMPLETE
    assert "Terminal raw page 0 has unconsumed next_page_token" in res.error_message


def test_validate_provider_batch_rejects_missing_intermediate_token() -> None:
    """validate_provider_batch_response fails closed when intermediate raw page lacks next_page_token."""
    raw_pages = [
        {
            "http_status": 200,
            "page_token": None,
            "body": {"bars": {"AAPL": []}, "next_page_token": None},  # Intermediate page lacks token!
        },
        {
            "http_status": 200,
            "page_token": "token2",
            "body": {"bars": {"AAPL": []}, "next_page_token": None},
        },
    ]
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta={
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 2,
            "raw_pages": raw_pages,
        },
        bars_by_symbol={"AAPL": []},
    )
    assert not res.is_valid
    assert res.status == PayloadIntegrityStatus.PAGINATION_INCOMPLETE
    assert "Intermediate raw page 0 is missing required next_page_token" in res.error_message


def test_validate_provider_batch_preserves_legitimate_empty_raw_page() -> None:
    """validate_provider_batch_response preserves legitimately completed empty provider page {'bars': {}}."""
    raw_pages = [{
        "http_status": 200,
        "page_token": None,
        "body": {"bars": {}, "next_page_token": None},
    }]
    res = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta={
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 1,
            "raw_pages": raw_pages,
        },
        bars_by_symbol={},
    )
    assert res.is_valid
    assert res.status == PayloadIntegrityStatus.VALID

    # Also test {'bars': {'AAPL': []}}
    raw_pages_empty_list = [{
        "http_status": 200,
        "page_token": None,
        "body": {"bars": {"AAPL": []}, "next_page_token": None},
    }]
    res2 = validate_provider_batch_response(
        symbols_requested=["AAPL"],
        meta={
            "http_status": 200,
            "pagination_complete": True,
            "page_count": 1,
            "raw_pages": raw_pages_empty_list,
        },
        bars_by_symbol={"AAPL": []},
    )
    assert res2.is_valid
    assert res2.status == PayloadIntegrityStatus.VALID


def test_resigned_artifact_with_missing_raw_pages_fails_closed_in_replay(tmp_path: Path) -> None:
    """An artifact claiming 200/complete with missing or empty raw pages fails closed in offline replay even when re-signed."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    sb_file = fixture_dir / "alpaca_stage_b_2024-01-02.json"
    sb_data = json.loads(sb_file.read_text(encoding="utf-8"))

    # Tamper: strip raw_pages evidence while claiming 200/complete
    for batch in sb_data["batches"]:
        batch["meta"]["raw_pages"] = []

    tampered_bytes = json.dumps(sb_data, indent=2).encode("utf-8")
    sb_file.write_bytes(tampered_bytes)

    # Re-sign the manifest so manifest checksum verification passes
    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"][sb_file.name]["sha256"] = hash_bytes(tampered_bytes)
    m_data["artifacts"][sb_file.name]["size_bytes"] = len(tampered_bytes)
    m_path.write_bytes(json.dumps(m_data, indent=2).encode("utf-8"))

    # Offline replay must detect missing raw pages and fail closed with BLOCKED_PROVIDER_DATA_INTEGRITY!
    res = replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")
    assert res.disposition == PilotDisposition.BLOCKED_PROVIDER_DATA_INTEGRITY
    assert res.provider_data_integrity_success is False
    assert res.stage_b_audit.provider_failure_count > 0
    assert not res.stage_b_audit.is_usable


def test_resigned_daily_artifact_with_missing_raw_pages_fails_closed(tmp_path: Path) -> None:
    """Re-signed daily artifact with missing raw_pages fails closed in replay due to parity rejection."""
    fixture_dir = _build_synthetic_fixture(tmp_path)
    daily_file = fixture_dir / "alpaca_daily_dec2023.json"
    daily_data = json.loads(daily_file.read_text(encoding="utf-8"))

    for batch in daily_data["batches"]:
        batch["meta"]["raw_pages"] = []

    tampered_bytes = json.dumps(daily_data, indent=2).encode("utf-8")
    daily_file.write_bytes(tampered_bytes)

    m_path = fixture_dir / "manifest_2024-01-02.json"
    m_data = json.loads(m_path.read_text(encoding="utf-8"))
    m_data["artifacts"][daily_file.name]["sha256"] = hash_bytes(tampered_bytes)
    m_data["artifacts"][daily_file.name]["size_bytes"] = len(tampered_bytes)
    m_path.write_bytes(json.dumps(m_data, indent=2).encode("utf-8"))

    with pytest.raises(ReplayIntegrityError, match="Top-20 selection hash mismatch"):
        replay_corr_003_pilot(input_dir=fixture_dir, repo_root=REPO_ROOT, pilot_date="2024-01-02")


def test_is_allowed_post_freeze_drift_rules() -> None:
    """Validate allowable vs forbidden post-freeze drift paths."""
    assert is_allowed_post_freeze_drift("docs/research/authorizations/DAYTRADE-003D-CORR-003-AUTHORIZATION.json")
    assert is_allowed_post_freeze_drift("docs/research/DAYTRADE-003D-CORR-003.md")
    assert is_allowed_post_freeze_drift("README.md")
    assert not is_allowed_post_freeze_drift("docs/research/specs/DAYTRADE-003B-ORB-v1.json")
    assert not is_allowed_post_freeze_drift("pyproject.toml")
    assert not is_allowed_post_freeze_drift("uv.lock")
    assert not is_allowed_post_freeze_drift("tradex/foo.py")
    assert not is_allowed_post_freeze_drift(".github/workflows/ci.yml")


def test_validate_run_lock_marker_directly(tmp_path: Path) -> None:
    """Validate run lock marker error handling when missing or non-dict."""
    non_existent = tmp_path / "does_not_exist.json"
    errs = validate_run_lock_marker(non_existent)
    assert any("does not exist" in e for e in errs)

    non_dict = tmp_path / "not_dict.json"
    non_dict.write_text("[1, 2, 3]", encoding="utf-8")
    errs2 = validate_run_lock_marker(non_dict)
    assert any("not a valid JSON object" in e for e in errs2)


def test_pre_live_guard_rejects_ignored_uv_lock_modification(tmp_path: Path) -> None:
    """With actual repository ignore behavior (uv.lock ignored in .gitignore),
    modifying or re-resolving uv.lock on disk is invisible to git status/diff,
    but is strictly caught and rejected by check_runtime_environment_freeze / pre-live guards."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)

    # Actual repo .gitignore ignoring uv.lock
    (tmp_path / ".gitignore").write_text("# uv lockfile is not tracked in this repo\nuv.lock\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "tradex"\n', encoding="utf-8")

    # Audited uv.lock on disk (write exact LF bytes)
    uv_lock_bytes = b"audited_lockfile_content_version_1\n"
    (tmp_path / "uv.lock").write_bytes(uv_lock_bytes)
    expected_uv_sha = hashlib.sha256(uv_lock_bytes).hexdigest()

    # Create environment spec referencing the audited uv.lock hash
    spec_dir = tmp_path / "docs" / "research" / "specs"
    spec_dir.mkdir(parents=True)
    env_spec_path = spec_dir / "DAYTRADE-003D-CORR-003-ENVIRONMENT.json"
    spec_data = {
        "task_id": "DAYTRADE-003D-CORR-003",
        "python_version_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "uv_lock_sha256": expected_uv_sha,
        "core_runtime_packages": {"pandas": "3.0.6"},
    }
    env_spec_path.write_bytes(json.dumps(spec_data, indent=2).encode("utf-8"))

    # Add and commit tracked files
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Freeze F"], cwd=tmp_path, check=True, capture_output=True)

    # Verify uv.lock is truly ignored by git
    status_out = subprocess.run(["git", "status", "--porcelain"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    assert status_out == "", "uv.lock must be ignored by git"

    # Now modify / re-resolve uv.lock on disk (without git tracking it)
    (tmp_path / "uv.lock").write_bytes(b"re_resolved_modified_lockfile_content_version_2\n")

    # Git still sees a completely clean tree!
    status_out_after = subprocess.run(["git", "status", "--porcelain"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    assert status_out_after == "", "uv.lock modification must remain ignored by git"

    # But check_runtime_environment_freeze FAILS CLOSED!
    with pytest.raises(RuntimeError, match=r"Ignored uv\.lock has been modified or re-resolved on disk"):
        check_runtime_environment_freeze(
            tmp_path,
            spec_path=env_spec_path,
            check_uv_lock=True,
            require_live_provider_packages=False,
            verify_spec_hash=False,
        )


def test_runtime_environment_freeze_matches_current_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hermetic positive test: check_runtime_environment_freeze verifies matching environment in isolation.

    Uses an isolated fixture environment and mock metadata so the test does not depend on
    ambient floating dependency resolution in CI, while strictly proving that a matching
    runtime environment passes validation.
    """
    spec_path = REPO_ROOT / CORR_003_ENV_SPEC_PATH
    spec_data = json.loads(spec_path.read_bytes())
    audited_sha = spec_data["accepted_uv_lock_sha256"]["windows_pilot_host_all_extras"]
    expected_pkgs = dict(spec_data["core_runtime_packages"])

    lock_bytes = b"audited_uv_lockfile_content_windows\n"
    (tmp_path / "uv.lock").write_bytes(lock_bytes)

    orig_sha256 = hashlib.sha256

    class _MockDigest:
        def hexdigest(self) -> str:
            return audited_sha

    def mock_sha256(data: bytes = b"") -> Any:
        if data == lock_bytes:
            return _MockDigest()
        return orig_sha256(data)

    monkeypatch.setattr("tradex.research.daytrade_orb.corr_003_pilot.hashlib.sha256", mock_sha256)
    monkeypatch.setattr(
        "importlib.metadata.version",
        lambda pkg: expected_pkgs.get(pkg, "0.0.0"),
    )

    spec = check_runtime_environment_freeze(
        tmp_path,
        spec_path=spec_path,
        require_live_provider_packages=False,
        check_uv_lock=True,
        verify_spec_hash=True,
    )
    assert spec["task_id"] == "DAYTRADE-003D-CORR-003"
    assert spec["python_version_major_minor"] == "3.11"
    assert len(spec["core_runtime_packages"]) >= 19


def test_runtime_environment_freeze_rejects_package_version_mismatch(tmp_path: Path) -> None:
    """Mismatched package version fails closed."""
    spec_path = tmp_path / "env_spec.json"
    spec_data = {
        "task_id": "DAYTRADE-003D-CORR-003",
        "python_version_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "uv_lock_sha256": "dummy",
        "core_runtime_packages": {
            "pandas": "99.99.99",  # non-matching version
        },
    }
    spec_path.write_bytes(json.dumps(spec_data, indent=2).encode("utf-8"))

    with pytest.raises(RuntimeError, match=r"Mismatched package version for 'pandas'"):
        check_runtime_environment_freeze(
            tmp_path,
            spec_path=spec_path,
            check_uv_lock=False,
            require_live_provider_packages=False,
            verify_spec_hash=False,
        )


def test_runtime_environment_freeze_rejects_missing_package(tmp_path: Path) -> None:
    """Missing required package fails closed."""
    spec_path = tmp_path / "env_spec.json"
    spec_data = {
        "task_id": "DAYTRADE-003D-CORR-003",
        "python_version_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "uv_lock_sha256": "dummy",
        "core_runtime_packages": {
            "nonexistent_package_xyz_123": "1.0.0",
        },
    }
    spec_path.write_bytes(json.dumps(spec_data, indent=2).encode("utf-8"))

    with pytest.raises(RuntimeError, match=r"Missing required package: 'nonexistent_package_xyz_123'"):
        check_runtime_environment_freeze(
            tmp_path,
            spec_path=spec_path,
            check_uv_lock=False,
            require_live_provider_packages=False,
            verify_spec_hash=False,
        )


def test_runtime_environment_freeze_rejects_python_version_mismatch(tmp_path: Path) -> None:
    """Python version mismatch fails closed."""
    spec_path = tmp_path / "env_spec.json"
    spec_data = {
        "task_id": "DAYTRADE-003D-CORR-003",
        "python_version_major_minor": "3.99",
        "uv_lock_sha256": "dummy",
        "core_runtime_packages": {},
    }
    spec_path.write_bytes(json.dumps(spec_data, indent=2).encode("utf-8"))

    with pytest.raises(RuntimeError, match=r"Python version mismatch: expected '3\.99'"):
        check_runtime_environment_freeze(
            tmp_path,
            spec_path=spec_path,
            check_uv_lock=False,
            require_live_provider_packages=False,
            verify_spec_hash=False,
        )


def test_pre_live_guard_clean_git_f_to_a_with_frozen_environment(tmp_path: Path) -> None:
    """A clean Git F->A path with frozen environment and Gary authorization passes all guards."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)

    # .gitignore ignoring uv.lock
    (tmp_path / ".gitignore").write_text("# uv lockfile is not tracked in this repo\nuv.lock\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "tradex"\n', encoding="utf-8")

    # Audited uv.lock on disk (write exact LF bytes)
    uv_lock_bytes = b"audited_lockfile_content\n"
    (tmp_path / "uv.lock").write_bytes(uv_lock_bytes)
    expected_uv_sha = hashlib.sha256(uv_lock_bytes).hexdigest()

    # Create environment spec referencing the audited uv.lock hash
    spec_dir = tmp_path / "docs" / "research" / "specs"
    spec_dir.mkdir(parents=True)
    env_spec_path = spec_dir / "DAYTRADE-003D-CORR-003-ENVIRONMENT.json"
    spec_data = {
        "task_id": "DAYTRADE-003D-CORR-003",
        "python_version_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "uv_lock_sha256": expected_uv_sha,
        "core_runtime_packages": {},
    }
    env_spec_path.write_text(json.dumps(spec_data, indent=2), encoding="utf-8")

    # Add and commit tracked files at Freeze F
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Freeze F"], cwd=tmp_path, check=True, capture_output=True)
    freeze_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    # Commit A adding Gary's authorization
    auth_dir = tmp_path / "docs" / "research" / "authorizations"
    auth_dir.mkdir(parents=True)
    auth_file = auth_dir / "DAYTRADE-003D-CORR-003-AUTHORIZATION.json"
    auth_file.write_text(
        json.dumps(
            {
                "task_id": "DAYTRADE-003D-CORR-003",
                "pilot_date": "2024-01-02",
                "authorized_by": "Gary Yang",
                "frozen_implementation_sha": freeze_sha,
                "run_scope": "ONE_SHOT_PILOT_JAN_2_2024",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", str(auth_file)], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit A (Gary auth)"], cwd=tmp_path, check=True, capture_output=True)

    # Guards pass cleanly
    check_pre_live_code_freeze(tmp_path, freeze_sha, verify_environment=False)
    check_pilot_authorization(tmp_path, freeze_sha, authorized_by_gary=True)
    env_checked = check_runtime_environment_freeze(
        tmp_path,
        spec_path=env_spec_path,
        check_uv_lock=True,
        require_live_provider_packages=False,
        verify_spec_hash=False,
    )
    assert env_checked["task_id"] == "DAYTRADE-003D-CORR-003"


def _load_pilot_cli() -> Any:
    import importlib.util

    script_path = REPO_ROOT / "scripts" / "research" / "daytrade_003d_corr_003_pilot.py"
    spec = importlib.util.spec_from_file_location("daytrade_003d_corr_003_pilot_cli", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pilot_runner_cli_check_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Hermetic test: CLI check-env subcommand verifies matching and rejecting environments in isolation."""
    spec_dir = tmp_path / "docs" / "research" / "specs"
    spec_dir.mkdir(parents=True)
    real_spec_bytes = (REPO_ROOT / CORR_003_ENV_SPEC_PATH).read_bytes()
    (spec_dir / "DAYTRADE-003D-CORR-003-ENVIRONMENT.json").write_bytes(real_spec_bytes)

    lock_bytes = b"audited_uv_lockfile_cli_content\n"
    (tmp_path / "uv.lock").write_bytes(lock_bytes)

    spec_data = json.loads(real_spec_bytes.decode("utf-8"))
    audited_sha = spec_data["accepted_uv_lock_sha256"]["linux_ci_runner_standard_extras"]
    expected_pkgs = dict(spec_data["core_runtime_packages"])
    expected_pkgs.update(spec_data.get("live_provider_packages", {}))

    orig_sha256 = hashlib.sha256

    class _MockDigest:
        def hexdigest(self) -> str:
            return audited_sha

    def mock_sha256(data: bytes = b"") -> Any:
        if data == lock_bytes:
            return _MockDigest()
        return orig_sha256(data)

    monkeypatch.setattr("tradex.research.daytrade_orb.corr_003_pilot.hashlib.sha256", mock_sha256)
    monkeypatch.setattr(
        "importlib.metadata.version",
        lambda pkg: expected_pkgs.get(pkg, "0.0.0"),
    )

    # 1. Success path: matching environment returns 0 with success banner
    cli_mod = _load_pilot_cli()
    monkeypatch.setattr(sys, "argv", ["daytrade_003d_corr_003_pilot.py", "check-env", "--repo-root", str(tmp_path)])
    exit_code = cli_mod.main()
    captured = capsys.readouterr()
    assert exit_code == 0, f"check-env failed unexpectedly: {captured.out}\n{captured.err}"
    assert "Runtime environment strictly matches frozen specification" in captured.out
    assert "Core Packages Checked: 19" in captured.out

    # 2. Failure path: mismatched package fails closed with exit code 1 and error diagnostic
    monkeypatch.setattr(
        "importlib.metadata.version",
        lambda pkg: "99.99.99" if pkg == "pandas" else expected_pkgs.get(pkg, "0.0.0"),
    )
    exit_code_mismatch = cli_mod.main()
    captured_mismatch = capsys.readouterr()
    assert exit_code_mismatch == 1
    assert "[ENVIRONMENT CHECK FAILED]" in captured_mismatch.out
    assert "Mismatched package version for 'pandas'" in captured_mismatch.out


def test_runtime_environment_freeze_rejects_missing_uv_lock(tmp_path: Path) -> None:
    """When check_uv_lock=True, missing uv.lock fails closed with explicit error."""
    spec_path = tmp_path / "env_spec.json"
    spec_data = {
        "task_id": "DAYTRADE-003D-CORR-003",
        "python_version_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "accepted_uv_lock_sha256": ["audited_sha_123"],
        "core_runtime_packages": {},
    }
    spec_path.write_bytes(json.dumps(spec_data, indent=2).encode("utf-8"))

    # uv.lock does not exist in tmp_path
    assert not (tmp_path / "uv.lock").exists()

    with pytest.raises(RuntimeError, match=r"Missing required uv\.lock on disk"):
        check_runtime_environment_freeze(
            tmp_path,
            spec_path=spec_path,
            check_uv_lock=True,
            require_live_provider_packages=False,
            verify_spec_hash=False,
        )


def test_pre_live_guard_rejects_missing_uv_lock_in_clean_repo(tmp_path: Path) -> None:
    """A clean Git repo missing uv.lock fails closed at the pre-live execution gate."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)

    # .gitignore ignoring uv.lock
    (tmp_path / ".gitignore").write_text("# uv lockfile is not tracked in this repo\nuv.lock\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "tradex"\n', encoding="utf-8")

    spec_dir = tmp_path / "docs" / "research" / "specs"
    spec_dir.mkdir(parents=True)
    real_spec = (REPO_ROOT / CORR_003_ENV_SPEC_PATH).read_bytes()
    (spec_dir / "DAYTRADE-003D-CORR-003-ENVIRONMENT.json").write_bytes(real_spec)

    # Commit at freeze F (uv.lock is not present!)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Freeze F"], cwd=tmp_path, check=True, capture_output=True)
    freeze_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    # Git tree is clean, uv.lock is absent on disk
    status_out = subprocess.run(["git", "status", "--porcelain"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    assert status_out == ""
    assert not (tmp_path / "uv.lock").exists()

    # check_pre_live_code_freeze fails closed because uv.lock is missing!
    with pytest.raises(RuntimeError, match=r"Missing required uv\.lock on disk"):
        check_pre_live_code_freeze(tmp_path, freeze_sha, verify_environment=True)


def test_runtime_environment_freeze_rejects_missing_accepted_hashes_field(tmp_path: Path) -> None:
    """Missing accepted lockfile hashes field in spec fails closed."""
    spec_path = tmp_path / "env_spec.json"
    spec_data = {
        "task_id": "DAYTRADE-003D-CORR-003",
        "python_version_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "core_runtime_packages": {},
    }
    spec_path.write_bytes(json.dumps(spec_data, indent=2).encode("utf-8"))
    (tmp_path / "uv.lock").write_bytes(b"some_lockfile_content\n")

    with pytest.raises(RuntimeError, match=r"Runtime environment specification is missing required 'accepted_uv_lock_sha256'"):
        check_runtime_environment_freeze(
            tmp_path,
            spec_path=spec_path,
            check_uv_lock=True,
            require_live_provider_packages=False,
            verify_spec_hash=False,
        )


def test_runtime_environment_freeze_rejects_empty_accepted_hashes_field(tmp_path: Path) -> None:
    """Empty or whitespace-only accepted lockfile hashes in spec fails closed."""
    spec_path = tmp_path / "env_spec.json"
    spec_data = {
        "task_id": "DAYTRADE-003D-CORR-003",
        "python_version_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "accepted_uv_lock_sha256": ["   ", ""],
        "core_runtime_packages": {},
    }
    spec_path.write_bytes(json.dumps(spec_data, indent=2).encode("utf-8"))
    (tmp_path / "uv.lock").write_bytes(b"some_lockfile_content\n")

    with pytest.raises(RuntimeError, match=r"Runtime environment specification contains empty or invalid accepted lockfile hashes"):
        check_runtime_environment_freeze(
            tmp_path,
            spec_path=spec_path,
            check_uv_lock=True,
            require_live_provider_packages=False,
            verify_spec_hash=False,
        )


def test_runtime_environment_freeze_positive_exact_audited_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Positive test: active runtime matches exact audited specification and on-disk uv.lock in isolation."""
    spec_path = REPO_ROOT / CORR_003_ENV_SPEC_PATH
    spec_data = json.loads(spec_path.read_bytes())
    audited_sha = spec_data["accepted_uv_lock_sha256"]["linux_ci_runner_standard_extras"]
    expected_pkgs = dict(spec_data["core_runtime_packages"])
    expected_pkgs.update(spec_data.get("live_provider_packages", {}))

    lock_bytes = b"audited_uv_lockfile_content_linux\n"
    (tmp_path / "uv.lock").write_bytes(lock_bytes)

    orig_sha256 = hashlib.sha256

    class _MockDigest:
        def hexdigest(self) -> str:
            return audited_sha

    def mock_sha256(data: bytes = b"") -> Any:
        if data == lock_bytes:
            return _MockDigest()
        return orig_sha256(data)

    monkeypatch.setattr("tradex.research.daytrade_orb.corr_003_pilot.hashlib.sha256", mock_sha256)
    monkeypatch.setattr(
        "importlib.metadata.version",
        lambda pkg: expected_pkgs.get(pkg, "0.0.0"),
    )

    spec = check_runtime_environment_freeze(
        tmp_path,
        spec_path=spec_path,
        check_uv_lock=True,
        require_live_provider_packages=True,
        verify_spec_hash=True,
    )
    assert spec["task_id"] == "DAYTRADE-003D-CORR-003"
    assert spec["python_version_major_minor"] == "3.11"
    assert "accepted_uv_lock_sha256" in spec
    assert len(spec["core_runtime_packages"]) >= 19
    assert len(spec["live_provider_packages"]) >= 3


def test_pilot_runner_cli_check_env_rejects_missing_uv_lock(tmp_path: Path) -> None:
    """CLI check-env fails closed when uv.lock is missing on disk."""
    spec_dir = tmp_path / "docs" / "research" / "specs"
    spec_dir.mkdir(parents=True)
    real_spec = (REPO_ROOT / CORR_003_ENV_SPEC_PATH).read_bytes()
    (spec_dir / "DAYTRADE-003D-CORR-003-ENVIRONMENT.json").write_bytes(real_spec)

    assert not (tmp_path / "uv.lock").exists()

    res = subprocess.run(
        [
            sys.executable,
            "scripts/research/daytrade_003d_corr_003_pilot.py",
            "check-env",
            "--repo-root",
            str(tmp_path),
            "--require-live-providers",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 1
    assert "Missing required uv.lock on disk" in res.stdout


def test_live_pilot_preflight_rejects_missing_uv_lock(tmp_path: Path) -> None:
    """Live pilot preflight rejects missing uv.lock without provider calls or credential loading."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Gary Yang"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gary.yang@airbyte.com"], cwd=tmp_path, check=True, capture_output=True)

    (tmp_path / ".gitignore").write_text("# uv lockfile is not tracked in this repo\nuv.lock\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "tradex"\n', encoding="utf-8")

    spec_dir = tmp_path / "docs" / "research" / "specs"
    spec_dir.mkdir(parents=True)
    real_spec = (REPO_ROOT / CORR_003_ENV_SPEC_PATH).read_bytes()
    (spec_dir / "DAYTRADE-003D-CORR-003-ENVIRONMENT.json").write_bytes(real_spec)

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Freeze F"], cwd=tmp_path, check=True, capture_output=True)
    freeze_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    auth_dir = tmp_path / "docs" / "research" / "authorizations"
    auth_dir.mkdir(parents=True)
    auth_file = auth_dir / "DAYTRADE-003D-CORR-003-AUTHORIZATION.json"
    auth_file.write_text(
        json.dumps(
            {
                "task_id": "DAYTRADE-003D-CORR-003",
                "pilot_date": "2024-01-02",
                "authorized_by": "Gary Yang",
                "frozen_implementation_sha": freeze_sha,
                "run_scope": "ONE_SHOT_PILOT_JAN_2_2024",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", str(auth_file)], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit A (Gary auth)"], cwd=tmp_path, check=True, capture_output=True)

    assert not (tmp_path / "uv.lock").exists()

    res = subprocess.run(
        [
            sys.executable,
            "scripts/research/daytrade_003d_corr_003_pilot.py",
            "pilot",
            "--pre-live-sha",
            freeze_sha,
            "--repo-root",
            str(tmp_path),
            "--authorize-live",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 1
    assert "Missing required uv.lock on disk" in res.stdout





