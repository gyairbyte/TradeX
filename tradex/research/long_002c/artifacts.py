"""Artifact serialization, Parquet dataset generation, and manifest writing for LONG-002C.

Writes row-level tabular datasets to gitignored data/research/long_002c/ and committed
safe summaries to docs/research/artifacts/LONG-002C/<run-id>/.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.research.long_002c.models import (
    BaselineComparatorOutput,
    DataEligibility,
    DataQualityCoverage,
    DecisionObservation,
    EarningsScheduleStatus,
    EpisodeMembership,
    ExclusionReasonRecord,
    MasterOpportunityEpisode,
    OutcomeLabelRecord,
    ProvenanceProviderRecord,
    SecurityClassificationStatus,
)
from tradex.research.long_002c.spec import REPO_ROOT


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_external_parquet_tables(
    output_dir: Path,
    observations: list[DecisionObservation],
    eligibilities: list[DataEligibility],
    classifications: list[SecurityClassificationStatus],
    outcomes: list[OutcomeLabelRecord],
    episodes: list[MasterOpportunityEpisode],
    memberships: list[EpisodeMembership],
    baselines: list[BaselineComparatorOutput],
    quality: list[DataQualityCoverage],
    provenance: list[ProvenanceProviderRecord],
    exclusions: list[ExclusionReasonRecord],
    earnings: list[EarningsScheduleStatus] | None = None,
) -> list[dict[str, Any]]:
    """Save all row-level entities to Parquet files in output_dir (gitignored) and return file metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    file_records: list[dict[str, Any]] = []

    tables: list[tuple[str, list[Any], str]] = [
        ("decision_observations.parquet", observations, "decision_observations"),
        ("data_eligibility.parquet", eligibilities, "data_eligibility"),
        ("security_classification_status.parquet", classifications, "security_classification_status"),
        ("earnings_schedule_status.parquet", earnings or [], "earnings_schedule_status"),
        ("outcome_matrix.parquet", outcomes, "outcome_label_records"),
        ("master_episodes.parquet", episodes, "master_opportunity_episodes"),
        ("constituent_memberships.parquet", memberships, "episode_membership"),
        ("baseline_comparator_outputs.parquet", baselines, "baseline_comparator_outputs"),
        ("data_quality_coverage.parquet", quality, "data_quality_coverage"),
        ("provenance_records.parquet", provenance, "provenance_provider_records"),
        ("exclusions.parquet", exclusions, "exclusions_and_reason_codes"),
    ]

    for filename, record_list, schema_name in tables:
        file_path = output_dir / filename
        dict_list = [r.to_dict() for r in record_list]
        df = pd.DataFrame(dict_list) if dict_list else pd.DataFrame()
        df.to_parquet(file_path, index=False)

        byte_count = file_path.stat().st_size
        sha256_hash = _file_sha256(file_path)
        try:
            rel_path_str = file_path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel_path_str = file_path.as_posix()

        file_records.append(
            {
                "relative_path": rel_path_str,
                "schema_name": schema_name,
                "row_count": len(dict_list),
                "byte_count": byte_count,
                "sha256": sha256_hash,
            }
        )

    return file_records


