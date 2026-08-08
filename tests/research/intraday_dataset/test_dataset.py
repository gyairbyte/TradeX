"""Credential-free tests for INTRA-001B-DATASET-V1 pipeline."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from tradex.research.intraday_dataset import spec as spec_module
from tradex.research.intraday_dataset.alpaca_client import DatasetAlpacaClient
from tradex.research.intraday_dataset.dataset import (
    _aggregate_to_daily,
    _build_active_eligible,
    _detect_invalid_ohlc,
    _duplicate_tickers_in_rows,
    _filter_regular_session,
    _is_regular_close,
    _load_xnys,
    _month_from_pit,
    _prior_n_sessions,
    _ranking_timeframe_parity,
    _regular_session_grid,
    _sessions_in_range,
    _split_name_for_month,
    run_build_universe,
    run_fetch_ohlcv,
    run_plan,
    run_validate,
)
from tradex.research.intraday_dataset.models import ReferenceSnapshot


@pytest.fixture
def plan():
    plan, _ = spec_module.load_dataset_plan("docs/research/specs/INTRA-001B-dataset-v1.json")
    return plan


@pytest.fixture
def output_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def _make_daily(symbol: str, sessions: list[pd.Timestamp], close: float, volume: float) -> pd.DataFrame:
    n = len(sessions)
    base = np.full(n, close) * (1 + np.arange(n) * 0.001)
    dt = pd.to_datetime(sessions) + pd.Timedelta(hours=4, minutes=0)
    if dt.tz is None:
        dt = dt.tz_localize("UTC")
    else:
        dt = dt.tz_convert("UTC")
    df = pd.DataFrame({
        "open": base,
        "high": base * 1.01,
        "low": base * 0.99,
        "close": base,
        "volume": volume,
    }, index=dt)
    return df.sort_index()


def _make_5min(symbol: str, sessions: list[pd.Timestamp], close: float, volume: float) -> pd.DataFrame:
    grid = _regular_session_grid()
    n_sessions = len(sessions)
    n_bars = len(grid)
    session_idx = np.repeat(np.arange(n_sessions), n_bars)
    bar_idx = np.tile(np.arange(n_bars), n_sessions)
    base = close * (1 + session_idx * 0.001)
    session_dates = pd.to_datetime([s.date() for s in sessions])
    bar_times = pd.to_timedelta(grid.hour, unit="h") + pd.to_timedelta(grid.minute, unit="m")
    bar_datetimes = session_dates[session_idx] + bar_times[bar_idx]
    bar_datetimes = bar_datetimes.tz_localize("America/New_York").tz_convert("UTC")
    df = pd.DataFrame({
        "open": base,
        "high": base * 1.005,
        "low": base * 0.995,
        "close": base,
        "volume": volume / n_bars,
    }, index=bar_datetimes)
    return df.sort_index()


def _make_30min(symbol: str, sessions: list[pd.Timestamp], close: float, volume: float) -> pd.DataFrame:
    grid = pd.date_range("09:30", "15:30", freq="30min", tz="America/New_York")
    n_sessions = len(sessions)
    n_bars = len(grid)
    session_idx = np.repeat(np.arange(n_sessions), n_bars)
    bar_idx = np.tile(np.arange(n_bars), n_sessions)
    base = close * (1 + session_idx * 0.001)
    session_dates = pd.to_datetime([s.date() for s in sessions])
    bar_times = pd.to_timedelta(grid.hour, unit="h") + pd.to_timedelta(grid.minute, unit="m")
    bar_datetimes = session_dates[session_idx] + bar_times[bar_idx]
    bar_datetimes = bar_datetimes.tz_localize("America/New_York").tz_convert("UTC")
    df = pd.DataFrame({
        "open": base,
        "high": base * 1.005,
        "low": base * 0.995,
        "close": base,
        "volume": volume / n_bars,
    }, index=bar_datetimes)
    return df.sort_index()


class FakeAlpacaClient:
    """Returns deterministic bars without network calls."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.calls = 0
        self.close = 100.0
        self.volume = 60_000_000.0

    def get_bars(self, symbols, start_utc, end_utc, *, feed, timeframe, adjustment, asof=None, sort="asc", limit=10000, sleeper=None):
        self.calls += 1
        sessions = _sessions_in_range(_load_xnys(), start_utc, end_utc)
        dfs: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            if timeframe == "1Day":
                dfs[sym.upper()] = _make_daily(sym, sessions, self.close, self.volume)
            elif timeframe == "30Min":
                dfs[sym.upper()] = _make_30min(sym, sessions, self.close, self.volume)
            else:
                dfs[sym.upper()] = _make_5min(sym, sessions, self.close, self.volume)
        bar_count = sum(len(df) for df in dfs.values())
        return dfs, {
            "page_count": 1,
            "logical_calls": 1,
            "http_pages": 1,
            "http_attempts": 1,
            "http_429s": 0,
            "http_errors": 0,
            "next_page_token_present": False,
            "pagination_complete": True,
            "repeated_page_token": False,
            "pagination_cycle_detected": False,
            "retry_after_seconds": None,
            "safe_error_classification": "none",
            "page_bar_counts": [bar_count],
            "token_hashes": ["abc"],
            "token_sequence_sha256": "abc",
            "http_status": 200,
            "response_symbols": [s.upper() for s in symbols],
        }


