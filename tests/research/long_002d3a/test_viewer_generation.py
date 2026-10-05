"""Static HTML review interface generation tests for LONG-002D3A."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tradex.research.long_002d3a.viewer import generate_static_html_viewer


@pytest.fixture
def sample_blinded_case() -> dict[str, Any]:
    bars = [
        {
            "relative_index": -1,
            "relative_label": "T-1",
            "normalized_open": 100.0,
            "normalized_high": 102.0,
            "normalized_low": 99.0,
            "normalized_close": 101.0,
            "relative_volume": 1.0,
            "normalized_sma20": 100.0,
            "normalized_sma50": 98.0,
            "atr_pct_14": 2.0,
        },
        {
            "relative_index": 0,
            "relative_label": "T0",
            "normalized_open": 101.0,
            "normalized_high": 103.0,
            "normalized_low": 100.5,
            "normalized_close": 102.5,
            "relative_volume": 1.5,
            "normalized_sma20": 100.2,
            "normalized_sma50": 98.2,
            "atr_pct_14": 2.1,
        },
    ]

    return {
        "case_id": "D3A-PILOT-001",
        "stage_a": {
            "case_id": "D3A-PILOT-001",
            "relative_bars": bars,
            "technical_metrics": {
                "pre_decision_normalized_close_t0": 102.5,
                "return_5_bars_pct": 2.5,
                "relative_volume_t0": 1.5,
            },
            "spy_context": {
                "spy_return_20_bars_pct": 1.0,
                "stock_minus_spy_20_bars_pct": 1.5,
                "benchmark": "SPY",
            },
            "data_quality_warnings": [],
        },
        "stage_b": {
            "case_id": "D3A-PILOT-001",
            "pit_context": {
                "security_type": "U.S. Common Stock (Operating Company)",
                "market_cap_cohort": "$20B - $200B (Large Cap)",
                "trading_history_cohort": "established (252+ sessions history)",
                "pit_earnings_schedule_status": "unknown",
            },
            "data_confidence_status": "verified_local_pit_artifacts_only",
        },
    }


def test_generate_static_html_viewer(tmp_path: Path, sample_blinded_case: dict[str, Any]) -> None:
    html_path = tmp_path / "pilot_blinded" / "index.html"
    result_path = generate_static_html_viewer([sample_blinded_case], html_path)

    assert result_path.exists()
    content = result_path.read_text(encoding="utf-8")

    # Verify key HTML elements
    assert "<!DOCTYPE html>" in content
    assert "TradeX Blinded Review Pilot" in content
    assert "D3A-PILOT-001" in content
    assert "Stage A: Technical" in content
    assert "Stage B: Qualified Point-in-Time Context" in content
    assert "localStorage" in content
    assert "<svg" in content or "renderChart" in content


def test_viewer_html_contains_no_sensitive_fields(
    tmp_path: Path, sample_blinded_case: dict[str, Any]
) -> None:
    html_path = tmp_path / "test_index.html"
    generate_static_html_viewer([sample_blinded_case], html_path)
    content = html_path.read_text(encoding="utf-8")

    # Prohibited patterns
    assert "clean_target_reached" not in content
    assert "positive_master_episode" not in content
    assert "adverse_trap" not in content
    assert "near_miss" not in content
    assert "ordinary_non_mover" not in content
    assert "mfe_pct" not in content
    assert "mae_pct" not in content
