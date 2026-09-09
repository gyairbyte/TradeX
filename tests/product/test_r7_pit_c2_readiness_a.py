"""Product contract tests for MVP-ARCH-001-R7-PIT-001C2-READINESS-A.

Verifies:
1. All five candidate universe manifests exist and load through the real load_universe_manifest.
2. Every candidate uses effective_from = 2099-01-01 (future date fail-closed guard).
3. Every manifest description explicitly indicates research-only / not active.
4. Every candidate has a non-empty normalized symbol set matching frozen counts.
5. decision.json exists and adheres to strict governance fields:
   - status == "pending_gary_decision"
   - selected_universe is None
   - active_universe_authorized is False
   - c2_implementation_authorized is False
   - scheduler_authorized is False
6. decision.json references all five candidates with exact counts, hashes, and capacity metrics
   matching the actual manifests and real estimate_capacity.
7. APPROVED_PRODUCTION_STRATEGIES == ().
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tradex.pit.ops import estimate_capacity, load_universe_manifest
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / "docs" / "product" / "artifacts" / "r7-pit-c2-readiness-a"
DECISION_JSON = ARTIFACTS_DIR / "decision.json"

CANDIDATE_FILES = (
    "candidate-sector-etfs.json",
    "candidate-dow30.json",
    "candidate-dow30-sector-etfs.json",
    "candidate-sp100.json",
    "candidate-sp100-sector-etfs.json",
)

EXPECTED_COUNTS = {
    "candidate-sector-etfs": 15,
    "candidate-dow30": 30,
    "candidate-dow30-sector-etfs": 45,
    "candidate-sp100": 100,
    "candidate-sp100-sector-etfs": 115,
}


def test_all_five_candidate_manifests_exist_and_load() -> None:
    """Verify all 5 candidate manifests exist, load via real loader, and have future effective date."""
    assert ARTIFACTS_DIR.exists(), f"Artifacts directory missing: {ARTIFACTS_DIR}"

    for filename in CANDIDATE_FILES:
        filepath = ARTIFACTS_DIR / filename
        assert filepath.exists(), f"Candidate manifest missing: {filepath}"

        manifest = load_universe_manifest(filepath)

        # Invariants
        assert manifest.contract_version == 1
        assert manifest.effective_from == date(2099, 1, 1), (
            f"{filename} must use future effective_from 2099-01-01 to fail-closed on run-slot"
        )
        desc_lower = manifest.description.lower()
        assert "research-only" in desc_lower or "research only" in desc_lower
        assert "not active" in desc_lower
        assert len(manifest.symbols) > 0
        assert len(manifest.symbols) == EXPECTED_COUNTS[manifest.universe_id]


def test_decision_json_governance_invariants() -> None:
    """Verify decision packet enforces pending status and zero authorizations."""
    assert DECISION_JSON.exists(), f"decision.json missing: {DECISION_JSON}"

    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    assert packet["task_id"] == "MVP-ARCH-001-R7-PIT-001C2-READINESS-A"
    assert packet["status"] == "pending_gary_decision"
    assert packet["source_commit"] == "e111c04107b929b0b2ae8896755d57ec9b114f95"
    assert packet["selected_universe"] is None
    assert packet["active_universe_authorized"] is False
    assert packet["c2_implementation_authorized"] is False
    assert packet["scheduler_authorized"] is False
    assert packet["coverage_first_recommendation"] == "candidate-dow30-sector-etfs"
    assert packet["latency_first_recommendation"] == "candidate-dow30"
    assert set(packet["deferred_candidates"]) == {
        "candidate-sp100",
        "candidate-sp100-sector-etfs",
    }


def test_decision_json_candidate_metrics_consistency() -> None:
    """Verify decision.json candidate metrics agree with loaded manifests and real estimate_capacity."""
    with open(DECISION_JSON, "r", encoding="utf-8") as f:
        packet = json.load(f)

    candidates = packet["candidates"]
    assert len(candidates) == 5

    candidate_by_id = {c["universe_id"]: c for c in candidates}
    assert set(candidate_by_id.keys()) == set(EXPECTED_COUNTS.keys())

    for filename in CANDIDATE_FILES:
        filepath = ARTIFACTS_DIR / filename
        manifest = load_universe_manifest(filepath)
        cap = estimate_capacity(manifest)

        entry = candidate_by_id[manifest.universe_id]
        assert entry["universe_version"] == manifest.universe_version
        assert entry["effective_from"] == manifest.effective_from.isoformat()
        assert entry["symbol_count"] == len(manifest.symbols)
        assert entry["universe_hash"] == manifest.universe_hash
        assert entry["manifest_hash"] == manifest.manifest_hash
        assert entry["minimum_reference_requests"] == cap.minimum_reference_requests
        assert entry["maximum_reference_requests"] == cap.maximum_reference_requests
        assert entry["minimum_pacing_floor_seconds"] == pytest.approx(
            cap.minimum_pacing_floor_seconds, rel=1e-5
        )
        assert entry["maximum_pacing_floor_seconds"] == pytest.approx(
            cap.maximum_pacing_floor_seconds, rel=1e-5
        )
        assert entry["minimum_pacing_floor_minutes"] == pytest.approx(
            cap.minimum_pacing_floor_seconds / 60.0, rel=1e-5
        )
        assert entry["maximum_pacing_floor_minutes"] == pytest.approx(
            cap.maximum_pacing_floor_seconds / 60.0, rel=1e-5
        )


def test_approved_production_strategies_remains_empty() -> None:
    """Registry invariant: APPROVED_PRODUCTION_STRATEGIES is strictly empty."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()
