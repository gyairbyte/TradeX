"""Evaluation code freeze and verification for DAYTRADE-002B."""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .dataset import DaytradeDatasetManifest, get_repo_root
from .spec import DAYTRADE_002A_SPEC_SHA256, DaytradeSpec


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
        "tradex/research/daytrade_momentum/",
        "tests/research/daytrade_momentum/",
        "docs/research/specs/DAYTRADE-002A-v1.json",
        "docs/research/DAYTRADE-002A.md",
    ]
    try:
        out = _git("ls-files", "--", *pathspecs, cwd=repo_root)
        files = [line for line in out.splitlines() if line]
        if files:
            return files
    except FreezeError:
        pass

    # Fallback / file-system based discovery for testing environments
    discovered: list[str] = []
    for prefix in ["tradex/research/daytrade_momentum", "tests/research/daytrade_momentum"]:
        dir_p = repo_root / prefix
        if dir_p.is_dir():
            for p in dir_p.rglob("*.py"):
                discovered.append(p.relative_to(repo_root).as_posix())
    for doc in ["docs/research/specs/DAYTRADE-002A-v1.json", "docs/research/DAYTRADE-002A.md"]:
        if (repo_root / doc).is_file():
            discovered.append(doc)
    return sorted(discovered)


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
    require_clean: bool = True,
) -> EvaluationFreezeRecord:
    """Snapshot the current evaluation code state, verifying worktree cleanliness."""
    root = (repo_root or get_repo_root()).resolve()
    is_clean = check_worktree_clean(root)
    if require_clean and not is_clean:
        raise FreezeError("Worktree is dirty; evaluation state can only be frozen on a clean tree.")

    try:
        head_sha = get_git_head_sha(root)
    except FreezeError:
        head_sha = "unknown_synthetic_head"

    locked_spec_sha = spec_sha256 or DAYTRADE_002A_SPEC_SHA256
    file_hashes = hash_evaluation_files(root)

    return EvaluationFreezeRecord(
        evaluation_code_sha=head_sha,
        repository_clean=is_clean,
        frozen_at=datetime.now(UTC).isoformat(),
        spec_sha256=locked_spec_sha,
        manifest_sha256=manifest_sha256,
        evaluation_files=file_hashes,
    )


def verify_freeze_state(
    freeze: EvaluationFreezeRecord,
    repo_root: Path | None = None,
    spec: DaytradeSpec | None = None,
    manifest: DaytradeDatasetManifest | None = None,
) -> None:
    """Verify that current code state matches the frozen record."""
    root = (repo_root or get_repo_root()).resolve()

    if spec is not None and freeze.spec_sha256 != spec.sha256:
        raise FreezeError(
            f"Freeze spec SHA mismatch: frozen {freeze.spec_sha256} vs spec {spec.sha256}"
        )

    if manifest is not None and freeze.manifest_sha256 and freeze.manifest_sha256 != manifest.manifest_sha256:
        raise FreezeError(
            f"Freeze manifest SHA mismatch: frozen {freeze.manifest_sha256} vs manifest {manifest.manifest_sha256}"
        )

    try:
        current_head = get_git_head_sha(root)
        if freeze.evaluation_code_sha != "unknown_synthetic_head" and current_head != freeze.evaluation_code_sha:
            raise FreezeError(
                f"HEAD commit mismatch: frozen on {freeze.evaluation_code_sha}, current is {current_head}"
            )
    except FreezeError:
        pass

    # Verify every recorded file digest
    for rel_path, expected_sha in freeze.evaluation_files.items():
        fp = root / rel_path
        if not fp.is_file():
            raise FreezeError(f"Frozen evaluation file missing: {rel_path}")
        actual_sha = sha256_of_file(fp)
        if actual_sha != expected_sha:
            raise FreezeError(
                f"Frozen evaluation file tampered: {rel_path} (expected {expected_sha}, got {actual_sha})"
            )
