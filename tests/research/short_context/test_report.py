"""Tests for the short-term context study report pipeline."""
from __future__ import annotations

import json
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
    """A runtime config must match the locked spec exactly, including extra horizons."""
    output_dir = tmp_path / "study_out"

    mismatched_horizons = ScoreValidationConfig(
        warmup_bars=60,
        horizons=(1, 5),
        slippage_scenarios_bps=(0.0, 5.0, 10.0),
    )
    with pytest.raises(ValidationError, match="config.horizons"):
        run_study(
            synthetic_manifest["manifest_path"],
            synthetic_manifest["spec_path"],
            output_dir,
            config=mismatched_horizons,
        )

    extra_horizons = ScoreValidationConfig(
        warmup_bars=60,
        horizons=(1, 3, 5, 10),
        slippage_scenarios_bps=(0.0, 5.0, 10.0),
    )
    with pytest.raises(ValidationError, match="config.horizons"):
        run_study(
            synthetic_manifest["manifest_path"],
            synthetic_manifest["spec_path"],
            output_dir,
            config=extra_horizons,
        )

    commission_mismatch = ScoreValidationConfig(
        warmup_bars=60,
        horizons=(1, 3, 5),
        slippage_scenarios_bps=(0.0, 5.0, 10.0),
        commission_bps=10.0,
    )
    with pytest.raises(ValidationError, match="config.commission_bps"):
        run_study(
            synthetic_manifest["manifest_path"],
            synthetic_manifest["spec_path"],
            output_dir,
            config=commission_mismatch,
        )

    extra_slippage = ScoreValidationConfig(
        warmup_bars=60,
        horizons=(1, 3, 5),
        slippage_scenarios_bps=(0.0, 5.0, 10.0, 20.0),
    )
    with pytest.raises(ValidationError, match="config.slippage_scenarios_bps"):
        run_study(
            synthetic_manifest["manifest_path"],
            synthetic_manifest["spec_path"],
            output_dir,
            config=extra_slippage,
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


def test_run_study_records_runtime_config(synthetic_manifest, tmp_path: Path) -> None:
    """study.json must contain the effective ScoreValidationConfig used."""
    output_dir = tmp_path / "study_out"
    config = ScoreValidationConfig(
        warmup_bars=60,
        horizons=(1, 3, 5),
        slippage_scenarios_bps=(0.0, 5.0, 10.0),
        commission_bps=0.0,
    )
    run_study(
        synthetic_manifest["manifest_path"],
        synthetic_manifest["spec_path"],
        output_dir,
        config=config,
    )
    study = json.loads((output_dir / "study.json").read_text())
    assert "runtime_config" in study
    assert study["runtime_config"]["warmup_bars"] == 60
    assert study["runtime_config"]["horizons"] == [1, 3, 5]
    assert study["runtime_config"]["slippage_scenarios_bps"] == [0.0, 5.0, 10.0]
    assert study["runtime_config"]["commission_bps"] == 0.0
