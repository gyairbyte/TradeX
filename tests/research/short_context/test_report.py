"""Tests for the short-term context study report pipeline."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tradex.research.score_validation.models import ScoreValidationConfig
from tradex.research.short_context.models import CandidateResult, ValidationError
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


def test_run_study_rejects_config_that_disagrees_with_spec(synthetic_manifest, tmp_path: Path) -> None:
    """A runtime config missing the spec's primary horizon/slippage must fail fast."""
    output_dir = tmp_path / "study_out"
    mismatched = ScoreValidationConfig(
        warmup_bars=60,
        horizons=(1, 5),
        slippage_scenarios_bps=(0.0, 5.0, 10.0),
    )
    with pytest.raises(ValidationError, match="primary_horizon_bars"):
        run_study(
            synthetic_manifest["manifest_path"],
            synthetic_manifest["spec_path"],
            output_dir,
            config=mismatched,
        )


def test_run_study_selected_candidate_exercises_paired_backtest(synthetic_manifest, tmp_path: Path, monkeypatch) -> None:
    """Forcing a selected candidate runs the paired backtest branch end-to-end."""
    import tradex.research.short_context.report as report_module

    def _select_candidate(*_args, **_kwargs):
        return CandidateResult(
            selected_policy="market_rs",
            selection_reason="deterministic fixture",
            policy_metrics={},
        )

    monkeypatch.setattr(report_module, "select_candidate", _select_candidate)
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
    paired_csv = output_dir / "paired_backtests.csv"
    assert paired_csv.exists()
    paired_df = pd.read_csv(paired_csv)
    assert not paired_df.empty
    assert {"ticker", "total_trades_baseline", "total_trades_candidate"} <= set(paired_df.columns)
