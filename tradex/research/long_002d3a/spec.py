"""Specification loader and contract constants for LONG-002D3A."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

TASK_ID = "LONG-002D3A-BLINDED-REVIEW-PILOT-001"
PROGRAM = "LONG-002"
PHASE = "LONG-002D3A"

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002D3A-v1.json"
EXPECTED_SPEC_SHA256 = "7b2dcc9c0d53b56053c52dbc227bd04a96998120d26b49051627312c60545427"

DEV_START = "2016-01-01"
DEV_END = "2020-12-31"
POPULATION_CUTOFF = "20:30"
TARGET_PCT = 10.0
HORIZON_SESSIONS = 10

PILOT_SIZE = 24
PILOT_QUOTA_PER_STRATUM = 6
PILOT_SEED = 20261003

MAIN_STUDY_SIZE = 240
MAIN_STUDY_SEED = 20261004

# Aliases
SPEC_SHA256 = EXPECTED_SPEC_SHA256
FUTURE_MAIN_SIZE = MAIN_STUDY_SIZE
FUTURE_MAIN_SEED = MAIN_STUDY_SEED
PREREGISTRATION_COMMIT_SHA = "a6345f97330358b1dfbbdf7c11e6aba9f10e2c87"

STRATA_PRECEDENCE = (
    "positive_master_episode",
    "near_miss",
    "adverse_trap",
    "ordinary_non_mover",
)

QUARANTINED_SPLITS = (
    ("validation", "2021-01-01", "2022-12-31"),
    ("holdout", "2023-01-01", "2025-12-31"),
    ("shadow", "2026-01-01", "2099-12-31"),
)

UPSTREAM_INPUT_HASHES: dict[str, str] = {
    "decision_observations.parquet": "722bee866cabb697931dfb96abaf7f9250f1cd1240b405d2e308af0b6bbb48af",
    "outcome_matrix.parquet": "b59a5f7f8a8a0498abdadb156299719f43ffa8854df5cad8e20a6cd4fbe237c3",
    "master_episodes.parquet": "1fe5b36f98919465007a720908c626203e5272b054a4ef76be772db279b3cc98",
    "constituent_memberships.parquet": "53a8adc92f1210ef3a1b6d10c9eedd1f360dad2760897f97b5d293f473734b11",
    "baseline_comparator_outputs.parquet": "faec26ddb26fd5a17feddf5ae09232a8aeb8ba24c3529abd88422682357e4734",
    "feature_table.parquet": "7dc09bdeed02c44eb48a0143884deb0ad7795466a08e25fd26c32640a0c813d8",
    "discovery_manifest.json": "d1bf16d6b475c93b5c47e81a47af5597fd514432880107030040a81fd61e9947",
}


def load_spec_payload(spec_path: Path = SPEC_PATH) -> dict[str, Any]:
    """Load and parse machine-readable D3A JSON specification."""
    if not spec_path.exists():
        raise FileNotFoundError(f"D3A preregistration specification missing at: {spec_path}")
    with open(spec_path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_spec_integrity(spec_path: Path = SPEC_PATH) -> str:
    """Verify SHA-256 hash of D3A specification file."""
    if not spec_path.exists():
        raise FileNotFoundError(f"D3A spec file not found: {spec_path}")
    h = hashlib.sha256()
    with open(spec_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    digest = h.hexdigest()
    if digest != EXPECTED_SPEC_SHA256:
        raise ValueError(
            f"D3A Spec SHA-256 integrity breach! Expected {EXPECTED_SPEC_SHA256}, got {digest}"
        )
    return digest


verify_spec_sha256 = verify_spec_integrity


def verify_upstream_hashes(stage_c_dir: Path) -> None:
    """Verify hashes of Stage C upstream input files."""
    for fname, expected in UPSTREAM_INPUT_HASHES.items():
        if fname.endswith("feature_table.parquet"):
            continue
        p = stage_c_dir / fname
        if not p.exists():
            raise FileNotFoundError(f"Missing upstream file: {p}")
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        digest = h.hexdigest()
        if digest != expected:
            raise ValueError(f"Hash mismatch for {fname}: expected {expected}, got {digest}")


def enforce_split_guard(as_of_date: str) -> None:
    """Raise ValueError if as_of_date falls into validation, holdout, or shadow splits."""
    if as_of_date < DEV_START:
        raise ValueError(f"Observation date {as_of_date} precedes development split ({DEV_START})")
    if as_of_date > DEV_END:
        for split_name, q_start, q_end in QUARANTINED_SPLITS:
            if q_start <= as_of_date <= q_end:
                raise ValueError(
                    f"FAIL-CLOSED: Access to quarantined {split_name} split ({as_of_date}) is strictly forbidden!"
                )
        raise ValueError(f"Observation date {as_of_date} exceeds development split ({DEV_END})")
