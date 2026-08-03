"""Tests for offline snapshot creation and loading."""
from __future__ import annotations

import json

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


def _synthetic_fetcher(ticker, start, end, provider):
    from .conftest import make_synthetic_bars
    return make_synthetic_bars(ticker, start, end, seed=abs(hash(ticker)) % 10000)
