"""Aggregation and metric tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from tradex.research.score_validation.aggregate import (
    build_components,
    build_score_buckets,
    build_thresholds,
)
from tradex.research.score_validation.models import ScoreValidationConfig
from tradex.research.score_validation.report import run_study

from .conftest import write_bars_and_manifest


def _simple_config() -> ScoreValidationConfig:
    return ScoreValidationConfig(
        warmup_bars=50,
        horizons=(1,),
        slippage_scenarios_bps=(0.0,),
        score_bucket_edges=(0, 20, 40, 60, 80, 101),
        score_thresholds=(20, 30, 40, 50, 60, 70, 80),
        minimum_group_events=1,
    )


def _simple_events_df() -> pd.DataFrame:
    rows = []
    for score in [15, 25, 35, 45, 55, 65, 75, 85, 95, 100]:
        rows.append(
            {
                "ticker": "TEST",
                "split": "development",
                "score": float(score),
                "1_bar_outcome_status": "complete",
                "1_bar_net_return_pct_0bps": float(score) * 0.1 - 5.0,
                "component_ema_structure": score >= 50,
                "component_volume_confirmation": score >= 70,
                "component_rsi_momentum": score >= 30,
                "component_macd_positive": score >= 60,
                "component_pullback_ema": score >= 80,
            }
        )
    return pd.DataFrame(rows)


def test_score_100_belongs_to_final_bucket():
    config = _simple_config()
    df = _simple_events_df()
    buckets = build_score_buckets(df, config)
    assert not buckets.empty
    final = buckets[buckets["score_bucket"] == "80-100"]
    assert not final.empty


def test_score_bucket_boundaries():
    config = _simple_config()
    df = _simple_events_df()
    buckets = build_score_buckets(df, config)
    assert buckets["event_count"].sum() == 10


def test_current_threshold_label():
    config = _simple_config()
    df = _simple_events_df()
    thresh = build_thresholds(df, config)
    labels = thresh["threshold_label"].unique()
    assert "current_default" in labels
    current = thresh[thresh["threshold_label"] == "current_default"]
    assert (current["threshold"] == 40).all()


def test_threshold_exact_inclusion():
    config = _simple_config()
    df = _simple_events_df()
    thresh = build_thresholds(df, config)
    t40 = thresh[thresh["threshold"] == 40]
    total_retained = t40["event_count"].sum()
    # 7 events have score >= 40 (45, 55, 65, 75, 85, 95, 100).
    assert total_retained == 7


def test_component_present_absent_counts():
    config = _simple_config()
    df = _simple_events_df()
    comp = build_components(df, config)
    assert not comp.empty
    states = set(comp["component_state"].unique())
    assert states == {"present", "absent"}


def test_component_deltas_present():
    config = _simple_config()
    df = _simple_events_df()
    comp = build_components(df, config)
    ema = comp[(comp["component"] == "ema_structure") & (comp["component_state"] == "present")]
    assert not ema.empty
    assert "mean_return_present_minus_absent" in ema.columns


def test_empty_group_stable_schema():
    config = _simple_config()
    empty = pd.DataFrame(columns=["ticker", "split", "score"])
    buckets = build_score_buckets(empty, config)
    assert list(buckets.columns) == list(build_score_buckets(pd.DataFrame(), config).columns)
    assert buckets.empty


def test_sparse_group_marked(tmp_path: Path):
    config = ScoreValidationConfig(minimum_group_events=5, warmup_bars=50)
    manifest_path, _, _ = write_bars_and_manifest(tmp_path / "data")
    study = run_study(manifest_path, config)
    assert "sample_status" in study.score_buckets.columns
