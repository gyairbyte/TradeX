"""Command-line interface for LONG-002D3A Blinded Review Pilot.

Subcommands:
- run: Generate deterministic 24-case pilot sample, blinded packets, viewer, and safe artifacts.
- verify: Verify cryptographic commitments, checksums, and contract invariants.
- open-viewer: Launch the local static HTML reviewer in default browser.
- record-label: Submit and validate a reviewer label for Stage A or Stage B.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from tradex.research.long_002c.manifest import CandidateSecurity
from tradex.research.long_002d.loader import (
    create_read_only_alpaca_client,
    load_spy_daily_closes,
)
from tradex.research.long_002d3a.artifacts import (
    compute_file_sha256,
    write_pilot_artifacts,
)
from tradex.research.long_002d3a.audit import audit_all_pilot_cases
from tradex.research.long_002d3a.blinder import generate_blinded_case_packet
from tradex.research.long_002d3a.models import PilotCandidate
from tradex.research.long_002d3a.review_store import PilotReviewStore
from tradex.research.long_002d3a.spec import (
    CORR_SPEC_PATH,
    FUTURE_MAIN_SIZE,
    PILOT_SEED,
    PILOT_SIZE,
    SOURCE_PILOT_ANSWER_KEY_SHA256,
    SOURCE_PILOT_RUN_ID,
    SPEC_PATH,
    enforce_pilot_seed,
    verify_corr_spec_sha256,
    verify_source_answer_key,
    verify_spec_sha256,
    verify_stage_c_pit_hashes,
    verify_upstream_hashes,
)


def get_git_head_sha(repo_root: Path = Path(".")) -> str:
    """Return HEAD commit SHA using git rev-parse HEAD. Fail closed if unavailable."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        sha = res.stdout.strip()
        if len(sha) == 40 and all(c in "0123456789abcdefABCDEF" for c in sha):
            return sha.lower()
    except Exception as exc:
        raise RuntimeError(f"FAIL-CLOSED: Unable to determine git HEAD commit SHA: {exc}") from exc
    raise RuntimeError(f"FAIL-CLOSED: Invalid git HEAD commit SHA: '{sha}'")


