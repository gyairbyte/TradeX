"""TradeX multi-resolution day-trading research MVP package (DAYTRADE-001A)."""
from __future__ import annotations

from .evaluator import evaluate_setup
from .models import (
    CompletedBar,
    MultiResolutionSeries,
    Resolution,
    SetupEvaluationResult,
    SetupEvaluationStatus,
)
from .setup import DaytradeSetup
from .synthetic import (
    SYNTH_DAYTRADE_001,
    SyntheticDaytradeSetup,
    generate_synthetic_multi_res_data,
)

__version__ = "0.1.0"

__all__ = [
    "SYNTH_DAYTRADE_001",
    "CompletedBar",
    "DaytradeSetup",
    "MultiResolutionSeries",
    "Resolution",
    "SetupEvaluationResult",
    "SetupEvaluationStatus",
    "SyntheticDaytradeSetup",
    "evaluate_setup",
    "generate_synthetic_multi_res_data",
]
