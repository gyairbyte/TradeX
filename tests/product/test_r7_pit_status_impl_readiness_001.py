"""Product and governance tests for MVP-ARCH-001-R7-PIT-STATUS-IMPL-READINESS-001.

Validates:
1. Decision packet `decision.json` exists, loads, and satisfies all governance invariants:
   - task_id == "MVP-ARCH-001-R7-PIT-STATUS-IMPL-READINESS-001"
   - status == "ready_for_review"
   - base_commit == "024dfc2659cd64bb96aff91ae8d312b9c049ac52"
   - zero authorizations (production_status_semantics_change, schema_migration, provider_study,
     active_universe, c2_implementation, scheduler all False)
   - APPROVED_PRODUCTION_STRATEGIES == ()
   - candidate_b_status == "unselected" and candidate_c_status == "unselected"
   - selected_universe is None
2. Manifest Contract v2 requirements:
   - contract_version == 2
   - material fields include applicability; description is non-material
   - earnings applicability enum is ["required", "not_applicable"]
   - reference applicability enum is ["required"]
   - missing declaration policy is fail_closed
   - hardcoded ticker lists and provider inference are explicitly disallowed
3. Audit identity, versioned hashing, and idempotency:
   - universe_hash preserves exact historical symbol-set identity
   - v1 manifest_hash preserved 100% identically without applicability
   - v2 manifest_hash incorporates sorted applicability
   - request_fingerprint_v2 binds to manifest_hash without redundant raw applicability duplication
   - manifest_hash column constraint enforces NULL for v1 and NOT NULL for v2
   - cross-version conflicts fail closed
4. Schema v8 requirements:
   - all 4 PIT tables check contract_version IN (1, 2)
   - pit_capture_runs: nullable manifest_hash (NULL for v1, NOT NULL for v2), not_applicable_n, terminal count
   - pit_earnings_snapshots: observation_status IN ('known', 'not_applicable', 'unavailable', 'error'),
     observation_origin IN ('provider', 'manifest'), applicability_source, provider_call_attempted,
     nullable provider and request timestamps, mutual exclusion check
   - pit_reference_capture_runs: nullable manifest_hash, terminal count (known + unavailable + ambiguous + error),
     not_applicable_n not persisted (logically 0)
   - pit_reference_snapshots: minimal contract_version check update only, reference required
5. Historical Semantics:
   - historical v1 manifest_hash is NULL (never fabricated)
   - zero retrospective reinterpretation of v1 UNAVAILABLE observations
   - strict legacy evaluation preserved for v1
6. Operational Execution Health:
   - answers "Did TradeX execute reliably and truthfully record provider/domain evidence?"
   - run status SUCCEEDED when error_n == 0
   - slot health HEALTHY when both families have terminal SUCCEEDED runs
   - slot health DEGRADED when a run remains STARTED or partial error
   - slot health FAILED on missing run, conflict, total provider failure, fatal preflight, DB crash
   - stale run timeouts explicitly deferred
7. Evidence Completeness (Deterministic Count-Based):
   - no arbitrary 50% cutoff
   - applicable_n = requested_n - not_applicable_n
   - COMPLETE, PARTIAL, SPARSE defined deterministically by counts
   - slot aggregation: COMPLETE requires all expected families COMPLETE; SPARSE if any expected family has
     applicable_n > 0 and known_n == 0; otherwise PARTIAL
   - pooled ratio is informational only and never masks a sparse family
   - completeness tier never alters operational health or CLI exit codes
8. Provider-Call Behavior for NOT_APPLICABLE:
   - skip_provider_call model
   - zero network calls, provider is NULL, observation_origin is "manifest", provider_call_attempted is false
   - fact_json contains status_reason="manifest_not_applicable"
9. CLI Contract:
   - exit codes: 0 = healthy/not_due, 2 = degraded, 1 = failed
   - completeness impact on exit code is none
10. Migration Safety:
    - 12-step SQLite table rebuild inside single atomic transaction
    - row count verification for all 4 tables
    - foreign key checks, idempotency, rollback
11. PR Decomposition:
    - PR A, PR B, PR C with bounded scopes
12. Markdown Specification:
    - R7-PIT-STATUS-IMPL-READINESS-001.md exists and contains all required sections.
"""
from __future__ import annotations

