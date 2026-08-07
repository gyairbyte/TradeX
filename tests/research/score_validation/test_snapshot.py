"""Snapshot command tests with mocked provider access."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from tradex.research.score_validation.cleaning import (
    _SUPPORTED_HARD_ROW_INVARIANTS,
    verify_snapshot_sidecars,
)
from tradex.research.score_validation.manifest import load_manifest
from tradex.research.score_validation.models import ValidationError
from tradex.research.score_validation.snapshot import create_snapshot


def _make_history(start: str = "2020-01-01", periods: int = 120) -> pd.DataFrame:
    idx = pd.date_range(start, periods=periods, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * periods,
            "high": [101.0] * periods,
            "low": [99.0] * periods,
            "close": [100.5] * periods,
            "volume": [1e6] * periods,
        },
        index=idx,
    )


def _default_splits() -> dict[str, tuple[str, str]]:
    return {
        "development": ("2020-01-01", "2020-03-31"),
        "validation": ("2020-04-01", "2020-05-31"),
        "holdout": ("2020-06-01", "2020-06-30"),
    }


def test_snapshot_creates_manifest_and_csvs(tmp_path: Path):
    out = tmp_path / "dataset"
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.return_value = _make_history()
        manifest_path = create_snapshot(
            ["AAPL", "MSFT"],
            start=date(2020, 1, 1),
            end=date(2020, 5, 31),
            output_dir=out,
            splits=_default_splits(),
            provider="yahoo",
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
            output_dir=out,
            splits=_default_splits(),
            provider="yahoo",
        )
    manifest = load_manifest(manifest_path)
    assert [e.ticker for e in manifest.entries] == ["AAPL", "MSFT"]


def test_snapshot_rejects_empty_tickers(tmp_path: Path):
    out = tmp_path / "dataset"
    with pytest.raises(ValidationError, match="empty"):
        create_snapshot(
            [],
            start=date(2020, 1, 1),
            end=date(2020, 5, 31),
            output_dir=out,
            splits=_default_splits(),
        )


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
                splits=_default_splits(),
            )


def test_snapshot_rollback_on_one_ticker_failure(tmp_path: Path):
    out = tmp_path / "dataset"

    def side_effect(ticker, start, end, provider=None, *, settings=None):
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
                splits=_default_splits(),
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
                splits=_default_splits(),
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
            splits=_default_splits(),
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
            output_dir=out,
            splits=_default_splits(),
            provider="yahoo",
        )
        fake.assert_called_once()
        call_kwargs = fake.call_args.kwargs
        assert "provider" in call_kwargs


def test_snapshot_rejects_path_unsafe_ticker(tmp_path: Path):
    out = tmp_path / "dataset"
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.return_value = _make_history()
        with pytest.raises(ValidationError, match="invalid"):
            create_snapshot(
                ["../AAPL"],
                start=date(2020, 1, 1),
                end=date(2020, 5, 31),
                output_dir=out,
                splits=_default_splits(),
            )


def test_snapshot_resolves_provider_from_env(monkeypatch, tmp_path: Path):
    """create_snapshot must record the canonically resolved provider."""
    monkeypatch.setenv("DATA_PROVIDER", "schwab")
    out = tmp_path / "dataset"
    called: dict[str, Any] = {}

    def fake_history(ticker, start, end, provider=None, *, settings=None):
        called["provider"] = provider
        return _make_history()

    with patch("tradex.research.score_validation.snapshot.fetch_daily_history", side_effect=fake_history):
        manifest_path = create_snapshot(
            ["AAPL"],
            start=date(2020, 1, 1),
            end=date(2020, 5, 31),
            output_dir=out,
            splits=_default_splits(),
            provider=None,
        )
    manifest = load_manifest(manifest_path)
    assert manifest.entries[0].data_source == "schwab"
    assert called.get("provider") == "schwab"


def _ingestion_policy(symbol_count: int = 2) -> Any:
    from tradex.research.score_validation.cleaning import IngestionPolicy

    return IngestionPolicy(
        schema_version=1,
        policy_id="test-hard-invalid-row-exclusion",
        action="drop",
        structural_failures_remain_fatal=True,
        repair_values=False,
        require_all_symbols=True,
        required_symbol_count=symbol_count,
        max_total_invalid_rows=50,
        max_total_invalid_rate_pct=100.0,
        max_invalid_rows_per_ticker=5,
        max_invalid_rate_pct_per_ticker=100.0,
        max_consecutive_invalid_rows_per_ticker=1,
        allow_first_or_last_row_removal=False,
        minimum_pre_development_warmup_bars=5,
        hard_row_invariants=list(_SUPPORTED_HARD_ROW_INVARIANTS),
    )


def _make_history_with_invalid() -> pd.DataFrame:
    df = _make_history()
    df.loc[df.index[10], "high"] = 98.0
    return df


def test_snapshot_with_ingestion_policy_creates_sidecars(tmp_path: Path):
    out = tmp_path / "dataset"
    history = _make_history(start="2019-12-01", periods=150)

    def side_effect(ticker, start, end, provider=None, *, settings=None):
        if ticker == "AAPL":
            df = history.copy()
            df.loc[df.index[10], "high"] = 98.0
            return df
        return history

    policy = _ingestion_policy(2)
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history", side_effect=side_effect):
        manifest_path = create_snapshot(
            ["AAPL", "MSFT"],
            start=date(2019, 12, 1),
            end=date(2020, 4, 30),
            output_dir=out,
            splits=_default_splits(),
            provider="schwab",
            ingestion_spec=policy,
            context_spec_sha256="abc123" * 8,
        )
    manifest = load_manifest(manifest_path)
    assert {e.ticker for e in manifest.entries} == {"AAPL", "MSFT"}
    aapl_entry = next(e for e in manifest.entries if e.ticker == "AAPL")
    assert aapl_entry.rows == 149
    assert (out / "ingestion_spec.lock.json").is_file()
    assert (out / "snapshot_audit.json").is_file()
    assert (out / "snapshot_data_quality.csv").is_file()
    assert (out / "invalid_rows.csv").is_file()
    assert (out / "snapshot_checksums.sha256").is_file()


def test_snapshot_ingestion_rejects_non_schwab_provider(tmp_path: Path):
    out = tmp_path / "dataset"
    policy = _ingestion_policy(1)
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.return_value = _make_history()
        with pytest.raises(ValidationError, match="provider 'schwab'"):
            create_snapshot(
                ["AAPL"],
                start=date(2020, 1, 1),
                end=date(2020, 5, 31),
                output_dir=out,
                splits=_default_splits(),
                provider="yahoo",
                ingestion_spec=policy,
            )


def test_snapshot_ingestion_rejects_excessive_invalid_rows(tmp_path: Path):
    out = tmp_path / "dataset"
    df = _make_history(start="2019-12-01", periods=150)
    for i in range(6):
        df.loc[df.index[10 + i * 2], "high"] = 98.0
    policy = _ingestion_policy(1)
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history") as fake:
        fake.return_value = df
        with pytest.raises(ValidationError, match="per-ticker limit"):
            create_snapshot(
                ["AAPL"],
                start=date(2019, 12, 1),
                end=date(2020, 4, 30),
                output_dir=out,
                splits=_default_splits(),
                provider="schwab",
                ingestion_spec=policy,
            )


def _create_valid_snapshot(tmp_path: Path, with_invalid: bool = True):
    """Return a snapshot directory and ingestion spec sha for a valid 2-ticker snapshot."""
    out = tmp_path / "dataset"
    history = _make_history(start="2019-12-01", periods=150)

    def side_effect(ticker, start, end, provider=None, *, settings=None):
        if ticker == "AAPL" and with_invalid:
            df = history.copy()
            df["volume"] = df["volume"].astype(int)
            df.loc[df.index[10], "high"] = 98.0
            return df
        return history

    policy = _ingestion_policy(2)
    with patch("tradex.research.score_validation.snapshot.fetch_daily_history", side_effect=side_effect):
        manifest_path = create_snapshot(
            ["AAPL", "MSFT"],
            start=date(2019, 12, 1),
            end=date(2020, 4, 30),
            output_dir=out,
            splits=_default_splits(),
            provider="schwab",
            ingestion_spec=policy,
            context_spec_sha256="abcd1234" * 8,
        )
    spec_bytes = policy.to_json().encode("utf-8")
    return out, manifest_path, hashlib.sha256(spec_bytes).hexdigest()


def test_cleaned_csv_sha256_matches_manifest_hashes(tmp_path: Path):
    """The data-quality audit must agree with the manifest CSV hashes."""
    out, manifest_path, _ = _create_valid_snapshot(tmp_path)
    manifest = load_manifest(manifest_path)
    quality = pd.read_csv(out / "snapshot_data_quality.csv")
    for entry in manifest.entries:
        row = quality[quality["ticker"] == entry.ticker].iloc[0]
        assert row["cleaned_csv_sha256"] == entry.sha256


def test_snapshot_audit_excludes_self_hash_and_hashes_match(tmp_path: Path):
    """snapshot_audit.json must not contain its own hash; all sidecar hashes must be verifiable."""
    out, _manifest_path, _ = _create_valid_snapshot(tmp_path)
    audit = json.loads((out / "snapshot_audit.json").read_text())
    assert "snapshot_audit.json" not in audit["sidecar_sha256"]

    for name, expected in audit["sidecar_sha256"].items():
        file_path = out / name
        assert file_path.is_file()
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert actual == expected


def test_verify_snapshot_sidecars_valid(tmp_path: Path):
    _out, manifest_path, ingestion_sha = _create_valid_snapshot(tmp_path)
    snapshot_dir = manifest_path.parent
    audit = verify_snapshot_sidecars(
        snapshot_dir,
        ingestion_sha,
        expected_context_sha256="abcd1234" * 8,
        expected_manifest_path=manifest_path,
    )
    assert audit["provider"] == "schwab"
    assert audit["threshold_result"] == "passed"
    assert audit["retrieved_symbol_count"] == audit["required_symbol_count"]


def test_verify_snapshot_sidecars_rejects_tampered_sidecar(tmp_path: Path):
    _out, manifest_path, ingestion_sha = _create_valid_snapshot(tmp_path)
    snapshot_dir = manifest_path.parent
    (snapshot_dir / "invalid_rows.csv").write_text("tampered")
    with pytest.raises(ValidationError, match="Checksum mismatch|sidecar hash mismatch"):
        verify_snapshot_sidecars(
            snapshot_dir,
            ingestion_sha,
            expected_context_sha256="abcd1234" * 8,
            expected_manifest_path=manifest_path,
        )


def test_verify_snapshot_sidecars_rejects_missing_mandatory_sidecar(tmp_path: Path):
    _out, manifest_path, ingestion_sha = _create_valid_snapshot(tmp_path)
    snapshot_dir = manifest_path.parent
    (snapshot_dir / "invalid_rows.csv").unlink()
    with pytest.raises(ValidationError, match="missing mandatory sidecars|missing sidecar"):
        verify_snapshot_sidecars(
            snapshot_dir,
            ingestion_sha,
            expected_context_sha256="abcd1234" * 8,
            expected_manifest_path=manifest_path,
        )
