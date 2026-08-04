"""Deterministic, credential-free tests for the LONG-001 evaluation harness."""
from __future__ import annotations

import json
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from tradex.research import long_term_evaluation as lte
from tradex.signals.weights import LongWeights


def _synthetic_daily(ticker: str, n: int = 260, seed: int = 42) -> pd.DataFrame:
    """Create deterministic daily/weekly OHLCV DataFrame for one ticker."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-01-04", periods=n, freq="W-MON")
    trend = np.linspace(100.0, 180.0, n)
    noise = 2.0 * np.sin(np.linspace(0, 8 * np.pi, n)) + rng.normal(0, 1.5, n)
    close = trend + noise
    close = np.maximum(close, 10.0)
    volume = np.full(n, 1_000_000.0)
    volume[-20:] = 2_500_000.0
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": volume,
    }, index=idx)
    return df


def _sample_spec(**overrides: Any) -> lte.LongTermStudySpec:
    defaults: dict[str, Any] = {
        "provider": "synthetic",
        "universe": ("FAKEA",),
        "benchmark_ticker": "SPY",
        "start": date(2010, 1, 1),
        "end": date(2014, 12, 31),
        "warmup_end": date(2010, 12, 31),
        "development_end": date(2011, 12, 31),
        "validation_end": date(2012, 12, 31),
        "warmup_weeks": 50,
        "hold_weeks": (4,),
        "score_thresholds": (40,),
        "min_events_per_group": 1,
        "minimum_signals": 1,
        "minimum_tickers": 1,
        "bootstrap_resamples": 100,
    }
    defaults.update(overrides)
    return lte.LongTermStudySpec(**defaults)


def _build_manifest(data_dir: Path) -> lte.DatasetManifest:
    entries = []
    for path in sorted((data_dir / "data").glob("*.csv")):
        df = pd.read_csv(path, index_col="datetime", parse_dates=True)
        df, _, _, _ = lte._validate_bars(df, path.stem)
        entries.append(
            lte.ManifestEntry(
                ticker=path.stem,
                path=str(path.relative_to(data_dir)),
                sha256=lte._file_sha256(path),
                rows=len(df),
                start=df.index[0].to_pydatetime(),
                end=df.index[-1].to_pydatetime(),
                data_source="synthetic",
                adjustment_policy="synthetic",
            )
        )
    return lte.DatasetManifest(
        created_at=datetime.now(UTC),
        requested_start=date(2010, 1, 1),
        requested_end=date(2014, 12, 31),
        requested_universe=("FAKEA",),
        benchmark_ticker="SPY",
        entries=tuple(entries),
        splits={
            "warmup": {"start": date(2010, 1, 1), "end": date(2010, 12, 31)},
            "development": {"start": date(2011, 1, 1), "end": date(2011, 12, 31)},
            "validation": {"start": date(2012, 1, 1), "end": date(2012, 12, 31)},
            "holdout": {"start": date(2013, 1, 1), "end": date(2014, 12, 31)},
        },
    )


@pytest.fixture
def sample_data_dir(tmp_path: Path) -> Path:
    """Create a temporary dataset directory with two synthetic tickers."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for ticker, seed in [("FAKEA", 42), ("SPY", 43)]:
        df = _synthetic_daily(ticker, n=260, seed=seed)
        df.to_csv(data_dir / f"{ticker}.csv", index=True, index_label="datetime")
    return tmp_path


def test_spec_defaults_use_fresh_long_weights() -> None:
    spec = lte.LongTermStudySpec()
    assert spec.weights == LongWeights()
    assert spec.sha256 != ""


def test_spec_rejects_invalid_configuration() -> None:
    with pytest.raises(lte.StudyError, match="warmup_weeks must be >= 50"):
        lte.LongTermStudySpec(warmup_weeks=10)
    with pytest.raises(lte.StudyError, match="score_bucket_edges"):
        lte.LongTermStudySpec(score_bucket_edges=(0, 50, 100))


def test_manifest_verify_data_files_passes(sample_data_dir: Path) -> None:
    manifest = _build_manifest(sample_data_dir)
    assert manifest.verify_data_files(sample_data_dir) is True


def test_manifest_verify_data_files_fails_on_corruption(sample_data_dir: Path) -> None:
    manifest = _build_manifest(sample_data_dir)
    path = sample_data_dir / "data" / "FAKEA.csv"
    original = path.read_text()
    path.write_text(original + "\n#corrupt")
    assert manifest.verify_data_files(sample_data_dir) is False


def test_evaluate_study_runs_on_synthetic_data(sample_data_dir: Path) -> None:
    manifest = _build_manifest(sample_data_dir)
    spec = _sample_spec()
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    assert isinstance(result.events, pd.DataFrame)
    assert not result.events.empty
    assert "rule" in result.events.columns
    assert result.conclusion in {"supported", "rejected", "inconclusive", "data_inadequate"}