import json
from pathlib import Path

from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / "docs" / "product" / "artifacts" / "r7-pit-status-impl-readiness-001"
DECISION_JSON = ARTIFACTS_DIR / "decision.json"
READINESS_MD = REPO_ROOT / "docs" / "product" / "R7-PIT-STATUS-IMPL-READINESS-001.md"


def test_decision_json_exists_and_loads() -> None:
    """Verify decision.json exists and is valid JSON."""
    assert ARTIFACTS_DIR.exists(), f"Artifacts directory missing: {ARTIFACTS_DIR}"
    assert DECISION_JSON.exists(), f"decision.json missing: {DECISION_JSON}"

    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    assert isinstance(packet, dict)
    assert packet["task_id"] == "MVP-ARCH-001-R7-PIT-STATUS-IMPL-READINESS-001"
    assert packet["status"] == "ready_for_review"
    assert packet["base_commit"] == "024dfc2659cd64bb96aff91ae8d312b9c049ac52"
    assert packet["architecture_direction"] == "option_2_plus_3"


def test_governance_invariants() -> None:
    """Verify strict zero-authorization invariants and unselected universes."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    gov = packet["governance_invariants"]
    assert gov["production_status_semantics_change_authorized"] is False
    assert gov["schema_migration_authorized"] is False
    assert gov["provider_study_authorized"] is False
    assert gov["active_universe_authorized"] is False
    assert gov["c2_implementation_authorized"] is False
    assert gov["scheduler_authorized"] is False
    assert gov["approved_production_strategies"] == []
    assert gov["r7_status"] == "incomplete"
    assert gov["candidate_b_status"] == "unselected"
    assert gov["candidate_c_status"] == "unselected"
    assert gov["selected_universe"] is None

    # Registry invariant
    assert APPROVED_PRODUCTION_STRATEGIES == ()


def test_manifest_contract_v2_specification() -> None:
    """Verify Manifest Contract v2 specifications."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    m = packet["manifest_contract_v2"]
    assert m["contract_version"] == 2
    assert "applicability" in m["material_fields"]
    assert "description" in m["non_material_fields"]
    assert m["applicability_structure"] == "per_symbol_family_mapping"
    assert set(m["supported_families"]) == {"earnings", "reference"}
    assert set(m["earnings_applicability_enum"]) == {"required", "not_applicable"}
    assert set(m["reference_applicability_enum"]) == {"required"}
    assert m["missing_declaration_policy"] == "fail_closed"
    assert m["v1_compatibility_policy"] == "synthesize_required"
    assert m["hardcoded_ticker_rules_allowed"] is False
    assert m["infer_from_provider_allowed"] is False


