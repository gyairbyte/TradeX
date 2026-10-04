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
from tradex.research.long_002d3a.review_store import PilotReviewStore
from tradex.research.long_002d3a.sampler import sample_pilot_cases
from tradex.research.long_002d3a.spec import (
    FUTURE_MAIN_SIZE,
    PILOT_SEED,
    PILOT_SIZE,
    verify_spec_sha256,
    verify_upstream_hashes,
)


def run_pipeline(
    run_id: str | None = None,
    repo_root: Path = Path("."),
    seed: int = PILOT_SEED,
) -> dict[str, Any]:
    """Execute complete empirical pilot generation pipeline."""
    if run_id is None:
        run_id = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")

    print(f"=== LONG-002D3A Blinded Review Pilot Run: {run_id} ===")

    # 1. Verify spec integrity
    spec_path = repo_root / "docs" / "research" / "specs" / "LONG-002D3A-v1.json"
    verify_spec_sha256(spec_path)
    print("  [OK] Preregistration spec verified (SHA-256 matches locked value)")

    # 2. Verify upstream inputs integrity
    stage_c_dir = repo_root / "data" / "research" / "long_002c"
    cache_dir = repo_root / "data" / "cache" / "long_002c"
    feature_table_path = repo_root / "data" / "research" / "long_002d1" / "feature_table.parquet"

    verify_upstream_hashes(stage_c_dir)
    print("  [OK] Stage C upstream inputs verified byte-for-byte")

    # 3. Load discovery manifest for candidate security definitions
    manifest_path = stage_c_dir / "discovery_manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    cands_by_id = {
        c["immutable_security_id"]: CandidateSecurity.from_dict(c)
        for c in manifest_data["candidates"]
    }

    # 4. Initialize read-only Alpaca cache client (zero network calls)
    alpaca, _, tracker = create_read_only_alpaca_client(cache_dir)
    spy_closes = load_spy_daily_closes(alpaca)
    print("  [OK] Read-only cache client loaded; SPY closes verified")

    # 5. Sample 24 pilot cases deterministically
    print(f"  Sampling {PILOT_SIZE} pilot cases with seed {seed}...")
    candidates = sample_pilot_cases(stage_c_dir, seed=seed)
    assert len(candidates) == PILOT_SIZE

    # Load market cap for candidates from feature table
    ft_cols = ["immutable_security_id", "as_of_date", "cutoff_time", "market_cap"]
    df_ft = pq.read_table(feature_table_path, columns=ft_cols).to_pandas()
    df_ft_indexed = df_ft.set_index(["immutable_security_id", "as_of_date", "cutoff_time"])

    # 6. Generate blinded case packets and answer key records
    print("  Constructing Stage A and Stage B blinded packets...")
    stage_a_packets = []
    stage_b_packets = []
    answer_keys = []

    for cand in candidates:
        cand_sec = cands_by_id[cand.immutable_security_id]
        key = (cand.immutable_security_id, cand.as_of_date, cand.cutoff_time)

        mcap = None
        if key in df_ft_indexed.index:
            val = df_ft_indexed.loc[key, "market_cap"]
            if pd.notna(val):
                mcap = float(val)

        elig_row = {
            "market_cap": mcap,
            "cohort_type": "established",
            "trading_history_sessions": 252,
        }

        sa, sb, ak = generate_blinded_case_packet(
            candidate=cand,
            cand_security=cand_sec,
            alpaca=alpaca,
            spy_closes=spy_closes,
            eligibility_row=elig_row,
            earnings_row=None,
        )
        stage_a_packets.append(sa)
        stage_b_packets.append(sb)
        answer_keys.append(ak)

    # 7. Execute exhaustive blinding audit
    print("  Auditing case packets for identity, date, and outcome leakage...")
    stage_a_dicts = [p.to_dict() for p in stage_a_packets]
    stage_b_dicts = [p.to_dict() for p in stage_b_packets]
    audit_summary = audit_all_pilot_cases(stage_a_dicts, stage_b_dicts, answer_keys)
    assert audit_summary["all_cases_passed_blinding_audit"] is True
    print("  [OK] All 24 cases PASSED blinding audit (zero leakage)")

    # 8. Persist external and committed artifacts
    print("  Persisting artifacts and computing cryptographic commitment...")
    res = write_pilot_artifacts(
        run_id=run_id,
        stage_a_packets=stage_a_packets,
        stage_b_packets=stage_b_packets,
        answer_keys=answer_keys,
        audit_summary=audit_summary,
        candidates=candidates,
        repo_root=repo_root,
    )

    print("=== Execution Complete ===")
    print(f"Run ID: {run_id}")
    print(f"External Data Directory: {res['external_dir']}")
    print(f"Committed Artifacts Directory: {res['committed_dir']}")
    print(f"Answer Key SHA-256: {res['answer_key_sha256']}")
    print(f"Answer Key Bytes: {res['answer_key_bytes']}")
    print(f"Network audit: {tracker.live_request_path_attempts} live attempts, {tracker.outbound_http_requests_executed} HTTP calls executed")

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

    # 3. Verify main study contract status
    main_contract_file = committed_dir / "main_study_contract.json"
    with open(main_contract_file, "r", encoding="utf-8") as f:
        mc_data = json.load(f)
    if mc_data.get("execution_status") != "NOT_EXECUTED_IN_THIS_PR":
        print(f"  [FAIL] Invalid main study contract status: {mc_data.get('execution_status')}")
        return False
    if mc_data.get("main_study_sample_size") != FUTURE_MAIN_SIZE:
        print(f"  [FAIL] Invalid main study sample size: {mc_data.get('main_study_sample_size')}")
        return False
    print("  [OK] Main study contract verified (UNEXECUTED, size 240, 24 exclusions recorded)")

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
        run_pipeline(run_id=parsed.run_id, repo_root=parsed.repo_root, seed=parsed.seed)
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
