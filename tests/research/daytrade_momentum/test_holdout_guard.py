"""Tests for the strict 23-point holdout access guard and pre-holdout history isolation.

Enforces Clarification 4:
- All 23 validation prerequisites verified before any holdout access.
- Fails closed before any data loading or provider calls.
- Pre-holdout observations enter threshold history only and NEVER enter holdout metrics or baselines.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import tradex.research.daytrade_momentum.freeze as freeze_mod
from tradex.research.daytrade_momentum.calendar import get_regular_trading_sessions
from tradex.research.daytrade_momentum.dataset import (
    DaytradeDatasetManifest,
    acquire_dataset_partition,
    write_normalized_bars_csv,
)
from tradex.research.daytrade_momentum.freeze import (
    freeze_evaluation_state,
    sha256_of_file,
)
from tradex.research.daytrade_momentum.models import (
    HoldoutAccessDeniedError,
    HoldoutAccessProof,
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
) -> str:
    """Helper to build a self-consistent mock validation bundle with all 13 formal artifacts."""
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # 1. Manifest
    manifest = DaytradeDatasetManifest(
        task_id=spec.task_id,
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
        json.dumps({"spec_sha256": spec.sha256, "task_id": spec.task_id}, indent=2),
        encoding="utf-8",
    )

    # 4. Study JSON
    study = {
        "task_id": spec.task_id,
        "split": "validation",
        "disposition": disposition,
        "disposition_step": "step_5_support" if disposition == "supported" else "step_3_failure",
        "provenance": {
            "task_id": spec.task_id,
            "spec_sha256": spec.sha256,
            "evaluator_code_sha": freeze.evaluation_code_sha,
            "manifest_sha256": manifest.manifest_sha256,
            "evidence_confidence_cap": "limited_but_usable_evidence",
            "production_promotion_eligible": production_promotion_eligible,
        },
    }
    (artifact_dir / "study.json").write_text(json.dumps(study, indent=2), encoding="utf-8")

    # 5. Bootstrap, Metrics, Data Quality, Report, and CSV tables (all 13 formal artifacts)
    (artifact_dir / "bootstrap.json").write_text("{}", encoding="utf-8")
    (artifact_dir / "metrics.json").write_text("{}", encoding="utf-8")
    (artifact_dir / "data_quality.csv").write_text("ticker,session_date,excluded\n", encoding="utf-8")
    (artifact_dir / "events.csv").write_text("event_id,ticker,session_date\n", encoding="utf-8")
    (artifact_dir / "baseline_summary.csv").write_text("bucket,count,mean\n", encoding="utf-8")
    (artifact_dir / "per_etf.csv").write_text("ticker,event_count,mean_net_signed_return_2bps,win_rate_gross\n", encoding="utf-8")
    (artifact_dir / "monthly.csv").write_text("month,event_count,mean_net_return_2bps\n", encoding="utf-8")
    (artifact_dir / "direction.csv").write_text("direction,event_count,mean_net_return_2bps,mean_uplift_2bps\n", encoding="utf-8")
    (artifact_dir / "report.md").write_text("# Validation Report\n", encoding="utf-8")

    # 6. Checksums
    checksum_lines: list[str] = []
    files_to_hash = [
        "study.json", "spec.lock.json", "freeze.json", "manifest.lock.json",
        "bootstrap.json", "metrics.json", "data_quality.csv", "events.csv",
        "baseline_summary.csv", "per_etf.csv", "monthly.csv", "direction.csv", "report.md"
    ]
    for fn in files_to_hash:
        fp = artifact_dir / fn
        sha = hashlib.sha256(fp.read_bytes()).hexdigest()
        checksum_lines.append(f"{sha}  {fn}")

    checksum_file = artifact_dir / "checksums.sha256"
    checksum_file.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return hashlib.sha256(checksum_file.read_bytes()).hexdigest()


REQUIRED_13_ARTIFACTS = [
    "study.json",
    "spec.lock.json",
    "freeze.json",
    "manifest.lock.json",
    "bootstrap.json",
    "metrics.json",
    "data_quality.csv",
    "events.csv",
    "baseline_summary.csv",
    "per_etf.csv",
    "monthly.csv",
    "direction.csv",
    "report.md",
]


def test_supported_validation_passes_guard(locked_spec: DaytradeSpec, temp_output_dir: Path) -> None:
    """Verify that a valid supported validation bundle passes all 23 checks and returns typed HoldoutAccessProof."""
    vdir = temp_output_dir / "validation_supported"
    expected_bundle_sha = create_mock_supported_validation_bundle(vdir, locked_spec, disposition="supported")

    proof = verify_holdout_access_prerequisites(vdir, locked_spec)
    assert isinstance(proof, HoldoutAccessProof)
    assert proof.spec_sha256 == locked_spec.sha256
    assert proof.validation_bundle_sha256 == expected_bundle_sha


@pytest.mark.parametrize("disposition", ["rejected", "inconclusive"])
def test_unsupported_validation_blocks_holdout(
    disposition: str, locked_spec: DaytradeSpec, temp_output_dir: Path
) -> None:
    """Verify that validation with 'inconclusive' or 'rejected' disposition blocks holdout access."""
    vdir = temp_output_dir / f"validation_{disposition}"
    create_mock_supported_validation_bundle(vdir, locked_spec, disposition=disposition)

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

    with pytest.raises(HoldoutAccessDeniedError, match="Production promotion eligible must be explicitly present and False"):
        verify_holdout_access_prerequisites(vdir, locked_spec)


@pytest.mark.parametrize("artifact_name", REQUIRED_13_ARTIFACTS)
def test_missing_single_artifact_blocks_holdout(
    artifact_name: str, locked_spec: DaytradeSpec, temp_output_dir: Path
) -> None:
    """Verify holdout guard blocks if any of the 13 required validation artifacts is deleted."""
    vdir = temp_output_dir / f"missing_{artifact_name.replace('.', '_')}"
    create_mock_supported_validation_bundle(vdir, locked_spec)
    (vdir / artifact_name).unlink()

    with pytest.raises(HoldoutAccessDeniedError):
        verify_holdout_access_prerequisites(vdir, locked_spec)


@pytest.mark.parametrize("artifact_name", REQUIRED_13_ARTIFACTS)
def test_tampered_single_artifact_blocks_holdout(
    artifact_name: str, locked_spec: DaytradeSpec, temp_output_dir: Path
) -> None:
    """Verify holdout guard blocks if any of the 13 required validation artifacts has tampered content."""
    vdir = temp_output_dir / f"tampered_{artifact_name.replace('.', '_')}"
    create_mock_supported_validation_bundle(vdir, locked_spec)
    with (vdir / artifact_name).open("a", encoding="utf-8") as f:
        f.write("\n# TAMPERED LINE\n")

    with pytest.raises(HoldoutAccessDeniedError, match="Checksum mismatch"):
        verify_holdout_access_prerequisites(vdir, locked_spec)


def test_bundle_sha_changes_if_artifact_modified(locked_spec: DaytradeSpec, temp_output_dir: Path) -> None:
    """Verify modifying any artifact changes the deterministic validation_bundle_sha256."""
    vdir1 = temp_output_dir / "bundle_orig"
    sha1 = create_mock_supported_validation_bundle(vdir1, locked_spec)

    vdir2 = temp_output_dir / "bundle_diff"
    create_mock_supported_validation_bundle(vdir2, locked_spec)
    (vdir2 / "report.md").write_text("# Different report content\n", encoding="utf-8")

    # Re-sign checksums
    checksum_lines = [
        f"{hashlib.sha256((vdir2 / fn).read_bytes()).hexdigest()}  {fn}"
        for fn in REQUIRED_13_ARTIFACTS
    ]
    (vdir2 / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    sha2 = hashlib.sha256((vdir2 / "checksums.sha256").read_bytes()).hexdigest()

    assert sha1 != sha2


@pytest.mark.parametrize("missing_field", [
    "spec_sha256",
    "evaluator_code_sha",
    "manifest_sha256",
    "evidence_confidence_cap",
    "production_promotion_eligible",
])
def test_missing_provenance_field_blocks_holdout(
    missing_field: str, locked_spec: DaytradeSpec, temp_output_dir: Path
) -> None:
    """Verify holdout guard blocks if study.json provenance lacks any required field."""
    vdir = temp_output_dir / f"missing_prov_{missing_field}"
    create_mock_supported_validation_bundle(vdir, locked_spec)
    study = json.loads((vdir / "study.json").read_text(encoding="utf-8"))
    del study["provenance"][missing_field]
    (vdir / "study.json").write_text(json.dumps(study, indent=2), encoding="utf-8")

    # Re-sign checksums so it passes checksum check and fails in provenance validation
    checksum_lines = [
        f"{hashlib.sha256((vdir / fn).read_bytes()).hexdigest()}  {fn}"
        for fn in REQUIRED_13_ARTIFACTS
    ]
    (vdir / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    with pytest.raises(
        HoldoutAccessDeniedError,
        match=f"({missing_field}.*missing|missing.*{missing_field}|missing or mismatch|must be explicitly present)",
    ):
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


def test_real_dual_partition_holdout_pipeline_on_disk(
    locked_spec: DaytradeSpec, tmp_path: Path
) -> None:
    """Verify true on-disk dual-partition holdout evaluation without custom_sessions injection (Blocker 6)."""
    fast_spec = dataclasses.replace(locked_spec, bootstrap_resamples=50)
    dataset_root = tmp_path / "dataset"
    pre_dir = dataset_root / "preholdout"
    holdout_dir = dataset_root / "holdout"
    (pre_dir / "bars").mkdir(parents=True, exist_ok=True)
    (holdout_dir / "bars").mkdir(parents=True, exist_ok=True)

    # Select 20 history sessions for preholdout and 2 target sessions for holdout
    all_pre_sessions = get_regular_trading_sessions(
        locked_spec.development.start, locked_spec.validation.end, exclude_early_closes=True
    )
    hist_sessions = all_pre_sessions[-20:]

    all_holdout_sessions = get_regular_trading_sessions(
        locked_spec.holdout.start, locked_spec.holdout.end, exclude_early_closes=True
    )
    holdout_sessions = all_holdout_sessions[:2]

    pre_source_files: dict[str, str] = {}
    holdout_source_files: dict[str, str] = {}

    for sym in fast_spec.universe:
        # Preholdout bars (20 sessions)
        pre_dfs = []
        base_px = 100.0
        for s_date in hist_sessions:
            df_sess = generate_synthetic_session_bars(
                sym, s_date, base_price=base_px, signal_09_59_close=base_px * 1.005, exit_15_59_close=base_px * 1.006
            )
            pre_dfs.append(df_sess)
            base_px = base_px * 1.006
        pre_cat_df = pd.concat(pre_dfs, ignore_index=True)
        pre_csv_path = pre_dir / "bars" / f"{sym}.csv"
        write_normalized_bars_csv(pre_csv_path, pre_cat_df)
        pre_source_files[f"bars/{sym}.csv"] = sha256_of_file(pre_csv_path)

        # Holdout bars (2 sessions: session 0 is strong event move, session 1 is mild baseline move)
        holdout_dfs = []
        for idx, s_date in enumerate(holdout_sessions):
            if idx == 0:
                df_h = generate_synthetic_session_bars(
                    sym, s_date, base_price=base_px, signal_09_59_close=base_px * 1.025, exit_15_59_close=base_px * 1.030
                )
            else:
                df_h = generate_synthetic_session_bars(
                    sym, s_date, base_price=base_px, signal_09_59_close=base_px * 1.001, exit_15_59_close=base_px * 1.002
                )
            holdout_dfs.append(df_h)
            base_px = base_px * 1.002
        holdout_cat_df = pd.concat(holdout_dfs, ignore_index=True)
        holdout_csv_path = holdout_dir / "bars" / f"{sym}.csv"
        write_normalized_bars_csv(holdout_csv_path, holdout_cat_df)
        holdout_source_files[f"bars/{sym}.csv"] = sha256_of_file(holdout_csv_path)

    # Preholdout manifest
    pre_manifest = DaytradeDatasetManifest(
        task_id=fast_spec.task_id,
        spec_sha256=fast_spec.sha256,
        partition="preholdout",
        provider="alpaca",
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        calendar="XNYS",
        timezone="America/New_York",
        universe=fast_spec.universe,
        start_date=fast_spec.context_anchor_date,
        end_date=fast_spec.validation.end,
        source_files=pre_source_files,
    )
    pre_manifest.manifest_sha256 = pre_manifest.compute_sha256()
    (pre_dir / "manifest.lock.json").write_text(json.dumps(pre_manifest.to_dict(), indent=2), encoding="utf-8")

    # Validation bundle
    val_dir = tmp_path / "val_bundle"
    create_mock_supported_validation_bundle(val_dir, fast_spec, disposition="supported")

    # Overwrite val_dir's manifest.lock.json with exact preholdout manifest and update freeze & study.json provenance
    (val_dir / "manifest.lock.json").write_text(json.dumps(pre_manifest.to_dict(), indent=2), encoding="utf-8")
    val_freeze = freeze_evaluation_state(
        spec_sha256=fast_spec.sha256,
        manifest_sha256=pre_manifest.manifest_sha256,
        require_clean=False,
    )
    (val_dir / "freeze.json").write_text(json.dumps(val_freeze.to_dict(), indent=2), encoding="utf-8")
    study_data = json.loads((val_dir / "study.json").read_text(encoding="utf-8"))
    study_data["provenance"]["manifest_sha256"] = pre_manifest.manifest_sha256
    study_data["provenance"]["evaluator_code_sha"] = val_freeze.evaluation_code_sha
    (val_dir / "study.json").write_text(json.dumps(study_data, indent=2), encoding="utf-8")

    # Re-sign validation checksums
    checksum_lines = [
        f"{hashlib.sha256((val_dir / fn).read_bytes()).hexdigest()}  {fn}"
        for fn in REQUIRED_13_ARTIFACTS
    ]
    (val_dir / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    # Verify holdout prerequisites to obtain proof
    proof = verify_holdout_access_prerequisites(val_dir, fast_spec)

    # Evaluator code sha for holdout manifest lineage
    val_eval_sha = val_freeze.evaluation_code_sha

    # Holdout manifest with lineage fields
    holdout_manifest = DaytradeDatasetManifest(
        task_id=fast_spec.task_id,
        spec_sha256=fast_spec.sha256,
        partition="holdout",
        provider="alpaca",
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        calendar="XNYS",
        timezone="America/New_York",
        universe=fast_spec.universe,
        start_date=fast_spec.holdout.start,
        end_date=fast_spec.holdout.end,
        source_files=holdout_source_files,
        acquisition_provenance={
            "status": "authorized_provider_acquisition",
            "provider": "alpaca",
            "feed": "sip",
        },
        preholdout_manifest_sha256=pre_manifest.manifest_sha256,
        validation_bundle_sha256=proof.validation_bundle_sha256,
        evaluator_code_sha=val_eval_sha,
    )
    holdout_manifest.manifest_sha256 = holdout_manifest.compute_sha256()
    (holdout_dir / "manifest.lock.json").write_text(json.dumps(holdout_manifest.to_dict(), indent=2), encoding="utf-8")

    # Execute evaluate_split with split_name="holdout", reading 100% directly from disk!
    res = evaluate_split(
        split_name="holdout",
        spec=fast_spec,
        dataset_root=dataset_root,
        validation_artifact_dir=val_dir,
    )

    assert res.split == "holdout"
    assert res.disposition in ("supported", "inconclusive", "rejected")
    assert res.provenance["validation_bundle_sha256"] == proof.validation_bundle_sha256

    summary = res.metrics["provider_provenance_summary"]
    assert summary["status"] == "authorized_provider_acquisition"
    assert summary["provider"] == holdout_manifest.provider
    assert summary["feed"] == holdout_manifest.feed
    assert summary["timeframe"] == holdout_manifest.timeframe
    assert summary["adjustment"] == holdout_manifest.adjustment
    assert summary["calendar"] == holdout_manifest.calendar
    assert summary["timezone"] == holdout_manifest.timezone

    # Verify all generated events and non-events belong to the holdout partition
    for ev in res.events:
        assert ev.split == "holdout"
        assert ev.session_date >= date(2026, 7, 1)

    for ne in res.non_events:
        assert ne.split == "holdout"
        assert ne.session_date >= date(2026, 7, 1)


def test_holdout_acquisition_raw_lineage_cannot_authorize_holdout(
    locked_spec: DaytradeSpec, tmp_path: Path
) -> None:
    """Raw lineage string arguments must not exist in API or authorize holdout."""
    dataset_root = tmp_path / "dataset"
    with pytest.raises((TypeError, HoldoutAccessDeniedError)):
        acquire_dataset_partition(  # type: ignore[call-arg]
            dataset_root=dataset_root,
            partition="holdout",
            spec=locked_spec,
            validation_bundle_sha="fake",
            preholdout_manifest_sha="fake",
            evaluator_code_sha="fake",
            execute_provider=True,
        )


def test_holdout_acquisition_missing_proof_fails_closed_zero_credential_reads_and_zero_calls(
    locked_spec: DaytradeSpec, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing proof fails closed before any credentials are read or provider client constructed."""
    dataset_root = tmp_path / "dataset"

    cred_reads: list[str] = []
    orig_env_get = os.environ.get

    def tracked_env_get(key: str, default: Any = None) -> Any:
        if "ALPACA" in key:
            cred_reads.append(key)
        return orig_env_get(key, default)

    monkeypatch.setattr(os.environ, "get", tracked_env_get)

    client_init_count = 0
    import tradex.research.daytrade_momentum.dataset as dataset_mod

    orig_client_init = dataset_mod.DatasetAlpacaClient.__init__

    def tracked_client_init(self: Any, *args: Any, **kwargs: Any) -> None:
        nonlocal client_init_count
        client_init_count += 1
        orig_client_init(self, *args, **kwargs)

    monkeypatch.setattr(dataset_mod.DatasetAlpacaClient, "__init__", tracked_client_init)

    with pytest.raises(HoldoutAccessDeniedError) as exc_info:
        acquire_dataset_partition(
            dataset_root=dataset_root,
            partition="holdout",
            spec=locked_spec,
            validation_artifact_dir=None,
            holdout_access_proof=None,
            execute_provider=True,
        )

    assert "strictly requires verified HoldoutAccessProof" in str(exc_info.value)
    assert len(cred_reads) == 0, f"Unexpected credential reads: {cred_reads}"
    assert client_init_count == 0, "Provider client must not be constructed"


