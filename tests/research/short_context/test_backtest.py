"""Tests for paired backtest candidate scoring and gate logic."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from tradex.backtest.validation import canonicalize_bars
from tradex.market.models import ShortContextPolicy
from tradex.research.score_validation.models import ScoreValidationConfig, Split
from tradex.research.short_context.backtest import (
    _backtest_gate_failures,
    _holdout_window_bars,
    _make_candidate_score_fn,
    run_paired_backtests,
)
from tradex.research.short_context.spec import load_spec


def _trending_df(n: int = 80) -> pd.DataFrame:
    dates = pd.bdate_range(start=datetime(2020, 1, 1, tzinfo=UTC), periods=n)
    prices = 100.0 + pd.Series(range(n)) * 0.5
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices + 0.1,
            "low": prices - 0.1,
            "close": prices,
            "volume": 1_000_000,
        },
        index=dates,
    )


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_manifest(manifest: dict, data_dir: Path) -> Path:
    manifest_path = data_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


def _copy_manifest_with_shifted_dev_val(synthetic_manifest: dict, tmp_path: Path) -> str:
    """Return a new manifest path with development split target prices shifted.

    The validation and holdout windows are unchanged, so the limited warmup
    used by the paired backtest is identical and holdout metrics should match.
    """
    src_dir = Path(synthetic_manifest["data_dir"])
    dst_dir = tmp_path / "data_shifted"
    dst_dir.mkdir()

    for p in src_dir.iterdir():
        if p.suffix == ".csv" or p.name == "context_spec.json":
            shutil.copy2(p, dst_dir / p.name)

    target_csv = dst_dir / "AAPL.csv"
    target = pd.read_csv(target_csv, parse_dates=["datetime"], index_col="datetime")
    # Shift only the development split; validation and holdout are unchanged.
    development_end = pd.Timestamp("2020-06-30", tz="UTC")
    dev_mask = target.index <= development_end
    for col in ["open", "high", "low", "close"]:
        target.loc[dev_mask, col] = target.loc[dev_mask, col] + 1000.0
    target.index.name = "datetime"
    target.to_csv(target_csv, date_format="%Y-%m-%dT%H:%M:%S%z")

    manifest = json.loads((src_dir / "manifest.json").read_text())
    for entry in manifest["entries"]:
        if entry["ticker"] == "AAPL":
            entry["sha256"] = _sha(target_csv)
            entry["rows"] = len(target)
    manifest_path = _write_manifest(manifest, dst_dir)

    shutil.copy2(synthetic_manifest["spec_path"], dst_dir / "context_spec.json")
    return str(manifest_path)


def test_candidate_score_returns_zero_when_ineligible() -> None:
    target = _trending_df(80)
    market = _trending_df(80)
    score_fn = _make_candidate_score_fn(
        ticker="AAPL",
        market_df=market,
        sector_df=None,
        market_proxy="SPY",
        sector_proxy=None,
        policy=ShortContextPolicy.MARKET_RS,
    )
    result = score_fn(target)
    assert result["context_policy"] == "market_rs"
    assert "base_score" in result
    assert "market_context" in result


def test_backtest_gate_empty_candidate_fails() -> None:
    baseline = pd.DataFrame({"ticker": ["AAPL"], "total_trades": [5], "expectancy_pct": [1.0], "total_return_pct": [2.0], "max_drawdown_pct": [-5.0]})
    candidate = pd.DataFrame(columns=["ticker", "total_trades"])
    failures = _backtest_gate_failures(baseline, candidate, None)
    assert failures


def test_paired_backtest_runs_selected_candidate_branch(synthetic_manifest, tmp_path: Path) -> None:
    """Forcing a selected policy must exercise the candidate backtest and gate."""
    result = run_paired_backtests(
        synthetic_manifest["manifest_path"],
        synthetic_manifest["spec"],
        ScoreValidationConfig(),
        selected_policy="market_rs",
    )
    assert not result.baseline_metrics.empty
    assert not result.candidate_metrics.empty
    assert result.baseline_metrics["ticker"].tolist() == ["AAPL"]
    assert result.candidate_metrics["ticker"].tolist() == ["AAPL"]
    assert list(result.candidate_metrics.columns) == [
        "ticker",
        "data_source",
        "total_trades",
        "expectancy_pct",
        "total_return_pct",
        "profit_factor",
        "max_drawdown_pct",
        "sharpe_ratio",
    ]


def test_paired_backtest_ignores_development_and_validation_prices(synthetic_manifest, tmp_path: Path) -> None:
    """Changing pre-holdout target prices must not alter holdout backtest metrics."""
    shifted_manifest_path = _copy_manifest_with_shifted_dev_val(synthetic_manifest, tmp_path)
    spec, _ = load_spec(synthetic_manifest["spec_path"])

    config = ScoreValidationConfig()
    result_a = run_paired_backtests(
        synthetic_manifest["manifest_path"],
        spec,
        config,
        selected_policy="market_rs",
    )
    result_b = run_paired_backtests(
        shifted_manifest_path,
        spec,
        config,
        selected_policy="market_rs",
    )

    baseline_a = result_a.baseline_metrics.iloc[0].to_dict()
    baseline_b = result_b.baseline_metrics.iloc[0].to_dict()
    assert baseline_a["total_trades"] == baseline_b["total_trades"]
    assert baseline_a["total_return_pct"] == pytest.approx(baseline_b["total_return_pct"])
    assert baseline_a["max_drawdown_pct"] == pytest.approx(baseline_b["max_drawdown_pct"])


def test_holdout_window_bars_trims_to_holdout_split() -> None:
    """Pre-holdout bars are retained for warmup, but evaluation ends at holdout end."""
    dates = pd.bdate_range(start=datetime(2020, 1, 1, tzinfo=UTC), periods=200)
    df = pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000,
        },
        index=dates,
    )
    df = canonicalize_bars(df)
    holdout = Split(start=date(2020, 9, 1), end=date(2020, 9, 30))
    bars, warmup = _holdout_window_bars(df, holdout, min_warmup=50)

    last_date = bars.index[-1].date()
    first_holdout_date = bars.index[warmup - 1].date()
    assert last_date <= holdout.end
    assert first_holdout_date == holdout.start
    assert warmup >= 50
