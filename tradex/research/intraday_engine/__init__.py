"""Pure, synthetic intraday engine for the locked INTRA-001 research study."""
from __future__ import annotations

from .cli import main
from .engine import TickerInput, build_ticker_input_from_df, run_study
from .models import (
    Bar,
    CostScenario,
    GateResult,
    OpeningDriveState,
    PerSymbolMetrics,
    Signal,
    StudyMetrics,
    StudyOutcome,
    StudyResult,
    TickerMeta,
    Trade,
)
from .spec import load_spec
from .synthetic import generate_synthetic_inputs

__version__ = "1.0.0"

__all__ = [
    "Bar",
    "CostScenario",
    "GateResult",
    "OpeningDriveState",
    "PerSymbolMetrics",
    "Signal",
    "StudyMetrics",
    "StudyOutcome",
    "StudyResult",
    "TickerInput",
    "TickerMeta",
    "Trade",
    "build_ticker_input_from_df",
    "generate_synthetic_inputs",
    "load_spec",
    "main",
    "run_study",
]
