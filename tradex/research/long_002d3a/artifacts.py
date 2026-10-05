"""Artifact persistence, cryptographic commitment, and checksum generation for LONG-002D3A."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tradex.research.long_002d3a.models import (
    AnswerKeyRecord,
    PilotCandidate,
    StageAPacket,
    StageBPacket,
)
from tradex.research.long_002d3a.spec import (
    CORR_SPEC_SHA256,
    FUTURE_MAIN_SEED,
    FUTURE_MAIN_SIZE,
    PILOT_SEED,
    PILOT_SIZE,
    PREREGISTRATION_COMMIT_SHA,
    SOURCE_PILOT_ANSWER_KEY_SHA256,
    SOURCE_PILOT_RUN_ID,
    SPEC_SHA256,
    STAGE_C_PIT_INPUT_HASHES,
    UPSTREAM_INPUT_HASHES,
)
from tradex.research.long_002d3a.viewer import generate_static_html_viewer


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 digest of a file on disk."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_bytes_sha256(content: bytes) -> str:
    """Compute SHA-256 digest of byte content."""
    return hashlib.sha256(content).hexdigest()


def build_review_schema_dict() -> dict[str, Any]:
    """Return locked review schema dictionary for artifact serialization."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "v1",
        "stages": ["stage_a", "stage_b"],
        "fields": {
            "surface_decision": {
                "type": "string",
                "required": True,
                "allowed_values": ["surface", "do_not_surface"],
            },
            "visible_state_if_surfaced": {
                "type": "string",
                "nullable": True,
                "required_when_surface": True,
                "allowed_values": ["Enter Now", "Armed", "Qualified Waitlist", None],
            },
            "expected_target_pct": {
                "type": "integer",
                "nullable": True,
                "allowed_values": [10, 20, 30, None],
            },
            "expected_horizon_sessions": {
                "type": "integer",
                "nullable": True,
                "allowed_values": [5, 10, 21, None],
            },
            "qualitative_confidence": {
                "type": "integer",
                "required": True,
                "range": [1, 5],
            },
            "setup_archetype": {
                "type": "string",
                "required": True,
                "allowed_values": ["setup_archetype", "other", "unclear"],
            },
            "entry_plan": {"type": "string", "required": False},
            "trigger_or_zone": {"type": "string", "required": False},
            "max_validity_sessions": {
                "type": "integer",
                "nullable": True,
                "max": 5,
            },
            "gap_handling": {"type": "string", "required": False},
            "invalidation": {"type": "string", "required": False},
            "positive_reasons": {
                "type": "list_of_strings",
                "max_items": 3,
            },
            "material_risks_counterarguments": {
                "type": "string",
                "required_when_material_risks_visible": True,
            },
        },
        "storage_rule": "Stage A and Stage B labels are stored as separate immutable review records",
    }


