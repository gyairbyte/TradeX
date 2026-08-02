"""Determinism tests for the score-validation study."""
from __future__ import annotations

import filecmp
from pathlib import Path

from tradex.research.score_validation.cli import main

from .conftest import write_bars_and_manifest


def test_evaluate_is_deterministic(tmp_path: Path):
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
        "study.json",
        "report.md",
    ]
    for name in deterministic:
        assert filecmp.cmp(out1 / name, out2 / name, shallow=False), f"{name} differs"
