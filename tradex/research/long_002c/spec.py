"""Specification verification and split guard for LONG-002C.

Verifies upstream specification hashes and enforces strict development-only split boundaries.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "docs" / "research" / "specs" / "LONG-002C-design-v1.json"

WARMUP_START = "2015-01-01"
WARMUP_END = "2015-12-31"
DEV_START = "2016-01-01"
DEV_END = "2020-12-31"

VALIDATION_START = "2021-01-01"
VALIDATION_END = "2022-12-31"
HOLDOUT_START = "2023-01-01"
HOLDOUT_END = "2025-12-31"
SHADOW_START = "2026-01-01"

TARGET_GRID: list[tuple[float, int]] = [
    (10.0, 5),
    (10.0, 10),
    (10.0, 21),
    (20.0, 5),
    (20.0, 10),
    (20.0, 21),
    (30.0, 5),
    (30.0, 10),
    (30.0, 21),
]

PRIMARY_ENDPOINT = (10.0, 10)
FEASIBILITY_FALLBACK_ENDPOINT = (10.0, 21)

PRIMARY_ENTRY_FRICTION_BPS = 10.0
SENSITIVITY_FRICTION_BPS = [5.0, 25.0]
STRESS_FRICTION_BPS = 50.0

MAX_ENTRY_WINDOW_SESSIONS = 5
MAX_OUTCOME_HORIZON_SESSIONS = 21
TOTAL_FORWARD_SESSIONS_REQUIRED = 26


class SplitGuardViolationError(RuntimeError):
    """Raised when an operation attempts to access post-development (2021+) records."""


class SpecVerificationError(RuntimeError):
    """Raised when upstream specification hashes mismatch."""


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_long_002c_spec() -> dict[str, Any]:
    """Load the machine-readable LONG-002C design specification."""
    if not SPEC_PATH.exists():
        raise FileNotFoundError(f"Missing spec: {SPEC_PATH}")
    with SPEC_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def verify_upstream_spec_hashes() -> dict[str, str]:
    """Verify all 11 referenced upstream specification hashes match repository files."""
    spec = load_long_002c_spec()
    hashes = spec.get("upstream_spec_hashes", {})
    verified: dict[str, str] = {}
    mismatches: list[str] = []

    for rel_path, expected_sha in hashes.items():
        file_path = REPO_ROOT / rel_path
        if not file_path.exists():
            mismatches.append(f"Missing upstream file: {rel_path}")
            continue
        actual_sha = compute_sha256(file_path)
        if actual_sha != expected_sha:
            mismatches.append(
                f"SHA mismatch for {rel_path}: expected {expected_sha}, got {actual_sha}"
            )
        else:
            verified[rel_path] = actual_sha

    if mismatches:
        raise SpecVerificationError("; ".join(mismatches))

    return verified


def enforce_split_guard(date_or_path: str | Path) -> None:
    """Enforce fail-closed quarantine against validation/holdout/shadow data.

    Raises SplitGuardViolationError if the date or path indicates access to 2021-01-01 onward.
    """
    str_val = str(date_or_path)

    # Check for date string format YYYY-MM-DD
    if len(str_val) >= 10 and str_val[:4].isdigit():
        year = int(str_val[:4])
        if year >= 2021:
            raise SplitGuardViolationError(
                f"Access prohibited: Date {str_val} is in quarantined split (2021+). LONG-002C is development-only (2016-2020)."
            )

    # Check for path strings containing quarantined years or split names
    quarantined_tokens = [
        "validation",
        "holdout",
        "shadow_replay",
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
        "2026",
    ]
    lower_path = str_val.lower().replace("\\", "/")
    # If path explicitly refers to data files for 2021+
    for token in quarantined_tokens:
        if f"/{token}/" in lower_path or f"_{token}_" in lower_path or f"-{token}-" in lower_path:
            raise SplitGuardViolationError(
                f"Access prohibited: Path {str_val} references quarantined split token '{token}'."
            )
