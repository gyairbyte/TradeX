"""Deterministic consistency tests for LONG-002B-DEC-001."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tradex.research.long_002_data_feasibility.decision_001 import (
    PREREQUISITE_BUNDLE,
    UPSTREAM_SPEC_PATHS,
    build_decision_packet,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_prerequisite_artifact_exists_and_is_not_supported() -> None:
    """PR #50's final artifact bundle is present and records not_supported."""
    bundle = REPO_ROOT / PREREQUISITE_BUNDLE
    manifest = json.loads((bundle / "artifact_manifest.json").read_text())
    report = json.loads((bundle / "feasibility_report.json").read_text())
    assert manifest["overall_disposition"] == "not_supported"
    assert report["overall_disposition"] == "not_supported"
    family_map = {f["family"]: f["disposition"] for f in report.get("data_families", [])}
    for family in (
        "security_identity_lifecycle_and_exclusion_classification",
        "earnings_event_timing",
    ):
        assert family_map[family] == "not_supported"


def test_decision_packet_matches_pr_50_dispositions() -> None:
    """The generated packet preserves PR #50's blocked-family dispositions."""
    packet = build_decision_packet(REPO_ROOT)
    assert packet["prerequisite_artifact"]["overall_disposition"] == "not_supported"
    family_dispositions = packet["prerequisite_artifact"]["blocked_family_dispositions"]
    assert family_dispositions["security_identity_lifecycle_and_exclusion_classification"] == "not_supported"
    assert family_dispositions["earnings_event_timing"] == "not_supported"


def test_decision_packet_status_and_authorization_invariants() -> None:
    """The packet is pending_gary_decision and does not authorize LONG-002C or production promotion."""
    packet = build_decision_packet(REPO_ROOT)
    assert packet["status"] == "pending_gary_decision"
    assert packet["long_002c_authorized"] is False
    assert packet["production_promotion_eligible"] is False
    assert packet["selected_option_id"] is None


def test_options_are_mutually_exclusive_and_none_selected() -> None:
    """There are exactly three options, none selected, and each keeps LONG-002C unauthorized."""
    packet = build_decision_packet(REPO_ROOT)
    options = packet["options"]
    assert len(options) == 3
    selected = [o for o in options if o["selected"]]
    assert selected == []
    option_ids = {o["id"] for o in options}
    assert option_ids == {"1", "2", "3"}
    for option in options:
        assert option["long_002c_authorized"] is False


def test_fail_closed_unknown_policy_contract_is_complete() -> None:
    """Option 2 defines the required fail-closed unknown policy terms."""
    packet = build_decision_packet(REPO_ROOT)
    option_2 = next(o for o in packet["options"] if o["id"] == "2")
    assert option_2["requires_gary_approval"] is True
    assert option_2["contract_amendment_required"] is True
    terms = option_2["contract_terms"]
    assert terms["security_unknown_rows_excluded_from_eligible_universe"] is True
    assert terms["no_backfill_of_current_or_later_classifications_as_historical_facts"] is True
    assert terms["unknown_security_classification_is_not_treated_as_common_stock"] is True
    assert terms["earnings_schedule_fields_remain_unknown_when_historical_known_at_time_evidence_unavailable"] is True
    assert terms["current_calendars_sec_filing_timestamps_or_actual_release_dates_may_not_be_substituted_for_previously_known_schedules"] is True
    assert terms["unavailable_earnings_timing_cannot_become_predictive_feature_or_ranking_input"] is True
    assert terms["coverage_selection_bias_comparability_and_sample_sufficiency_risks_documented"] is True
    assert terms["authorizes_only_a_separate_long_002c_design_pr_after_explicit_gary_approval"] is True


def test_option_3_is_documentation_only_and_requires_separate_approval() -> None:
    """Option 3 proposes a bounded provider amendment but records no live calls."""
    packet = build_decision_packet(REPO_ROOT)
    option_3 = next(o for o in packet["options"] if o["id"] == "3")
    assert option_3["requires_gary_approval"] is True
    proposal = option_3["provider_amendment_proposal"]
    budget = proposal["budget"]
    assert budget["max_http_requests"] <= 120
    assert budget["max_runtime_minutes"] <= 30
    assert budget["max_fallbacks_per_family"] <= 2
    assert budget["no_provider_calls_until_gary_approval"] is True
    assert "security_identity_lifecycle_and_exclusion_classification" in proposal
    assert "earnings_event_timing" in proposal
    assert len(proposal["security_identity_lifecycle_and_exclusion_classification"]["fallbacks"]) <= 2
    assert len(proposal["earnings_event_timing"]["fallbacks"]) <= 2


def test_recommendation_does_not_change_status_or_authorize() -> None:
    """The advisory recommendation is recorded but does not select an option or authorize LONG-002C."""
    packet = build_decision_packet(REPO_ROOT)
    rec = packet["advisory_recommendation"]
    assert rec["option_id"] in {"1", "2", "3"}
    assert packet["selected_option_id"] is None
    assert packet["long_002c_authorized"] is False
    assert packet["status"] == "pending_gary_decision"
    assert any("coverage" in r.lower() or "selection bias" in r.lower() for r in rec["risks"])


def test_upstream_spec_hashes_match_locked_files() -> None:
    """The packet's upstream spec hashes match the current locked files."""
    packet = build_decision_packet(REPO_ROOT)
    for name, rel_path in UPSTREAM_SPEC_PATHS.items():
        expected = _sha256(REPO_ROOT / rel_path)
        assert packet["upstream_spec_hashes"][name] == expected


def test_static_json_matches_generated_packet() -> None:
    """The committed JSON payload is consistent with the generator output."""
    generated = build_decision_packet(REPO_ROOT)
    json_path = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002B-DEC-001.json"
    committed = json.loads(json_path.read_text())
    assert committed == generated


def test_markdown_packet_exists_and_contains_key_invariants() -> None:
    """The human-readable packet exists and states the core governance invariants."""
    md_path = REPO_ROOT / "docs" / "research" / "LONG-002B-DEC-001.md"
    text = md_path.read_text()
    assert "pending_gary_decision" in text
    assert "LONG-002C authorized" in text or "long_002c_authorized" in text
    assert "Option 1" in text
    assert "Option 2" in text
    assert "Option 3" in text
    assert "fail-closed" in text.lower()
    assert "historical known-at-the-decision-time" in text
    assert "Research-governance" in text or "research-governance" in text
