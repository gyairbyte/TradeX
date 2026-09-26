"""End-to-end synthetic proof test for the DAYTRADE-001C reversal pipeline via CLI."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tradex.research.daytrade_reversal.artifacts import sha256_of_file, write_artifact_bundle
from tradex.research.daytrade_reversal.calendar import get_regular_trading_sessions
from tradex.research.daytrade_reversal.cli import main
from tradex.research.daytrade_reversal.freeze import EvaluationFreezeRecord
from tradex.research.daytrade_reversal.models import GateEvaluationResult, StudyResult
from tradex.research.daytrade_reversal.spec import load_and_verify_spec


class MockDatasetAlpacaClient:
    """Mock DatasetAlpacaClient that returns synthetic 1-minute bars with realistic structure."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.max_retries = kwargs.get("max_retries", 1)
        self.request_count = 0

    def get_bars(
        self,
        symbols: list[str],
        start_utc: datetime,
        end_utc: datetime,
        feed: str,
        timeframe: str,
        adjustment: str,
        max_pages: int | None = None,
    ) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
        self.request_count += 1

        # Get all regular sessions in the requested month chunk
        sessions = get_regular_trading_sessions(start_utc.date(), end_utc.date(), exclude_early_close=True)
        if start_utc.month == 9 and start_utc.year == 2025:
            selected_sessions = sessions[-20:] if ("AAPL" in symbols and len(sessions) >= 20) else (sessions[:1] if sessions else [])
        elif start_utc.month == 10 and start_utc.year == 2025:
            selected_sessions = sessions[:2]
        else:
            selected_sessions = sessions[:1] if sessions else []

        dfs: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            frames: list[pd.DataFrame] = []
            for sess_d in selected_sessions:
                times = pd.date_range(
                    datetime(sess_d.year, sess_d.month, sess_d.day, 13, 30, tzinfo=UTC),
                    periods=390,
                    freq="1min",
                )
                base_p = 100.0
                opens = [base_p] * 390
                highs = [base_p + 0.10] * 390
                lows = [base_p - 0.10] * 390
                closes = [base_p] * 390
                volumes = [1000.0] * 390

                # On Oct 1, 2025 for symbol AAPL: introduce extreme reversal drop at minute 30
                if sess_d == date(2025, 10, 1) and symbol.upper() == "AAPL":
                    # Bar 30: drop -6%
                    opens[30] = 100.0
                    highs[30] = 100.0
                    lows[30] = 93.9
                    closes[30] = 94.0
                    # Bar 31-35: rebound
                    for m in range(31, 36):
                        opens[m] = 94.0 + (m - 30) * 0.6
                        highs[m] = opens[m] + 0.2
                        lows[m] = opens[m] - 0.1
                        closes[m] = opens[m] + 0.1

                df = pd.DataFrame(
                    {
                        "open": opens,
                        "high": highs,
                        "low": lows,
                        "close": closes,
                        "volume": volumes,
                    },
                    index=times,
                )
                df.index.name = "datetime"
                frames.append(df)

            dfs[symbol.upper()] = pd.concat(frames) if frames else pd.DataFrame()

        meta = {
            "logical_calls": 1,
            "http_pages": 1,
            "http_attempts": 1,
            "http_errors": 0,
            "safe_error_classification": "none",
            "pagination_complete": True,
            "malformed_timestamp_counts": {s.upper(): 0 for s in symbols},
        }
        return dfs, meta


