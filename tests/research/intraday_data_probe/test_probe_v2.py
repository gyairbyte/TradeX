"""Credential-free/network-free regression tests for INTRA-001B Alpaca v2 probe.

These tests exercise the corrected v2 audit contract: timestamp semantics,
pagination gating, direct/chunked independence, candidate-feed gating,
regular-session quality scope, SIP/IEX comparator scope, provider-contract
evidence classification, exact spec-byte locking, and safe-artifact schema.
"""
from __future__ import annotations

import json
from datetime import UTC, date, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import pytest

from tradex.research.intraday_data_probe.alpaca_client import (
    AlpacaRestClient,
    _token_hash,
    _token_sequence_hash,
)
from tradex.research.intraday_data_probe.models import ProbeRequestRecord
from tradex.research.intraday_data_probe.probe import (
    _analyze_request,
    _build_alpaca_feed_comparison_rows,
    _build_decision,
    _classify_timestamp_semantics,
    _eastern_bounds,
    _evaluate_alpaca_provider_contract,
    _session_bar_end_grid,
    _sha256_candles,
)
from tradex.research.intraday_data_probe.report import (
    write_probe_artifacts,
    write_probe_report,
)
from tradex.research.intraday_data_probe.spec import IntradayProbeSpec, load_probe_spec


@pytest.fixture
def v2_spec_path(tmp_path: Path) -> Path:
    p = tmp_path / "v2-spec.json"
    p.write_text(
        Path("docs/research/specs/INTRA-001B-alpaca-probe-v2.json").read_text(),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def v2_spec(v2_spec_path: Path) -> IntradayProbeSpec:
    spec, _ = load_probe_spec(v2_spec_path)
    return spec


@pytest.fixture
def cal() -> Any:
    return xcals.get_calendar("XNYS")


def _ny(ts: str) -> pd.Timestamp:
    return pd.Timestamp(ts, tz="America/New_York")


def _grid(spec: IntradayProbeSpec, cal: Any, d: date) -> dict[str, Any]:
    open_utc = cal.session_open(d).tz_convert("UTC")
    close_utc = cal.session_close(d).tz_convert("UTC")
    close_ny = close_utc.tz_convert(spec.timezone)
    grid = set(pd.date_range(start=open_utc, end=close_utc, freq="5min", inclusive="left"))
    bar_end_grid = set(_session_bar_end_grid(cal, d))
    return {
        "open_utc": open_utc,
        "close_utc": close_utc,
        "is_full": close_ny.time().hour == 16,
        "grid": grid,
        "bar_end_grid": bar_end_grid,
    }


def _df_from_timestamps(tss: list[pd.Timestamp]) -> pd.DataFrame:
    idx = pd.DatetimeIndex(tss, name="datetime")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
        index=idx,
    )


# ---------------------------------------------------------------------------
# Timestamp semantics
# ---------------------------------------------------------------------------


