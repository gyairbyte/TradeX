"""Future main-study structural contract foundation and pilot isolation enforcement."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tradex.research.long_002d3a.spec import (
    MAIN_STUDY_SEED,
    MAIN_STUDY_SIZE,
    PILOT_SIZE,
)

MAIN_STUDY_STRATA_COUNTS: dict[str, int] = {
    "positive_master_episode": 120,
    "ordinary_non_mover": 40,
    "near_miss": 40,
    "adverse_trap": 40,
}

MAIN_STUDY_BATCH_COUNT = 12
MAIN_STUDY_BATCH_SIZE = 20
MAIN_STUDY_MAX_TICKER_FREQUENCY = 2


def get_main_study_contract_summary() -> dict[str, Any]:
    """Return locked machine-readable summary of the future 240-case main study contract."""
    return {
        "task_id": "LONG-002D3A-BLINDED-REVIEW-PILOT-001",
        "future_main_study_total_cases": MAIN_STUDY_SIZE,
        "future_main_study_seed": MAIN_STUDY_SEED,
        "strata_counts": dict(MAIN_STUDY_STRATA_COUNTS),
        "batching": {
            "total_batches": MAIN_STUDY_BATCH_COUNT,
            "batch_size": MAIN_STUDY_BATCH_SIZE,
        },
        "ticker_frequency_limit": MAIN_STUDY_MAX_TICKER_FREQUENCY,
        "pilot_exclusion_count": PILOT_SIZE,
        "main_sample_generated": False,
        "status": "LOCKED_FOUNDATION_UNGENERATED",
    }


def validate_pilot_exclusion_from_main(
    main_candidate_keys: list[tuple[str, str, str]],
    pilot_exclusion_keys: list[tuple[str, str, str]] | set[tuple[str, str, str]],
) -> None:
    """Fail closed if any pilot observation key appears in the future main candidate pool.

    Each key is (immutable_security_id, as_of_date, cutoff_time).
    """
    pilot_set = set(pilot_exclusion_keys)
    overlap = [k for k in main_candidate_keys if k in pilot_set]
    if overlap:
        raise ValueError(
            f"FAIL-CLOSED PILOT EXCLUSION BREACH: {len(overlap)} pilot observation keys "
            f"found in future main sample pool! Overlapping keys: {overlap[:5]}"
        )


def assert_main_study_not_generated(external_dir: Path | None = None) -> None:
    """Fail closed if any file indicates that the 240-case main study was generated in this PR."""
    if external_dir is not None:
        main_file = external_dir / "main_study_cases.json"
        main_key = external_dir / "main_answer_key.json"
        if main_file.exists() or main_key.exists():
            raise RuntimeError(
                "FAIL-CLOSED: Main study 240-case generation is UNAUTHORIZED in LONG-002D3A!"
            )


def load_pilot_exclusion_keys(
    exclusion_file: Path,
    expected_sha256: str | None = None,
) -> list[tuple[str, str, str]]:
    """Load and verify external pilot exclusion keys."""
    if not exclusion_file.exists():
        raise FileNotFoundError(f"FAIL-CLOSED: Exclusion keys file missing: {exclusion_file}")
    if expected_sha256:
        import hashlib
        h = hashlib.sha256()
        with open(exclusion_file, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        actual_sha = h.hexdigest()
        if actual_sha != expected_sha256:
            raise ValueError(
                f"FAIL-CLOSED: Exclusion keys SHA-256 mismatch! Expected {expected_sha256}, got {actual_sha}"
            )
    import json
    with open(exclusion_file, "r", encoding="utf-8") as f:
        records = json.load(f)
    if len(records) != PILOT_SIZE:
        raise ValueError(
            f"FAIL-CLOSED: Expected {PILOT_SIZE} exclusion keys, got {len(records)}"
        )
    return [
        (r["immutable_security_id"], r["as_of_date"], r["cutoff_time"])
        for r in records
    ]
