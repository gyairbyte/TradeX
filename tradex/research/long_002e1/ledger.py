"""Append-only experiment ledger generation and audit schema for LONG-002E1."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class LedgerRecord:
    """Experiment ledger record schema for a material configuration attempt."""

    configuration_id: str
    family: str
    feature_subset: str
    hyperparameters_or_weights: dict[str, Any]
    attempt_number: int
    budget_slot: int
    status: str
    failure_reason_if_any: str | None
    folds_attempted: int
    folds_completed: int
    input_hashes: dict[str, str]
    preregistration_spec_sha: str
    execution_code_sha: str
    primary_metrics: dict[str, Any]
    robustness_metrics: dict[str, Any]
    created_at_or_run_reference: str


def write_experiment_ledger(
    records: list[LedgerRecord],
    output_path: Path,
) -> None:
    """Write experiment ledger records to JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(asdict(rec)) + "\n")
