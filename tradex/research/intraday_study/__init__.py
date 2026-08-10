"""INTRA-001D locked real-data intraday study adapter and orchestrator."""
from __future__ import annotations

from .cli import main
from .loader import load_symbol_month
from .manifest import (
    SymbolMonth,
    load_data_quality,
    load_manifest_lock,
    load_universe_manifest,
    verify_dataset_integrity,
)
from .study import run_split

__version__ = "1.0.0"

__all__ = [
    "SymbolMonth",
    "load_data_quality",
    "load_manifest_lock",
    "load_symbol_month",
    "load_universe_manifest",
    "main",
    "run_split",
    "verify_dataset_integrity",
]
