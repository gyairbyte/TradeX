"""Specification and governance boundary tests for LONG-002E2."""

from __future__ import annotations

from typing import Any

import pytest

from tradex.research.long_002e2.spec import (
    ALLOWED_DISPOSITIONS,
    ALLOWED_RECOMMENDED_ACTIONS,
    BASE_GIT_SHA,
    DEV_END,
    DEV_START,
    E1_CORRECTED_RUN_ID,
    E1_PREDICTION_PATH,
    E1_SAFE_ARTIFACT_HASHES,
    E1_SAFE_ARTIFACTS_DIR,
    EVALUATION_SESSIONS_COUNT,
    EXPECTED_D1_FEATURE_TABLE_SHA256,
    EXPECTED_E1_PREDICTION_SHA256,
    EXPECTED_PREDICTION_ROW_COUNT,
    EXPECTED_SPEC_SHA256,
    EXPECTED_STAGE_C_BASELINE_SHA256,
    FROZEN_FEATURES,
    LOCALIZATION_THRESHOLD,
    POPULATION_CUTOFF,
    REPO_ROOT,
    REPRESENTATIVE_CONFIGURATION_ID,
    REPRESENTATIVE_SELECTION_BASIS,
    SPEC_PATH,
    TASK_ID,
    UPSTREAM_SPECS,
    compute_file_sha256,
    load_e2_spec,
    verify_e2_spec_hash,
)
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES


@pytest.fixture(scope="module")
def e2_spec() -> dict[str, Any]:
    return load_e2_spec()


# --- Requirement 1: E2 spec hash verified ---
def test_01_e2_spec_hash_verified() -> None:
    assert SPEC_PATH.exists()
    computed = compute_file_sha256(SPEC_PATH)
    assert computed == EXPECTED_SPEC_SHA256
    verify_e2_spec_hash()


# --- Requirement 2: Original E1 spec hash unchanged ---
def test_02_original_e1_spec_hash_unchanged() -> None:
    path, expected_hash = UPSTREAM_SPECS["LONG-002E1-v1.json"]
    assert path.exists()
    computed = compute_file_sha256(path)
    assert computed == expected_hash


# --- Requirement 3: E1 correction spec hash unchanged ---
def test_03_e1_correction_spec_hash_unchanged() -> None:
    path, expected_hash = UPSTREAM_SPECS["LONG-002E1-CORR-001-v1.json"]
    assert path.exists()
    computed = compute_file_sha256(path)
    assert computed == expected_hash


# --- Requirement 4: Representative configuration is exactly LOGIT_S4_C300 ---
def test_04_representative_configuration_is_logit_s4_c300(e2_spec: dict[str, Any]) -> None:
    rep = e2_spec["representative_configuration"]
    assert rep["configuration_id"] == "LOGIT_S4_C300"
    assert rep["configuration_id"] == REPRESENTATIVE_CONFIGURATION_ID
    assert rep["family"] == "regularized_probabilistic"
    assert rep["feature_subset_id"] == "S4"


# --- Requirement 5: Selection basis is locked E1 ordering ---
def test_05_selection_basis_is_locked_e1_ordering(e2_spec: dict[str, Any]) -> None:
    rep = e2_spec["representative_configuration"]
    assert rep["selection_basis"] == "best_by_locked_LONG_002E1_ordering"
    assert rep["selection_basis"] == REPRESENTATIVE_SELECTION_BASIS
    assert rep.get("not_a_new_model_configuration") is True


# --- Requirement 6: No new model configuration registry exists ---
def test_06_no_new_model_configuration_registry_exists(e2_spec: dict[str, Any]) -> None:
    assert "configuration_registry" not in e2_spec
    no_fit = e2_spec.get("no_new_model_fitting", {})
    assert no_fit.get("empirical_model_fitting_prohibited") is True
    assert "LogisticRegression.fit" in no_fit.get("prohibited_calls", [])
    assert "HistGradientBoostingClassifier.fit" in no_fit.get("prohibited_calls", [])
    assert "StandardScaler.fit" in no_fit.get("prohibited_calls", [])


# --- Requirement 7: Search budget stays 36 consumed / 12 unused ---
def test_07_search_budget_stays_36_consumed_12_unused(e2_spec: dict[str, Any]) -> None:
    budget = e2_spec["search_budget"]
    assert budget["total_long_002e_budget"] == 48
    assert budget["material_configurations_consumed_before"] == 36
    assert budget["material_configurations_consumed_after"] == 36
    assert budget["remaining_long_002e_budget"] == 12


# --- Requirement 8: Round 2 unauthorized ---
def test_08_round_2_unauthorized(e2_spec: dict[str, Any]) -> None:
    budget = e2_spec["search_budget"]
    assert budget["round2_authorized"] is False
    assert budget["requires_separate_assignment"] is True


