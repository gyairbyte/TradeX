"""Locked probe-spec loading and validation for the reference provider probe."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReferenceProbeSpec:
    """Machine-readable INTRA-001B-reference probe specification."""

    schema_version: int
    task_id: str
    probe_version: int
    provider: str
    study_parent: str
    amendment_path: str
    original_strategy_spec_path: str
    expected_original_strategy_spec_sha256: str
    alpaca_v2_artifact_path: str
    probe_dates: tuple[str, ...]
    candidate_selection_order: tuple[str, ...]
    fallback_probe_dates: tuple[str, ...] = ()
    fallback_dataset_start: str | None = None
    fallback_dataset_end: str | None = None
    no_paid_upgrade: bool = True
    no_composite_reference_stack: bool = True
    alpha_vantage: dict[str, Any] = field(default_factory=dict)
    massive: dict[str, Any] = field(default_factory=dict)
    safe_artifact_schema_version: int = 1
    expected_safe_artifacts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "probe_version": self.probe_version,
            "provider": self.provider,
            "study_parent": self.study_parent,
            "amendment_path": self.amendment_path,
            "original_strategy_spec_path": self.original_strategy_spec_path,
            "expected_original_strategy_spec_sha256": self.expected_original_strategy_spec_sha256,
            "alpaca_v2_artifact_path": self.alpaca_v2_artifact_path,
            "probe_dates": list(self.probe_dates),
            "fallback_probe_dates": list(self.fallback_probe_dates),
            "fallback_dataset_start": self.fallback_dataset_start,
            "fallback_dataset_end": self.fallback_dataset_end,
            "candidate_selection_order": list(self.candidate_selection_order),
            "no_paid_upgrade": self.no_paid_upgrade,
            "no_composite_reference_stack": self.no_composite_reference_stack,
            "alpha_vantage": self.alpha_vantage,
            "massive": self.massive,
            "safe_artifact_schema_version": self.safe_artifact_schema_version,
            "expected_safe_artifacts": list(self.expected_safe_artifacts),
        }


class SpecValidationError(ValueError):
    """Raised when a probe spec violates the locked contract."""


def _as_tuple(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(p.strip() for p in value.split(",") if p.strip())
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    raise SpecValidationError(f"{name} must be a list of strings")


def load_probe_spec(path: str | Path) -> tuple[ReferenceProbeSpec, bytes]:
    """Load and validate a reference probe spec, returning the object and raw bytes."""
    p = Path(path).expanduser().resolve()
    raw = p.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise SpecValidationError("Probe spec must be a JSON object")

    required = {
        "schema_version",
        "task_id",
        "probe_version",
        "provider",
        "study_parent",
        "amendment_path",
        "original_strategy_spec_path",
        "expected_original_strategy_spec_sha256",
        "probe_dates",
        "candidate_selection_order",
        "no_paid_upgrade",
        "no_composite_reference_stack",
        "alpha_vantage",
        "massive",
        "safe_artifact_schema_version",
        "expected_safe_artifacts",
    }
    missing = required - set(data.keys())
    if missing:
        raise SpecValidationError(f"Probe spec missing fields: {sorted(missing)}")

    spec = ReferenceProbeSpec(
        schema_version=int(data["schema_version"]),
        task_id=str(data["task_id"]),
        probe_version=int(data["probe_version"]),
        provider=str(data["provider"]),
        study_parent=str(data["study_parent"]),
        amendment_path=str(data["amendment_path"]),
        original_strategy_spec_path=str(data["original_strategy_spec_path"]),
        expected_original_strategy_spec_sha256=str(data["expected_original_strategy_spec_sha256"]),
        alpaca_v2_artifact_path=str(data.get("alpaca_v2_artifact_path", "")),
        probe_dates=_as_tuple(data["probe_dates"], "probe_dates"),
        candidate_selection_order=_as_tuple(data["candidate_selection_order"], "candidate_selection_order"),
        fallback_probe_dates=_as_tuple(data.get("fallback_probe_dates", []), "fallback_probe_dates"),
        fallback_dataset_start=data.get("fallback_dataset_start"),
        fallback_dataset_end=data.get("fallback_dataset_end"),
        no_paid_upgrade=bool(data["no_paid_upgrade"]),
        no_composite_reference_stack=bool(data["no_composite_reference_stack"]),
        alpha_vantage=dict(data.get("alpha_vantage", {})),
        massive=dict(data.get("massive", {})),
        safe_artifact_schema_version=int(data["safe_artifact_schema_version"]),
        expected_safe_artifacts=_as_tuple(data["expected_safe_artifacts"], "expected_safe_artifacts"),
    )
    return spec, raw


def sha256_of_file(path: str | Path) -> str:
    """Return SHA-256 of a file's bytes."""
    return hashlib.sha256(Path(path).expanduser().resolve().read_bytes()).hexdigest()
