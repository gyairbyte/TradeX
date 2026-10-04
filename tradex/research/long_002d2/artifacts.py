"""Artifact generation and cryptographic checksum serialization for LONG-002D2."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tradex.research.long_002d2.models import (
    CandidateEvaluationResult,
    InputIntegrityAudit,
)
from tradex.research.long_002d2.spec import (
    EXPECTED_SPEC_SHA256,
    FROZEN_BASELINE_ID,
    FROZEN_BASELINE_TOP_10_CLEAN_RATE,
    FROZEN_BASELINE_TOP_10_COUNT,
    FROZEN_BASELINE_TOP_10_LIFT,
    FROZEN_BASELINE_TOP_25_CLEAN_RATE,
    FROZEN_BASELINE_TOP_25_COUNT,
    FROZEN_BASELINE_TOP_25_LIFT,
    PHASE,
    PROGRAM,
    TASK_ID,
)


def serialize_json_artifact(payload: Any, path: Path) -> str:
    """Serialize a Python structure to canonical formatted JSON and return its SHA-256."""
    text = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_d2_artifacts(
    run_id: str,
    output_dir: Path,
    preregistration_commit_sha: str,
    execution_code_sha: str,
    audit: InputIntegrityAudit,
    primary_result: CandidateEvaluationResult,
    challenger_result: CandidateEvaluationResult,
    execution_timing: dict[str, Any],
) -> dict[str, str]:
    """Generate and write all committed summary artifacts for LONG-002D2."""
    output_dir.mkdir(parents=True, exist_ok=True)
    checksums: dict[str, str] = {}

    # 1. execution_metadata.json
    metadata_payload = {
        "task_id": TASK_ID,
        "run_id": run_id,
        "execution_code_sha": execution_code_sha,
        "program": PROGRAM,
        "phase": PHASE,
        "title": "Incremental Ranking Value of Relative Volume Beyond Frozen VAM5",
        "classification": "research_only",
        "production_promotion_eligible": False,
        "approved_production_strategies": [],
        "preregistration": {
            "spec_sha256": EXPECTED_SPEC_SHA256,
            "preregistration_commit_sha": preregistration_commit_sha,
            "authorization": {
                "authorizer": "Gary Yang",
                "authorization_date": "2026-09-28",
                "scope": "development-only incremental-value study",
            },
        },
        "timing": execution_timing,
        "frozen_baseline_reference": {
            "comparator_id": FROZEN_BASELINE_ID,
            "formula": "0.5 * cross_sectional_momentum_5_pct + 0.5 * cross_sectional_atr_pct_14_pct",
            "top_10": {
                "count": FROZEN_BASELINE_TOP_10_COUNT,
                "clean_rate": FROZEN_BASELINE_TOP_10_CLEAN_RATE,
                "lift": FROZEN_BASELINE_TOP_10_LIFT,
            },
            "top_25": {
                "count": FROZEN_BASELINE_TOP_25_COUNT,
                "clean_rate": FROZEN_BASELINE_TOP_25_CLEAN_RATE,
                "lift": FROZEN_BASELINE_TOP_25_LIFT,
            },
        },
        "evaluated_candidates": [
            primary_result.feature_id,
            challenger_result.feature_id,
        ],
        "primary_status": primary_result.status,
    }
    p_meta = output_dir / "execution_metadata.json"
    checksums["execution_metadata.json"] = serialize_json_artifact(metadata_payload, p_meta)

    # 2. input_integrity.json
    audit_dict = asdict(audit)
    p_audit = output_dir / "input_integrity.json"
    checksums["input_integrity.json"] = serialize_json_artifact(audit_dict, p_audit)

    # 3. rerank_summary.json
    rerank_payload = {
        "primary_candidate": {
            "feature_id": primary_result.feature_id,
            "role": primary_result.role,
            "status": primary_result.status,
            "common_observations": primary_result.common_observations,
            "coverage_within_top_25": primary_result.coverage_within_top_25,
            "evaluation_dates_count": primary_result.evaluation_dates_count,
            "total_selected_count": primary_result.total_selected_count,
            "candidate_clean_count": primary_result.candidate_clean_count,
            "candidate_precision": primary_result.candidate_precision,
            "matched_vam5_clean_count": primary_result.matched_vam5_clean_count,
            "matched_vam5_precision": primary_result.matched_vam5_precision,
            "absolute_precision_delta": primary_result.absolute_precision_delta,
            "precision_ratio": primary_result.precision_ratio,
            "incremental_clean_events": primary_result.incremental_clean_events,
            "selection_overlap_count": primary_result.selection_overlap_count,
            "selection_overlap_rate": primary_result.selection_overlap_rate,
            "positive_annual_years_count": primary_result.positive_annual_years_count,
            "annual_breakdowns": [asdict(b) for b in primary_result.annual_breakdowns],
        },
        "secondary_challenger": {
            "feature_id": challenger_result.feature_id,
            "role": challenger_result.role,
            "status": challenger_result.status,
            "note": "Descriptive challenger only; did not alter primary status or produce an automatic winner",
            "common_observations": challenger_result.common_observations,
            "coverage_within_top_25": challenger_result.coverage_within_top_25,
            "evaluation_dates_count": challenger_result.evaluation_dates_count,
            "total_selected_count": challenger_result.total_selected_count,
            "candidate_clean_count": challenger_result.candidate_clean_count,
            "candidate_precision": challenger_result.candidate_precision,
            "matched_vam5_clean_count": challenger_result.matched_vam5_clean_count,
            "matched_vam5_precision": challenger_result.matched_vam5_precision,
            "absolute_precision_delta": challenger_result.absolute_precision_delta,
            "precision_ratio": challenger_result.precision_ratio,
            "incremental_clean_events": challenger_result.incremental_clean_events,
            "selection_overlap_count": challenger_result.selection_overlap_count,
            "selection_overlap_rate": challenger_result.selection_overlap_rate,
            "positive_annual_years_count": challenger_result.positive_annual_years_count,
            "annual_breakdowns": [asdict(b) for b in challenger_result.annual_breakdowns],
        },
    }
    p_rerank = output_dir / "rerank_summary.json"
    checksums["rerank_summary.json"] = serialize_json_artifact(rerank_payload, p_rerank)

    # 4. bootstrap_summary.json
    boot_payload = {
        "method": "paired_fixed_non_overlapping_calendar_block_bootstrap",
        "replicates": 1000,
        "seed": 20260928,
        "primary_candidate": {
            "feature_id": primary_result.feature_id,
            "bootstrap_21": asdict(primary_result.bootstrap_21),
            "bootstrap_42": asdict(primary_result.bootstrap_42),
        },
        "secondary_challenger": {
            "feature_id": challenger_result.feature_id,
            "bootstrap_21": asdict(challenger_result.bootstrap_21),
            "bootstrap_42": asdict(challenger_result.bootstrap_42),
        },
    }
    p_boot = output_dir / "bootstrap_summary.json"
    checksums["bootstrap_summary.json"] = serialize_json_artifact(boot_payload, p_boot)

    # 5. regime_diagnostic_summary.json
    regime_payload = {
        "diagnostic_feature": "spy_return_20",
        "method": "date_level_ranking_three_fixed_bins",
        "disclaimer": "Purely descriptive market-regime context diagnostic; did not filter securities, alter candidate direction, or affect primary status",
        "primary_candidate": {
            "feature_id": primary_result.feature_id,
            "regimes": [asdict(r) for r in primary_result.regime_breakdowns],
        },
        "secondary_challenger": {
            "feature_id": challenger_result.feature_id,
            "regimes": [asdict(r) for r in challenger_result.regime_breakdowns],
        },
    }
    p_regime = output_dir / "regime_diagnostic_summary.json"
    checksums["regime_diagnostic_summary.json"] = serialize_json_artifact(regime_payload, p_regime)

    # 6. checksums.sha256
    lines = [f"{sha}  {fname}\n" for fname, sha in sorted(checksums.items())]
    p_chk = output_dir / "checksums.sha256"
    p_chk.write_text("".join(lines), encoding="utf-8", newline="\n")

    return checksums
