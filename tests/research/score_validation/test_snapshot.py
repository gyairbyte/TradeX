"""Snapshot command tests with mocked provider access."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from tradex.research.score_validation.manifest import load_manifest
from tradex.research.score_validation.models import ValidationError
from tradex.research.score_validation.snapshot import create_snapshot


def _make_history() -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=120, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * 120,
            "high": [101.0] * 120,
            "low": [99.0] * 120,
            "close": [100.5] * 120,
            "volume": [1e6] * 120,
        },
        index=idx,
    )


def test_snapshot_creates_manifest_and_csvs(tmp_path: Path):
    out = tmp_path / "dataset"
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.return_value = _make_history()
        manifest_path = create_snapshot(
            ["AAPL", "MSFT"],
            start=date(2020, 1, 1),
            end=date(2020, 5, 31),
            provider="yahoo",
            output_dir=out,
        )
    assert manifest_path.is_file()
    assert (out / "AAPL.csv").is_file()
    assert (out / "MSFT.csv").is_file()

    manifest = load_manifest(manifest_path)
    assert {e.ticker for e in manifest.entries} == {"AAPL", "MSFT"}
    assert all(e.data_source == "yahoo" for e in manifest.entries)
    assert all(len(e.sha256) == 64 for e in manifest.entries)


def test_snapshot_deduplicates_tickers(tmp_path: Path):
    out = tmp_path / "dataset"
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.return_value = _make_history()
        manifest_path = create_snapshot(
            ["aapl", "AAPL", "MSFT"],
            start=date(2020, 1, 1),
            end=date(2020, 5, 31),
            provider="yahoo",
            output_dir=out,
        )
    manifest = load_manifest(manifest_path)
    assert [e.ticker for e in manifest.entries] == ["AAPL", "MSFT"]


def test_snapshot_rejects_empty_tickers(tmp_path: Path):
    out = tmp_path / "dataset"
    with pytest.raises(ValidationError, match="empty"):
        create_snapshot([], start=date(2020, 1, 1), end=date(2020, 5, 31), output_dir=out)


def test_snapshot_rejects_bad_date_range(tmp_path: Path):
    out = tmp_path / "dataset"
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.return_value = _make_history()
        with pytest.raises(ValidationError, match="End date"):
            create_snapshot(
                ["AAPL"],
                start=date(2020, 5, 31),
                end=date(2020, 1, 1),
                output_dir=out,
            )


def test_snapshot_rollback_on_one_ticker_failure(tmp_path: Path):
    out = tmp_path / "dataset"

    def side_effect(ticker, start, end, provider=None):
        if ticker == "FAIL":
            raise RuntimeError("provider failure")
        return _make_history()

    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.side_effect = side_effect
        with pytest.raises(RuntimeError, match="provider failure"):
            create_snapshot(
                ["AAPL", "FAIL", "MSFT"],
                start=date(2020, 1, 1),
                end=date(2020, 5, 31),
                output_dir=out,
            )
    assert not out.exists() or not any(out.iterdir())


def test_snapshot_respects_existing_output_dir(tmp_path: Path):
    out = tmp_path / "dataset"
    out.mkdir()
    (out / "existing.txt").write_text("do not delete")
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.return_value = _make_history()
        with pytest.raises(ValidationError, match="overwrite"):
            create_snapshot(
                ["AAPL"],
                start=date(2020, 1, 1),
                end=date(2020, 5, 31),
                output_dir=out,
            )


def test_snapshot_overwrite_flag(tmp_path: Path):
    out = tmp_path / "dataset"
    out.mkdir()
    (out / "existing.txt").write_text("delete me")
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.return_value = _make_history()
        manifest_path = create_snapshot(
            ["AAPL"],
            start=date(2020, 1, 1),
            end=date(2020, 5, 31),
            output_dir=out,
            overwrite=True,
        )
    assert manifest_path.is_file()
    assert not (out / "existing.txt").exists()


def test_snapshot_no_direct_provider_calls(tmp_path: Path):
    out = tmp_path / "dataset"
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.return_value = _make_history()
        create_snapshot(
            ["AAPL"],
            start=date(2020, 1, 1),
            end=date(2020, 5, 31),
            provider="yahoo",
            output_dir=out,
        )
        fake.assert_called_once()
        call_kwargs = fake.call_args.kwargs
        assert "provider" in call_kwargs
