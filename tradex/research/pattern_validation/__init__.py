"""Pattern-similarity validation study package."""
from __future__ import annotations

from .models import (
    BootstrapConfig,
    DataQualityRow,
    DatasetManifest,
    Fingerprint,
    ManifestEntry,
    Observation,
    PeriodMetrics,
    PromotionDecision,
    Split,
    StudyResult,
    StudySpec,
    TickerMetrics,
    Trade,
    ValidationError,
)
from .report import run_study, write_study
from .snapshot import create_snapshot

__all__ = [
    "BootstrapConfig",
    "DataQualityRow",
    "DatasetManifest",
    "Fingerprint",
    "ManifestEntry",
    "Observation",
    "PeriodMetrics",
    "PromotionDecision",
    "Split",
    "StudyResult",
    "StudySpec",
    "TickerMetrics",
    "Trade",
    "ValidationError",
    "create_snapshot",
    "run_study",
    "write_study",
]
