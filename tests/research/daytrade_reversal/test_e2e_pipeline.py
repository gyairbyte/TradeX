"""End-to-end synthetic proof test for the DAYTRADE-001C reversal pipeline."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from tradex.research.daytrade_reversal.artifacts import sha256_of_file, write_artifact_bundle
from tradex.research.daytrade_reversal.calendar import (
    get_regular_trading_sessions,
)
from tradex.research.daytrade_reversal.dataset import (
    DaytradeDatasetManifest,
    load_private_dataset,
    write_normalized_bars_csv,
)
from tradex.research.daytrade_reversal.freeze import EvaluationFreezeRecord
from tradex.research.daytrade_reversal.models import GateEvaluationResult, StudyResult
from tradex.research.daytrade_reversal.spec import DaytradeSpec, load_and_verify_spec
from tradex.research.daytrade_reversal.study import (
    HoldoutAccessDeniedError,
    evaluate_split,
    load_and_evaluate_holdout,
)
from tradex.research.daytrade_reversal.synthetic import generate_synthetic_session_bars


def _create_synthetic_partition_data(
    partition_dir: Path,
    spec: DaytradeSpec,
    partition_name: str,
    start_date: str,
    end_date: str,
    preholdout_manifest_sha: str | None = None,
) -> DaytradeDatasetManifest:
    bars_dir = partition_dir / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)

    start_d = date.fromisoformat(start_date)
    end_d = date.fromisoformat(end_date)
    trading_days = get_regular_trading_sessions(start_d, end_d, exclude_early_close=True)

    # For fast deterministic test, write bars for the universe
    source_files: dict[str, str] = {}
    for ticker in spec.universe:
        all_bars: list[pd.DataFrame] = []
        # Sample trading days to keep test fast (e.g. first 5 and last 5)
        sampled_days = trading_days[:5] + trading_days[-5:] if len(trading_days) > 10 else trading_days
        for td in sampled_days:
            df = generate_synthetic_session_bars(ticker, td)
            all_bars.append(df)

        full_df = pd.concat(all_bars, ignore_index=True) if all_bars else pd.DataFrame()
        csv_path = bars_dir / f"{ticker}.csv"
        write_normalized_bars_csv(csv_path, full_df)
        rel_path = f"bars/{ticker}.csv"
        source_files[rel_path] = sha256_of_file(csv_path)

    manifest = DaytradeDatasetManifest(
        study_id="DAYTRADE-001B",
        spec_sha256=spec.sha256,
        partition=partition_name,
        provider="alpaca",
        feed="sip",
        timeframe="1Min",
        adjustment="split",
        session_calendar="XNYS",
        timezone="America/New_York",
        universe=list(spec.universe),
        start_date=start_date,
        end_date=end_date,
        source_files=source_files,
        preholdout_manifest_sha256=preholdout_manifest_sha,
    )
    manifest_dict = manifest.to_dict()
    man_file = partition_dir / "manifest.lock.json"
    man_file.write_text(json.dumps(manifest_dict, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def test_e2e_synthetic_pipeline_flow(tmp_path: Path, monkeypatch) -> None:
    """Prove the complete synthetic future C2 flow across preholdout and holdout."""
    spec = load_and_verify_spec()

    # 1. Set up synthetic dataset root outside repository
    dataset_root = tmp_path / "dataset_root"
    preholdout_dir = dataset_root / "preholdout"
    holdout_dir = dataset_root / "holdout"

    pre_manifest = _create_synthetic_partition_data(
        preholdout_dir,
        spec,
        partition_name="preholdout",
        start_date=spec.warmup.start,
        end_date=spec.validation.end,
    )
    pre_manifest_dict = pre_manifest.to_dict()
    pre_manifest_sha = pre_manifest_dict["manifest_sha256"]

    # 2. Freeze evaluator state
    freeze_rec = EvaluationFreezeRecord(
        evaluation_code_sha="deadbeef0123456789abcdef0123456789abcdef",
        repository_clean=True,
        frozen_at="2026-09-25T00:00:00Z",
        spec_sha256=spec.sha256,
        manifest_sha256=pre_manifest_sha,
        evaluation_files={},
    )
    monkeypatch.setattr("tradex.research.daytrade_reversal.study.verify_freeze_state", lambda *a, **kw: None)

    # 3. Load private dataset for development split
    dev_sessions, dev_dq = load_private_dataset(
        dataset_root=dataset_root,
        split_name="development",
        spec=spec,
    )
    assert len(dev_sessions) > 0
    assert len(dev_dq) > 0

    # 4. Evaluate development split and write artifacts
    dev_out = tmp_path / "artifacts" / "development"
    dev_result = evaluate_split(
        split_name="development",
        sessions=dev_sessions,
        spec=spec,
        data_quality_reports=dev_dq,
        freeze_record=freeze_rec,
        manifest_sha256=pre_manifest_sha,
    )
    write_artifact_bundle(
        output_dir=dev_out,
        result=dev_result,
        spec=spec,
        freeze_record=freeze_rec,
        manifest_data=pre_manifest_dict,
        data_quality_reports=dev_dq,
    )
    assert (dev_out / "checksums.sha256").is_file()
    assert (dev_out / "study.json").is_file()

    # 5. Load private dataset for validation split
    _val_sessions, val_dq = load_private_dataset(
        dataset_root=dataset_root,
        split_name="validation",
        spec=spec,
    )
    val_out = tmp_path / "artifacts" / "validation"

    # 6. Simulate validation disposition = "supported"
    val_prov = {
        "evidence_confidence_cap": "limited_but_usable_evidence",
        "production_promotion_eligible": False,
        "evaluator_code_sha": freeze_rec.evaluation_code_sha,
        "spec_sha256": spec.sha256,
        "manifest_sha256": pre_manifest_sha,
        "provider": "alpaca",
        "feed": "sip",
    }
    val_result = StudyResult(
        task_id="DAYTRADE-001B",
        split="validation",
        disposition="supported",
        disposition_step="step_5_support",
        disposition_reason="All synthetic gates passed",
        gates={
            "data_quality_gate": GateEvaluationResult("data_quality_gate", True, {}),
            "sample_gate": GateEvaluationResult("sample_gate", True, {}),
            "step_2_evidence_sufficiency": GateEvaluationResult("step_2_evidence_sufficiency", True, {}),
        },
        metrics={"event_count": 350},
        bootstrap={},
        provenance=val_prov,
    )
    write_artifact_bundle(
        output_dir=val_out,
        result=val_result,
        spec=spec,
        freeze_record=freeze_rec,
        manifest_data=pre_manifest_dict,
        data_quality_reports=val_dq,
    )

    # 7. Create separate holdout partition
    holdout_manifest = _create_synthetic_partition_data(
        holdout_dir,
        spec,
        partition_name="holdout",
        start_date=spec.holdout.start,
        end_date=spec.holdout.end,
        preholdout_manifest_sha=pre_manifest_sha,
    )
    assert holdout_manifest.preholdout_manifest_sha256 == pre_manifest_sha

    # 8. Load and evaluate holdout
    def holdout_data_loader():
        s, q = load_private_dataset(dataset_root, "holdout", spec)
        return s, q

    holdout_result = load_and_evaluate_holdout(
        validation_artifact_dir=val_out,
        spec=spec,
        holdout_loader=holdout_data_loader,
    )
    assert holdout_result.split == "holdout"
    assert holdout_result.task_id == "DAYTRADE-001B"

    # 9. Verify holdout access blocked if validation was inconclusive
    val_inconclusive_out = tmp_path / "artifacts" / "validation_inconclusive"
    val_inconclusive_result = StudyResult(
        task_id="DAYTRADE-001B",
        split="validation",
        disposition="inconclusive",
        disposition_step="step_2_evidence_sufficiency",
        disposition_reason="Insufficient sample",
        gates={"sample_gate": GateEvaluationResult("sample_gate", False, {})},
        provenance=val_prov,
    )
    write_artifact_bundle(
        output_dir=val_inconclusive_out,
        result=val_inconclusive_result,
        spec=spec,
        freeze_record=freeze_rec,
        manifest_data=pre_manifest_dict,
    )

    with pytest.raises(HoldoutAccessDeniedError, match="must be strictly 'supported'"):
        load_and_evaluate_holdout(
            validation_artifact_dir=val_inconclusive_out,
            spec=spec,
            holdout_loader=holdout_data_loader,
        )
