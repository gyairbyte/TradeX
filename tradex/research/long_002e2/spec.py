"""Preregistered specification constants and schemas for LONG-002E2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]

# Spec metadata
SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002E2-v1.json"
EXPECTED_SPEC_SHA256 = "cec5105883198cbd856c763cd39993fa1e2f72960fd7c4c5bb17dbfd2a0f9519"
PREREGISTRATION_SPEC_SHA256 = EXPECTED_SPEC_SHA256

# Correction specification metadata (LONG-002E2-CORR-001)
CORR_001_SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002E2-CORR-001-v1.json"
EXPECTED_CORR_001_SPEC_SHA256 = "4e57fb503d99bab5e02a90461eb2da6ce32825f065075c85587e8fec225c74a0"

TASK_ID = "LONG-002E2-LOGISTIC-STABILITY-DIAGNOSTIC-001"
PROGRAM = "LONG-002"
PHASE = "LONG-002E2"
BASE_GIT_SHA = "58df7d468d7175264758a997a7a9c701c7f8d369"
AUTHORIZATION_DATE = "2026-10-06"
AUTHORIZER = "Gary Yang"

REPRESENTATIVE_CONFIGURATION_ID = "LOGIT_S4_C300"
REPRESENTATIVE_SELECTION_BASIS = "best_by_locked_LONG_002E1_ordering"
# Corrected hyperparameter matching canonical E1 configuration registry (C denotes 3.0, not three hundred)
CORRECTED_REPRESENTATIVE_HYPERPARAMETERS = {
    "C": 3.0,
    "penalty": "l2",
    "solver": "lbfgs",
    "max_iter": 1000,
    "class_weight": None,
}

# Evaluation population bounds
DEV_START = "2018-01-01"
DEV_END = "2020-12-31"
POPULATION_CUTOFF = "20:30"
EVALUATION_SESSIONS_COUNT = 730
EXPECTED_PREDICTION_ROW_COUNT = 610648
JOIN_KEYS = ["immutable_security_id", "as_of_date", "cutoff_time"]

# Required input paths and digests
E1_PREDICTION_PATH = Path(
    "data/research/long_002e1/LONG-002E1-20261006_152832/predictions_regularized_probabilistic_LOGIT_S4_C300.parquet"
)
EXPECTED_E1_PREDICTION_SHA256 = "837b824ac11754a900b44c2e118872996a9cad424cab1c549be7df5b61780062"

D1_FEATURE_TABLE_PATH = Path("data/research/long_002d1/feature_table.parquet")
EXPECTED_D1_FEATURE_TABLE_SHA256 = (
    "7dc09bdeed02c44eb48a0143884deb0ad7795466a08e25fd26c32640a0c813d8"
)

STAGE_C_BASELINE_PATH = Path("data/research/long_002c/baseline_comparator_outputs.parquet")
EXPECTED_STAGE_C_BASELINE_SHA256 = (
    "faec26ddb26fd5a17feddf5ae09232a8aeb8ba24c3529abd88422682357e4734"
)

# Upstream specifications and committed artifact hashes
UPSTREAM_SPECS = {
    "LONG-002-v1.json": (
        REPO_ROOT / "docs" / "research" / "specs" / "LONG-002-v1.json",
        "f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5",
    ),
    "LONG-002E1-v1.json": (
        REPO_ROOT / "docs" / "research" / "specs" / "LONG-002E1-v1.json",
        "d10b3fd5e24cf6880d76f18cf84eabe23cf65d6fa0a32735877b7383ae51c2b0",
    ),
    "LONG-002E1-CORR-001-v1.json": (
        REPO_ROOT / "docs" / "research" / "specs" / "LONG-002E1-CORR-001-v1.json",
        "6a4345f6c9c0b96a3c11d4e44b437157128f1222ad346466f8d51c9f4f550c96",
    ),
}

E1_CORRECTED_RUN_ID = "LONG-002E1-20261006_152832"
E1_SAFE_ARTIFACTS_DIR = (
    REPO_ROOT / "docs" / "research" / "artifacts" / "LONG-002E1" / E1_CORRECTED_RUN_ID
)
E1_SAFE_ARTIFACT_HASHES = {
    "annual_stability.json": "5a9d15232fc09a76a70422a57c8c137d86df25f2214037a449ba4ee9a3c8f5cf",
    "baseline_summary.json": "3838600a636a9539337201d551933115211f89476bbaee9d0baa2a8391fa126d",
    "round1_summary.json": "dfde6712084a7ac1d9c58f8c5babb22cf24aba146e2762bc5368cb7d90201708",
}

# Frozen features
FROZEN_FEATURES = [
    "return_5",
    "atr_pct_14",
    "return_20",
    "return_60",
    "close_vs_sma20",
    "close_vs_sma60",
    "sma20_slope_5",
    "relative_volume_20",
]

# Bootstrap parameters
BOOTSTRAP_BLOCK_SIZE = 21
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = 20261006

# Localization threshold & decision rules
LOCALIZATION_THRESHOLD = 0.60
ALLOWED_DISPOSITIONS = [
    "bounded_followup_hypothesis_warranted",
    "no_bounded_regime_hypothesis_supported",
    "diagnostic_invalid",
]
ALLOWED_RECOMMENDED_ACTIONS = [
    "preregister_one_bounded_followup_hypothesis",
    "close_initial_long_002e_search_preserve_unused_budget",
    "invalidate_and_correct_diagnostic",
]


def compute_file_sha256(path: Path) -> str:
    """Compute deterministic SHA-256 digest of file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_e2_spec_hash() -> None:
    """Verify that the E2 specification file exists and matches the locked SHA-256 digest."""
    if not SPEC_PATH.exists():
        raise FileNotFoundError(f"LONG-002E2 specification missing at {SPEC_PATH}")
    computed = compute_file_sha256(SPEC_PATH)
    if computed != EXPECTED_SPEC_SHA256:
        raise ValueError(
            f"LONG-002E2 SPECIFICATION TAMPERED / HASH MISMATCH: {computed} != {EXPECTED_SPEC_SHA256}"
        )


def load_e2_spec() -> dict[str, Any]:
    """Load verified E2 specification."""
    verify_e2_spec_hash()
    with SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def verify_corr_001_spec_hash() -> None:
    """Verify that the LONG-002E2-CORR-001 specification file exists and matches the locked SHA-256 digest."""
    if not CORR_001_SPEC_PATH.exists():
        raise FileNotFoundError(
            f"LONG-002E2-CORR-001 specification missing at {CORR_001_SPEC_PATH}"
        )
    computed = compute_file_sha256(CORR_001_SPEC_PATH)
    if computed != EXPECTED_CORR_001_SPEC_SHA256:
        raise ValueError(
            f"LONG-002E2-CORR-001 SPECIFICATION TAMPERED / HASH MISMATCH: {computed} != {EXPECTED_CORR_001_SPEC_SHA256}"
        )


def load_corr_001_spec() -> dict[str, Any]:
    """Load verified LONG-002E2-CORR-001 specification."""
    verify_corr_001_spec_hash()
    with CORR_001_SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)
