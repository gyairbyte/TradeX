"""DAYTRADE-001C1 Locked 1-Minute Extreme Downside Reversal Engine & Pipeline Foundation."""
from __future__ import annotations

from .baseline import build_baseline_pool, match_event_baselines
from .bootstrap import run_joint_cluster_bootstrap
from .calendar import build_regular_session_grid, is_early_close_session, is_trading_session
from .dataset import DaytradeDatasetManifest, validate_dataset_root
from .events import classify_overlapping_events, compute_session_threshold, detect_events_in_session
from .freeze import freeze_evaluation_state, verify_freeze_state
from .gates import evaluate_gates_and_disposition
from .models import (
    BaselineObservation,
    BootstrapCI,
    DataQualityReport,
    DaytradeBar,
    DaytradeSession,
    EventObservation,
    GateEvaluationResult,
    HorizonOutcome,
    SplitDataQualitySummary,
    StudyResult,
)
from .outcomes import calculate_horizon_outcomes_for_bar
from .quality import audit_ticker_session, evaluate_split_quality
from .spec import DAYTRADE_001B_SPEC_SHA256, DaytradeSpec, load_and_verify_spec
from .study import HoldoutAccessDeniedError, evaluate_split, load_and_evaluate_holdout

__version__ = "0.1.0"

__all__ = [
    "DAYTRADE_001B_SPEC_SHA256",
    "BaselineObservation",
    "BootstrapCI",
    "DataQualityReport",
    "DaytradeBar",
    "DaytradeDatasetManifest",
    "DaytradeSession",
    "DaytradeSpec",
    "EventObservation",
    "GateEvaluationResult",
    "HoldoutAccessDeniedError",
    "HorizonOutcome",
    "SplitDataQualitySummary",
    "StudyResult",
    "audit_ticker_session",
    "build_baseline_pool",
    "build_regular_session_grid",
    "calculate_horizon_outcomes_for_bar",
    "classify_overlapping_events",
    "compute_session_threshold",
    "detect_events_in_session",
    "evaluate_gates_and_disposition",
    "evaluate_split",
    "evaluate_split_quality",
    "freeze_evaluation_state",
    "is_early_close_session",
    "is_trading_session",
    "load_and_evaluate_holdout",
    "load_and_verify_spec",
    "match_event_baselines",
    "run_joint_cluster_bootstrap",
    "validate_dataset_root",
    "verify_freeze_state",
]