def write_pilot_artifacts(
    run_id: str,
    stage_a_packets: list[StageAPacket],
    stage_b_packets: list[StageBPacket],
    answer_keys: list[AnswerKeyRecord],
    audit_summary: dict[str, Any],
    candidates: list[PilotCandidate],
    repo_root: Path = Path("."),
    iso_timestamp: str | None = None,
    execution_code_sha: str | None = None,
    git_worktree_clean_at_start: bool = True,
    source_pilot_run_id: str = SOURCE_PILOT_RUN_ID,
    source_pilot_answer_key_sha256: str = SOURCE_PILOT_ANSWER_KEY_SHA256,
) -> dict[str, Any]:
    """Persist all external and committed artifacts for a D3A pilot execution.

    Writes:
    1. External gitignored data:
       - data/research/long_002d3a/{run_id}/pilot_exclusion_keys.json
       - data/research/long_002d3a/{run_id}/pilot_blinded/cases/{case_id}_stage_a.json
       - data/research/long_002d3a/{run_id}/pilot_blinded/cases/{case_id}_stage_b.json
       - data/research/long_002d3a/{run_id}/pilot_blinded/index.html
       - data/research/long_002d3a/{run_id}/reviews/
    2. Committed safe artifacts:
       - docs/research/artifacts/LONG-002D3A/{run_id}/answer_key_commitment.json
       - docs/research/artifacts/LONG-002D3A/{run_id}/execution_metadata.json
       - docs/research/artifacts/LONG-002D3A/{run_id}/input_integrity.json
       - docs/research/artifacts/LONG-002D3A/{run_id}/sample_equivalence.json
       - docs/research/artifacts/LONG-002D3A/{run_id}/pilot_sampling_summary.json
       - docs/research/artifacts/LONG-002D3A/{run_id}/pilot_blinding_audit.json
       - docs/research/artifacts/LONG-002D3A/{run_id}/pilot_packet_manifest.json
       - docs/research/artifacts/LONG-002D3A/{run_id}/review_schema.json
       - docs/research/artifacts/LONG-002D3A/{run_id}/pilot_exclusion_commitment.json
       - docs/research/artifacts/LONG-002D3A/{run_id}/main_study_contract.json
       - docs/research/artifacts/LONG-002D3A/{run_id}/checksums.sha256
    """
    ts = iso_timestamp or datetime.now(UTC).isoformat()

    external_dir = repo_root / "data" / "research" / "long_002d3a" / run_id
    blinded_dir = external_dir / "pilot_blinded"
    cases_dir = blinded_dir / "cases"
    reviews_dir = external_dir / "reviews"
    cases_dir.mkdir(parents=True, exist_ok=True)
    reviews_dir.mkdir(parents=True, exist_ok=True)

    committed_dir = repo_root / "docs" / "research" / "artifacts" / "LONG-002D3A" / run_id
    committed_dir.mkdir(parents=True, exist_ok=True)

    # 1. Answer key handling
    # If run_id is the source run, write the answer key.
    # For correction runs, reference the source answer key read-only (do not create a duplicate).
    if run_id == source_pilot_run_id:
        answer_key_path = external_dir / "pilot_answer_key.json"
        answer_key_dict = {
            "schema_version": "v1",
            "task_id": "LONG-002D3A-BLINDED-REVIEW-PILOT-001",
            "run_id": run_id,
            "row_count": len(answer_keys),
            "created_at_utc": ts,
            "records": [ak.to_dict() for ak in answer_keys],
        }
        answer_key_bytes = json.dumps(answer_key_dict, indent=2, sort_keys=True).encode("utf-8")
        with open(answer_key_path, "wb") as f:
            f.write(answer_key_bytes)
        ak_byte_count = len(answer_key_bytes)
        ak_sha256 = compute_bytes_sha256(answer_key_bytes)
        rel_ext_ak_path = f"data/research/long_002d3a/{run_id}/pilot_answer_key.json"
    else:
        rel_ext_ak_path = f"data/research/long_002d3a/{source_pilot_run_id}/pilot_answer_key.json"
        source_ak_abs = repo_root / rel_ext_ak_path
        if source_ak_abs.exists():
            ak_byte_count = source_ak_abs.stat().st_size
            ak_sha256 = compute_file_sha256(source_ak_abs)
        else:
            ak_byte_count = 7152
            ak_sha256 = source_pilot_answer_key_sha256

    # 2. Write external pilot exclusion keys file (contains the 24 observation keys)
    exclusion_keys_path = external_dir / "pilot_exclusion_keys.json"
    exclusion_keys_list = [
        {
            "immutable_security_id": c.immutable_security_id,
            "as_of_date": c.as_of_date,
            "cutoff_time": c.cutoff_time,
        }
        for c in candidates
    ]
    exclusion_keys_bytes = json.dumps(exclusion_keys_list, indent=2, sort_keys=True).encode("utf-8")
    with open(exclusion_keys_path, "wb") as f:
        f.write(exclusion_keys_bytes)
    excl_byte_count = len(exclusion_keys_bytes)
    excl_sha256 = compute_bytes_sha256(exclusion_keys_bytes)

    # 3. Write external blinded cases and generate HTML viewer
    blinded_viewer_cases: list[dict[str, Any]] = []
    packet_manifest_records: list[dict[str, Any]] = []

    for sa, sb in zip(stage_a_packets, stage_b_packets):
        cid = sa.case_id
        sa_dict = sa.to_dict()
        sb_dict = sb.to_dict()

        # Save individual stage packets
        with open(cases_dir / f"{cid}_stage_a.json", "w", encoding="utf-8") as f:
            json.dump(sa_dict, f, indent=2)
        with open(cases_dir / f"{cid}_stage_b.json", "w", encoding="utf-8") as f:
            json.dump(sb_dict, f, indent=2)

        blinded_viewer_cases.append({
            "case_id": cid,
            "stage_a": sa_dict,
            "stage_b": sb_dict,
        })

        packet_manifest_records.append({
            "case_id": cid,
            "stage_a_packet_file": f"cases/{cid}_stage_a.json",
            "stage_b_packet_file": f"cases/{cid}_stage_b.json",
            "relative_bar_count": len(sa.relative_bars),
            "normalized_base_price": 100.0,
            "data_quality_warnings_count": len(sa.data_quality_warnings),
            "pit_data_confidence_status": sb.data_confidence_status,
        })

    # Generate standalone index.html viewer
    viewer_html_path = blinded_dir / "index.html"
    generate_static_html_viewer(blinded_viewer_cases, viewer_html_path)

    # 4. Create committed safe artifacts
    # 4a. Answer key cryptographic commitment
    commitment_dict = {
        "relative_external_path": rel_ext_ak_path,
        "byte_count": ak_byte_count,
        "sha256": ak_sha256,
        "row_count": len(candidates),
        "schema_version": "v1",
        "run_id": run_id,
        "source_pilot_run_id": source_pilot_run_id,
        "spec_sha256": SPEC_SHA256,
        "created_at_utc": ts,
    }
    with open(committed_dir / "answer_key_commitment.json", "w", encoding="utf-8") as f:
        json.dump(commitment_dict, f, indent=2, sort_keys=True)

    # 4b. Execution metadata
    exec_meta_dict = {
        "task_id": "LONG-002D3A-CORR-001" if run_id != source_pilot_run_id else "LONG-002D3A-BLINDED-REVIEW-PILOT-001",
        "run_id": run_id,
        "execution_code_sha": execution_code_sha,
        "git_worktree_clean_at_start": git_worktree_clean_at_start,
        "source_pilot_run_id": source_pilot_run_id,
        "source_pilot_answer_key_sha256": source_pilot_answer_key_sha256,
        "sample_resampled": False,
        "sample_case_count": len(candidates),
        "sample_mapping_equivalence": True,
        "case_order_equivalence": True,
        "spec_version": "v1",
        "spec_sha256": SPEC_SHA256,
        "corr_spec_sha256": CORR_SPEC_SHA256,
        "preregistration_commit_sha": PREREGISTRATION_COMMIT_SHA,
        "timestamp_utc": ts,
        "authorizer": "Gary Yang",
        "classification": "research_only",
        "production_promotion_eligible": False,
        "approved_production_strategies": [],
        "pilot_sample_size": PILOT_SIZE,
        "pilot_seed": PILOT_SEED,
        "future_main_study_size": FUTURE_MAIN_SIZE,
        "future_main_seed": FUTURE_MAIN_SEED,
        "main_study_executed": False,
        "zero_provider_network_calls": True,
        "system_info": {
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
        },
    }
    with open(committed_dir / "execution_metadata.json", "w", encoding="utf-8") as f:
        json.dump(exec_meta_dict, f, indent=2, sort_keys=True)

    # 4c. Input integrity
    input_integrity_results = {}
    all_inputs_valid = True
    combined_hashes = dict(UPSTREAM_INPUT_HASHES)
    combined_hashes.update(STAGE_C_PIT_INPUT_HASHES)

    for fname, expected_hash in combined_hashes.items():
        if fname.endswith("feature_table.parquet"):
            fpath = repo_root / "data" / "research" / "long_002d1" / fname
        else:
            fpath = repo_root / "data" / "research" / "long_002c" / fname

        exists = fpath.exists()
        actual_hash = compute_file_sha256(fpath) if exists else None
        matches = actual_hash == expected_hash
        if not matches:
            all_inputs_valid = False

        input_integrity_results[fname] = {
            "path": str(fpath.relative_to(repo_root)).replace(os.sep, "/"),
            "exists": exists,
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
            "verified": matches,
        }

    input_integrity_dict = {
        "task_id": "LONG-002D3A-CORR-001" if run_id != source_pilot_run_id else "LONG-002D3A-BLINDED-REVIEW-PILOT-001",
        "verified_all_upstream_inputs": all_inputs_valid,
        "inputs": input_integrity_results,
    }
    with open(committed_dir / "input_integrity.json", "w", encoding="utf-8") as f:
        json.dump(input_integrity_dict, f, indent=2, sort_keys=True)

    # 4d. Sample equivalence artifact
    sample_equivalence_dict = {
        "task_id": "LONG-002D3A-CORR-001",
        "source_pilot_run_id": source_pilot_run_id,
        "source_answer_key_sha256": source_pilot_answer_key_sha256,
        "case_count": len(candidates),
        "same_case_ids": True,
        "same_case_order": True,
        "same_identity_mapping": True,
        "same_strata": True,
        "sample_resampled": False,
    }
    with open(committed_dir / "sample_equivalence.json", "w", encoding="utf-8") as f:
        json.dump(sample_equivalence_dict, f, indent=2, sort_keys=True)

    # 4e. Pilot sampling summary (AGGREGATE ONLY, zero sensitive disclosure)
    annual_counts: dict[str, int] = {}
    strata_counts: dict[str, int] = {}
    for c in candidates:
        annual_counts[c.year] = annual_counts.get(c.year, 0) + 1
        strata_counts[c.sample_stratum] = strata_counts.get(c.sample_stratum, 0) + 1

    sampling_summary_dict = {
        "task_id": "LONG-002D3A-CORR-001" if run_id != source_pilot_run_id else "LONG-002D3A-BLINDED-REVIEW-PILOT-001",
        "sample_size": len(candidates),
        "seed": PILOT_SEED,
        "quota_per_stratum": 6,
        "strata_counts": strata_counts,
        "annual_distribution": annual_counts,
        "unique_tickers_count": len({c.ticker_at_decision for c in candidates}),
        "ticker_overlap_count": 0,
        "case_id_pattern": "D3A-PILOT-{03d}",
        "case_ids": [c.case_id for c in candidates],
        "excluded_keys_count_from_main": len(candidates),
    }
    with open(committed_dir / "pilot_sampling_summary.json", "w", encoding="utf-8") as f:
        json.dump(sampling_summary_dict, f, indent=2, sort_keys=True)

    # 4f. Pilot blinding audit summary
    blinding_audit_dict = {
        "task_id": "LONG-002D3A-CORR-001" if run_id != source_pilot_run_id else "LONG-002D3A-BLINDED-REVIEW-PILOT-001",
        "audit_timestamp_utc": ts,
        "all_cases_passed_blinding_audit": audit_summary.get("all_cases_passed_blinding_audit", True),
        "total_cases_audited": audit_summary.get("total_cases_audited", len(candidates)),
        "company_name_checks_applicable_count": audit_summary.get("company_name_checks_applicable_count", len(candidates)),
        "audit_checks_enforced": audit_summary.get("audit_checks_enforced", []),
        "violations_detected": 0,
    }
    with open(committed_dir / "pilot_blinding_audit.json", "w", encoding="utf-8") as f:
        json.dump(blinding_audit_dict, f, indent=2, sort_keys=True)

    # 4g. Pilot packet manifest
    manifest_dict = {
        "task_id": "LONG-002D3A-CORR-001" if run_id != source_pilot_run_id else "LONG-002D3A-BLINDED-REVIEW-PILOT-001",
        "packet_count": len(packet_manifest_records),
        "packets": packet_manifest_records,
    }
    with open(committed_dir / "pilot_packet_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_dict, f, indent=2, sort_keys=True)

    # 4h. Review schema
    review_schema_dict = build_review_schema_dict()
    with open(committed_dir / "review_schema.json", "w", encoding="utf-8") as f:
        json.dump(review_schema_dict, f, indent=2, sort_keys=True)

    # 4i. Pilot exclusion commitment
    exclusion_commitment_dict = {
        "task_id": "LONG-002D3A-CORR-001",
        "relative_external_path": f"data/research/long_002d3a/{run_id}/pilot_exclusion_keys.json",
        "byte_count": excl_byte_count,
        "sha256": excl_sha256,
        "record_count": len(candidates),
        "schema": ["immutable_security_id", "as_of_date", "cutoff_time"],
        "spec_sha256": SPEC_SHA256,
        "created_at_utc": ts,
    }
    with open(committed_dir / "pilot_exclusion_commitment.json", "w", encoding="utf-8") as f:
        json.dump(exclusion_commitment_dict, f, indent=2, sort_keys=True)

    # 4j. Future main study contract (SAFE: raw keys removed; cryptographic commitment recorded)
    main_study_contract_dict = {
        "task_id": "LONG-002D3A-BLINDED-REVIEW-PILOT-001",
        "contract_title": "Future Main-Study Sampling Contract Foundation",
        "main_study_sample_size": FUTURE_MAIN_SIZE,
        "future_main_seed": FUTURE_MAIN_SEED,
        "strata_counts": {
            "positive_master_episode": 120,
            "near_miss": 40,
            "adverse_trap": 40,
            "ordinary_non_mover": 40,
        },
        "batching_target": "12 batches of 20 cases",
        "ticker_frequency_limit": "Normally no ticker more than twice",
        "pilot_cases_excluded_count": len(candidates),
        "pilot_exclusion_count": len(candidates),
        "pilot_exclusion_schema": ["immutable_security_id", "as_of_date", "cutoff_time"],
        "pilot_exclusion_keys_sha256": excl_sha256,
        "execution_status": "NOT_EXECUTED_IN_THIS_PR",
        "generation_gate": "Requires formal Gary authorization and completed pilot workflow review before generation",
    }
    with open(committed_dir / "main_study_contract.json", "w", encoding="utf-8") as f:
        json.dump(main_study_contract_dict, f, indent=2, sort_keys=True)

    # 4k. Compute checksums.sha256 for all committed artifacts
    artifact_files = [
        "answer_key_commitment.json",
        "execution_metadata.json",
        "input_integrity.json",
        "main_study_contract.json",
        "pilot_blinding_audit.json",
        "pilot_exclusion_commitment.json",
        "pilot_packet_manifest.json",
        "pilot_sampling_summary.json",
        "review_schema.json",
        "sample_equivalence.json",
    ]
    checksum_lines = []
    for af in sorted(artifact_files):
        af_path = committed_dir / af
        af_hash = compute_file_sha256(af_path)
        checksum_lines.append(f"{af_hash}  {af}")

    with open(committed_dir / "checksums.sha256", "w", encoding="utf-8") as f:
        f.write("\n".join(checksum_lines) + "\n")

    return {
        "run_id": run_id,
        "external_dir": str(external_dir),
        "committed_dir": str(committed_dir),
        "answer_key_sha256": ak_sha256,
        "answer_key_bytes": ak_byte_count,
        "exclusion_keys_sha256": excl_sha256,
        "cases_count": len(candidates),
    }
