"""Deterministic invariants for the committed MVP-ARCH-001 artifact."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = REPO_ROOT / "docs" / "product" / "MVP-ARCH-001.json"
MD_PATH = REPO_ROOT / "docs" / "product" / "MVP-ARCH-001.md"
TRACKER_PATH = REPO_ROOT / "docs" / "PROJECT-TRACKER.md"

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
    assert "gary_approved" in text
    assert "Gary Yang" in text
    assert "2026-08-19" in text


def test_classification_and_status(inv: dict) -> None:
    assert inv["classification"] == "product-architecture-and-governance-design-only"
    assert inv["decision_status"] == "gary_approved"
    assert inv["mvp_arch_001_status"]["decision_status"] == "gary_approved"
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
    options_providers = [
        p for p in inv["provider_inventory"] if p["name"] in ("unusual_whales", "tradier")
    ]
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
    mapping = {
        d["tab"]: (d["recommended_disposition"], d["target_area"])
        for d in inv["dashboard_inventory"]
    }
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
        if s["evidence_state"] in {
            "rejected",
            "not_supported",
            "inconclusive",
            "research_only",
            "exploratory",
            "legacy_heuristic",
        }:
            assert s["may_use_actionable_labels"] is False, s["component"]
            assert s["may_generate_automatic_alerts"] is False, s["component"]


def test_signal_journal_is_legacy_telemetry(inv: dict) -> None:
    journal = next(d for d in inv["dashboard_inventory"] if d["tab"] == "Signal Journal")
    assert journal["classification"] == "legacy_signal_telemetry"
    assert inv["journal_outcome_contract"]["current_state"] == "legacy_signal_telemetry"


def test_candidate_contract_separates_layers_and_concepts(inv: dict) -> None:
    contract = inv["candidate_contract"]
    snap_fields = contract["r5a_snapshot_fields"]
    eval_fields = contract["r5a_evaluation_envelope_fields"]
    evid_fields = contract["r5a_evidence_fields"]
    reas_fields = contract["r5a_reason_fields"]
    miss_fields = contract["r5a_missing_data_fields"]
    future_fields = contract["future_layer_fields_not_in_r5a_snapshot"]

    # Snapshot fields are neutral point-in-time facts
    assert "candidate_id" in snap_fields
    assert "contract_version" in snap_fields
    assert "symbol" in snap_fields
    assert "decision_timestamp" in snap_fields
    assert "trading_date" in snap_fields
    assert "security_identity_status" in snap_fields
    assert "created_at" in snap_fields

    # No strategy, trade plan, or actionability on candidate snapshot
    assert "strategy_id" not in snap_fields
    assert "candidate_state" not in snap_fields
    assert "entry_plan" not in snap_fields
    assert "invalidation_stop" not in snap_fields
    assert "outcome_status" not in snap_fields

    # Future layer fields explicitly documented
    assert "outcome_status" in future_fields
    assert "enter_now" in future_fields
    assert "armed" in future_fields
    assert "waitlist" in future_fields
    assert "entry_plan" in future_fields
    assert "strategy_id" in future_fields

    # Evaluation envelope
    assert "evaluation_id" in eval_fields
    assert "evaluator_id" in eval_fields
    assert "dimensions" in eval_fields

    # Evidence & Reasons & MissingData
    assert "evidence_type" in evid_fields
    assert "source_evidence_id" in reas_fields
    assert "status" in miss_fields


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
    candidate_step = next(
        s for s in inv["rollout_plan"] if s["order"] == 5
    )
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
    assert any("MVP-ARCH-001-R1" in g for g in invariants)


def test_governance_invariants_distinguish_r1_r2_r3_r4_r5a_from_later_steps(inv: dict) -> None:
    """Invariants prove R1/R2/R3/R4/R5A are Gary-approved while R5B/R5C/Steps 6-8 remain pending and broad booleans are false."""
    invariants = inv["governance_invariants"]
    # 1. No invariant claims EVERY rollout step remains pending.
    assert not any(
        "each rollout implementation step remains pending" in g.lower() for g in invariants
    )
    assert not any(
        "every rollout implementation step remains pending" in g.lower() for g in invariants
    )

    # 2. Invariant accurately distinguishes R1, R2, R3, R4, R5A, R5B, and R5C from later steps.
    r_invariant = next(
        (
            g
            for g in invariants
            if "MVP-ARCH-001-R1" in g
            and "MVP-ARCH-001-R2" in g
            and "MVP-ARCH-001-R3" in g
            and "MVP-ARCH-001-R4" in g
            and "MVP-ARCH-001-R5A" in g
            and "MVP-ARCH-001-R5B" in g
            and "MVP-ARCH-001-R5C" in g
        ),
        None,
    )
    assert r_invariant is not None, "Missing R1/R2/R3/R4/R5A/R5B/R5C governance invariant"
    assert "design-only" in r_invariant.lower()
    assert "separately gary-approved" in r_invariant.lower()
    assert re.search(r"steps 6[\u2013-]8 remain pending", r_invariant, re.IGNORECASE)
    assert "does not authorize production trading changes" in r_invariant.lower()

    # 3. Markdown matches the JSON invariant.
    md_text = MD_PATH.read_text(encoding="utf-8")
    assert not re.search(
        r"each rollout implementation step remains pending", md_text, re.IGNORECASE
    )
    assert "MVP-ARCH-001-R1" in md_text
    assert "MVP-ARCH-001-R2" in md_text
    assert "MVP-ARCH-001-R3" in md_text
    assert "MVP-ARCH-001-R4" in md_text
    assert "MVP-ARCH-001-R5A" in md_text
    assert "MVP-ARCH-001-R5B" in md_text
    assert "MVP-ARCH-001-R5C" in md_text

    # 4. Broad authorization booleans remain false.
    auth = inv["authorization"]
    for key, value in auth.items():
        assert value is False, f"authorization.{key}={value}"


def test_governance_invariants_do_not_contain_blanket_dashboard_prohibition(inv: dict) -> None:
    """Governance invariants must qualify dashboard prohibitions to avoid contradicting R3/R5C."""
    invariants = inv["governance_invariants"]
    # 1. No invariant contains an unqualified blanket prohibition on dashboard changes.
    for g in invariants:
        if "dashboard changes" in g:
            assert (
                "beyond the separately approved r3 navigation scope" in g.lower()
                or "beyond the separately approved r3/r5c navigation scope" in g.lower()
            ), g

    # 2. Markdown matches JSON qualification.
    md_text = MD_PATH.read_text(encoding="utf-8")
    for match in re.finditer(r"dashboard changes?(.*?)(?:\.|\n)", md_text, re.IGNORECASE):
        line = match.group(0).lower()
        if "does not authorize" in line or "does not implement" in line:
            assert (
                "beyond the separately approved r3 navigation scope" in line
                or "beyond the separately approved r3/r5c navigation scope" in line
            ), line

    # 3. R3 is explicitly navigation-authorized while Steps 4-8 and trading remain unauthorized.
    r3 = next(a for a in inv["rollout_approvals"] if a["task_id"] == "MVP-ARCH-001-R3")
    assert r3["implementation_authorized"] is True
    assert r3["navigation_changes_authorized"] is True
    assert r3["research_lab_navigation_authorized"] is True
    assert r3["settings_navigation_authorized"] is True
    assert r3["production_trading_changes_authorized"] is False
    assert r3["signal_logic_changes_authorized"] is False
    assert r3["score_changes_authorized"] is False
    assert r3["weight_changes_authorized"] is False
    assert r3["threshold_changes_authorized"] is False
    assert r3["alert_behavior_changes_authorized"] is False
    assert r3["provider_changes_authorized"] is False
    assert r3["provider_calls_authorized"] is False
    assert r3["live_provider_calls_authorized"] is False
    assert r3["database_migration_authorized"] is False
    assert r3["candidate_persistence_authorized"] is False
    assert r3["journal_replacement_authorized"] is False
    assert r3["pit_capture_authorized"] is False
    assert r3["strategy_promotion_authorized"] is False
    assert r3["long_002c_work_authorized"] is False


def test_governance_invariants_do_not_contain_blanket_alert_prohibition(inv: dict) -> None:
    """Governance invariants must qualify alert prohibitions to avoid contradicting R4."""
    invariants = inv["governance_invariants"]
    # 1. No invariant contains an unqualified blanket prohibition on alert changes.
    for g in invariants:
        if "alert changes" in g:
            assert "beyond the separately approved r4 gating scope" in g.lower(), g

    # 2. Markdown matches JSON qualification.
    md_text = MD_PATH.read_text(encoding="utf-8")
    for match in re.finditer(r"alert changes?(.*?)(?:\.|\n)", md_text, re.IGNORECASE):
        line = match.group(0).lower()
        if "does not authorize" in line or "does not implement" in line:
            assert "beyond the separately approved r4 gating scope" in line, line

    # 3. R4 is explicitly alert-gating authorized while Steps 5-8 and trading remain unauthorized.
    r4 = next(a for a in inv["rollout_approvals"] if a["task_id"] == "MVP-ARCH-001-R4")
    assert r4["implementation_authorized"] is True
    assert r4["alert_behavior_changes_authorized"] is True
    assert r4["automatic_actionable_alert_gating_authorized"] is True
    assert r4["production_trading_changes_authorized"] is False
    assert r4["signal_logic_changes_authorized"] is False
    assert r4["score_changes_authorized"] is False
    assert r4["weight_changes_authorized"] is False
    assert r4["threshold_changes_authorized"] is False
    assert r4["ranking_changes_authorized"] is False
    assert r4["candidate_eligibility_changes_authorized"] is False
    assert r4["navigation_changes_authorized"] is False
    assert r4["provider_changes_authorized"] is False
    assert r4["provider_calls_authorized"] is False
    assert r4["live_provider_calls_authorized"] is False
    assert r4["database_migration_authorized"] is False
    assert r4["candidate_persistence_authorized"] is False
    assert r4["journal_replacement_authorized"] is False
    assert r4["pit_capture_authorized"] is False
    assert r4["strategy_promotion_authorized"] is False
    assert r4["long_002c_work_authorized"] is False


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


@pytest.fixture
def tracker_text() -> str:
    assert TRACKER_PATH.exists(), f"Missing {TRACKER_PATH}"
    return TRACKER_PATH.read_text(encoding="utf-8")


_LONG_002_AUTH_KEYS = {
    "long_002b_amend_002_completed": True,
    "long_002c_design_authorized_by_pr52": True,
    "long_002c_currently_paused_by_gary": True,
    "long_002c_dataset_construction_authorized": False,
    "long_002c_work_authorized_by_mvp_arch_001": False,
}


def test_tracker_contains_explicit_long_002_authorization(tracker_text: str) -> None:
    lower = tracker_text.lower()
    for key, value in _LONG_002_AUTH_KEYS.items():
        assert key in tracker_text, f"Missing explicit LONG-002 key: {key}"
        # Each key is followed by the expected boolean string value (possibly in backticks).
        bool_token = "true" if value else "false"
        assert re.search(rf"{re.escape(key)}[^\n]{{0,40}}`?{bool_token}`?", lower), key


def test_tracker_does_not_contain_ambiguous_long_002c_authorization(
    tracker_text: str,
) -> None:
    """`long_002c_work_authorized` (without suffix) is gone; the explicit MVP-bound key remains."""
    assert re.search(r"\blong_002c_work_authorized\b", tracker_text) is None
    assert "long_002c_work_authorized_by_mvp_arch_001" in tracker_text


def test_tracker_long_002b_amend_002_is_not_current_phase(tracker_text: str) -> None:
    assert re.search(r"\*\*Current phase:\*\*.*?LONG-002B-AMEND-002", tracker_text) is None
    # It is, however, listed as a completed phase.
    assert "**Completed phase:** `LONG-002B-AMEND-002`" in tracker_text


def test_tracker_does_not_say_long_002a_is_active_or_in_progress(tracker_text: str) -> None:
    lower = tracker_text.lower()
    assert "devin/long-002a-locked-research-contract" not in lower
    assert (
        re.search(
            r"long[-_]002a.*(?:is now the active|active research contract|in progress|current phase)",
            lower,
        )
        is None
    )
    assert re.search(r"(?:active research contract|current phase).*(?:long[-_]002a)", lower) is None


def test_tracker_does_not_recommend_starting_long_002a_or_002b(
    tracker_text: str,
) -> None:
    text = tracker_text.lower()
    # Capture the remaining-work and recommended-order sections.
    m = re.search(r"(?si)\*\*Remaining non-completed items:\*\*(.*?)\Z", text)
    assert m, "Could not find remaining-work section"
    tail = m.group(1)
    stale = [
        "review and accept the locked `long-002`",
        "long-002b — core data feasibility",
        "long-002a locked research contract",
        "long-002a is now the active",
        "active research program is now `long-002`",
        "devin/long-002a-locked-research-contract",
    ]
    for phrase in stale:
        assert phrase not in tail, f"Stale recommendation remains: {phrase!r}"


def test_tracker_mvp_arch_001_is_separate_and_gary_approved(tracker_text: str) -> None:
    lower = tracker_text.lower()
    assert "mvp-arch-001" in lower
    # The tracker marks MVP-ARCH-001 completed/Gary approved and does not list it
    # as pending, in progress, or current phase.
    mvp_section = _section(tracker_text, "### MVP-ARCH-001:")
    assert "gary_approved" in mvp_section.lower()
    assert "pending_gary_decision" not in mvp_section.lower()
    assert "in progress" not in mvp_section.lower()
    assert "**Current phase:**" not in mvp_section
    # The tracker repeats the explicit assertion from the JSON: MVP-ARCH-001 does
    # not authorize LONG-002C work.
    assert "long_002c_work_authorized_by_mvp_arch_001" in tracker_text


def _section(text: str, header: str) -> str:
    m = re.search(rf"(?si){re.escape(header)}(.*?)(?:\n## |\n\*\*|\Z)", text)
    assert m, f"Could not find section: {header}"
    return m.group(1)


def test_tracker_summary_and_remaining_work_are_consistent(tracker_text: str) -> None:
    remaining = _section(tracker_text, "**Remaining non-completed items:**")
    work_order = _section(tracker_text, "**Recommended next work order:**")
    pr_order = _section(tracker_text, "**Recommended next pull request order:**")

    # MVP-ARCH-001 is now completed/Gary approved and must not appear as a
    # remaining non-completed workstream.
    assert "MVP-ARCH-001" not in remaining
    assert "LONG-002C" in remaining
    assert "DAYTRADE-001" in remaining
    assert "LONG-002A" not in remaining
    assert "LONG-002B" not in remaining

    # The tracker narrative documents the completed/merged R1-R4 steps, separately approved R5A, R5B, and R5C,
    # and unauthorized status of subsequent steps.
    assert "r4 was separately gary-approved" in tracker_text.lower()
    assert "r5a was separately gary-approved on 2026-08-23 for candidate snapshot domain contract and schema v4 persistence primitives only and implemented by pr #61" in tracker_text.lower()
    assert "no production strategy was promoted" in tracker_text.lower()
    assert "steps 6–8 remain pending separate gary approval" in tracker_text.lower() or "steps 6-8 remain pending separate gary approval" in tracker_text.lower()

    # The recommended work order states a separate Gary/ChatGPT decision is required and no next PR is already authorized.
    assert "separate gary/chatgpt sequencing and approval decision" in work_order.lower()
    assert "no next rollout implementation pr is currently authorized" in work_order.lower()
    assert "LONG-002C" in work_order
    assert "DAYTRADE-001" in work_order
    assert (
        "no next implementation pr is currently authorized"
        in pr_order.lower()
    )
    assert "long-002a-locked-research-contract" not in tracker_text.lower()


_STATUS_ORDER = ["Completed", "Deferred", "Proposed", "In progress", "Blocked", "Rejected"]


def _parse_tracker_status_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {s: 0 for s in _STATUS_ORDER}
    for line in re.findall(r"(?m)^- \*\*Status:\*\* (.+)$", text):
        if re.search(r"\bin progress\b", line, re.IGNORECASE):
            counts["In progress"] += 1
        elif re.search(r"\b(?:completed?|complete)\b", line, re.IGNORECASE):
            counts["Completed"] += 1
        else:
            for status in _STATUS_ORDER:
                if re.match(rf"{re.escape(status)}(?:\b|$)", line, re.IGNORECASE):
                    counts[status] += 1
                    break
    return counts


def _parse_tracker_priority_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {"High": 0, "Medium": 0, "Low": 0}
    for p in re.findall(r"(?m)^- \*\*Priority:\*\* (High|Medium|Low)$", text):
        counts[p] += 1
    return counts


def _parse_summary_table(text: str, table_name: str) -> dict[str, int]:
    pattern = rf"(?msi)^## Summary by {re.escape(table_name)}\s*\n(.*?)(?:\n## |\n\*\*|\Z)"
    m = re.search(pattern, text)
    assert m, f"Could not find summary table: {table_name}"
    section = m.group(1)
    rows = re.findall(r"\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|", section)
    return {k.strip(): int(v) for k, v in rows if k.strip().lower() != "status"}


def test_tracker_summary_status_counts_match_entries(tracker_text: str) -> None:
    actual = _parse_tracker_status_counts(tracker_text)
    table = _parse_summary_table(tracker_text, "status")
    # The table must list the same totals that appear in the task entries.
    for status in _STATUS_ORDER:
        assert actual[status] == table.get(status, 0), (
            f"{status}: entries={actual[status]}, table={table.get(status, 0)}"
        )


def test_tracker_summary_priority_counts_match_entries(tracker_text: str) -> None:
    actual = _parse_tracker_priority_counts(tracker_text)
    table = _parse_summary_table(tracker_text, "priority")
    for priority in ["High", "Medium", "Low"]:
        assert actual[priority] == table.get(priority, 0), (
            f"{priority}: entries={actual[priority]}, table={table.get(priority, 0)}"
        )


def test_decision_record_fields(inv: dict) -> None:
    """The machine-readable decision record contains Gary's design-only approval."""
    record = inv["approval_record"]
    assert record["approved_by"] == "Gary Yang"
    assert record["approved_on"] == "2026-08-19"
    assert record["approval_scope"] == "design_only"
    assert record["implementation_authorized"] is False
    assert record["production_trading_changes_authorized"] is False
    assert record["long_002c_dataset_construction_authorized"] is False
    assert "MVP-ARCH-001" in record["decision_quote"]


