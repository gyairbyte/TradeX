"""Tests for LONG-002D2 specification schema and immutability."""
from __future__ import annotations

import json

from tradex.research.long_002d2.spec import (
    BOOTSTRAP_PRIMARY_BLOCK_SIZE,
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_ROBUSTNESS_BLOCK_SIZE,
    BOOTSTRAP_SEED,
    CHALLENGER_ID,
    DEV_END,
    DEV_START,
    EXPECTED_SPEC_SHA256,
    FROZEN_BASELINE_ID,
    POPULATION_CUTOFF,
    PRIMARY_CANDIDATE_ID,
    SPEC_PATH,
    TASK_ID,
    load_spec_payload,
    verify_spec_integrity,
)


def test_spec_file_exists() -> None:
    """Verify that the machine-readable specification file exists on disk."""
    assert SPEC_PATH.exists(), f"Spec file missing at {SPEC_PATH}"


def test_spec_integrity_hash() -> None:
    """Verify the SHA-256 digest of the spec file matches the locked hash."""
    computed = verify_spec_integrity()
    assert computed == EXPECTED_SPEC_SHA256


def test_spec_required_keys() -> None:
    """Verify that all required contract sections exist in the spec payload."""
    payload = load_spec_payload()

    assert payload["task_id"] == TASK_ID
    assert payload["program"] == "LONG-002"
    assert payload["phase"] == "LONG-002D2"
    assert payload["classification"] == "research_only"
    assert payload["production_promotion_eligible"] is False
    assert payload["approved_production_strategies"] == []

    # Authorization
    auth = payload["authorization"]
    assert auth["authorizer"] == "Gary Yang"
    assert auth["authorization_date"] == "2026-09-28"
    assert "validation_access" in auth["unauthorized_actions"]
    assert "production_promotion" in auth["unauthorized_actions"]

    # Upstream evidence
    upstream = payload["upstream_evidence"]
    assert upstream["stage_c"]["run_id"] == "2026-09-27-161243"
    assert upstream["stage_c"]["primary_cutoff"] == POPULATION_CUTOFF
    assert upstream["frozen_baseline"]["comparator_id"] == FROZEN_BASELINE_ID

    # Study population
    pop = payload["study_population"]
    assert pop["split"] == "development"
    assert pop["start_date"] == DEV_START
    assert pop["end_date"] == DEV_END
    assert pop["cutoff_time"] == POPULATION_CUTOFF
    assert pop["raw_outcome_eligible_required"] is True
    assert pop["split_boundary_purged_allowed"] is False

    # Candidates
    assert payload["primary_candidate"]["feature_id"] == PRIMARY_CANDIDATE_ID
    assert payload["primary_candidate"]["hypothesized_direction"] == "HIGHER"
    assert payload["secondary_challenger"]["feature_id"] == CHALLENGER_ID
    assert payload["secondary_challenger"]["hypothesized_direction"] == "HIGHER"

    # Regime diagnostic
    regime = payload["spy_regime_diagnostic"]
    assert regime["feature_id"] == "spy_return_20"
    assert len(regime["bins"]) == 3

    # Bootstrap configuration
    boot = payload["bootstrap_configuration"]
    assert boot["primary_block_size_sessions"] == BOOTSTRAP_PRIMARY_BLOCK_SIZE
    assert boot["robustness_block_size_sessions"] == BOOTSTRAP_ROBUSTNESS_BLOCK_SIZE
    assert boot["replicates"] == BOOTSTRAP_REPLICATES
    assert boot["seed"] == BOOTSTRAP_SEED

    # Status decision rules
    rules = payload["status_decision_rules"]
    assert "supported_for_next_stage" in rules["allowed_statuses"]
    assert "inconclusive" in rules["allowed_statuses"]
    assert "not_supported" in rules["allowed_statuses"]
    assert "invalid_data_contract" in rules["allowed_statuses"]


def test_spec_json_canonical_formatting() -> None:
    """Verify JSON can be deserialized and reserialized cleanly."""
    payload = load_spec_payload()
    dumped = json.dumps(payload, indent=2)
    reloaded = json.loads(dumped)
    assert reloaded == payload