def _write_fake_reference_snapshots(output_dir: Path, plan) -> None:
    ref_dir = output_dir / "reference_snapshots"
    ref_dir.mkdir(parents=True, exist_ok=True)
    taxonomy = {
        "mapping": {"CS": "common_stock", "ETF": "etf"},
        "rows": [],
        "fetched_at": datetime.now(UTC).isoformat(),
    }
    (ref_dir / "taxonomy.json").write_text(json.dumps(taxonomy), encoding="utf-8")
    for pit in plan.monthly_pit_dates:
        for state in ("active", "inactive"):
            rows = []
            for i in range(60):
                ticker = f"STOCK{i:03d}"
                rows.append({
                    "ticker": ticker,
                    "type": "CS",
                    "primary_exchange": "XNYS",
                    "active": state == "active",
                })
            # Add one duplicate and one excluded type/exchange.
            rows.append({"ticker": "DUPLICATE", "type": "CS", "primary_exchange": "XNYS"})
            rows.append({"ticker": "DUPLICATE", "type": "CS", "primary_exchange": "XNYS"})
            rows.append({"ticker": "PREFERRED", "type": "PFD", "primary_exchange": "XNYS"})
            rows.append({"ticker": "OTCTICK", "type": "CS", "primary_exchange": "OTCM"})
            rows.append({"ticker": "BADTICKER", "type": "", "primary_exchange": "XNYS"})
            payload = {
                "pit_date": pit,
                "state": state,
                "row_count": len(rows),
                "raw_sha256": "fake",
                "canonical_sha256": "fake",
                "duplicate_details": [],
                "observations": [{
                    "provider": "massive",
                    "pit_date": pit,
                    "state": state,
                    "requested_at": datetime.now(UTC).isoformat(),
                    "elapsed_seconds": 0.1,
                    "row_count": len(rows),
                    "raw_sha256": "fake",
                    "http_status": 200,
                    "error": "",
                    "page_count": 1,
                    "first_page_count": len(rows),
                    "last_page_count": len(rows),
                    "pagination_complete": True,
                    "max_pages_reached": False,
                    "repeated_cursor_detected": False,
                    "cycle_detected": False,
                    "unexpected_next_url": False,
                    "full_snapshot_sha256": "fake",
                    "canonical_ticker_count": len(rows),
                    "blank_ticker_count": 0,
                    "duplicate_ticker_count": 1,
                    "unresolved_duplicate_count": 0,
                }],
                "pages": [],
                "rows": rows,
                "fetched_at": datetime.now(UTC).isoformat(),
            }
            (ref_dir / f"{pit}_{state}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_plan_hashes(plan):
    assert plan.original_strategy_spec_sha256 == "09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464"
    assert len(plan.monthly_pit_dates) == 12


def test_month_from_pit():
    assert _month_from_pit("2024-12-31") == "2025-01"
    assert _month_from_pit("2025-01-31") == "2025-02"
    assert _month_from_pit("2025-11-30") == "2025-12"


def test_prior_n_sessions():
    calendar = _load_xnys()
    first = pd.Timestamp("2025-01-02")  # first trading day of Jan 2025
    sessions = _prior_n_sessions(calendar, first, 20)
    assert len(sessions) == 20
    assert all(s < pd.Timestamp("2025-01-02", tz="America/New_York") for s in sessions)


def test_sessions_in_range():
    calendar = _load_xnys()
    start = pd.Timestamp("2025-01-02", tz="America/New_York").tz_convert("UTC")
    # End must cover the regular-session close to include the last day.
    end = pd.Timestamp("2025-01-31 16:00", tz="America/New_York").tz_convert("UTC")
    sessions = _sessions_in_range(calendar, start, end)
    assert 20 <= len(sessions) <= 22
    assert all(s >= start.tz_convert("America/New_York") for s in sessions)
    assert pd.Timestamp("2025-01-31", tz="America/New_York") in sessions


def test_regular_session_grid():
    grid = _regular_session_grid()
    assert len(grid) == 78
    assert grid[0].hour == 9 and grid[0].minute == 30
    assert grid[-1].hour == 15 and grid[-1].minute == 55


def test_is_regular_close():
    assert _is_regular_close(pd.Timestamp("2025-01-02 16:00", tz="America/New_York"))
    assert not _is_regular_close(pd.Timestamp("2025-01-02 13:00", tz="America/New_York"))


def test_duplicate_tickers_in_rows():
    rows = [
        {"ticker": "A"},
        {"ticker": "A"},
        {"ticker": "B"},
    ]
    dups = _duplicate_tickers_in_rows(rows)
    assert dups == {"A"}


def test_build_active_eligible(plan, output_dir):
    _write_fake_reference_snapshots(output_dir, plan)
    mapping = {"CS": "common_stock", "PFD": "preferred_stock"}
    snap = ReferenceSnapshot(
        pit_date="2025-01-31",
        state="active",
        rows=[
            {"ticker": "A", "type": "CS", "primary_exchange": "XNYS"},
            {"ticker": "A", "type": "CS", "primary_exchange": "XNYS"},
            {"ticker": "B", "type": "CS", "primary_exchange": "XNAS"},
            {"ticker": "C", "type": "PFD", "primary_exchange": "XNYS"},
            {"ticker": "D", "type": "CS", "primary_exchange": "OTCM"},
            {"ticker": "", "type": "CS", "primary_exchange": "XNYS"},
        ],
        observations=[],
        pages=[],
        raw_sha256="fake",
        canonical_sha256="fake",
        duplicate_details=[],
    )
    eligible, exclusions, dups = _build_active_eligible(snap, mapping, plan.conservative_universe_controls)
    tickers = {r["ticker"] for r in eligible}
    assert tickers == {"B"}
    assert dups == {"A"}
    reasons = {e["reason"] for e in exclusions}
    assert "duplicate_symbol" in reasons
    assert any("security_type" in r for r in reasons)
    assert any("exchange_not_allowed" in r for r in reasons)
    assert any("blank_ticker" in r for r in reasons)


def test_ranking_timeframe_parity(plan):
    calendar = _load_xnys()
    client = FakeAlpacaClient()
    ok, msg = _ranking_timeframe_parity(
        client,
        calendar,
        ["SPY"],
        "2024-06-03",
        "2024-06-07",
        0.1,
    )
    assert ok, msg


def test_filter_regular_session(plan, output_dir):
    calendar = _load_xnys()
    sessions = _prior_n_sessions(calendar, pd.Timestamp("2025-01-02"), 3)
    df = _make_5min("A", sessions, 100.0, 100_000_000.0)
    # Add premarket and after-hours bars.
    pre = pd.DataFrame([{
        "datetime": sessions[0] - pd.Timedelta(hours=2),
        "open": 99,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": 1000,
    }])
    pre["datetime"] = pd.to_datetime(pre["datetime"], utc=True)
    pre = pre.set_index("datetime")
    post = pd.DataFrame([{
        "datetime": sessions[0] + pd.Timedelta(hours=8),
        "open": 99,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": 1000,
    }])
    post["datetime"] = pd.to_datetime(post["datetime"], utc=True)
    post = post.set_index("datetime")
    df = pd.concat([df, pre, post]).sort_index()
    filtered, counts = _filter_regular_session(df, calendar)
    assert len(filtered) == 3 * 78
    assert counts["premarket"] >= 1
    assert counts["after_hours"] >= 1


def test_detect_invalid_ohlc():
    df = pd.DataFrame({
        "open": [100.0, 100.0],
        "high": [101.0, 99.0],
        "low": [99.0, 100.0],
        "close": [100.0, 100.0],
        "volume": [1000, 1000],
    }, index=pd.date_range("2025-01-02 09:30", periods=2, freq="5min", tz="America/New_York"))
    assert _detect_invalid_ohlc(df) == 1


def test_aggregate_to_daily():
    calendar = _load_xnys()
    sessions = _prior_n_sessions(calendar, pd.Timestamp("2025-01-02"), 5)
    df5 = _make_5min("A", sessions, 100.0, 78_000_000.0)
    daily = _aggregate_to_daily({"A": df5}, calendar)
    assert "A" in daily
    assert 4 <= len(daily["A"]) <= 5
    assert abs(float(daily["A"]["volume"].sum()) - 78_000_000.0 * len(daily["A"])) < 1


def test_build_universe_with_fake_client(monkeypatch, plan, output_dir):
    _write_fake_reference_snapshots(output_dir, plan)
    run_plan(plan, output_dir)
    monkeypatch.setattr("tradex.research.intraday_dataset.dataset.DatasetAlpacaClient", FakeAlpacaClient)
    run_build_universe(plan, output_dir, "dummy", "dummy")
    universe = pd.read_csv(output_dir / "universe" / "universe_manifest.csv")
    stocks = universe[(universe["stratum"] == "stock") & (universe["included"] == True)]
    assert len(stocks) == 12 * 50
    etfs = universe[(universe["stratum"] == "etf") & (universe["included"] == True)]
    assert len(etfs) == 12 * 13
    first_month = stocks[stocks["effective_month"] == "2025-01"]
    assert len(first_month) == 50
    assert all(first_month["prior_close"] >= 5.0)
    assert all(first_month["median_prior_20_dollar_volume"] >= 50_000_000.0)


def test_fetch_ohlcv_with_fake_client(monkeypatch, plan, output_dir):
    _write_fake_reference_snapshots(output_dir, plan)
    run_plan(plan, output_dir)
    monkeypatch.setattr("tradex.research.intraday_dataset.dataset.DatasetAlpacaClient", FakeAlpacaClient)
    run_build_universe(plan, output_dir, "dummy", "dummy")
    run_fetch_ohlcv(plan, output_dir, "dummy", "dummy")
    ohlcv_manifest = pd.read_csv(output_dir / "ohlcv" / "ohlcv_manifest.csv")
    assert len(ohlcv_manifest) == 12 * (50 + 13)
    quality = pd.read_csv(output_dir / "ohlcv" / "data_quality.csv")
    assert len(quality) == len(ohlcv_manifest)
    assert (quality["missing_bar_rate_pct"] <= 5.0).all()
    assert (quality["zero_volume_bar_rate_pct"] <= 10.0).all()
    assert (quality["duplicate_bar_rate_pct"] <= 1.0).all()


def test_validate_and_finalize(plan, output_dir, monkeypatch):
    _write_fake_reference_snapshots(output_dir, plan)
    run_plan(plan, output_dir)
    monkeypatch.setattr("tradex.research.intraday_dataset.dataset.DatasetAlpacaClient", FakeAlpacaClient)
    run_build_universe(plan, output_dir, "dummy", "dummy")
    run_fetch_ohlcv(plan, output_dir, "dummy", "dummy")
    summary = run_validate(plan, output_dir)
    assert summary["disposition"] == "valid"


def test_plan_validation_catches_bad_sha():
    bad = json.loads(Path("docs/research/specs/INTRA-001B-dataset-v1.json").read_text())
    bad["original_strategy_spec"]["sha256"] = "bad"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(bad, f)
        path = f.name
    try:
        with pytest.raises(spec_module.SpecValidationError):
            spec_module.load_dataset_plan(path)
    finally:
        os.unlink(path)


def test_no_provider_calls_on_import():
    """Importing the module must not trigger network or credential access."""
    # Re-importing already happened in fixtures; just assert client init requires keys.
    with pytest.raises(OSError):
        DatasetAlpacaClient("", "")


def test_split_name_for_month(plan):
    assert _split_name_for_month(plan, "2025-01") == "development"
    assert _split_name_for_month(plan, "2025-06") == "development"
    assert _split_name_for_month(plan, "2025-07") == "validation"
    assert _split_name_for_month(plan, "2025-09") == "validation"
    assert _split_name_for_month(plan, "2025-10") == "holdout"
    assert _split_name_for_month(plan, "2025-12") == "holdout"


def test_sessions_in_range_no_next_month_overlap():
    """March 2025 must not include 2025-04-01 as an expected session."""
    calendar = _load_xnys()
    start = pd.Timestamp("2025-03-01", tz="America/New_York").tz_convert("UTC")
    end = (pd.Timestamp("2025-03-31", tz="America/New_York") + pd.Timedelta(hours=24)).tz_convert("UTC")
    sessions = _sessions_in_range(calendar, start, end)
    assert pd.Timestamp("2025-04-01", tz="America/New_York") not in sessions
    # 2025-03-31 is a regular session and should be included.
    assert pd.Timestamp("2025-03-31", tz="America/New_York") in sessions


def test_filter_regular_session_rejects_off_grid():
    calendar = _load_xnys()
    sessions = _prior_n_sessions(calendar, pd.Timestamp("2025-01-02"), 1)
    df = _make_5min("A", sessions, 100.0, 78_000_000.0)
    # Insert an off-grid bar at 09:33 (not a 5-minute bar start)
    bad_ts = pd.Timestamp(sessions[0].date()) + pd.Timedelta(hours=9, minutes=33)
    bad_ts = bad_ts.tz_localize("America/New_York").tz_convert("UTC")
    bad = pd.DataFrame([{
        "datetime": bad_ts,
        "open": 99,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": 1000,
    }])
    bad["datetime"] = pd.to_datetime(bad["datetime"], utc=True)
    bad = bad.set_index("datetime")
    df = pd.concat([df, bad]).sort_index()
    filtered, counts = _filter_regular_session(df, calendar)
    assert counts["off_grid"] >= 1
    assert len(filtered) == 78


def test_duplicate_and_malformed_rows_observable(plan, output_dir, monkeypatch):
    _write_fake_reference_snapshots(output_dir, plan)
    run_plan(plan, output_dir)
    monkeypatch.setattr("tradex.research.intraday_dataset.dataset.DatasetAlpacaClient", FakeAlpacaClient)
    run_build_universe(plan, output_dir, "dummy", "dummy")
    run_fetch_ohlcv(plan, output_dir, "dummy", "dummy")
    quality = pd.read_csv(output_dir / "ohlcv" / "data_quality.csv")
    assert "pre_dedup_duplicate_bars" in quality.columns
    assert "malformed_rows" in quality.columns


def test_incomplete_ranking_pagination_fails_closed(plan, output_dir, monkeypatch):
    class BrokenAlpacaClient(FakeAlpacaClient):
        def get_bars(self, *args, **kwargs):
            dfs, meta = super().get_bars(*args, **kwargs)
            meta["pagination_complete"] = False
            return dfs, meta

    _write_fake_reference_snapshots(output_dir, plan)
    run_plan(plan, output_dir)
    monkeypatch.setattr("tradex.research.intraday_dataset.dataset.DatasetAlpacaClient", BrokenAlpacaClient)
    with pytest.raises(RuntimeError, match="Ranking pagination incomplete"):
        run_build_universe(plan, output_dir, "dummy", "dummy")


def test_incomplete_ohlcv_pagination_marks_invalid(plan, output_dir, monkeypatch):
    class BrokenAlpacaClient(FakeAlpacaClient):
        def get_bars(self, *args, **kwargs):
            dfs, meta = super().get_bars(*args, **kwargs)
            if kwargs.get("timeframe") == "5Min":
                meta["pagination_complete"] = False
            return dfs, meta

    _write_fake_reference_snapshots(output_dir, plan)
    run_plan(plan, output_dir)
    monkeypatch.setattr("tradex.research.intraday_dataset.dataset.DatasetAlpacaClient", BrokenAlpacaClient)
    run_build_universe(plan, output_dir, "dummy", "dummy")
    run_fetch_ohlcv(plan, output_dir, "dummy", "dummy")
    summary = run_validate(plan, output_dir)
    assert summary["disposition"] == "invalid"


def test_incomplete_massive_snapshot_fails_closed(plan, output_dir, monkeypatch):
    _write_fake_reference_snapshots(output_dir, plan)
    # Corrupt one active snapshot to be incomplete.
    snap_path = output_dir / "reference_snapshots" / "2025-01-31_active.json"
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    data["observations"][0]["pagination_complete"] = False
    snap_path.write_text(json.dumps(data), encoding="utf-8")
    run_plan(plan, output_dir)
    monkeypatch.setattr("tradex.research.intraday_dataset.dataset.DatasetAlpacaClient", FakeAlpacaClient)
    with pytest.raises(RuntimeError, match="Active snapshot for .* is incomplete"):
        run_build_universe(plan, output_dir, "dummy", "dummy")


def test_monthly_5pct_rejection_calculation(plan, output_dir, monkeypatch):
    _write_fake_reference_snapshots(output_dir, plan)
    run_plan(plan, output_dir)
    monkeypatch.setattr("tradex.research.intraday_dataset.dataset.DatasetAlpacaClient", FakeAlpacaClient)
    run_build_universe(plan, output_dir, "dummy", "dummy")
    run_fetch_ohlcv(plan, output_dir, "dummy", "dummy")
    summary = run_validate(plan, output_dir)
    assert "monthly_rejections" in summary
    for stats in summary["monthly_rejections"].values():
        assert "rejected_pct" in stats
        assert "breaches_5pct_threshold" in stats