def is_git_worktree_clean(repo_root: Path = Path(".")) -> bool:
    """Check if git working tree is clean. Fail closed if error."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return len(res.stdout.strip()) == 0
    except Exception as exc:
        raise RuntimeError(f"FAIL-CLOSED: Unable to check git status: {exc}") from exc


def reconstruct_candidates_from_source_answer_key(
    source_ak_path: Path,
) -> list[PilotCandidate]:
    """Reconstruct 24 PilotCandidate objects from the frozen source answer key.

    Enforces:
    - Never calls sampler.sample_pilot_cases().
    - Verifies source answer key SHA-256 matches locked hash.
    - Preserves exact 24 cases, case IDs (D3A-PILOT-001..024), and order.
    """
    verify_source_answer_key(source_ak_path)
    with open(source_ak_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("records", [])
    if len(records) != PILOT_SIZE:
        raise ValueError(f"Expected {PILOT_SIZE} records in source answer key, got {len(records)}")

    candidates: list[PilotCandidate] = []
    for i, r in enumerate(records):
        expected_cid = f"D3A-PILOT-{i+1:03d}"
        if r["case_id"] != expected_cid:
            raise ValueError(
                f"FAIL-CLOSED: Case ID ordering mismatch! Expected {expected_cid}, got {r['case_id']}"
            )
        cand = PilotCandidate(
            case_id=r["case_id"],
            sample_stratum=r["sample_stratum"],
            immutable_security_id=r["immutable_security_id"],
            as_of_date=r["decision_date"],
            cutoff_time=r["cutoff_time"],
            ticker_at_decision=r["ticker"],
            year=r["decision_date"][:4],
            episode_id=r.get("episode_id"),
            clean_target_reached=r.get("clean_target_reached", False),
            target_progress_ratio=r.get("target_progress_ratio", 0.0),
            near_miss=r.get("near_miss", False),
            adverse_excursion=r.get("adverse_excursion", False),
            mfe_pct=r.get("mfe_pct"),
            mae_pct=r.get("mae_pct"),
            time_to_target=r.get("time_to_target"),
        )
        candidates.append(cand)

    return candidates


def verify_exact_sample_equivalence(
    candidates: list[PilotCandidate],
    source_ak_path: Path,
) -> None:
    """Assert exact equality against frozen source answer key on all identifying fields."""
    with open(source_ak_path, "r", encoding="utf-8") as f:
        ak_data = json.load(f)
    records = ak_data.get("records", [])
    if len(candidates) != len(records):
        raise ValueError(
            f"SAMPLE EQUIVALENCE FAILURE: candidate count {len(candidates)} != source count {len(records)}"
        )

    for i, (c, r) in enumerate(zip(candidates, records)):
        if c.case_id != r["case_id"]:
            raise ValueError(f"SAMPLE EQUIVALENCE FAILURE at index {i}: case_id {c.case_id} != {r['case_id']}")
        if c.sample_stratum != r["sample_stratum"]:
            raise ValueError(f"SAMPLE EQUIVALENCE FAILURE at index {i}: stratum {c.sample_stratum} != {r['sample_stratum']}")
        if c.immutable_security_id != r["immutable_security_id"]:
            raise ValueError(f"SAMPLE EQUIVALENCE FAILURE at index {i}: sec_id {c.immutable_security_id} != {r['immutable_security_id']}")
        if c.as_of_date != r["decision_date"]:
            raise ValueError(f"SAMPLE EQUIVALENCE FAILURE at index {i}: date {c.as_of_date} != {r['decision_date']}")
        if c.cutoff_time != r["cutoff_time"]:
            raise ValueError(f"SAMPLE EQUIVALENCE FAILURE at index {i}: cutoff {c.cutoff_time} != {r['cutoff_time']}")
        if c.episode_id != r.get("episode_id"):
            raise ValueError(f"SAMPLE EQUIVALENCE FAILURE at index {i}: episode_id {c.episode_id} != {r.get('episode_id')}")


def load_pit_tables(stage_c_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load and index Stage C PIT evidence tables with strict duplicate and schema checks."""
    verify_stage_c_pit_hashes(stage_c_dir)

    de_path = stage_c_dir / "data_eligibility.parquet"
    sc_path = stage_c_dir / "security_classification_status.parquet"
    es_path = stage_c_dir / "earnings_schedule_status.parquet"

    # Required fields verification
    df_de = pq.read_table(de_path).to_pandas()
    df_sc = pq.read_table(sc_path).to_pandas()
    df_es = pq.read_table(es_path).to_pandas()

    req_de = [
        "immutable_security_id", "as_of_date", "cutoff_time", "market_cap",
        "trading_history_sessions", "cohort_type", "eligibility_passed",
        "rejection_reason_codes", "index_membership_verified",
    ]
    for col in req_de:
        if col not in df_de.columns:
            raise ValueError(f"Missing required field '{col}' in data_eligibility.parquet")

    req_sc = [
        "immutable_security_id", "as_of_date", "ticker_at_decision",
        "inferred_classification", "classification_status",
        "is_eligible_common_stock", "provenance_source",
    ]
    for col in req_sc:
        if col not in df_sc.columns:
            raise ValueError(f"Missing required field '{col}' in security_classification_status.parquet")

    req_es = [
        "immutable_security_id", "as_of_date", "cutoff_time",
        "schedule_status", "next_earnings_date", "announcement_timing",
        "sessions_to_earnings", "provenance_source",
    ]
    for col in req_es:
        if col not in df_es.columns:
            raise ValueError(f"Missing required field '{col}' in earnings_schedule_status.parquet")

    # Duplicate check for data_eligibility on (immutable_security_id, as_of_date, cutoff_time)
    if df_de.duplicated(subset=["immutable_security_id", "as_of_date", "cutoff_time"]).any():
        raise ValueError("FAIL-CLOSED: Duplicate keys detected in data_eligibility.parquet!")

    # Duplicate check for earnings_schedule_status on (immutable_security_id, as_of_date, cutoff_time)
    if df_es.duplicated(subset=["immutable_security_id", "as_of_date", "cutoff_time"]).any():
        raise ValueError("FAIL-CLOSED: Duplicate keys detected in earnings_schedule_status.parquet!")

    # Check security_classification_status for conflicting records per (immutable_security_id, as_of_date)
    sc_unique_class = df_sc.drop_duplicates(subset=["immutable_security_id", "as_of_date", "is_eligible_common_stock", "inferred_classification"])
    if sc_unique_class.duplicated(subset=["immutable_security_id", "as_of_date"]).any():
        raise ValueError("FAIL-CLOSED: Conflicting classification records in security_classification_status.parquet!")

    df_de_indexed = df_de.set_index(["immutable_security_id", "as_of_date", "cutoff_time"])
    df_sc_indexed = sc_unique_class.drop_duplicates(subset=["immutable_security_id", "as_of_date"]).set_index(["immutable_security_id", "as_of_date"])
    df_es_indexed = df_es.set_index(["immutable_security_id", "as_of_date", "cutoff_time"])

    return df_de_indexed, df_sc_indexed, df_es_indexed


