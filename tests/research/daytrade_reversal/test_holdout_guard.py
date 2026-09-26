"""Holdout protection guard and invocation isolation tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradex.research.daytrade_reversal.freeze import EvaluationFreezeRecord
from tradex.research.daytrade_reversal.study import (
    HoldoutAccessDeniedError,
    load_and_evaluate_holdout,
)


def _write_validation_artifacts(
    target_dir: Path,
    disposition: str = "supported",
    split: str = "validation",
    spec_sha: str = "0651e075ff0641510788582a67827e065347f851e9363964f85a193a3d166620",
) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    study_data = {
        "task_id": "DAYTRADE-001B",
        "split": split,
        "disposition": disposition,
        "disposition_step": "step_5_support" if disposition == "supported" else "step_3_directional_failure",
        "disposition_reason": "Test disposition",
    }
    (target_dir / "study.json").write_text(json.dumps(study_data), encoding="utf-8")
    (target_dir / "spec.lock.json").write_text(json.dumps({"sha256": spec_sha}), encoding="utf-8")


def test_holdout_loader_never_invoked_when_validation_not_supported(
    tmp_path: Path,
    locked_spec,
) -> None:
    """When validation disposition is 'inconclusive' or 'rejected', loader is NEVER invoked."""
    val_dir = tmp_path / "validation_inconclusive"
    _write_validation_artifacts(val_dir, disposition="inconclusive")

    loader_mock = MagicMock()

    with pytest.raises(HoldoutAccessDeniedError, match="validation disposition is 'inconclusive'"):
        load_and_evaluate_holdout(
            validation_artifact_dir=val_dir,
            spec=locked_spec,
            holdout_loader=loader_mock,
        )

    # CRITICAL: Loader itself must NEVER have been called!
    assert loader_mock.call_count == 0


def test_holdout_loader_never_invoked_when_validation_artifacts_missing(
    tmp_path: Path,
    locked_spec,
) -> None:
    """When validation directory or study.json is missing, loader is NEVER invoked."""
    missing_dir = tmp_path / "non_existent_val"
    loader_mock = MagicMock()

    with pytest.raises(HoldoutAccessDeniedError, match="does not exist"):
        load_and_evaluate_holdout(
            validation_artifact_dir=missing_dir,
            spec=locked_spec,
            holdout_loader=loader_mock,
        )

    assert loader_mock.call_count == 0


def test_holdout_loader_never_invoked_when_spec_sha_mismatches(
    tmp_path: Path,
    locked_spec,
) -> None:
    """When validation was run with a different spec hash, loader is NEVER invoked."""
    val_dir = tmp_path / "validation_mismatched_spec"
    _write_validation_artifacts(val_dir, disposition="supported", spec_sha="bad_sha_12345")

    loader_mock = MagicMock()

    with pytest.raises(HoldoutAccessDeniedError, match="Spec hash mismatch"):
        load_and_evaluate_holdout(
            validation_artifact_dir=val_dir,
            spec=locked_spec,
            holdout_loader=loader_mock,
        )

    assert loader_mock.call_count == 0


def test_holdout_loader_never_invoked_when_freeze_code_mismatches(
    tmp_path: Path,
    locked_spec,
) -> None:
    """When evaluation code freeze verification fails, loader is NEVER invoked."""
    val_dir = tmp_path / "validation_supported"
    _write_validation_artifacts(val_dir, disposition="supported")

    bad_freeze = EvaluationFreezeRecord(
        evaluation_code_sha="0000000000000000000000000000000000000000",
        repository_clean=True,
        frozen_at="2026-09-25T00:00:00Z",
        spec_sha256=locked_spec.sha256,
        manifest_sha256=None,
        evaluation_files={},
    )

    loader_mock = MagicMock()

    with pytest.raises(HoldoutAccessDeniedError, match="freeze check failed"):
        load_and_evaluate_holdout(
            validation_artifact_dir=val_dir,
            spec=locked_spec,
            holdout_loader=loader_mock,
            freeze_record=bad_freeze,
        )

    assert loader_mock.call_count == 0


def test_holdout_loader_invoked_when_all_prerequisites_pass(
    tmp_path: Path,
    locked_spec,
) -> None:
    """When validation is 'supported' and spec matches, holdout loader is safely invoked."""
    val_dir = tmp_path / "validation_supported"
    _write_validation_artifacts(val_dir, disposition="supported", spec_sha=locked_spec.sha256)

    loader_mock = MagicMock(return_value=[])

    result = load_and_evaluate_holdout(
        validation_artifact_dir=val_dir,
        spec=locked_spec,
        holdout_loader=loader_mock,
    )

    assert loader_mock.call_count == 1
    assert result.split == "holdout"
