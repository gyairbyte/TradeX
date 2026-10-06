"""Preregistered specification constants and schemas for LONG-002E1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002E1-v1.json"
EXPECTED_SPEC_SHA256 = "d10b3fd5e24cf6880d76f18cf84eabe23cf65d6fa0a32735877b7383ae51c2b0"
PREREGISTRATION_SPEC_SHA256 = EXPECTED_SPEC_SHA256
PREREGISTRATION_COMMIT_SHA = "49103f84ffbf7cd7b60216c2866ad103282bae58"

CORR_SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002E1-CORR-001-v1.json"
EXPECTED_CORR_SPEC_SHA256 = "6a4345f6c9c0b96a3c11d4e44b437157128f1222ad346466f8d51c9f4f550c96"
SUPERSEDED_RUN_ID = "LONG-002E1-20261006_133722"

TASK_ID = "LONG-002E1-ROUND1-CANDIDATE-SEARCH-001"
CORR_TASK_ID = "LONG-002E1-CORR-001"
PROGRAM = "LONG-002"
PHASE = "LONG-002E1"
BASE_GIT_SHA = "8058c5d858b70090335338176f11a20ddfd04502"

# Population bounds
DEV_START = "2016-01-01"
DEV_END = "2020-12-31"
PRIMARY_OOF_START = "2017-01-01"
PRIMARY_OOF_END = "2020-12-31"
CORRECTED_OOF_START = "2018-01-01"
CORRECTED_OOF_END = "2020-12-31"
POPULATION_CUTOFF = "20:30"
TARGET_PCT = 10.0
HORIZON_SESSIONS = 10
LABEL_COLUMN = "clean_target_reached"

# Expected input paths and SHA-256 digests
D1_FEATURE_TABLE_PATH = Path("data/research/long_002d1/feature_table.parquet")
D1_FEATURE_TABLE_SHA256 = "7dc09bdeed02c44eb48a0143884deb0ad7795466a08e25fd26c32640a0c813d8"

STAGE_C_BASELINE_PATH = Path("data/research/long_002c/baseline_comparator_outputs.parquet")
STAGE_C_BASELINE_SHA256 = "faec26ddb26fd5a17feddf5ae09232a8aeb8ba24c3529abd88422682357e4734"

STAGE_C_OUTCOME_PATH = Path("data/research/long_002c/outcome_matrix.parquet")
STAGE_C_OUTCOME_SHA256 = "b59a5f7f8a8a0498abdadb156299719f43ffa8854df5cad8e20a6cd4fbe237c3"

EXPECTED_DENOMINATOR = 758731
EXPECTED_CLEAN_EVENTS = 67257
EXPECTED_BASE_RATE = 0.08864393282993459

# Frozen 8 predictive features
ALLOWED_FEATURES = [
    "return_5",
    "atr_pct_14",
    "return_20",
    "return_60",
    "close_vs_sma20",
    "close_vs_sma60",
    "sma20_slope_5",
    "relative_volume_20",
]

EXCLUDED_FEATURES = [
    "proximity_high20",
    "proximity_high60",
    "true_range_compression_5_20",
    "dollar_volume_trend_20_60",
    "up_volume_share_20",
    "spy_return_20",
    "stock_minus_spy_20",
]

# Random seed
DETERMINISTIC_SEED = 20261005

# Search budget
ROUND_1_BUDGET = 36
ROUND_2_MAX_BUDGET = 12
TOTAL_E_BUDGET = 48

# Bootstrap parameters
BOOTSTRAP_PRIMARY_BLOCK = 21
BOOTSTRAP_ROBUSTNESS_BLOCK = 42
BOOTSTRAP_REPLICATES = 1000

# Ranking K parameters
PRIMARY_K = 10
SECONDARY_K = 25


def compute_file_sha256(path: Path) -> str:
    """Compute the SHA-256 digest of a file in streaming chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_spec() -> dict[str, Any]:
    """Load and return the locked LONG-002E1 specification dictionary."""
    with SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_corr_spec() -> dict[str, Any]:
    """Load and return the locked LONG-002E1-CORR-001 correction specification dictionary."""
    with CORR_SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def verify_spec_integrity() -> None:
    """Verify that both committed specifications exist and match their locked hashes."""
    if not SPEC_PATH.exists():
        raise FileNotFoundError(f"Preregistration specification missing at {SPEC_PATH}")
    current_sha = compute_file_sha256(SPEC_PATH)
    if current_sha != EXPECTED_SPEC_SHA256:
        raise ValueError(
            f"SPECIFICATION INTEGRITY BREACH: Spec SHA {current_sha} != expected {EXPECTED_SPEC_SHA256}"
        )

    if not CORR_SPEC_PATH.exists():
        raise FileNotFoundError(f"Correction specification missing at {CORR_SPEC_PATH}")
    corr_sha = compute_file_sha256(CORR_SPEC_PATH)
    if corr_sha != EXPECTED_CORR_SPEC_SHA256:
        raise ValueError(
            f"CORRECTION SPEC INTEGRITY BREACH: Spec SHA {corr_sha} != expected {EXPECTED_CORR_SPEC_SHA256}"
        )
