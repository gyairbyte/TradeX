"""Artifacts persistence, cryptographic commitment, and CLI tests for LONG-002D3A."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tradex.research.long_002d3a.artifacts import compute_file_sha256
from tradex.research.long_002d3a.cli import open_viewer, verify_run
from tradex.research.long_002d3a.spec import SPEC_SHA256


@pytest.fixture
def repo_root() -> Path:
    return Path(".")


def test_committed_artifacts_exist_and_match_checksums(repo_root: Path) -> None:
    # Run ID generated during empirical pilot run
    run_id = "2026-10-04-131000"
    committed_dir = repo_root / "docs" / "research" / "artifacts" / "LONG-002D3A" / run_id
    if not committed_dir.exists():
        pytest.skip(f"Committed artifacts dir not found: {committed_dir}")

    checksum_file = committed_dir / "checksums.sha256"
    assert checksum_file.exists()

    with open(checksum_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) == 8, f"Expected 8 checksum entries, got {len(lines)}"

    for line in lines:
        expected_sha, fname = line.split(maxsplit=1)
        actual_sha = compute_file_sha256(committed_dir / fname)
        assert actual_sha == expected_sha, f"Checksum mismatch for {fname}"


def test_answer_key_commitment_matches_external_data(repo_root: Path) -> None:
    run_id = "2026-10-04-131000"
    committed_dir = repo_root / "docs" / "research" / "artifacts" / "LONG-002D3A" / run_id
    if not committed_dir.exists():
        pytest.skip(f"Committed artifacts dir not found: {committed_dir}")

    commitment_file = committed_dir / "answer_key_commitment.json"
    with open(commitment_file, "r", encoding="utf-8") as f:
        comm = json.load(f)

    assert comm["run_id"] == run_id
    assert comm["spec_sha256"] == SPEC_SHA256
    assert comm["row_count"] == 24
    assert comm["schema_version"] == "v1"

    ext_path = repo_root / comm["relative_external_path"]
    if ext_path.exists():
        actual_bytes = ext_path.stat().st_size
        actual_sha = compute_file_sha256(ext_path)
        assert actual_bytes == comm["byte_count"]
        assert actual_sha == comm["sha256"]

        with open(ext_path, "r", encoding="utf-8") as f:
            ak = json.load(f)
        assert len(ak.get("records", [])) == 24


def test_cli_verify_subcommand_succeeds(repo_root: Path) -> None:
    run_id = "2026-10-04-131000"
    committed_dir = repo_root / "docs" / "research" / "artifacts" / "LONG-002D3A" / run_id
    if not committed_dir.exists():
        pytest.skip(f"Committed artifacts dir not found: {committed_dir}")

    success = verify_run(run_id=run_id, repo_root=repo_root)
    assert success is True


def test_cli_verify_fails_on_tampered_checksum(repo_root: Path, tmp_path: Path) -> None:
    # Build a synthetic run with invalid checksum
    syn_artifacts = tmp_path / "docs" / "research" / "artifacts" / "LONG-002D3A" / "syn_run"
    syn_artifacts.mkdir(parents=True)

    fake_meta = syn_artifacts / "execution_metadata.json"
    fake_meta.write_text('{"task_id": "test"}', encoding="utf-8")

    fake_sums = syn_artifacts / "checksums.sha256"
    fake_sums.write_text("0000000000000000000000000000000000000000000000000000000000000000  execution_metadata.json\n", encoding="utf-8")

    success = verify_run(run_id="syn_run", repo_root=tmp_path)
    assert success is False


def test_cli_open_viewer_returns_valid_uri(repo_root: Path) -> None:
    run_id = "2026-10-04-131000"
    viewer_path = repo_root / "data" / "research" / "long_002d3a" / run_id / "pilot_blinded" / "index.html"
    if not viewer_path.exists():
        pytest.skip(f"External viewer not present at {viewer_path}")

    uri = open_viewer(run_id=run_id, repo_root=repo_root, no_browser=True)
    assert uri.startswith("file://")
    assert "pilot_blinded/index.html" in uri or "pilot_blinded\\index.html" in uri.replace("/", "\\")


def test_git_status_confirms_answer_key_is_ignored(repo_root: Path) -> None:
    run_id = "2026-10-04-131000"
    ext_answer_key = repo_root / "data" / "research" / "long_002d3a" / run_id / "pilot_answer_key.json"
    if not ext_answer_key.exists():
        pytest.skip("External answer key not present on disk")

    res = subprocess.run(
        ["git", "check-ignore", str(ext_answer_key)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, "External answer key must be gitignored!"
    assert "pilot_answer_key.json" in res.stdout
