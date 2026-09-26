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
    manifest: DaytradeDatasetManifest | None = None,
) -> tuple[StudyResult, EvaluationFreezeRecord, DaytradeDatasetManifest]:
    target_dir.mkdir(parents=True, exist_ok=True)
    effective_spec_sha = spec_sha or spec.sha256

    if manifest is None:
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


def _setup_valid_disk_partitions(
    dataset_dir: Path,
    spec: DaytradeSpec,
    evaluator_code_sha: str = "head1234567890abcdef1234567890abcdef1234",
    val_bundle_sha: str | None = None,
) -> tuple[DaytradeDatasetManifest, DaytradeDatasetManifest]:
    import pandas as pd

    from tradex.research.daytrade_reversal.artifacts import sha256_of_file
    from tradex.research.daytrade_reversal.dataset import write_normalized_bars_csv

    pre_dir = dataset_dir / "preholdout"
    pre_bars = pre_dir / "bars"
    pre_bars.mkdir(parents=True, exist_ok=True)
    pre_sources: dict[str, str] = {}
    for t in spec.universe:
        p = pre_bars / f"{t}.csv"
        write_normalized_bars_csv(p, pd.DataFrame(columns=["bar_start", "open", "high", "low", "close", "volume"]))
        pre_sources[f"bars/{t}.csv"] = sha256_of_file(p)

    pre_manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=spec.sha256,
        partition="preholdout",
        universe=list(spec.universe),
        start_date=spec.warmup.start,
        end_date=spec.validation.end,
        source_files=pre_sources,
    )
    pre_data = pre_manifest.to_dict()
    (pre_dir / "manifest.lock.json").write_text(json.dumps(pre_data, indent=2), encoding="utf-8")

    holdout_dir = dataset_dir / "holdout"
    holdout_bars = holdout_dir / "bars"
    holdout_bars.mkdir(parents=True, exist_ok=True)
    holdout_sources: dict[str, str] = {}
    for t in spec.universe:
        p = holdout_bars / f"{t}.csv"
        write_normalized_bars_csv(p, pd.DataFrame(columns=["bar_start", "open", "high", "low", "close", "volume"]))
        holdout_sources[f"bars/{t}.csv"] = sha256_of_file(p)

    holdout_manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=spec.sha256,
        partition="holdout",
        universe=list(spec.universe),
        start_date=spec.holdout.start,
        end_date=spec.holdout.end,
        source_files=holdout_sources,
        preholdout_manifest_sha256=pre_data["manifest_sha256"],
        validation_bundle_sha256=val_bundle_sha or ("b" * 64),
        evaluator_code_sha=evaluator_code_sha,
    )
    h_data = holdout_manifest.to_dict()
    (holdout_dir / "manifest.lock.json").write_text(json.dumps(h_data, indent=2), encoding="utf-8")
    return pre_manifest, holdout_manifest


def test_holdout_loading_fails_when_evaluator_code_sha_mismatches(
    tmp_path: Path,
    locked_spec: DaytradeSpec,
    monkeypatch,
) -> None:
    """Clarification 2: Changing only holdout_manifest.evaluator_code_sha fails closed before reading bars."""
    from tradex.research.daytrade_reversal.artifacts import sha256_of_file
    from tradex.research.daytrade_reversal.dataset import DatasetSecurityError, load_private_dataset

    monkeypatch.setattr("tradex.research.daytrade_reversal.study.verify_freeze_state", lambda *a, **kw: None)
    evaluator_sha = "head1234567890abcdef1234567890abcdef1234"
    dataset_dir = tmp_path / "dataset"
    val_dir = tmp_path / "validation_dir"

    # Pre-setup disk partitions
    pre_man, _ = _setup_valid_disk_partitions(dataset_dir, locked_spec, evaluator_code_sha=evaluator_sha)
    # Build validation bundle using exact pre_manifest
    _build_valid_validation_bundle(val_dir, locked_spec, disposition="supported", evaluator_code_sha=evaluator_sha, manifest=pre_man)
    val_bundle_sha = sha256_of_file(val_dir / "checksums.sha256")

    # Re-setup holdout manifest with correct validation_bundle_sha BUT altered evaluator_code_sha
    holdout_dir = dataset_dir / "holdout"
    holdout_sources = {f"bars/{t}.csv": sha256_of_file(holdout_dir / "bars" / f"{t}.csv") for t in locked_spec.universe}
    tampered_holdout_manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="holdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.holdout.start,
        end_date=locked_spec.holdout.end,
        source_files=holdout_sources,
        preholdout_manifest_sha256=pre_man.to_dict()["manifest_sha256"],
        validation_bundle_sha256=val_bundle_sha,
        evaluator_code_sha="altered_evaluator_sha_9999999999999999999",  # ONLY THIS IS CHANGED
    )
    (holdout_dir / "manifest.lock.json").write_text(json.dumps(tampered_holdout_manifest.to_dict(), indent=2), encoding="utf-8")

    with pytest.raises(DatasetSecurityError, match="evaluator_code_sha"):
        load_private_dataset(
            dataset_root=dataset_dir,
            split_name="holdout",
            spec=locked_spec,
            validation_artifact_dir=val_dir,
        )