def write_committed_summaries(
    bundle_dir: Path,
    run_id: str,
    manifest_files: list[dict[str, Any]],
    observations: list[DecisionObservation],
    outcomes: list[OutcomeLabelRecord],
    episodes: list[MasterOpportunityEpisode],
    baselines: list[BaselineComparatorOutput],
    quality: list[DataQualityCoverage],
    provenance: list[ProvenanceProviderRecord],
    exclusions: list[ExclusionReasonRecord],
    feasibility_report: dict[str, Any],
    execution_metadata: dict[str, Any],
    winning_baseline: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Write committed JSON summary artifacts and checksums.sha256 to bundle_dir."""
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # 1. dataset_manifest.json
    manifest_path = bundle_dir / "dataset_manifest.json"
    manifest_data = {
        "task_id": "LONG-002C-EXEC-001",
        "run_id": run_id,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "external_files": manifest_files,
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    # 2. data_quality_report.json
    quality_path = bundle_dir / "data_quality_report.json"
    q_dicts = [q.to_dict() for q in quality]
    avg_comp = (
        sum(q["completeness_pct"] for q in q_dicts) / len(q_dicts) if q_dicts else 0.0
    )
    quality_summary = {
        "split_name": "development",
        "security_count": len(q_dicts),
        "average_completeness_pct": round(avg_comp, 2),
        "securities": q_dicts,
    }
    quality_path.write_text(json.dumps(quality_summary, indent=2), encoding="utf-8")

    # 3. outcome_census_summary.json
    outcome_path = bundle_dir / "outcome_census_summary.json"
    cells: dict[str, dict[str, Any]] = {}
    for target_pct, horizon in [
        (10.0, 5),
        (10.0, 10),
        (10.0, 21),
        (20.0, 5),
        (20.0, 10),
        (20.0, 21),
        (30.0, 5),
        (30.0, 10),
        (30.0, 21),
    ]:
        cell_key = f"+{int(target_pct)}%_{horizon}d"
        cell_recs = [
            o
            for o in outcomes
            if o.target_pct == target_pct and o.horizon_sessions == horizon
        ]
        n_tot = len(cell_recs)
        clean_cnt = sum(1 for o in cell_recs if o.clean_target_reached)
        gross_cnt = sum(1 for o in cell_recs if o.target_progress_ratio >= 1.0)
        near_cnt = sum(1 for o in cell_recs if o.near_miss)
        part_cnt = sum(1 for o in cell_recs if o.partial_move)
        adv_cnt = sum(1 for o in cell_recs if o.adverse_excursion)
        sust_cnt = sum(1 for o in cell_recs if o.sustained_target)

        cells[cell_key] = {
            "target_pct": target_pct,
            "horizon_sessions": horizon,
            "total_evaluated": n_tot,
            "clean_target_reached_count": clean_cnt,
            "clean_target_reached_rate": round(clean_cnt / n_tot, 6) if n_tot else 0.0,
            "gross_target_reached_count": gross_cnt,
            "gross_target_reached_rate": round(gross_cnt / n_tot, 6) if n_tot else 0.0,
            "near_miss_count": near_cnt,
            "partial_move_count": part_cnt,
            "adverse_excursion_count": adv_cnt,
            "sustained_target_count": sust_cnt,
        }

    # Dual reporting: raw vs actionable
    known_e_obs = [o for o in observations if o.earnings_schedule_status == "known"]
    unknown_e_obs = [o for o in observations if o.earnings_schedule_status == "unknown"]

    outcome_summary = {
        "nine_cells": cells,
        "dual_reporting": {
            "total_observations": len(observations),
            "raw_outcome_eligible_observations": sum(
                1 for o in observations if o.raw_outcome_eligible
            ),
            "earnings_schedule_known_count": len(known_e_obs),
            "earnings_schedule_unknown_count": len(unknown_e_obs),
            "actionable_eligible_count": sum(
                1 for o in observations if o.actionability_status == "eligible"
            ),
            "unavailable_earnings_unknown_count": sum(
                1
                for o in observations
                if o.actionability_status == "unavailable_earnings_unknown"
            ),
        },
    }
    outcome_path.write_text(json.dumps(outcome_summary, indent=2), encoding="utf-8")

    # 4. master_episodes_summary.json
    episodes_path = bundle_dir / "master_episodes_summary.json"
    ann_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {"10": 0, "20": 0, "30": 0}
    unique_secs = set()
    for ep in episodes:
        yr = ep.anchor_as_of_date[:4]
        ann_counts[yr] = ann_counts.get(yr, 0) + 1
        tier_counts[ep.max_target_tier_reached] = (
            tier_counts.get(ep.max_target_tier_reached, 0) + 1
        )
        unique_secs.add(ep.anchor_security_id)

    episodes_summary = {
        "total_episodes": len(episodes),
        "unique_anchor_securities": len(unique_secs),
        "annual_counts": ann_counts,
        "max_target_tier_counts": tier_counts,
        "average_constituent_observations": round(
            sum(ep.constituent_observation_count for ep in episodes) / len(episodes),
            2,
        )
        if episodes
        else 0.0,
    }
    episodes_path.write_text(json.dumps(episodes_summary, indent=2), encoding="utf-8")

    # 5. endpoint_feasibility_report.json
    feasibility_path = bundle_dir / "endpoint_feasibility_report.json"
    feasibility_path.write_text(
        json.dumps(feasibility_report, indent=2), encoding="utf-8"
    )

    # 6. baseline_census_summary.json
    baselines_path = bundle_dir / "baseline_census_summary.json"
    # Group baselines by comparator_id
    comp_groups: dict[str, list[BaselineComparatorOutput]] = {}
    for b in baselines:
        comp_groups.setdefault(b.comparator_id, []).append(b)

    baseline_metrics: dict[str, Any] = {}
    for cid, b_list in comp_groups.items():
        fam = b_list[0].comparator_family
        top_10_cnt = sum(1 for b in b_list if b.top_10_flag)
        top_25_cnt = sum(1 for b in b_list if b.top_25_flag)
        baseline_metrics[cid] = {
            "comparator_family": fam,
            "total_evaluations": len(b_list),
            "top_10_percentile_count": top_10_cnt,
            "top_25_percentile_count": top_25_cnt,
        }

    winner_id = (
        winning_baseline.get("winner_comparator_id", "simple_momentum_20")
        if winning_baseline
        else "simple_momentum_20"
    )
    baseline_summary = {
        "comparators": baseline_metrics,
        "empirically_selected_strongest_baseline": winner_id,
        "frozen_strongest_simple_baseline": winner_id,
        "selection_details": winning_baseline or {},
        "notes": "Baselines evaluated on common observations with repository default LongWeights() and selected via primary-endpoint decile lift.",
    }
    baselines_path.write_text(json.dumps(baseline_summary, indent=2), encoding="utf-8")

    # 7. exclusion_summary.json
    exclusion_path = bundle_dir / "exclusion_summary.json"
    cat_counts: dict[str, int] = {}
    code_counts: dict[str, int] = {}
    for ex in exclusions:
        cat_counts[ex.reason_category] = cat_counts.get(ex.reason_category, 0) + 1
        code_counts[ex.reason_code] = code_counts.get(ex.reason_code, 0) + 1

    exclusion_summary = {
        "total_exclusions": len(exclusions),
        "by_category": cat_counts,
        "by_reason_code": code_counts,
    }
    exclusion_path.write_text(json.dumps(exclusion_summary, indent=2), encoding="utf-8")

    # 8. provenance_summary.json
    provenance_path = bundle_dir / "provenance_summary.json"
    prov_dicts = [p.to_dict() for p in provenance]
    providers_used = sorted({p.provider_name for p in provenance})
    provenance_summary = {
        "total_requests": len(prov_dicts),
        "providers_used": providers_used,
        "records": prov_dicts,
    }
    provenance_path.write_text(json.dumps(provenance_summary, indent=2), encoding="utf-8")

    # 9. execution_metadata.json
    exec_path = bundle_dir / "execution_metadata.json"
    exec_path.write_text(json.dumps(execution_metadata, indent=2), encoding="utf-8")

    # 10. checksums.sha256
    checksums_path = bundle_dir / "checksums.sha256"
    files_to_hash = [
        manifest_path,
        quality_path,
        outcome_path,
        episodes_path,
        feasibility_path,
        baselines_path,
        exclusion_path,
        provenance_path,
        exec_path,
    ]
    checksum_lines: list[str] = []
    sha_map: dict[str, str] = {}
    for f in sorted(files_to_hash, key=lambda p: p.name):
        h = _file_sha256(f)
        sha_map[f.name] = h
        checksum_lines.append(f"{h}  {f.name}")

    checksums_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    sha_map["checksums.sha256"] = _file_sha256(checksums_path)

    return sha_map
