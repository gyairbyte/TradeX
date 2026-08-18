"""Deterministic regression tests for LONG-002B-AMEND-002."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tradex.research.long_002_data_feasibility.amendment_002 import (
    AMEND_001_BUNDLE,
    DECISION_PACKET_JSON,
    DECISION_PACKET_MD,
    STARTING_MAIN_SHA,
    UPSTREAM_SPEC_PATHS,
    build_selection_record,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_selection_record_status_and_authorization() -> None:
    """The selection record reflects Gary's approval of Option 2 and the correct authorization boundary."""
    record = build_selection_record(REPO_ROOT)
    assert record["amendment_id"] == "LONG-002B-AMEND-002"
    assert record["status"] == "gary_approved"
    assert record["selected_option_id"] == "2"
    assert record["fail_closed_unknown_policy_approved"] is True
    assert record["long_002c_design_pr_authorized"] is True
    assert record["long_002c_dataset_construction_authorized"] is False
    assert record["production_promotion_eligible"] is False
    assert record["starting_main_sha"] == STARTING_MAIN_SHA
    assert record["prerequisite_decision_packet_commit"] == STARTING_MAIN_SHA
    assert "dataset construction" in record["authorization_boundary"].lower()


def test_only_option_2_selected_and_others_not_authorized() -> None:
    """Options 1 and 3 from the decision packet are not selected or authorized."""
    decision = json.loads((REPO_ROOT / DECISION_PACKET_JSON).read_text())
    option_1 = next(o for o in decision["options"] if o["id"] == "1")
    option_2 = next(o for o in decision["options"] if o["id"] == "2")
    option_3 = next(o for o in decision["options"] if o["id"] == "3")
    assert option_2["selected"] is False  # selection is recorded in AMEND-002, not by mutating the packet
    assert option_2["requires_gary_approval"] is True
    assert option_1["selected"] is False
    assert option_3["selected"] is False
    assert option_1["long_002c_authorized"] is False
    assert option_2["long_002c_authorized"] is False
    assert option_3["long_002c_authorized"] is False


def test_prior_not_supported_findings_unchanged() -> None:
    """LONG-002B and LONG-002B-AMEND-001 feasibility findings remain not_supported."""
    record = build_selection_record(REPO_ROOT)
    assert record["amendment_001_artifact_reference"]["overall_disposition"] == "not_supported"
    decision = json.loads((REPO_ROOT / DECISION_PACKET_JSON).read_text())
    family_map = {f["id"]: f["disposition"] for f in decision["blocked_families"]}
    assert family_map["security_identity_lifecycle_and_exclusion_classification"] == "not_supported"
    assert family_map["earnings_event_timing"] == "not_supported"


def test_security_unknowns_excluded_not_common_stock() -> None:
    """Unknown security classification is excluded and never treated as common stock."""
    record = build_selection_record(REPO_ROOT)
    sec = record["locked_security_policy"]
    assert "independently" in sec["per_date_classification"].lower()
    assert "never" in sec["no_backfill"].lower()
    assert "never" in sec["unknown_not_common_stock"].lower()
    assert "excluded" in sec["unknown_excluded_from_universe"].lower()
    assert sec["coverage_failure_inconclusive"].startswith("Coverage failure")


def test_no_historical_classification_backfill() -> None:
    """Current or later classifications cannot backfill historical facts."""
    record = build_selection_record(REPO_ROOT)
    assert "never backfill" in record["locked_security_policy"]["no_backfill"].lower()
    assert any("never" in inv.lower() and "backfill" in inv.lower() for inv in record["governance_invariants"])


def test_earnings_unknowns_not_confirmed_non_earnings() -> None:
    """Unknown PIT earnings schedule cannot be labeled a confirmed non-earnings setup."""
    record = build_selection_record(REPO_ROOT)
    assert "cannot be labeled" in record["locked_earnings_policy"]["no_confirmed_non_earnings"].lower()
    assert record["locked_earnings_policy"]["schedule_unknown_when_unavailable"].startswith("When")


def test_earnings_unknowns_cannot_reach_enter_now_or_armed() -> None:
    """Unknown earnings schedule cannot reach Enter Now or Armed under the ordinary policy."""
    record = build_selection_record(REPO_ROOT)
    earn = record["locked_earnings_policy"]
    assert "enter now" in earn["no_enter_now_or_armed"].lower()
    assert "armed" in earn["no_enter_now_or_armed"].lower()
    assert "waitlist" in earn["maximum_actionable_state"].lower() or "do_not_surface" in earn["maximum_actionable_state"].lower()


def test_no_retrospective_earnings_proxy() -> None:
    """Current calendars, SEC filing timestamps, actual release dates, or reconstructed dates cannot restore actionability."""
    record = build_selection_record(REPO_ROOT)
    text = record["locked_earnings_policy"]["no_retrospective_proxies"].lower()
    assert "current calendars" in text
    assert "sec filing" in text
    assert "actual" in text
    assert "retrospectively" in text or "restore" in text
    assert any("retrospective" in inv.lower() for inv in record["governance_invariants"])


