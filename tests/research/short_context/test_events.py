"""Tests for context event generation."""
from __future__ import annotations

from tradex.research.score_validation.models import ScoreValidationConfig
from tradex.research.short_context.events import build_event_dataframe, generate_context_events


def test_generate_events_columns(synthetic_manifest) -> None:
    config = ScoreValidationConfig(
        warmup_bars=60,
        horizons=(1, 3, 5),
        slippage_scenarios_bps=(0.0, 5.0, 10.0),
    )
    spec = synthetic_manifest["spec"]
    events, _quality = generate_context_events(synthetic_manifest["manifest_path"], spec, config)
    df = build_event_dataframe(events, spec)
    assert "market_rs_eligible" in df.columns
    assert "market_sector_rs_eligible" in df.columns
    assert "3_bar_outcome_status" in df.columns
    assert not df.empty


def test_holdout_events_not_leaked_into_development(synthetic_manifest) -> None:
    config = ScoreValidationConfig(
        warmup_bars=60,
        horizons=(1, 3, 5),
        slippage_scenarios_bps=(0.0, 5.0, 10.0),
    )
    spec = synthetic_manifest["spec"]
    events, _ = generate_context_events(synthetic_manifest["manifest_path"], spec, config)
    df = build_event_dataframe(events, spec)
    dev_dates = df.loc[df["split"] == "development", "signal_time"]
    holdout_dates = df.loc[df["split"] == "holdout", "signal_time"]
    assert not dev_dates.empty and not holdout_dates.empty
    assert dev_dates.max() < holdout_dates.min()


def test_data_quality_preserves_manifest_source_and_checksum(synthetic_manifest) -> None:
    config = ScoreValidationConfig(
        warmup_bars=60,
        horizons=(1, 3, 5),
        slippage_scenarios_bps=(0.0, 5.0, 10.0),
    )
    spec = synthetic_manifest["spec"]
    _events, quality_rows = generate_context_events(synthetic_manifest["manifest_path"], spec, config)
    assert len(quality_rows) == len(spec.target_tickers)
    quality = quality_rows[0].to_dict()
    assert quality["data_source"] == "synthetic"
    assert quality["sha256"]
    assert quality["manifest_rows"] > 0
    assert quality["validated_rows"] > 0
    assert quality["sha256"] != ""
