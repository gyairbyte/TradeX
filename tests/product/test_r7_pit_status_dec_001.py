"""Product contract tests for MVP-ARCH-001-R7-PIT-STATUS-DEC-001.

Verifies:
1. Decision packet decision.json exists, loads, and adheres to governance invariants:
   - task_id == "MVP-ARCH-001-R7-PIT-STATUS-DEC-001"
   - status == "pending_gary_decision"
   - source_commit == "93d2174fed72f325e4ea87199c2aac9045998cbb"
   - selected_status_policy is None
   - production_status_semantics_change_authorized is False
   - schema_migration_authorized is False
   - provider_study_authorized is False
   - active_universe_authorized is False
   - c2_implementation_authorized is False
   - scheduler_authorized is False
2. Decision packet records current Schema v7 / current all-known contract accurately:
   - schema_version == 7
   - capture_contract_version == 1
   - family_success_requires_all_known is True
   - slot_success_requires_both_families_succeeded is True
3. Decision markdown document exists and contains all 29 required sections.
4. Decision test does NOT enforce a particular recommendation, leaving Gary free
   to select among documented options.
5. APPROVED_PRODUCTION_STRATEGIES == ().
"""
from __future__ import annotations

import json
from pathlib import Path

from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / "docs" / "product" / "artifacts" / "r7-pit-status-dec-001"
DECISION_JSON = ARTIFACTS_DIR / "decision.json"
DECISION_MD = REPO_ROOT / "docs" / "product" / "R7-PIT-STATUS-DEC-001.md"


def test_decision_json_exists_and_loads() -> None:
    """Verify decision.json exists and is valid JSON."""
    assert ARTIFACTS_DIR.exists(), f"Artifacts directory missing: {ARTIFACTS_DIR}"
    assert DECISION_JSON.exists(), f"decision.json missing: {DECISION_JSON}"

    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    assert isinstance(packet, dict)


def test_decision_json_governance_invariants() -> None:
    """Verify decision packet enforces pending status, null selection, and zero authorizations."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    assert packet["task_id"] == "MVP-ARCH-001-R7-PIT-STATUS-DEC-001"
    assert packet["status"] == "pending_gary_decision"
    assert packet["source_commit"] == "93d2174fed72f325e4ea87199c2aac9045998cbb"

    # Selection policy must remain null until Gary decides
    assert packet["selected_status_policy"] is None

    # Strict authorization booleans must all be False
    assert packet["production_status_semantics_change_authorized"] is False
    assert packet["schema_migration_authorized"] is False
    assert packet["provider_study_authorized"] is False
    assert packet["active_universe_authorized"] is False
    assert packet["c2_implementation_authorized"] is False
    assert packet["scheduler_authorized"] is False


def test_decision_json_records_current_contracts() -> None:
    """Verify decision packet accurately records current Schema v7 and all-known semantics."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    current = packet["current_contract"]
    assert current["schema_version"] == 7
    assert current["capture_contract_version"] == 1
    assert current["family_success_requires_all_known"] is True
    assert current["slot_success_requires_both_families_succeeded"] is True

    # Provenance finding accurately recorded
    assert "provenance_limitation_finding" in packet
    finding = packet["provenance_limitation_finding"]
    assert "cannot reliably distinguish" in finding
    assert "swallowed" in finding


def test_decision_packet_evaluates_options_without_forcing_selection() -> None:
    """Verify all 5 options are present and Gary remains free to select any policy."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    opts = packet["evaluated_options"]
    assert "option_1" in opts
    assert "option_2" in opts
    assert "option_3" in opts
    assert "option_4" in opts
    assert "option_5" in opts

    # Test does not mandate that selected_status_policy match recommended_direction
    assert packet["selected_status_policy"] is None


def test_decision_markdown_exists_and_contains_all_required_sections() -> None:
    """Verify R7-PIT-STATUS-DEC-001.md exists and contains all 29 required sections."""
    assert DECISION_MD.exists(), f"Decision markdown missing: {DECISION_MD}"
    content = DECISION_MD.read_text(encoding="utf-8")

    required_sections = [
        "1. Executive Summary",
        "2. Decision Question",
        "3. Current Repository Behavior",
        "4. Why READINESS-A Exposed the Issue",
        "5. Observation-State Inventory",
        "6. Earnings-Path Inventory",
        "7. Reference-Path Inventory",
        "8. Current Provenance Limitations",
        "9. Operational Health vs. Evidence Completeness",
        "10. Applicability Analysis",
        "11. Option 1 — Retain Strict All-Known Semantics",
        "12. Option 2 — Separate Operational Health From Evidence Completeness",
        "13. Option 3 — Applicability-Aware Semantics",
        "14. Option 4 — Threshold-Based Family Success",
        "15. Option 5 — Require Empirical Provider Study Before Semantics Change",
        "16. Comparative Decision Matrix",
        "17. Recommended Design Direction",
        "18. What Evidence Supports the Recommendation",
        "19. What Remains Uncertain",
        "20. Schema-v7 / Historical Compatibility",
        "21. Future Status and Reason Taxonomy",
        "22. Health and Alert Semantics",
        "23. CLI and Exit-Code Implications",
        "24. Candidate B and Candidate C Implications",
        "25. Implementation Boundary and Sequencing",
        "26. Empirical-Study Specification",
        "27. Risks and Failure Modes",
        "28. Gary Decision Required",
        "29. Non-Authorization Statement",
    ]

    import re

    def _normalize(s: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", " ", s).strip().lower()

    normalized_content = _normalize(content)
    for section in required_sections:
        normalized_section = _normalize(section)
        assert normalized_section in normalized_content, f"Missing section: {section}"

    # Critical text validations
    assert "selected_status_policy = null" in content or "selected_status_policy` remains `null" in content
    assert "Schema v7 cannot reliably distinguish" in content


def test_approved_production_strategies_remains_empty() -> None:
    """Registry invariant: APPROVED_PRODUCTION_STRATEGIES is strictly empty."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()
