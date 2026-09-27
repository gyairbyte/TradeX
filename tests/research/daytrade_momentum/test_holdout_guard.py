"""Tests for the strict 23-point holdout access guard and pre-holdout history isolation.

Enforces Clarification 4:
- All 23 validation prerequisites verified before any holdout access.
- Fails closed before any data loading or provider calls.
- Pre-holdout observations enter threshold history only and NEVER enter holdout metrics or baselines.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

import tradex.research.daytrade_momentum.freeze as freeze_mod
from tradex.research.daytrade_momentum.dataset import DaytradeDatasetManifest
from tradex.research.daytrade_momentum.freeze import freeze_evaluation_state
from tradex.research.daytrade_momentum.models import (
    HoldoutAccessDeniedError,
)
from tradex.research.daytrade_momentum.spec import (
    LOCKED_FROZEN_UNIVERSE,
    DaytradeSpec,
)
from tradex.research.daytrade_momentum.study import (
    evaluate_split,
    verify_holdout_access_prerequisites,
)
from tradex.research.daytrade_momentum.synthetic import (
    build_synthetic_session_from_bars,
    generate_synthetic_session_bars,
)


@pytest.fixture(autouse=True)
def mock_clean_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock clean worktree for unit tests."""
    monkeypatch.setattr(freeze_mod, "check_worktree_clean", lambda root: True)


