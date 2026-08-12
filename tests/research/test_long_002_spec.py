"""Deterministic, credential-free tests for the LONG-002 locked research contract.

These tests validate the machine-readable specification in
``docs/research/specs/LONG-002-v1.json``. They do not access market data,
providers, or validation/holdout outcomes.
"""

from __future__ import annotations

import json
import re
from datetime import date
from itertools import product
from pathlib import Path

import pytest

SPEC_PATH = Path("docs/research/specs/LONG-002-v1.json")
MD_PATH = Path("docs/research/LONG-002.md")


@pytest.fixture(scope="module")
def spec() -> dict:
    with SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def long_002_md_text() -> str:
    return MD_PATH.read_text(encoding="utf-8")


def test_spec_json_parses_and_is_json_safe(spec: dict) -> None:
    """JSON parses and serializes without NaN/Infinity."""
    json.dumps(spec, allow_nan=False)


def test_study_identity_and_version(spec: dict) -> None:
    assert spec["task_id"] == "LONG-002"
    assert spec["spec_version"] == 1
    assert spec["spec_name"].startswith("LONG-002:")
    assert spec["classification"] == "research-only"
    assert spec["production_promotion_eligible"] is False
    assert spec["status"] == "pre_registered_not_executed"


def test_historical_periods_are_locked_and_non_overlapping(spec: dict) -> None:
    periods = spec["historical_periods"]
    for split in ("warmup", "development", "validation", "holdout"):
        assert split in periods
        assert "start" in periods[split]
        assert "end" in periods[split]

    warmup = periods["warmup"]
    dev = periods["development"]
    val = periods["validation"]
    hold = periods["holdout"]

    assert date.fromisoformat(warmup["start"]) < date.fromisoformat(warmup["end"])
    assert date.fromisoformat(dev["start"]) < date.fromisoformat(dev["end"])
    assert date.fromisoformat(val["start"]) < date.fromisoformat(val["end"])
    assert date.fromisoformat(hold["start"]) < date.fromisoformat(hold["end"])

    assert date.fromisoformat(warmup["end"]) < date.fromisoformat(dev["start"])
    assert date.fromisoformat(dev["end"]) < date.fromisoformat(val["start"])
    assert date.fromisoformat(val["end"]) < date.fromisoformat(hold["start"])
    assert periods["holdout"]["untouched"] is True


def test_target_grid_contains_all_nine_targets(spec: dict) -> None:
    targets = spec["outcome_and_entry_contract"]["target_grid"]["all_nine_targets_must_be_calculated"]
    got = {(t["target_pct"], t["horizon_sessions"]) for t in targets}
    expected = set(product([10, 20, 30], [5, 10, 21]))
    assert got == expected


def test_primary_endpoint_and_only_fallback(spec: dict) -> None:
    hierarchy = spec["outcome_and_entry_contract"]["confirmatory_hierarchy"]
    primary = hierarchy["primary"]
    assert primary["target_pct"] == 10
    assert primary["horizon_sessions"] == 10

    fallback = hierarchy["feasibility_fallback"]
    assert fallback["target_pct"] == 10
    assert fallback["horizon_sessions"] == 21


def test_universe_eligibility_matches_contract(spec: dict) -> None:
    eligibility = spec["eligibility_defaults"]
    assert eligibility["market_cap"]["non_index_floor_usd"] == 3_000_000_000
    assert eligibility["market_cap"]["default_floor_usd"] == 3_000_000_000
    assert eligibility["price"]["current_close_min_usd"] == 5
    assert eligibility["price"]["prior_20_session_median_close_min_usd"] == 5
    assert eligibility["liquidity"]["prior_20_session_median_dollar_volume_min_usd"] == 20_000_000
    assert eligibility["liquidity"]["prior_60_session_median_dollar_volume_min_usd"] == 10_000_000
    assert eligibility["trading_history"]["established_min_sessions"] == 252
    assert eligibility["trading_history"]["recent_ipo_min_sessions"] == 63


def test_display_caps_exactly_7_12_12(spec: dict) -> None:
    display = spec["display_contract"]
    assert display["max_enter_now"] == 7
    assert display["max_armed"] == 12
    assert display["max_qualified_waitlist"] == 12


