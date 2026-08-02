"""Shared fixtures for score-validation tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradex.research.score_validation.models import ScoreValidationConfig


@pytest.fixture
def score_config() -> ScoreValidationConfig:
    return ScoreValidationConfig(warmup_bars=50)


def make_synthetic_bars(
    n: int = 120,
    *,
    start: str = "2020-01-01",
    close: np.ndarray | None = None,
    tz: str = "UTC",
) -> pd.DataFrame:
    if close is None:
        t = np.arange(n)
        close = 100 + 0.2 * t + 0.5 * np.sin(t / 3)
        close[-10:] += np.linspace(0, 1.5, 10)
    opens = close - 0.1
    highs = close + 0.5
    lows = close - 0.5
    idx = pd.date_range(start, periods=n, freq="D", tz=tz)
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": close,
            "volume": np.ones(n) * 1e6,
        },
        index=idx,
    )


def write_bars_and_manifest(tmp_path: Path) -> tuple[Path, pd.DataFrame, str]:
    """Write a single-ticker CSV + manifest into ``tmp_path`` and return manifest path."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    df = make_synthetic_bars(120)
    df.index.name = "datetime"
    csv_path = tmp_path / "TEST.csv"
    df.to_csv(csv_path)
    sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "dataset_name": "test",
        "created_at": "2026-08-01T00:00:00+00:00",
        "source_description": "synthetic test data",
        "entries": [
            {
                "ticker": "TEST",
                "path": "TEST.csv",
                "sha256": sha,
                "rows": len(df),
                "start": df.index[0].isoformat(),
                "end": df.index[-1].isoformat(),
                "data_source": "synthetic",
                "adjustment_policy": "none",
            }
        ],
        "splits": {
            "development": {"start": "2020-01-01", "end": "2021-12-31"},
            "validation": {"start": "2022-01-01", "end": "2023-12-31"},
            "holdout": {"start": "2024-01-01", "end": "2025-12-31"},
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path, df, sha


@pytest.fixture
def manifest_and_bars(tmp_path: Path) -> tuple[Path, pd.DataFrame, str]:
    return write_bars_and_manifest(tmp_path)
