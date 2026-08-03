"""Shared fixtures for short-term context research tests."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradex.research.short_context.spec import load_spec


def make_ohlcv(
    n: int = 120,
    start_date: datetime | None = None,
    growth: float = 0.002,
    noise: float = 0.005,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a deterministic daily OHLCV DataFrame with an upward trend."""
    if start_date is None:
        start_date = datetime(2020, 1, 1, tzinfo=UTC)
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start_date, periods=n)
    returns = rng.normal(growth, noise, n)
    prices = 100.0 * np.exp(np.cumsum(returns))
    opens = prices * (1 + rng.uniform(-0.005, 0.005, n))
    closes = prices * (1 + rng.uniform(-0.005, 0.005, n))
    high = np.maximum(opens, closes) * (1 + rng.uniform(0, 0.01, n))
    low = np.minimum(opens, closes) * (1 - rng.uniform(0, 0.01, n))
    volumes = 1_000_000 + np.arange(n) * 50_000 + rng.integers(0, 100_000, n)
    df = pd.DataFrame(
        {
            "datetime": dates,
            "open": opens,
            "high": high,
            "low": low,
            "close": closes,
            "volume": volumes.astype(int),
        }
    )
    df.set_index("datetime", inplace=True)
    df.index = df.index.tz_convert(UTC)
    return df


def make_market_proxy(n: int = 120, start_date: datetime | None = None, seed: int = 43) -> pd.DataFrame:
    """A slower-rising proxy used for market and sector context."""
    if start_date is None:
        start_date = datetime(2020, 1, 1, tzinfo=UTC)
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start_date, periods=n)
    returns = rng.normal(0.0005, 0.004, n)
    prices = 200.0 * np.exp(np.cumsum(returns))
    opens = prices * (1 + rng.uniform(-0.001, 0.001, n))
    closes = prices * (1 + rng.uniform(-0.001, 0.001, n))
    high = np.maximum(opens, closes) * (1 + rng.uniform(0, 0.005, n))
    low = np.minimum(opens, closes) * (1 - rng.uniform(0, 0.005, n))
    df = pd.DataFrame(
        {
            "datetime": dates,
            "open": opens,
            "high": high,
            "low": low,
            "close": closes,
            "volume": 10_000_000 + rng.integers(0, 1_000_000, n),
        }
    )
    df.set_index("datetime", inplace=True)
    df.index = df.index.tz_convert(UTC)
    return df


def write_df(df: pd.DataFrame, path: Path) -> str:
    """Write a DataFrame to CSV and return its SHA-256 hex digest."""
    df = df.copy()
    df.index.name = "datetime"
    df.to_csv(path, date_format="%Y-%m-%dT%H:%M:%S%z")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture
def synthetic_manifest(tmp_path: Path):
    """Create a small manifest with a target, market proxy, and sector proxy."""
    n = 252
    start = datetime(2020, 1, 1, tzinfo=UTC)
    target = make_ohlcv(n=n, start_date=start, seed=42)
    market = make_market_proxy(n=n, start_date=start, seed=43)
    sector = make_market_proxy(n=n, start_date=start, seed=44)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target_sha = write_df(target, data_dir / "AAPL.csv")
    market_sha = write_df(market, data_dir / "SPY.csv")
    sector_sha = write_df(sector, data_dir / "XLK.csv")

    manifest = {
        "schema_version": 1,
        "dataset_name": "short-context-synthetic",
        "created_at": datetime.now(UTC).isoformat(),
        "source_description": "synthetic",
        "entries": [
            _entry("AAPL", "AAPL.csv", target_sha, target, "synthetic"),
            _entry("SPY", "SPY.csv", market_sha, market, "synthetic"),
            _entry("XLK", "XLK.csv", sector_sha, sector, "synthetic"),
        ],
        "splits": {
            "development": {"start": "2020-01-01", "end": "2020-06-30"},
            "validation": {"start": "2020-07-01", "end": "2020-09-30"},
            "holdout": {"start": "2020-10-01", "end": "2020-12-31"},
        },
    }
    manifest_path = data_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    spec = {
        "schema_version": 1,
        "study_name": "synthetic-short-context",
        "target_tickers": ["AAPL"],
        "default_market_proxy": "SPY",
        "ticker_context": {
            "AAPL": {"market_proxy": "SPY", "sector_proxy": "XLK"},
        },
        "candidate_policies": ["market_rs", "market_sector_rs"],
        "primary_horizon_bars": 3,
        "primary_slippage_bps": 5.0,
        "horizons": [1, 3, 5],
        "slippage_scenarios_bps": [0.0, 5.0, 10.0],
        "commission_bps": 0.0,
        "minimum_holdout_events": 5,
        "minimum_holdout_tickers": 1,
        "minimum_event_retention_pct": 10.0,
        "minimum_ticker_coverage_pct": 10.0,
        "baseline_score_threshold": 40,
    }
    spec_path = tmp_path / "context_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2))
    spec_obj, _ = load_spec(spec_path)

    return {
        "manifest_path": str(manifest_path),
        "spec_path": str(spec_path),
        "spec": spec_obj,
        "data_dir": str(data_dir),
        "target": target,
        "market": market,
        "sector": sector,
    }


def _entry(ticker: str, rel_path: str, sha: str, df: pd.DataFrame, source: str) -> dict:
    return {
        "ticker": ticker,
        "path": rel_path,
        "sha256": sha,
        "rows": len(df),
        "start": df.index[0].isoformat(),
        "end": df.index[-1].isoformat(),
        "data_source": source,
        "adjustment_policy": "provider_default",
    }