def test_snapshot_cutoffs_are_20_30_and_09_00_america_new_york(spec: dict) -> None:
    cutoffs = spec["snapshot_cutoffs"]
    assert cutoffs["timezone"] == "America/New_York"
    assert cutoffs["evening_snapshot"]["time"] == "20:30"
    assert cutoffs["morning_snapshot"]["time"] == "09:00"


def test_primary_transaction_cost_scenarios(spec: dict) -> None:
    costs = spec["transaction_costs"]
    assert costs["primary_scenario_bps_per_side"] == 10
    assert sorted(costs["sensitivity_scenarios_bps_per_side"]) == [5, 25]
    assert costs["stress_diagnostic_bps_per_side"] == 50


def test_allowed_model_families_are_only_three_locked(spec: dict) -> None:
    families = spec["allowed_model_families"]["allowlist"]
    ids = {f["id"] for f in families}
    assert ids == {
        "cross_sectional_rank_score",
        "regularized_probabilistic_time_to_event",
        "shallow_strongly_regularized_gbdt",
    }


def test_model_search_budget_is_36_plus_12(spec: dict) -> None:
    budget = spec["allowed_model_families"]["search_budget"]
    round1 = budget["round_1"]
    round2 = budget["round_2"]
    assert round1["max_material_configurations_per_family"] == 12
    assert round1["max_total_material_configurations"] == 36
    assert round2["max_additional_material_configurations_across_all_families"] == 12
    assert budget["initial_total_max"] == 48


def test_trigger_budget_is_12_non_control(spec: dict) -> None:
    assert spec["trigger_families"]["search_budget"]["max_material_non_control_configurations"] == 12


def test_m1_and_m2_budgets_are_8_each(spec: dict) -> None:
    stop_exit = spec["stop_and_exit_management"]
    assert stop_exit["m1_downside_invalidation_research"]["max_material_configurations"] == 8
    assert stop_exit["m2_profit_exit_research"]["max_material_configurations"] == 8
    assert stop_exit["m2_profit_exit_research"]["normal_lifetime_sessions"] == 21


def test_shadow_burn_in_and_minimums(spec: dict) -> None:
    shadow = spec["prospective_shadow_contract"]
    assert shadow["burn_in"]["sessions"] == 10
    assert shadow["burn_in"]["excluded"] is True
    assert shadow["official_minimum"]["sessions"] == 126
    assert shadow["official_minimum"]["min_unique_actionable_recommendation_episodes"] == 50
    assert shadow["official_minimum"]["min_mechanically_executable_shadow_entries"] == 30
    assert shadow["snapshot_completion_target_pct"] == 99


def test_no_numerical_values_for_deferred_gates(spec: dict) -> None:
    """Deferred qualification/performance gates must not silently contain numbers.

    Exact numerical advancement thresholds and sample-count gates are deferred to
    development-only evidence; the JSON must not invent them.
    """
    for item in spec["deferred_decisions"]["items"]:
        assert item["status"] == "deferred"
        assert "when_decided" in item
        assert "data_may_be_used" in item

    # actual_minimums block is explicitly deferred
    assert spec["statistical_evidence_and_uncertainty"]["actual_minimums"]["status"] == "deferred"

    # advance/disposition exact thresholds are deferred
    assert spec["advancement_disposition_framework"]["exact_thresholds_deferred"]


def test_this_pr_makes_no_provider_calls(spec: dict) -> None:
    assert spec["data_provider_governance"]["this_pr_makes_zero_provider_calls"] is True
    assert spec["data_provider_governance"]["this_pr_makes_zero_provider_selection"] is True
    assert spec["production_boundary"]["this_pr_changes_production_code"] is False
    assert spec["production_boundary"]["this_pr_changes_trading_behavior"] is False
    assert spec["production_boundary"]["this_pr_retrieves_real_market_data"] is False
    assert spec["production_boundary"]["this_pr_evaluates_historical_outcomes"] is False
    assert spec["production_boundary"]["this_pr_accesses_validation_or_holdout"] is False


def test_spec_file_is_deterministic_relative_path() -> None:
    assert SPEC_PATH.is_file()
    assert SPEC_PATH.suffix == ".json"


