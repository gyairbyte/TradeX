"""Tests for LONG-002D3A specification schema, split quarantine, and governance immutability."""
from __future__ import annotations

import pytest

from tradex.research.long_002d3a.spec import (
    DEV_END,
    DEV_START,
    EXPECTED_SPEC_SHA256,
    MAIN_STUDY_SEED,
    MAIN_STUDY_SIZE,
    PILOT_QUOTA_PER_STRATUM,
    PILOT_SEED,
    PILOT_SIZE,
    POPULATION_CUTOFF,
    REPO_ROOT,
    SPEC_PATH,
    STRATA_PRECEDENCE,
    TASK_ID,
    UPSTREAM_INPUT_HASHES,
    enforce_split_guard,
    load_spec_payload,
    verify_spec_integrity,
)
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES


def test_spec_file_exists_and_integrity_hash_matches() -> None:
    """AC1: Spec exists and matches exact preregistered SHA-256 digest."""
    assert SPEC_PATH.exists(), f"Spec missing at {SPEC_PATH}"
    computed = verify_spec_integrity()
    assert computed == EXPECTED_SPEC_SHA256


def test_spec_task_identity_and_governance() -> None:
    """Verify task classification, authorization, and promotion boundaries."""
    payload = load_spec_payload()
    assert payload["task_id"] == TASK_ID
    assert payload["classification"] == "research_only"
    assert payload["production_promotion_eligible"] is False
    assert payload["approved_production_strategies"] == []

    auth = payload["authorization"]
    assert auth["authorizer"] == "Gary Yang"
    assert auth["authorization_date"] == "2026-10-03"
    assert auth["bounded_by"] == "ChatGPT"
    assert "executing_240_case_main_review" in auth["unauthorized_actions"]
    assert "production_promotion" in auth["unauthorized_actions"]
    assert "validation_access" in auth["unauthorized_actions"]
    assert "holdout_access" in auth["unauthorized_actions"]
    assert "shadow_replay_access" in auth["unauthorized_actions"]


def test_development_only_split_and_quarantine() -> None:
    """AC2: Development-only split enforced; validation, holdout, and shadow rejected."""
    payload = load_spec_payload()
    pop = payload["study_population"]
    assert pop["split"] == "development"
    assert pop["start_date"] == DEV_START
    assert pop["end_date"] == DEV_END
    assert pop["cutoff_time"] == POPULATION_CUTOFF

    # Valid development dates must pass guard
    enforce_split_guard("2016-01-04")
    enforce_split_guard("2018-06-15")
    enforce_split_guard("2020-12-30")

    # Dates before development must fail
    with pytest.raises(ValueError, match="precedes development split"):
        enforce_split_guard("2015-12-31")

    # Validation dates (2021-2022) must fail
    with pytest.raises(ValueError, match="quarantined validation split"):
        enforce_split_guard("2021-01-04")
    with pytest.raises(ValueError, match="quarantined validation split"):
        enforce_split_guard("2022-12-30")

    # Holdout dates (2023-2025) must fail
    with pytest.raises(ValueError, match="quarantined holdout split"):
        enforce_split_guard("2023-01-03")
    with pytest.raises(ValueError, match="quarantined holdout split"):
        enforce_split_guard("2025-12-31")

    # Shadow dates (2026+) must fail
    with pytest.raises(ValueError, match="quarantined shadow split"):
        enforce_split_guard("2026-01-02")
    with pytest.raises(ValueError, match="quarantined shadow split"):
        enforce_split_guard("2026-10-03")


def test_exact_20_30_population_enforced() -> None:
    """Exact 20:30 evening snapshot population enforced; 09:00 out of scope."""
    payload = load_spec_payload()
    pop = payload["study_population"]
    assert pop["cutoff_time"] == "20:30"
    assert "09:00" in pop["out_of_scope_cutoffs"]


def test_pilot_study_contract_parameters() -> None:
    """Verify pilot sample size, strata quotas, seed, and exclusion contract."""
    payload = load_spec_payload()
    pilot = payload["pilot_study_contract"]
    assert pilot["sample_size"] == PILOT_SIZE == 24
    assert pilot["quota_per_stratum"] == PILOT_QUOTA_PER_STRATUM == 6
    assert pilot["pilot_random_seed"] == PILOT_SEED == 20261003
    assert pilot["strata_counts"] == {
        "positive_master_episode": 6,
        "near_miss": 6,
        "adverse_trap": 6,
        "ordinary_non_mover": 6,
    }
    assert pilot["case_id_range"] == ["D3A-PILOT-001", "D3A-PILOT-024"]


def test_strata_precedence_and_definitions() -> None:
    """Verify strata priority precedence and definitions."""
    payload = load_spec_payload()
    strata = payload["strata_definitions"]
    assert list(strata["class_priority_precedence"]) == list(STRATA_PRECEDENCE)
    assert set(strata["classes"].keys()) == set(STRATA_PRECEDENCE)


def test_future_main_study_contract_foundation() -> None:
    """Verify future main study structural parameters without execution."""
    payload = load_spec_payload()
    main_c = payload["future_main_study_contract"]
    assert main_c["main_study_sample_size"] == MAIN_STUDY_SIZE == 240
    assert main_c["future_main_seed"] == MAIN_STUDY_SEED == 20261004
    assert main_c["strata_counts"] == {
        "positive_master_episode": 120,
        "ordinary_non_mover": 40,
        "near_miss": 40,
        "adverse_trap": 40,
    }
    assert main_c["execution_status"] == "NOT_EXECUTED_IN_THIS_PR"


def test_upstream_required_input_digests() -> None:
    """Verify preregistered digests for Stage C, D1, and D2 inputs."""
    payload = load_spec_payload()
    required = payload["upstream_evidence"]["required_input_digests"]
    for fname, exp_sha in UPSTREAM_INPUT_HASHES.items():
        assert fname in required, f"Missing digest for {fname}"
        assert required[fname]["sha256"] == exp_sha


def test_approved_production_strategies_is_empty() -> None:
    """AC26: APPROVED_PRODUCTION_STRATEGIES is strictly empty."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()


def test_d1_and_d2_specs_remain_unmodified() -> None:
    """Upstream D1 and D2 specs must remain unmodified."""
    d1_spec = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002D1-v1.json"
    d2_spec = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002D2-v1.json"

    assert d1_spec.exists()
    assert d2_spec.exists()

    payload = load_spec_payload()
    d1_exp = payload["upstream_evidence"]["stage_d1"]["preregistration_spec_sha256"]
    d2_exp = payload["upstream_evidence"]["stage_d2"]["preregistration_spec_sha256"]

    import hashlib
    with open(d1_spec, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == d1_exp
    with open(d2_spec, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == d2_exp
