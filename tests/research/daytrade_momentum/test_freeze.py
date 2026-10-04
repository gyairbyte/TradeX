"""Tests for evaluation code freeze, clean worktree verification, and tamper detection."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import tradex.research.daytrade_momentum.freeze as freeze_mod
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


def test_verify_freeze_success(locked_spec: DaytradeSpec, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify clean freeze record verifies successfully against spec and manifest."""
    source_files = {f"bars/{ticker}.csv": "a" * 64 for ticker in locked_spec.universe}
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
        source_files=source_files,
        manifest_sha256="manifest_sha_ok_123",
    )

    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256=manifest.manifest_sha256,
        require_clean=False,
    )

    monkeypatch.setattr(freeze_mod, "check_worktree_clean", lambda root: True)
    monkeypatch.setattr(freeze_mod, "get_git_head_sha", lambda root: freeze.evaluation_code_sha)

    # Should not raise
    verify_freeze_state(freeze, spec=locked_spec, manifest=manifest, require_clean=True)


def test_freeze_dirty_worktree_rejection(locked_spec: DaytradeSpec, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify verify_freeze_state fails closed when worktree is dirty."""
    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256="manifest_sha_123",
        require_clean=False,
    )

    monkeypatch.setattr(freeze_mod, "check_worktree_clean", lambda root: False)
    monkeypatch.setattr(freeze_mod, "get_git_head_sha", lambda root: freeze.evaluation_code_sha)

    with pytest.raises(FreezeError, match="Worktree is dirty"):
        verify_freeze_state(freeze, spec=locked_spec, require_clean=True)


def test_freeze_head_mismatch_rejection(locked_spec: DaytradeSpec, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify verify_freeze_state fails closed when git HEAD does not match freeze record."""
    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256="manifest_sha_123",
        require_clean=False,
    )

    monkeypatch.setattr(freeze_mod, "check_worktree_clean", lambda root: True)
    monkeypatch.setattr(freeze_mod, "get_git_head_sha", lambda root: "different_head_sha_9999")

    with pytest.raises(FreezeError, match="HEAD commit mismatch"):
        verify_freeze_state(freeze, spec=locked_spec, require_clean=True)


def test_freeze_missing_manifest_sha_rejection(locked_spec: DaytradeSpec) -> None:
    """Verify verify_freeze_state fails closed when freeze is not bound to a manifest."""
    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256=None,
        require_clean=False,
    )

    with pytest.raises(FreezeError, match="Formal evaluation freeze must be bound to a dataset manifest"):
        verify_freeze_state(freeze, spec=locked_spec, require_clean=False)


def test_freeze_manifest_sha_mismatch_rejection(locked_spec: DaytradeSpec, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify verify_freeze_state fails closed when manifest SHA does not match."""
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
        source_files={f"bars/{ticker}.csv": "a" * 64 for ticker in locked_spec.universe},
        manifest_sha256="correct_manifest_sha_123",
    )

    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256="other_manifest_sha_456",
        require_clean=False,
    )

    monkeypatch.setattr(freeze_mod, "check_worktree_clean", lambda root: True)
    monkeypatch.setattr(freeze_mod, "get_git_head_sha", lambda root: freeze.evaluation_code_sha)

    with pytest.raises(FreezeError, match="Freeze manifest SHA mismatch"):
        verify_freeze_state(freeze, spec=locked_spec, manifest=manifest, require_clean=False)


def test_freeze_tamper_file_rejection(locked_spec: DaytradeSpec, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify tampering with a recorded file hash raises FreezeError."""
    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256="mock_manifest_sha",
        require_clean=False,
    )

    monkeypatch.setattr(freeze_mod, "check_worktree_clean", lambda root: True)
    monkeypatch.setattr(freeze_mod, "get_git_head_sha", lambda root: freeze.evaluation_code_sha)

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
        verify_freeze_state(tampered_freeze, spec=locked_spec, require_clean=False)