def test_production_progression_requires_long_002j_then_separate_pr(spec: dict) -> None:
    """The promotion gate is exactly: I -> J prospectively_supported -> separate PR."""
    prod_boundary = spec["production_boundary"]["production_promotion_requires"].lower()
    # LONG-002I does not authorize production; it authorizes only the J shadow.
    assert "long-002i" in prod_boundary
    assert "long-002j" in prod_boundary
    assert "prospectively supported" in prod_boundary or "prospectively_supported" in prod_boundary
    assert "separate" in prod_boundary
    assert "gary-approved" in prod_boundary
    assert prod_boundary.index("long-002j") > prod_boundary.index("long-002i")
    assert "production" in prod_boundary.split("long-002j")[-1]

    shadow_note = spec["prospective_shadow_contract"]["prospective_support_authorizes_only_consideration"].lower()
    assert "prospectively_supported" in shadow_note or "prospectively supported" in shadow_note
    assert "long-002j" in shadow_note
    assert "separate" in shadow_note
    assert "gary-approved" in shadow_note
    assert "does not by itself authorize production deployment" in shadow_note
    assert "long-002i" in shadow_note
    assert "prospective shadow" in shadow_note
    assert "not production promotion" in shadow_note
    assert "authorizes only the" in shadow_note

    i_desc = spec["phased_program"]["LONG-002I"]["description"].lower()
    assert "authorizes only long-002j prospective shadow" in i_desc
    assert "not production deployment" in i_desc

    j_desc = spec["phased_program"]["LONG-002J"]["description"].lower()
    assert "prospectively supported" in j_desc or "prospectively_supported" in j_desc
    assert "authorizes only consideration of a separate" in j_desc
    assert "gary-approved" in j_desc
    assert "production" in j_desc


def test_universe_exclusions_are_complete(spec: dict) -> None:
    exclusions = set(spec["universe"]["exclusions"])
    required = {
        "OTC",
        "warrant",
        "right",
        "unit",
        "preferred_stock",
        "ETN",
        "closed_end_fund",
        "pre_merger_spac",
        "shell_company",
        "other_structurally_incomparable_securities",
    }
    assert required.issubset(exclusions)


def test_universe_and_pit_invariants(spec: dict) -> None:
    universe = spec["universe"]
    assert universe["primary_security_types"] == ["U.S.-listed operating-company common stocks"]
    assert universe["index_membership_is_not_a_predictor"] is True
    assert "not primary stock candidates" in universe["etf_usage"].lower()

    policy = universe["pit_constituent_policy"]
    assert policy["use_best_reliable_point_in_time_membership"] is True
    assert policy["never_substitute_current_membership_as_historical_fact"] is True
    assert policy["document_survivorship_and_constituent_limitations"] is True
    assert policy["perfect_pit_constituent_history_not_a_hard_blocker"] is True
    assert policy["apply_to_index_membership_aids"] is True


def test_validation_tie_break_order_is_exactly_six_steps(spec: dict) -> None:
    ranking = spec["ranking_objective"]
    tie_break = ranking["validation_tie_break_order"]
    assert len(tie_break) == 6
    expected_order = [
        "pass_all_risk_actionability_calibration_sample_gates",
        "highest_clean_target_precision_at_locked_top_k",
        "highest_expected_clean_move_value_at_same_k",
        "lower_adverse_rate",
        "better_calibration",
        "simpler_more_explainable_when_materially_similar",
    ]
    assert [t["criterion"] for t in tie_break] == expected_order
    for i, t in enumerate(tie_break, start=1):
        assert t["step"] == i


def test_expected_clean_move_value_formula_and_speed_treatment(spec: dict) -> None:
    ecvm = spec["ranking_objective"]["expected_clean_move_value"]
    assert ecvm["operates_on_mutually_exclusive_highest_target_tiers"] is True
    assert ecvm["capped_at"] == 30
    formula = ecvm["formula"]
    # Mutually exclusive weighted highest-tier formula.
    assert "10%" in formula
    assert "20%" in formula
    assert "30%" in formula
    assert "P(" in formula
    assert "highest clean tier" in formula
    # The formula is a weighted sum of three mutually exclusive highest-tier probabilities.
    assert formula.startswith("10% * P(")
    assert "+ 20% * P(" in formula
    assert "+ 30% * P(" in formula

    speed = ecvm["speed_preference_and_discount"].lower()
    assert "frozen before validation" in speed
    assert "not tuned post-hoc" in speed


