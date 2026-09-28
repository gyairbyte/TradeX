"""Tests for LONG-002D2 artifact serialization and checksums."""
from __future__ import annotations

import json
from pathlib import Path

from tradex.research.long_002d2.artifacts import write_d2_artifacts
from tradex.research.long_002d2.models import (
    AnnualBreakdown,
    BootstrapDistributionSummary,
    CandidateEvaluationResult,
    InputIntegrityAudit,
    RegimeDiagnosticMetrics,
)


def test_write_d2_artifacts(tmp_path: Path) -> None:
    """Verify that write_d2_artifacts writes all required files and matching checksums."""
    audit = InputIntegrityAudit(
        feature_table_path="dummy_feat.parquet",
        feature_table_sha256="dummy_feat_sha",
        feature_table_rows=100,
        baseline_path="dummy_base.parquet",
        baseline_sha256="dummy_base_sha",
        baseline_rows=100,
        outcome_matrix_path=None,
        outcome_matrix_sha256=None,
        zero_validation_rows=True,
        zero_holdout_rows=True,
        zero_shadow_rows=True,
        zero_network_calls=True,
        join_keys_unique=True,
        all_dates_within_dev=True,
        all_cutoffs_20_30=True,
        gates_passed=True,
    )
    b_summary = BootstrapDistributionSummary(
        block_size_sessions=21,
        replicates=10,
        seed=20260928,
        mean_delta=0.01,
        median_delta=0.01,
        std_err=0.002,
        ci_2_5=0.005,
        ci_97_5=0.015,
    )
    annual = AnnualBreakdown(
        year=2017,
        eval_dates_count=10,
        selected_count=20,
        candidate_clean_count=4,
        candidate_precision=0.20,
        matched_vam5_clean_count=3,
        matched_vam5_precision=0.15,
        absolute_delta=0.05,
        precision_ratio=1.3333,
        positive_delta=True,
    )
    regime = RegimeDiagnosticMetrics(
        regime_name="lower_regime",
        description="lower",
        percentile_min=0.0,
        percentile_max=30.0,
        date_count=3,
        selected_count=6,
        candidate_clean_count=1,
        candidate_precision=0.1667,
        matched_vam5_clean_count=1,
        matched_vam5_precision=0.1667,
        absolute_delta=0.0,
        precision_ratio=1.0,
    )

    primary_res = CandidateEvaluationResult(
        feature_id="relative_volume_20",
        role="primary_candidate",
        status="supported_for_next_stage",
        common_observations=100,
        coverage_within_top_25=1.0,
        evaluation_dates_count=10,
        total_selected_count=20,
        candidate_clean_count=4,
        candidate_precision=0.20,
        matched_vam5_clean_count=3,
        matched_vam5_precision=0.15,
        absolute_precision_delta=0.05,
        precision_ratio=1.3333,
        incremental_clean_events=1,
        selection_overlap_count=15,
        selection_overlap_rate=0.75,
        annual_breakdowns=[annual],
        positive_annual_years_count=1,
        bootstrap_21=b_summary,
        bootstrap_42=b_summary,
        regime_breakdowns=[regime],
    )

    challenger_res = CandidateEvaluationResult(
        feature_id="sma20_slope_5",
        role="secondary_challenger",
        status="descriptive_challenger",
        common_observations=100,
        coverage_within_top_25=1.0,
        evaluation_dates_count=10,
        total_selected_count=20,
        candidate_clean_count=4,
        candidate_precision=0.20,
        matched_vam5_clean_count=3,
        matched_vam5_precision=0.15,
        absolute_precision_delta=0.05,
        precision_ratio=1.3333,
        incremental_clean_events=1,
        selection_overlap_count=15,
        selection_overlap_rate=0.75,
        annual_breakdowns=[annual],
        positive_annual_years_count=1,
        bootstrap_21=b_summary,
        bootstrap_42=b_summary,
        regime_breakdowns=[regime],
    )

    checksums = write_d2_artifacts(
        run_id="test_run",
        output_dir=tmp_path,
        preregistration_commit_sha="dummy_sha",
        audit=audit,
        primary_result=primary_res,
        challenger_result=challenger_res,
        execution_timing={"duration_seconds": 1.0},
    )

    expected_files = [
        "execution_metadata.json",
        "input_integrity.json",
        "rerank_summary.json",
        "bootstrap_summary.json",
        "regime_diagnostic_summary.json",
    ]
    for ef in expected_files:
        assert ef in checksums
        assert (tmp_path / ef).exists()
        content = json.loads((tmp_path / ef).read_text(encoding="utf-8"))
        assert isinstance(content, dict)

    assert (tmp_path / "checksums.sha256").exists()
