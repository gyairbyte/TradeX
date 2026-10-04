"""Preregistered specification constants and schemas for LONG-002D2."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002D2-v1.json"
EXPECTED_SPEC_SHA256 = "db82482333fb0c9810279d289e87e82e7274802fae82269cbf1b63c7ad2a6fb8"

TASK_ID = "LONG-002D2-INCREMENTAL-RERANK-001"
PROGRAM = "LONG-002"
PHASE = "LONG-002D2"

# Population and bounds
DEV_START = "2016-01-01"
DEV_END = "2020-12-31"
POPULATION_CUTOFF = "20:30"
TARGET_PCT = 10.0
HORIZON_SESSIONS = 10
LABEL_COLUMN = "clean_target_reached"

# Expected upstream hashes
D1_FEATURE_TABLE_PATH = Path("data/research/long_002d1/feature_table.parquet")
D1_FEATURE_TABLE_SHA256 = "7dc09bdeed02c44eb48a0143884deb0ad7795466a08e25fd26c32640a0c813d8"

STAGE_C_BASELINE_PATH = Path("data/research/long_002c/baseline_comparator_outputs.parquet")
STAGE_C_BASELINE_SHA256 = "faec26ddb26fd5a17feddf5ae09232a8aeb8ba24c3529abd88422682357e4734"

STAGE_C_OUTCOME_PATH = Path("data/research/long_002c/outcome_matrix.parquet")
STAGE_C_OUTCOME_SHA256 = "b59a5f7f8a8a0498abdadb156299719f43ffa8854df5cad8e20a6cd4fbe237c3"

EXPECTED_DENOMINATOR = 758731
EXPECTED_CLEAN_EVENTS = 67257
EXPECTED_BASE_RATE = 0.088644

# Frozen baseline metadata
FROZEN_BASELINE_ID = "volatility_aware_momentum_5"
FROZEN_BASELINE_TOP_10_COUNT = 76407
FROZEN_BASELINE_TOP_10_CLEAN_COUNT = 11731
FROZEN_BASELINE_TOP_10_CLEAN_RATE = 0.153533
FROZEN_BASELINE_TOP_10_LIFT = 1.7320

FROZEN_BASELINE_TOP_25_COUNT = 190288
FROZEN_BASELINE_TOP_25_CLEAN_COUNT = 24144
FROZEN_BASELINE_TOP_25_CLEAN_RATE = 0.126881
FROZEN_BASELINE_TOP_25_LIFT = 1.4314

# Candidate feature IDs
PRIMARY_CANDIDATE_ID = "relative_volume_20"
CHALLENGER_ID = "sma20_slope_5"
REGIME_DIAGNOSTIC_ID = "spy_return_20"

# Bootstrap configuration
BOOTSTRAP_PRIMARY_BLOCK_SIZE = 21
BOOTSTRAP_ROBUSTNESS_BLOCK_SIZE = 42
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = 20260928

# Allowed statuses
STATUS_SUPPORTED = "supported_for_next_stage"
STATUS_INCONCLUSIVE = "inconclusive"
STATUS_NOT_SUPPORTED = "not_supported"
STATUS_INVALID_DATA_CONTRACT = "invalid_data_contract"

ALLOWED_STATUSES = (
    STATUS_SUPPORTED,
    STATUS_INCONCLUSIVE,
    STATUS_NOT_SUPPORTED,
    STATUS_INVALID_DATA_CONTRACT,
)


@dataclass(frozen=True)
class CandidateSpec:
    """Specification for a candidate feature evaluated in D2."""

    feature_id: str
    role: str
    hypothesized_direction: str
    formula: str


PRIMARY_CANDIDATE_SPEC = CandidateSpec(
    feature_id=PRIMARY_CANDIDATE_ID,
    role="primary_candidate",
    hypothesized_direction="HIGHER",
    formula="volume_t / median(volume over PRIOR 20 completed sessions, excluding t)",
)

SECONDARY_CHALLENGER_SPEC = CandidateSpec(
    feature_id=CHALLENGER_ID,
    role="secondary_challenger",
    hypothesized_direction="HIGHER",
    formula="SMA20_t / SMA20_t-5 - 1",
)


def load_spec_payload(spec_path: Path | None = None) -> dict[str, Any]:
    """Load and return the machine-readable preregistered specification."""
    p = spec_path or SPEC_PATH
    if not p.exists():
        raise FileNotFoundError(f"Preregistration spec not found at {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def verify_spec_integrity(spec_path: Path | None = None) -> str:
    """Compute and verify the SHA-256 digest of the preregistered spec."""
    p = spec_path or SPEC_PATH
    if not p.exists():
        raise FileNotFoundError(f"Preregistration spec not found at {p}")
    content = p.read_bytes()
    computed_sha = hashlib.sha256(content).hexdigest()
    if computed_sha != EXPECTED_SPEC_SHA256:
        raise ValueError(
            f"SPEC INTEGRITY VIOLATION: Computed {computed_sha} != expected {EXPECTED_SPEC_SHA256}"
        )
    return computed_sha


def enforce_split_guard(as_of_date: str) -> None:
    """Enforce strict quarantine guard: reject any date outside the development split."""
    if as_of_date < DEV_START or as_of_date > DEV_END:
        raise ValueError(
            f"SPLIT QUARANTINE BREACH: as_of_date '{as_of_date}' outside development split "
            f"[{DEV_START}, {DEV_END}]. Validation (2021-2022), holdout (2023-2025), "
            "and shadow (2026+) splits are strictly quarantined."
        )


def enforce_cutoff_guard(cutoff_time: str) -> None:
    """Enforce cutoff guard: only 20:30 is in scope for D2."""
    if cutoff_time != POPULATION_CUTOFF:
        raise ValueError(
            f"CUTOFF GUARD BREACH: cutoff_time '{cutoff_time}' != expected '{POPULATION_CUTOFF}'."
        )


def evaluate_relative_volume_status(
    pooled_precision_delta: float,
    ci_2_5_block_21: float,
    ci_97_5_block_21: float,
    median_block_42: float,
    annual_positive_delta_years: int,
    all_integrity_gates_passed: bool,
) -> str:
    """Evaluate primary relative-volume decision status strictly under locked preregistered rules.

    Rules:
    - invalid_data_contract if integrity gates fail.
    - supported_for_next_stage requires ALL:
        1. pooled_precision_delta > 0
        2. ci_2_5_block_21 > 0
        3. annual_positive_delta_years >= 4 (out of 5)
        4. median_block_42 > 0
        5. all_integrity_gates_passed == True
    - not_supported applies only if clear contrary evidence exists:
        EITHER:
            ci_97_5_block_21 <= 0
        OR:
            pooled_precision_delta <= 0 AND annual_positive_delta_years <= 2
    - All other outcomes:
        inconclusive
    """
    if not all_integrity_gates_passed:
        return STATUS_INVALID_DATA_CONTRACT

    is_supported = (
        pooled_precision_delta > 0.0
        and ci_2_5_block_21 > 0.0
        and annual_positive_delta_years >= 4
        and median_block_42 > 0.0
    )
    if is_supported:
        return STATUS_SUPPORTED

    is_not_supported = (ci_97_5_block_21 <= 0.0) or (
        pooled_precision_delta <= 0.0 and annual_positive_delta_years <= 2
    )
    if is_not_supported:
        return STATUS_NOT_SUPPORTED

    return STATUS_INCONCLUSIVE
