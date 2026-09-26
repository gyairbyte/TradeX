"""Command-line interface tests for daytrade_reversal."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradex.research.daytrade_reversal.cli import main
from tradex.research.daytrade_reversal.dataset import get_repo_root
from tradex.research.daytrade_reversal.spec import SpecError


def test_cli_verify_spec_success() -> None:
    """CLI verify-spec exits 0 for canonical locked specification."""
    rc = main(["verify-spec"])
    assert rc == 0


def test_cli_verify_spec_tampered_fails(tmp_path: Path) -> None:
    """CLI verify-spec raises SpecError on tampered file."""
    bad_spec = tmp_path / "bad.json"
    bad_spec.write_text('{"bad": true}', encoding="utf-8")
    with pytest.raises(SpecError):
        main(["verify-spec", "--spec", str(bad_spec)])


def test_cli_freeze_writes_record(tmp_path: Path) -> None:
    """CLI freeze writes freeze.json to output directory."""
    out = tmp_path / "freeze_out"
    rc = main(["freeze", "--output", str(out)])
    assert rc == 0
    freeze_json = out / "freeze.json"
    assert freeze_json.is_file()
    data = json.loads(freeze_json.read_text(encoding="utf-8"))
    assert "evaluation_code_sha" in data
    assert "evaluation_files" in data


def test_cli_build_dataset_unauthorized_fails_closed(tmp_path: Path) -> None:
    """CLI build-dataset fails closed without --dry-run."""
    rc = main(["build-dataset", "--dataset-root", str(tmp_path)])
    assert rc == 1


def test_cli_build_dataset_dry_run_succeeds(tmp_path: Path) -> None:
    """CLI build-dataset succeeds with --dry-run and external root."""
    rc = main(["build-dataset", "--dataset-root", str(tmp_path), "--dry-run"])
    assert rc == 0


def test_cli_build_dataset_in_repo_rejected() -> None:
    """CLI build-dataset rejects destination inside git worktree even with dry-run."""
    in_repo = get_repo_root() / "data" / "bad_root"
    with pytest.raises(ValueError, match="inside the tracked repository"):
        main(["build-dataset", "--dataset-root", str(in_repo), "--dry-run"])


def test_cli_evaluate_development_writes_all_artifacts(tmp_path: Path) -> None:
    """CLI evaluate writes all required study artifacts."""
    out = tmp_path / "dev_eval_out"
    rc = main(["evaluate", "--split", "development", "--output", str(out)])
    assert rc == 0

    expected_files = [
        "study.json",
        "spec.lock.json",
        "data_quality.csv",
        "events.csv",
        "baseline_summary.csv",
        "per_ticker.csv",
        "monthly.csv",
        "bootstrap.json",
        "metrics.json",
        "report.md",
        "checksums.sha256",
    ]
    for fn in expected_files:
        assert (out / fn).is_file(), f"Missing artifact: {fn}"


def test_cli_evaluate_holdout_requires_validation_dir(tmp_path: Path) -> None:
    """CLI evaluate --split holdout without validation dir fails."""
    out = tmp_path / "holdout_out"
    rc = main(["evaluate", "--split", "holdout", "--output", str(out)])
    assert rc == 1
