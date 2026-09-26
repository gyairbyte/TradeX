"""Holdout protection guard and invocation isolation tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradex.research.daytrade_reversal.artifacts import write_artifact_bundle
from tradex.research.daytrade_reversal.dataset import DaytradeDatasetManifest
from tradex.research.daytrade_reversal.freeze import EvaluationFreezeRecord
from tradex.research.daytrade_reversal.models import GateEvaluationResult, StudyResult
from tradex.research.daytrade_reversal.spec import DaytradeSpec
from tradex.research.daytrade_reversal.study import (
    HoldoutAccessDeniedError,
    load_and_evaluate_holdout,
)


def _build_valid_validation_bundle(
    target_dir: Path,
    spec: DaytradeSpec,
    disposition: str = "supported",
    evaluator_code_sha: str = "head1234567890abcdef1234567890abcdef1234",
    spec_sha: str | None = None,
) -> tuple[StudyResult, EvaluationFreezeRecord, DaytradeDatasetManifest]:
    target_dir.mkdir(parents=True, exist_ok=True)
    effective_spec_sha = spec_sha or spec.sha256

    manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=effective_spec_sha,
        partition="preholdout",
        start_date=spec.warmup.start,
        end_date=spec.validation.end,
        universe=list(spec.universe),
        source_files={f"bars/{t}.csv": "a" * 64 for t in spec.universe},
    )
    manifest_data = manifest.to_dict()
    manifest_sha = manifest_data["manifest_sha256"]
    manifest.manifest_sha256 = manifest_sha

    freeze_record = EvaluationFreezeRecord(
        evaluation_code_sha=evaluator_code_sha,
        repository_clean=True,
        frozen_at="2026-09-25T00:00:00Z",
        spec_sha256=effective_spec_sha,
        manifest_sha256=manifest_sha,
        evaluation_files={},
    )

    provenance = {
        "evidence_confidence_cap": "limited_but_usable_evidence",
        "production_promotion_eligible": False,
        "evaluator_code_sha": evaluator_code_sha,
        "spec_sha256": effective_spec_sha,
        "manifest_sha256": manifest_sha,
        "provider": "alpaca",
        "feed": "sip",
    }

    result = StudyResult(
        task_id="DAYTRADE-001B",
        split="validation",
        disposition=disposition,
        disposition_step="step_5_support" if disposition == "supported" else "step_2_evidence_sufficiency",
        disposition_reason="Test disposition reason",
        gates={
            "data_quality_gate": GateEvaluationResult("data_quality_gate", True, {}),
            "step_2_evidence_sufficiency": GateEvaluationResult("step_2_evidence_sufficiency", True, {}),
        },
        metrics={"event_count": 50},
        bootstrap={},
        provenance=provenance,
    )

    write_artifact_bundle(
        output_dir=target_dir,
        result=result,
        spec=spec,
        freeze_record=freeze_record,
        manifest_data=manifest.to_dict(),
    )

    return result, freeze_record, manifest


def test_holdout_loader_never_invoked_when_validation_not_supported(
    tmp_path: Path,
    locked_spec,
    monkeypatch,
) -> None:
    """When validation disposition is 'inconclusive' or 'rejected', loader is NEVER invoked."""
    val_dir = tmp_path / "validation_inconclusive"
    _build_valid_validation_bundle(val_dir, locked_spec, disposition="inconclusive")
    monkeypatch.setattr("tradex.research.daytrade_reversal.study.verify_freeze_state", lambda *a, **kw: None)

    loader_mock = MagicMock()

    with pytest.raises(HoldoutAccessDeniedError, match="must be strictly 'supported'"):
        load_and_evaluate_holdout(
            validation_artifact_dir=val_dir,
            spec=locked_spec,
            holdout_loader=loader_mock,
        )

    assert loader_mock.call_count == 0


def test_holdout_loader_never_invoked_when_validation_artifacts_missing(
    tmp_path: Path,
    locked_spec,
) -> None:
    """When validation directory or checksums.sha256 is missing, loader is NEVER invoked."""
    missing_dir = tmp_path / "non_existent_val"
    loader_mock = MagicMock()

    with pytest.raises(HoldoutAccessDeniedError, match="does not exist"):
        load_and_evaluate_holdout(
            validation_artifact_dir=missing_dir,
            spec=locked_spec,
            holdout_loader=loader_mock,
        )

    assert loader_mock.call_count == 0


def test_holdout_loader_never_invoked_when_checksums_tampered(
    tmp_path: Path,
    locked_spec,
    monkeypatch,
) -> None:
    """When any file checksum does not match, loader is NEVER invoked."""
    val_dir = tmp_path / "validation_tampered"
    _build_valid_validation_bundle(val_dir, locked_spec, disposition="supported")
    monkeypatch.setattr("tradex.research.daytrade_reversal.study.verify_freeze_state", lambda *a, **kw: None)

    # Tamper study.json after checksums written
    study_file = val_dir / "study.json"
    content = json.loads(study_file.read_text(encoding="utf-8"))
    content["disposition"] = "supported"
    content["extra"] = "tampered"
    study_file.write_text(json.dumps(content), encoding="utf-8")

    loader_mock = MagicMock()
    with pytest.raises(HoldoutAccessDeniedError, match="Checksum mismatch"):
        load_and_evaluate_holdout(
            validation_artifact_dir=val_dir,
            spec=locked_spec,
            holdout_loader=loader_mock,
        )

    assert loader_mock.call_count == 0


def test_holdout_loader_never_invoked_when_spec_sha_mismatches(
    tmp_path: Path,
    locked_spec,
    monkeypatch,
) -> None:
    """When validation was run with a different spec hash, loader is NEVER invoked."""
    val_dir = tmp_path / "validation_mismatched_spec"
    _build_valid_validation_bundle(val_dir, locked_spec, disposition="supported", spec_sha="bad_sha_12345")
    monkeypatch.setattr("tradex.research.daytrade_reversal.study.verify_freeze_state", lambda *a, **kw: None)

    loader_mock = MagicMock()

    with pytest.raises(HoldoutAccessDeniedError, match=r"(?i)spec.*mismatch"):
        load_and_evaluate_holdout(
            validation_artifact_dir=val_dir,
            spec=locked_spec,
            holdout_loader=loader_mock,
        )

    assert loader_mock.call_count == 0


def test_holdout_loader_never_invoked_when_freeze_code_mismatches(
    tmp_path: Path,
    locked_spec,
    monkeypatch,
) -> None:
    """When evaluation code freeze verification fails, loader is NEVER invoked."""
    val_dir = tmp_path / "validation_bad_freeze"
    _build_valid_validation_bundle(val_dir, locked_spec, disposition="supported")

    # Force verify_freeze_state to raise FreezeError
    from tradex.research.daytrade_reversal.freeze import FreezeError

    def fail_freeze(*a, **kw):
        raise FreezeError("Evaluator code SHA mismatch")

    monkeypatch.setattr("tradex.research.daytrade_reversal.study.verify_freeze_state", fail_freeze)

    loader_mock = MagicMock()

    with pytest.raises(HoldoutAccessDeniedError, match="evaluator code freeze check failed"):
        load_and_evaluate_holdout(
            validation_artifact_dir=val_dir,
            spec=locked_spec,
            holdout_loader=loader_mock,
        )

    assert loader_mock.call_count == 0


def test_holdout_loader_invoked_when_all_prerequisites_pass(
    tmp_path: Path,
    locked_spec,
    monkeypatch,
) -> None:
    """When validation is 'supported' and all prerequisites pass, holdout loader is safely invoked."""
    val_dir = tmp_path / "validation_supported"
    _build_valid_validation_bundle(val_dir, locked_spec, disposition="supported")
    monkeypatch.setattr("tradex.research.daytrade_reversal.study.verify_freeze_state", lambda *a, **kw: None)

    loader_mock = MagicMock(return_value=[])

    result = load_and_evaluate_holdout(
        validation_artifact_dir=val_dir,
        spec=locked_spec,
        holdout_loader=loader_mock,
    )

    assert loader_mock.call_count == 1
    assert result.split == "holdout"