def run_pipeline(
    run_id: str | None = None,
    repo_root: Path = Path("."),
    seed: int = PILOT_SEED,
    execution_code_sha: str | None = None,
    _allow_dirty_for_unit_tests: bool = False,
) -> dict[str, Any]:
    """Execute complete empirical pilot generation pipeline."""
    # 0. Enforce locked seed policy
    enforce_pilot_seed(seed)

    if run_id is None:
        run_id = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")

    print(f"=== LONG-002D3A Blinded Review Pilot Run: {run_id} ===")

    # 1. Verify spec and correction contract integrity
    spec_path = repo_root / "docs" / "research" / "specs" / "LONG-002D3A-v1.json"
    verify_spec_sha256(spec_path if spec_path.exists() else SPEC_PATH)
    print("  [OK] Preregistration spec verified (SHA-256 matches locked value)")

    corr_spec_path = repo_root / "docs" / "research" / "specs" / "LONG-002D3A-CORR-001.json"
    verify_corr_spec_sha256(corr_spec_path if corr_spec_path.exists() else CORR_SPEC_PATH)
    print("  [OK] CORR-001 correction contract verified (SHA-256 matches locked value)")

    # 2. Execution provenance verification (runtime HEAD is authoritative)
    runtime_sha = get_git_head_sha(repo_root)
    if not runtime_sha or len(runtime_sha) != 40:
        raise RuntimeError(f"FAIL-CLOSED: Unresolved or invalid runtime git HEAD SHA: '{runtime_sha}'")

    if execution_code_sha is not None and execution_code_sha.strip().lower() != runtime_sha.lower():
        raise RuntimeError(
            f"FAIL-CLOSED: Supplied execution_code_sha '{execution_code_sha}' does not match "
            f"authoritative runtime git HEAD SHA '{runtime_sha}'!"
        )

    git_sha = runtime_sha
    is_clean = is_git_worktree_clean(repo_root)
    if not is_clean and not _allow_dirty_for_unit_tests:
        raise RuntimeError(
            "FAIL-CLOSED: Git working tree is dirty! Official correction execution requires a clean worktree."
        )
    print(f"  [OK] Execution provenance verified (HEAD: {git_sha[:8]}, clean: {is_clean})")

    # 3. Verify upstream inputs and Stage C PIT evidence integrity
    stage_c_dir = repo_root / "data" / "research" / "long_002c"
    cache_dir = repo_root / "data" / "cache" / "long_002c"

    verify_upstream_hashes(stage_c_dir)
    print("  [OK] Stage C upstream inputs verified byte-for-byte")

    df_de_idx, df_sc_idx, df_es_idx = load_pit_tables(stage_c_dir)
    print("  [OK] Stage C PIT evidence tables verified and indexed")

    # 4. Load discovery manifest for candidate security definitions
    manifest_path = stage_c_dir / "discovery_manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    cands_by_id = {
        c["immutable_security_id"]: CandidateSecurity.from_dict(c)
        for c in manifest_data["candidates"]
    }

    # 5. Initialize read-only Alpaca cache client (zero network calls)
    alpaca, _, tracker = create_read_only_alpaca_client(cache_dir)
    spy_closes = load_spy_daily_closes(alpaca)
    print("  [OK] Read-only cache client loaded; SPY closes verified")

    # 6. Reconstruct the exact 24 pilot cases from frozen source answer key
    source_ak_path = repo_root / "data" / "research" / "long_002d3a" / SOURCE_PILOT_RUN_ID / "pilot_answer_key.json"
    print(f"  Reconstructing {PILOT_SIZE} cases from frozen source answer key ({source_ak_path})...")
    candidates = reconstruct_candidates_from_source_answer_key(source_ak_path)
    verify_exact_sample_equivalence(candidates, source_ak_path)
    print("  [OK] Exact sample equivalence confirmed (zero resampling, exact ordering preserved)")

    # 7. Generate blinded case packets with authentic Stage C PIT joins
    print("  Constructing Stage A and Stage B blinded packets...")
    stage_a_packets = []
    stage_b_packets = []
    answer_keys = []

    for cand in candidates:
        cand_sec = cands_by_id[cand.immutable_security_id]
        key_cutoff = (cand.immutable_security_id, cand.as_of_date, cand.cutoff_time)
        key_date = (cand.immutable_security_id, cand.as_of_date)

        if key_cutoff not in df_de_idx.index:
            raise KeyError(f"FAIL-CLOSED: Missing data eligibility for {cand.case_id}: {key_cutoff}")
        if key_date not in df_sc_idx.index:
            raise KeyError(f"FAIL-CLOSED: Missing classification for {cand.case_id}: {key_date}")
        if key_cutoff not in df_es_idx.index:
            raise KeyError(f"FAIL-CLOSED: Missing earnings status for {cand.case_id}: {key_cutoff}")

        de_row = df_de_idx.loc[key_cutoff].to_dict()
        sc_row = df_sc_idx.loc[key_date].to_dict()
        es_row = df_es_idx.loc[key_cutoff].to_dict()

        sa, sb, ak = generate_blinded_case_packet(
            candidate=cand,
            cand_security=cand_sec,
            alpaca=alpaca,
            spy_closes=spy_closes,
            eligibility_row=de_row,
            classification_row=sc_row,
            earnings_row=es_row,
        )
        stage_a_packets.append(sa)
        stage_b_packets.append(sb)
        answer_keys.append(ak)

    # 8. Execute exhaustive blinding audit (including company-name and viewer HTML checks)
    print("  Auditing case packets for identity, company-name, date, and outcome leakage...")
    stage_a_dicts = [p.to_dict() for p in stage_a_packets]
    stage_b_dicts = [p.to_dict() for p in stage_b_packets]

    audit_summary = audit_all_pilot_cases(
        stage_a_packets=stage_a_dicts,
        stage_b_packets=stage_b_dicts,
        answer_keys=answer_keys,
        cands_by_id=cands_by_id,
        viewer_html_text=None,
    )
    assert audit_summary["all_cases_passed_blinding_audit"] is True
    print("  [OK] All 24 cases PASSED blinding audit (zero leakage)")

    # 9. Persist external and committed artifacts
    print("  Persisting artifacts and computing cryptographic commitments...")
    res = write_pilot_artifacts(
        run_id=run_id,
        stage_a_packets=stage_a_packets,
        stage_b_packets=stage_b_packets,
        answer_keys=answer_keys,
        audit_summary=audit_summary,
        candidates=candidates,
        repo_root=repo_root,
        execution_code_sha=git_sha,
        git_worktree_clean_at_start=is_clean,
        source_pilot_run_id=SOURCE_PILOT_RUN_ID,
        source_pilot_answer_key_sha256=SOURCE_PILOT_ANSWER_KEY_SHA256,
    )

    # 10. Audit generated index.html viewer file directly on disk
    viewer_html_path = Path(res["external_dir"]) / "pilot_blinded" / "index.html"
    if viewer_html_path.exists():
        with open(viewer_html_path, "r", encoding="utf-8") as f:
            viewer_html_text = f.read()
        html_audit = audit_all_pilot_cases(
            stage_a_packets=stage_a_dicts,
            stage_b_packets=stage_b_dicts,
            answer_keys=answer_keys,
            cands_by_id=cands_by_id,
            viewer_html_text=viewer_html_text,
        )
        assert html_audit["all_cases_passed_blinding_audit"] is True
        print("  [OK] Viewer HTML PASSED full identity and company-name blinding audit")

    print("=== Execution Complete ===")
    print(f"Run ID: {run_id}")
    print(f"External Data Directory: {res['external_dir']}")
    print(f"Committed Artifacts Directory: {res['committed_dir']}")
    print(f"Source Answer Key SHA-256: {res['answer_key_sha256']}")
    print(f"Pilot Exclusion Keys SHA-256: {res['exclusion_keys_sha256']}")
    print(f"Network audit: {tracker.live_request_path_attempts} live attempts, {tracker.outbound_http_requests_executed} HTTP calls executed")
    if tracker.live_request_path_attempts != 0 or tracker.outbound_http_requests_executed != 0:
        raise RuntimeError(
            f"FAIL-CLOSED: Network isolation breach detected! {tracker.live_request_path_attempts} live attempts, "
            f"{tracker.outbound_http_requests_executed} HTTP calls executed."
        )

    return res


