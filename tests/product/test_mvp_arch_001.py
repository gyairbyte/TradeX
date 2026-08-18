"""Deterministic invariants for the committed MVP-ARCH-001 artifact."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = REPO_ROOT / "docs" / "product" / "MVP-ARCH-001.json"
MD_PATH = REPO_ROOT / "docs" / "product" / "MVP-ARCH-001.md"

_ALLOWED_LIFECYCLES = {
    "operational_primary",
    "operational_fallback",
    "specialized_reference",
    "research_only",
    "experimental",
    "archived",
}

_ALLOWED_DISPOSITIONS = {
    "keep_primary",
    "keep_but_relabel",
    "merge_into_workflow",
    "move_to_research_lab",
    "replace",
    "archive",
}

_ALLOWED_EVIDENCE_STATES = {
    "legacy_heuristic",
    "exploratory",
    "research_only",
    "not_supported",
    "rejected",
    "inconclusive",
    "shadow",
    "production_approved",
    "archived",
}

_TARGET_AREAS = {"Today", "Candidate Detail", "Journal", "Research Lab", "Settings"}


@pytest.fixture
def inv() -> dict:
    assert JSON_PATH.exists(), f"Missing {JSON_PATH}"
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def test_artifact_files_exist() -> None:
    assert JSON_PATH.exists()
    assert MD_PATH.exists()
    text = MD_PATH.read_text(encoding="utf-8")
    assert "MVP-ARCH-001" in text
    assert "pending_gary_decision" in text


def test_classification_and_status(inv: dict) -> None:
    assert inv["classification"] == "product-architecture-and-governance-design-only"
    assert inv["decision_status"] == "pending_gary_decision"
    assert inv["mvp_arch_001_status"]["separate_workstream_from_long_002"] is True
    assert inv["mvp_arch_001_status"]["does_not_authorize_long_002c"] is True


def test_mvp_authorization_does_not_authorize_anything(inv: dict) -> None:
    auth = inv["authorization"]
    for key, value in auth.items():
        if key != "pr_merge_authorized_without_gary_decision":
            assert value is False, key
    assert "long_002c_work_authorized" not in auth


def test_long_002_status_is_precise(inv: dict) -> None:
    ls = inv["long_002_status"]
    assert ls["long_002b_amend_002_completed"] is True
    assert ls["long_002c_design_authorized_by_pr52"] is True
    assert ls["long_002c_currently_paused_by_gary"] is True
    assert ls["long_002c_dataset_construction_authorized"] is False
    assert ls["long_002c_work_authorized_by_mvp_arch_001"] is False


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
    assert not required - names, f"Missing providers: {required - names}"


def test_provider_runtime_accessible_is_distinguished(inv: dict) -> None:
    """Unusual Whales / Tradier are runtime-accessible but not used in production ranking/actionability."""
    for p in inv["provider_inventory"]:
        assert "runtime_accessible" in p, p["name"]
        assert "used_in_production_ranking_or_actionability" in p, p["name"]
        assert "production_runtime" not in p, p["name"]
    options_providers = [p for p in inv["provider_inventory"] if p["name"] in ("unusual_whales", "tradier")]
    for p in options_providers:
        assert p["runtime_accessible"] is True, p["name"]
        assert p["used_in_production_ranking_or_actionability"] is False, p["name"]


def test_provider_lifecycle_values_are_allowed(inv: dict) -> None:
    for p in inv["provider_inventory"]:
        assert p["recommended_lifecycle"] in _ALLOWED_LIFECYCLES, p["name"]


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
    assert not required - tabs, f"Missing tabs: {required - tabs}"


def test_dashboard_disposition_and_target_area_are_allowed(inv: dict) -> None:
    target_areas = set()
    for d in inv["dashboard_inventory"]:
        assert d["recommended_disposition"] in _ALLOWED_DISPOSITIONS, d["tab"]
        assert d["target_area"] in _TARGET_AREAS, d["tab"]
        target_areas.add(d["target_area"])
    assert target_areas == _TARGET_AREAS, f"Missing target areas: {_TARGET_AREAS - target_areas}"


def test_navigation_converges_to_five_areas(inv: dict) -> None:
    """Scanner -> Today; Confluence/Pre-Market/Help into workflow; Coil/Pattern/Options -> Research Lab; Alerts -> Settings; Journal -> Journal."""
    mapping = {d["tab"]: (d["recommended_disposition"], d["target_area"]) for d in inv["dashboard_inventory"]}
    assert mapping["Scanner"] == ("merge_into_workflow", "Today")
    assert mapping["Confluence"][0] == "merge_into_workflow"
    assert mapping["Confluence"][1] in {"Today", "Candidate Detail"}
    assert mapping["Pre-Market"][0] == "merge_into_workflow"
    assert mapping["Pre-Market"][1] in {"Today", "Candidate Detail"}
    assert mapping["Help"][0] == "merge_into_workflow"
    assert mapping["Help"][1] in {"Today", "Candidate Detail"}
    assert mapping["Coil Detector"] == ("move_to_research_lab", "Research Lab")
    assert mapping["Pattern Similarity"][0] in {"move_to_research_lab", "archive"}
    assert mapping["Pattern Similarity"][1] == "Research Lab"
    assert mapping["Options Activity"][0] in {"archive", "move_to_research_lab"}
    assert mapping["Options Activity"][1] == "Research Lab"
    assert mapping["Alerts"] == ("merge_into_workflow", "Settings")
    assert mapping["Signal Journal"] == ("replace", "Journal")
    assert mapping["Weights"][0] == "archive"


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
        assert s["evidence_state"] in _ALLOWED_EVIDENCE_STATES, s["component"]


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


def test_candidate_contract_includes_outcome_status(inv: dict) -> None:
    fields = inv["candidate_contract"]["fields"]
    assert "outcome_status" in fields


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


def test_long_002c_dataset_and_production_promotion_unauthorized(inv: dict) -> None:
    assert inv["long_002_status"]["long_002c_dataset_construction_authorized"] is False
    assert inv["authorization"]["strategy_promotion_authorized"] is False


def test_dashboard_dispositions_no_unauthorized_removal(inv: dict) -> None:
    auth = inv["authorization"]
    assert auth["provider_removal_authorized"] is False
    assert auth["dashboard_changes_authorized"] is False


def test_alert_changes_not_authorized(inv: dict) -> None:
    assert inv["authorization"]["alert_changes_authorized"] is False


def test_rollout_plan_is_ordered_and_rollback_is_safe(inv: dict) -> None:
    orders = [s["order"] for s in inv["rollout_plan"]]
    assert orders == sorted(orders)
    assert len(orders) == 8
    candidate_step = next(s for s in inv["rollout_plan"] if s["pr"] == "Candidate persistence contract")
    assert "drop" not in candidate_step["rollback"].lower()
    journal_step = next(s for s in inv["rollout_plan"] if s["pr"] == "Journal/outcome replacement")
    assert "new executable-strategy journal table remains empty" in journal_step["rollback"].lower()
    alert_step = next(s for s in inv["rollout_plan"] if s["pr"] == "Alert gating")
    assert "fail-closed" in alert_step["rollback"].lower()


def test_governance_invariants_present(inv: dict) -> None:
    invariants = inv["governance_invariants"]
    assert any("LONG-002B-AMEND-002" in g and "paused" in g for g in invariants)
    assert any("MVP-ARCH-001 is a separate" in g for g in invariants)
    assert any("production_approved" in g for g in invariants)


def test_target_navigation_has_five_areas(inv: dict) -> None:
    areas = [a["area"] for a in inv["target_navigation"]]
    assert areas == ["Today", "Candidate Detail", "Journal", "Research Lab", "Settings"]


def test_committed_json_is_authoritative_and_valid(inv: dict) -> None:
    """The JSON on disk parses and contains the required top-level decision keys."""
    assert inv["artifact_id"] == "MVP-ARCH-001"
    assert "provider_inventory" in inv
    assert "dashboard_inventory" in inv
    assert "strategy_evidence_inventory" in inv
    assert "candidate_contract" in inv
    assert "rollout_plan" in inv
