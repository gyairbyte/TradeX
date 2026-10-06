"""Deterministic contract tests for DAYTRADE-003A multi-resolution re-anchor artifacts."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tradex.research.daytrade_mvp import CompletedBar, Resolution
from tradex.strategies.registry import (
    APPROVED_PRODUCTION_STRATEGIES,
    has_production_strategy_capability,
)

GAP_MATRIX_PATH = Path("docs/research/artifacts/DAYTRADE-003A/original_thesis_gap_matrix.json")
DECISION_DOC_PATH = Path("docs/research/DAYTRADE-003A-ORIGINAL-THESIS-REANCHOR.md")


def test_gap_matrix_json_parses_and_has_valid_identity() -> None:
    """Gap matrix JSON parses cleanly and contains verified task identity."""
    assert GAP_MATRIX_PATH.exists(), f"Missing required artifact: {GAP_MATRIX_PATH}"
    with GAP_MATRIX_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["task_id"] == "DAYTRADE-003A-ORIGINAL-THESIS-REANCHOR-001"
    assert data["classification"] == "research_design_only"
    assert data["governance"]["selected_path"] == "PATH_B_MULTI_RESOLUTION_REANCHOR"
    assert data["governance"]["base_commit"] == "58df7d468d7175264758a997a7a9c701c7f8d369"


def test_governance_invariants_strictly_fail_closed() -> None:
    """Governance safety flags must all be False."""
    with GAP_MATRIX_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["production_change_authorized"] is False
    assert data["real_data_access_authorized"] is False
    assert data["provider_calls_authorized"] is False
    assert data["holdout_access_authorized"] is False
    assert data["governance"]["approved_production_strategies_empty"] is True


def test_original_four_layer_hierarchy_preserved() -> None:
    """Original hierarchy: Daily -> 133-tick -> 1-minute -> 50-tick -> execution."""
    with GAP_MATRIX_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    thesis = data["original_thesis"]
    assert len(thesis) == 5

    resolutions = [item["resolution"] for item in thesis]
    assert resolutions == ["daily", "133_tick", "1_minute", "50_tick", "execution_lifecycle"]

    # Verify matching Resolution enum values in daytrade_mvp
    assert Resolution.DAILY.value == "daily"
    assert Resolution.TICK_133.value == "133_tick"
    assert Resolution.MINUTE_1.value == "1_minute"
    assert Resolution.TICK_50.value == "50_tick"


def test_stable_gap_ids_and_provider_distinction() -> None:
    """All required stable gap IDs present; repository vs external provider capability distinguished."""
    with GAP_MATRIX_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    gaps = {item["gap_id"]: item for item in data["major_gaps"]}
    expected_ids = [
        "DT3-GAP-DATA-001",
        "DT3-GAP-TICK-001",
        "DT3-GAP-SYNC-001",
        "DT3-GAP-SETUP-001",
        "DT3-GAP-EVAL-001",
    ]
    for gid in expected_ids:
        assert gid in gaps, f"Missing required stable gap ID: {gid}"
        assert gaps[gid]["repository_status"] in (
            "NOT_SUPPORTED",
            "PARTIALLY_SUPPORTED",
            "UNRESOLVED_REQUIRES_GARY",
        )

    # DT3-GAP-DATA-001 external status must be UNKNOWN, not falsely claimed as NOT_SUPPORTED externally
    assert (
        gaps["DT3-GAP-DATA-001"]["external_provider_status"]
        == "UNKNOWN_REQUIRES_DAYTRADE_003B_VERIFICATION"
    )
    assert gaps["DT3-GAP-DATA-001"]["repository_status"] == "NOT_SUPPORTED"


def test_unresolved_items_remain_explicitly_unresolved() -> None:
    """Policy decisions and Gary strategy inputs must not be silently filled."""
    with GAP_MATRIX_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    policies = data["policy_decisions_required"]
    assert len(policies) >= 6
    for p in policies:
        assert p["current_status"] == "UNRESOLVED_REQUIRES_LOCK"

    gary_inputs = data["strategy_inputs_requiring_gary_definition"]
    assert len(gary_inputs) >= 8
    # Assert that strategy inputs remain questions rather than locked rules
    for inp in gary_inputs:
        assert "questions" in inp
        assert "unresolved" in inp["questions"].lower()


def test_no_invented_gary_strategy_thresholds() -> None:
    """Gap matrix must not encode invented Gary strategy requirements (ADV, ATR thresholds)."""
    with GAP_MATRIX_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Verify no approved strategy thresholds are asserted in governance or original thesis
    raw_text = json.dumps(data)
    assert "ADV >" not in raw_text
    assert "ADV > $10M" not in raw_text
    assert "ATR > $1.50" not in raw_text
    assert "blended holdout" not in raw_text.lower()


def test_actual_repository_file_inventory() -> None:
    """Verify that actual daytrade_mvp files exist and nonexistent files are not claimed."""
    mvp_dir = Path("tradex/research/daytrade_mvp")
    assert (mvp_dir / "models.py").exists()
    assert (mvp_dir / "setup.py").exists()
    assert (mvp_dir / "evaluator.py").exists()
    assert (mvp_dir / "synthetic.py").exists()

    # Nonexistent files must NOT exist
    assert not (mvp_dir / "series.py").exists()
    assert not (mvp_dir / "study.py").exists()


def test_completed_bar_capability_validation_truth() -> None:
    """CompletedBar enforces high >= low and volume >= 0, but does not reject zero prices."""
    now = datetime(2026, 10, 6, 14, 0, tzinfo=UTC)
    # Valid bar with zero prices is allowed under current code (models.py does not enforce O,H,L,C > 0)
    bar = CompletedBar(
        timestamp=now,
        open=0.0,
        high=0.0,
        low=0.0,
        close=0.0,
        volume=100.0,
        resolution=Resolution.TICK_50,
    )
    assert bar.open == 0.0

    # Inverted high/low is strictly rejected
    with pytest.raises(ValueError, match="cannot be less than low"):
        CompletedBar(
            timestamp=now,
            open=10.0,
            high=9.0,
            low=10.0,
            close=10.0,
            volume=100.0,
            resolution=Resolution.TICK_50,
        )

    # Negative volume is strictly rejected
    with pytest.raises(ValueError, match="cannot be negative"):
        CompletedBar(
            timestamp=now,
            open=10.0,
            high=10.0,
            low=10.0,
            close=10.0,
            volume=-1.0,
            resolution=Resolution.TICK_50,
        )


def test_roadmap_status_truthful() -> None:
    """DAYTRADE-003A status in roadmap is completed_pending_review."""
    with GAP_MATRIX_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    roadmap = {item["phase"]: item for item in data["recommended_sequence"]}
    assert roadmap["DAYTRADE-003A"]["status"] == "completed_pending_review"
    assert "blended" not in roadmap["DAYTRADE-003H"]["title"].lower()


def test_production_strategy_registry_invariant() -> None:
    """Production strategy registry remains strictly empty."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()
    assert not has_production_strategy_capability("DAYTRADE-003A", "0.1.0", "journal_execution")
    assert not has_production_strategy_capability("DAYTRADE-003A", "0.1.0", "automatic_alerts")


def test_decision_document_covers_ten_canonical_questions_and_no_blended_holdout() -> None:
    """The decision markdown document must exist, answer all 10 questions, and avoid blended holdout."""
    assert DECISION_DOC_PATH.exists(), f"Missing decision document: {DECISION_DOC_PATH}"
    content = DECISION_DOC_PATH.read_text(encoding="utf-8")

    assert "The Ten Required Canonical Answers" in content
    for q_idx in range(1, 11):
        assert f"### {q_idx}." in content

    # Enforce absence of prohibited phrases
    assert "blended holdout" not in content.lower()
    assert "ADV > $10M" not in content