def test_audit_identity_and_versioned_hashing() -> None:
    """Verify exact versioned manifest hashing, universe hashing, and drift checks."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    audit = packet["audit_identity_and_drift_model"]
    assert audit["universe_hash_historical_meaning_preserved"] is True
    assert "contract_version': 1" in audit["v1_manifest_hash_definition"]
    assert "applicability" not in audit["v1_manifest_hash_definition"]
    assert "contract_version': 2" in audit["v2_manifest_hash_definition"]
    assert "applicability" in audit["v2_manifest_hash_definition"]

    # Request fingerprint v2 incorporates manifest_hash
    assert "manifest_hash" in audit["capture_request_fingerprint_v2"]
    assert "contract_version': 2" in audit["capture_request_fingerprint_v2"]

    # Drift checks
    assert audit["drift_checks"]["symbol_drift"] == "fail_closed_universe_conflict"
    assert audit["drift_checks"]["manifest_drift"] == "fail_closed_manifest_conflict"
    assert audit["drift_checks"]["cross_version_conflict"] == "fail_closed_manifest_conflict"


def test_schema_v8_table_and_contract_constraints() -> None:
    """Verify Schema v8 specifications across all 4 PIT tables."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    s = packet["schema_v8_specification"]
    assert s["schema_version"] == 8
    assert s["pit_capture_contract_version"] == 2

    # All 4 tables accept contract_version IN (1, 2)
    tbl_checks = s["table_contract_version_constraints"]
    for tbl in [
        "pit_capture_runs",
        "pit_earnings_snapshots",
        "pit_reference_capture_runs",
        "pit_reference_snapshots",
    ]:
        assert tbl_checks[tbl] == "CHECK (contract_version IN (1, 2))"

    # pit_capture_runs changes
    cr = s["pit_capture_runs_changes"]
    assert "contract_version = 1 AND manifest_hash IS NULL" in cr["manifest_hash_constraint"]
    assert "contract_version = 2 AND manifest_hash IS NOT NULL" in cr["manifest_hash_constraint"]
    assert "known_n + not_applicable_n + unavailable_n + error_n" in cr["terminal_count_constraint"]

    # pit_earnings_snapshots changes
    es = s["pit_earnings_snapshots_changes"]
    assert "not_applicable" in es["observation_status_constraint"]
    assert "observation_origin" in es
    assert "applicability_source" in es
    assert "provider_call_attempted" in es
    assert "provider IS NULL" in es["provenance_mutual_exclusion_check"]
    assert "observation_origin = 'manifest'" in es["provenance_mutual_exclusion_check"]
    assert "observation_origin = 'provider'" in es["provenance_mutual_exclusion_check"]

    # pit_reference_capture_runs changes
    rcr = s["pit_reference_capture_runs_changes"]
    assert "contract_version = 1 AND manifest_hash IS NULL" in rcr["manifest_hash_constraint"]
    assert "contract_version = 2 AND manifest_hash IS NOT NULL" in rcr["manifest_hash_constraint"]
    assert "known_n + unavailable_n + ambiguous_n + error_n" in rcr["terminal_count_constraint"]
    assert rcr["not_applicable_n_persisted"] is False

    # pit_reference_snapshots changes
    rs = s["pit_reference_snapshots_changes"]
    assert rs["not_applicable_supported"] is False
    assert rs["origin_columns_needed"] is False


def test_historical_v1_handling_no_reinterpretation() -> None:
    """Verify historical v1 rows are protected from semantic reinterpretation and fabricated sentinels."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    h = packet["historical_v1_handling"]
    assert h["policy"] == "versioned_bifurcation_zero_reinterpretation"
    assert h["v1_manifest_hash_persisted"] is None
    assert h["v1_observations_reinterpretation"] is False
    assert h["v1_drift_guard"] == "legacy_universe_hash_only"
    assert h["v1_health_evaluation"] == "strict_legacy_all_known"


def test_operational_execution_health_model() -> None:
    """Verify operational health answers reliability, not evidence abundance."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    health = packet["operational_execution_health_model"]
    assert "Did TradeX execute reliably and truthfully record provider/domain evidence?" in health["core_question"]
    assert "Did TradeX obtain every desired fact?" in health["does_not_answer"]
    assert health["stale_run_timeout"] == "explicitly_deferred"

    lifecycle = health["run_status_lifecycle"]
    assert "error_n == 0" in lifecycle["succeeded"]
    assert "0 < error_n < requested_n" in lifecycle["partial"]
    assert "error_n == requested_n" in lifecycle["failed"]

    tt = health["slot_health_truth_table"]
    assert "Non-trading day" in tt["not_due"]
    assert "error_n == 0 for both" in tt["healthy"]
    assert "remains STARTED" in tt["degraded"]
    assert "PARTIAL run" in tt["degraded"]
    assert "MISSING" in tt["failed"]
    assert "universe conflict" in tt["failed"].lower()