def test_freeze_tamper_spec_rejection(locked_spec: DaytradeSpec) -> None:
    """Verify spec hash mismatch raises FreezeError."""
    freeze = freeze_evaluation_state(
        spec_sha256="f" * 64,  # wrong spec SHA
        manifest_sha256="mock_manifest_sha",
        require_clean=False,
    )

    with pytest.raises(FreezeError, match="Freeze spec SHA mismatch"):
        verify_freeze_state(freeze, spec=locked_spec, require_clean=False)


def test_freeze_rejects_dry_run_manifest(locked_spec: DaytradeSpec) -> None:
    """Verify freeze_evaluation_state fails closed when passed a dry-run manifest."""
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
        acquisition_provenance={"status": "dry_run_no_provider_calls"},
    )
    with pytest.raises(FreezeError, match="Cannot freeze evaluation state against a dry-run"):
        freeze_evaluation_state(
            spec_sha256=locked_spec.sha256,
            manifest=manifest,
            require_clean=False,
        )


def test_freeze_verification_rejects_dry_run_manifest(
    locked_spec: DaytradeSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify verify_freeze_state fails closed when bound to a dry-run manifest."""
    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256="manifest_sha_123",
        require_clean=False,
    )
    monkeypatch.setattr(freeze_mod, "check_worktree_clean", lambda root: True)
    monkeypatch.setattr(freeze_mod, "get_git_head_sha", lambda root: freeze.evaluation_code_sha)

    dry_manifest = DaytradeDatasetManifest(
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
        acquisition_provenance={"status": "dry_run_no_provider_calls"},
        manifest_sha256="manifest_sha_123",
    )
    with pytest.raises(FreezeError, match="Cannot bind or verify evaluation freeze against a dry-run"):
        verify_freeze_state(freeze, spec=locked_spec, manifest=dry_manifest, require_clean=False)


def test_direct_validation_evaluation_fails_without_freeze(
    locked_spec: DaytradeSpec, tmp_path: Path
) -> None:
    """Verify evaluate_split('validation') fails closed without a bound EvaluationFreezeRecord."""
    from tradex.research.daytrade_momentum.study import evaluate_split

    dataset_root = tmp_path / "dataset"
    pre_dir = dataset_root / "preholdout"
    pre_dir.mkdir(parents=True, exist_ok=True)
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
        source_files={f"bars/{s}.csv": "a" * 64 for s in locked_spec.universe},
    )
    manifest.manifest_sha256 = manifest.compute_sha256()
    (pre_dir / "manifest.lock.json").write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="strictly requires a bound EvaluationFreezeRecord"):
        evaluate_split(split_name="validation", spec=locked_spec, dataset_root=dataset_root, freeze=None)


def test_direct_validation_evaluation_fails_on_freeze_manifest_mismatch(
    locked_spec: DaytradeSpec, tmp_path: Path
) -> None:
    """Verify evaluate_split('validation') fails closed when freeze manifest SHA does not match preholdout manifest."""
    from datetime import date

    from tradex.research.daytrade_momentum.dataset import write_normalized_bars_csv
    from tradex.research.daytrade_momentum.study import evaluate_split
    from tradex.research.daytrade_momentum.synthetic import generate_synthetic_session_bars

    dataset_root = tmp_path / "dataset"
    pre_dir = dataset_root / "preholdout"
    (pre_dir / "bars").mkdir(parents=True, exist_ok=True)

    source_files = {}
    for s in locked_spec.universe:
        p = pre_dir / "bars" / f"{s}.csv"
        df = generate_synthetic_session_bars(s, date(2026, 1, 2))
        write_normalized_bars_csv(p, df)
        source_files[f"bars/{s}.csv"] = freeze_mod.sha256_of_file(p)

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
        source_files=source_files,
    )
    manifest.manifest_sha256 = manifest.compute_sha256()
    (pre_dir / "manifest.lock.json").write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    freeze = freeze_evaluation_state(
        spec_sha256=locked_spec.sha256,
        manifest_sha256="wrong_manifest_sha_999",
        require_clean=False,
    )

    with pytest.raises(FreezeError, match="Freeze manifest SHA .* mismatch"):
        evaluate_split(split_name="validation", spec=locked_spec, dataset_root=dataset_root, freeze=freeze)
