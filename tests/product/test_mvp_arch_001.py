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
    candidate_step = next(
        s for s in inv["rollout_plan"] if s["pr"] == "Candidate persistence contract"
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


def test_governance_invariants_distinguish_r1_and_r2_from_later_steps(inv: dict) -> None:
    """Invariants prove R1/R2 are Gary-approved while Steps 3-8 remain pending and broad booleans are false."""
    invariants = inv["governance_invariants"]
    # 1. No invariant claims EVERY rollout step remains pending.
    assert not any(
        "each rollout implementation step remains pending" in g.lower() for g in invariants
    )
    assert not any(
        "every rollout implementation step remains pending" in g.lower() for g in invariants
    )

    # 2. Invariant accurately distinguishes R1 and R2 from Steps 3-8.
    r_invariant = next(
        (g for g in invariants if "MVP-ARCH-001-R1" in g and "MVP-ARCH-001-R2" in g),
        None,
    )
    assert r_invariant is not None, "Missing R1/R2 governance invariant"
    assert "design-only" in r_invariant.lower()
    assert "separately gary-approved" in r_invariant.lower()
    assert re.search(r"steps 3[\u2013-]8 remain pending", r_invariant, re.IGNORECASE)
    assert "does not authorize production trading changes" in r_invariant.lower()

    # 3. Markdown matches the JSON invariant.
    md_text = MD_PATH.read_text(encoding="utf-8")
    assert not re.search(
        r"each rollout implementation step remains pending", md_text, re.IGNORECASE
    )
    assert "MVP-ARCH-001-R1" in md_text
    assert "MVP-ARCH-001-R2" in md_text

    # 4. Broad authorization booleans remain false.
    auth = inv["authorization"]
    for key, value in auth.items():
        assert value is False, f"authorization.{key}={value}"


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

    # The recommended work order says no implementation is authorized.
    assert "no mvp-arch-001 implementation" in work_order.lower()
    assert "LONG-002C" in work_order
    assert "DAYTRADE-001" in work_order
    assert "no product or research implementation pr is currently authorized" in pr_order.lower()
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
    """The JSON records Gary's scoped approvals for MVP-ARCH-001-R1 and R2 without broad booleans."""
    approvals = inv.get("rollout_approvals", [])
    assert len(approvals) >= 2
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