def test_primary_metrics_are_complete_and_locked(spec: dict) -> None:
    primary = set(spec["ranking_objective"]["primary_metrics"])
    expected = {
        "clean_target_precision_at_10",
        "clean_target_precision_at_25",
        "expected_clean_move_value_at_10",
        "expected_clean_move_value_at_25",
        "adverse_rate",
        "calibration",
        "actionability",
        "time_to_target",
        "lift_over_strongest_simple_baseline",
        "opportunities_per_week",
        "product_diagnostics_at_7_12_31",
    }
    assert primary == expected
    assert spec["ranking_objective"]["candidate_feature_families_are_hypotheses_not_assumed_signals"] is True


def test_blinded_review_frozen_label_schema_is_complete(spec: dict) -> None:
    schema = spec["blinded_chart_review_protocol"]["main_sample"]["frozen_label_schema"]
    expected_keys = {
        "surface_decision",
        "visible_state_if_surfaced",
        "expected_target_and_horizon",
        "qualitative_confidence",
        "setup_archetype",
        "entry_plan",
        "trigger_zone",
        "max_five_session_validity",
        "gap_handling",
        "invalidation",
        "max_three_primary_positive_reasons",
        "material_risks_and_counterarguments",
        "preserve_stage_a_and_b_labels_independently",
    }
    assert set(schema.keys()) == expected_keys

    assert set(schema["surface_decision"]) == {"surface", "do_not_surface"}
    assert set(schema["visible_state_if_surfaced"]) == {"Enter Now", "Armed", "Qualified Waitlist"}
    assert schema["expected_target_and_horizon"] is True
    assert schema["qualitative_confidence"] == "1-5 scale"
    assert set(schema["setup_archetype"]) == {"setup_archetype", "other", "unclear"}
    for key in (
        "entry_plan",
        "trigger_zone",
        "max_five_session_validity",
        "gap_handling",
        "invalidation",
        "max_three_primary_positive_reasons",
        "material_risks_and_counterarguments",
        "preserve_stage_a_and_b_labels_independently",
    ):
        assert schema[key] is True


def test_provider_search_budget_and_governance_are_locked(spec: dict) -> None:
    gov = spec["data_provider_governance"]
    budget = gov["provider_search_budget"]
    assert budget["per_data_family"]["preferred_provider"] == 1
    assert budget["per_data_family"]["named_fallback_candidates_max"] == 2
    assert budget["bounded_retries_api_calls_runtime"] is True
    assert budget["no_silent_provider_switch"] is True
    assert "minimum usable data" in budget["stop_condition"].lower()
    assert "provider exploration stops" in budget["stop_condition"].lower()

    assert gov["additional_provider_hunting_requires_gary_approval"] is True
    assert gov["additional_provider_hunting_must_address_calculation_invalidating_blocker"] is True
    assert gov["this_pr_makes_zero_provider_calls"] is True
    assert gov["this_pr_makes_zero_provider_selection"] is True


def test_reference_position_notionals_are_locked_and_synced(spec: dict, long_002_md_text: str) -> None:
    notionals = spec["eligibility_defaults"]["live_execution_gates"]["reference_position_notionals_usd"]
    assert notionals["typical_min"] == 10_000
    assert notionals["typical_max"] == 20_000

    # The human contract must also state the $10K-$20K reference notional in the live execution gates section.
    section_match = re.search(
        r"### Live execution gates.*?(?=\n## |\n### |\Z)", long_002_md_text, re.DOTALL
    )
    assert section_match, "Live execution gates section not found in LONG-002.md"
    section = section_match.group(0)
    assert "10,000" in section or "$10K" in section
    assert "20,000" in section or "$20K" in section
    assert "reference" in section.lower()


def test_no_locked_future_artifact_list(spec: dict) -> None:
    """Future artifact filenames are not locked in LONG-002A."""
    assert "required_artifacts_for_future_phases" not in spec
    assert "future_artifacts_policy" in spec
    policy = spec["future_artifacts_policy"].lower()
    assert "non-binding" in policy or "illustrative" in policy


def test_recommendation_episode_lifecycle_is_deferred(spec: dict) -> None:
    episode = next(
        (item for item in spec["deferred_decisions"]["items"] if "recommendation episode lifecycle" in item["item"]),
        None,
    )
    assert episode is not None
    assert episode["status"] == "deferred"
    when = episode["when_decided"].lower()
    assert "before long-002e" in when
    assert "development-only" in when
    data = episode["data_may_be_used"].lower()
    assert "no validation/holdout" in data or "no validation" in data or "no holdout" in data
