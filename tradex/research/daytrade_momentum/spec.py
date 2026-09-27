"""Locked specification loader and SHA-256 verifier for DAYTRADE-002A."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DAYTRADE_002A_SPEC_SHA256 = (
    "dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127"
)

LOCKED_FROZEN_UNIVERSE: tuple[str, ...] = (
    "XLK", "XLV", "XLF", "XLY", "XLP",
    "XLE", "XLI", "XLB", "XLU", "XLRE",
    "XLC", "SPY", "QQQ", "IWM", "DIA",
)


class SpecError(ValueError):
    """Raised when the study specification fails validation or hash check."""


@dataclass(frozen=True)
class SplitDates:
    """Start and end dates for a dataset split."""

    start: str
    end: str


@dataclass(frozen=True)
class DaytradeSpec:
    """Strongly typed representation of the locked DAYTRADE-002A specification."""

    task_id: str
    spec_version: int
    sha256: str
    universe: tuple[str, ...]
    context_anchor_date: str
    warmup: SplitDates
    development: SplitDates
    validation: SplitDates
    holdout: SplitDates
    trailing_sessions: int
    quantile: float
    percentile: float
    quantile_method: str
    entry_bar: str
    exit_bar: str
    primary_cost_bps_per_side: float
    bootstrap_resamples: int
    bootstrap_seed: int
    bootstrap_confidence_level_pct: float
    bootstrap_cluster_variable: str
    raw_dict: dict[str, Any]

    def get_split_dates(self, split_name: str) -> SplitDates:
        """Return the locked start and end dates for a supported evaluation split.

        Note: Warmup is not an evaluatable performance split.
        """
        name = split_name.lower().strip()
        if name == "development":
            return self.development
        elif name == "validation":
            return self.validation
        elif name == "holdout":
            return self.holdout
        elif name == "warmup":
            raise ValueError(
                "Warmup is history-only and cannot be evaluated as a target performance split."
            )
        raise ValueError(
            f"Unsupported split name '{split_name}'. Must be 'development', 'validation', or 'holdout'."
        )

    get_evaluatable_split_dates = get_split_dates

    def get_history_dates(self, split_name: str) -> tuple[str, str] | None:
        """Return (history_start, history_end) for historical context preceding the split.

        The locked rule requires threshold(D) to be computed over exactly the previous 20
        VALID completed regular sessions. History loading must provide enough earlier authorized
        observations (walking back into earlier authorized splits as needed) to find 20 valid observations.
        - Development: 2025-12-31 context anchor through 2026-01-30 warmup
        - Validation: 2025-12-31 context anchor through 2026-04-30 development
        - Holdout: 2025-12-31 context anchor through 2026-06-30 validation (entire preholdout)
        """
        name = split_name.lower().strip()
        if name == "development":
            return (self.context_anchor_date, self.warmup.end)
        elif name == "validation":
            return (self.context_anchor_date, self.development.end)
        elif name == "holdout":
            return (self.context_anchor_date, self.validation.end)
        return None

    def get_split_end_datetime(self, split_name: str) -> datetime:
        """Return the exact regular session close in UTC (16:00 ET) on the split end date."""
        split_dates = self.get_split_dates(split_name)
        end_d = date.fromisoformat(split_dates.end)
        dt_local = datetime.combine(end_d, time(16, 0), tzinfo=ZoneInfo("America/New_York"))
        return dt_local.astimezone(UTC)


def default_spec_path() -> Path:
    """Return the repository-relative path to the locked DAYTRADE-002A specification."""
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "docs" / "research" / "specs" / "DAYTRADE-002A-v1.json"


def sha256_of_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def load_and_verify_spec(
    spec_path: Path | None = None,
    expected_sha256: str = DAYTRADE_002A_SPEC_SHA256,
) -> DaytradeSpec:
    """Load and strictly verify the locked DAYTRADE-002A specification JSON.

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
    if data.get("task_id") != "DAYTRADE-002A":
        raise SpecError(f"Unexpected task_id in specification: {data.get('task_id')}")

    # Verify universe matches locked frozen snapshot directly (not mutable presets)
    universe_symbols = tuple(data.get("universe", {}).get("symbols", []))
    if universe_symbols != LOCKED_FROZEN_UNIVERSE:
        raise SpecError(
            f"Universe symbols mismatch locked 15 ETF snapshot: count {len(universe_symbols)} vs {len(LOCKED_FROZEN_UNIVERSE)}"
        )

    # Verify splits
    dates = data.get("dates_and_splits", {})
    try:
        anchor_date = dates["context_anchor"]["date"]
        warmup = SplitDates(dates["warmup"]["start"], dates["warmup"]["end"])
        dev = SplitDates(dates["development"]["start"], dates["development"]["end"])
        val = SplitDates(dates["validation"]["start"], dates["validation"]["end"])
        holdout = SplitDates(dates["holdout"]["start"], dates["holdout"]["end"])
    except KeyError as e:
        raise SpecError(f"Missing required split date definition: {e}") from e

    # Verify threshold definition
    signal_def = data.get("signal_definition", {})
    thresh_def = signal_def.get("threshold_definition", {})
    trailing_sessions = 20
    quantile = float(thresh_def.get("quantile", 0.80))
    percentile = float(thresh_def.get("percentile", 80.0))
    method = thresh_def.get("method", "linear")

    if quantile != 0.80 or percentile != 80.0 or method != "linear":
        raise SpecError(f"Invalid threshold configuration: quantile={quantile}, method={method}")

    # Verify execution timing
    timing = data.get("execution_and_outcomes", {}).get("timing", {})
    entry_bar = timing.get("entry_bar_start", "15:30")
    exit_bar = timing.get("exit_bar_start", "15:59")

    # Verify friction
    friction = data.get("execution_friction", {})
    primary_cost = float(friction.get("primary_cost_bps_per_side", 2.0))

    # Verify statistical inference
    inference = data.get("statistical_inference", {})
    resamples = int(inference.get("bootstrap_resamples", 2000))
    seed = int(inference.get("random_seed", 20260926))
    ci_level = float(inference.get("confidence_level_pct", 95.0))
    cluster_var = inference.get("cluster_variable", "session_date")
    if cluster_var != "session_date":
        raise SpecError(f"Invalid bootstrap cluster variable {cluster_var}; must be 'session_date'")

    # Verify session semantics
    session_sem = data.get("session_semantics", {})
    if session_sem.get("official_closing_auction_price_used") is not False:
        raise SpecError("Specification must explicitly lock official_closing_auction_price_used == False")

    return DaytradeSpec(
        task_id=data["task_id"],
        spec_version=int(data.get("spec_version", 1)),
        sha256=actual_sha256,
        universe=universe_symbols,
        context_anchor_date=anchor_date,
        warmup=warmup,
        development=dev,
        validation=val,
        holdout=holdout,
        trailing_sessions=trailing_sessions,
        quantile=quantile,
        percentile=percentile,
        quantile_method=method,
        entry_bar=entry_bar,
        exit_bar=exit_bar,
        primary_cost_bps_per_side=primary_cost,
        bootstrap_resamples=resamples,
        bootstrap_seed=seed,
        bootstrap_confidence_level_pct=ci_level,
        bootstrap_cluster_variable=cluster_var,
        raw_dict=data,
    )


def verify_spec(spec_path: Path | str | None = None) -> bool:
    """Load and verify specification, returning True if valid."""
    load_and_verify_spec(spec_path)
    return True