def verify_run(run_id: str, repo_root: Path = Path(".")) -> bool:
    """Verify cryptographic commitments, checksums, and contract invariants."""
    print(f"=== Verifying LONG-002D3A Run: {run_id} ===")
    committed_dir = repo_root / "docs" / "research" / "artifacts" / "LONG-002D3A" / run_id
    if not committed_dir.exists():
        print(f"ERROR: Committed artifacts directory not found: {committed_dir}")
        return False

    # 1. Verify checksums.sha256
    checksums_file = committed_dir / "checksums.sha256"
    if not checksums_file.exists():
        print(f"ERROR: Missing checksums.sha256 in {committed_dir}")
        return False

    with open(checksums_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    all_checksums_match = True
    for line in lines:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        expected_hash, fname = parts
        target_path = committed_dir / fname
        if not target_path.exists():
            print(f"  [FAIL] Missing artifact file: {fname}")
            all_checksums_match = False
            continue
        actual_hash = compute_file_sha256(target_path)
        if actual_hash != expected_hash:
            print(f"  [FAIL] Checksum MISMATCH for {fname}: expected {expected_hash}, got {actual_hash}")
            all_checksums_match = False
        else:
            print(f"  [OK] Checksum matches: {fname}")

    if not all_checksums_match:
        print("ERROR: Checksum verification failed!")
        return False

    # 2. Verify answer key commitment against external file if present locally
    commitment_file = committed_dir / "answer_key_commitment.json"
    with open(commitment_file, "r", encoding="utf-8") as f:
        commitment_data = json.load(f)

    ext_rel_path = commitment_data["relative_external_path"]
    ext_abs_path = repo_root / ext_rel_path
    if ext_abs_path.exists():
        print(f"  Checking external answer key: {ext_rel_path}...")
        actual_size = ext_abs_path.stat().st_size
        actual_hash = compute_file_sha256(ext_abs_path)
        if actual_size != commitment_data["byte_count"]:
            print(f"  [FAIL] Byte count mismatch: expected {commitment_data['byte_count']}, got {actual_size}")
            return False
        if actual_hash != commitment_data["sha256"]:
            print(f"  [FAIL] SHA-256 mismatch: expected {commitment_data['sha256']}, got {actual_hash}")
            return False
        with open(ext_abs_path, "r", encoding="utf-8") as f:
            ak_data = json.load(f)
        if len(ak_data.get("records", [])) != commitment_data["row_count"]:
            print(f"  [FAIL] Row count mismatch: expected {commitment_data['row_count']}, got {len(ak_data.get('records', []))}")
            return False
        print("  [OK] External answer key cryptographic commitment verified byte-for-byte!")
    else:
        print(f"  [INFO] External answer key not present on this machine (commitment {commitment_data['sha256'][:12]}... recorded).")

    # 3. Verify pilot exclusion commitment against external file if present locally
    exclusion_commitment_file = committed_dir / "pilot_exclusion_commitment.json"
    if exclusion_commitment_file.exists():
        with open(exclusion_commitment_file, "r", encoding="utf-8") as f:
            excl_comm = json.load(f)
        excl_ext_path = repo_root / excl_comm["relative_external_path"]
        if excl_ext_path.exists():
            print(f"  Checking external exclusion keys: {excl_comm['relative_external_path']}...")
            actual_excl_size = excl_ext_path.stat().st_size
            actual_excl_sha = compute_file_sha256(excl_ext_path)
            if actual_excl_size != excl_comm["byte_count"]:
                print(f"  [FAIL] Exclusion byte count mismatch: expected {excl_comm['byte_count']}, got {actual_excl_size}")
                return False
            if actual_excl_sha != excl_comm["sha256"]:
                print(f"  [FAIL] Exclusion SHA-256 mismatch: expected {excl_comm['sha256']}, got {actual_excl_sha}")
                return False
            with open(excl_ext_path, "r", encoding="utf-8") as f:
                excl_records = json.load(f)
            if len(excl_records) != excl_comm["record_count"]:
                print(f"  [FAIL] Exclusion record count mismatch: expected {excl_comm['record_count']}, got {len(excl_records)}")
                return False
            print("  [OK] External exclusion keys cryptographic commitment verified byte-for-byte!")

    # 4. Verify main study contract status and forward blinding hygiene
    main_contract_file = committed_dir / "main_study_contract.json"
    with open(main_contract_file, "r", encoding="utf-8") as f:
        mc_data = json.load(f)
    if mc_data.get("execution_status") != "NOT_EXECUTED_IN_THIS_PR":
        print(f"  [FAIL] Invalid main study contract status: {mc_data.get('execution_status')}")
        return False
    if mc_data.get("main_study_sample_size") != FUTURE_MAIN_SIZE:
        print(f"  [FAIL] Invalid main study sample size: {mc_data.get('main_study_sample_size')}")
        return False
    # Forward blinding hygiene: ensure raw keys are NOT present in committed contract for correction runs
    if run_id != SOURCE_PILOT_RUN_ID and "pilot_excluded_keys" in mc_data:
        print("  [FAIL] Raw pilot_excluded_keys found in committed main study contract!")
        return False
    print("  [OK] Main study contract verified (UNEXECUTED, size 240)")

    print("=== Verification Successful! ===")
    return True


def open_viewer(run_id: str, repo_root: Path = Path("."), no_browser: bool = False) -> str:
    """Locate and open the local static HTML reviewer."""
    viewer_path = repo_root / "data" / "research" / "long_002d3a" / run_id / "pilot_blinded" / "index.html"
    if not viewer_path.exists():
        raise FileNotFoundError(f"Viewer not found at {viewer_path}. Has pipeline been run for {run_id}?")

    file_uri = viewer_path.resolve().as_uri()
    print(f"Blinded Pilot Reviewer URL: {file_uri}")
    if not no_browser:
        webbrowser.open(file_uri)
    return file_uri


def record_label_cli(
    run_id: str,
    case_id: str,
    stage: str,
    label_input: str,
    repo_root: Path = Path("."),
    allow_overwrite: bool = False,
) -> None:
    """Record reviewer label via CLI."""
    review_dir = repo_root / "data" / "research" / "long_002d3a" / run_id / "reviews"
    store = PilotReviewStore(review_dir)

    # Parse input as file path or raw JSON string
    p = Path(label_input)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(label_input)

    data["case_id"] = case_id
    data["stage"] = stage
    if "submitted_at_utc" not in data:
        data["submitted_at_utc"] = datetime.now(UTC).isoformat()

    saved_path = store.save_label(data, allow_overwrite=allow_overwrite)
    print(f"Label saved successfully: {saved_path}")

    prog = store.get_progress()
    print(f"Current progress: Stage A: {prog['stage_a_labeled_count']}/24 | Stage B: {prog['stage_b_labeled_count']}/24 | Fully Reviewed: {prog['fully_reviewed_count']}/24")


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for LONG-002D3A CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m tradex.research.long_002d3a.cli",
        description="LONG-002D3A Blinded Review Pilot CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: run
    p_run = subparsers.add_parser("run", help="Generate pilot sample, packets, and artifacts")
    p_run.add_argument("--run-id", type=str, default=None, help="Optional run ID (defaults to UTC timestamp)")
    p_run.add_argument("--seed", type=int, default=PILOT_SEED, help="Random seed (defaults to 20261003)")
    p_run.add_argument("--repo-root", type=Path, default=Path("."), help="Path to repository root")

    # Subcommand: verify
    p_verify = subparsers.add_parser("verify", help="Verify run artifacts and commitments")
    p_verify.add_argument("--run-id", type=str, required=True, help="Run ID to verify")
    p_verify.add_argument("--repo-root", type=Path, default=Path("."), help="Path to repository root")

    # Subcommand: open-viewer
    p_view = subparsers.add_parser("open-viewer", help="Open local static HTML reviewer")
    p_view.add_argument("--run-id", type=str, required=True, help="Run ID to view")
    p_view.add_argument("--repo-root", type=Path, default=Path("."), help="Path to repository root")
    p_view.add_argument("--no-browser", action="store_true", help="Do not launch browser; print URI only")

    # Subcommand: record-label
    p_label = subparsers.add_parser("record-label", help="Submit reviewer label")
    p_label.add_argument("--run-id", type=str, required=True, help="Run ID")
    p_label.add_argument("--case-id", type=str, required=True, help="Case ID (e.g. D3A-PILOT-001)")
    p_label.add_argument("--stage", type=str, required=True, choices=["stage_a", "stage_b"], help="Review stage")
    p_label.add_argument("--label-json", type=str, required=True, help="JSON string or file path containing label")
    p_label.add_argument("--repo-root", type=Path, default=Path("."), help="Path to repository root")
    p_label.add_argument("--allow-overwrite", action="store_true", help="Allow overwriting existing label")

    return parser


def main(args: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.command == "run":
        run_pipeline(
            run_id=parsed.run_id,
            repo_root=parsed.repo_root,
            seed=parsed.seed,
        )
        return 0
    elif parsed.command == "verify":
        success = verify_run(run_id=parsed.run_id, repo_root=parsed.repo_root)
        return 0 if success else 1
    elif parsed.command == "open-viewer":
        open_viewer(run_id=parsed.run_id, repo_root=parsed.repo_root, no_browser=parsed.no_browser)
        return 0
    elif parsed.command == "record-label":
        record_label_cli(
            run_id=parsed.run_id,
            case_id=parsed.case_id,
            stage=parsed.stage,
            label_input=parsed.label_json,
            repo_root=parsed.repo_root,
            allow_overwrite=parsed.allow_overwrite,
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
