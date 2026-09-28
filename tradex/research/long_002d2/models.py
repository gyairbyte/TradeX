"""Data models and result schemas for LONG-002D2."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AnnualBreakdown:
    """Annual performance breakdown for candidate vs matched VAM5."""

    year: int
    eval_dates_count: int
    selected_count: int
    candidate_clean_count: int
    candidate_precision: float
    matched_vam5_clean_count: int
    matched_vam5_precision: float
    absolute_delta: float
    precision_ratio: float
    positive_delta: bool


@dataclass(frozen=True)
class BootstrapDistributionSummary:
    """Summary statistics for paired bootstrap distribution."""

    block_size_sessions: int
    replicates: int
    seed: int
    mean_delta: float
    median_delta: float
    std_err: float
    ci_2_5: float
    ci_97_5: float


@dataclass(frozen=True)
class RegimeDiagnosticMetrics:
    """Descriptive performance metrics within an SPY return regime."""

    regime_name: str
    description: str
    percentile_min: float
    percentile_max: float
    date_count: int
    selected_count: int
    candidate_clean_count: int
    candidate_precision: float
    matched_vam5_clean_count: int
    matched_vam5_precision: float
    absolute_delta: float
    precision_ratio: float


@dataclass
class CandidateEvaluationResult:
    """Complete evaluation result for a candidate feature reranker."""

    feature_id: str
    role: str
    status: str
    common_observations: int
    coverage_within_top_25: float
    evaluation_dates_count: int
    total_selected_count: int
    candidate_clean_count: int
    candidate_precision: float
    matched_vam5_clean_count: int
    matched_vam5_precision: float
    absolute_precision_delta: float
    precision_ratio: float
    incremental_clean_events: int
    selection_overlap_count: int
    selection_overlap_rate: float
    annual_breakdowns: list[AnnualBreakdown]
    positive_annual_years_count: int
    bootstrap_21: BootstrapDistributionSummary
    bootstrap_42: BootstrapDistributionSummary
    regime_breakdowns: list[RegimeDiagnosticMetrics] = field(default_factory=list)


@dataclass(frozen=True)
class InputIntegrityAudit:
    """Cryptographic and coverage audit of input datasets."""

    feature_table_path: str
    feature_table_sha256: str
    feature_table_rows: int
    baseline_path: str
    baseline_sha256: str
    baseline_rows: int
    outcome_matrix_path: str | None
    outcome_matrix_sha256: str | None
    zero_validation_rows: bool
    zero_holdout_rows: bool
    zero_shadow_rows: bool
    zero_network_calls: bool
    join_keys_unique: bool
    all_dates_within_dev: bool
    all_cutoffs_20_30: bool
    gates_passed: bool
    gate_details: dict[str, Any] = field(default_factory=dict)