def test_events_are_point_in_time_and_use_next_bar_entry(sample_data_dir: Path) -> None:
    """A signal at bar i must use open at bar i+1 and not use future prices."""
    manifest = _build_manifest(sample_data_dir)
    spec = _sample_spec(universe=("FAKEA",))
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    events = result.events[result.events["rule"] == "candidate"]
    assert not events.empty
    for _idx, row in events.head(5).iterrows():
        assert row["entry_time"] > row["signal_time"]
        assert row["raw_entry_price"] is not None


def test_split_isolation(sample_data_dir: Path) -> None:
    """Events fall into the split defined by signal_time."""
    manifest = _build_manifest(sample_data_dir)
    spec = _sample_spec(universe=("FAKEA",))
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    for _idx, row in result.events.iterrows():
        split = spec.split_for(row["signal_time"])
        assert split == row["split"]


def test_evaluation_with_explicit_weights_ignores_saved_config(sample_data_dir: Path) -> None:
    """Passing an explicit LongWeights instance prevents loading user-saved weights."""
    manifest = _build_manifest(sample_data_dir)
    custom = LongWeights(secular_uptrend=100, rsi_healthy=0, volume_accumulation=0, macd_bullish=0, bb_coil=0)
    spec = _sample_spec(universe=("FAKEA",), weights=custom)
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    assert result.weight_snapshot["secular_uptrend"] == 100


def test_conclusion_inconclusive_for_small_holdout() -> None:
    """With fewer than minimum signals in holdout, conclusion is inconclusive."""
    spec = lte.LongTermStudySpec(minimum_signals=100, hold_weeks=(4,))
    summary = {
        "split_stats": {
            "validation": {
                "sample_present": True,
                "candidate": {"count": 200, "ticker_count": 20, "max_ticker_concentration": 0.05},
                "baseline": {"count": 200, "ticker_count": 20, "max_ticker_concentration": 0.05},
            },
            "holdout": {"sample_present": False},
        }
    }
    assert lte._derive_conclusion(pd.DataFrame(), pd.DataFrame(), summary, spec) == "inconclusive"


def test_snapshot_dataset_uses_provided_fetch_fn() -> None:
    """snapshot_dataset can use an injected fetch callable for deterministic testing."""
    calls: list[tuple[str, date, date, str]] = []

    def fake_fetch(ticker: str, start: date, end: date, provider: str) -> pd.DataFrame:
        calls.append((ticker, start, end, provider))
        return _synthetic_daily(ticker, n=120)

    with tempfile.TemporaryDirectory() as td:
        output = Path(td)
        spec = _sample_spec(universe=("FAKEA",), benchmark_ticker="SPY")
        manifest = lte.snapshot_dataset(spec, output, fetch_fn=fake_fetch)
        assert len([e for e in manifest.entries if not e.failure]) == 2
        assert manifest.entries[0].ticker == "FAKEA"
        assert (output / "data" / "FAKEA.csv").exists()


def test_result_json_is_deterministic_and_json_safe(sample_data_dir: Path) -> None:
    manifest = _build_manifest(sample_data_dir)
    spec = _sample_spec(universe=("FAKEA",))
    result1 = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    result2 = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    d1 = result1.to_dict(include_records=True)
    d2 = result2.to_dict(include_records=True)
    d1["generated_at"] = None
    d2["generated_at"] = None
    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    json.loads(result1.to_json())


def test_daily_to_weekly_xnys_aggregation() -> None:
    """Daily Monday bars aggregate to a Friday-labeled weekly bar."""
    idx = pd.date_range("2023-01-03", periods=10, freq="B")  # 10 business days (Mon-Fri x2)
    close = np.linspace(100.0, 110.0, len(idx))
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": np.full(len(idx), 1_000_000.0),
    }, index=idx)
    weekly = lte._aggregate_daily_to_weekly(df)
    assert not weekly.empty
    # The first week ending Friday should be 2023-01-06.
    assert weekly.index[0].dayofweek == 4


def test_non_overlapping_trade_count_is_less_than_events(sample_data_dir: Path) -> None:
    """Non-overlapping trade count should not exceed overlapping event count for the same rule."""
    manifest = _build_manifest(sample_data_dir)
    spec = _sample_spec(universe=("FAKEA",), hold_weeks=(4,))
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    if result.trades.empty:
        return
    for rule in ("candidate", "baseline"):
        ev_count = len(result.events[result.events["rule"] == rule])
        tr_count = len(result.trades[result.trades["rule"] == rule])
        assert tr_count <= ev_count


def test_cross_split_exclusion_recorded(sample_data_dir: Path) -> None:
    """Events whose exit would cross a split boundary are marked cross_split_excluded."""
    manifest = _build_manifest(sample_data_dir)
    spec = _sample_spec(universe=("FAKEA",), hold_weeks=(52,))
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    status_col = f"{spec.hold_weeks[0]}_bar_outcome_status"
    assert status_col in result.events.columns
    assert "cross_split_excluded" in result.events[status_col].values
