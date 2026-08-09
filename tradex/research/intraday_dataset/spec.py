"""Locked dataset plan loading and validation for INTRA-001B-DATASET-V1."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _repo_relative(path: str | Path) -> str:
    """Return a relative repo-root path; fall back to a normalized absolute path if outside the repo."""
    p = Path(path).expanduser().resolve()
    try:
        return str(p.relative_to(_REPO_ROOT))
    except ValueError:
        return str(p)


@dataclass(frozen=True)
class DatasetPlan:
    """Machine-readable INTRA-001B one-year dataset plan."""

    schema_version: str
    task_id: str
    dataset_id: str
    study_parent: str
    original_strategy_spec_path: Path
    original_strategy_spec_sha256: str
    amendment_v3_path: Path
    amendment_v3_sha256: str
    v4_decision_doc_path: Path
    v4_decision_doc_sha256: str
    alpaca_v2_probe_spec_path: Path
    alpaca_v2_probe_spec_sha256: str
    provider_roles: dict[str, Any]
    dataset: dict[str, Any]
    monthly_pit_dates: tuple[str, ...]
    reference_snapshot_policy: dict[str, Any]
    conservative_universe_controls: dict[str, Any]
    etf_stratum: dict[str, Any]
    liquidity_ranking: dict[str, Any]
    ohlcv_policy: dict[str, Any]
    ranking_download_efficiency: dict[str, Any]
    data_quality_thresholds: dict[str, Any]
    retry_limits: dict[str, Any]
    estimated_resources: dict[str, Any]
    safe_artifact_policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "dataset_id": self.dataset_id,
            "study_parent": self.study_parent,
            "original_strategy_spec": {
                "path": _repo_relative(self.original_strategy_spec_path),
                "sha256": self.original_strategy_spec_sha256,
            },
            "data_sufficiency_amendment": {
                "path": _repo_relative(self.amendment_v3_path),
                "sha256": self.amendment_v3_sha256,
            },
            "reference_probe_evidence": {
                "v4_decision_document": _repo_relative(self.v4_decision_doc_path),
                "v4_decision_document_sha256": self.v4_decision_doc_sha256,
                "alpaca_v2_probe_spec": _repo_relative(self.alpaca_v2_probe_spec_path),
                "alpaca_v2_probe_spec_sha256": self.alpaca_v2_probe_spec_sha256,
            },
            "provider_roles": self.provider_roles,
            "dataset": self.dataset,
            "monthly_pit_dates": list(self.monthly_pit_dates),
            "reference_snapshot_policy": self.reference_snapshot_policy,
            "conservative_universe_controls": self.conservative_universe_controls,
            "etf_stratum": self.etf_stratum,
            "liquidity_ranking": self.liquidity_ranking,
            "ohlcv_policy": self.ohlcv_policy,
            "ranking_download_efficiency": self.ranking_download_efficiency,
            "data_quality_thresholds": self.data_quality_thresholds,
            "retry_limits": self.retry_limits,
            "estimated_resources": self.estimated_resources,
            "safe_artifact_policy": self.safe_artifact_policy,
        }


class SpecValidationError(ValueError):
    """Raised when a dataset plan violates the locked contract."""


def _as_tuple(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(p.strip() for p in value.split(",") if p.strip())
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    raise SpecValidationError(f"{name} must be a list of strings")


def sha256_of_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).expanduser().resolve().read_bytes()).hexdigest()


def load_dataset_plan(path: str | Path) -> tuple[DatasetPlan, bytes]:
    """Load and validate the dataset plan, returning the object and raw bytes."""
    p = Path(path).expanduser().resolve()
    raw = p.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise SpecValidationError("Dataset plan must be a JSON object")

    required_top = {
        "schema_version",
        "task_id",
        "dataset_id",
        "study_parent",
        "original_strategy_spec",
        "data_sufficiency_amendment",
        "reference_probe_evidence",
        "provider_roles",
        "dataset",
        "monthly_pit_dates",
        "reference_snapshot_policy",
        "conservative_universe_controls",
        "etf_stratum",
        "liquidity_ranking",
        "ohlcv_policy",
        "safe_artifact_policy",
    }
    missing = required_top - set(data.keys())
    if missing:
        raise SpecValidationError(f"Dataset plan missing top-level fields: {sorted(missing)}")

    original = data["original_strategy_spec"]
    amendment = data["data_sufficiency_amendment"]
    reference = data["reference_probe_evidence"]
    for key, label in [("path", "original path"), ("sha256", "original sha256")]:
        if key not in original:
            raise SpecValidationError(f"original_strategy_spec missing {label}")
    for key, label in [("path", "amendment path"), ("sha256", "amendment sha256")]:
        if key not in amendment:
            raise SpecValidationError(f"data_sufficiency_amendment missing {label}")
    for key in ("v4_decision_document", "v4_decision_document_sha256", "alpaca_v2_probe_spec", "alpaca_v2_probe_spec_sha256"):
        if key not in reference:
            raise SpecValidationError(f"reference_probe_evidence missing {key}")

    original_path = Path(original["path"]).expanduser().resolve()
    amendment_path = Path(amendment["path"]).expanduser().resolve()
    v4_path = Path(reference["v4_decision_document"]).expanduser().resolve()
    alpaca_v2_path = Path(reference["alpaca_v2_probe_spec"]).expanduser().resolve()

    for file_path, expected_sha, label in [
        (original_path, original["sha256"], "original strategy spec"),
        (amendment_path, amendment["sha256"], "amendment v3"),
        (v4_path, reference["v4_decision_document_sha256"], "V4 decision doc"),
        (alpaca_v2_path, reference["alpaca_v2_probe_spec_sha256"], "Alpaca v2 probe spec"),
    ]:
        if not file_path.exists():
            raise SpecValidationError(f"{label} not found: {file_path}")
        actual = sha256_of_file(file_path)
        if actual != expected_sha:
            raise SpecValidationError(
                f"{label} SHA-256 mismatch: expected {expected_sha}, got {actual}"
            )

    plan = DatasetPlan(
        schema_version=str(data["schema_version"]),
        task_id=str(data["task_id"]),
        dataset_id=str(data["dataset_id"]),
        study_parent=str(data["study_parent"]),
        original_strategy_spec_path=original_path,
        original_strategy_spec_sha256=original["sha256"],
        amendment_v3_path=amendment_path,
        amendment_v3_sha256=amendment["sha256"],
        v4_decision_doc_path=v4_path,
        v4_decision_doc_sha256=reference["v4_decision_document_sha256"],
        alpaca_v2_probe_spec_path=alpaca_v2_path,
        alpaca_v2_probe_spec_sha256=reference["alpaca_v2_probe_spec_sha256"],
        provider_roles=dict(data.get("provider_roles", {})),
        dataset=dict(data.get("dataset", {})),
        monthly_pit_dates=_as_tuple(data["monthly_pit_dates"], "monthly_pit_dates"),
        reference_snapshot_policy=dict(data.get("reference_snapshot_policy", {})),
        conservative_universe_controls=dict(data.get("conservative_universe_controls", {})),
        etf_stratum=dict(data.get("etf_stratum", {})),
        liquidity_ranking=dict(data.get("liquidity_ranking", {})),
        ohlcv_policy=dict(data.get("ohlcv_policy", {})),
        ranking_download_efficiency=dict(data.get("ranking_download_efficiency", {})),
        data_quality_thresholds=dict(data.get("data_quality_thresholds", {})),
        retry_limits=dict(data.get("retry_limits", {})),
        estimated_resources=dict(data.get("estimated_resources", {})),
        safe_artifact_policy=dict(data.get("safe_artifact_policy", {})),
    )
    return plan, raw