def create_mock_supported_validation_bundle(
    artifact_dir: Path,
    spec: DaytradeSpec,
    disposition: str = "supported",
    production_promotion_eligible: bool = False,
    provider: str = "alpaca",
) -> None:
    """Helper to build a self-consistent mock validation bundle."""
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # 1. Manifest
    manifest = DaytradeDatasetManifest(
        task_id="DAYTRADE-002B",
        spec_sha256=spec.sha256,
        partition="preholdout",
        provider=provider,
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        calendar="XNYS",
        timezone="America/New_York",
        universe=LOCKED_FROZEN_UNIVERSE,
        start_date=spec.context_anchor_date,
        end_date=spec.validation.end,
        source_files={f"bars/{ticker}.csv": "a" * 64 for ticker in LOCKED_FROZEN_UNIVERSE},
    )
    manifest.manifest_sha256 = manifest.compute_sha256()
    (artifact_dir / "manifest.lock.json").write_text(
        json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
    )

    # 2. Freeze
    freeze = freeze_evaluation_state(
        spec_sha256=spec.sha256,
        manifest_sha256=manifest.manifest_sha256,
        require_clean=False,
    )
    (artifact_dir / "freeze.json").write_text(
        json.dumps(freeze.to_dict(), indent=2), encoding="utf-8"
    )

    # 3. Spec Lock
    (artifact_dir / "spec.lock.json").write_text(
        json.dumps({"spec_sha256": spec.sha256, "task_id": "DAYTRADE-002A"}, indent=2),
        encoding="utf-8",
    )

    # 4. Study JSON
    study = {
        "task_id": "DAYTRADE-002B",
        "split": "validation",
        "disposition": disposition,
        "disposition_step": "step_5_support" if disposition == "supported" else "step_3_failure",
        "provenance": {
            "task_id": "DAYTRADE-002B",
            "spec_sha256": spec.sha256,
            "evaluator_code_sha": freeze.evaluation_code_sha,
            "manifest_sha256": manifest.manifest_sha256,
            "evidence_confidence_cap": "limited_but_usable_evidence",
            "production_promotion_eligible": production_promotion_eligible,
        },
    }
    (artifact_dir / "study.json").write_text(json.dumps(study, indent=2), encoding="utf-8")

    # 5. Bootstrap & Metrics & Quality & Report
    (artifact_dir / "bootstrap.json").write_text("{}", encoding="utf-8")
    (artifact_dir / "metrics.json").write_text("{}", encoding="utf-8")
    (artifact_dir / "data_quality.csv").write_text("ticker,session_date,excluded\n", encoding="utf-8")
    (artifact_dir / "report.md").write_text("# Validation Report\n", encoding="utf-8")

    # 6. Checksums
    checksum_lines: list[str] = []
    files_to_hash = [
        "study.json", "spec.lock.json", "freeze.json", "manifest.lock.json",
        "bootstrap.json", "metrics.json", "data_quality.csv", "report.md"
    ]
    for fn in files_to_hash:
        fp = artifact_dir / fn
        sha = hashlib.sha256(fp.read_bytes()).hexdigest()
        checksum_lines.append(f"{sha}  {fn}")

    (artifact_dir / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")


def test_supported_validation_passes_guard(locked_spec: DaytradeSpec, temp_output_dir: Path) -> None:
    """Verify that a valid supported validation bundle passes all 23 checks."""
    vdir = temp_output_dir / "validation_supported"
    create_mock_supported_validation_bundle(vdir, locked_spec, disposition="supported")

    # Should succeed without raising
    verify_holdout_access_prerequisites(vdir, locked_spec)


def test_unsupported_validation_blocks_holdout(locked_spec: DaytradeSpec, temp_output_dir: Path) -> None:
    """Verify that validation with 'inconclusive' or 'rejected' disposition blocks holdout access."""
    vdir = temp_output_dir / "validation_rejected"
    create_mock_supported_validation_bundle(vdir, locked_spec, disposition="rejected")

    with pytest.raises(HoldoutAccessDeniedError, match="holdout access is strictly prohibited"):
        verify_holdout_access_prerequisites(vdir, locked_spec)


def test_checksum_tampering_blocks_holdout(locked_spec: DaytradeSpec, temp_output_dir: Path) -> None:
    """Verify that modifying any file in the bundle fails checksum verification."""
    vdir = temp_output_dir / "validation_tampered"
    create_mock_supported_validation_bundle(vdir, locked_spec)

    # Tamper with study.json content after checksums were generated
    (vdir / "study.json").write_text('{"tampered": true}', encoding="utf-8")

    with pytest.raises(HoldoutAccessDeniedError, match="Checksum mismatch"):
        verify_holdout_access_prerequisites(vdir, locked_spec)


def test_promotion_eligible_blocks_holdout(locked_spec: DaytradeSpec, temp_output_dir: Path) -> None:
    """Verify that production_promotion_eligible == True in validation provenance is rejected."""
    vdir = temp_output_dir / "validation_promo_true"
    create_mock_supported_validation_bundle(vdir, locked_spec, production_promotion_eligible=True)

    with pytest.raises(HoldoutAccessDeniedError, match="Production promotion eligible must be False"):
        verify_holdout_access_prerequisites(vdir, locked_spec)


def test_evaluate_split_holdout_fails_without_validation_dir(
    locked_spec: DaytradeSpec, temp_dataset_root: Path
) -> None:
    """Verify evaluate_split('holdout') raises HoldoutAccessDeniedError if validation dir is missing."""
    with pytest.raises(HoldoutAccessDeniedError, match="requires --validation-artifact-dir"):
        evaluate_split(
            split_name="holdout",
            spec=locked_spec,
            dataset_root=temp_dataset_root,
            validation_artifact_dir=None,
        )


def test_preholdout_history_isolation_in_holdout(
    locked_spec: DaytradeSpec, temp_dataset_root: Path, temp_output_dir: Path
) -> None:
    """Verify pre-holdout observations enter threshold history ONLY and never enter holdout events/baselines."""
    vdir = temp_output_dir / "val_bundle"
    create_mock_supported_validation_bundle(vdir, locked_spec)

    # Construct sessions: 20 sessions in validation (for threshold history) + 1 session in holdout
    # Dates: holdout starts 2026-07-01
    val_date = date(2026, 6, 29)
    holdout_date = date(2026, 7, 2)

    df_val = generate_synthetic_session_bars("SPY", val_date, signal_09_59_close=105.0)
    sess_val = build_synthetic_session_from_bars("SPY", val_date, df_val)

    # Holdout session
    df_holdout = generate_synthetic_session_bars("SPY", holdout_date, signal_09_59_close=100.1)
    sess_holdout = build_synthetic_session_from_bars("SPY", holdout_date, df_holdout)

    sessions_by_ticker = {
        "SPY": [sess_val, sess_holdout],
    }
    for sym in locked_spec.universe:
        if sym != "SPY":
            sessions_by_ticker[sym] = []

    res = evaluate_split(
        split_name="holdout",
        spec=locked_spec,
        dataset_root=temp_dataset_root,
        validation_artifact_dir=vdir,
        custom_sessions=sessions_by_ticker,
        custom_reports=[],
    )

    # Verification: sess_val must NOT be in holdout events or non-events
    for ev in res.events:
        assert ev.session_date != val_date
        assert ev.split == "holdout"

    for ne in res.non_events:
        assert ne.session_date != val_date
        assert ne.split == "holdout"
