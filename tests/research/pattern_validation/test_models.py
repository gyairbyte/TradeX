"""Tests for pattern-validation model validation and serialization."""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tradex.research.pattern_validation.models import (
    DatasetManifest,
    ManifestEntry,
    Split,
    StudySpec,
    ValidationError,
    _canonical_json_sha256,
)
from tradex.research.pattern_validation.snapshot import load_snapshot


def test_study_spec_rejects_bool_for_number():
    with pytest.raises(ValidationError):
        StudySpec(research_test_mode=True, tickers=("AAPL",), lookback_days=True)


def test_study_spec_rejects_numeric_string():
    with pytest.raises(ValidationError):
        StudySpec(research_test_mode=True, tickers=("AAPL",), lookback_days="10")


def test_study_spec_rejects_duplicate_tickers():
    with pytest.raises(ValidationError, match="duplicates"):
        StudySpec(research_test_mode=True, tickers=("AAPL", "AAPL"))


def test_study_spec_rejects_overlapping_splits():
    splits = {
        "a": Split(date(2020, 1, 1), date(2020, 12, 31)),
        "b": Split(date(2020, 6, 1), date(2021, 6, 1)),
    }
    with pytest.raises(ValidationError, match="overlap"):
        StudySpec(research_test_mode=True, tickers=("AAPL",), splits=splits)


def test_study_spec_rejects_split_outside_range():
    splits = {
        "development": Split(date(2019, 1, 1), date(2019, 12, 31)),
    }
    with pytest.raises(ValidationError, match="within"):
        StudySpec(research_test_mode=True, tickers=("AAPL",), start_date=date(2020, 1, 1), end_date=date(2020, 12, 31), splits=splits)


def test_study_spec_rejects_unknown_keys():
    with pytest.raises(TypeError):
        StudySpec(research_test_mode=True, tickers=("AAPL",), unknown_field=1)


def test_study_spec_universe_hash_is_stable():
    spec1 = StudySpec(research_test_mode=True, tickers=("AAPL", "MSFT"))
    spec2 = StudySpec(research_test_mode=True, tickers=("MSFT", "AAPL"))
    assert spec1.universe_hash != spec2.universe_hash


def test_study_spec_sha256_is_stable():
    spec = StudySpec(research_test_mode=True, tickers=("AAPL", "MSFT"))
    h1 = spec.sha256
    h2 = _canonical_json_sha256(spec.to_lock_dict())
    assert h1 == h2


def test_study_spec_rejects_numeric_string_slippage():
    with pytest.raises(ValidationError):
        StudySpec(
            research_test_mode=True,
            tickers=("AAPL",),
            slippage_scenarios_bps=("10",),
        )


def test_study_spec_rejects_numeric_string_series_weights():
    with pytest.raises(ValidationError):
        StudySpec(
            research_test_mode=True,
            tickers=("AAPL",),
            series_weights={"price_pct": "0.35"},
        )


def test_study_spec_lock_dict_contains_research_test_mode():
    spec = StudySpec(research_test_mode=True, tickers=("AAPL",))
    lock = spec.to_lock_dict()
    assert "research_test_mode" in lock
    assert lock["research_test_mode"] is True


def test_study_spec_sha256_changes_with_research_test_mode():
    base = StudySpec(research_test_mode=True, tickers=("AAPL",))
    lock_test = dict(base.to_lock_dict())
    lock_test["research_test_mode"] = True
    lock_locked = dict(base.to_lock_dict())
    lock_locked["research_test_mode"] = False
    assert _canonical_json_sha256(lock_test) != _canonical_json_sha256(lock_locked)


def test_study_spec_series_weights_and_splits_are_immutable():
    spec = StudySpec(research_test_mode=True, tickers=("AAPL",))
    assert isinstance(spec.series_weights, dict)
    assert isinstance(spec.splits, dict)
    with pytest.raises(TypeError):
        spec.series_weights["price_pct"] = 0.0
    with pytest.raises(TypeError):
        spec.splits["extra"] = Split(date(2020, 1, 1), date(2020, 12, 31))


def test_run_study_rejects_manifest_provider_mismatch(tiny_bars, tiny_spec):
    import tempfile
    from dataclasses import replace
    from datetime import date

    from tradex.research.pattern_validation.models import Split
    from tradex.research.pattern_validation.report import run_study
    from tradex.research.pattern_validation.snapshot import create_snapshot

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "snap"
        manifest_path = create_snapshot(
            tickers=["AAPL"],
            start=date(2020, 1, 2),
            end=date(2024, 12, 31),
            output_dir=out,
            splits={"validation": Split(date(2020, 1, 2), date(2024, 12, 31))},
            fetch_fn=lambda t, s, e, p: tiny_bars.get(t, tiny_bars["AAPL"]),
            overwrite=True,
            created_at=datetime(2020, 1, 2, tzinfo=UTC),
        )
        manifest, bars = load_snapshot(manifest_path)
        bad_spec = replace(
            tiny_spec,
            provider="yahoo",
            splits={"validation": Split(date(2020, 1, 2), date(2024, 12, 31))},
            start_date=date(2020, 1, 2),
            end_date=date(2024, 12, 31),
            tickers=("AAPL",),
        )
        with pytest.raises(ValidationError, match="provider"):
            run_study(manifest, bars, bad_spec)


def test_manifest_serialization_roundtrip(tmp_path):
    from datetime import datetime
    entry = ManifestEntry(
        ticker="AAPL",
        path="AAPL.csv",
        sha256="abc",
        rows=10,
        start=None,
        end=None,
        data_source="synthetic",
        adjustment_policy="provider_default",
        failure=None,
    )
    manifest = DatasetManifest(
        schema_version=1,
        dataset_name="test",
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
        source_description="test",
        provider="synthetic",
        adjustment_policy="provider_default",
        request_start=date(2020, 1, 1),
        request_end=date(2020, 12, 31),
        entries=(entry,),
        splits={},
        requested_tickers=("AAPL",),
        successful_tickers=("AAPL",),
        failed_tickers=(),
        failure_categories=(),
    )
    path = tmp_path / "manifest.lock.json"
    path.write_text(manifest.to_json(indent=2), encoding="utf-8")
    from tradex.research.pattern_validation.models import load_manifest
    loaded = load_manifest(path)
    assert loaded.requested_tickers == ("AAPL",)


def test_spec_json_roundtrip(tmp_path):
    spec = StudySpec(research_test_mode=True, tickers=("AAPL", "MSFT"))
    path = tmp_path / "spec.json"
    path.write_text(spec.to_json(indent=2), encoding="utf-8")
    from tradex.research.pattern_validation.models import load_spec
    loaded = load_spec(path, research_test_mode=True)
    assert loaded.tickers == ("AAPL", "MSFT")
    assert loaded.sha256 == spec.sha256


def test_production_promotion_eligible_must_be_false():
    spec = StudySpec(research_test_mode=True, tickers=("AAPL",))
    assert spec.production_promotion_eligible is False
    object.__setattr__(spec, "production_promotion_eligible", True)
    with pytest.raises(ValidationError, match="production_promotion_eligible"):
        StudySpec.__post_init__(spec)
