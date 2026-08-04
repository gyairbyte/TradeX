"""Tests for offline snapshot creation and loading."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import ClassVar
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from tradex.research.pattern_validation.models import ValidationError
from tradex.research.pattern_validation.snapshot import create_snapshot, load_snapshot


def test_snapshot_writes_manifest_and_csvs(tmp_path, tiny_study_dates):
    out = tmp_path / "snap"
    manifest_path = create_snapshot(
        tickers=["AAPL", "MSFT"],
        start=tiny_study_dates["start_date"],
        end=tiny_study_dates["end_date"],
        output_dir=out,
        splits=tiny_study_dates["splits"],
        fetch_fn=_synthetic_fetcher,
        overwrite=True,
    )
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(data["successful_tickers"]) == {"AAPL", "MSFT"}
    assert (out / "AAPL.csv").exists()
    assert (out / "MSFT.csv").exists()


def test_snapshot_refuses_overwrite_without_flag(tmp_path, tiny_study_dates):
    out = tmp_path / "snap"
    out.mkdir()
    with pytest.raises(ValidationError, match="already exists"):
        create_snapshot(
            tickers=["AAPL"],
            start=tiny_study_dates["start_date"],
            end=tiny_study_dates["end_date"],
            output_dir=out,
            splits=tiny_study_dates["splits"],
            fetch_fn=_synthetic_fetcher,
        )


def test_snapshot_records_failed_tickers(tmp_path, tiny_study_dates):
    out = tmp_path / "snap"

    def failing_fetcher(ticker, start, end, provider):
        raise ValueError("network unavailable")

    manifest_path = create_snapshot(
        tickers=["AAPL"],
        start=tiny_study_dates["start_date"],
        end=tiny_study_dates["end_date"],
        output_dir=out,
        splits=tiny_study_dates["splits"],
        fetch_fn=failing_fetcher,
        overwrite=True,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["failed_tickers"] == ["AAPL"]
    assert "ValueError" in manifest["failure_categories"]


def test_load_snapshot_roundtrip(tmp_path, tiny_study_dates):
    out = tmp_path / "snap"
    manifest_path = create_snapshot(
        tickers=["AAPL"],
        start=tiny_study_dates["start_date"],
        end=tiny_study_dates["end_date"],
        output_dir=out,
        splits=tiny_study_dates["splits"],
        fetch_fn=_synthetic_fetcher,
        overwrite=True,
    )
    manifest, bars = load_snapshot(manifest_path)
    assert "AAPL" in bars
    assert len(bars["AAPL"]) > 0
    assert manifest.requested_tickers == ("AAPL",)


def test_load_snapshot_fails_on_checksum_mismatch(tmp_path, tiny_study_dates):
    out = tmp_path / "snap"
    manifest_path = create_snapshot(
        tickers=["AAPL"],
        start=tiny_study_dates["start_date"],
        end=tiny_study_dates["end_date"],
        output_dir=out,
        splits=tiny_study_dates["splits"],
        fetch_fn=_synthetic_fetcher,
        overwrite=True,
    )
    # Corrupt the CSV on disk by mutating a stable string in the header.
    csv_path = out / "AAPL.csv"
    csv_path.write_text(csv_path.read_text(encoding="utf-8").replace("datetime", "datetimex"), encoding="utf-8")
    with pytest.raises(ValidationError, match="checksum mismatch"):
        load_snapshot(manifest_path)


def test_snapshot_validates_ohlc_invariants(tmp_path, tiny_study_dates):
    def bad_fetcher(ticker, start, end, provider):
        df = _synthetic_fetcher(ticker, start, end, provider).copy()
        # Create an OHLC inconsistency: high below close.
        df.loc[df.index[10], "high"] = df.loc[df.index[10], "close"] * 0.5
        return df

    out = tmp_path / "snap"
    create_snapshot(
        tickers=["AAPL"],
        start=tiny_study_dates["start_date"],
        end=tiny_study_dates["end_date"],
        output_dir=out,
        splits=tiny_study_dates["splits"],
        fetch_fn=bad_fetcher,
        overwrite=True,
    )
    raw = _synthetic_fetcher("AAPL", tiny_study_dates["start_date"], tiny_study_dates["end_date"], None)
    cleaned = pd.read_csv(out / "AAPL.csv", index_col=0, parse_dates=True)
    assert len(cleaned) == len(raw) - 1


def test_snapshot_manifest_is_stable_with_fixed_created_at(tmp_path, tiny_study_dates):
    from datetime import UTC, datetime
    fixed = datetime(2020, 1, 2, tzinfo=UTC)
    out1 = tmp_path / "snap1"
    out2 = tmp_path / "snap2"
    manifest_path1 = create_snapshot(
        tickers=["AAPL"],
        start=tiny_study_dates["start_date"],
        end=tiny_study_dates["end_date"],
        output_dir=out1,
        splits=tiny_study_dates["splits"],
        fetch_fn=_synthetic_fetcher,
        overwrite=True,
        created_at=fixed,
    )
    manifest_path2 = create_snapshot(
        tickers=["AAPL"],
        start=tiny_study_dates["start_date"],
        end=tiny_study_dates["end_date"],
        output_dir=out2,
        splits=tiny_study_dates["splits"],
        fetch_fn=_synthetic_fetcher,
        overwrite=True,
        created_at=fixed,
    )
    data1 = json.loads(manifest_path1.read_text(encoding="utf-8"))
    data2 = json.loads(manifest_path2.read_text(encoding="utf-8"))
    assert data1["created_at"] == data2["created_at"]
    assert data1["manifest_sha256"] == data2["manifest_sha256"]
    assert (out1 / "AAPL.csv").read_bytes() == (out2 / "AAPL.csv").read_bytes()


def test_snapshot_csv_is_sorted_by_index(tmp_path, tiny_study_dates):
    out = tmp_path / "snap"
    create_snapshot(
        tickers=["AAPL"],
        start=tiny_study_dates["start_date"],
        end=tiny_study_dates["end_date"],
        output_dir=out,
        splits=tiny_study_dates["splits"],
        fetch_fn=_synthetic_fetcher,
        overwrite=True,
    )
    df = pd.read_csv(out / "AAPL.csv", index_col=0, parse_dates=True)
    assert df.index.is_monotonic_increasing


def _synthetic_fetcher(ticker, start, end, provider):
    from .conftest import make_synthetic_bars
    return make_synthetic_bars(ticker, start, end, seed=abs(hash(ticker)) % 10000)


def _make_candle(dt: datetime, open_: float, high: float, low: float, close: float, volume: float) -> dict:
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "datetime": int(dt.timestamp() * 1000),
    }


class _GuardedSchwabClient:
    """Fake Schwab client that exposes only the allowed market-data method."""

    _ALLOWED: ClassVar[set[str]] = {"get_price_history_every_day"}

    def __init__(self, candles):
        self._candles = candles
        self.calls = []

    def __getattr__(self, name: str):
        if name in self._ALLOWED:
            return self._make_candle_method(name)
        raise AttributeError(f"forbidden Schwab client method accessed: {name}")

    def _make_candle_method(self, name: str):
        def _call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return Mock(
                status_code=200,
                raise_for_status=Mock(),
                json=Mock(return_value={"candles": self._candles}),
            )
        return _call


def test_snapshot_with_guarded_fake_schwab_client(tmp_path, tiny_study_dates):
    """The snapshot path can use a fake Schwab client without credentials or network."""
    start = tiny_study_dates["start_date"]
    end = tiny_study_dates["end_date"]
    t1 = datetime(2020, 1, 2, tzinfo=UTC)
    t2 = datetime(2020, 1, 3, tzinfo=UTC)
    client = _GuardedSchwabClient([
        _make_candle(t1, 100.0, 101.0, 99.0, 100.5, 1000),
        _make_candle(t2, 100.5, 102.0, 100.0, 101.5, 1100),
    ])

    out = tmp_path / "snap"
    with patch("tradex.data.history._get_schwab_client", return_value=client):
        manifest_path = create_snapshot(
            tickers=["AAPL"],
            start=start,
            end=end,
            output_dir=out,
            splits=tiny_study_dates["splits"],
            provider="schwab",
            overwrite=True,
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provider"] == "schwab"
    assert manifest["successful_tickers"] == ["AAPL"]
    assert manifest["failed_tickers"] == []
    df = pd.read_csv(out / "AAPL.csv", index_col=0, parse_dates=True)
    assert len(df) == 2
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert any(call[0] == "get_price_history_every_day" for call in client.calls)


def test_guarded_fake_schwab_client_forbids_account_endpoints():
    """The fake client raises on any disallowed account/position/order/transaction method."""
    client = _GuardedSchwabClient([])
    for forbidden in ("get_accounts", "get_positions", "get_orders", "get_transactions"):
        with pytest.raises(AttributeError, match="forbidden"):
            getattr(client, forbidden)
