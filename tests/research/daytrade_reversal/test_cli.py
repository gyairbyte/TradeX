"""Command-line interface tests for daytrade_reversal."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradex.research.daytrade_reversal.cli import main
from tradex.research.daytrade_reversal.dataset import (
    DaytradeDatasetManifest,
    get_repo_root,
)
from tradex.research.daytrade_reversal.spec import SpecError, load_and_verify_spec


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


def test_cli_freeze_fails_closed_without_manifest(tmp_path: Path) -> None:
    """CLI freeze without --manifest or --dataset-root fails closed."""
    out = tmp_path / "freeze_out"
    rc = main(["freeze", "--output", str(out)])
    assert rc == 1


def test_cli_freeze_fails_closed_in_repo_output(tmp_path: Path) -> None:
    """CLI freeze rejects output directory inside git repository."""
    in_repo = get_repo_root() / "tmp_freeze"
    rc = main(["freeze", "--output", str(in_repo)])
    assert rc == 1


def _setup_valid_partition(partition_dir: Path, spec) -> Path:
    import pandas as pd

    from tradex.research.daytrade_reversal.artifacts import sha256_of_file
    from tradex.research.daytrade_reversal.dataset import write_normalized_bars_csv

    bars_dir = partition_dir / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)
    source_files: dict[str, str] = {}
    for ticker in spec.universe:
        csv_file = bars_dir / f"{ticker}.csv"
        df = pd.DataFrame([
            {"bar_start": "2025-01-02T14:30:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000}
        ])
        write_normalized_bars_csv(csv_file, df)
        source_files[f"bars/{ticker}.csv"] = sha256_of_file(csv_file)

    manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=spec.sha256,
        partition="preholdout",
        start_date=spec.warmup.start,
        end_date=spec.validation.end,
        universe=list(spec.universe),
        source_files=source_files,
    )
    man_file = partition_dir / "manifest.lock.json"
    man_file.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    return man_file


def test_cli_freeze_fails_closed_on_dirty_worktree(tmp_path: Path, monkeypatch) -> None:
    """CLI freeze fails closed if worktree has uncommitted modifications or untracked files."""
    spec = load_and_verify_spec()
    man_file = _setup_valid_partition(tmp_path, spec)

    out = tmp_path / "freeze_out"
    from tradex.research.daytrade_reversal.freeze import FreezeError

    monkeypatch.setattr("tradex.research.daytrade_reversal.cli.freeze_evaluation_state", MagicMock(side_effect=FreezeError("dirty worktree")))
    rc = main(["freeze", "--manifest", str(man_file), "--output", str(out)])
    assert rc == 1


def test_cli_freeze_writes_record_with_valid_manifest(tmp_path: Path, monkeypatch) -> None:
    """CLI freeze writes freeze.json to external output directory when manifest is valid and repo is clean."""
    spec = load_and_verify_spec()
    man_file = _setup_valid_partition(tmp_path, spec)

    monkeypatch.setattr("tradex.research.daytrade_reversal.freeze.check_worktree_clean", lambda repo: True)

    out = tmp_path / "freeze_out"
    rc = main(["freeze", "--manifest", str(man_file), "--output", str(out)])
    assert rc == 0
    freeze_json = out / "freeze.json"
    assert freeze_json.is_file()
    data = json.loads(freeze_json.read_text(encoding="utf-8"))
    assert "evaluation_code_sha" in data
    assert "evaluation_files" in data


def test_cli_freeze_fails_if_source_csv_is_mutated(tmp_path: Path, monkeypatch) -> None:
    """Freeze fails if any source CSV is mutated after manifest generation."""
    spec = load_and_verify_spec()
    man_file = _setup_valid_partition(tmp_path, spec)

    # Mutate one source file
    csv_file = tmp_path / "bars" / f"{spec.universe[0]}.csv"
    csv_file.write_text("corrupted content", encoding="utf-8")

    monkeypatch.setattr("tradex.research.daytrade_reversal.freeze.check_worktree_clean", lambda repo: True)

    out = tmp_path / "freeze_out"
    rc = main(["freeze", "--manifest", str(man_file), "--output", str(out)])
    assert rc == 1


def test_cli_build_dataset_unauthorized_fails_closed(tmp_path: Path) -> None:
    """CLI build-dataset fails closed without --dry-run or with provider execution in C1."""
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


def test_cli_build_dataset_with_mocked_provider_succeeds(tmp_path: Path, monkeypatch) -> None:
    """CLI build-dataset --execute-provider acquires preholdout partition when provider is mocked."""
    monkeypatch.setenv("ALPACA_API_KEY", "test_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")

    from tradex.research.daytrade_reversal.dataset import DaytradeDatasetManifest
    spec = load_and_verify_spec()
    fake_manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=spec.sha256,
        partition="preholdout",
        universe=list(spec.universe),
        source_files={f"bars/{t}.csv": "a" * 64 for t in spec.universe},
    )
    fake_summary = {
        "partition": "preholdout",
        "total_symbols": 30,
        "total_requests": 30,
        "total_pages": 30,
        "total_retries": 0,
        "manifest_sha256": "fake_sha",
        "manifest_path": str(tmp_path / "preholdout" / "manifest.lock.json"),
    }
    monkeypatch.setattr(
        "tradex.research.daytrade_reversal.cli.acquire_dataset_partition",
        lambda *args, **kwargs: (fake_manifest, fake_summary),
    )

    rc = main([
        "build-dataset",
        "--dataset-root", str(tmp_path),
        "--split", "preholdout",
        "--execute-provider",
    ])
    assert rc == 0


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


def test_cli_evaluate_validation_requires_freeze(tmp_path: Path) -> None:
    """CLI evaluate --split validation requires --freeze."""
    out = tmp_path / "val_eval_out"
    rc = main(["evaluate", "--split", "validation", "--output", str(out)])
    assert rc == 1


def test_cli_evaluate_with_dataset_root(tmp_path: Path, monkeypatch) -> None:
    """CLI evaluate --dataset-root loads dataset via load_private_dataset."""
    out = tmp_path / "eval_out"
    ds_root = tmp_path / "ext_ds"
    ds_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "tradex.research.daytrade_reversal.cli.load_private_dataset",
        lambda dataset_root, split_name, spec: ([], []),
    )

    rc = main([
        "evaluate",
        "--split", "development",
        "--dataset-root", str(ds_root),
        "--output", str(out),
    ])
    assert rc == 0
    assert (out / "study.json").is_file()


def test_cli_evaluate_holdout_never_parses_holdout_before_validation_passes(tmp_path: Path, monkeypatch) -> None:
    """CLI evaluate --split holdout must NEVER call load_private_dataset if validation prerequisites fail."""
    mock_load = MagicMock(return_value=([], []))
    monkeypatch.setattr("tradex.research.daytrade_reversal.cli.load_private_dataset", mock_load)

    # 1. Without validation artifact dir
    out = tmp_path / "holdout_out"
    rc = main(["evaluate", "--split", "holdout", "--dataset-root", str(tmp_path), "--output", str(out)])
    assert rc == 1
    assert mock_load.call_count == 0

    # 2. With invalid validation artifact dir (missing files)
    bad_val_dir = tmp_path / "empty_val_dir"
    bad_val_dir.mkdir(parents=True, exist_ok=True)
    rc = main([
        "evaluate",
        "--split", "holdout",
        "--dataset-root", str(tmp_path),
        "--validation-artifact-dir", str(bad_val_dir),
        "--output", str(out),
    ])
    assert rc == 2
    assert mock_load.call_count == 0
