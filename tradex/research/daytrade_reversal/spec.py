"""Locked specification loader and SHA-256 verifier for DAYTRADE-001B."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tradex.watchlists.presets import DOW30

DAYTRADE_001B_SPEC_SHA256 = (
    "0651e075ff0641510788582a67827e065347f851e9363964f85a193a3d166620"
)

LOCKED_UNIVERSE: tuple[str, ...] = DOW30


class SpecError(ValueError):
    """Raised when the study specification fails validation or hash check."""


@dataclass(frozen=True)
class SplitDates:
    """Start and end dates for a dataset split."""

    start: str
    end: str


@dataclass(frozen=True)
class DaytradeSpec:
    """Strongly typed representation of the locked DAYTRADE-001B specification."""

    task_id: str
    spec_version: int
    sha256: str
    universe: tuple[str, ...]
    warmup: SplitDates
    development: SplitDates
    validation: SplitDates
    holdout: SplitDates
    trailing_sessions: int
    quantile: float
    earliest_event_start: str
    latest_event_start: str
    primary_cost_bps_per_side: float
    bootstrap_resamples: int
    bootstrap_seed: int
    bootstrap_confidence_level_pct: float
    raw_dict: dict[str, Any]


def default_spec_path() -> Path:
    """Return the repository-relative path to the locked DAYTRADE-001B specification."""
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "docs" / "research" / "specs" / "DAYTRADE-001B-v1.json"


def sha256_of_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def load_and_verify_spec(
    spec_path: Path | None = None,
    expected_sha256: str = DAYTRADE_001B_SPEC_SHA256,
) -> DaytradeSpec:
    """Load and strictly verify the locked DAYTRADE-001B specification JSON.

    Fails closed if the file does not exist, cannot be parsed, does not match the
    locked SHA-256 hash, or has tampered universe or parameter definitions.
    """
    path = spec_path or default_spec_path()
    if not path.is_file():
        raise SpecError(f"Specification file not found at: {path}")

    raw_bytes = path.read_bytes()
    actual_sha256 = sha256_of_bytes(raw_bytes)
    if actual_sha256 != expected_sha256:
        raise SpecError(
            f"Locked specification SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except Exception as e:
        raise SpecError(f"Specification JSON is malformed: {e}") from e

    # Verify task identity and governance
    if data.get("task_id") != "DAYTRADE-001B":
        raise SpecError(f"Unexpected task_id in specification: {data.get('task_id')}")

    # Verify universe
    universe_symbols = tuple(data.get("universe", {}).get("symbols", []))
    if universe_symbols != LOCKED_UNIVERSE:
        raise SpecError(
            f"Universe symbols mismatch locked DOW30 preset: count {len(universe_symbols)} vs {len(LOCKED_UNIVERSE)}"
        )

    # Verify splits
    dates = data.get("dates_and_splits", {})
    try:
        warmup = SplitDates(dates["warmup"]["start"], dates["warmup"]["end"])
        dev = SplitDates(dates["development"]["start"], dates["development"]["end"])
        val = SplitDates(dates["validation"]["start"], dates["validation"]["end"])
        holdout = SplitDates(dates["holdout"]["start"], dates["holdout"]["end"])
    except KeyError as e:
        raise SpecError(f"Missing required split date definition: {e}") from e

    # Verify quantile and window
    event_def = data.get("event_definition", {})
    trailing_sessions = event_def.get("trailing_window_sessions", 20)
    quantile = float(event_def.get("quantile", 0.001))
    if quantile != 0.001:
        raise SpecError(f"Invalid quantile {quantile}; must be 0.001")

    timing = data.get("eligibility_and_timing", {})
    earliest = timing.get("earliest_event_bar_start", "09:31")
    latest = timing.get("latest_event_bar_start", "15:54")

    # Friction
    friction = data.get("execution_friction", {})
    primary_cost = float(friction.get("primary_cost_bps_per_side", 2.0))

    # Bootstrap
    inference = data.get("statistical_inference", {})
    resamples = int(inference.get("bootstrap_resamples", 2000))
    seed = int(inference.get("random_seed", 20260925))
    ci_level = float(inference.get("confidence_level_pct", 95.0))

    return DaytradeSpec(
        task_id=data["task_id"],
        spec_version=int(data.get("spec_version", 1)),
        sha256=actual_sha256,
        universe=universe_symbols,
        warmup=warmup,
        development=dev,
        validation=val,
        holdout=holdout,
        trailing_sessions=trailing_sessions,
        quantile=quantile,
        earliest_event_start=earliest,
        latest_event_start=latest,
        primary_cost_bps_per_side=primary_cost,
        bootstrap_resamples=resamples,
        bootstrap_seed=seed,
        bootstrap_confidence_level_pct=ci_level,
        raw_dict=data,
    )
