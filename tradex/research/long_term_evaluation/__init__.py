"""LONG-001 research-only evaluation of the production long-term score."""
from __future__ import annotations

from .cli import main
from .evaluate import _derive_conclusion, _load_ticker_df, _score_bar, _score_vectorized, evaluate_study
from .models import (
    CONCLUSION_ORDER,
    LONG_TERM_BENCHMARK,
    LONG_TERM_ETF_UNIVERSE,
    LONG_TERM_STOCK_UNIVERSE,
    LONG_TERM_UNIVERSE,
    DataQualityRow,
    DatasetManifest,
    EventOutcome,
    EventRecord,
    LongTermStudySpec,
    ManifestEntry,
    StudyError,
    StudyResult,
    _aggregate_daily_to_weekly,
    _file_sha256,
    _validate_bars,
    load_manifest,
)
from .snapshot import snapshot_dataset

__all__ = [
    "CONCLUSION_ORDER",
    "LONG_TERM_BENCHMARK",
    "LONG_TERM_ETF_UNIVERSE",
    "LONG_TERM_STOCK_UNIVERSE",
    "LONG_TERM_UNIVERSE",
    "DataQualityRow",
    "DatasetManifest",
    "EventOutcome",
    "EventRecord",
    "LongTermStudySpec",
    "ManifestEntry",
    "StudyError",
    "StudyResult",
    "_aggregate_daily_to_weekly",
    "_derive_conclusion",
    "_file_sha256",
    "_load_ticker_df",
    "_score_bar",
    "_score_vectorized",
    "_validate_bars",
    "evaluate_study",
    "load_manifest",
    "main",
    "snapshot_dataset",
]