def test_holdout_acquisition_valid_typed_proof_authorizes_acquisition(
    locked_spec: DaytradeSpec, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synthetic verified HoldoutAccessProof allows acquisition path to proceed to fake client."""
    dataset_root = tmp_path / "dataset"
    proof = HoldoutAccessProof(
        spec_sha256=locked_spec.sha256,
        manifest_sha256="test_manifest_sha256",
        evaluator_code_sha="test_eval_code_sha",
        validation_bundle_sha256="test_bundle_sha256",
    )

    class FakeAlpacaClient:
        max_retries = 1
        call_count = 0

        def get_bars(
            self, symbols: list[str], start_utc: Any, end_utc: Any, **kwargs: Any
        ) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
            self.call_count += 1
            sym = symbols[0]
            df = pd.DataFrame([{
                "datetime": pd.Timestamp("2026-07-01 13:30:00", tz="UTC"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000,
                "trade_count": 50,
                "vwap": 100.2,
                "symbol": sym,
            }])
            meta = {
                "pagination_complete": True,
                "next_page_token_present": False,
                "safe_error_classification": "none",
                "logical_calls": 1,
                "http_pages": 1,
                "http_attempts": 1,
                "retries": 0,
                "http_429s": 0,
                "http_errors": 0,
                "malformed_timestamp_counts": {sym: 0},
            }
            return {sym: df}, meta

    fake_client = FakeAlpacaClient()
    cred_reads: list[str] = []
    orig_env_get = os.environ.get

    def tracked_env_get(key: str, default: Any = None) -> Any:
        if "ALPACA" in key:
            cred_reads.append(key)
        return orig_env_get(key, default)

    monkeypatch.setattr(os.environ, "get", tracked_env_get)

    manifest = acquire_dataset_partition(
        dataset_root=dataset_root,
        partition="holdout",
        spec=locked_spec,
        client=fake_client,
        execute_provider=True,
        holdout_access_proof=proof,
    )

    assert isinstance(manifest, DaytradeDatasetManifest)
    assert manifest.partition == "holdout"
    assert manifest.preholdout_manifest_sha256 == proof.manifest_sha256
    assert manifest.validation_bundle_sha256 == proof.validation_bundle_sha256
    assert manifest.evaluator_code_sha == proof.evaluator_code_sha
    assert len(cred_reads) == 0, "No credentials should be read when client is injected"
    assert fake_client.call_count > 0, "Provider client should have been called"


def test_holdout_acquisition_forged_ordinary_dict_rejected(
    locked_spec: DaytradeSpec, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dictionary containing equivalent string fields must not be accepted as a proof."""
    dataset_root = tmp_path / "dataset"
    pseudo_proof = {
        "spec_sha256": locked_spec.sha256,
        "manifest_sha256": "fake_manifest",
        "evaluator_code_sha": "fake_code",
        "validation_bundle_sha256": "fake_bundle",
    }
    cred_reads: list[str] = []
    orig_env_get = os.environ.get

    def tracked_env_get(key: str, default: Any = None) -> Any:
        if "ALPACA" in key:
            cred_reads.append(key)
        return orig_env_get(key, default)

    monkeypatch.setattr(os.environ, "get", tracked_env_get)

    with pytest.raises(HoldoutAccessDeniedError) as exc_info:
        acquire_dataset_partition(
            dataset_root=dataset_root,
            partition="holdout",
            spec=locked_spec,
            holdout_access_proof=pseudo_proof,  # type: ignore[arg-type]
            execute_provider=True,
        )

    assert "must be an instance of HoldoutAccessProof" in str(exc_info.value)
    assert len(cred_reads) == 0