def test_unknown_earnings_unavailable_for_actionability_and_kpi() -> None:
    """Unknown earnings observations are unavailable for actionability/KPI evaluation."""
    record = build_selection_record(REPO_ROOT)
    assert "unavailable" in record["locked_earnings_policy"]["actionability_and_kpi_marked_unavailable"].lower()


def test_insufficient_schedule_coverage_inconclusive() -> None:
    """Insufficient known-schedule coverage produces an inconclusive result rather than a relaxed gate."""
    record = build_selection_record(REPO_ROOT)
    assert "inconclusive" in record["locked_earnings_policy"]["insufficient_coverage_inconclusive"].lower()
    assert "relaxed" not in record["locked_earnings_policy"]["insufficient_coverage_inconclusive"].lower()
    assert "weaken" in record["locked_earnings_policy"]["no_weakening_for_sample_size"].lower()


def test_task_identity_is_amendment_not_program() -> None:
    """The selection record is scoped to LONG-002B-AMEND-002 and preserves LONG-002 as program_id."""
    record = build_selection_record(REPO_ROOT)
    assert record["task_id"] == "LONG-002B-AMEND-002"
    assert record["amendment_id"] == "LONG-002B-AMEND-002"
    assert record["program_id"] == "LONG-002"


def test_approval_provenance_is_post_pr51_assignment_not_pr_itself() -> None:
    """PR #51 was the prerequisite decision packet, not the approval source; the selection came from the assignment."""
    record = build_selection_record(REPO_ROOT)
    assert record["starting_main_sha"] == STARTING_MAIN_SHA
    assert record["prerequisite_decision_packet_commit"] == STARTING_MAIN_SHA
    source = record["gary_approval_source"].lower()
    assert "pr #51" not in source or "not" in source
    assert "assignment" in source
    assert "explicit option 2" in source or "option 2 selection" in source
    assert "prerequisite" in source
    assert "merge commit" in source


def test_only_long_002c_design_pr_authorized() -> None:
    """Only a LONG-002C design PR is authorized; dataset construction, provider calls, and production changes are not."""
    record = build_selection_record(REPO_ROOT)
    assert record["long_002c_design_pr_authorized"] is True
    assert record["long_002c_dataset_construction_authorized"] is False
    boundary = record["authorization_boundary"].lower()
    assert "design" in boundary
    assert "dataset construction" in boundary
    assert "provider calls" in boundary
    assert "production" in boundary or "outcome" in boundary
    inv_text = " ".join(record["governance_invariants"]).lower()
    assert "only a long-002c design pr is authorized" in inv_text


def test_upstream_hashes_match_current_files() -> None:
    """The selection record's upstream spec hashes match the current locked files."""
    record = build_selection_record(REPO_ROOT)
    for name, rel_path in UPSTREAM_SPEC_PATHS.items():
        expected = _sha256(REPO_ROOT / rel_path)
        assert record["upstream_spec_hashes"][name] == expected


def test_decision_packet_hashes_match_current_files() -> None:
    """The selection record references the current decision packet by hash."""
    record = build_selection_record(REPO_ROOT)
    dec = record["decision_packet_reference"]
    assert dec["markdown_sha256"] == _sha256(REPO_ROOT / DECISION_PACKET_MD)
    assert dec["json_sha256"] == _sha256(REPO_ROOT / DECISION_PACKET_JSON)


def test_amendment_001_artifact_hashes_match() -> None:
    """The selection record references the PR #50 artifact manifest and report by hash."""
    record = build_selection_record(REPO_ROOT)
    bundle = REPO_ROOT / AMEND_001_BUNDLE
    assert record["amendment_001_artifact_reference"]["manifest_sha256"] == _sha256(bundle / "artifact_manifest.json")
    assert record["amendment_001_artifact_reference"]["report_sha256"] == _sha256(bundle / "feasibility_report.json")


def test_static_json_matches_generated_record() -> None:
    """The committed JSON selection record is consistent with the generator output."""
    generated = build_selection_record(REPO_ROOT)
    json_path = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002B-AMEND-002.json"
    committed = json.loads(json_path.read_text())
    assert committed == generated


def test_markdown_amendment_exists_and_contains_key_invariants() -> None:
    """The human-readable amendment exists and states the core governance invariants."""
    md_path = REPO_ROOT / "docs" / "research" / "LONG-002B-AMEND-002.md"
    text = md_path.read_text()
    assert "gary_approved" in text.lower() or "gary approved" in text.lower()
    assert "Option 2" in text
    assert "LONG-002C design PR authorized" in text or "long_002c_design_pr_authorized" in text
    assert "dataset construction authorized" in text.lower() or "long_002c_dataset_construction_authorized" in text
    assert "fail-closed" in text.lower()
    assert "Enter Now" in text or "Armed" in text
    assert "Waitlist" in text or "do_not_surface" in text