def test_evidence_completeness_deterministic_count_model() -> None:
    """Verify evidence completeness uses deterministic count semantics without arbitrary percentage thresholds."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    comp = packet["evidence_completeness_model"]
    earnings = comp["family_level"]["earnings"]
    assert earnings["applicable_n_formula"] == "requested_n - not_applicable_n"
    assert earnings["all_not_applicable_tier"] == "COMPLETE"
    assert earnings["all_known_tier"] == "COMPLETE"
    assert earnings["some_known_tier"] == "PARTIAL"
    assert earnings["zero_known_tier"] == "SPARSE"

    ref = comp["family_level"]["reference"]
    assert ref["logical_not_applicable_n"] == 0
    assert ref["all_known_tier"] == "COMPLETE"
    assert ref["some_known_tier"] == "PARTIAL"
    assert ref["zero_known_tier"] == "SPARSE"

    slot = comp["slot_level_aggregation"]
    assert "All expected families are COMPLETE" in slot["complete_condition"]
    assert "applicable_n > 0 and known_n == 0" in slot["sparse_condition"]
    assert slot["pooled_ratio_role"] == "informational_only"

    # Operational independence
    assert "NEVER alters operational health" in comp["operational_independence"]


def test_not_applicable_truthful_provenance() -> None:
    """Verify NOT_APPLICABLE skips provider calls and records truthful manifest provenance."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    na = packet["not_applicable_provider_behavior"]
    assert na["model"] == "skip_provider_call"
    assert na["network_calls"] == 0
    assert na["latency_recorded"] is None
    assert na["provider"] is None
    assert na["observation_origin"] == "manifest"
    assert na["applicability_source"] == "manifest"
    assert na["provider_call_attempted"] is False
    assert "manifest_not_applicable" in na["fact_json"]


def test_cli_contract_exit_codes() -> None:
    """Verify CLI exit codes reflect operational execution health exclusively."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    cli = packet["cli_contract"]
    assert "healthy or not due" in cli["exit_codes"]["0"]
    assert "degradation" in cli["exit_codes"]["2"]
    assert "failure" in cli["exit_codes"]["1"]
    assert cli["completeness_impact_on_exit"] == "none"


def test_migration_safety_12_step_rebuild() -> None:
    """Verify Schema v7 to v8 migration specifications."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    mig = packet["migration_v7_to_v8"]
    assert mig["procedure"] == "12_step_sqlite_table_rebuild"
    assert mig["transaction_boundary"] == "single_atomic_transaction"
    assert mig["manifest_hash_backfill"] is None
    assert "strict_pre_and_post_equality" in mig["row_count_verification"]


def test_pr_decomposition() -> None:
    """Verify future implementation PR decomposition into PR A, PR B, and PR C."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    pr = packet["pr_decomposition"]
    assert "pr_a" in pr
    assert "pr_b" in pr
    assert "pr_c" in pr
    assert "Versioned applicability and persistence primitives" in pr["pr_a"]["name"]
    assert "Two-dimensional operational/read model semantics" in pr["pr_b"]["name"]
    assert "Universe selection / C2 activation" in pr["pr_c"]["name"]


def test_readiness_markdown_exists_and_contains_sections() -> None:
    """Verify R7-PIT-STATUS-IMPL-READINESS-001.md exists and contains all required sections."""
    assert READINESS_MD.exists(), f"Readiness markdown missing: {READINESS_MD}"
    content = READINESS_MD.read_text(encoding="utf-8")

    required_sections = [
        "1. Executive Summary & Objective",
        "2. Relationship to Upstream Packets",
        "3. Verified Starting State & Governance Invariants",
        "4. Core Contract 1: Manifest Applicability Contract (v2)",
        "5. Core Contract 2: Audit Identity and Drift Detection",
        "6. Core Contract 3: Schema v8 Specification",
        "7. Core Contract 4: Historical Semantics (Versioned Bifurcation)",
        "8. Core Contract 5: Operational Execution Health",
        "9. Core Contract 6: Evidence Completeness",
        "10. Core Contract 7: Provider-Call Behavior for NOT_APPLICABLE",
        "11. Core Contract 8: Capture-Run Lifecycle Compatibility",
        "12. Core Contract 9: CLI Contract",
        "13. Core Contract 10: Migration Safety & 12-Step Rebuild Procedure",
        "14. Candidate B and Candidate C Dispositions",
        "15. Bounded Future Implementation PR Decomposition",
        "16. Non-Authorizations & Governance Invariants",
    ]

    import re

    def _norm(s: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", " ", s).strip().lower()

    normalized_content = _norm(content)
    for s in required_sections:
        assert _norm(s) in normalized_content, f"Missing section: {s}"

    # Critical assertions
    assert "option_2_plus_3" in content
    assert "manifest_hash" in content
    assert "skip provider call" in content.lower()
    assert "12-step" in content.lower()
    assert "zero historical reinterpretation" in content.lower()
