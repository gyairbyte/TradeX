"""Tests for DAYTRADE-002B command-line interface commands."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradex.research.daytrade_momentum.cli import main


def test_cli_verify_spec() -> None:
    """Verify CLI verify-spec subcommand returns 0 on canonical spec."""
    code = main(["verify-spec"])
    assert code == 0


def test_cli_freeze_subcommand(temp_output_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI freeze subcommand outputs freeze.json."""
    # Monkeypatch check_worktree_clean to return True for test environment
    import tradex.research.daytrade_momentum.freeze as freeze_mod
    monkeypatch.setattr(freeze_mod, "check_worktree_clean", lambda root: True)

    freeze_dir = temp_output_dir / "freeze_out"
    code = main(["freeze", "--output", str(freeze_dir)])
    assert code == 0
    assert (freeze_dir / "freeze.json").is_file()

    freeze_data = json.loads((freeze_dir / "freeze.json").read_text(encoding="utf-8"))
    assert "evaluation_code_sha" in freeze_data
    assert "spec_sha256" in freeze_data


def test_cli_evaluate_development(temp_output_dir: Path, temp_dataset_root: Path) -> None:
    """Verify CLI evaluate subcommand on development split."""
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
    manifest_file = temp_dataset_root / "manifest_preholdout.json"
    assert manifest_file.is_file()
    m = json.loads(manifest_file.read_text(encoding="utf-8"))
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
