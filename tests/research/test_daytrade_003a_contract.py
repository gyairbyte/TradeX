"""Deterministic contract tests for DAYTRADE-003A multi-resolution re-anchor artifacts."""
from __future__ import annotations

import json
from pathlib import Path

from tradex.research.daytrade_mvp import Resolution
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


def test_stable_gap_ids_present_and_documented() -> None:
    """All required stable gap IDs must be present in the gap matrix."""
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
        assert gaps[gid]["status"] in ("NOT_SUPPORTED", "PARTIALLY_SUPPORTED", "UNRESOLVED_REQUIRES_GARY")


def test_unresolved_items_remain_explicitly_unresolved() -> None:
    """Policy decisions and Gary strategy inputs must not be silently filled."""
    with GAP_MATRIX_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    policies = data["policy_decisions_required"]
    assert len(policies) >= 5
    for p in policies:
        assert p["current_status"] == "UNRESOLVED_REQUIRES_LOCK"

    gary_inputs = data["strategy_inputs_requiring_gary_definition"]
    assert len(gary_inputs) >= 8


def test_production_strategy_registry_invariant() -> None:
    """Production strategy registry remains strictly empty."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()
    assert not has_production_strategy_capability("DAYTRADE-003A", "0.1.0", "journal_execution")
    assert not has_production_strategy_capability("DAYTRADE-003A", "0.1.0", "automatic_alerts")


def test_decision_document_covers_ten_canonical_questions() -> None:
    """The decision markdown document must exist and answer all ten required questions."""
    assert DECISION_DOC_PATH.exists(), f"Missing decision document: {DECISION_DOC_PATH}"
    content = DECISION_DOC_PATH.read_text(encoding="utf-8")

    assert "The Ten Required Canonical Answers" in content
    for q_idx in range(1, 11):
        assert f"### {q_idx}." in content
