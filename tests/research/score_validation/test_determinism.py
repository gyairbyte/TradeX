"""Determinism tests for the score-validation study."""
from __future__ import annotations

import filecmp
from datetime import UTC, datetime
from pathlib import Path

from tradex.research.score_validation.cli import main

from .conftest import write_bars_and_manifest


class FixedDateTime(datetime):
    """Deterministic datetime subclass used to freeze ``generated_at``."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 1, 12, 0, 0, tzinfo=UTC)

    @classmethod
    def combine(cls, date, time, tzinfo=None):
        return datetime.combine(date, time, tzinfo=tzinfo)


def _patch_datetime(monkeypatch):
    monkeypatch.setattr(
        "tradex.research.score_validation.models.datetime", FixedDateTime
    )


def test_evaluate_is_deterministic(tmp_path: Path, monkeypatch):
    _patch_datetime(monkeypatch)

    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    out1 = tmp_path / "results1"
    out2 = tmp_path / "results2"

    ret1 = main(
        ["evaluate", "--manifest", str(manifest_path), "--output-dir", str(out1), "--warmup-bars", "50"]
    )
    ret2 = main(
        ["evaluate", "--manifest", str(manifest_path), "--output-dir", str(out2), "--warmup-bars", "50"]
    )
    assert ret1 == ret2 == 0

    # Compare deterministic files (exclude generated_at in study.json and report.md timestamp).
    deterministic = [
        "events.csv",
        "score_buckets.csv",
        "thresholds.csv",
        "components.csv",
        "score_distribution.csv",
        "component_frequency.csv",
        "ticker_summary.csv",
        "data_quality.csv",
        "manifest.lock.json",
    ]
    for name in deterministic:
        assert filecmp.cmp(out1 / name, out2 / name, shallow=False), f"{name} differs"


def test_study_to_json_is_deterministic(tmp_path: Path, monkeypatch):
    _patch_datetime(monkeypatch)

    from tradex.research.score_validation.models import ScoreValidationConfig
    from tradex.research.score_validation.report import run_study

    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    study1 = run_study(manifest_path, ScoreValidationConfig(warmup_bars=50))
    study2 = run_study(manifest_path, ScoreValidationConfig(warmup_bars=50))
    assert study1.to_json() == study2.to_json()