def test_holdout_loading_fails_when_preholdout_manifest_mismatches_validation(
    tmp_path: Path,
    locked_spec: DaytradeSpec,
    monkeypatch,
) -> None:
    """Preholdout manifest tampered after validation fails closed during holdout load."""
    from tradex.research.daytrade_reversal.artifacts import sha256_of_file
    from tradex.research.daytrade_reversal.dataset import DatasetSecurityError, load_private_dataset

    monkeypatch.setattr("tradex.research.daytrade_reversal.study.verify_freeze_state", lambda *a, **kw: None)
    evaluator_sha = "head1234567890abcdef1234567890abcdef1234"
    dataset_dir = tmp_path / "dataset"
    val_dir = tmp_path / "validation_dir"

    pre_man, _ = _setup_valid_disk_partitions(dataset_dir, locked_spec, evaluator_code_sha=evaluator_sha)
    _build_valid_validation_bundle(val_dir, locked_spec, disposition="supported", evaluator_code_sha=evaluator_sha, manifest=pre_man)

    # Tamper preholdout manifest after validation bundle created
    pre_dir = dataset_dir / "preholdout"
    pre_man_tampered = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="preholdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.warmup.start,
        end_date=locked_spec.validation.end,
        source_files={f"bars/{t}.csv": sha256_of_file(pre_dir / "bars" / f"{t}.csv") for t in locked_spec.universe},
        evaluator_code_sha="tampered_different_field",
    )
    (pre_dir / "manifest.lock.json").write_text(json.dumps(pre_man_tampered.to_dict(), indent=2), encoding="utf-8")

    with pytest.raises(DatasetSecurityError, match="Preholdout manifest SHA"):
        load_private_dataset(
            dataset_root=dataset_dir,
            split_name="holdout",
            spec=locked_spec,
            validation_artifact_dir=val_dir,
        )


def test_holdout_loading_fails_when_preholdout_source_file_tampered(
    tmp_path: Path,
    locked_spec: DaytradeSpec,
    monkeypatch,
) -> None:
    """Mutating preholdout source file on disk fails closed during holdout load."""
    from tradex.research.daytrade_reversal.artifacts import sha256_of_file
    from tradex.research.daytrade_reversal.dataset import DatasetSecurityError, load_private_dataset

    monkeypatch.setattr("tradex.research.daytrade_reversal.study.verify_freeze_state", lambda *a, **kw: None)
    evaluator_sha = "head1234567890abcdef1234567890abcdef1234"
    dataset_dir = tmp_path / "dataset"
    val_dir = tmp_path / "validation_dir"

    pre_man, _ = _setup_valid_disk_partitions(dataset_dir, locked_spec, evaluator_code_sha=evaluator_sha)
    _build_valid_validation_bundle(val_dir, locked_spec, disposition="supported", evaluator_code_sha=evaluator_sha, manifest=pre_man)
    val_bundle_sha = sha256_of_file(val_dir / "checksums.sha256")

    # Update holdout manifest with correct validation_bundle_sha
    holdout_dir = dataset_dir / "holdout"
    holdout_sources = {f"bars/{t}.csv": sha256_of_file(holdout_dir / "bars" / f"{t}.csv") for t in locked_spec.universe}
    holdout_manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=locked_spec.sha256,
        partition="holdout",
        universe=list(locked_spec.universe),
        start_date=locked_spec.holdout.start,
        end_date=locked_spec.holdout.end,
        source_files=holdout_sources,
        preholdout_manifest_sha256=pre_man.to_dict()["manifest_sha256"],
        validation_bundle_sha256=val_bundle_sha,
        evaluator_code_sha=evaluator_sha,
    )
    (holdout_dir / "manifest.lock.json").write_text(json.dumps(holdout_manifest.to_dict(), indent=2), encoding="utf-8")

    # Mutate a bar CSV in preholdout on disk
    mutated_csv = dataset_dir / "preholdout" / "bars" / f"{locked_spec.universe[0]}.csv"
    mutated_csv.write_text("bar_start,open,high,low,close,volume\n2025-01-02T09:31:00Z,1,1,1,1,1\n", encoding="utf-8")

    with pytest.raises(DatasetSecurityError, match="Source file hash mismatch"):
        load_private_dataset(
            dataset_root=dataset_dir,
            split_name="holdout",
            spec=locked_spec,
            validation_artifact_dir=val_dir,
        )


def test_holdout_acquisition_fails_before_provider_when_preholdout_tampered(
    tmp_path: Path,
    locked_spec: DaytradeSpec,
    monkeypatch,
) -> None:
    """Holdout acquisition fails closed before making provider calls if preholdout disk file is tampered."""
    from tradex.research.daytrade_reversal.dataset import (
        DatasetSecurityError,
        acquire_dataset_partition,
    )

    monkeypatch.setattr("tradex.research.daytrade_reversal.study.verify_freeze_state", lambda *a, **kw: None)
    evaluator_sha = "head1234567890abcdef1234567890abcdef1234"
    dataset_dir = tmp_path / "dataset"
    val_dir = tmp_path / "validation_dir"

    pre_man, _ = _setup_valid_disk_partitions(dataset_dir, locked_spec, evaluator_code_sha=evaluator_sha)
    _build_valid_validation_bundle(val_dir, locked_spec, disposition="supported", evaluator_code_sha=evaluator_sha, manifest=pre_man)

    # Mutate preholdout CSV on disk
    mutated_csv = dataset_dir / "preholdout" / "bars" / f"{locked_spec.universe[0]}.csv"
    mutated_csv.write_text("corrupted content", encoding="utf-8")

    mock_client = MagicMock()
    mock_client.max_retries = 1

    with pytest.raises(DatasetSecurityError, match="Source file hash mismatch"):
        acquire_dataset_partition(
            spec=locked_spec,
            dataset_root=dataset_dir,
            partition="holdout",
            client=mock_client,
            validation_bundle_dir=val_dir,
        )

    # Provider call count must remain strictly 0
    assert mock_client.get_bars.call_count == 0
