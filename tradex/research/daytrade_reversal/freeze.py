"""Evaluation code freeze and verification for DAYTRADE-001."""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .dataset import get_repo_root


class FreezeError(Exception):
    """Raised when evaluation code cannot be frozen or verified."""


@dataclass(frozen=True)
class EvaluationFreezeRecord:
    """Immutable record of the frozen evaluation code."""

    evaluation_code_sha: str
    repository_clean: bool
    frozen_at: str
    spec_sha256: str
    manifest_sha256: str | None
    evaluation_files: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationFreezeRecord:
        return cls(**data)


def _git(*args: str, cwd: Path | None = None) -> str:
    cmd = ["git", *args]
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FreezeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def check_worktree_clean(repo_root: Path) -> bool:
    """Return True if no tracked or untracked modifications exist in the worktree."""
    try:
        status = _git("status", "--porcelain", cwd=repo_root)
        return status == ""
    except FreezeError:
        return False


def get_git_head_sha(repo_root: Path) -> str:
    """Return the current git HEAD commit SHA."""
    return _git("rev-parse", "HEAD", cwd=repo_root)


def sha256_of_file(path: Path) -> str:
    """Return hex SHA-256 of file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def evaluation_file_paths(repo_root: Path) -> list[str]:
    """Return tracked paths comprising the locked evaluation code."""
    pathspecs = [
        "tradex/research/daytrade_reversal/",
        "tests/research/daytrade_reversal/",
        "docs/research/specs/DAYTRADE-001B-v1.json",
        "docs/research/DAYTRADE-001B.md",
    ]
    try:
        out = _git("ls-files", "--", *pathspecs, cwd=repo_root)
        return [line for line in out.splitlines() if line]
    except FreezeError:
        # Fallback for synthetic / isolated environments without full git index
        pkg = repo_root / "tradex" / "research" / "daytrade_reversal"
        if pkg.is_dir():
            return [p.relative_to(repo_root).as_posix() for p in pkg.glob("*.py")]
        return []


def hash_evaluation_files(repo_root: Path) -> dict[str, str]:
    """Compute SHA-256 for all tracked evaluation files."""
    digests: dict[str, str] = {}
    for rel in evaluation_file_paths(repo_root):
        p = repo_root / rel
        if p.is_file():
            digests[rel] = sha256_of_file(p)
    return digests


def freeze_evaluation_state(
    repo_root: Path | None = None,
    spec_sha256: str = "",
    manifest_sha256: str | None = None,
    frozen_at: datetime | None = None,
    require_clean: bool = True,
) -> EvaluationFreezeRecord:
    """Freeze current evaluation git HEAD, cleanliness, and source file hashes."""
    root = (repo_root or get_repo_root()).resolve()
    clean = check_worktree_clean(root)
    if require_clean and not clean:
        raise FreezeError(
            "Cannot freeze evaluation code: repository has uncommitted modifications or untracked files."
        )

    head = get_git_head_sha(root)
    file_hashes = hash_evaluation_files(root)
    at_str = (frozen_at or datetime.now(UTC)).isoformat()

    return EvaluationFreezeRecord(
        evaluation_code_sha=head,
        repository_clean=clean,
        frozen_at=at_str,
        spec_sha256=spec_sha256,
        manifest_sha256=manifest_sha256,
        evaluation_files=file_hashes,
    )


def verify_freeze_state(
    freeze_record: EvaluationFreezeRecord,
    repo_root: Path | None = None,
    require_clean: bool = True,
    require_manifest: bool = False,
) -> None:
    """Verify that current code state matches the frozen record.

    Fails closed if HEAD, worktree cleanliness, or file hashes differ.
    """
    root = (repo_root or get_repo_root()).resolve()
    current_head = get_git_head_sha(root)
    if current_head != freeze_record.evaluation_code_sha:
        raise FreezeError(
            f"Evaluator code SHA mismatch: frozen {freeze_record.evaluation_code_sha}, "
            f"current {current_head}"
        )

    if require_clean and not check_worktree_clean(root):
        raise FreezeError(
            "Evaluation code worktree is dirty (uncommitted modifications or untracked files exist)."
        )

    if require_manifest and not freeze_record.manifest_sha256:
        raise FreezeError("Evidence freeze record is missing required manifest_sha256.")

    for rel, expected_sha in freeze_record.evaluation_files.items():
        p = root / rel
        if not p.is_file():
            raise FreezeError(f"Frozen evaluation file missing: {rel}")
        actual_sha = sha256_of_file(p)
        if actual_sha != expected_sha:
            raise FreezeError(
                f"Frozen evaluation file hash mismatch for {rel}: "
                f"expected {expected_sha}, got {actual_sha}"
            )
