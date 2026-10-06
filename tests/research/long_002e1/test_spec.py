"""Deterministic, credential-free specification tests for LONG-002E1.

Validates the locked specification, governance boundaries, search budgets,
feature registries, upstream hashes, and configuration registries.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

REPO_ROOT = Path(__file__).resolve().parents[3]

E1_SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002E1-v1.json"
EXPECTED_E1_SPEC_SHA256 = "d10b3fd5e24cf6880d76f18cf84eabe23cf65d6fa0a32735877b7383ae51c2b0"

# Upstream locked specs and artifacts
LONG_002_SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002-v1.json"
LONG_002D1_SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002D1-v1.json"
LONG_002D2_SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002D2-v1.json"
LONG_002D3B_SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002D3B-v1.json"
D3B_FEATURE_REGISTRY_PATH = REPO_ROOT / "docs" / "research" / "artifacts" / "LONG-002D3B" / "feature_registry.json"
D3B_REC_CONTRACT_PATH = REPO_ROOT / "docs" / "research" / "artifacts" / "LONG-002D3B" / "recommendation_episode_contract.json"
D3B_READINESS_PATH = REPO_ROOT / "docs" / "research" / "artifacts" / "LONG-002D3B" / "readiness_decision.json"

LOCKED_UPSTREAM_HASHES = {
    "LONG-002-v1.json": "f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5",
    "LONG-002D1-v1.json": "cfa450824d269fb80a276ad9986835faf08f5d1a632722d0824502c68f738381",
    "LONG-002D2-v1.json": "db82482333fb0c9810279d289e87e82e7274802fae82269cbf1b63c7ad2a6fb8",
    "LONG-002D3B-v1.json": "130eec4c9f9afd5c7b1e826e5a39aa8a6fba748ce53d2001cb089716b8d7992c",
    "D3B_feature_registry.json": "57a1837f25004272d3a1a16fce3939d184ba5f388a117a3e631df4b12158d628",
    "D3B_recommendation_episode_contract.json": "e503991cb2fca33e00a5a150a61f22e5b4d9df9ee64505113e3b4b9be2803642",
    "D3B_readiness_decision.json": "3511bb186aa8c95ed5c2b6b471969e7cb9ab1d39bac8939007c4ec4102020a25",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def e1_spec() -> dict[str, Any]:
    with E1_SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def d3b_feature_registry() -> dict[str, Any]:
    with D3B_FEATURE_REGISTRY_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


# --- Tests 1-11: SPEC / GOVERNANCE ---


def test_01_e1_spec_hash_verified() -> None:
    """Verify LONG-002E1-v1.json cryptographic digest."""
    assert _sha256(E1_SPEC_PATH) == EXPECTED_E1_SPEC_SHA256


def test_02_d3b_feature_registry_hash_verified() -> None:
    """Verify D3B feature registry cryptographic digest."""
    assert _sha256(D3B_FEATURE_REGISTRY_PATH) == LOCKED_UPSTREAM_HASHES["D3B_feature_registry.json"]


def test_03_d3b_recommendation_episode_contract_hash_verified() -> None:
    """Verify D3B recommendation episode contract cryptographic digest."""
    assert _sha256(D3B_REC_CONTRACT_PATH) == LOCKED_UPSTREAM_HASHES["D3B_recommendation_episode_contract.json"]
    assert _sha256(D3B_READINESS_PATH) == LOCKED_UPSTREAM_HASHES["D3B_readiness_decision.json"]


def test_04_exactly_eight_predictive_features_allowed(e1_spec: dict[str, Any]) -> None:
    """Verify exactly 8 features are allowed as predictive inputs."""
    allowed = e1_spec["frozen_feature_registry"]["allowed_predictive_features"]
    expected = [
        "return_5",
        "atr_pct_14",
        "return_20",
        "return_60",
        "close_vs_sma20",
        "close_vs_sma60",
        "sma20_slope_5",
        "relative_volume_20",
    ]
    assert len(allowed) == 8
    assert sorted(allowed) == sorted(expected)


def test_05_excluded_features_cannot_enter_a_config(e1_spec: dict[str, Any]) -> None:
    """Verify excluded features are strictly banned from all feature subsets."""
    excluded = set(e1_spec["frozen_feature_registry"]["excluded_features"])
    for subset_id, subset in e1_spec["frozen_feature_registry"]["feature_subsets"].items():
        subset_feats = set(subset["features"])
        overlap = subset_feats.intersection(excluded)
        assert overlap == set(), f"Subset {subset_id} contains excluded features: {overlap}"


def test_06_pullback_and_reverse_proximity_cannot_enter_a_config(e1_spec: dict[str, Any]) -> None:
    """Verify post-hoc pullback finding and reverse proximity are forbidden."""
    for subset in e1_spec["frozen_feature_registry"]["feature_subsets"].values():
        for feat in subset["features"]:
            assert "pullback" not in feat.lower()
            assert "dip" not in feat.lower()
            assert "proximity" not in feat.lower()


def test_07_exactly_36_round1_configurations(e1_spec: dict[str, Any]) -> None:
    """Verify exactly 36 material Round-1 configurations are registered."""
    reg = e1_spec["material_configuration_registry"]
    total = reg["total_authorized_configurations"]
    assert total == 36

    all_ids = []
    for fam in reg["families"].values():
        all_ids.extend(fam["configuration_ids"])
    assert len(all_ids) == 36


def test_08_exactly_12_configurations_per_family(e1_spec: dict[str, Any]) -> None:
    """Verify exactly 12 configurations per approved model family."""
    reg = e1_spec["material_configuration_registry"]
    families = reg["families"]
    assert len(families) == 3
    for fam_key, fam in families.items():
        assert len(fam["configuration_ids"]) == 12, f"Family {fam_key} does not have 12 configs"


def test_09_config_ids_unique(e1_spec: dict[str, Any]) -> None:
    """Verify all 36 configuration IDs are unique."""
    reg = e1_spec["material_configuration_registry"]
    all_ids = []
    for fam in reg["families"].values():
        all_ids.extend(fam["configuration_ids"])
    assert len(all_ids) == len(set(all_ids)) == 36


def test_10_failed_config_still_consumes_budget(e1_spec: dict[str, Any]) -> None:
    """Verify search budget policy: failures consume budget, no silent replacement."""
    budget = e1_spec["search_budget_accounting"]
    assert budget["round_1_budget"] == 36
    assert "consume" in budget["failed_attempt_policy"].lower()
    assert "replacement" in budget["failed_attempt_policy"].lower()


def test_11_round_2_cannot_execute_from_e1_cli(e1_spec: dict[str, Any]) -> None:
    """Verify Round 2 remains unauthorized and gated."""
    assert e1_spec["round2_guardrails_frozen"]["round2_authorized"] is False
    assert e1_spec["round2_guardrails_frozen"]["requires_separate_assignment"] is True
    assert e1_spec["round2_guardrails_frozen"]["max_configurations_total"] == 12


def test_governance_invariants(e1_spec: dict[str, Any]) -> None:
    """Verify production boundary and quarantine invariants."""
    assert e1_spec["base_git_sha"] == "8058c5d858b70090335338176f11a20ddfd04502"
    assert e1_spec["production_boundary"]["production_promotion_eligible"] is False
    assert e1_spec["production_boundary"]["production_change_authorized"] is False
    assert APPROVED_PRODUCTION_STRATEGIES == ()
    assert e1_spec["quarantine_and_governance"]["validation_access_authorized"] is False
    assert e1_spec["quarantine_and_governance"]["holdout_access_authorized"] is False
    assert e1_spec["quarantine_and_governance"]["shadow_access_authorized"] is False
    assert e1_spec["quarantine_and_governance"]["zero_provider_calls"] is True
