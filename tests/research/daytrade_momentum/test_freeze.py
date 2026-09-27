"""Tests for evaluation code freeze, clean worktree verification, and tamper detection."""
from __future__ import annotations

import pytest

from tradex.research.daytrade_momentum.dataset import DaytradeDatasetManifest
from tradex.research.daytrade_momentum.freeze import (
    EvaluationFreezeRecord,
    FreezeError,
    freeze_evaluation_state,
    verify_freeze_state,
)
from tradex.research.daytrade_momentum.spec import DaytradeSpec


def test_freeze_creation_and_roundtrip(locked_spec: DaytradeSpec) -> None:
    """Verify freeze record captures state, file digests, and serializes roundtrip."""
    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256="mock_manifest_sha_12345",
        require_clean=False,
    )

    assert freeze.spec_sha256 == locked_spec.sha256
    assert freeze.manifest_sha256 == "mock_manifest_sha_12345"
    assert len(freeze.evaluation_files) > 0

    # Serialization roundtrip
    d = freeze.to_dict()
    restored = EvaluationFreezeRecord.from_dict(d)
    assert restored.evaluation_code_sha == freeze.evaluation_code_sha
    assert restored.evaluation_files == freeze.evaluation_files


def test_verify_freeze_success(locked_spec: DaytradeSpec) -> None:
    """Verify clean freeze record verifies successfully against spec and manifest."""
    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        provider="alpaca",
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        calendar="XNYS",
        timezone="America/New_York",
        universe=locked_spec.universe,
        start_date=locked_spec.context_anchor_date,
        end_date=locked_spec.validation.end,
        source_files={},
        manifest_sha256="manifest_sha_ok_123",
    )

    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256=manifest.manifest_sha256,
        require_clean=False,
    )

    # Should not raise
    verify_freeze_state(freeze, spec=locked_spec, manifest=manifest)


def test_freeze_tamper_file_rejection(locked_spec: DaytradeSpec) -> None:
    """Verify tampering with a recorded file hash raises FreezeError."""
    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        require_clean=False,
    )

    # Tamper with the expected SHA of one of the files
    first_file = next(iter(freeze.evaluation_files.keys()))
    tampered_files = dict(freeze.evaluation_files)
    tampered_files[first_file] = "0" * 64

    tampered_freeze = EvaluationFreezeRecord(
        evaluation_code_sha=freeze.evaluation_code_sha,
        repository_clean=freeze.repository_clean,
        frozen_at=freeze.frozen_at,
        spec_sha256=freeze.spec_sha256,
        manifest_sha256=freeze.manifest_sha256,
        evaluation_files=tampered_files,
    )

    with pytest.raises(FreezeError, match="tampered"):
        verify_freeze_state(tampered_freeze, spec=locked_spec)


def test_freeze_tamper_spec_rejection(locked_spec: DaytradeSpec) -> None:
    """Verify spec hash mismatch raises FreezeError."""
    freeze = freeze_evaluation_state(
        spec_sha256="f" * 64,  # wrong spec SHA
        require_clean=False,
    )

    with pytest.raises(FreezeError, match="Freeze spec SHA mismatch"):
        verify_freeze_state(freeze, spec=locked_spec)
