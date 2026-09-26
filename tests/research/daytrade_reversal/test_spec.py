"""Specification loading and hash verification tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from tradex.research.daytrade_reversal.spec import (
    DAYTRADE_001B_SPEC_SHA256,
    LOCKED_UNIVERSE,
    DaytradeSpec,
    SpecError,
    load_and_verify_spec,
)
from tradex.watchlists.presets import DOW30


def test_spec_loads_and_verifies_hash(locked_spec) -> None:
    """Locked spec loads cleanly and matches exact expected SHA-256."""
    assert locked_spec.task_id == "DAYTRADE-001B"
    assert locked_spec.sha256 == DAYTRADE_001B_SPEC_SHA256
    assert locked_spec.universe == DOW30
    assert len(locked_spec.universe) == 30
    assert locked_spec.trailing_sessions == 20
    assert locked_spec.quantile == 0.001
    assert locked_spec.bootstrap_resamples == 2000
    assert locked_spec.bootstrap_seed == 20260925


def test_spec_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    """Tampered spec file fails closed with SpecError."""
    tampered_file = tmp_path / "tampered_spec.json"
    tampered_file.write_text('{"task_id": "DAYTRADE-001B", "tampered": true}', encoding="utf-8")

    with pytest.raises(SpecError, match="SHA-256 mismatch"):
        load_and_verify_spec(tampered_file)


def test_spec_missing_file_fails_closed(tmp_path: Path) -> None:
    """Non-existent spec file fails closed with SpecError."""
    non_existent = tmp_path / "missing.json"
    with pytest.raises(SpecError, match="not found"):
        load_and_verify_spec(non_existent)


def test_universe_matches_frozen_dow30(locked_spec) -> None:
    """Universe must exactly match the locked 30 symbols from presets.DOW30."""
    assert locked_spec.universe == LOCKED_UNIVERSE
    assert "AAPL" in locked_spec.universe
    assert "MSFT" in locked_spec.universe
    assert "NVDA" in locked_spec.universe


def test_split_dates_frozen(locked_spec) -> None:
    """All four split boundaries must match the locked DAYTRADE-001B specification."""
    assert locked_spec.warmup.start == "2024-12-02"
    assert locked_spec.warmup.end == "2025-01-01"
    assert locked_spec.development.start == "2025-01-02"
    assert locked_spec.development.end == "2025-06-30"
    assert locked_spec.validation.start == "2025-07-01"
    assert locked_spec.validation.end == "2025-09-30"
    assert locked_spec.holdout.start == "2025-10-01"
    assert locked_spec.holdout.end == "2025-12-31"

    # Test split helpers
    assert locked_spec.get_history_dates("development") == ("2024-12-02", "2025-01-01")
    assert locked_spec.get_history_dates("validation") == ("2025-01-02", "2025-06-30")
    assert locked_spec.get_history_dates("holdout") == ("2025-07-01", "2025-09-30")
    assert locked_spec.get_history_dates("warmup") is None

    with pytest.raises(ValueError, match="Unsupported split name"):
        locked_spec.get_split_dates("invalid_split")


def test_all_required_metrics_contract(tmp_path: Path, locked_spec: DaytradeSpec) -> None:
    """Contract test: StudyResult.metrics and generated metrics.json must contain all 31 locked required metrics."""
    import json
    import math

    from tradex.research.daytrade_reversal.artifacts import write_artifact_bundle
    from tradex.research.daytrade_reversal.study import evaluate_split

    spec_path = Path(__file__).resolve().parents[3] / "docs" / "research" / "specs" / "DAYTRADE-001B-v1.json"
    assert spec_path.is_file(), f"Spec file not found at {spec_path}"
    raw_spec = json.loads(spec_path.read_text(encoding="utf-8"))
    required_metrics = raw_spec.get("required_metrics", [])
    assert len(required_metrics) == 31, f"Expected 31 required metrics, found {len(required_metrics)}"

    # 1. Evaluate split with empty sessions (baseline/edge-case)
    result = evaluate_split("validation", sessions=[], spec=locked_spec)

    # Assert no missing locked required metrics
    missing_metrics = [m for m in required_metrics if m not in result.metrics]
    assert not missing_metrics, f"Missing locked required metrics in StudyResult: {missing_metrics}"

    # Assert all values are strictly JSON-safe (no NaN or Inf)
    for k, v in result.metrics.items():
        if isinstance(v, float):
            assert not math.isnan(v), f"Metric '{k}' contains NaN"
            assert not math.isinf(v), f"Metric '{k}' contains Infinity"

    # Serializing with allow_nan=False must succeed
    json_bytes = json.dumps(result.metrics, allow_nan=False)
    assert json_bytes is not None

    # Uncomputable metrics with empty sessions must be None or explicit status
    assert result.metrics["event_count"] == 0
    assert result.metrics["represented_ticker_count"] == 0
    assert result.metrics["eligible_minute_count"] == 0
    assert result.metrics["mean_gross_forward_return_1m"] is None
    assert result.metrics["median_gross_forward_return_1m"] is None
    assert result.metrics["mean_net_forward_return_2bps"] is None
    assert result.metrics["median_net_forward_return_2bps"] is None
    assert result.metrics["provider_provenance_summary"] == {"status": "unavailable", "reason": "no_manifest_provided"}

    # 2. Verify metrics.json artifact contains exact same keys
    out_dir = tmp_path / "metrics_artifacts"
    write_artifact_bundle(output_dir=out_dir, result=result, spec=locked_spec)
    metrics_file = out_dir / "metrics.json"
    assert metrics_file.is_file()
    saved_metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
    missing_saved = [m for m in required_metrics if m not in saved_metrics]
    assert not missing_saved, f"Missing locked required metrics in saved metrics.json: {missing_saved}"
