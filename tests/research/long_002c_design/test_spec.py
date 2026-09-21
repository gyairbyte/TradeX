"""Deterministic, credential-free tests for LONG-002C-DESIGN-001.

Validates the machine-readable design specification and human-readable contract
without accessing live market data, providers, or validation/holdout records.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002C-design-v1.json"
MD_PATH = REPO_ROOT / "docs" / "research" / "LONG-002C-DESIGN.md"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def spec() -> dict:
    assert SPEC_PATH.exists(), f"Missing spec: {SPEC_PATH}"
    with SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def md_text() -> str:
    assert MD_PATH.exists(), f"Missing markdown document: {MD_PATH}"
    return MD_PATH.read_text(encoding="utf-8")


def test_json_parses_and_is_json_safe(spec: dict) -> None:
    """JSON parses and serializes without NaN/Infinity."""
    json_str = json.dumps(spec, allow_nan=False)
    assert len(json_str) > 0


def test_task_and_design_identity(spec: dict) -> None:
    """Task ID, program ID, version, and status match requirements."""
    assert spec["task_id"] == "LONG-002C-DESIGN-001"
    assert spec["program_id"] == "LONG-002"
    assert spec["design_version"] == 1
    assert spec["status"] == "proposed_for_gary_review"
    assert spec["classification"] == "research-governance-design-only"
    assert spec["base_commit_sha"] == "afa9b40d039e08df1a5edb1be21fb53ee8e0d9aa"


def test_all_upstream_spec_hashes_match(spec: dict) -> None:
    """All referenced upstream specification hashes match repository files."""
    hashes = spec["upstream_spec_hashes"]
    assert len(hashes) == 11
    for rel_path, expected_sha in hashes.items():
        file_path = REPO_ROOT / rel_path
        assert file_path.exists(), f"Upstream file missing: {rel_path}"
        actual_sha = _sha256(file_path)
        assert actual_sha == expected_sha, f"SHA mismatch for {rel_path}: expected {expected_sha}, got {actual_sha}"


def test_authorizations_are_strictly_false_except_design_work(spec: dict) -> None:
    """Design work is authorized; all execution/construction booleans are strictly false."""
    auth = spec["authorization"]
    assert auth["design_work_authorized"] is True
    assert "2026-09-20" in auth["design_work_authorization_source"]
    assert auth["long_002c_execution_authorized"] is False
    assert auth["dataset_construction_authorized"] is False
    assert auth["provider_calls_authorized"] is False
    assert auth["historical_outcome_analysis_authorized"] is False
    assert auth["validation_access_authorized"] is False
    assert auth["holdout_access_authorized"] is False
    assert auth["production_change_authorized"] is False
    assert auth["production_promotion_eligible"] is False


def test_historical_splits_are_preserved_and_quarantined(spec: dict) -> None:
    """Locked splits (2015, 2016-2020, 2021-2022, 2023-2025, 2026+) are preserved."""
    splits = spec["historical_splits"]
    assert splits["warmup"]["start"] == "2015-01-01"
    assert splits["warmup"]["end"] == "2015-12-31"
    assert splits["development"]["start"] == "2016-01-01"
    assert splits["development"]["end"] == "2020-12-31"
    assert splits["validation"]["start"] == "2021-01-01"
    assert splits["validation"]["end"] == "2022-12-31"
    assert splits["holdout"]["start"] == "2023-01-01"
    assert splits["holdout"]["end"] == "2025-12-31"
    assert splits["shadow_replay"]["start"] == "2026-01-01"


def test_validation_and_holdout_access_prohibited(spec: dict) -> None:
    """Validation and holdout access are strictly prohibited in LONG-002C."""
    splits = spec["historical_splits"]
    assert splits["validation"]["access_prohibited"] is True
    assert splits["holdout"]["access_prohibited"] is True
    assert splits["shadow_replay"]["access_prohibited"] is True
    assert spec["split_boundary_guard"]["fail_closed"] is True
    assert spec["split_boundary_guard"]["max_entry_window_sessions"] == 5
    assert spec["split_boundary_guard"]["max_outcome_horizon_sessions"] == 21
    assert spec["split_boundary_guard"]["total_forward_sessions_required"] == 26


def test_target_grid_contains_all_nine_combinations(spec: dict) -> None:
    """Target grid contains all nine mandatory target/horizon cells."""
    grid = spec["outcome_labeling_specification"]["target_grid"]
    assert len(grid) == 9
    expected = {
        (10, 5), (10, 10), (10, 21),
        (20, 5), (20, 10), (20, 21),
        (30, 5), (30, 10), (30, 21),
    }
    actual = {(item["target_pct"], item["horizon_sessions"]) for item in grid}
    assert actual == expected


def test_primary_endpoint_and_sole_feasibility_fallback(spec: dict) -> None:
    """Primary endpoint is clean +10%/10 and sole feasibility fallback is clean +10%/21."""
    hierarchy = spec["outcome_labeling_specification"]["confirmatory_hierarchy"]
    assert hierarchy["primary"]["target_pct"] == 10
    assert hierarchy["primary"]["horizon_sessions"] == 10
    assert hierarchy["feasibility_fallback"]["target_pct"] == 10
    assert hierarchy["feasibility_fallback"]["horizon_sessions"] == 21
    rule = hierarchy["feasibility_fallback"]["invocation_rule"].lower()
    assert "label-only development census" in rule
    assert "not depend on predictive model performance" in rule


def test_snapshot_cutoffs_are_20_30_and_09_00_america_new_york(spec: dict) -> None:
    """Cutoffs are 20:30 and 09:00 America/New_York on XNYS calendar."""
    cutoffs = spec["decision_observation_contract"]["cutoffs"]
    assert spec["decision_observation_contract"]["timezone"] == "America/New_York"
    assert spec["decision_observation_contract"]["exchange_calendar"] == "XNYS"
    assert cutoffs["evening"]["time"] == "20:30"
    assert cutoffs["morning"]["time"] == "09:00"


def test_security_fail_closed_unknown_policy_preserved(spec: dict) -> None:
    """Security classification unknown policy fails closed to exclusion."""
    entities = {e["entity_id"]: e for e in spec["dataset_manifest_architecture"]["entities"]}
    sec = entities["security_classification_status"]
    fields = sec["fields"]
    assert "provider_type_code" in fields
    assert "inferred_classification" in fields
    assert "classification_status" in fields
    assert "unknown_fail_closed" in fields["classification_status"]


def test_earnings_fail_closed_unknown_policy_preserved(spec: dict) -> None:
    """Earnings unknown policy marks observations unavailable for actionability."""
    rec = spec["status_separation_contract"]["earnings_unknown_census_recommendation"]
    action_rule = rec["actionability_census_rule"].lower()
    assert "actionability_unavailable_earnings_unknown" in action_rule
    assert "cannot qualify for enter now or armed" in action_rule


def test_status_separation_dimensions(spec: dict) -> None:
    """Status dimensions separate raw outcome, universe, completeness, earnings, actionability."""
    dims = spec["status_separation_contract"]["dimensions"]
    assert "raw_outcome_eligibility" in dims
    assert "universe_security_eligibility" in dims
    assert "data_completeness" in dims
    assert "earnings_schedule_knowledge" in dims
    assert "actionability_eligibility" in dims


def test_master_episode_21_session_nonrecursive_contract(spec: dict) -> None:
    """Master opportunity episodes enforce 21-session non-recursive windowing."""
    ep = spec["master_episodes_specification"]
    assert ep["window_duration_sessions"] == 21
    assert ep["no_recursive_extension"] is True
    assert "pre_target" in ep["constituent_tags"]
    assert "target_session" in ep["constituent_tags"]
    assert "post_target" in ep["constituent_tags"]
    assert "ex-post" in ep["ex_post_labeling_rule"].lower()


def test_baseline_families_and_volatility_50_50_weights(spec: dict) -> None:
    """Baseline families include all 6 locked comparators with 50/50 volatility weights."""
    baselines = spec["frozen_baseline_census"]["locked_comparator_families"]
    ids = {b["id"] for b in baselines}
    expected_ids = {
        "universe_base_rate",
        "simple_momentum",
        "spy_relative_momentum",
        "pit_sector_relative_momentum",
        "volatility_aware_momentum",
        "existing_tradex_long_term_scorer",
    }
    assert ids == expected_ids
    vol = next(b for b in baselines if b["id"] == "volatility_aware_momentum")
    assert "50%" in vol["weighting"]
    assert "fixed at 50/50" in vol["optimization_rule"].lower()


def test_legacy_scorer_uses_fresh_defaults_no_user_weights(spec: dict) -> None:
    """Legacy long-term scorer baseline uses fresh LongWeights() and no saved user weights."""
    baselines = spec["frozen_baseline_census"]["locked_comparator_families"]
    legacy = next(b for b in baselines if b["id"] == "existing_tradex_long_term_scorer")
    config = legacy["configuration"].lower()
    assert "fresh repository defaults" in config
    assert "longweights()" in config
    assert "no saved user weights" in config


def test_endpoint_feasibility_no_binomial_precommitment(spec: dict) -> None:
    """Feasibility procedure does not precommit to an i.i.d. binomial rule."""
    proc = spec["endpoint_feasibility_procedure"]
    principle = proc["principle"].lower()
    assert "no numerical sample gates or i.i.d. binomial rules are locked" in principle
    assert "dependence-aware" in principle
    steps_text = " ".join(proc["deterministic_steps"]).lower()
    assert "time-block resampling" in steps_text
    assert "independent master opportunity episodes" in steps_text
    assert "freeze the proposed numerical gates before any validation" in steps_text


def test_warmup_handling_does_not_confuse_missing_with_ipo(spec: dict) -> None:
    """Warmup specification preserves recent IPO cohort and marks shortfall as null."""
    warmup = spec["warmup_availability_specification"]["handling_policy"]
    assert "never be confused with a genuine recent ipo" in warmup["provider_missing_vs_ipo"].lower()
    assert "returns null" in warmup["feature_shortfall_null"].lower()
    assert "never backfilled as zero" in warmup["feature_shortfall_null"].lower()
    assert "unavailable_insufficient_lookback" in warmup["observation_availability"].lower()


def test_no_production_or_r7_files_in_design() -> None:
    """Design does not introduce or modify production or R7 code."""
    # Ensure no files under tradex/pit or tradex/strategies or production scorers are modified in git status
    import subprocess
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    changed_files = [line[3:].strip() for line in result.stdout.strip().splitlines() if line.strip()]
    for f in changed_files:
        assert not f.startswith("tradex/pit/"), f"R7 file modified: {f}"
        assert not f.startswith("tradex/strategies/"), f"Strategy registry modified: {f}"
        assert not f.startswith("tradex/signals/"), f"Production signal modified: {f}"
        assert not f.startswith("scripts/manage_pit_scheduler.ps1"), f"Scheduler script modified: {f}"


def test_markdown_design_exists_and_contains_invariants(md_text: str) -> None:
    """Markdown design document exists and contains core governance invariants."""
    assert "LONG-002C-DESIGN-001" in md_text
    assert "proposed_for_gary_review" in md_text
    assert "afa9b40d039e08df1a5edb1be21fb53ee8e0d9aa" in md_text
    assert "Master Opportunity Episodes" in md_text
    assert "Frozen Baseline Census" in md_text
    assert "Fail-Closed" in md_text or "fail-closed" in md_text
    assert "20:30 America/New_York" in md_text
    assert "09:00 America/New_York" in md_text
    lower = md_text.lower()
    assert "clean +10%" in lower
    assert "clean +20%" in lower
    assert "clean +30%" in lower
    assert "5, 10, 21" in md_text
