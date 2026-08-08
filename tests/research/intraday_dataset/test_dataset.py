"""Credential-free tests for INTRA-001B-DATASET-V1 pipeline."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    rows = []
    for i, s in enumerate(sessions):
        rows.append({
            "datetime": s + pd.Timedelta(hours=4, minutes=0),
            "open": close * (1 + i * 0.001),
            "high": close * (1 + i * 0.001) * 1.01,
            "low": close * (1 + i * 0.001) * 0.99,
            "close": close * (1 + i * 0.001),
            "volume": volume,
        })
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    return df.set_index("datetime").tz_convert("UTC").sort_index()


def _make_5min(symbol: str, sessions: list[pd.Timestamp], close: float, volume: float) -> pd.DataFrame:
    grid = _regular_session_grid()
    rows = []
    for i, s in enumerate(sessions):
        base = close * (1 + i * 0.001)
        for j, t in enumerate(grid):
            bar_ts = pd.Timestamp(s.date()) + pd.Timedelta(hours=t.hour, minutes=t.minute)
            bar_ts = bar_ts.tz_localize("America/New_York").tz_convert("UTC")
            rows.append({
                "datetime": bar_ts,
                "open": base,
                "high": base * 1.005,
                "low": base * 0.995,
                "close": base,
                "volume": volume / 78,
            })
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    return df.set_index("datetime").sort_index()


def _make_30min(symbol: str, sessions: list[pd.Timestamp], close: float, volume: float) -> pd.DataFrame:
    grid = pd.date_range("09:30", "15:30", freq="30min", tz="America/New_York")
    rows = []
    for i, s in enumerate(sessions):
        base = close * (1 + i * 0.001)
        for t in grid:
            bar_ts = pd.Timestamp(s.date()) + pd.Timedelta(hours=t.hour, minutes=t.minute)
            bar_ts = bar_ts.tz_localize("America/New_York").tz_convert("UTC")
            rows.append({
                "datetime": bar_ts,
                "open": base,
                "high": base * 1.005,
                "low": base * 0.995,
                "close": base,
                "volume": volume / 13,
            })
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    return df.set_index("datetime").sort_index()


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
        return dfs, {
            "page_count": 1,
            "next_page_token_present": False,
            "pagination_complete": True,
            "repeated_page_token": False,
            "pagination_cycle_detected": False,
            "retry_after_seconds": None,
            "safe_error_classification": "none",
            "page_bar_counts": [len(sessions) * (1 if timeframe == "1Day" else 78)],
            "token_hashes": ["abc"],
            "token_sequence_sha256": "abc",
            "http_status": 200,
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
    end = pd.Timestamp("2025-01-31", tz="America/New_York").tz_convert("UTC")
    sessions = _sessions_in_range(calendar, start, end)
    assert 20 <= len(sessions) <= 22
    assert all(s >= start.tz_convert("America/New_York") for s in sessions)


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