# --- Requirement 9 & 69: Production unchanged, APPROVED_PRODUCTION_STRATEGIES == () ---
def test_09_production_unchanged_and_empty_strategies(e2_spec: dict[str, Any]) -> None:
    prod = e2_spec["production_boundary"]
    assert prod["production_promotion_eligible"] is False
    assert prod["production_change_authorized"] is False
    assert prod["production_trading_logic_modified"] is False
    assert prod["approved_production_strategies"] == []
    assert APPROVED_PRODUCTION_STRATEGIES == ()


# --- Requirements 10, 11, 12, 13: Expected input hashes and paths in spec ---
def test_10_through_13_input_hashes_and_artifacts(e2_spec: dict[str, Any]) -> None:
    inputs = e2_spec["required_input_artifacts"]
    assert inputs["e1_representative_prediction_parquet"]["sha256"] == EXPECTED_E1_PREDICTION_SHA256
    assert inputs["e1_representative_prediction_parquet"]["expected_row_count"] == EXPECTED_PREDICTION_ROW_COUNT
    assert inputs["d1_feature_table"]["sha256"] == EXPECTED_D1_FEATURE_TABLE_SHA256
    assert inputs["stage_c_baseline_comparator_outputs"]["sha256"] == EXPECTED_STAGE_C_BASELINE_SHA256

    assert E1_SAFE_ARTIFACTS_DIR.exists()
    assert E1_CORRECTED_RUN_ID == "LONG-002E1-20261006_152832"
    for filename, expected_hash in E1_SAFE_ARTIFACT_HASHES.items():
        artifact_path = E1_SAFE_ARTIFACTS_DIR / filename
        assert artifact_path.exists(), f"Missing E1 safe artifact {filename}"
        assert compute_file_sha256(artifact_path) == expected_hash, f"Hash mismatch for {filename}"


# --- Requirements 16, 17, 18, 19, 20: Quarantines, Dates, and Cutoff ---
def test_16_through_20_quarantines_and_population(e2_spec: dict[str, Any]) -> None:
    q = e2_spec["quarantine_and_governance"]
    assert q["validation_access_authorized"] is False
    assert q["validation_period"]["status"] == "quarantined_unopened"
    assert q["holdout_access_authorized"] is False
    assert q["holdout_period"]["status"] == "quarantined_unopened"
    assert q["shadow_access_authorized"] is False
    assert q["shadow_period"]["status"] == "quarantined_unopened"
    assert q["zero_provider_calls"] is True

    pop = e2_spec["common_evaluation_population"]
    assert pop["cutoff_time"] == "20:30"
    assert pop["cutoff_time"] == POPULATION_CUTOFF
    assert pop["start_date"] == DEV_START
    assert pop["end_date"] == DEV_END
    assert pop["evaluation_dates_count"] == EVALUATION_SESSIONS_COUNT
    assert pop["expected_observation_count"] == EXPECTED_PREDICTION_ROW_COUNT


# --- Requirement 46: Frozen 8 predictive features ---
def test_46_frozen_eight_features(e2_spec: dict[str, Any]) -> None:
    expected_8 = [
        "return_5",
        "atr_pct_14",
        "return_20",
        "return_60",
        "close_vs_sma20",
        "close_vs_sma60",
        "sma20_slope_5",
        "relative_volume_20",
    ]
    assert e2_spec["frozen_features"] == expected_8
    assert FROZEN_FEATURES == expected_8


# --- Requirements 55, 56, 57, 58, 59: Decision Logic and Localization rules ---
def test_55_through_59_localization_decision_rules(e2_spec: dict[str, Any]) -> None:
    rules = e2_spec["localization_and_decision_rules"]
    assert rules["localization_threshold"] == 0.60
    assert LOCALIZATION_THRESHOLD == 0.60
    assert set(rules["allowed_diagnostic_dispositions"]) == set(ALLOWED_DISPOSITIONS)
    assert set(rules["allowed_recommended_next_actions"]) == set(ALLOWED_RECOMMENDED_ACTIONS)
    assert len(rules["allowed_diagnostic_dispositions"]) == 3
    assert TASK_ID == "LONG-002E2-LOGISTIC-STABILITY-DIAGNOSTIC-001"
    assert BASE_GIT_SHA == "58df7d468d7175264758a997a7a9c701c7f8d369"
    assert REPO_ROOT.exists()
    assert E1_PREDICTION_PATH.as_posix() == (
        "data/research/long_002e1/LONG-002E1-20261006_152832/"
        "predictions_regularized_probabilistic_LOGIT_S4_C300.parquet"
    )
