"""Direct configuration, model, and validation tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradex.research.score_validation.manifest import load_manifest
from tradex.research.score_validation.models import (
    ScoreValidationConfig,
    ValidationError,
    _slippage_key,
)

from .conftest import write_bars_and_manifest


def test_config_rejects_bool_values():
    with pytest.raises(ValidationError, match="integer"):
        ScoreValidationConfig(warmup_bars=True)


def test_config_rejects_fractional_integer_fields():
    with pytest.raises(ValidationError, match="integer"):
        ScoreValidationConfig(warmup_bars=50.5)
    with pytest.raises(ValidationError, match="integer"):
        ScoreValidationConfig(score_bucket_edges=(0, 20.5, 40, 60, 80, 101))
    with pytest.raises(ValidationError, match="integer"):
        ScoreValidationConfig(score_thresholds=(20.0, 30, 40))


def test_config_rejects_string_integers():
    with pytest.raises(ValidationError, match="integer"):
        ScoreValidationConfig(warmup_bars="50")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="integer"):
        ScoreValidationConfig(horizons=("1", "3", "5"))  # type: ignore[arg-type]


def test_config_rejects_empty_research_dimensions():
    with pytest.raises(ValidationError, match="empty"):
        ScoreValidationConfig(horizons=())
    with pytest.raises(ValidationError, match="empty"):
        ScoreValidationConfig(score_thresholds=())
    with pytest.raises(ValidationError, match="empty"):
        ScoreValidationConfig(slippage_scenarios_bps=())
    with pytest.raises(ValidationError, match="empty"):
        ScoreValidationConfig(score_bucket_edges=())


def test_config_rejects_nan_or_infinite():
    with pytest.raises(ValidationError, match="finite"):
        ScoreValidationConfig(slippage_scenarios_bps=(float("nan"),))
    with pytest.raises(ValidationError, match="finite"):
        ScoreValidationConfig(slippage_scenarios_bps=(float("inf"),))
    with pytest.raises(ValidationError, match="nonnegative"):
        ScoreValidationConfig(commission_bps=-1.0)


def test_config_rejects_bool_slippage():
    with pytest.raises(ValidationError, match="boolean"):
        ScoreValidationConfig(slippage_scenarios_bps=(True,))


def test_slippage_key_lossless_and_collision_free():
    """Fractional and integer slippage values must have distinct, stable string keys."""
    assert _slippage_key(0.0) == "0"
    assert _slippage_key(0) == "0"
    assert _slippage_key(5.0) == "5"
    assert _slippage_key(2.5) == "2.5"
    assert _slippage_key(0.5) == "0.5"
    assert _slippage_key(2.50) == "2.5"
    # Distinct keys for distinct float values.
    assert _slippage_key(2.5) != _slippage_key(2.0)
    assert _slippage_key(0.5) != _slippage_key(0.0)


def test_config_bucket_edges_first_zero_last_above_100():
    with pytest.raises(ValidationError, match="start at 0"):
        ScoreValidationConfig(score_bucket_edges=(10, 20, 101))
    with pytest.raises(ValidationError, match="exceed 100"):
        ScoreValidationConfig(score_bucket_edges=(0, 20, 100))


def test_config_thresholds_within_range_and_sorted():
    with pytest.raises(ValidationError, match="within 0-100"):
        ScoreValidationConfig(score_thresholds=(20, 101))
    with pytest.raises(ValidationError, match="unique and sorted"):
        ScoreValidationConfig(score_thresholds=(20, 30, 30))


def test_manifest_rejects_unknown_top_level_keys(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    data = json.loads(manifest_path.read_text())
    data["unknown_key"] = "extra"
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="unknown top-level keys"):
        load_manifest(manifest_path)


def test_manifest_rejects_unknown_entry_keys(tmp_path: Path):
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    data = json.loads(manifest_path.read_text())
    data["entries"][0]["extra"] = "value"
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="unknown keys"):
        load_manifest(manifest_path)


def test_manifest_rejects_contiguous_splits_as_overlapping(tmp_path: Path):
    """Adjacent inclusive splits share a date; they must be rejected."""
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    data = json.loads(manifest_path.read_text())
    data["splits"] = {
        "development": {"start": "2020-01-01", "end": "2020-12-31"},
        "validation": {"start": "2020-12-31", "end": "2021-12-31"},
        "holdout": {"start": "2022-01-01", "end": "2023-12-31"},
    }
    manifest_path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValidationError, match="not after previous split end"):
        load_manifest(manifest_path)


def test_manifest_sha256_attached(tmp_path: Path):
    import hashlib

    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    expected_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    manifest = load_manifest(manifest_path)
    assert getattr(manifest, "_sha256", None) == expected_sha
