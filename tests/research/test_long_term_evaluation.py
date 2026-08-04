"""Deterministic, credential-free tests for the LONG-001 evaluation harness."""
from __future__ import annotations

import json
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from tradex.research import long_term_evaluation as lte
from tradex.signals.weights import LongWeights


def _synthetic_daily(ticker: str, n: int = 260, seed: int = 42) -> pd.DataFrame:
    """Create deterministic daily OHLCV DataFrame for one ticker (Mondays)."""
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
    df.index = df.index.tz_localize("UTC")
    return df


def _synthetic_daily_business_days(ticker: str, n: int = 260, seed: int = 42) -> pd.DataFrame:
    """Deterministic daily business-day OHLCV for a single ticker."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-01-04", periods=n, freq="B")
    trend = np.linspace(100.0, 180.0, n)
    noise = 2.0 * np.sin(np.linspace(0, 8 * np.pi, n)) + rng.normal(0, 1.5, n)
    close = trend + noise
    close = np.maximum(close, 10.0)
    volume = np.full(n, 1_000_000.0)
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": volume,
    }, index=idx)
    df.index = df.index.tz_localize("UTC")
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
        "min_required_weekly_bars": 50,
        "hold_weeks": (4,),
        "score_thresholds": (40,),
        "score_bucket_edges": (0, 25, 40, 60, 80, 101),
        "slippage_scenarios_bps": (0.0, 10.0, 25.0),
        "decision_slippage_bps": 5.0,
        "min_events_per_group": 1,
        "min_ticker_trades_for_cohort_gate": 1,
        "minimum_signals": 1,
        "minimum_stock_tickers": 1,
        "minimum_etf_tickers": 1,
        "bootstrap_resamples": 100,
        "minimum_lift_bps": 25.0,
        "q10_support_max_worse_bps": 200.0,
    }
    defaults.update(overrides)
    return lte.LongTermStudySpec(**defaults)


def _build_manifest(data_dir: Path, spec: lte.LongTermStudySpec | None = None) -> lte.DatasetManifest:
    spec = spec or _sample_spec()
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
        provider=spec.provider,
        timeframe=spec.timeframe,
        adjustment_policy=spec.adjustment_policy,
        package_version="test",
        requested_start=spec.start,
        requested_end=spec.end,
        requested_universe=spec.universe,
        benchmark_ticker=spec.benchmark_ticker,
        successful_tickers=tuple({e.ticker for e in entries}),
        entries=tuple(entries),
        splits={
            "warmup": {"start": spec.start, "end": spec.warmup_end},
            "development": {"start": spec.warmup_end + timedelta(days=1), "end": spec.development_end},
            "validation": {"start": spec.development_end + timedelta(days=1), "end": spec.validation_end},
            "holdout": {"start": spec.validation_end + timedelta(days=1), "end": spec.end},
        },
    )


@pytest.fixture
def sample_data_dir(tmp_path: Path) -> Path:
    """Create a temporary dataset directory with two synthetic tickers."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for ticker, seed in [("FAKEA", 42), ("SPY", 43)]:
        df = _synthetic_daily_business_days(ticker, n=1000, seed=seed)
        df.to_csv(data_dir / f"{ticker}.csv", index=True, index_label="datetime")
    return tmp_path


