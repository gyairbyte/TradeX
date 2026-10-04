"""Tests for DAYTRADE-002B command-line interface commands."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import tradex.research.daytrade_momentum.freeze as freeze_mod
from tradex.research.daytrade_momentum.cli import main
from tradex.research.daytrade_momentum.dataset import (
    DaytradeDatasetManifest,
    sha256_of_file,
    write_normalized_bars_csv,
)
from tradex.research.daytrade_momentum.spec import DaytradeSpec
from tradex.research.daytrade_momentum.synthetic import generate_synthetic_session_bars


@pytest.fixture(autouse=True)
def mock_clean_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock clean worktree for CLI tests."""
    monkeypatch.setattr(freeze_mod, "check_worktree_clean", lambda root: True)


def _populate_minimal_preholdout(root: Path, spec: DaytradeSpec) -> Path:
    """Populate minimal valid preholdout partition with manifest and bar files."""
    part_dir = root / "preholdout"
    bars_dir = part_dir / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)
    source_files = {}

    for sym in spec.universe:
        csv_fp = bars_dir / f"{sym}.csv"
        # Generate 1 session (context anchor)
        df = generate_synthetic_session_bars(sym, date(2025, 12, 31))
        write_normalized_bars_csv(csv_fp, df)
        source_files[f"bars/{sym}.csv"] = sha256_of_file(csv_fp)

    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002B",
        spec_sha256=spec.sha256,
        partition="preholdout",
        provider="alpaca",
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        calendar="XNYS",
        timezone="America/New_York",
        universe=spec.universe,
        start_date=spec.context_anchor_date,
        end_date=spec.validation.end,
        source_files=source_files,
    )
    manifest.manifest_sha256 = manifest.compute_sha256()
    m_path = part_dir / "manifest.lock.json"
    m_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    return m_path


def test_cli_verify_spec() -> None:
    """Verify CLI verify-spec subcommand returns 0 on canonical spec."""
    code = main(["verify-spec"])
    assert code == 0


def test_cli_freeze_requires_manifest_or_dataset_root(temp_output_dir: Path) -> None:
    """Verify CLI freeze subcommand fails if neither --manifest nor --dataset-root is provided."""
    freeze_dir = temp_output_dir / "freeze_out"
    code = main(["freeze", "--output", str(freeze_dir)])
    assert code != 0


def test_cli_freeze_subcommand(
    locked_spec: DaytradeSpec, temp_output_dir: Path, temp_dataset_root: Path
) -> None:
    """Verify CLI freeze subcommand succeeds with valid preholdout manifest."""
    manifest_path = _populate_minimal_preholdout(temp_dataset_root, locked_spec)

    freeze_dir = temp_output_dir / "freeze_out"
    code = main(["freeze", "--manifest", str(manifest_path), "--output", str(freeze_dir)])
    assert code == 0
    assert (freeze_dir / "freeze.json").is_file()

    freeze_data = json.loads((freeze_dir / "freeze.json").read_text(encoding="utf-8"))
    assert "evaluation_code_sha" in freeze_data
    assert "spec_sha256" in freeze_data
    assert freeze_data["manifest_sha256"] is not None


def test_cli_evaluate_development(
    locked_spec: DaytradeSpec, temp_output_dir: Path, temp_dataset_root: Path
) -> None:
    """Verify CLI evaluate subcommand on development split."""
    _populate_minimal_preholdout(temp_dataset_root, locked_spec)

    eval_dir = temp_output_dir / "eval_out"
    code = main([
        "evaluate",
        "--split", "development",
        "--dataset-root", str(temp_dataset_root),
        "--output", str(eval_dir),
    ])
    assert code == 0
    assert (eval_dir / "study.json").is_file()
    assert (eval_dir / "checksums.sha256").is_file()

    study_data = json.loads((eval_dir / "study.json").read_text(encoding="utf-8"))
    assert study_data["split"] == "development"
    assert study_data["disposition"] in ("supported", "inconclusive", "rejected")


def test_cli_build_dataset_dry_run(temp_dataset_root: Path) -> None:
    """Verify CLI build-dataset in dry-run mode completes without network calls."""
    code = main([
        "build-dataset",
        "--dataset-root", str(temp_dataset_root),
        "--split", "preholdout",
        "--dry-run",
    ])
    assert code == 0
    dry_run_file = temp_dataset_root / "preholdout" / "manifest.dry-run.json"
    formal_file = temp_dataset_root / "preholdout" / "manifest.lock.json"
    assert dry_run_file.is_file()
    assert not formal_file.is_file()
    m = json.loads(dry_run_file.read_text(encoding="utf-8"))
    assert m["partition"] == "preholdout"
    assert m["acquisition_provenance"]["execute_provider"] is False


def test_cli_build_dataset_holdout_blocks_without_validation_dir(temp_dataset_root: Path) -> None:
    """Verify build-dataset --split holdout fails if validation-artifact-dir is missing."""
    code = main([
        "build-dataset",
        "--dataset-root", str(temp_dataset_root),
        "--split", "holdout",
        "--dry-run",
    ])
    assert code != 0


def test_cli_build_dataset_holdout_with_valid_validation_dir(
    locked_spec: DaytradeSpec, temp_output_dir: Path, temp_dataset_root: Path
) -> None:
    """Verify build-dataset --split holdout succeeds in dry-run with valid validation bundle."""
    from tests.research.daytrade_momentum.test_holdout_guard import (
        create_mock_supported_validation_bundle,
    )

    val_dir = temp_output_dir / "val_bundle"
    create_mock_supported_validation_bundle(val_dir, locked_spec)

    code = main([
        "build-dataset",
        "--dataset-root", str(temp_dataset_root),
        "--split", "holdout",
        "--validation-artifact-dir", str(val_dir),
        "--dry-run",
    ])
    assert code == 0
    dry_run_file = temp_dataset_root / "holdout" / "manifest.dry-run.json"
    assert dry_run_file.is_file()
    m = json.loads(dry_run_file.read_text(encoding="utf-8"))
    assert m["partition"] == "holdout"
    assert m["preholdout_manifest_sha256"] is not None
    assert m["validation_bundle_sha256"] is not None
    assert m["evaluator_code_sha"] is not None