def test_design_approval_does_not_authorize_implementation(inv: dict) -> None:
    """Every implementation/production authorization boolean remains false."""
    auth = inv["authorization"]
    for key, value in auth.items():
        assert value is False, f"authorization.{key}={value}"
    assert inv["approval_record"]["implementation_authorized"] is False
    assert inv["approval_record"]["production_trading_changes_authorized"] is False
    assert inv["approval_record"]["long_002c_dataset_construction_authorized"] is False
    assert inv["long_002_status"]["long_002c_dataset_construction_authorized"] is False
    assert inv["long_002_status"]["long_002c_work_authorized_by_mvp_arch_001"] is False


def test_rollout_steps_require_separate_gary_approval(inv: dict) -> None:
    for step in inv["rollout_plan"]:
        assert step["requires_gary_approval"] is True, step["pr"]


def _file_contains_mvp_approved_boundary(path: Path, patterns: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    section: str | None = None
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            section = m.group(0)
            break
    assert section is not None, f"No MVP-ARCH-001 section found in {path}"
    section_lower = section.lower()
    assert "gary_approved" in section_lower, path
    assert "design-only" in section_lower or "design_only" in section_lower, path
    assert "implementation" in section_lower, path
    assert "2026-08-19" in section_lower, path
    assert "gary yang" in section_lower, path
    # The boundary statement must not be contradicted by an implementation
    # authorization claim in the same section.
    assert re.search(r"implementation(?:_authorized)?\s*[:=]?\s*true", section_lower) is None, path


def test_markdown_agrees_with_approved_json() -> None:
    _file_contains_mvp_approved_boundary(
        MD_PATH,
        [r"(?msi)^# MVP-ARCH-001:.*?(?=^## |\Z)"],
    )


def test_readme_agrees_with_approved_json() -> None:
    readme = REPO_ROOT / "README.md"
    _file_contains_mvp_approved_boundary(
        readme,
        [r"(?msi)^#### MVP-ARCH-001:.*?(?=^#### |^### |^## |\Z)"],
    )


def test_claude_agrees_with_approved_json() -> None:
    claude = REPO_ROOT / "CLAUDE.md"
    _file_contains_mvp_approved_boundary(
        claude,
        [r"(?msi)^- \*\*Product consolidation \(MVP-ARCH-001\).*?(?=^- \*\*|^## |^### |^#### |\Z)"],
    )


def test_setup_agrees_with_r3_navigation() -> None:
    """SETUP.md must accurately reference R3 navigation locations."""
    setup_path = REPO_ROOT / "SETUP.md"
    assert setup_path.exists()
    text = setup_path.read_text(encoding="utf-8")

    # Watcher / Coil reference
    assert "Research Lab → Coil Context" in text
    assert "Signal Journal" in text

    # Navigation cheat-sheet
    assert "Research Lab" in text
    assert "Settings" in text
    assert "Alert Delivery" in text
    assert "Legacy Weights" in text
    assert "Pattern Similarity — Rejected" in text
    assert "Options Activity — Exploratory" in text

    # Ensure Coil Detector is not listed as an independent top-level tab in table
    cheat_sheet_match = re.search(r"## 14\. Navigation cheat-sheet.*?(?=## 15|\Z)", text, re.DOTALL)
    assert cheat_sheet_match is not None
    table_text = cheat_sheet_match.group(0)
    assert "| **Coil Detector** |" not in table_text
    assert "| **Weights** |" not in table_text
    assert "| **Alerts** |" not in table_text


def test_tracker_mvp_arch_001_marked_completed(tracker_text: str) -> None:
    mvp = _section(tracker_text, "### MVP-ARCH-001:")
    assert "gary_approved" in mvp.lower()
    assert "completed" in mvp.lower()
    assert "pending_gary_decision" not in mvp.lower()
    assert "in progress" not in mvp.lower()


def test_tracker_long_002c_authorized_but_paused(tracker_text: str) -> None:
    lower = tracker_text.lower()
    assert "long_002c_design_authorized_by_pr52" in lower
    assert "long_002c_currently_paused_by_gary" in lower
    assert "long_002c_dataset_construction_authorized" in lower
    assert "long_002c_work_authorized_by_mvp_arch_001" in lower


def test_rollout_approvals_record(inv: dict) -> None:
    """The JSON records Gary's scoped approvals for MVP-ARCH-001-R1, R2, and R3 without broad booleans."""
    approvals = inv.get("rollout_approvals", [])
    assert len(approvals) >= 3
    r1 = next((a for a in approvals if a.get("task_id") == "MVP-ARCH-001-R1"), None)
    assert r1 is not None
    assert r1["rollout_order"] == 1
    assert r1["approval_status"] == "gary_approved"
    assert r1["approved_by"] == "Gary Yang"
    assert r1["approved_on"] == "2026-08-21"
    assert r1["implementation_authorized"] is True
    assert r1["production_trading_changes_authorized"] is False
    assert r1["navigation_changes_authorized"] is False
    assert r1["alert_behavior_changes_authorized"] is False
    assert r1["provider_changes_authorized"] is False
    assert r1["provider_calls_authorized"] is False
    assert r1["database_migration_authorized"] is False
    assert r1["strategy_promotion_authorized"] is False
    assert r1["long_002c_work_authorized"] is False

    r2 = next((a for a in approvals if a.get("task_id") == "MVP-ARCH-001-R2"), None)
    assert r2 is not None
    assert r2["rollout_order"] == 2
    assert r2["approval_status"] == "gary_approved"
    assert r2["approved_by"] == "Gary Yang"
    assert r2["approved_on"] == "2026-08-21"
    assert r2["scope"] == "provider lifecycle/configuration simplification only"
    assert r2["implementation_authorized"] is True
    assert r2["provider_changes_authorized"] is True
    assert r2["default_ohlcv_provider_change_authorized"] is True
    assert r2["premarket_source_decoupling_authorized"] is True
    assert r2["earnings_unknown_handling_authorized"] is True
    assert r2["production_trading_changes_authorized"] is False
    assert r2["signal_logic_changes_authorized"] is False
    assert r2["score_changes_authorized"] is False
    assert r2["weight_changes_authorized"] is False
    assert r2["threshold_changes_authorized"] is False
    assert r2["navigation_changes_authorized"] is False
    assert r2["alert_behavior_changes_authorized"] is False
    assert r2["live_provider_calls_authorized"] is False
    assert r2["database_migration_authorized"] is False
    assert r2["strategy_promotion_authorized"] is False
    assert r2["long_002c_work_authorized"] is False

    r3 = next((a for a in approvals if a.get("task_id") == "MVP-ARCH-001-R3"), None)
    assert r3 is not None
    assert r3["rollout_order"] == 3
    assert r3["approval_status"] == "gary_approved"
    assert r3["approved_by"] == "Gary Yang"
    assert r3["approved_on"] == "2026-08-22"
    assert r3["scope"] == "navigation consolidation only"
    assert r3["implementation_authorized"] is True
    assert r3["navigation_changes_authorized"] is True
    assert r3["research_lab_navigation_authorized"] is True
    assert r3["settings_navigation_authorized"] is True
    assert r3["production_trading_changes_authorized"] is False
    assert r3["signal_logic_changes_authorized"] is False
    assert r3["score_changes_authorized"] is False
    assert r3["weight_changes_authorized"] is False
    assert r3["threshold_changes_authorized"] is False
    assert r3["alert_behavior_changes_authorized"] is False
    assert r3["provider_changes_authorized"] is False
    assert r3["provider_calls_authorized"] is False
    assert r3["live_provider_calls_authorized"] is False
    assert r3["database_migration_authorized"] is False
    assert r3["candidate_persistence_authorized"] is False
    assert r3["journal_replacement_authorized"] is False
    assert r3["pit_capture_authorized"] is False
    assert r3["strategy_promotion_authorized"] is False
    assert r3["long_002c_work_authorized"] is False

    r4 = next((a for a in approvals if a.get("task_id") == "MVP-ARCH-001-R4"), None)
    assert r4 is not None
    assert r4["rollout_order"] == 4
    assert r4["approval_status"] == "gary_approved"
    assert r4["approved_by"] == "Gary Yang"
    assert r4["approved_on"] == "2026-08-22"
    assert r4["scope"] == "fail-closed automatic market alert gating only"
    assert r4["implementation_authorized"] is True
    assert r4["alert_behavior_changes_authorized"] is True
    assert r4["automatic_actionable_alert_gating_authorized"] is True
    assert r4["production_trading_changes_authorized"] is False
    assert r4["signal_logic_changes_authorized"] is False
    assert r4["score_changes_authorized"] is False
    assert r4["weight_changes_authorized"] is False
    assert r4["threshold_changes_authorized"] is False
    assert r4["ranking_changes_authorized"] is False
    assert r4["candidate_eligibility_changes_authorized"] is False
    assert r4["navigation_changes_authorized"] is False
    assert r4["provider_changes_authorized"] is False
    assert r4["provider_calls_authorized"] is False
    assert r4["live_provider_calls_authorized"] is False
    assert r4["database_migration_authorized"] is False
    assert r4["candidate_persistence_authorized"] is False
    assert r4["journal_replacement_authorized"] is False
    assert r4["pit_capture_authorized"] is False
    assert r4["strategy_promotion_authorized"] is False
    assert r4["long_002c_work_authorized"] is False

    r5a = next((a for a in approvals if a.get("task_id") == "MVP-ARCH-001-R5A"), None)
    assert r5a is not None
    assert r5a["rollout_order"] == 5
    assert r5a["approval_status"] == "gary_approved"
    assert r5a["approved_by"] == "Gary Yang"
    assert r5a["approved_on"] == "2026-08-23"
    assert r5a["scope"] == "candidate snapshot domain contract and additive schema v4 persistence primitives only"
    assert r5a["implementation_authorized"] is True
    assert r5a["database_migration_authorized"] is True
    assert r5a["candidate_persistence_primitives_authorized"] is True
    assert r5a["candidate_schema_v4_authorized"] is True
    assert r5a["production_trading_changes_authorized"] is False
    assert r5a["signal_logic_changes_authorized"] is False
    assert r5a["score_changes_authorized"] is False
    assert r5a["weight_changes_authorized"] is False
    assert r5a["threshold_changes_authorized"] is False
    assert r5a["ranking_changes_authorized"] is False
    assert r5a["candidate_eligibility_changes_authorized"] is False
    assert r5a["candidate_runtime_writes_authorized"] is False
    assert r5a["candidate_aggregation_authorized"] is False
    assert r5a["candidate_evaluator_logic_authorized"] is False
    assert r5a["actionable_candidate_states_authorized"] is False
    assert r5a["candidate_ui_authorized"] is False
    assert r5a["navigation_changes_authorized"] is False
    assert r5a["alert_behavior_changes_authorized"] is False
    assert r5a["provider_changes_authorized"] is False
    assert r5a["provider_calls_authorized"] is False
    assert r5a["live_provider_calls_authorized"] is False
    assert r5a["journal_replacement_authorized"] is False
    assert r5a["outcome_tracking_authorized"] is False
    assert r5a["pit_capture_job_authorized"] is False
    assert r5a["strategy_promotion_authorized"] is False
    assert r5a["long_002c_work_authorized"] is False
    assert r5a["r5b_implementation_authorized"] is True
    assert r5a["r5c_implementation_authorized"] is False

    r5b = next((a for a in approvals if a.get("task_id") == "MVP-ARCH-001-R5B"), None)
    assert r5b is not None
    assert r5b["rollout_order"] == 6
    assert r5b["approval_status"] == "gary_approved"
    assert r5b["approved_by"] == "Gary Yang"
    assert r5b["approved_on"] == "2026-08-23"
    assert r5b["scope"] == "prospective observation aggregation and descriptive exploratory shadow candidate evaluation only"
    assert r5b["implementation_authorized"] is True
    assert r5b["candidate_runtime_writes_authorized"] is True
    assert r5b["candidate_aggregation_authorized"] is True
    assert r5b["shadow_descriptive_evaluator_authorized"] is True
    assert r5b["database_migration_authorized_for_r5b"] is False
    assert r5b["schema_changes_authorized"] is False
    assert r5b["new_provider_calls_authorized"] is False
    assert r5b["provider_behavior_changes_authorized"] is False
    assert r5b["candidate_trading_eligibility_changes_authorized"] is False
    assert r5b["actionable_candidate_states_authorized"] is False
    assert r5b["ranking_changes_authorized"] is False
    assert r5b["score_changes_authorized"] is False
    assert r5b["weight_changes_authorized"] is False
    assert r5b["threshold_changes_authorized"] is False
    assert r5b["signal_logic_changes_authorized"] is False
    assert r5b["alert_behavior_changes_authorized"] is False
    assert r5b["candidate_ui_authorized"] is False
    assert r5b["navigation_changes_authorized"] is False
    assert r5b["strategy_promotion_authorized"] is False
    assert r5b["production_trading_changes_authorized"] is False
    assert r5b["r5c_implementation_authorized"] is True
    assert r5b["journal_replacement_authorized"] is False
    assert r5b["r6_implementation_authorized"] is False
    assert r5b["r7_implementation_authorized"] is False
    assert r5b["r8_implementation_authorized"] is False
    assert r5b["long_002c_work_authorized"] is False

    r5c = next((a for a in approvals if a.get("task_id") == "MVP-ARCH-001-R5C"), None)
    assert r5c is not None
    assert r5c["rollout_order"] == 7
    assert r5c["approval_status"] == "gary_approved"
    assert r5c["approved_by"] == "Gary Yang"
    assert r5c["approved_on"] == "2026-08-23"
    assert r5c["scope"] == "truthful read-only Today and Candidate Detail workflow only"
    assert r5c["implementation_authorized"] is True
    assert r5c["candidate_ui_authorized"] is True
    assert r5c["today_tab_authorized"] is True
    assert r5c["candidate_detail_authorized"] is True
    assert r5c["read_only_candidate_queries_authorized"] is True
    assert r5c["database_migration_authorized"] is False
    assert r5c["schema_changes_authorized"] is False
    assert r5c["candidate_persistence_writes_authorized"] is False
    assert r5c["provider_calls_authorized"] is False
    assert r5c["provider_changes_authorized"] is False
    assert r5c["candidate_trading_eligibility_changes_authorized"] is False
    assert r5c["actionable_candidate_states_authorized"] is False
    assert r5c["ranking_changes_authorized"] is False
    assert r5c["score_changes_authorized"] is False
    assert r5c["weight_changes_authorized"] is False
    assert r5c["threshold_changes_authorized"] is False
    assert r5c["signal_logic_changes_authorized"] is False
    assert r5c["alert_behavior_changes_authorized"] is False
    assert r5c["strategy_promotion_authorized"] is False
    assert r5c["production_trading_changes_authorized"] is False
    assert r5c["journal_replacement_authorized"] is False
    assert r5c["r6_implementation_authorized"] is False
    assert r5c["r7_implementation_authorized"] is False
    assert r5c["r8_implementation_authorized"] is False
    assert r5c["long_002c_work_authorized"] is False


def test_governance_invariants_database_migration_authorized_consistency(inv: dict) -> None:
    """Verify that R5A additive schema-v4 migration is authorized without blanket invariant contradictions."""
    approvals = inv.get("rollout_approvals", [])
    r5a = next((a for a in approvals if a.get("task_id") == "MVP-ARCH-001-R5A"), None)
    assert r5a is not None
    assert r5a["database_migration_authorized"] is True
    assert r5a["candidate_schema_v4_authorized"] is True

    invariants = inv["governance_invariants"]
    # Blanket "no database migrations" without qualification must not exist
    for inv_str in invariants:
        if "database migrations" in inv_str:
            assert "beyond the separately approved additive MVP-ARCH-001-R5A schema-v4 persistence scope" in inv_str

    # Markdown and JSON invariants must match exactly
    doc_text = MD_PATH.read_text(encoding="utf-8")
    for inv_str in invariants:
        assert inv_str in doc_text