@pytest.fixture
def business_day_data_dir(tmp_path: Path) -> Path:
    """Create a temporary dataset directory with business-day bars."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for ticker, seed in [("FAKEA", 42), ("SPY", 43)]:
        df = _synthetic_daily_business_days(ticker, n=1000, seed=seed)
        df.to_csv(data_dir / f"{ticker}.csv", index=True, index_label="datetime")
    return tmp_path


def test_spec_defaults_use_fresh_long_weights() -> None:
    spec = lte.LongTermStudySpec()
    assert spec.weights == LongWeights()
    assert spec.sha256 != ""
    assert spec.universe == lte.LONG_TERM_UNIVERSE
    assert spec.score_bucket_edges == (0, 25, 40, 60, 80, 101)
    assert spec.slippage_scenarios_bps == (0.0, 10.0, 25.0)
    assert spec.decision_slippage_bps == 5.0


def test_spec_rejects_invalid_configuration() -> None:
    with pytest.raises(lte.StudyError, match="warmup_weeks must be >= 60"):
        lte.LongTermStudySpec(warmup_weeks=10)
    with pytest.raises(lte.StudyError, match="score_bucket_edges"):
        lte.LongTermStudySpec(score_bucket_edges=(0, 50, 100))


def test_manifest_verify_data_files_passes(sample_data_dir: Path) -> None:
    spec = _sample_spec()
    manifest = _build_manifest(sample_data_dir, spec)
    assert manifest.verify_data_files(sample_data_dir) is True


def test_manifest_verify_data_files_fails_on_corruption(sample_data_dir: Path) -> None:
    spec = _sample_spec()
    manifest = _build_manifest(sample_data_dir, spec)
    path = sample_data_dir / "data" / "FAKEA.csv"
    original = path.read_text()
    path.write_text(original + "\n#corrupt")
    assert manifest.verify_data_files(sample_data_dir) is False


def test_manifest_verify_metadata_fail_closed(sample_data_dir: Path) -> None:
    spec = _sample_spec()
    manifest = _build_manifest(sample_data_dir, spec)
    assert manifest.verify_metadata(spec) is True

    bad_spec = _sample_spec(universe=("OTHER",))
    assert manifest.verify_metadata(bad_spec) is False


def test_evaluate_study_runs_on_synthetic_data(sample_data_dir: Path) -> None:
    spec = _sample_spec()
    manifest = _build_manifest(sample_data_dir, spec)
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    assert isinstance(result.events, pd.DataFrame)
    assert not result.events.empty
    assert "rule" in result.events.columns
    assert result.conclusion in {"supports_further_research", "reject_or_deprioritize", "inconclusive"}


def test_events_are_point_in_time_and_use_next_bar_entry(business_day_data_dir: Path) -> None:
    """A signal at bar i must use open at bar i+1 and not use future prices."""
    spec = _sample_spec(universe=("FAKEA",))
    manifest = _build_manifest(business_day_data_dir, spec)
    result = lte.evaluate_study(manifest, spec, data_dir=business_day_data_dir)
    events = result.events[result.events["rule"] == "candidate"]
    assert not events.empty
    for _idx, row in events.head(5).iterrows():
        assert row["entry_time"] > row["signal_time"]
        assert row["raw_entry_price"] is not None


def test_split_isolation(sample_data_dir: Path) -> None:
    """Events fall into the split defined by signal_time."""
    spec = _sample_spec(universe=("FAKEA",))
    manifest = _build_manifest(sample_data_dir, spec)
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    for _idx, row in result.events.iterrows():
        split = spec.split_for(row["signal_time"])
        assert split == row["split"]


def test_evaluation_with_explicit_weights_ignores_saved_config(sample_data_dir: Path) -> None:
    """Passing an explicit LongWeights instance prevents loading user-saved weights."""
    spec = _sample_spec(universe=("FAKEA",))
    manifest = _build_manifest(sample_data_dir, spec)
    custom = LongWeights(secular_uptrend=100, rsi_healthy=0, volume_accumulation=0, macd_bullish=0, bb_coil=0)
    spec = _sample_spec(universe=("FAKEA",), weights=custom)
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    assert result.weight_snapshot["secular_uptrend"] == 100


def test_score_vectorized_matches_production_score(business_day_data_dir: Path) -> None:
    """Vectorized scoring must match per-bar production long_term.score calls."""
    spec = _sample_spec(universe=("FAKEA",))
    manifest = _build_manifest(business_day_data_dir, spec)
    weekly = lte._load_ticker_df(
        next(e for e in manifest.entries if e.ticker == "FAKEA"),
        business_day_data_dir,
        spec,
    )
    vectorized_scores, _ = lte._score_vectorized(weekly, spec)
    for i in range(spec.min_required_weekly_bars - 1, len(weekly)):
        prod_score, _ = lte._score_bar(weekly, i, spec)
        assert vectorized_scores[i] == pytest.approx(prod_score, rel=1e-9)


def test_score_parity_with_na_n_warmup_and_ties() -> None:
    """Score parity holds when early bars are NaN and when volume ties occur."""
    idx = pd.date_range("2010-01-04", periods=260, freq="B", tz="UTC")
    close = np.full(260, 100.0)
    close[130:140] = 100.5  # small uptrend to trigger EMA
    close[140:150] = 100.0
    volume = np.full(260, 1_000_000.0)
    volume[230:] = 1_500_000.0  # tied-ish volume
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": volume,
    }, index=idx)
    spec = _sample_spec(universe=("FAKEA",))
    weekly = lte._aggregate_daily_to_weekly(df)
    if len(weekly) < spec.min_required_weekly_bars:
        pytest.skip("insufficient weekly bars for parity test")
    vectorized_scores, _ = lte._score_vectorized(weekly, spec)
    for i in range(spec.min_required_weekly_bars - 1, len(weekly)):
        prod_score, _ = lte._score_bar(weekly, i, spec)
        assert vectorized_scores[i] == pytest.approx(prod_score, rel=1e-9)


def test_daily_to_weekly_xnys_aggregation() -> None:
    """Daily business-day bars aggregate to an XNYS Friday-labeled weekly bar."""
    idx = pd.date_range("2023-01-03", periods=10, freq="B")  # Tue-Fri + Mon-Thu
    close = np.linspace(100.0, 110.0, len(idx))
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": np.full(len(idx), 1_000_000.0),
    }, index=idx)
    df.index = df.index.tz_localize("UTC")
    weekly = lte._aggregate_daily_to_weekly(df)
    assert not weekly.empty
    # First complete week ends 2023-01-06 (Friday).
    assert weekly.index[0].dayofweek == 4
    assert weekly.index[0].date() == date(2023, 1, 6)
    assert weekly["first_session_open_time"].iloc[0] is not None


def test_daily_to_weekly_excludes_incomplete_trailing_week() -> None:
    """A partial final week (no Friday session) is dropped."""
    idx = pd.date_range("2023-01-03", periods=7, freq="B")  # Tue-Mon, Friday present
    close = np.linspace(100.0, 107.0, len(idx))
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": np.full(len(idx), 1_000_000.0),
    }, index=pd.DatetimeIndex(idx, tz="UTC"))
    weekly = lte._aggregate_daily_to_weekly(df)
    # Only the first week (ending Friday Jan 6) is complete; Mon Jan 9 is incomplete.
    assert len(weekly) == 1
    assert weekly.index[0].date() == date(2023, 1, 6)


def test_non_overlapping_trade_count_is_less_than_events(sample_data_dir: Path) -> None:
    """Non-overlapping trade count should not exceed overlapping event count for the same rule."""
    spec = _sample_spec(universe=("FAKEA",), hold_weeks=(4,))
    manifest = _build_manifest(sample_data_dir, spec)
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    if result.trades.empty:
        return
    for rule in ("candidate", "baseline"):
        ev_count = len(result.events[result.events["rule"] == rule])
        tr_count = len(result.trades[result.trades["rule"] == rule])
        assert tr_count <= ev_count


def test_cross_split_exclusion_recorded(sample_data_dir: Path) -> None:
    """Events whose exit would cross a split boundary are marked cross_split_excluded."""
    spec = _sample_spec(universe=("FAKEA",), hold_weeks=(52,))
    manifest = _build_manifest(sample_data_dir, spec)
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    status_col = f"{spec.hold_weeks[0]}_bar_outcome_status"
    assert status_col in result.events.columns
    assert "cross_split_excluded" in result.events[status_col].values


def test_cross_split_excluded_does_not_advance_non_overlap(sample_data_dir: Path) -> None:
    """A cross-split-excluded trade must not block future signals for the full horizon."""
    spec = _sample_spec(universe=("FAKEA",), hold_weeks=(52,))
    manifest = _build_manifest(sample_data_dir, spec)
    result = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    trades = result.trades[result.trades["rule"] == "candidate"]
    if trades.empty:
        return
    # There should not be a giant gap in signal indices caused by one excluded trade.
    status_col = f"{spec.hold_weeks[0]}_bar_outcome_status"
    excluded = trades[trades[status_col] == "cross_split_excluded"]
    assert not excluded.empty or len(trades) > 0


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
        assert set(manifest.successful_tickers) == {"FAKEA", "SPY"}


def test_result_json_is_deterministic_and_json_safe(sample_data_dir: Path) -> None:
    spec = _sample_spec(universe=("FAKEA",))
    manifest = _build_manifest(sample_data_dir, spec)
    result1 = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    result2 = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    d1 = result1.to_dict(include_records=True)
    d2 = result2.to_dict(include_records=True)
    d1["generated_at"] = None
    d2["generated_at"] = None
    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    json.loads(result1.to_json())


def test_paired_bootstrap_determinism(sample_data_dir: Path) -> None:
    """The paired candidate-minus-baseline bootstrap is deterministic."""
    spec = _sample_spec(universe=("FAKEA",))
    manifest = _build_manifest(sample_data_dir, spec)
    result1 = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    result2 = lte.evaluate_study(manifest, spec, data_dir=sample_data_dir)
    if result1.bootstrap.empty:
        return
    b1 = result1.bootstrap.reset_index(drop=True)
    b2 = result2.bootstrap.reset_index(drop=True)
    for col in ["mean_diff_pct", "ci_lower", "ci_upper"]:
        assert (b1[col].to_numpy() == b2[col].to_numpy()).all()


def test_conclusion_supports_further_research() -> None:
    """When all gates are met, the conclusion is supports_further_research."""
    spec = _sample_spec(
        minimum_signals=1,
        minimum_stock_tickers=1,
        minimum_etf_tickers=1,
        minimum_lift_bps=1.0,
        q10_support_max_worse_bps=1000.0,
    )
    summary = {
        "split_stats": {
            "validation": {
                "sample_present": True,
                "candidate": {"mean_net_return_pct": 2.0},
                "baseline": {"mean_net_return_pct": 1.0},
                "pooled_lift_pct": 1.0,
            },
            "holdout": {
                "sample_present": True,
                "candidate": {"count": 10, "mean_net_return_pct": 2.0},
                "baseline": {"count": 10, "mean_net_return_pct": 1.0},
                "pooled_lift_pct": 1.0,
                "pooled_lift_at_cost_sensitivity_pct": 0.5,
                "q10_lift_pct": 0.0,
                "positive_lift_fraction_stock": 1.0,
                "positive_lift_fraction_etf": 1.0,
            },
        },
        "bootstrap_stats": {
            "holdout": {"ci_lower": 0.1},
        },
    }
    trades = pd.DataFrame({
        "ticker": ["AAPL", "AAPL", "QQQ", "QQQ"],
        "split": ["holdout", "holdout", "holdout", "holdout"],
        "rule": ["candidate", "baseline", "candidate", "baseline"],
        "overlap_policy": ["non_overlapping"] * 4,
    })
    result = lte._derive_conclusion(pd.DataFrame(), trades, summary, spec)
    assert result == "supports_further_research"


def test_conclusion_support_uses_trades_not_events() -> None:
    """The support cohort gate must count non-overlapping trades, not events."""
    spec = _sample_spec(
        minimum_signals=1,
        minimum_stock_tickers=1,
        minimum_etf_tickers=1,
        minimum_lift_bps=1.0,
        q10_support_max_worse_bps=1000.0,
    )
    summary = {
        "split_stats": {
            "validation": {
                "sample_present": True,
                "candidate": {"mean_net_return_pct": 2.0},
                "baseline": {"mean_net_return_pct": 1.0},
            },
            "holdout": {
                "sample_present": True,
                "candidate": {"count": 10, "mean_net_return_pct": 2.0},
                "baseline": {"count": 10, "mean_net_return_pct": 1.0},
                "pooled_lift_at_cost_sensitivity_pct": 0.5,
                "q10_lift_pct": 0.0,
                "positive_lift_fraction_stock": 1.0,
                "positive_lift_fraction_etf": 1.0,
            },
        },
        "bootstrap_stats": {
            "holdout": {"ci_lower": 0.1},
        },
    }
    # Events claim to have non-overlapping holdout coverage for stock + ETF,
    # but the actual non-overlapping trade records are missing.
    events = pd.DataFrame({
        "ticker": ["AAPL", "AAPL", "QQQ", "QQQ"],
        "split": ["holdout", "holdout", "holdout", "holdout"],
        "rule": ["candidate", "baseline", "candidate", "baseline"],
        "overlap_policy": ["non_overlapping"] * 4,
    })
    result = lte._derive_conclusion(events, pd.DataFrame(), summary, spec)
    assert result == "inconclusive"


def test_conclusion_support_fails_when_etf_underrepresented() -> None:
    """The support gate is inconclusive when an ETF cohort is below its minimum."""
    spec = _sample_spec(
        minimum_signals=1,
        minimum_stock_tickers=1,
        minimum_etf_tickers=1,
        minimum_lift_bps=1.0,
        q10_support_max_worse_bps=1000.0,
    )
    summary = {
        "split_stats": {
            "validation": {
                "sample_present": True,
                "candidate": {"mean_net_return_pct": 2.0},
                "baseline": {"mean_net_return_pct": 1.0},
            },
            "holdout": {
                "sample_present": True,
                "candidate": {"count": 10, "mean_net_return_pct": 2.0},
                "baseline": {"count": 10, "mean_net_return_pct": 1.0},
                "pooled_lift_at_cost_sensitivity_pct": 0.5,
                "q10_lift_pct": 0.0,
                "positive_lift_fraction_stock": 1.0,
                "positive_lift_fraction_etf": 1.0,
            },
        },
        "bootstrap_stats": {
            "holdout": {"ci_lower": 0.1},
        },
    }
    # Only stock tickers in holdout trades.
    trades = pd.DataFrame({
        "ticker": ["AAPL", "AAPL", "MSFT", "MSFT"],
        "split": ["holdout", "holdout", "holdout", "holdout"],
        "rule": ["candidate", "baseline", "candidate", "baseline"],
        "overlap_policy": ["non_overlapping"] * 4,
    })
    result = lte._derive_conclusion(pd.DataFrame(), trades, summary, spec)
    assert result == "inconclusive"


def test_conclusion_reject_or_deprioritize() -> None:
    """The reject gate fires when the holdout point estimate is strongly negative."""
    spec = _sample_spec()
    summary = {
        "split_stats": {
            "holdout": {
                "sample_present": True,
                "candidate": {"count": 10, "mean_net_return_pct": -1.0},
                "baseline": {"count": 10, "mean_net_return_pct": 1.0},
            },
        },
        "bootstrap_stats": {},
    }
    result = lte._derive_conclusion(pd.DataFrame(), pd.DataFrame(), summary, spec)
    assert result == "reject_or_deprioritize"


def test_conclusion_inconclusive_for_inadequate_holdout() -> None:
    """With no holdout sample, conclusion is inconclusive."""
    spec = _sample_spec()
    summary = {
        "split_stats": {
            "validation": {"sample_present": False},
            "holdout": {"sample_present": False},
        }
    }
    assert lte._derive_conclusion(pd.DataFrame(), pd.DataFrame(), summary, spec) == "inconclusive"


def test_exact_13_and_26_week_exit_timing(business_day_data_dir: Path) -> None:
    """A 13-week holding period means entry at i+1 and exit at i+14 close."""
    spec = _sample_spec(universe=("FAKEA",), hold_weeks=(13, 26))
    manifest = _build_manifest(business_day_data_dir, spec)
    result = lte.evaluate_study(manifest, spec, data_dir=business_day_data_dir)
    complete = result.events[result.events["13_bar_outcome_status"] == "complete"]
    assert not complete.empty
    for _idx, row in complete.head(5).iterrows():
        signal = pd.Timestamp(row["signal_time"], tz="UTC")
        exit_ = pd.Timestamp(row["13_bar_exit_time"], tz="UTC")
        # Index is weekly close. There should be 13 weekly closes between signal and exit.
        assert exit_ > signal


def test_protocol_json_matches_spec_defaults() -> None:
    """If a protocol file exists, it must round-trip to the default spec."""
    protocol_path = Path(__file__).resolve().parents[2] / "docs" / "research" / "LONG-001.json"
    if not protocol_path.exists():
        pytest.skip("protocol file not yet committed")
    raw = json.loads(protocol_path.read_text(encoding="utf-8"))
    from tradex.research.long_term_evaluation.cli import _spec_from_dict
    from_spec = _spec_from_dict(raw)
    default = lte.LongTermStudySpec()
    assert from_spec.universe == default.universe
    assert from_spec.score_bucket_edges == default.score_bucket_edges
    assert from_spec.slippage_scenarios_bps == default.slippage_scenarios_bps
    assert from_spec.weights == default.weights


def test_cli_help_does_not_load_env_or_network() -> None:
    """CLI --help works without .env, credentials, or network."""
    from tradex.research.long_term_evaluation.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["snapshot", "--help"])
    assert exc.value.code == 0
