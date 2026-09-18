"""Deterministic product and operational universe contract tests for MVP-ARCH-001-R7-PIT-STATUS-IMPL-C.

Verifies:
1. Canonical operational manifest exists and loads via real load_universe_manifest as Contract v2.
2. Exact 45-symbol set matching Candidate C.
3. Exact Candidate C universe_hash.
4. Deterministic computed manifest_hash committed to decision record.
5. 15 ETF symbols declared with earnings = 'not_applicable', reference = 'required'.
6. 30 equity symbols declared with earnings = 'required', reference = 'required'.
7. All 45 symbols have reference = 'required'.
8. Effective date is 2026-09-21 and universe version is 2026-09-21-v1.
9. Pure pacing capacity estimate matches Candidate C bounds.
10. PR C decision artifact exists and aligns with canonical manifest and governance.
11. Governance invariants: Schema remains v8 and APPROVED_PRODUCTION_STRATEGIES is empty.
12. Windows scheduler asset exists and its non-mutating Validate action passes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from tradex.pit.ops import estimate_capacity, load_universe_manifest
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES
from tradex.tracker.store import _SCHEMA_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_MANIFEST_PATH = REPO_ROOT / "docs" / "product" / "manifests" / "pit-universe-2026-09-21-v1.json"
DECISION_JSON_PATH = REPO_ROOT / "docs" / "product" / "artifacts" / "r7-pit-status-impl-c" / "decision.json"
HUMAN_DOC_PATH = REPO_ROOT / "docs" / "product" / "R7-PIT-STATUS-IMPL-C.md"
SCHEDULER_SCRIPT_PATH = REPO_ROOT / "scripts" / "manage_pit_scheduler.ps1"

FROZEN_CANDIDATE_C_UNIVERSE_HASH = "83d6e6e66991743b3a6301a674adbdf4425e2dc524ed027c7ee4d6097c371f29"
EXPECTED_MANIFEST_HASH = "4eee8a5da39c74db499b6f644f6891d61f6a30b0f98d95b53445b12929c9dedb"

EXPECTED_ETFS = {
    "DIA", "IWM", "QQQ", "SPY", "XLB", "XLC", "XLE", "XLF",
    "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
}

EXPECTED_EQUITIES = {
    "AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO",
    "CVX", "DIS", "GS", "HD", "HON", "IBM", "JNJ", "JPM",
    "KO", "MCD", "MMM", "MRK", "MSFT", "NKE", "NVDA", "PG",
    "SHW", "TRV", "UNH", "V", "VZ", "WMT",
}


def test_canonical_manifest_loads_and_verifies_contract_v2() -> None:
    """Verify the canonical operational manifest exists, loads as v2, and matches locked attributes."""
    assert CANONICAL_MANIFEST_PATH.exists(), f"Missing canonical manifest: {CANONICAL_MANIFEST_PATH}"

    manifest = load_universe_manifest(CANONICAL_MANIFEST_PATH)

    assert manifest.contract_version == 2
    assert manifest.universe_id == "candidate-dow30-sector-etfs"
    assert manifest.universe_version == "2026-09-21-v1"
    assert manifest.effective_from == date(2026, 9, 21)
    assert len(manifest.symbols) == 45
    assert set(manifest.symbols) == EXPECTED_EQUITIES | EXPECTED_ETFS

    assert manifest.universe_hash == FROZEN_CANDIDATE_C_UNIVERSE_HASH
    assert manifest.manifest_hash == EXPECTED_MANIFEST_HASH


def test_canonical_manifest_applicability_breakdown() -> None:
    """Verify explicit per-symbol applicability breakdown for equities and ETFs."""
    manifest = load_universe_manifest(CANONICAL_MANIFEST_PATH)
    assert manifest.applicability is not None
    assert len(manifest.applicability) == 45

    for sym in EXPECTED_ETFS:
        app = manifest.applicability[sym]
        assert app["earnings"] == "not_applicable", f"ETF {sym} must have earnings = not_applicable"
        assert app["reference"] == "required", f"ETF {sym} must have reference = required"

    for sym in EXPECTED_EQUITIES:
        app = manifest.applicability[sym]
        assert app["earnings"] == "required", f"Equity {sym} must have earnings = required"
        assert app["reference"] == "required", f"Equity {sym} must have reference = required"

    # All 45 symbols require reference
    ref_required = sum(1 for a in manifest.applicability.values() if a["reference"] == "required")
    assert ref_required == 45

    # 30 require earnings, 15 not applicable
    earn_required = sum(1 for a in manifest.applicability.values() if a["earnings"] == "required")
    earn_na = sum(1 for a in manifest.applicability.values() if a["earnings"] == "not_applicable")
    assert earn_required == 30
    assert earn_na == 15


def test_capacity_estimation_matches_candidate_c() -> None:
    """Verify pure pacing floor capacity math matches Candidate C specifications."""
    manifest = load_universe_manifest(CANONICAL_MANIFEST_PATH)
    cap = estimate_capacity(manifest)

    assert cap.symbol_count == 45
    assert cap.minimum_reference_requests == 45
    assert cap.maximum_reference_requests == 90
    assert cap.minimum_pacing_floor_seconds == pytest.approx(532.4, abs=0.1)
    assert cap.maximum_pacing_floor_seconds == pytest.approx(1076.9, abs=0.1)


def test_pr_c_decision_artifact_consistency() -> None:
    """Verify decision.json exists and strictly enforces PR C authorization metadata."""
    assert DECISION_JSON_PATH.exists(), f"Missing decision.json: {DECISION_JSON_PATH}"

    with open(DECISION_JSON_PATH, "r", encoding="utf-8") as f:
        decision = json.load(f)

    assert decision["task_id"] == "MVP-ARCH-001-R7-PIT-STATUS-IMPL-C"
    assert decision["decision_status"] == "gary_approved"
    assert decision["approved_by"] == "Gary Yang"
    assert decision["approved_on"] == "2026-09-18"
    assert decision["selected_candidate"] == "C"
    assert decision["selected_universe"] == "candidate-dow30-sector-etfs"
    assert decision["selected_universe_version"] == "2026-09-21-v1"
    assert decision["effective_from"] == "2026-09-21"

    assert decision["contract_version"] == 2
    assert decision["symbol_count"] == 45
    assert decision["equity_count"] == 30
    assert decision["etf_count"] == 15
    assert decision["equities_requiring_earnings"] == 30
    assert decision["etfs_earnings_not_applicable"] == 15
    assert decision["reference_required"] == 45

    assert decision["universe_hash"] == FROZEN_CANDIDATE_C_UNIVERSE_HASH
    assert decision["manifest_hash"] == EXPECTED_MANIFEST_HASH

    assert decision["candidate_b_status"] == "not_selected"
    assert decision["candidate_c_status"] == "selected"

    assert decision["operational_universe_selected"] is True
    assert decision["scheduler_assets_authorized"] is True
    assert decision["scheduler_installed"] is False
    assert decision["scheduler_enabled"] is False
    assert decision["live_provider_calls_performed"] is False


def test_governance_invariants_and_empty_strategy_registry() -> None:
    """Verify Schema v8, empty strategy registry, and presence of human documentation."""
    assert _SCHEMA_VERSION == 8
    assert APPROVED_PRODUCTION_STRATEGIES == ()

    assert HUMAN_DOC_PATH.exists(), f"Missing human doc: {HUMAN_DOC_PATH}"
    doc_text = HUMAN_DOC_PATH.read_text(encoding="utf-8")
    assert "MVP-ARCH-001-R7-PIT-STATUS-IMPL-C" in doc_text
    assert "candidate-dow30-sector-etfs" in doc_text
    assert "2026-09-18" in doc_text
    assert "Gary Yang" in doc_text
    assert FROZEN_CANDIDATE_C_UNIVERSE_HASH in doc_text
    assert EXPECTED_MANIFEST_HASH in doc_text


def test_powershell_scheduler_asset_exists_and_validates() -> None:
    """Verify manage_pit_scheduler.ps1 exists and non-mutating validation passes on Windows."""
    assert SCHEDULER_SCRIPT_PATH.exists(), f"Missing scheduler script: {SCHEDULER_SCRIPT_PATH}"

    if sys.platform == "win32":
        result = subprocess.run(
            [
                "powershell.exe",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCHEDULER_SCRIPT_PATH),
                "-Action",
                "Validate",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"Scheduler validation failed:\n{result.stdout}\n{result.stderr}"
        assert "[PASS] Host timezone: Eastern Standard Time" in result.stdout
        assert "[PASS] Manifest validated successfully via CLI." in result.stdout
        assert "Safe validation completed. No OS scheduled tasks were created or modified." in result.stdout
