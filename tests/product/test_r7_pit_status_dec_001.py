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
3. Three-way family aggregation contract (SUCCEEDED / PARTIAL / FAILED) is upheld
   and false generalization (known_n < requested_n -> PARTIAL) is rejected.
4. Candidate B and C status in decision.json is unresolved_pending_policy_and_prerequisites.
5. NOT_ANNOUNCED is explicitly conceptual / evidence-dependent and not inferred from Yahoo absence.
6. Empirical study does not claim raw Yahoo/yfinance HTTP status/body visibility as guaranteed.
7. Dedicated Rollout Step 7 PIT Operations Runner (MVP-ARCH-001-R7-PIT-001C1) entry is preserved in tracker.
8. Decision markdown document exists and contains all 29 required sections.
9. Decision test does NOT enforce a particular recommendation, leaving Gary free
   to select among documented options.
10. APPROVED_PRODUCTION_STRATEGIES == ().
"""
from __future__ import annotations

import json
from pathlib import Path

from tradex.pit.models import CaptureRunStatus
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


def test_family_aggregation_three_way_contract() -> None:
    """Verify three-way family aggregation contract and absence of false generalizations."""
    content = DECISION_MD.read_text(encoding="utf-8")

    # Three-way aggregation contract must be explicit in document
    assert r"\text{known\_n} == \text{requested\_n} & \implies \text{family SUCCEEDED}" in content
    assert r"0 < \text{known\_n} < \text{requested\_n} & \implies \text{family PARTIAL}" in content
    assert r"\text{known\_n} == 0 & \implies \text{family FAILED}" in content

    # False generalization that any known_n < requested_n implies PARTIAL must NOT appear
    assert r"any } \text{known\_n} < \text{requested\_n} \implies \text{family PARTIAL}" not in content
    assert "known_n < requested_n -> family PARTIAL" not in content

    # CaptureRunStatus enum defines distinct SUCCEEDED, PARTIAL, and FAILED states
    assert CaptureRunStatus.SUCCEEDED.value == "succeeded"
    assert CaptureRunStatus.PARTIAL.value == "partial"
    assert CaptureRunStatus.FAILED.value == "failed"


def test_candidate_b_and_c_machine_readable_status() -> None:
    """Verify Candidate B and C status in decision.json is unresolved_pending_policy_and_prerequisites."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    disposition = packet.get("candidate_compatibility_disposition", {})
    assert "candidate_b" in disposition, "candidate_b missing from candidate_compatibility_disposition"
    assert "candidate_c" in disposition, "candidate_c missing from candidate_compatibility_disposition"

    cand_b = disposition["candidate_b"]
    cand_c = disposition["candidate_c"]

    assert cand_b["status"] == "unresolved_pending_policy_and_prerequisites"
    assert cand_c["status"] == "unresolved_pending_policy_and_prerequisites"
    assert cand_b["symbol_count"] == 30
    assert cand_c["symbol_count"] == 45


def test_not_announced_is_explicitly_conceptual() -> None:
    """Verify NOT_ANNOUNCED is documented as conceptual and not derivable from Yahoo absence."""
    content = DECISION_MD.read_text(encoding="utf-8")

    assert "NOT_ANNOUNCED" in content
    assert "Conceptual / requires authoritative source; not derivable from current Schema v7 evidence" in content
    assert "This is not derivable from current Schema v7 evidence or Yahoo absence" in content


def test_empirical_study_yahoo_observability_distinction() -> None:
    """Verify empirical study specification does not treat Yahoo raw HTTP status as guaranteed."""
    content = DECISION_MD.read_text(encoding="utf-8")

    assert "For Yahoo (`yfinance`), raw HTTP status codes and response bodies must NOT be assumed to be exposed" in content
    assert "The study should test TradeX-visible behavior first" in content


def test_tracker_preserves_c1_rollout_record() -> None:
    """Verify docs/PROJECT-TRACKER.md preserves the dedicated C1 runner rollout entry."""
    tracker_path = REPO_ROOT / "docs" / "PROJECT-TRACKER.md"
    assert tracker_path.exists(), f"Tracker file missing: {tracker_path}"
    tracker_content = tracker_path.read_text(encoding="utf-8")

    assert "Rollout Step 7 PIT Operations Runner (MVP-ARCH-001-R7-PIT-001C1)" in tracker_content
    assert "Rollout Step 7 PIT Observation Completeness & Health Semantics (MVP-ARCH-001-R7-PIT-STATUS-DEC-001)" in tracker_content


def test_approved_production_strategies_remains_empty() -> None:
    """Registry invariant: APPROVED_PRODUCTION_STRATEGIES is strictly empty."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()