def test_e2e_synthetic_pipeline_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise complete synthetic C2 pipeline flow through real CLI commands.

    Proves:
    1. Preholdout dataset acquisition via CLI (`build-dataset --split preholdout --execute-provider`).
    2. Code freeze via CLI (`freeze`).
    3. Development evaluation via CLI (`evaluate --split development`).
    4. Validation evaluation via CLI (`evaluate --split validation --freeze`).
    5. Non-supported validation bundle blocks holdout acquisition and holdout evaluation.
    6. Supported validation fixture authorizes holdout acquisition (`build-dataset --split holdout`).
    7. Preholdout partition is byte-for-byte immutable across holdout acquisition.
    8. Holdout manifest preserves full cryptographic lineage (`preholdout_manifest_sha256`,
       `validation_bundle_sha256`, `evaluator_code_sha`, `spec_sha256`, `acquisition_provenance`).
    9. Holdout evaluation via CLI (`evaluate --split holdout`) successfully loads September validation
       history from preholdout and evaluates holdout events immediately on October 1st.
    """
    spec = load_and_verify_spec()

    # Configure test environment
    monkeypatch.setenv("ALPACA_API_KEY", "mock_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "mock_secret")
    monkeypatch.setattr("tradex.research.daytrade_reversal.freeze.check_worktree_clean", lambda repo: True)
    monkeypatch.setattr("tradex.research.daytrade_reversal.cli.DatasetAlpacaClient", MockDatasetAlpacaClient)

    dataset_root = tmp_path / "dataset_root"
    artifacts_dir = tmp_path / "artifacts"
    dev_out = artifacts_dir / "development"
    val_out = artifacts_dir / "validation"
    freeze_dir = tmp_path / "freeze"

    # =========================================================================
    # Step 1: Preholdout dataset acquisition via CLI
    # =========================================================================
    rc = main([
        "build-dataset",
        "--dataset-root", str(dataset_root),
        "--split", "preholdout",
        "--execute-provider",
    ])
    assert rc == 0

    preholdout_dir = dataset_root / "preholdout"
    assert preholdout_dir.is_dir()
    pre_man_path = preholdout_dir / "manifest.lock.json"
    assert pre_man_path.is_file()

    pre_man_data = json.loads(pre_man_path.read_text(encoding="utf-8"))
    assert pre_man_data["partition"] == "preholdout"
    assert pre_man_data["study_id"] == "DAYTRADE-001B"
    assert pre_man_data["spec_sha256"] == spec.sha256
    assert len(pre_man_data["source_files"]) == len(spec.universe)
    assert "acquisition_provenance" in pre_man_data
    assert pre_man_data["acquisition_provenance"]["total_symbols"] == 30

    bars_files = list((preholdout_dir / "bars").glob("*.csv"))
    assert len(bars_files) == 30

    # Snapshot preholdout partition file hashes to prove immutability later
    preholdout_hashes_before = {
        str(p.relative_to(preholdout_dir)).replace("\\", "/"): sha256_of_file(p)
        for p in preholdout_dir.rglob("*")
        if p.is_file()
    }
    assert len(preholdout_hashes_before) == 31  # 30 bars + 1 manifest

    # =========================================================================
    # Step 2: Code freeze via CLI
    # =========================================================================
    rc = main([
        "freeze",
        "--dataset-root", str(dataset_root),
        "--output", str(freeze_dir),
    ])
    assert rc == 0
    freeze_path = freeze_dir / "freeze.json"
    assert freeze_path.is_file()

    freeze_data = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert freeze_data["manifest_sha256"] == pre_man_data["manifest_sha256"]
    assert freeze_data["spec_sha256"] == spec.sha256
    assert freeze_data["repository_clean"] is True

    # =========================================================================
    # Step 3: Development evaluation via CLI
    # =========================================================================
    rc = main([
        "evaluate",
        "--split", "development",
        "--dataset-root", str(dataset_root),
        "--output", str(dev_out),
    ])
    assert rc == 0
    assert (dev_out / "study.json").is_file()
    assert (dev_out / "checksums.sha256").is_file()
    assert (dev_out / "spec.lock.json").is_file()
    dev_study = json.loads((dev_out / "study.json").read_text(encoding="utf-8"))
    assert dev_study["split"] == "development"
    assert dev_study["task_id"] == "DAYTRADE-001B"

    # =========================================================================
    # Step 4: Validation evaluation via CLI (requires --freeze)
    # =========================================================================
    rc = main([
        "evaluate",
        "--split", "validation",
        "--freeze", str(freeze_path),
        "--dataset-root", str(dataset_root),
        "--output", str(val_out),
    ])
    assert rc == 0
    assert (val_out / "study.json").is_file()
    assert (val_out / "checksums.sha256").is_file()
    assert (val_out / "freeze.json").is_file()
    assert (val_out / "manifest.lock.json").is_file()
    assert (val_out / "spec.lock.json").is_file()
    assert (val_out / "report.md").is_file()

    val_study = json.loads((val_out / "study.json").read_text(encoding="utf-8"))
    assert val_study["split"] == "validation"
    assert val_study["task_id"] == "DAYTRADE-001B"
    # Clarification 2: Accept whatever disposition synthetic dataset produces
    assert val_study["disposition"] == "inconclusive"

    # =========================================================================
    # Step 5: Negative guardrails on inconclusive validation bundle
    # =========================================================================
    # Inconclusive validation must block holdout acquisition
    rc_build_blocked = main([
        "build-dataset",
        "--dataset-root", str(dataset_root),
        "--split", "holdout",
        "--execute-provider",
        "--validation-artifact-dir", str(val_out),
    ])
    assert rc_build_blocked == 2

    # Inconclusive validation must block holdout evaluation
    rc_eval_blocked = main([
        "evaluate",
        "--split", "holdout",
        "--dataset-root", str(dataset_root),
        "--validation-artifact-dir", str(val_out),
        "--output", str(tmp_path / "artifacts" / "holdout_blocked"),
    ])
    assert rc_eval_blocked == 2

    # =========================================================================
    # Step 6: Create supported validation bundle fixture for conditional holdout
    # =========================================================================
    supported_val_dir = artifacts_dir / "validation_supported"
    supported_freeze = EvaluationFreezeRecord.from_dict(freeze_data)
    supported_result = StudyResult(
        task_id="DAYTRADE-001B",
        split="validation",
        disposition="supported",
        disposition_step="step_5_support",
        disposition_reason="All synthetic gates passed in supported fixture",
        gates={
            "data_quality_gate": GateEvaluationResult("data_quality_gate", True, {}),
            "sample_gate": GateEvaluationResult("sample_gate", True, {}),
            "step_2_evidence_sufficiency": GateEvaluationResult("step_2_evidence_sufficiency", True, {}),
        },
        metrics={"event_count": 350},
        bootstrap={},
        provenance={
            "evidence_confidence_cap": "limited_but_usable_evidence",
            "production_promotion_eligible": False,
            "evaluator_code_sha": supported_freeze.evaluation_code_sha,
            "spec_sha256": spec.sha256,
            "manifest_sha256": pre_man_data["manifest_sha256"],
            "provider": "alpaca",
            "feed": "sip",
        },
    )
    write_artifact_bundle(
        output_dir=supported_val_dir,
        result=supported_result,
        spec=spec,
        freeze_record=supported_freeze,
        manifest_data=pre_man_data,
    )
    supported_val_bundle_sha = sha256_of_file(supported_val_dir / "checksums.sha256")

    # =========================================================================
    # Step 7: Authorized holdout acquisition via CLI
    # =========================================================================
    rc = main([
        "build-dataset",
        "--dataset-root", str(dataset_root),
        "--split", "holdout",
        "--execute-provider",
        "--validation-artifact-dir", str(supported_val_dir),
    ])
    assert rc == 0

    # =========================================================================
    # Step 8: Assert preholdout partition immutability (Clarification 5)
    # =========================================================================
    preholdout_hashes_after = {
        str(p.relative_to(preholdout_dir)).replace("\\", "/"): sha256_of_file(p)
        for p in preholdout_dir.rglob("*")
        if p.is_file()
    }
    assert preholdout_hashes_before == preholdout_hashes_after

    # =========================================================================
    # Step 9: Verify holdout partition and manifest lineage (Clarifications 1 & 3)
    # =========================================================================
    holdout_dir = dataset_root / "holdout"
    assert holdout_dir.is_dir()
    holdout_man_file = holdout_dir / "manifest.lock.json"
    assert holdout_man_file.is_file()

    holdout_man_data = json.loads(holdout_man_file.read_text(encoding="utf-8"))
    assert holdout_man_data["partition"] == "holdout"
    assert holdout_man_data["study_id"] == "DAYTRADE-001B"
    assert holdout_man_data["spec_sha256"] == spec.sha256
    assert holdout_man_data["preholdout_manifest_sha256"] == pre_man_data["manifest_sha256"]
    assert holdout_man_data["validation_bundle_sha256"] == supported_val_bundle_sha
    assert holdout_man_data["evaluator_code_sha"] == supported_freeze.evaluation_code_sha
    assert len(holdout_man_data["source_files"]) == len(spec.universe)
    assert "acquisition_provenance" in holdout_man_data
    assert holdout_man_data["acquisition_provenance"]["total_symbols"] == 30

    holdout_bars_files = list((holdout_dir / "bars").glob("*.csv"))
    assert len(holdout_bars_files) == 30

    # =========================================================================
    # Step 10: Holdout evaluation via CLI
    # =========================================================================
    holdout_out = artifacts_dir / "holdout"
    rc = main([
        "evaluate",
        "--split", "holdout",
        "--dataset-root", str(dataset_root),
        "--validation-artifact-dir", str(supported_val_dir),
        "--output", str(holdout_out),
    ])
    assert rc == 0
    assert (holdout_out / "study.json").is_file()
    assert (holdout_out / "checksums.sha256").is_file()
    assert (holdout_out / "freeze.json").is_file()
    assert (holdout_out / "manifest.lock.json").is_file()
    assert (holdout_out / "spec.lock.json").is_file()
    assert (holdout_out / "report.md").is_file()

    holdout_study = json.loads((holdout_out / "study.json").read_text(encoding="utf-8"))
    assert holdout_study["split"] == "holdout"
    assert holdout_study["task_id"] == "DAYTRADE-001B"
    assert holdout_study["provenance"]["evaluator_code_sha"] == supported_freeze.evaluation_code_sha
    assert holdout_study["provenance"]["manifest_sha256"] == holdout_man_data["manifest_sha256"]
    # Check that holdout evaluated events immediately (from September historical context)
    assert holdout_study["metrics"]["event_count"] >= 1
