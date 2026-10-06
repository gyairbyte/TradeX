"""Tests for LONG-002E2-CORR-001 representative hyperparameter metadata correction and invariants."""

from __future__ import annotations

import json

from tradex.research.long_002e2.spec import (
    CORR_001_SPEC_PATH,
    CORRECTED_REPRESENTATIVE_HYPERPARAMETERS,
    E1_PREDICTION_PATH,
    E1_SAFE_ARTIFACTS_DIR,
    EXPECTED_CORR_001_SPEC_SHA256,
    EXPECTED_E1_PREDICTION_SHA256,
    EXPECTED_SPEC_SHA256,
    REPO_ROOT,
    REPRESENTATIVE_CONFIGURATION_ID,
    SPEC_PATH,
    compute_file_sha256,
    load_corr_001_spec,
    load_e2_spec,
)


def test_corr_001_spec_hash_and_validity() -> None:
    """Verify that LONG-002E2-CORR-001 spec exists, matches expected SHA-256, and links base spec."""
    assert CORR_001_SPEC_PATH.exists()
    computed_hash = compute_file_sha256(CORR_001_SPEC_PATH)
    assert computed_hash == EXPECTED_CORR_001_SPEC_SHA256

    spec = load_corr_001_spec()
    assert spec["task_id"] == "LONG-002E2-CORR-001"
    assert spec["classification"] == "research_only_correction"
    assert spec["base_specification"]["path"] == "docs/research/specs/LONG-002E2-v1.json"
    assert spec["base_specification"]["sha256"] == EXPECTED_SPEC_SHA256
    assert spec["corrected_representative_metadata"]["configuration_id"] == "LOGIT_S4_C300"
    assert spec["corrected_representative_metadata"]["corrected_c"] == 3.0
    assert spec["corrected_representative_metadata"]["preregistered_c_erroneous"] == 300.0


def test_original_spec_frozen_and_not_modified_in_place() -> None:
    """Verify the original LONG-002E2-v1.json specification is preserved unchanged."""
    assert SPEC_PATH.exists()
    assert compute_file_sha256(SPEC_PATH) == EXPECTED_SPEC_SHA256
    base_spec = load_e2_spec()
    assert base_spec["task_id"] == "LONG-002E2-LOGISTIC-STABILITY-DIAGNOSTIC-001"


def test_cross_check_representative_against_canonical_e1_registry() -> None:
    """Cross-check representative model metadata against canonical E1 configuration registry."""
    config_reg_path = E1_SAFE_ARTIFACTS_DIR / "configuration_registry.json"
    assert config_reg_path.exists(), f"Missing canonical E1 registry: {config_reg_path}"

    with config_reg_path.open("r", encoding="utf-8") as f:
        registry = json.load(f)

    # Find representative configuration in canonical E1 registry
    matching = [
        cfg for cfg in registry if cfg["configuration_id"] == REPRESENTATIVE_CONFIGURATION_ID
    ]
    assert len(matching) == 1, f"Expected exactly one entry for {REPRESENTATIVE_CONFIGURATION_ID}"

    e1_cfg = matching[0]
    assert e1_cfg["family"] == "regularized_probabilistic"
    assert e1_cfg["feature_subset_id"] == "S4"

    params = e1_cfg["parameters"]
    assert params["C"] == 3.0, f"Canonical E1 C parameter must be 3.0, got {params['C']}"
    assert params["penalty"] == "l2"
    assert params["solver"] == "lbfgs"
    assert params["max_iter"] == 1000
    assert params["class_weight"] is None

    # Cross-check against code constant
    assert CORRECTED_REPRESENTATIVE_HYPERPARAMETERS["C"] == params["C"]
    assert CORRECTED_REPRESENTATIVE_HYPERPARAMETERS["penalty"] == params["penalty"]
    assert CORRECTED_REPRESENTATIVE_HYPERPARAMETERS["solver"] == params["solver"]
    assert CORRECTED_REPRESENTATIVE_HYPERPARAMETERS["max_iter"] == params["max_iter"]


def test_exact_frozen_representative_prediction_sha_unchanged() -> None:
    """Verify input prediction parquet SHA-256 matches locked digest."""
    full_pred_path = REPO_ROOT / E1_PREDICTION_PATH
    assert full_pred_path.exists(), f"Missing prediction parquet: {full_pred_path}"
    pred_sha = compute_file_sha256(full_pred_path)
    assert pred_sha == EXPECTED_E1_PREDICTION_SHA256


def test_no_code_used_erroneous_c300_in_e2_computation() -> None:
    """Verify no source code in tradex.research.long_002e2 uses 300.0 as a parameter or fits models."""
    pkg_dir = REPO_ROOT / "tradex" / "research" / "long_002e2"
    for py_file in pkg_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "LogisticRegression(" not in content
        assert "HistGradientBoostingClassifier(" not in content
        assert ".fit(" not in content
        assert '"C": 300' not in content
        assert "C=300" not in content
        assert "C: 300" not in content


def test_e2_safe_artifacts_checksums_preserved() -> None:
    """Verify all existing E2 diagnostic safe artifacts match their committed checksums."""
    e2_artifacts_dir = (
        REPO_ROOT / "docs" / "research" / "artifacts" / "LONG-002E2" / "LONG-002E2-20261006_183219"
    )
    checksums_file = e2_artifacts_dir / "checksums.sha256"
    assert checksums_file.exists(), f"Missing checksums file: {checksums_file}"

    lines = checksums_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 13

    for line in lines:
        expected_sha, fname = line.strip().split()
        target_file = e2_artifacts_dir / fname
        assert target_file.exists(), f"Missing artifact: {target_file}"
        computed_sha = compute_file_sha256(target_file)
        assert computed_sha == expected_sha, (
            f"Checksum mismatch for {fname}: {computed_sha} != {expected_sha}"
        )
