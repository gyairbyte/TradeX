"""Specification integrity, hash verification, and governance tests for DAYTRADE-003."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradex.research.daytrade_orb import (
    LOCKED_003B_SPEC_SHA256,
    LOCKED_003C_RESOLUTION_SHA256,
    EffectiveORBSpec,
    SpecError,
    load_effective_spec,
    sha256_of_file,
)
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_003B_PATH = REPO_ROOT / "docs" / "research" / "specs" / "DAYTRADE-003B-ORB-v1.json"
SPEC_003C_PATH = REPO_ROOT / "docs" / "research" / "specs" / "DAYTRADE-003C-ORB-RESOLUTION-v1.json"
MD_003B_PATH = REPO_ROOT / "docs" / "research" / "DAYTRADE-003B-ORB.md"


def test_upstream_003b_spec_hash_integrity() -> None:
    """Requirement: DAYTRADE-003B spec hash remains strictly 62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0."""
    actual_hash = sha256_of_file(SPEC_003B_PATH)
    assert actual_hash == LOCKED_003B_SPEC_SHA256, (
        f"003B hash drift! Expected {LOCKED_003B_SPEC_SHA256}, got {actual_hash}"
    )


def test_resolution_003c_spec_hash_integrity() -> None:
    """Requirement: DAYTRADE-003C resolution spec hash is deterministic and matches locked constant."""
    actual_hash = sha256_of_file(SPEC_003C_PATH)
    assert actual_hash == LOCKED_003C_RESOLUTION_SHA256, (
        f"003C hash drift! Expected {LOCKED_003C_RESOLUTION_SHA256}, got {actual_hash}"
    )


def test_specs_are_valid_and_json_safe() -> None:
    """Requirement: Both spec files parse cleanly without NaN or Infinity."""
    for path in (SPEC_003B_PATH, SPEC_003C_PATH):
        content = json.loads(path.read_text(encoding="utf-8"))
        serialized = json.dumps(content, allow_nan=False, indent=2)
        assert len(serialized) > 0


def test_approved_production_strategies_strictly_empty() -> None:
    """Requirement: APPROVED_PRODUCTION_STRATEGIES == () is strictly preserved."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()


def test_load_effective_spec_success() -> None:
    """Requirement: EffectiveORBSpec loader extracts all locked parameters correctly."""
    spec = load_effective_spec(REPO_ROOT)
    assert isinstance(spec, EffectiveORBSpec)
    assert spec.task_id == "DAYTRADE-003C-ORB-EVALUATOR-001"
    assert spec.strategy_id == "DAYTRADE-003B-ORB-SIP5M"
    assert spec.upstream_strategy_id == "DAYTRADE-003B-ORB-SIP5M"
    assert spec.upstream_task_id == "DAYTRADE-003B-ORB-PREREG-001"
    assert spec.upstream_spec_sha256 == LOCKED_003B_SPEC_SHA256
    assert spec.resolution_spec_sha256 == LOCKED_003C_RESOLUTION_SHA256
    assert spec.price_threshold == 5.0
    assert spec.adv14_threshold == 1000000.0
    assert spec.atr14_threshold == 0.50
    assert spec.rv_threshold == 1.0
    assert spec.top_n == 20
    assert spec.initial_equity == 25000.0
    assert spec.leverage_cap == 4.0
    assert spec.risk_fraction == 0.01
    assert spec.stop_loss_atr_mult == 0.10
    assert spec.commission_per_share == 0.0035
    assert spec.slippage_bps_a == 0.0
    assert spec.slippage_bps_b == 2.0
    assert spec.slippage_bps_c == 5.0
    assert spec.bootstrap_resamples == 2000
    assert spec.bootstrap_seed == 20261007
    assert spec.bootstrap_confidence_level_pct == 95.0


def test_spec_drift_fails_closed(tmp_path: Path) -> None:
    """Requirement: Any byte tampering in specs causes load_effective_spec to fail closed."""
    # Create mock dir with drifted spec
    mock_specs = tmp_path / "docs" / "research" / "specs"
    mock_specs.mkdir(parents=True)

    # Valid 003B copy
    (mock_specs / "DAYTRADE-003B-ORB-v1.json").write_bytes(SPEC_003B_PATH.read_bytes())

    # Tampered 003C copy
    tampered_003c = json.loads(SPEC_003C_PATH.read_text(encoding="utf-8"))
    tampered_003c["task_id"] = "TAMPERED_TASK_ID"
    (mock_specs / "DAYTRADE-003C-ORB-RESOLUTION-v1.json").write_text(
        json.dumps(tampered_003c), encoding="utf-8"
    )

    with pytest.raises(SpecError, match="Resolution DAYTRADE-003C spec hash drift detected"):
        load_effective_spec(tmp_path)


def test_resolution_spec_governance_flags() -> None:
    """Requirement: Governance flags in 003C prohibit live data, empirical execution, and promotion."""
    spec_dict = json.loads(SPEC_003C_PATH.read_text(encoding="utf-8"))
    gov = spec_dict["governance"]
    assert gov["research_evaluator_authorized"] is True
    assert gov["synthetic_verification_authorized"] is True
    assert gov["real_market_data_acquisition_authorized"] is False
    assert gov["provider_api_calls_authorized"] is False
    assert gov["private_dataset_access_authorized"] is False
    assert gov["development_execution_authorized"] is False
    assert gov["validation_execution_authorized"] is False
    assert gov["holdout_access_authorized"] is False
    assert gov["production_promotion_authorized"] is False
    assert gov["approved_production_strategies_empty"] is True
