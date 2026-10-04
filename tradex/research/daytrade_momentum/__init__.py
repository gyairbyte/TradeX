"""DAYTRADE-002B Locked Early-to-Late ETF Momentum Evaluator & Pipeline Foundation."""
from __future__ import annotations

from .baseline import build_baseline_pool, match_event_baselines
from .bootstrap import run_session_date_cluster_bootstrap
from .calendar import (
    build_regular_session_grid,
    get_immediately_preceding_regular_session,
    get_regular_trading_sessions,
    is_early_close_session,
    is_trading_session,
)
from .dataset import DaytradeDatasetManifest, validate_dataset_root
from .events import (
    calculate_first_half_hour_return,
    classify_session_observation,
    compute_ticker_threshold,
)
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
    SplitDataQualitySummary,
    StudyResult,
)
from .outcomes import (
    apply_friction_to_gross_return,
    calculate_gross_signed_return,
    calculate_gross_win_rate,
)
from .quality import audit_ticker_session, evaluate_split_quality
from .spec import (
    DAYTRADE_002A_SPEC_SHA256,
    LOCKED_FROZEN_UNIVERSE,
    DaytradeSpec,
    load_and_verify_spec,
    verify_spec,
)
from .study import HoldoutAccessDeniedError, evaluate_split, load_and_evaluate_holdout

__version__ = "0.1.0"

__all__ = [
    "DAYTRADE_002A_SPEC_SHA256",
    "LOCKED_FROZEN_UNIVERSE",
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
    "SplitDataQualitySummary",
    "StudyResult",
    "apply_friction_to_gross_return",
    "audit_ticker_session",
    "build_baseline_pool",
    "build_regular_session_grid",
    "calculate_first_half_hour_return",
    "calculate_gross_signed_return",
    "calculate_gross_win_rate",
    "classify_session_observation",
    "compute_ticker_threshold",
    "evaluate_gates_and_disposition",
    "evaluate_split",
    "evaluate_split_quality",
    "freeze_evaluation_state",
    "get_immediately_preceding_regular_session",
    "get_regular_trading_sessions",
    "is_early_close_session",
    "is_trading_session",
    "load_and_evaluate_holdout",
    "load_and_verify_spec",
    "match_event_baselines",
    "run_session_date_cluster_bootstrap",
    "validate_dataset_root",
    "verify_freeze_state",
    "verify_spec",
]
