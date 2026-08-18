"""Deterministic invariants for MVP-ARCH-001 decision packet."""
from __future__ import annotations

from pathlib import Path

import pytest

from tradex.product.mvp_arch_001 import (
    _DASHBOARD_DISPOSITIONS,
    _EVIDENCE_STATES,
    _PROVIDER_LIFECYCLES,
    build_inventory,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MD_PATH = REPO_ROOT / "docs" / "product" / "MVP-ARCH-001.md"
JSON_PATH = REPO_ROOT / "docs" / "product" / "MVP-ARCH-001.json"


@pytest.fixture
def inv() -> dict:
    return build_inventory()


def test_artifact_files_exist() -> None:
    assert MD_PATH.exists(), f"Missing {MD_PATH}"
    assert JSON_PATH.exists(), f"Missing {JSON_PATH}"
    assert "MVP-ARCH-001" in MD_PATH.read_text(encoding="utf-8")
    assert '"artifact_id": "MVP-ARCH-001"' in JSON_PATH.read_text(encoding="utf-8")


def test_classification_and_status(inv: dict) -> None:
    assert inv["classification"] == "product-architecture-and-governance-design-only"
    assert inv["decision_status"] == "pending_gary_decision"


def test_no_authorized_actions(inv: dict) -> None:
    auth = inv["authorization"]
    assert auth["production_behavior_changes_authorized"] is False
    assert auth["provider_calls_authorized"] is False
    assert auth["dashboard_changes_authorized"] is False
    assert auth["provider_removal_authorized"] is False
    assert auth["alert_changes_authorized"] is False
    assert auth["database_migration_authorized"] is False
    assert auth["strategy_promotion_authorized"] is False
    assert auth["long_002c_work_authorized"] is False
    assert auth["pr_merge_authorized_without_gary_decision"] is False


def test_prerequisite_is_pr52_merge(inv: dict) -> None:
    assert inv["prerequisite_commit"] == "52cff71fd73105c7a2a01bc6f9ccc19c3ae204a2"


def test_required_providers_included(inv: dict) -> None:
    names = {p["name"] for p in inv["provider_inventory"]}
    required = {
        "yahoo",
        "schwab",
        "alpaca",
        "ibkr",
        "massive_polygon",
        "sec_edgar",
        "unusual_whales",
        "tradier",
        "wikipedia",
    }
    missing = required - names
    assert not missing, f"Missing providers: {missing}"


def test_provider_lifecycle_values_are_allowed(inv: dict) -> None:
    for p in inv["provider_inventory"]:
        assert p["recommended_lifecycle"] in _PROVIDER_LIFECYCLES, p["name"]


def test_required_dashboard_tabs_included(inv: dict) -> None:
    tabs = {d["tab"] for d in inv["dashboard_inventory"]}
    required = {
        "Scanner",
        "Coil Detector",
        "Confluence",
        "Pattern Similarity",
        "Pre-Market",
        "Options Activity",
        "Alerts",
        "Signal Journal",
        "Weights",
        "Help",
    }
    missing = required - tabs
    assert not missing, f"Missing tabs: {missing}"


def test_dashboard_disposition_values_are_allowed(inv: dict) -> None:
    for d in inv["dashboard_inventory"]:
        assert d["recommended_disposition"] in _DASHBOARD_DISPOSITIONS, d["tab"]


def test_required_strategy_components_included(inv: dict) -> None:
    names = {s["component"] for s in inv["strategy_evidence_inventory"]}
    required = {
        "Production intraday scorer",
        "Production short-term scorer",
        "Production long-term scorer",
        "Coil detector",
        "Confluence",
        "Premarket gaps",
        "Options activity",
        "Pattern similarity / PATTERN-001",
        "SHORT-001",
        "LONG-001",
        "INTRA-001",
        "LONG-002",
    }
    missing = required - names
    assert not missing, f"Missing components: {missing}"


def test_evidence_state_values_are_allowed(inv: dict) -> None:
    for s in inv["strategy_evidence_inventory"]:
        assert s["evidence_state"] in _EVIDENCE_STATES, s["component"]


def test_no_strategy_is_production_approved(inv: dict) -> None:
    for s in inv["strategy_evidence_inventory"]:
        assert s["evidence_state"] != "production_approved", s["component"]


def test_actionability_separation(inv: dict) -> None:
    for s in inv["strategy_evidence_inventory"]:
        if s["evidence_state"] in {"rejected", "not_supported", "inconclusive", "research_only", "exploratory", "legacy_heuristic"}:
            assert s["may_use_actionable_labels"] is False, s["component"]
            assert s["may_generate_automatic_alerts"] is False, s["component"]


def test_signal_journal_is_legacy_telemetry(inv: dict) -> None:
    journal = next(d for d in inv["dashboard_inventory"] if d["tab"] == "Signal Journal")
    assert journal["classification"] == "legacy_signal_telemetry"
    assert inv["journal_outcome_contract"]["current_state"] == "legacy_signal_telemetry"


def test_candidate_contract_separates_concepts(inv: dict) -> None:
    fields = inv["candidate_contract"]["fields"]
    assert "setup_quality_score" in fields
    assert "move_potential" in fields
    assert "entry_readiness" in fields
    assert "downside_risk" in fields
    assert "data_confidence" in fields
    assert "evidence_state" in fields


def test_score_not_actionability_or_probability(inv: dict) -> None:
    rules = inv["candidate_contract"]["rules"]
    assert any("0-100" in r and "probability" in r for r in rules)
    assert any("not" in r and "actionability" in r for r in rules)


def test_long_002c_is_paused_and_dataset_unauthorized(inv: dict) -> None:
    long002 = next(s for s in inv["strategy_evidence_inventory"] if s["component"] == "LONG-002")
    assert "paused" in long002["notes"].lower()
    assert long002["may_generate_automatic_alerts"] is False


def test_long_002c_dataset_and_production_promotion_unauthorized(inv: dict) -> None:
    auth = inv["authorization"]
    assert auth["long_002c_work_authorized"] is False
    assert auth["strategy_promotion_authorized"] is False


def test_dashboard_dispositions_no_unauthorized_removal(inv: dict) -> None:
    for d in inv["dashboard_inventory"]:
        assert d["recommended_disposition"] in _DASHBOARD_DISPOSITIONS
        if d["tab"] in {"Pattern Similarity", "Options Activity", "Weights"}:
            assert d["recommended_disposition"] == "archive", d["tab"]


def test_provider_deletion_not_authorized(inv: dict) -> None:
    auth = inv["authorization"]
    assert auth["provider_removal_authorized"] is False
    assert auth["dashboard_changes_authorized"] is False


def test_alert_changes_not_authorized(inv: dict) -> None:
    assert inv["authorization"]["alert_changes_authorized"] is False


def test_rollout_plan_is_ordered(inv: dict) -> None:
    orders = [s["order"] for s in inv["rollout_plan"]]
    assert orders == sorted(orders)
    assert len(orders) == 8


def test_governance_invariants_present(inv: dict) -> None:
    invariants = inv["governance_invariants"]
    assert any("LONG-002C" in g and "paused" in g for g in invariants)
    assert any("provider call" in g.lower() for g in invariants)
    assert any("production_approved" in g for g in invariants)


def test_target_navigation_has_five_areas(inv: dict) -> None:
    areas = [a["area"] for a in inv["target_navigation"]]
    assert areas == ["Today", "Candidate Detail", "Journal", "Research Lab", "Settings"]
