"""Tests for the short-term context study report pipeline."""
from __future__ import annotations

from pathlib import Path

from tradex.research.score_validation.models import ScoreValidationConfig
from tradex.research.short_context.report import run_study


def test_run_study_writes_expected_files(synthetic_manifest, tmp_path: Path) -> None:
    output_dir = tmp_path / "study_out"
    run_study(
        synthetic_manifest["manifest_path"],
        synthetic_manifest["spec_path"],
        output_dir,
        config=ScoreValidationConfig(
            warmup_bars=60,
            horizons=(1, 3, 5),
            slippage_scenarios_bps=(0.0, 5.0, 10.0),
        ),
    )
    expected = {
        "study.json",
        "context_events.csv",
        "candidate_comparison.csv",
        "candidate_selection.json",
        "holdout_evaluation.csv",
        "paired_backtests.csv",
        "ticker_comparison.csv",
        "data_quality.csv",
        "report.md",
        "manifest.lock.json",
        "context_spec.lock.json",
    }
    assert {p.name for p in output_dir.iterdir()} == expected
    report_text = (output_dir / "report.md").read_text()
    assert "Short-Term Market Context Study" in report_text
    assert "The existing short-term component score and weights were not changed." in report_text