def test_bar_start_session_classified(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    grids = {d: _grid(v2_spec, cal, d)}
    tss = list(grids[d]["grid"])
    df = _df_from_timestamps([ts.tz_convert(v2_spec.timezone) for ts in tss])
    result = _classify_timestamp_semantics(df, cal, grids, ZoneInfo(v2_spec.timezone), exclude_early_close=True)
    assert result == "bar_start"


def test_bar_end_session_classified(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    grids = {d: _grid(v2_spec, cal, d)}
    tss = list(grids[d]["bar_end_grid"])
    df = _df_from_timestamps([ts.tz_convert(v2_spec.timezone) for ts in tss])
    result = _classify_timestamp_semantics(df, cal, grids, ZoneInfo(v2_spec.timezone), exclude_early_close=True)
    assert result == "bar_end"


def test_bar_start_plus_close_extra_remains_bar_start(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    grids = {d: _grid(v2_spec, cal, d)}
    start_tss = list(grids[d]["grid"])
    close_extra = [grids[d]["close_utc"].tz_convert(v2_spec.timezone)]
    df = _df_from_timestamps([ts.tz_convert(v2_spec.timezone) for ts in start_tss + close_extra])
    result = _classify_timestamp_semantics(df, cal, grids, ZoneInfo(v2_spec.timezone), exclude_early_close=True)
    assert result == "bar_start"


def test_mixed_session_semantics_is_ambiguous(v2_spec: IntradayProbeSpec, cal: Any):
    d1 = date(2024, 6, 3)
    d2 = date(2024, 6, 4)
    grids = {d1: _grid(v2_spec, cal, d1), d2: _grid(v2_spec, cal, d2)}
    tss = list(grids[d1]["grid"]) + list(grids[d2]["bar_end_grid"])
    df = _df_from_timestamps([ts.tz_convert(v2_spec.timezone) for ts in tss])
    result = _classify_timestamp_semantics(df, cal, grids, ZoneInfo(v2_spec.timezone), exclude_early_close=True)
    assert result == "ambiguous"


def test_insufficient_data_is_undetermined(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    grids = {d: _grid(v2_spec, cal, d)}
    # Only two middle timestamps.
    start_grid = sorted(grids[d]["grid"])
    tss = [start_grid[10], start_grid[20]]
    df = _df_from_timestamps([ts.tz_convert(v2_spec.timezone) for ts in tss])
    result = _classify_timestamp_semantics(df, cal, grids, ZoneInfo(v2_spec.timezone), exclude_early_close=True)
    assert result == "undetermined"


def test_early_close_excluded_from_semantics(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 7, 3)  # Early close 13:00 ET
    if not cal.is_session(d):
        pytest.skip("Selected date not an XNYS session")
    grids = {d: _grid(v2_spec, cal, d)}
    tss = list(grids[d]["grid"])
    df = _df_from_timestamps([ts.tz_convert(v2_spec.timezone) for ts in tss])
    result = _classify_timestamp_semantics(df, cal, grids, ZoneInfo(v2_spec.timezone), exclude_early_close=True)
    assert result == "undetermined"


def test_extended_hours_do_not_create_semantics_vote(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    grids = {d: _grid(v2_spec, cal, d)}
    open_ny = grids[d]["open_utc"].tz_convert(v2_spec.timezone)
    # Pre-market 09:25 ET
    pre = (open_ny - timedelta(minutes=5)).tz_convert(v2_spec.timezone)
    df = _df_from_timestamps([pre])
    result = _classify_timestamp_semantics(df, cal, grids, ZoneInfo(v2_spec.timezone), exclude_early_close=True)
    assert result == "undetermined"


def test_session_bar_end_grid_does_not_include_open(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    grid = _session_bar_end_grid(cal, d)
    open_utc = cal.session_open(d).tz_convert("UTC")
    assert open_utc not in grid
    assert (open_utc + timedelta(minutes=5)) in grid
    assert cal.session_close(d).tz_convert("UTC") in grid


# ---------------------------------------------------------------------------
# Pagination gating
# ---------------------------------------------------------------------------


def _base_v2(**kwargs: Any) -> ProbeRequestRecord:
    defaults = {
        "probe_id": "full-SPY-sip-rep1",
        "symbol": "SPY",
        "method": "sip",
        "repetition": 1,
        "requested_eastern_start": "",
        "requested_eastern_end": "",
        "requested_utc_start": "",
        "requested_utc_end": "",
        "http_status": 200,
        "safe_error_classification": "none",
        "raw_candle_count": 100,
        "normalized_candle_count": 100,
        "raw_earliest_timestamp": None,
        "raw_latest_timestamp": None,
        "requested_range_earliest": None,
        "requested_range_latest": None,
        "out_of_range_candles": 0,
        "unique_regular_sessions": 1,
        "expected_eligible_sessions": 1,
        "expected_regular_session_bars": 100,
        "returned_regular_session_bars": 100,
        "primary_session_bars": 100,
        "early_close_session_bars": 0,
        "extended_hours_bars": 0,
        "regular_session_coverage_pct": 100.0,
        "missing_regular_session_bars": 0,
        "duplicate_timestamps": 0,
        "duplicate_bar_rate_pct": 0.0,
        "zero_volume_bars": 0,
        "zero_volume_rate_pct": 0.0,
        "invalid_ohlc_rows": 0,
        "non_five_minute_intervals": 0,
        "candle_payload_sha256": "",
        "requested_range_normalized_sha256": "",
        "date_bound_classification": "honored_exactly",
        "timestamp_semantics_classification": "bar_start",
        "threshold_result": "passed",
        "retry_after_seconds": None,
        "notes": "",
        "page_count": 1,
        "next_page_token_present": False,
        "pagination_complete": True,
        "repeated_page_token": False,
        "pagination_cycle_detected": False,
        "page_bar_counts": (100,),
        "token_sequence_sha256": "abc",
        "regular_session_zero_volume_bars": 0,
        "regular_session_zero_volume_rate_pct": 0.0,
        "regular_session_invalid_ohlc_rows": 0,
        "regular_session_duplicate_timestamps": 0,
        "regular_session_duplicate_bar_rate_pct": 0.0,
    }
    return ProbeRequestRecord(**{**defaults, **kwargs})


def _repeat_row(method: str = "sip", match: bool = True) -> dict[str, Any]:
    return {
        "base_probe_id": "full-SPY-sip",
        "symbol": "SPY",
        "method": method,
        "date_range": "test",
        "repeat_hash_match": match,
        "rep1_http_status": 200,
        "rep2_http_status": 200,
        "rep1_primary_session_bars": 100,
        "rep2_primary_session_bars": 100,
        "rep1_hash": "h1",
        "rep2_hash": "h2" if not match else "h1",
        "rep1_threshold": "passed",
        "rep2_threshold": "passed",
        "rep1_page_count": 1,
        "rep2_page_count": 1,
        "rep1_pagination_complete": True,
        "rep2_pagination_complete": True,
        "rep1_repeated_page_token": False,
        "rep2_repeated_page_token": False,
        "rep1_pagination_cycle_detected": False,
        "rep2_pagination_cycle_detected": False,
    }


def _overlap_row(method: str = "sip", classification: str = "match") -> dict[str, Any]:
    return {
        "method": method,
        "window": "window-2024-06",
        "symbol": "SPY",
        "repetition": 1,
        "left_probe_id": f"overlap-left-SPY-{method}-rep1",
        "right_probe_id": f"overlap-right-SPY-{method}-rep1",
        "left_hash": "h1",
        "right_hash": "h1",
        "classification": classification,
        "overlap_start": "2024-06-10T13:30:00.000000+0000",
    }


def test_complete_one_page_request_passes(v2_spec: IntradayProbeSpec):
    r = _base_v2(pagination_complete=True, page_count=1)
    decision = _build_decision(v2_spec, [r], [_repeat_row()], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.direct_full_range_supported is True


def test_complete_multi_page_request_passes(v2_spec: IntradayProbeSpec):
    r = _base_v2(pagination_complete=True, page_count=3, page_bar_counts=(5000, 5000, 5000))
    decision = _build_decision(v2_spec, [r], [_repeat_row()], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.direct_full_range_supported is True


def test_pagination_cycle_fails_support(v2_spec: IntradayProbeSpec):
    r = _base_v2(pagination_complete=True, pagination_cycle_detected=True, regular_session_coverage_pct=100.0)
    decision = _build_decision(v2_spec, [r], [], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.direct_full_range_supported is False
    assert decision.outcome == "not_supported"


def test_repeated_page_token_fails_support(v2_spec: IntradayProbeSpec):
    r = _base_v2(pagination_complete=True, repeated_page_token=True, regular_session_coverage_pct=100.0)
    decision = _build_decision(v2_spec, [r], [], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.direct_full_range_supported is False
    assert decision.outcome == "not_supported"


def test_incomplete_pagination_fails_even_with_full_coverage(v2_spec: IntradayProbeSpec):
    r = _base_v2(pagination_complete=False, regular_session_coverage_pct=100.0)
    decision = _build_decision(v2_spec, [r], [], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.direct_full_range_supported is False


def test_page_count_mismatch_fails_repeatability(v2_spec: IntradayProbeSpec):
    r1 = _base_v2(probe_id="full-SPY-sip-rep1", page_count=1)
    r2 = _base_v2(probe_id="full-SPY-sip-rep2", page_count=2)
    repeat = [_repeat_row(match=False)]
    decision = _build_decision(v2_spec, [r1, r2], repeat, [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.repeatability_passed is False
    assert decision.pagination_repeatability_passed is False


def test_token_sequence_hash_is_deterministic():
    seq = ["abc", "def", "ghi"]
    h1 = _token_sequence_hash(seq)
    h2 = _token_sequence_hash(seq)
    assert h1 == h2
    assert len(h1) == 64


def test_token_hash_never_exposes_raw_token():
    raw = "super_secret_pagination_token"
    h = _token_hash(raw)
    assert raw not in h
    assert _token_hash(None) == _token_hash("null")


# ---------------------------------------------------------------------------
# Direct / chunked independence
# ---------------------------------------------------------------------------


def test_direct_and_chunked_both_true_prefers_direct(v2_spec: IntradayProbeSpec):
    bounded = []
    for w in v2_spec.bounded_window_probes:
        for s in v2_spec.symbols:
            bounded.append(_base_v2(probe_id=f"{w.id}-{s}-sip-rep1", symbol=s, method="sip", threshold_result="passed", date_bound_classification="honored_exactly", primary_session_bars=78, raw_candle_count=78))
    full = _base_v2(probe_id="full-SPY-sip-rep1", raw_candle_count=100, primary_session_bars=100, regular_session_coverage_pct=100.0)
    decision = _build_decision(v2_spec, bounded + [full], [_repeat_row("sip")], [], [_overlap_row("sip")], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.direct_full_range_supported is True
    assert decision.chunked_historical_windows_supported is True
    assert decision.selected_windowing_policy == "direct_full_range"


def test_chunked_only_true(v2_spec: IntradayProbeSpec):
    bounded = []
    for w in v2_spec.bounded_window_probes:
        for s in v2_spec.symbols:
            bounded.append(_base_v2(probe_id=f"{w.id}-{s}-sip-rep1", symbol=s, method="sip", threshold_result="passed", date_bound_classification="honored_exactly", primary_session_bars=78, raw_candle_count=78))
    decision = _build_decision(v2_spec, bounded, [_repeat_row("sip")], [], [_overlap_row("sip")], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.direct_full_range_supported is False
    assert decision.chunked_historical_windows_supported is True
    assert decision.selected_windowing_policy == "bounded_monthly_chunks"


def test_neither_direct_nor_chunked(v2_spec: IntradayProbeSpec):
    r = _base_v2(threshold_result="failed", raw_candle_count=0)
    decision = _build_decision(v2_spec, [r], [], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.direct_full_range_supported is False
    assert decision.chunked_historical_windows_supported is False
    assert decision.selected_windowing_policy == "none"


# ---------------------------------------------------------------------------
# Candidate feed gating
# ---------------------------------------------------------------------------


def test_sip_passes_can_approve(v2_spec: IntradayProbeSpec):
    r = _base_v2(method="sip", timestamp_semantics_classification="bar_start")
    decision = _build_decision(v2_spec, [r], [_repeat_row("sip")], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.approved_for_intra_001_five_minute_ohlcv is True
    assert decision.selected_feed == "sip"


def test_sip_fails_iex_passes_does_not_approve(v2_spec: IntradayProbeSpec):
    iex = _base_v2(method="iex", timestamp_semantics_classification="bar_start", regular_session_coverage_pct=100.0)
    decision = _build_decision(v2_spec, [iex], [], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.approved_for_intra_001_five_minute_ohlcv is False
    assert decision.selected_feed == ""


def test_iex_cannot_become_selected_feed(v2_spec: IntradayProbeSpec):
    iex = _base_v2(method="iex", timestamp_semantics_classification="bar_start", regular_session_coverage_pct=100.0)
    decision = _build_decision(v2_spec, [iex], [], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.selected_feed != "iex"


# ---------------------------------------------------------------------------
# Regular-session quality scope
# ---------------------------------------------------------------------------

def _session_primary_tss(spec: IntradayProbeSpec, cal: Any, d: date) -> list[pd.Timestamp]:
    return sorted(_grid(spec, cal, d)["grid"])


def _make_alpaca_bars(tss: list[pd.Timestamp], volumes: list[int] | None = None) -> list[dict]:
    candles = []
    for i, ts in enumerate(tss):
        v = 1000 if volumes is None else volumes[i]
        candles.append({
            "t": ts.tz_convert(UTC).isoformat().replace("+00:00", "Z"),
            "o": 100.0,
            "h": 101.0,
            "l": 99.0,
            "c": 100.5,
            "v": v,
        })
    return candles


def test_zero_volume_in_extended_hours_does_not_fail_candidate_grid(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(d, d, v2_spec.timezone)
    primary_tss = _session_primary_tss(v2_spec, cal, d)
    open_utc = cal.session_open(d).tz_convert("UTC")
    pre_market = open_utc - pd.Timedelta(minutes=5)
    candles = _make_alpaca_bars([pre_market] + primary_tss, volumes=[0] + [1000] * len(primary_tss))
    rec = _analyze_request(
        None, 200, candles, "SPY", "sip", start_utc, end_utc, d, d, cal, v2_spec,
        "test", 1, None, "none", provider="alpaca",
        page_info={"page_count": 1, "pagination_complete": True, "repeated_page_token": False, "pagination_cycle_detected": False, "page_bar_counts": [len(candles)], "token_sequence_sha256": "x"},
    )
    assert rec.regular_session_zero_volume_bars == 0
    assert rec.zero_volume_bars == 1
    assert rec.threshold_result == "passed"



def test_regular_session_zero_volume_threshold_fails(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(d, d, v2_spec.timezone)
    primary_tss = _session_primary_tss(v2_spec, cal, d)
    volumes = [0] * (len(primary_tss) // 2) + [1000] * (len(primary_tss) - len(primary_tss) // 2)
    candles = _make_alpaca_bars(primary_tss, volumes=volumes)
    rec = _analyze_request(
        None, 200, candles, "SPY", "sip", start_utc, end_utc, d, d, cal, v2_spec,
        "test", 1, None, "none", provider="alpaca",
        page_info={"page_count": 1, "pagination_complete": True, "repeated_page_token": False, "pagination_cycle_detected": False, "page_bar_counts": [len(candles)], "token_sequence_sha256": "x"},
    )
    zero_rate = rec.regular_session_zero_volume_rate_pct
    assert zero_rate > v2_spec.maximum_zero_volume_bar_rate_pct
    assert rec.threshold_result == "failed"


def test_invalid_ohlc_in_regular_session_fails_threshold(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(d, d, v2_spec.timezone)
    primary_tss = _session_primary_tss(v2_spec, cal, d)
    candles = _make_alpaca_bars(primary_tss)
    # Make one regular-session candle invalid: high < open.
    candles[10]["h"] = 98.0
    rec = _analyze_request(
        None, 200, candles, "SPY", "sip", start_utc, end_utc, d, d, cal, v2_spec,
        "test", 1, None, "none", provider="alpaca",
        page_info={"page_count": 1, "pagination_complete": True, "repeated_page_token": False, "pagination_cycle_detected": False, "page_bar_counts": [len(candles)], "token_sequence_sha256": "x"},
    )
    assert rec.regular_session_invalid_ohlc_rows == 1
    assert rec.threshold_result == "failed"


def test_missing_regular_session_bar_reduces_coverage(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(d, d, v2_spec.timezone)
    primary_tss = _session_primary_tss(v2_spec, cal, d)
    # Drop the 15:55 bar (last regular session bar)
    primary_tss = primary_tss[:-1]
    candles = _make_alpaca_bars(primary_tss)
    rec = _analyze_request(
        None, 200, candles, "SPY", "sip", start_utc, end_utc, d, d, cal, v2_spec,
        "test", 1, None, "none", provider="alpaca",
        page_info={"page_count": 1, "pagination_complete": True, "repeated_page_token": False, "pagination_cycle_detected": False, "page_bar_counts": [len(candles)], "token_sequence_sha256": "x"},
    )
    assert rec.missing_regular_session_bars == 1
    assert rec.regular_session_coverage_pct < 100.0


def test_close_1600_cannot_replace_missing_1555(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    start_utc, end_utc = _eastern_bounds(d, d, v2_spec.timezone)
    primary_tss = _session_primary_tss(v2_spec, cal, d)
    # Drop 15:55, add 16:00.
    primary_tss = primary_tss[:-1] + [cal.session_close(d).tz_convert("UTC")]
    candles = _make_alpaca_bars(primary_tss)
    rec = _analyze_request(
        None, 200, candles, "SPY", "sip", start_utc, end_utc, d, d, cal, v2_spec,
        "test", 1, None, "none", provider="alpaca",
        page_info={"page_count": 1, "pagination_complete": True, "repeated_page_token": False, "pagination_cycle_detected": False, "page_bar_counts": [len(candles)], "token_sequence_sha256": "x"},
    )
    assert rec.missing_regular_session_bars == 1
    assert rec.regular_session_coverage_pct < 100.0


# ---------------------------------------------------------------------------
# SIP / IEX diagnostics
# ---------------------------------------------------------------------------

def _make_norm_df(tss: list[pd.Timestamp], vol: int = 1000) -> pd.DataFrame:
    idx = pd.DatetimeIndex(tss, name="datetime")
    return pd.DataFrame({
        "open": [100.0] * len(tss),
        "high": [101.0] * len(tss),
        "low": [99.0] * len(tss),
        "close": [100.5] * len(tss),
        "volume": [vol] * len(tss),
    }, index=idx)


def test_sip_iex_paired_diagnostics(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    _eastern_bounds(d, d, v2_spec.timezone)
    primary_tss = _session_primary_tss(v2_spec, cal, d)
    requested_dfs = {
        "window-2024-06-SPY-sip": _make_norm_df(primary_tss, vol=1000),
        "window-2024-06-SPY-iex": _make_norm_df(primary_tss, vol=800),
    }
    recs = [
        _base_v2(probe_id="window-2024-06-SPY-sip-rep1", symbol="SPY", method="sip", requested_eastern_start="2024-06-03T00:00:00-04:00", requested_eastern_end="2024-06-03T23:59:59-04:00"),
        _base_v2(probe_id="window-2024-06-SPY-iex-rep1", symbol="SPY", method="iex", requested_eastern_start="2024-06-03T00:00:00-04:00", requested_eastern_end="2024-06-03T23:59:59-04:00"),
    ]
    rows = _build_alpaca_feed_comparison_rows(recs, requested_dfs, spec=v2_spec)
    assert len(rows) == 1
    row = rows[0]
    assert row["paired_timestamp_count"] == len(primary_tss)
    assert row["overlap_pct"] == 100.0
    assert row["total_sip_volume"] == len(primary_tss) * 1000
    assert row["total_iex_volume"] == len(primary_tss) * 800
    assert row["total_volume_iex_sip_ratio"] == pytest.approx(0.8)
    assert row["median_paired_volume_iex_sip_ratio"] == pytest.approx(0.8)
    assert row["ohlc_diff_flag"] is False
    assert row["ohlc_diff_count"] == 0


def test_sip_iex_diagnostics_ignore_extended_hours(v2_spec: IntradayProbeSpec, cal: Any):
    d = date(2024, 6, 3)
    _eastern_bounds(d, d, v2_spec.timezone)
    primary_tss = _session_primary_tss(v2_spec, cal, d)
    open_utc = cal.session_open(d).tz_convert("UTC")
    extended = [open_utc - pd.Timedelta(minutes=5)]
    requested_dfs = {
        "window-2024-06-SPY-sip": _make_norm_df(extended + primary_tss, vol=1000),
        "window-2024-06-SPY-iex": _make_norm_df(extended + primary_tss, vol=800),
    }
    recs = [
        _base_v2(probe_id="window-2024-06-SPY-sip-rep1", symbol="SPY", method="sip", requested_eastern_start="2024-06-03T00:00:00-04:00", requested_eastern_end="2024-06-03T23:59:59-04:00"),
        _base_v2(probe_id="window-2024-06-SPY-iex-rep1", symbol="SPY", method="iex", requested_eastern_start="2024-06-03T00:00:00-04:00", requested_eastern_end="2024-06-03T23:59:59-04:00"),
    ]
    rows = _build_alpaca_feed_comparison_rows(recs, requested_dfs, spec=v2_spec)
    assert rows[0]["paired_timestamp_count"] == len(primary_tss)


# ---------------------------------------------------------------------------
# Provider contract evidence
# ---------------------------------------------------------------------------

class _FakeAlpacaClient:
    def __init__(self, responses: dict[str, Any]):
        self._responses = responses

    def get_assets(self, *, status: str = "active", asset_class: str | None = None):
        key = f"assets:{status}"
        return self._responses.get(key, (404, []))

    def get_corporate_actions(self, *, symbols: list[str], start: str, end: str):
        return self._responses.get("corporate_actions", (404, {}))


def test_provider_contract_matrix_has_at_least_18_rows(v2_spec: IntradayProbeSpec):
    client = _FakeAlpacaClient({
        "assets:active": (200, [{"symbol": "SPY"}]),
        "assets:inactive": (200, []),
        "corporate_actions": (200, {"corporate_actions": []}),
    })
    _, rows = _evaluate_alpaca_provider_contract(client, v2_spec, records=[], feed_comparison_rows=[])
    assert len(rows) >= 18
    reqs = {r["requirement"] for r in rows}
    assert "ohlcv_five_minute_history" in reqs
    assert "regular_session_history" in reqs
    assert "consolidated_volume_provenance" in reqs
    assert "timestamp_convention" in reqs


def test_active_assets_do_not_prove_pit_universe(v2_spec: IntradayProbeSpec):
    client = _FakeAlpacaClient({
        "assets:active": (200, [{"symbol": "SPY"}]),
        "assets:inactive": (200, []),
        "corporate_actions": (200, {"corporate_actions": []}),
    })
    _, rows = _evaluate_alpaca_provider_contract(client, v2_spec, records=[], feed_comparison_rows=[])
    row = next(r for r in rows if r["requirement"] == "point_in_time_universe")
    assert row["supported"] is False or row["evidence_type"] in ("unproven", "live_evidence")


def test_inactive_assets_listing_does_not_imply_delisted_support(v2_spec: IntradayProbeSpec):
    client = _FakeAlpacaClient({
        "assets:active": (200, [{"symbol": "SPY", "status": "active"}, {"symbol": "DELISTED", "status": "inactive"}]),
        "assets:inactive": (200, [{"symbol": "DELISTED", "status": "inactive"}]),
        "corporate_actions": (200, {"corporate_actions": []}),
    })
    _, rows = _evaluate_alpaca_provider_contract(client, v2_spec, records=[], feed_comparison_rows=[])
    inactive = next(r for r in rows if r["requirement"] == "current_inactive_asset_master")
    delisted = next(r for r in rows if r["requirement"] == "delisted_symbol_handling")
    assert inactive["supported"] is True
    assert delisted["supported"] is False


def test_corporate_action_reachability_does_not_imply_historical_completeness(v2_spec: IntradayProbeSpec):
    client = _FakeAlpacaClient({
        "assets:active": (200, [{"symbol": "SPY"}]),
        "assets:inactive": (200, []),
        "corporate_actions": (200, {"corporate_actions": []}),
    })
    _, rows = _evaluate_alpaca_provider_contract(client, v2_spec, records=[], feed_comparison_rows=[])
    row = next(r for r in rows if r["requirement"] == "corporate_action_historical_completeness")
    assert row["supported"] is False or row["evidence_type"] != "documented_capability"


def test_supported_complete_only_when_every_contract_dimension_true(v2_spec: IntradayProbeSpec):
    r = _base_v2(method="sip", timestamp_semantics_classification="bar_start")
    provider_rows = [
        {"requirement": "ohlcv_history", "supported": True, "evidence_type": "live_evidence"},
        {"requirement": "regular_session_history", "supported": True, "evidence_type": "live_evidence"},
        {"requirement": "consolidated_venue_volume", "supported": True, "evidence_type": "live_evidence"},
        {"requirement": "timestamp_convention", "supported": True, "evidence_type": "live_evidence"},
        {"requirement": "adjustment", "supported": True, "evidence_type": "documented_capability"},
        {"requirement": "corporate_action_endpoint_reachable", "supported": True, "evidence_type": "live_evidence"},
        {"requirement": "corporate_action_historical_completeness", "supported": True, "evidence_type": "documented_capability"},
        {"requirement": "symbol_mapping_asof", "supported": True, "evidence_type": "documented_capability"},
        {"requirement": "inactive_symbol_listing", "supported": True, "evidence_type": "live_evidence"},
        {"requirement": "delisted_symbol_handling", "supported": True, "evidence_type": "documented_capability"},
        {"requirement": "point_in_time_universe", "supported": True, "evidence_type": "documented_capability"},
        {"requirement": "monthly_pit_reproducibility", "supported": True, "evidence_type": "documented_capability"},
        {"requirement": "security_type_stock_etf", "supported": True, "evidence_type": "documented_capability"},
        {"requirement": "security_type_warrant_right_unit_preferred", "supported": True, "evidence_type": "documented_capability"},
        {"requirement": "historical_security_type", "supported": True, "evidence_type": "documented_capability"},
        {"requirement": "current_active_asset_master", "supported": True, "evidence_type": "live_evidence"},
        {"requirement": "current_inactive_asset_master", "supported": True, "evidence_type": "live_evidence"},
        {"requirement": "single_provider_no_mixing", "supported": True, "evidence_type": "documented_capability"},
    ]
    decision = _build_decision(v2_spec, [r], [_repeat_row("sip")], [], [], "a" * 64, "b" * 64, "x" * 40, "", provider_contract_rows=provider_rows)
    assert decision.outcome == "supported_complete"
    assert decision.single_provider_contract_satisfied is True


def test_supported_ohlcv_only_when_contract_incomplete(v2_spec: IntradayProbeSpec):
    r = _base_v2(method="sip", timestamp_semantics_classification="bar_start")
    provider_rows = [
        {"requirement": "ohlcv_history", "supported": True, "evidence_type": "live_evidence"},
        {"requirement": "point_in_time_universe", "supported": False, "evidence_type": "unproven"},
    ]
    decision = _build_decision(v2_spec, [r], [_repeat_row("sip")], [], [], "a" * 64, "b" * 64, "x" * 40, "", provider_contract_rows=provider_rows)
    assert decision.outcome == "supported_ohlcv_only"
    assert decision.single_provider_contract_satisfied is False
    assert decision.methodology_decision_required is True


def test_probe_did_not_mix_providers_can_coexist_with_incomplete_contract(v2_spec: IntradayProbeSpec):
    r = _base_v2(method="sip", timestamp_semantics_classification="bar_start")
    decision = _build_decision(v2_spec, [r], [_repeat_row("sip")], [], [], "a" * 64, "b" * 64, "x" * 40, "", provider_contract_rows=[])
    assert decision.probe_did_not_mix_providers is True
    assert decision.single_provider_contract_satisfied is False


def test_passing_ohlcv_does_not_imply_complete_provider_for_alpaca(v2_spec: IntradayProbeSpec):
    r = _base_v2(method="sip", timestamp_semantics_classification="bar_start", regular_session_coverage_pct=100.0)
    decision = _build_decision(v2_spec, [r], [_repeat_row("sip")], [], [], "a" * 64, "b" * 64, "x" * 40, "", provider_contract_rows=[])
    assert decision.approved_for_intra_001_five_minute_ohlcv is True
    assert decision.approved_as_complete_intra_001_data_source is False


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def test_safe_bundle_contains_pagination_summary_and_no_raw_tokens(v2_spec: IntradayProbeSpec, tmp_path: Path):
    from tradex.research.intraday_data_probe.models import ProbeReport
    r = _base_v2(page_bar_counts=(5000, 5000), token_sequence_sha256="abc123")
    report = ProbeReport(
        records=[r],
        decision=_build_decision(v2_spec, [r], [], [], [], "a" * 64, "b" * 64, "x" * 40, ""),
        method_parity_rows=[],
        repeatability_rows=[],
        chunk_overlap_rows=[],
        summary_rows=[],
        feed_comparison_rows=[],
        provider_contract_rows=[],
    )
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(v2_spec.to_dict()), encoding="utf-8")
    spec_bytes = spec_path.read_bytes()
    artifact_dir = tmp_path / "artifacts"
    write_probe_artifacts(
        report=report,
        spec=v2_spec,
        probe_spec_bytes=spec_bytes,
        strategy_spec_path=tmp_path / "strategy.json",
        artifact_dir=artifact_dir,
        pre_registration_commit="x" * 40,
    )
    safe_dir = next(artifact_dir.iterdir())
    assert (safe_dir / "pagination_summary.csv").exists()
    pagination = (safe_dir / "pagination_summary.csv").read_text(encoding="utf-8")
    assert "page_bar_counts" in pagination
    # Raw token placeholders should not appear; only hashes and counts are written.
    assert "next_page_token" not in pagination or pagination.count("next_page_token") == 0
    assert "raw_token" not in pagination


def test_probe_spec_lock_bytes_equal_source_bytes(v2_spec: IntradayProbeSpec, tmp_path: Path):
    from tradex.research.intraday_data_probe.models import ProbeReport
    r = _base_v2()
    report = ProbeReport(
        records=[r],
        decision=_build_decision(v2_spec, [r], [], [], [], "a" * 64, "b" * 64, "x" * 40, ""),
        method_parity_rows=[],
        repeatability_rows=[],
        chunk_overlap_rows=[],
        summary_rows=[],
        feed_comparison_rows=[],
        provider_contract_rows=[],
    )
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(v2_spec.to_dict()), encoding="utf-8")
    spec_bytes = spec_path.read_bytes()
    artifact_dir = tmp_path / "artifacts"
    write_probe_artifacts(
        report=report,
        spec=v2_spec,
        probe_spec_bytes=spec_bytes,
        strategy_spec_path=tmp_path / "strategy.json",
        artifact_dir=artifact_dir,
        pre_registration_commit="x" * 40,
    )
    safe_dir = next(artifact_dir.iterdir())
    lock_bytes = (safe_dir / "probe_spec.lock.json").read_bytes()
    assert lock_bytes == spec_bytes


def test_v2_report_has_56_sections(v2_spec: IntradayProbeSpec, tmp_path: Path):
    from tradex.research.intraday_data_probe.models import ProbeReport
    r = _base_v2()
    report = ProbeReport(
        records=[r],
        decision=_build_decision(v2_spec, [r], [], [], [], "a" * 64, "b" * 64, "x" * 40, ""),
        method_parity_rows=[],
        repeatability_rows=[],
        chunk_overlap_rows=[],
        summary_rows=[],
        feed_comparison_rows=[],
        provider_contract_rows=[],
    )
    report_path = tmp_path / "report.md"
    write_probe_report(
        report=report,
        spec=v2_spec,
        probe_spec_sha256="b" * 64,
        strategy_spec_sha256="a" * 64,
        pre_registration_commit="x" * 40,
        report_path=report_path,
    )
    text = report_path.read_text(encoding="utf-8")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    # Allow slightly more or exactly 56; the requirement is "at minimum" 56 sections.
    assert len(headings) >= 56


# ---------------------------------------------------------------------------
# Schwab non-regression
# ---------------------------------------------------------------------------

def test_schwab_spec_still_loads_strictly():
    spec, _ = load_probe_spec("docs/research/specs/INTRA-001B-schwab-probe-v1.json")
    assert spec.provider == "schwab"
    assert "alpaca" not in spec.task_id.lower()


def test_schwab_passing_ohlcv_does_not_approve_complete_provider():
    schwab_spec, _ = load_probe_spec("docs/research/specs/INTRA-001B-schwab-probe-v1.json")
    r = _base_v2(probe_id="full-SPY-convenience-rep1", method="convenience_every_five_minutes", timestamp_semantics_classification="undetermined")
    decision = _build_decision(schwab_spec, [r], [], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.approved_as_complete_intra_001_data_source is False


# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------

def test_cli_help_no_credentials_required():
    from tradex.research.intraday_data_probe.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_missing_alpaca_credentials_fail_before_network():
    from tradex.config import DataProviderSettings, TradeXSettings
    from tradex.research.intraday_data_probe.alpaca_client import make_alpaca_client
    settings = TradeXSettings(data=DataProviderSettings(alpaca_api_key="", alpaca_secret_key=""))
    with pytest.raises(OSError, match="ALPACA"):
        make_alpaca_client(settings)


def test_sha256_candles_hides_raw_sensitive_metadata():
    candles = [{"datetime": "2024-06-03T13:30:00Z", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000}]
    h = _sha256_candles(candles, None)
    assert len(h) == 64
    assert "100" not in h


# ---------------------------------------------------------------------------
# v2 review corrections (PR #41)
# ---------------------------------------------------------------------------


def test_v2_decision_schema_fields_populated(v2_spec: IntradayProbeSpec):
    r = _base_v2()
    decision = _build_decision(v2_spec, [r], [_repeat_row("sip")], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.probe_version == 2
    assert decision.target_entitlement == "basic_free"
    assert decision.v1_pre_registration_commit == "286493eceeffd6aec872ce7516bed5d1b0cd304f"
    assert decision.v2_pre_registration_commit == "x" * 40
    assert decision.client_version  # non-empty string (requests==...)
    assert decision.excluded_security_types_supported is False


def test_sip_bar_start_iex_ambiguous_candidate_summary_bar_start_decision_unchanged(v2_spec: IntradayProbeSpec):
    """IEX comparison feed returning ambiguous timestamps must not pull the candidate summary away from bar_start or change core gates."""
    sip = _base_v2(probe_id="full-SPY-sip-rep1", method="sip", timestamp_semantics_classification="bar_start")
    iex = _base_v2(probe_id="full-SPY-iex-rep1", method="iex", timestamp_semantics_classification="ambiguous")
    decision = _build_decision(
        v2_spec,
        [sip, iex],
        [_repeat_row("sip"), _repeat_row("iex")],
        [],
        [],
        "a" * 64,
        "b" * 64,
        "x" * 40,
        "",
    )
    assert decision.candidate_timestamp_semantics == "bar_start"
    assert decision.timestamp_semantics_passed is True
    assert decision.approved_for_intra_001_five_minute_ohlcv is True
    assert decision.direct_full_range_supported is True
    # outcome stays supported_ohlcv_only because provider-contract rows are empty (single-provider contract not met)
    assert decision.outcome == "supported_ohlcv_only"


def test_inactive_asset_listing_supported_uses_inactive_master_row():
    """inactive_asset_listing_supported must be driven by the current_inactive_asset_master contract row."""
    from tradex.research.intraday_data_probe.spec import load_probe_spec
    spec, _ = load_probe_spec("docs/research/specs/INTRA-001B-alpaca-probe-v2.json")
    r = _base_v2()
    provider_rows = [
        {"requirement": "current_active_asset_master", "supported": True, "evidence_type": "live_evidence", "limitation": "", "source": ""},
        {"requirement": "current_inactive_asset_master", "supported": False, "evidence_type": "live_evidence", "limitation": "", "source": ""},
    ]
    decision = _build_decision(spec, [r], [_repeat_row("sip")], [], [], "a" * 64, "b" * 64, "x" * 40, "", provider_contract_rows=provider_rows)
    assert decision.inactive_asset_listing_supported is False


def test_inactive_asset_listing_supported_true_when_inactive_master_true():
    spec, _ = load_probe_spec("docs/research/specs/INTRA-001B-alpaca-probe-v2.json")
    r = _base_v2()
    provider_rows = [
        {"requirement": "current_active_asset_master", "supported": True, "evidence_type": "live_evidence", "limitation": "", "source": ""},
        {"requirement": "current_inactive_asset_master", "supported": True, "evidence_type": "live_evidence", "limitation": "", "source": ""},
    ]
    decision = _build_decision(spec, [r], [_repeat_row("sip")], [], [], "a" * 64, "b" * 64, "x" * 40, "", provider_contract_rows=provider_rows)
    assert decision.inactive_asset_listing_supported is True


def test_v2_no_provider_mixing_legacy_field_deprecated(v2_spec: IntradayProbeSpec):
    """The legacy no_provider_mixing_contract_satisfied field must not appear in v2 decision serialization."""
    r = _base_v2()
    decision = _build_decision(v2_spec, [r], [_repeat_row("sip")], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.probe_did_not_mix_providers is True
    assert decision.single_provider_contract_satisfied is False
    assert "no_provider_mixing_contract_satisfied" not in decision.to_dict()


def test_v2_method_parity_not_applicable_for_alpaca(v2_spec: IntradayProbeSpec):
    """Alpaca has no Schwab-style method pairs; method_parity_passed must be None, not True."""
    r = _base_v2()
    decision = _build_decision(v2_spec, [r], [_repeat_row("sip")], [], [], "a" * 64, "b" * 64, "x" * 40, "")
    assert decision.method_parity_applicable is False
    assert decision.method_parity_passed is None


def test_v2_provider_contract_documented_capability_cites_alpaca_docs(v2_spec: IntradayProbeSpec):
    """Rows classified as documented_capability must include official Alpaca doc URLs and a review date."""
    client = AlpacaRestClient("PKDUMMY", "dummy_secret")

    def _trading_get(path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
        if path == "/v2/assets":
            return 200, [{"symbol": "SPY", "asset_class": "us_equity"}]
        if path == "/v1/corporate-actions":
            return 200, {"actions": []}
        return 0, {}

    client._trading_get = _trading_get  # type: ignore[assignment]
    r = _base_v2()
    _, rows = _evaluate_alpaca_provider_contract(client, v2_spec, records=[r], feed_comparison_rows=[])
    by_req = {row["requirement"]: row for row in rows}
    for req in ("adjustment_raw", "symbol_mapping_asof"):
        row = by_req[req]
        assert row["evidence_type"] == "documented_capability"
        assert "docs.alpaca.markets/us/reference/stockbars" in row["source"]
        assert "reviewed" in row["source"]
